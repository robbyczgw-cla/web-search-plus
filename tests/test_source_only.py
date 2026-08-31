import os
import unittest
from unittest import mock

from scripts import provider_registry, search


class SourceOnlyCharterTests(unittest.TestCase):
    def test_perplexity_is_not_a_live_provider(self):
        self.assertNotIn("perplexity", provider_registry.PROVIDER_SPECS)
        self.assertNotIn("perplexity", provider_registry.SEARCH_PROVIDER_IDS)
        self.assertNotIn("perplexity", provider_registry.DEFAULT_PROVIDER_PRIORITY)
        self.assertNotIn(
            "perplexity",
            search.DEFAULT_CONFIG["auto_routing"]["provider_priority"],
        )
        self.assertNotIn("perplexity", search.DEFAULT_CONFIG)

    def test_kilo_and_perplexity_keys_are_ignored(self):
        with mock.patch.dict(
            os.environ,
            {"KILOCODE_API_KEY": "kilo-test", "PERPLEXITY_API_KEY": "pplx-test"},
            clear=True,
        ):
            self.assertIsNone(search.get_api_key("perplexity"))
            self.assertFalse(
                search.provider_is_configured(
                    "perplexity",
                    {"perplexity": {"api_key": "still-here"}},
                )
            )

    def test_search_perplexity_is_gone(self):
        self.assertFalse(hasattr(search, "search_perplexity"))

    def test_stale_priority_cannot_route_to_perplexity(self):
        analyzer = search.QueryAnalyzer(
            {
                "auto_routing": {
                    "fallback_provider": "serper",
                    "provider_priority": ["perplexity", "brave", "serper"],
                    "disabled_providers": [],
                },
                "brave": {"api_key": "x"},
                "serper": {"api_key": "x"},
                "perplexity": {"api_key": "x"},
            }
        )
        routed = analyzer.route("weather in Vienna today")
        self.assertNotEqual(routed["provider"], "perplexity")
        self.assertNotIn("perplexity", routed.get("scores", {}))
