import contextlib
import io
import json
import os
import sys
import tempfile
import time as _time
import unittest
from pathlib import Path
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from scripts import provider_registry, search


class ProviderRegistryTests(unittest.TestCase):
    def test_registry_covers_all_configured_providers(self):
        for provider in search.DEFAULT_CONFIG["auto_routing"]["provider_priority"]:
            self.assertIn(provider, provider_registry.PROVIDER_SPECS)
        self.assertIn("serpbase", provider_registry.PROVIDER_SPECS)

    def test_default_priority_excludes_serpbase(self):
        self.assertNotIn("serpbase", provider_registry.DEFAULT_PROVIDER_PRIORITY)
        self.assertFalse(provider_registry.PROVIDER_SPECS["serpbase"].auto_allowed_by_default)

    def test_default_priority_matches_search_config(self):
        self.assertEqual(
            list(provider_registry.DEFAULT_PROVIDER_PRIORITY),
            search.DEFAULT_CONFIG["auto_routing"]["provider_priority"],
        )

    def test_extract_provider_ids_match_extract_script(self):
        from scripts import extract
        self.assertEqual(list(provider_registry.EXTRACT_PROVIDER_IDS), extract.EXTRACT_PROVIDER_PRIORITY)

    def test_get_api_key_reads_registry_env_vars(self):
        from unittest import mock
        import os
        with mock.patch.dict(os.environ, {"TAVILY_API_KEY": "tvly-test"}, clear=True):
            self.assertEqual(search.get_api_key("tavily"), "tvly-test")
        with mock.patch.dict(os.environ, {"KILOCODE_API_KEY": "kilo-test"}, clear=True):
            self.assertIsNone(search.get_api_key("perplexity"))


class RetryJitterTests(unittest.TestCase):
    def test_retry_delay_stays_within_jitter_bounds(self):
        for attempt, base in enumerate(search.RETRY_BACKOFF_SECONDS):
            for _ in range(25):
                delay = search._retry_delay(attempt)
                self.assertGreaterEqual(delay, base)
                self.assertLessEqual(delay, base * (1 + search.RETRY_JITTER_FRACTION))

    def test_retry_delay_clamps_attempt_index(self):
        delay = search._retry_delay(99)
        base = search.RETRY_BACKOFF_SECONDS[-1]
        self.assertGreaterEqual(delay, base)
        self.assertLessEqual(delay, base * (1 + search.RETRY_JITTER_FRACTION))


class RoutingClassTests(unittest.TestCase):
    def analyzer(self):
        return search.QueryAnalyzer({"auto_routing": search.DEFAULT_CONFIG["auto_routing"]})

    def test_detects_canonical_routing_classes(self):
        cases = {
            "openssl security advisory CVE-2026-1234 mitigation": "security_advisory",
            "nist ai rmf whitepaper pdf": "policy_pdf",
            "nvidia quarterly results gross margin guidance": "finance_earnings_official",
            "pydantic official documentation api reference": "official_docs",
            "official anthropic claude release notes": "official_vendor_release",
            "best pizza in graz": "general",
        }
        analyzer = self.analyzer()
        for query, expected in cases.items():
            self.assertEqual(analyzer._detect_routing_class(query), expected, query)

    def test_route_exposes_routing_class_in_analysis_summary(self):
        config = {
            "auto_routing": search.DEFAULT_CONFIG["auto_routing"],
            "serper": {"api_key": "x" * 20},
        }
        routed = search.QueryAnalyzer(config).route("official anthropic claude release notes")
        self.assertEqual(routed["analysis_summary"]["routing_class"], "official_vendor_release")


class RerankTests(unittest.TestCase):
    def test_rerank_boosts_canonical_domain_over_mirrors(self):
        results = [
            {"url": "https://www.youtube.com/watch?v=1", "title": "video", "snippet": "x"},
            {"url": "https://medium.com/post", "title": "blog", "snippet": "x"},
            {"url": "https://www.anthropic.com/news/claude", "title": "Claude release", "snippet": "official"},
        ]
        reranked, meta = search.rerank_results_for_intent(
            "official anthropic claude release notes", "official_vendor_release", results
        )
        self.assertTrue(meta["reranked"])
        self.assertEqual(meta["top_domain_after"], "anthropic.com")
        self.assertEqual(reranked[0]["url"], "https://www.anthropic.com/news/claude")

    def test_rerank_noop_for_general_class(self):
        results = [{"url": "https://a.example/1"}, {"url": "https://b.example/2"}]
        reranked, meta = search.rerank_results_for_intent("anything", "general", results)
        self.assertFalse(meta["reranked"])
        self.assertEqual(reranked, results)

    def test_authority_signals_summarize_canonical_hits(self):
        results = [
            {"url": "https://www.anthropic.com/news/claude"},
            {"url": "https://medium.com/post"},
            {"url": "https://example.org/article"},
        ]
        signals = search.build_authority_signals("official_vendor_release", results)
        self.assertTrue(signals["rules_applied"])
        self.assertTrue(signals["canonical_top_result"])
        self.assertEqual(signals["canonical_domain_hits"], ["anthropic.com"])
        self.assertEqual(signals["demoted_domain_hits"], ["medium.com"])


class QualityReportTests(unittest.TestCase):
    def test_quality_report_scores_domain_diversity_and_extract_need(self):
        result = {
            "results": [
                {"url": "https://example.com/a", "title": "A", "description": "short"},
                {"url": "https://example.com/b", "title": "B", "description": "tiny"},
                {"url": "https://news.example.org/c", "title": "C", "description": "useful enough snippet for source triage"},
            ],
            "metadata": {"dedup_count": 2},
        }
        routing = {
            "provider": "tavily",
            "confidence": 0.32,
            "confidence_level": "low",
            "reason": "low confidence test",
            "scores": {"tavily": 4.0, "exa": 3.7},
        }

        report = search.build_quality_report(
            query="explain some obscure topic",
            result=result,
            routing_info=routing,
            providers_considered=["tavily", "exa", "linkup"],
            eligible_providers=["tavily", "exa"],
            cooldown_skips=[{"provider": "linkup", "cooldown_remaining_seconds": 42}],
            errors=[{"provider": "brave", "error": "missing key"}],
        )

        self.assertEqual(report["selected_provider"], "tavily")
        self.assertEqual(report["duplicate_count"], 2)
        self.assertEqual(report["domain_count"], 2)
        self.assertAlmostEqual(report["domain_diversity"], 2 / 3)
        self.assertEqual(report["confidence"], "low")
        self.assertTrue(report["extract_recommended"])
        self.assertIn("low routing confidence", report["extract_reasons"])
        self.assertEqual(report["skipped_providers"][0]["provider"], "linkup")

    def test_quality_report_includes_authority_signals_for_canonical_class(self):
        result = {
            "results": [
                {"url": "https://www.anthropic.com/news", "description": "clear snippet " * 8},
                {"url": "https://medium.com/post", "description": "clear snippet " * 8},
                {"url": "https://example.org/x", "description": "clear snippet " * 8},
            ],
            "metadata": {"dedup_count": 0},
        }
        routing = {
            "provider": "serper",
            "confidence_level": "high",
            "confidence": 0.9,
            "analysis_summary": {"routing_class": "official_vendor_release"},
        }
        report = search.build_quality_report(
            query="official anthropic claude release notes",
            result=result,
            routing_info=routing,
            providers_considered=["serper"],
            eligible_providers=["serper"],
            cooldown_skips=[],
            errors=[],
        )
        signals = report["authority_signals"]
        self.assertIsNotNone(signals)
        self.assertEqual(signals["canonical_domain_hits"], ["anthropic.com"])
        self.assertEqual(signals["demoted_domain_hits"], ["medium.com"])
        self.assertTrue(signals["canonical_top_result"])

    def test_quality_report_for_forced_provider_does_not_treat_missing_confidence_as_low(self):
        result = {
            "results": [
                {"url": "https://a.example/1", "description": "clear snippet " * 8},
                {"url": "https://b.example/2", "description": "clear snippet " * 8},
                {"url": "https://c.example/3", "description": "clear snippet " * 8},
            ],
            "metadata": {"dedup_count": 0},
        }
        routing = {"auto_routed": False, "provider": "linkup"}

        report = search.build_quality_report(
            query="best turntables under 1000 euro",
            result=result,
            routing_info=routing,
            providers_considered=["linkup"],
            eligible_providers=["linkup"],
            cooldown_skips=[],
            errors=[],
        )

        self.assertEqual(report["confidence"], "unknown")
        self.assertFalse(report["extract_recommended"])


class ResearchModeTests(unittest.TestCase):
    def test_select_research_providers_prefers_primary_plus_source_providers(self):
        selected = search.select_research_providers(
            primary_provider="tavily",
            provider_priority=["tavily", "linkup", "exa", "firecrawl", "brave"],
            available_providers={"tavily", "linkup", "exa", "brave"},
            max_providers=3,
        )

        self.assertEqual(selected, ["tavily", "linkup", "exa"])

    def test_research_mode_merges_dedups_and_extracts_top_sources(self):
        provider_payloads = {
            "tavily": {"provider": "tavily", "results": [
                {"url": "https://example.com/a", "title": "A", "description": "Alpha"},
                {"url": "https://example.com/dupe", "title": "Dupe", "description": "Duplicate"},
            ]},
            "linkup": {"provider": "linkup", "results": [
                {"url": "https://example.com/dupe", "title": "Dupe 2", "description": "Duplicate again"},
                {"url": "https://other.test/b", "title": "B", "description": "Beta"},
            ]},
        }
        calls = []

        def execute(provider):
            calls.append(provider)
            return provider_payloads[provider]

        def extract(urls):
            return {"provider": "linkup", "results": [{"url": u, "content": f"content for {u}"} for u in urls]}

        result = search.run_research_mode(
            query="compare alpha beta",
            research_providers=["tavily", "linkup"],
            execute_search=execute,
            extract_urls=extract,
            max_results=5,
            max_extract_urls=2,
        )

        # Providers run concurrently, so completion/call order is not guaranteed,
        # but both must be queried and result ordering must stay deterministic.
        self.assertEqual(sorted(calls), ["linkup", "tavily"])
        self.assertEqual(result["mode"], "research")
        self.assertEqual(result["routing"]["providers_queried"], ["tavily", "linkup"])
        self.assertEqual(result["metadata"]["dedup_count"], 1)
        self.assertEqual([r["url"] for r in result["results"]], [
            "https://example.com/a",
            "https://example.com/dupe",
            "https://other.test/b",
        ])
        self.assertEqual([s["url"] for s in result["source_summaries"]], [
            "https://example.com/a",
            "https://example.com/dupe",
        ])
        self.assertEqual(result["source_summaries"][0]["content"], "content for https://example.com/a")

    def test_research_mode_keeps_search_results_when_extraction_fails(self):
        def execute(provider):
            return {"provider": provider, "results": [
                {"url": "https://source.test/a", "title": "A", "description": "Alpha"},
            ]}

        def extract(urls):
            raise RuntimeError("extract provider timed out")

        result = search.run_research_mode(
            query="grounded answer please",
            research_providers=["linkup"],
            execute_search=execute,
            extract_urls=extract,
            max_results=3,
            max_extract_urls=1,
        )

        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["source_summaries"], [])
        self.assertEqual(result["routing"]["extraction_provider"], None)
        self.assertEqual(result["routing"]["extraction_error"], "extract provider timed out")
        self.assertEqual(result["metadata"]["extracted_url_count"], 0)

    def test_research_mode_preserves_provider_order_when_completion_is_out_of_order(self):
        def execute(provider):
            # Provider submitted first finishes last; ordering must still follow
            # submission order so deduplication stays deterministic.
            if provider == "tavily":
                _time.sleep(0.05)
            return {"provider": provider, "results": [
                {"url": f"https://{provider}.test/a", "title": provider, "description": "x"},
            ]}

        def extract(urls):
            return {"provider": None, "results": []}

        result = search.run_research_mode(
            query="ordered research",
            research_providers=["tavily", "linkup"],
            execute_search=execute,
            extract_urls=extract,
            max_results=5,
            max_extract_urls=0,
        )

        self.assertEqual(result["routing"]["providers_queried"], ["tavily", "linkup"])
        self.assertEqual([r["url"] for r in result["results"]], [
            "https://tavily.test/a",
            "https://linkup.test/a",
        ])

    def test_research_mode_respects_time_budget_between_providers_and_skips_extract(self):
        ticks = iter([0.0, 0.0, 6.0, 6.0])
        calls = []

        def now():
            return next(ticks)

        def execute(provider):
            calls.append(provider)
            return {"provider": provider, "results": [
                {"url": f"https://{provider}.test/a", "title": provider, "description": "Result"},
            ]}

        def extract(urls):
            raise AssertionError("extract should be skipped once budget is exhausted")

        result = search.run_research_mode(
            query="time boxed research",
            research_providers=["linkup", "tavily"],
            execute_search=execute,
            extract_urls=extract,
            max_results=5,
            max_extract_urls=1,
            time_budget_seconds=5,
            now_fn=now,
        )

        self.assertEqual(calls, ["linkup"])
        self.assertEqual(result["routing"]["provider_errors"], [{"provider": "tavily", "error": "skipped: research time budget exhausted"}])
        self.assertEqual(result["routing"]["extraction_error"], "skipped: research time budget exhausted")
        self.assertEqual(result["metadata"]["extracted_url_count"], 0)


class MainPipelineTests(unittest.TestCase):
    """End-to-end coverage of rerank + quality report through main()."""

    def test_auto_routed_search_reranks_and_reports_authority_signals(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        cache_dir = Path(tmp.name)
        fake = {"provider": "serper", "query": "q", "results": [
            {"title": "vid", "url": "https://youtube.com/watch?v=1", "snippet": "x", "score": 1.0},
            {"title": "Claude", "url": "https://www.anthropic.com/news/claude", "snippet": "official", "score": 0.9},
        ], "images": [], "answer": ""}
        buf = io.StringIO()
        argv = ["search.py", "-q", "official anthropic claude release notes", "--quality-report", "--no-cache"]
        with mock.patch.object(search, "CACHE_DIR", cache_dir), \
                mock.patch.object(search, "PROVIDER_HEALTH_FILE", cache_dir / "provider_health.json"), \
                mock.patch.object(sys, "argv", argv), \
                mock.patch.dict(os.environ, {"SERPER_API_KEY": "x" * 20}, clear=True), \
                mock.patch.object(search, "search_serper", return_value=dict(fake)), \
                contextlib.redirect_stdout(buf):
            search.main()
        out = json.loads(buf.getvalue())

        self.assertEqual(out["results"][0]["url"], "https://www.anthropic.com/news/claude")
        self.assertTrue(out["metadata"]["intent_rerank"]["reranked"])
        signals = out["quality_report"]["authority_signals"]
        self.assertEqual(signals["routing_class"], "official_vendor_release")
        self.assertTrue(signals["canonical_top_result"])


if __name__ == "__main__":
    unittest.main()
