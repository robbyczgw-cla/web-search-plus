"""Tests for the v3.3.0 plugin-parity sync (hermes v2.5–v2.9 features)."""

import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts import extract, provider_stats, quality, search, search_locale, url_security  # noqa: E402


class FreshnessSearchTypeTests(unittest.TestCase):
    def test_freshness_applied_for_native_provider(self):
        meta = search.freshness_metadata("serper", "week")
        self.assertTrue(meta["applied"])
        self.assertEqual(meta["native_value"], "qdr:w")

    def test_freshness_not_applied_for_unsupported_provider(self):
        meta = search.freshness_metadata("tavily", "week")
        self.assertFalse(meta["applied"])
        self.assertIn("reason", meta)

    def test_search_type_only_serper_native(self):
        self.assertTrue(search.search_type_metadata("serper", "news")["applied"])
        self.assertFalse(search.search_type_metadata("brave", "news")["applied"])


class SerperNewsTests(unittest.TestCase):
    def test_news_vertical_parses_news_field(self):
        payload = {
            "news": [
                {"title": "T", "link": "https://n.example/a", "snippet": "s",
                 "date": "1 hour ago", "source": "Example News", "imageUrl": "https://img", "position": 1},
            ]
        }
        with mock.patch.object(search, "make_request", return_value=payload):
            result = search.search_serper("q", "key", search_type="news")
        self.assertEqual(len(result["results"]), 1)
        item = result["results"][0]
        self.assertEqual(item["source"], "Example News")
        self.assertEqual(item["thumbnail"], "https://img")
        self.assertEqual(item["position"], 1)

    def test_web_vertical_still_reads_organic(self):
        payload = {"organic": [{"title": "T", "link": "https://example.com", "snippet": "s"}]}
        with mock.patch.object(search, "make_request", return_value=payload):
            result = search.search_serper("q", "key")
        self.assertEqual(result["results"][0]["url"], "https://example.com")


class KeenableTests(unittest.TestCase):
    def test_keyed_endpoint_uses_api_key_header(self):
        endpoint, headers = search._keenable_endpoint("https://api.keenable.ai/v1/search", "kee-key", True)
        self.assertEqual(endpoint, "https://api.keenable.ai/v1/search")
        self.assertEqual(headers["X-API-Key"], "kee-key")

    def test_public_endpoint_when_opted_in(self):
        endpoint, headers = search._keenable_endpoint("https://api.keenable.ai/v1/search", None, True)
        self.assertTrue(endpoint.endswith("/public"))
        self.assertNotIn("X-API-Key", headers)

    def test_no_key_no_public_raises_config_error(self):
        with self.assertRaises(search.ProviderConfigError):
            search._keenable_endpoint("https://api.keenable.ai/v1/search", None, False)

    def test_public_tier_warning_in_metadata(self):
        payload = {"results": [{"title": "t", "url": "https://example.com", "snippet": "s"}]}
        with mock.patch.object(search, "make_request", return_value=payload):
            result = search.search_keenable("q", api_key=None, public_allowed=True)
        self.assertTrue(result["metadata"]["public_endpoint"])
        self.assertIn("no SLA", result["metadata"]["public_endpoint_warning"])

    def test_provider_is_configured_via_public_tier(self):
        with mock.patch.dict(os.environ, {"WSP_KEENABLE_ALLOW_PUBLIC": "1"}, clear=True):
            self.assertTrue(search.provider_is_configured("keenable", {}))
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(search.provider_is_configured("keenable", {}))

    def test_keenable_never_wins_score_ties(self):
        config = {"auto_routing": {"enabled": True}}
        with mock.patch.object(search, "provider_is_configured", return_value=True), \
                mock.patch.object(search.provider_stats, "performance_adjustments", return_value={}):
            routing = search.QueryAnalyzer(config).route("zxqv")
        self.assertNotEqual(routing["provider"], "keenable")


class SpamFilterDiversityTests(unittest.TestCase):
    def test_spam_mirror_removed(self):
        results = [
            {"url": "https://newbedev.com/answer", "title": "mirror"},
            {"url": "https://stackoverflow.com/q/1", "title": "canonical"},
        ]
        kept, removed = quality.filter_spam_results(results)
        self.assertEqual(len(kept), 1)
        self.assertEqual(removed, ["newbedev.com"])

    def test_lookalike_domain_not_blocked(self):
        results = [{"url": "https://newbedev.com.evil.example/x", "title": "lookalike"}]
        kept, removed = quality.filter_spam_results(results)
        self.assertEqual(len(kept), 1)
        self.assertEqual(removed, [])

    def test_allowlist_rescues_domain(self):
        results = [{"url": "https://w3cub.com/docs", "title": "m"}]
        kept, _ = quality.filter_spam_results(results, allowed=["w3cub.com"])
        self.assertEqual(len(kept), 1)

    def test_extra_blocked_domains(self):
        results = [{"url": "https://spam.example/x"}]
        kept, removed = quality.filter_spam_results(results, extra_blocked=["spam.example"])
        self.assertEqual(kept, [])
        self.assertEqual(removed, ["spam.example"])

    def test_domain_diversity_caps_head_slots(self):
        results = [{"url": f"https://one.example/{i}"} for i in range(4)] + [{"url": "https://two.example/a"}]
        reranked, demoted = quality.rerank_domain_diversity(results, max_per_domain=2)
        self.assertEqual(demoted, 2)
        self.assertEqual(len(reranked), 5)  # demoted, not dropped
        self.assertEqual(reranked[2]["url"], "https://two.example/a")

    def test_domain_constraints_from_site_operator(self):
        constraints = quality.extract_domain_constraints("bug site:github.com", ["Docs.Python.org"])
        self.assertEqual(constraints, ["docs.python.org", "github.com"])

    def test_lookalike_domain_gets_no_authority_boost(self):
        self.assertFalse(quality._domain_matches_rule("openai.com.evil.example", "openai.com"))
        self.assertTrue(quality._domain_matches_rule("blog.openai.com", "openai.com"))
        self.assertTrue(quality._domain_matches_rule("docs.python.org", "docs."))
        self.assertFalse(quality._domain_matches_rule("notdocs.com", "docs."))


class ProviderStatsTests(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"WSP_DISABLE_CACHE": "1"}, clear=False)
        self.env.start()
        provider_stats._reset_provider_stats_for_tests()

    def tearDown(self):
        provider_stats._reset_provider_stats_for_tests()
        self.env.stop()

    def test_no_adjustment_below_min_samples(self):
        for _ in range(provider_stats.MIN_SAMPLES_FOR_ADJUSTMENT - 1):
            provider_stats.record_provider_outcome("tavily", 0.5, 5, False)
        self.assertEqual(provider_stats.performance_adjustment("tavily"), 0.0)

    def test_adjustment_bounded(self):
        for _ in range(20):
            provider_stats.record_provider_outcome("fast", 0.1, 5, False)
            provider_stats.record_provider_outcome("slow", 60.0, 0, True)
        fast = provider_stats.performance_adjustment("fast")
        slow = provider_stats.performance_adjustment("slow")
        self.assertGreater(fast, 0)
        self.assertLess(slow, 0)
        self.assertLessEqual(abs(fast), provider_stats.MAX_SCORE_ADJUSTMENT)
        self.assertLessEqual(abs(slow), provider_stats.MAX_SCORE_ADJUSTMENT)

    def test_stale_samples_ignored(self):
        old = time.time() - provider_stats.SAMPLE_MAX_AGE_SECONDS - 10
        for _ in range(10):
            provider_stats.record_provider_outcome("old", 0.1, 5, False, now=old)
        self.assertIsNone(provider_stats.get_provider_performance("old"))


class RetryCooldownTests(unittest.TestCase):
    def test_parse_retry_after_seconds(self):
        self.assertEqual(search.parse_retry_after("7"), 7.0)
        self.assertIsNone(search.parse_retry_after(None))
        self.assertIsNone(search.parse_retry_after("garbage"))

    def test_parse_retry_after_http_date(self):
        from email.utils import formatdate
        value = formatdate(time.time() + 20, usegmt=True)
        parsed = search.parse_retry_after(value)
        self.assertIsNotNone(parsed)
        self.assertGreater(parsed, 10)

    def test_transient_codes_extended(self):
        self.assertIn(502, search.TRANSIENT_HTTP_CODES)
        self.assertIn(500, search.TRANSIENT_HTTP_CODES)

    def test_failure_decay_restarts_ladder(self):
        with mock.patch.object(search, "_load_provider_health", return_value={
            "p": {"failure_count": 3, "last_failure_at": int(time.time()) - search.FAILURE_DECAY_SECONDS - 60},
        }), mock.patch.object(search, "_save_provider_health"):
            state = search.mark_provider_failure("p", "boom")
        self.assertEqual(state["failure_count"], 1)
        self.assertEqual(state["cooldown_seconds"], search.COOLDOWN_STEPS_SECONDS[0])

    def test_retry_after_feeds_cooldown_capped(self):
        with mock.patch.object(search, "_load_provider_health", return_value={}), \
                mock.patch.object(search, "_save_provider_health"):
            state = search.mark_provider_failure("p", "429", retry_after=99999)
        self.assertEqual(state["cooldown_seconds"], search.COOLDOWN_STEPS_SECONDS[-1])


class ExtractTruncationTests(unittest.TestCase):
    def test_base64_images_replaced(self):
        content = "before ![diagram](data:image/png;base64,AAAA) after <img src=\"data:image/gif;base64,BBBB\" alt=\"logo\"> end ![ok](https://x/y.png)"
        cleaned = extract.sanitize_extract_content(content)
        self.assertIn("[IMAGE: diagram]", cleaned)
        self.assertIn("[IMAGE: logo]", cleaned)
        self.assertIn("https://x/y.png", cleaned)
        self.assertNotIn("base64", cleaned)

    def test_truncation_head_tail_window(self):
        formatted = extract.format_truncated_extract_content("x" * 1000, 100)
        self.assertTrue(formatted["truncated"])
        self.assertEqual(formatted["original_chars"], 1000)
        self.assertIn("[... omitted middle ...]", formatted["content"])
        self.assertIn("Content truncated", formatted["content"])

    def test_short_content_untouched(self):
        formatted = extract.format_truncated_extract_content("short", 100)
        self.assertFalse(formatted["truncated"])
        self.assertEqual(formatted["content"], "short")

    def test_priority_tavily_first_serper_last(self):
        self.assertEqual(extract.EXTRACT_PROVIDER_PRIORITY[0], "tavily")
        self.assertEqual(extract.EXTRACT_PROVIDER_PRIORITY[-1], "serper")
        self.assertIn("keenable", extract.EXTRACT_PROVIDER_PRIORITY)

    def test_extract_plus_truncates_oversized_content(self):
        big = "y" * 40000
        with mock.patch.dict(os.environ, {"TAVILY_API_KEY": "tavi-key"}, clear=True):
            with mock.patch.object(extract, "extract_tavily", return_value={
                "provider": "tavily",
                "results": [{"url": "https://example.com", "title": "T", "content": big, "raw_content": big, "provider": "tavily"}],
            }):
                result = extract.extract_plus(["https://example.com"], provider="auto")
        item = result["results"][0]
        self.assertTrue(item["truncated"])
        self.assertEqual(item["original_chars"], 40000)
        self.assertLess(len(item["content"]), 20000)

    def test_keenable_public_tier_used_in_extract_fallback(self):
        with mock.patch.dict(os.environ, {"WSP_KEENABLE_ALLOW_PUBLIC": "1"}, clear=True):
            with mock.patch.object(extract, "extract_keenable", return_value={
                "provider": "keenable",
                "results": [{"url": "https://example.com", "title": "T", "content": "ok", "raw_content": "ok", "provider": "keenable"}],
            }) as fake:
                result = extract.extract_plus(["https://example.com"], provider="auto")
        self.assertEqual(result["provider"], "keenable")
        self.assertTrue(fake.called)


class LocaleTests(unittest.TestCase):
    def test_location_hint_wins_over_fallback(self):
        resolved = search_locale.resolve_locale("serper", {}, "best coffee in Berlin")
        self.assertEqual(resolved["country"], "de")
        self.assertEqual(resolved["metadata"]["source"]["country"], "hint")

    def test_conflicting_hints_do_not_resolve(self):
        self.assertIsNone(search_locale.detect_location_country("Paris vs Madrid comparison"))

    def test_language_inference_requires_auto(self):
        resolved = search_locale.resolve_locale("serper", {}, "wie viel kostet das beste Hotel")
        self.assertEqual(resolved["language"], "en")
        resolved_auto = search_locale.resolve_locale("serper", {"locale": {"language": "auto"}}, "wie viel kostet das beste Hotel")
        self.assertEqual(resolved_auto["language"], "de")
        self.assertEqual(resolved_auto["metadata"]["source"]["language"], "inferred")

    def test_query_language_never_implies_country(self):
        resolved = search_locale.resolve_locale("serper", {"locale": {"language": "auto"}}, "wie viel kostet das beste Hotel")
        self.assertEqual(resolved["country"], "us")

    def test_cli_values_win(self):
        resolved = search_locale.resolve_locale("serper", {"locale": {"country": "de", "language": "de"}}, "best coffee in Berlin", cli_country="AT", cli_language="EN")
        self.assertEqual(resolved["country"], "at")
        self.assertEqual(resolved["language"], "en")
        self.assertEqual(resolved["metadata"]["source"], {"country": "cli", "language": "cli"})

    def test_ambiguous_or_terse_queries_infer_nothing(self):
        self.assertIsNone(search_locale.infer_query_language("DAC R2R NOS"))

    def test_locale_provider_set(self):
        self.assertTrue(search_locale.provider_supports_locale("serper"))
        self.assertFalse(search_locale.provider_supports_locale("serpbase"))


class UrlSecurityTests(unittest.TestCase):
    def test_cgnat_range_blocked(self):
        with self.assertRaises(ValueError):
            url_security.validate_outbound_url("https://100.64.0.1/x")

    def test_ipv4_mapped_ipv6_blocked(self):
        with self.assertRaises(ValueError):
            url_security.validate_outbound_url("https://[::ffff:10.0.0.1]/x")


if __name__ == "__main__":
    unittest.main()
