import os
import sys
import unittest
from pathlib import Path
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from scripts import extract, search


class RoutingParityTests(unittest.TestCase):
    def make_analyzer(self):
        config = {
            "auto_routing": {
                "fallback_provider": "serper",
                "provider_priority": [
                    "tavily",
                    "linkup",
                    "querit",
                    "exa",
                    "firecrawl",
                    "perplexity",
                    "brave",
                    "serper",
                    "you",
                    "searxng",
                ],
                "disabled_providers": ["searxng"],
            },
            "serper": {"api_key": "x"},
            "brave": {"api_key": "x"},
            "tavily": {"api_key": "x"},
            "querit": {"api_key": "x"},
            "linkup": {"api_key": "x"},
            "exa": {"api_key": "x"},
            "firecrawl": {"api_key": "x"},
            "perplexity": {"api_key": "x"},
            "you": {"api_key": "x"},
            "searxng": {},
        }
        return search.QueryAnalyzer(config)

    def test_linkup_routing_for_source_grounded_query(self):
        routed = self.make_analyzer().route("find credible sources and citations for AI tutoring outcomes")
        self.assertEqual(routed["provider"], "linkup")

    def test_multilingual_recency_query_scores_querit_signal(self):
        routed = self.make_analyzer().route("latest AI policy updates in Germany")
        self.assertGreater(routed["scores"]["querit"], 0)
        self.assertIn(routed["provider"], {"serper", "brave", "perplexity", "querit", "tavily"})

    def test_generic_current_web_query_uses_brave_or_serper(self):
        routed = self.make_analyzer().route("weather in Vienna today")
        self.assertIn(routed["provider"], {"brave", "serper", "perplexity"})

    def test_tie_breaker_is_deterministic(self):
        winners = ["brave", "serper"]
        first = search._choose_tie_winner("weather in Vienna today", winners, winners)
        second = search._choose_tie_winner("weather in Vienna today", winners, winners)
        self.assertEqual(first, second)
        self.assertIn(first, winners)


class ExtractTests(unittest.TestCase):
    def test_invalid_url_rejected(self):
        result = extract.extract_plus(["example.com"], provider="auto")
        self.assertIn("Invalid URL", result["error"])

    def test_missing_keys_reported(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            result = extract.extract_plus(["https://example.com"], provider="auto")
        self.assertEqual(result["error"], "All extraction providers failed")
        self.assertEqual(result["fallback_errors"][0]["provider"], "firecrawl")
        self.assertEqual(result["fallback_errors"][0]["error"], "missing_api_key")

    def test_auto_fallback_uses_next_provider_after_failure(self):
        with mock.patch.dict(os.environ, {"FIRECRAWL_API_KEY": "fire", "LINKUP_API_KEY": "link"}, clear=True):
            with mock.patch.object(extract, "extract_firecrawl", side_effect=RuntimeError("boom")):
                with mock.patch.object(extract, "extract_linkup", return_value={
                    "provider": "linkup",
                    "results": [{"url": "https://example.com", "title": "Example", "content": "ok", "raw_content": "ok", "provider": "linkup"}],
                }):
                    result = extract.extract_plus(["https://example.com"], provider="auto")
        self.assertEqual(result["provider"], "linkup")
        self.assertTrue(result["routing"]["fallback_used"])
        self.assertEqual(result["routing"]["fallback_errors"][0]["provider"], "firecrawl")


if __name__ == "__main__":
    unittest.main()
