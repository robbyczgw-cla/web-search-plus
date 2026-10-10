"""The skill's 4.x interface on top of the 5.0.1 engine: flags, env vars, config."""

import json
import os
import unittest

import _support
from _support import SkillTestCase, search_answer, wsp_skill
from wsp_core import config as engine_config
from wsp_core.provider_registry import DEFAULT_PROVIDER_PRIORITY

# Every flag the 4.3.1 skill CLI accepted (scripts/search.py, scripts/extract.py).
SEARCH_FLAGS_431 = [
    "--allow-private-urls", "--auto", "--cache-stats", "--cache-ttl", "--categories", "--category",
    "--clear-cache", "--compact", "--country", "--depth", "--end-date", "--engines", "--exa-depth",
    "--exa-type", "--exa-verbosity", "--exclude-domains", "--explain-routing", "--firecrawl-scrape",
    "--firecrawl-sources", "--freshness", "--images", "--include-domains", "--language", "--linkup-depth",
    "--linkup-output-type", "--livecrawl", "--max-results", "--mode", "--no-cache", "--no-news",
    "--provider", "--quality-report", "--query", "--querit-base-path", "--querit-base-url",
    "--raw-content", "--research-extract-count", "--research-providers", "--research-time-budget",
    "--searxng-safesearch", "--searxng-url", "--similar-url", "--start-date", "--time-range", "--topic",
    "--type", "--you-safesearch", "-a", "-n", "-p", "-q",
]
EXTRACT_FLAGS_431 = [
    "--url", "--provider", "--format", "--include-images", "--include-raw-html", "--render-js",
    "--allow-private-urls", "--extract-char-limit", "--compact",
]


def search_parser():
    from wsp_core import search as search_module

    wsp_skill._patch_search_parser(search_module)
    return search_module.build_parser(wsp_skill.load_config())


class FlagCompatibilityTests(SkillTestCase):
    def test_every_431_search_flag_is_accepted(self):
        options = set(search_parser()._option_string_actions)
        self.assertEqual([f for f in SEARCH_FLAGS_431 if f not in options], [])

    def test_every_431_extract_flag_is_accepted(self):
        options = set(wsp_skill.build_extract_parser()._option_string_actions)
        self.assertEqual([f for f in EXTRACT_FLAGS_431 if f not in options], [])

    def test_431_provider_choices_are_unchanged(self):
        parser = search_parser()
        choices = set(parser._option_string_actions["--provider"].choices)
        self.assertEqual(choices, {"serper", "serpbase", "brave", "tavily", "querit", "linkup", "exa",
                                   "firecrawl", "you", "searxng", "keenable", "auto"})
        extract_choices = set(wsp_skill.build_extract_parser()._option_string_actions["--provider"].choices)
        self.assertEqual(extract_choices, {"auto", "tavily", "exa", "linkup", "firecrawl", "you", "keenable", "serper"})

    def test_legacy_synthesis_options_map_to_source_results(self):
        args = search_parser().parse_args(["-q", "x", "--exa-depth", "deep-reasoning",
                                           "--linkup-output-type", "sourcedAnswer"])
        self.assertEqual(args.exa_depth, "normal")
        self.assertEqual(args.linkup_output_type, "searchResults")

    def test_parallel_is_refused(self):
        for argv in (["-p", "parallel", "-q", "x"], ["--mode", "research", "-q", "x", "--research-providers", "parallel"]):
            code, _out, err = self.run_cli(wsp_skill.run_search, argv)
            self.assertEqual(code, 2, argv)
            self.assertIn("parallel", err)
        result = wsp_skill.extract_urls(["https://example.com"], provider="parallel")
        self.assertIn("not part of this skill", result["error"])

    def test_similar_url_private_target_is_blocked(self):
        code, _out, err = self.run_cli(wsp_skill.run_search, ["-p", "exa", "--similar-url", "http://10.0.0.5/"])
        self.assertEqual(code, 1)
        self.assertIn("--similar-url blocked", err)


class ProviderFlagCarryTests(SkillTestCase):
    keys = dict(_support.FAKE_KEYS)

    def test_provider_specific_flags_reach_the_provider_on_the_hedged_path(self):
        seen = {}

        def tavily(query, api_key=None, max_results=5, **kwargs):
            seen.update(kwargs, max_results=max_results)
            return search_answer("tavily")(query, api_key, max_results)

        self.patch_provider("search_tavily", tavily)
        code, out, err = self.run_cli(wsp_skill.run_search, [
            "-p", "tavily", "-q", "weather in Vienna today", "--depth", "advanced", "--topic", "news",
            "--raw-content", "-n", "3", "--compact"])
        self.assertEqual(code, 0, err)
        self.assertEqual(seen["depth"], "advanced")
        self.assertEqual(seen["topic"], "news")
        self.assertTrue(seen["include_raw_content"])
        self.assertEqual(json.loads(out)["provider"], "tavily")


class EnvAliasTests(SkillTestCase):
    def test_keenable_public_alias(self):
        os.environ["WSP_KEENABLE_ALLOW_PUBLIC"] = "1"
        wsp_skill.apply_env_aliases()
        self.assertEqual(os.environ["KEENABLE_ALLOW_PUBLIC"], "1")
        self.assertTrue(engine_config.keyless_public_allowed("keenable", {}))

    def test_engine_name_wins_over_alias(self):
        os.environ["WSP_KEENABLE_ALLOW_PUBLIC"] = "1"
        os.environ["KEENABLE_ALLOW_PUBLIC"] = "0"
        wsp_skill.apply_env_aliases()
        self.assertEqual(os.environ["KEENABLE_ALLOW_PUBLIC"], "0")

    def test_parallel_key_is_dropped(self):
        os.environ["PARALLEL_API_KEY"] = "par-test-key-12345"
        wsp_skill.apply_env_aliases()
        self.assertNotIn("PARALLEL_API_KEY", os.environ)

    def test_locale_env(self):
        os.environ["WSP_LOCALE_COUNTRY"] = "AT"
        os.environ["WSP_LOCALE_LANGUAGE"] = "de"
        config = wsp_skill.load_config()
        self.assertEqual(config["defaults"]["locale"], {"country": "at", "language": "de"})

    def test_extract_char_limit_env(self):
        os.environ["WSP_EXTRACT_CHAR_LIMIT"] = "4000"
        self.assertEqual(wsp_skill.extract_char_limit(None, wsp_skill.load_config()), 4000)

    def test_allow_private_env(self):
        os.environ["WSP_ALLOW_PRIVATE_URLS"] = "1"
        self.assertTrue(wsp_skill.load_config()["extract"]["allow_private_urls"])

    def test_hermes_profile_env_is_not_read(self):
        from wsp_core import env_loader

        paths = env_loader.candidate_env_paths(_support.SCRIPTS_DIR / "__init__.py")
        self.assertTrue(all(_support.SKILL_DIR in p.resolve().parents or p.resolve().parent == _support.SKILL_DIR
                            for p in paths), paths)


class ConfigMigrationTests(SkillTestCase):
    def adapt(self, user_config):
        path = _support.CACHE_DIR / "config.json"
        path.write_text(json.dumps(user_config), encoding="utf-8")
        os.environ["WEB_SEARCH_PLUS_CONFIG"] = str(path)
        return wsp_skill.load_config(), path

    def test_431_example_config_loads_and_migrates(self):
        legacy = {
            "defaults": {"provider": "serper", "max_results": 5},
            "auto_routing": {"enabled": True, "fallback_provider": "serper",
                             "provider_priority": list(wsp_skill.SKILL_4X_DEFAULT_PRIORITY),
                             "disabled_providers": [], "confidence_threshold": 0.3},
            "serper": {"country": "us", "language": "en", "type": "search"},
            "brave": {"country": "US", "search_lang": "en", "safesearch": "moderate"},
            "serpbase": {"api_url": "https://api.serpbase.com/search", "timeout": 30},
            "locale": {"country": "at", "language": "auto"},
        }
        config, path = self.adapt(legacy)
        self.assertTrue(path.exists(), "a 4.x config must not be moved aside")
        self.assertEqual(config["defaults"]["locale"], {"country": "at", "language": "auto"})
        self.assertNotIn("country", config["serper"])
        self.assertNotIn("search_lang", config["brave"])
        self.assertEqual(config["serpbase"]["api_url"], "https://api.serpbase.dev/google/search")
        self.assertEqual(config["auto_routing"]["provider_priority"],
                         [p for p in DEFAULT_PROVIDER_PRIORITY if p != "parallel"])

    def test_serper_locale_seeds_global_locale(self):
        config, _ = self.adapt({"serper": {"country": "de", "language": "de"}})
        self.assertEqual(config["defaults"]["locale"], {"country": "de", "language": "de"})

    def test_custom_priority_is_kept(self):
        config, _ = self.adapt({"auto_routing": {"provider_priority": ["exa", "serper", "brave"]}})
        self.assertEqual(config["auto_routing"]["provider_priority"][:3], ["exa", "serper", "brave"])

    def test_parallel_is_never_configured(self):
        config, _ = self.adapt({"parallel": {"api_key": "par-test-key-123"},
                                "auto_routing": {"provider_priority": ["parallel", "brave"],
                                                 "fallback_provider": "parallel"}})
        self.assertNotIn("parallel", config["auto_routing"]["provider_priority"])
        self.assertIn("parallel", config["auto_routing"]["disabled_providers"])
        self.assertNotEqual(config["auto_routing"]["fallback_provider"], "parallel")
        self.assertFalse(engine_config.provider_configured("parallel", config))

    def test_auto_routing_off_uses_defaults_provider(self):
        config, _ = self.adapt({"defaults": {"provider": "brave"}, "auto_routing": {"enabled": False}})
        self.assertEqual(config["default_provider"], "brave")

    def test_invalid_config_is_reported_not_moved(self):
        path = _support.CACHE_DIR / "config.json"
        path.write_text("{not json", encoding="utf-8")
        os.environ["WEB_SEARCH_PLUS_CONFIG"] = str(path)
        wsp_skill.load_config()
        self.assertTrue(path.exists())
        self.assertEqual(list(_support.CACHE_DIR.glob("config.json.broken-*")), [])

    def test_typesafe_helper_stays_off(self):
        config, _ = self.adapt({"jev": {"enabled": True}})
        self.assertFalse(config["jev"]["enabled"])


class GuidanceTests(unittest.TestCase):
    def test_hermes_setup_hints_are_rewritten(self):
        text = wsp_skill.skill_guidance({
            "error": "Run: python3 ~/.hermes/plugins/web-search-plus/setup.py setup --preset starter",
            "how_to_fix": ["2. Run: python3 ~/.hermes/plugins/web-search-plus/setup.py setup brave",
                           "3. Or add BRAVE_API_KEY to your Hermes profile .env"],
        })
        dumped = json.dumps(text)
        self.assertNotIn("hermes", dumped.lower())
        self.assertIn("python3 scripts/setup.py", dumped)


if __name__ == "__main__":
    unittest.main()
