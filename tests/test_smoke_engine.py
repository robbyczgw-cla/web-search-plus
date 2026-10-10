"""Smoke tests: the vendored 5.0.1 engine behind the skill's CLI, with fake providers.

No network and no real keys: providers are replaced on ``wsp_core.providers``,
DNS is faked, and opening a socket fails the test.
"""

import json
import os
import stat
import threading
import time
import unittest

import _support
from _support import SkillTestCase, search_answer, search_empty, wsp_skill
from wsp_core.query_limits import PROVIDER_QUERY_LIMITS, fit_query


class AutoRoutingSmokeTests(SkillTestCase):
    keys = dict(_support.FAKE_KEYS)

    def setUp(self):
        super().setUp()
        self.calls = []
        for name in ("brave", "serper", "exa", "tavily", "linkup", "firecrawl"):
            self.patch_provider(f"search_{name}", search_answer(name, self.calls))

    def search(self, *argv):
        code, out, err = self.run_cli(wsp_skill.run_search, ["--compact", *argv])
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_docs_query_goes_to_exa(self):
        result = self.search("-q", "python asyncio TaskGroup documentation")
        self.assertEqual(result["provider"], "exa")
        self.assertEqual(result["routing"]["routing_policy"], "routing-v3")
        self.assertEqual(result["routing"]["reason"], "intent_docs")

    def test_general_and_news_queries_go_to_brave(self):
        self.assertEqual(self.search("-q", "weather in Vienna today")["provider"], "brave")
        self.assertEqual(self.search("-q", "latest news about the EU AI Act")["provider"], "brave")

    def test_shopping_query_goes_to_serper(self):
        self.assertEqual(self.search("-q", "iPhone 16 Pro Max price")["provider"], "serper")

    def test_output_keeps_the_4x_top_level_shape(self):
        result = self.search("-q", "weather in Vienna today")
        for key in ("provider", "query", "results", "routing", "metadata", "cached"):
            self.assertIn(key, result)
        first = result["results"][0]
        self.assertTrue({"title", "url", "snippet"} <= set(first))

    def test_explicit_provider(self):
        result = self.search("-p", "tavily", "-q", "weather in Vienna today")
        self.assertEqual(result["provider"], "tavily")
        self.assertEqual(self.calls, [("tavily", "weather in Vienna today")])

    def test_explain_routing_runs_offline(self):
        result = self.search("--explain-routing", "-q", "arXiv paper LLM scaling laws")
        self.assertEqual(result["intent"]["intent"], "academic")
        self.assertEqual(self.calls, [])

    def test_result_cache_and_no_cache(self):
        self.search("-q", "weather in Vienna today")
        self.search("-q", "weather in Vienna today")
        self.assertEqual(len(self.calls), 1, "second identical search should be a cache hit")
        self.search("-q", "weather in Vienna today", "--no-cache")
        self.assertEqual(len(self.calls), 2)

    def test_disable_cache_env(self):
        os.environ["WSP_DISABLE_CACHE"] = "1"
        self.search("-q", "weather in Vienna today")
        self.search("-q", "weather in Vienna today")
        self.assertEqual(len(self.calls), 2)

    def test_cache_files_are_owner_only(self):
        self.search("-q", "weather in Vienna today")
        cache_dir = _support.CACHE_DIR
        self.assertEqual(stat.S_IMODE(cache_dir.stat().st_mode), 0o700)
        files = [p for p in cache_dir.rglob("*") if p.is_file()]
        self.assertTrue(files)
        for path in files:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode) & 0o077, 0, path)
        for path in [p for p in cache_dir.rglob("*") if p.is_dir()]:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode) & 0o077, 0, path)

    def test_max_results_is_clamped(self):
        result = self.search("-p", "brave", "-q", "weather in Vienna today", "-n", "0")
        self.assertGreaterEqual(len(result["results"]), 1)


class FallbackSmokeTests(SkillTestCase):
    keys = dict(_support.FAKE_KEYS)

    def search(self, *argv):
        code, out, err = self.run_cli(wsp_skill.run_search, ["--compact", "--no-cache", *argv])
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_empty_answer_falls_back(self):
        calls = []
        self.patch_provider("search_brave", search_empty("brave", calls))
        self.patch_provider("search_serper", search_answer("serper", calls))
        result = self.search("-q", "weather in Vienna today")
        self.assertEqual(result["provider"], "serper")
        self.assertTrue(result["routing"]["fallback_used"])
        self.assertEqual(result["routing"]["original_provider"], "brave")

    def test_failing_provider_falls_back(self):
        from wsp_core.http_client import ProviderRequestError

        def broken(query, api_key=None, max_results=5, **_kwargs):
            raise ProviderRequestError("upstream exploded", status_code=503, transient=True)

        self.patch_provider("search_brave", broken)
        self.patch_provider("search_serper", search_answer("serper"))
        result = self.search("-q", "weather in Vienna today")
        self.assertEqual(result["provider"], "serper")

    def test_slow_provider_is_hedged(self):
        release = threading.Event()
        self.addCleanup(release.set)

        def slow(query, api_key=None, max_results=5, **kwargs):
            release.wait(8)
            return search_answer("brave")(query, api_key, max_results)

        self.patch_provider("search_brave", slow)
        self.patch_provider("search_serper", search_answer("serper"))
        started = time.monotonic()
        result = self.search("-q", "weather in Vienna today")
        elapsed = time.monotonic() - started
        release.set()
        self.assertEqual(result["provider"], "serper")
        self.assertLess(elapsed, 7.5)


class ResearchSmokeTests(SkillTestCase):
    keys = dict(_support.FAKE_KEYS)

    def test_research_mode_fuses_providers_and_extracts(self):
        for name in ("brave", "serper", "exa", "tavily", "linkup"):
            self.patch_provider(f"search_{name}", search_answer(name, url_prefix="https://shared"))
        extracted = []

        def fake_extract(urls, *args, **kwargs):
            extracted.extend(urls)
            return {"provider": "tavily", "results": [
                {"url": u, "title": "T", "content": "EU AI Act obligations text " * 20} for u in urls]}

        self.patch_provider("extract_tavily", fake_extract)
        code, out, err = self.run_cli(wsp_skill.run_search, [
            "--compact", "--mode", "research", "-q", "EU AI Act obligations for foundation models",
            "--research-providers", "brave", "serper", "--research-extract-count", "1",
        ])
        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertEqual(result["routing"]["mode"], "research")
        self.assertTrue(result["results"])
        self.assertTrue(extracted)


class ExtractSmokeTests(SkillTestCase):
    keys = {"TAVILY_API_KEY": _support.FAKE_KEYS["TAVILY_API_KEY"],
            "FIRECRAWL_API_KEY": _support.FAKE_KEYS["FIRECRAWL_API_KEY"]}

    def setUp(self):
        super().setUp()
        self.calls = []

        def fake_tavily(urls, *args, **kwargs):
            self.calls.append(("tavily", list(urls)))
            return {"provider": "tavily", "results": [
                {"url": u, "title": "T", "content": ("word " * 8000) if "long" in u else "short page"}
                for u in urls]}

        self.patch_provider("extract_tavily", fake_tavily)

    def extract(self, *argv, expect=0):
        code, out, err = self.run_cli(wsp_skill.run_extract, ["--compact", *argv])
        self.assertEqual(code, expect, err)
        return json.loads(out)

    def test_extract_cli_shape(self):
        result = self.extract("--url", "https://example.com/a")
        self.assertEqual(result["provider"], "tavily")
        self.assertEqual(result["routing"]["requested_provider"], "auto")
        self.assertEqual(result["results"][0]["content"], "short page")

    def test_one_bad_url_does_not_sink_the_batch(self):
        result = self.extract("--url", "https://example.com/a", "--url", "https://internal.example.test/x",
                              "--url", "https://example.org/b")
        self.assertEqual([r["url"] for r in result["results"]],
                         ["https://example.com/a", "https://internal.example.test/x", "https://example.org/b"])
        self.assertIn("private/internal", result["results"][1]["error"])
        self.assertNotIn("10.1.2.3", json.dumps(result))
        self.assertEqual(self.calls, [("tavily", ["https://example.com/a", "https://example.org/b"])])

    def test_all_private_urls_fail_without_provider_call(self):
        self.extract("--url", "https://internal.example.test/x", expect=1)
        self.assertEqual(self.calls, [])

    def test_allow_private_keeps_metadata_blocked(self):
        result = self.extract("--allow-private-urls", "--url", "http://169.254.169.254/latest",
                              "--url", "https://internal.example.test/x")
        self.assertIn("metadata", result["results"][0]["error"])
        self.assertEqual(result["results"][1]["content"], "short page")
        self.assertEqual(self.calls, [("tavily", ["https://internal.example.test/x"])])

    def test_allow_private_env(self):
        os.environ["WSP_ALLOW_PRIVATE_URLS"] = "1"
        result = self.extract("--url", "https://internal.example.test/x")
        self.assertEqual(result["results"][0]["content"], "short page")

    def test_long_page_gets_head_tail_window(self):
        result = self.extract("--url", "https://example.com/long", "--extract-char-limit", "3000")
        item = result["results"][0]
        self.assertTrue(item["truncated"])
        self.assertEqual(item["original_chars"], 40000)
        self.assertLess(len(item["content"]), 3600)
        self.assertIn("[Content truncated: original 40000 chars", item["content"])

    def test_char_limit_env(self):
        os.environ["WSP_EXTRACT_CHAR_LIMIT"] = "2000"
        item = self.extract("--url", "https://example.com/long")["results"][0]
        self.assertLess(len(item["content"]), 2600)

    def test_default_char_limit_is_15000(self):
        item = self.extract("--url", "https://example.com/long")["results"][0]
        self.assertTrue(item["truncated"])
        self.assertLess(len(item["content"]), 15600)

    def test_explicit_provider_and_fallback(self):
        from wsp_core.http_client import ProviderRequestError

        def broken(urls, *args, **kwargs):
            raise ProviderRequestError("down", status_code=503, transient=True)

        self.patch_provider("extract_firecrawl", broken)
        result = self.extract("--provider", "firecrawl", "--url", "https://example.com/a")
        self.assertEqual(result["provider"], "tavily")
        self.assertTrue(result["routing"]["fallback_used"])

    def test_extract_cache_and_no_cache(self):
        self.extract("--url", "https://example.com/a")
        self.extract("--url", "https://example.com/a")
        self.assertEqual(len(self.calls), 1)
        self.extract("--url", "https://example.com/a", "--no-cache")
        self.assertEqual(len(self.calls), 2)
        os.environ["WSP_DISABLE_CACHE"] = "1"
        self.extract("--url", "https://example.com/a")
        self.assertEqual(len(self.calls), 3)

    def test_no_key_reports_skill_setup(self):
        os.environ.pop("TAVILY_API_KEY")
        os.environ.pop("FIRECRAWL_API_KEY")
        result = self.extract("--url", "https://example.com/a", expect=1)
        self.assertIn("python3 scripts/setup.py", result["error"])
        self.assertNotIn(".hermes", json.dumps(result))


class QueryLimitTests(unittest.TestCase):
    def test_brave_limit_is_600_chars_75_words(self):
        limit = PROVIDER_QUERY_LIMITS["brave"]
        self.assertEqual((limit.chars, limit.words), (600, 75))
        seventy_five = " ".join(["word"] * 75)
        self.assertEqual(fit_query("brave", seventy_five), (seventy_five, None))
        shortened, info = fit_query("brave", " ".join(["word"] * 90))
        self.assertEqual(len(shortened.split()), 75)
        self.assertEqual(info["limit_words"], 75)


if __name__ == "__main__":
    unittest.main()
