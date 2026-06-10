import contextlib
import io
import ipaddress
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from scripts import extract, provider_registry, search, url_security


class TriggerScopeTests(unittest.TestCase):
    """The skill manifest must not register generic auto-activation triggers."""

    GENERIC_TRIGGERS = {"search", "find", "look up", "lookup", "research", "browse", "web"}

    def load_triggers(self):
        with open(SKILL_DIR / "package.json", encoding="utf-8") as f:
            manifest = json.load(f)
        return manifest["clawhub"]["triggers"]

    def test_no_generic_single_word_triggers(self):
        triggers = self.load_triggers()
        for trigger in triggers:
            self.assertNotIn(trigger.strip().lower(), self.GENERIC_TRIGGERS,
                             f"Generic trigger {trigger!r} would auto-activate on everyday requests")

    def test_triggers_are_narrowly_scoped(self):
        triggers = self.load_triggers()
        self.assertTrue(triggers, "manifest must declare triggers")
        for trigger in triggers:
            words = trigger.strip().lower().split()
            self.assertTrue(
                len(words) >= 2 or "wsp" in words,
                f"Trigger {trigger!r} is too broad — use a multi-word or wsp-prefixed phrase",
            )

    def test_expected_scoped_triggers_present(self):
        triggers = {t.strip().lower() for t in self.load_triggers()}
        for expected in ("web search plus", "wsp search", "search the web for", "extract url content"):
            self.assertIn(expected, triggers)

    def test_manifest_declares_permissions(self):
        with open(SKILL_DIR / "package.json", encoding="utf-8") as f:
            manifest = json.load(f)
        permissions = manifest["clawhub"]["permissions"]
        self.assertIn("network", permissions)
        self.assertIn("env", permissions)
        self.assertIn("filesystem", permissions)
        hosts = permissions["network"]["outbound_hosts"]
        self.assertIn("google.serper.dev", hosts)
        self.assertIn("api.tavily.com", hosts)


class SsrfValidationTests(unittest.TestCase):
    def test_non_http_scheme_rejected(self):
        for url in ("ftp://example.com/file", "file:///etc/passwd", "gopher://example.com"):
            with self.assertRaises(ValueError):
                url_security.validate_outbound_url(url)

    def test_private_ip_literals_blocked(self):
        for host in ("10.0.0.1", "127.0.0.1", "192.168.1.1", "172.16.0.5",
                     "169.254.10.20", "0.0.0.0", "[::1]", "[fc00::1]", "[fe80::1]"):
            with self.assertRaises(ValueError, msg=host):
                url_security.validate_outbound_url(f"http://{host}/path")

    def test_metadata_endpoints_blocked_even_with_private_opt_in(self):
        for host in ("169.254.169.254", "metadata.google.internal"):
            with self.assertRaises(ValueError, msg=host):
                url_security.validate_outbound_url(f"http://{host}/latest", allow_private=True)
            with mock.patch.dict(os.environ, {"WSP_ALLOW_PRIVATE_URLS": "1"}):
                with self.assertRaises(ValueError, msg=host):
                    url_security.validate_outbound_url(f"http://{host}/latest")

    def test_hostname_resolving_to_private_ip_blocked(self):
        fake = [(2, 1, 6, "", ("10.1.2.3", 80))]
        with mock.patch.object(url_security.socket, "getaddrinfo", return_value=fake):
            with self.assertRaises(ValueError):
                url_security.validate_outbound_url("http://internal.corp.example/page")

    def test_public_hostname_allowed(self):
        fake = [(2, 1, 6, "", ("93.184.216.34", 443))]
        with mock.patch.object(url_security.socket, "getaddrinfo", return_value=fake):
            url = url_security.validate_outbound_url("https://example.com/page")
        self.assertEqual(url, "https://example.com/page")

    def test_unresolvable_hostname_blocked(self):
        with mock.patch.object(url_security.socket, "getaddrinfo", side_effect=url_security.socket.gaierror):
            with self.assertRaises(ValueError):
                url_security.validate_outbound_url("https://does-not-resolve.invalid/")

    def test_private_opt_in_allows_private_targets(self):
        self.assertEqual(
            url_security.validate_outbound_url("http://192.168.1.10/status", allow_private=True),
            "http://192.168.1.10/status",
        )
        with mock.patch.dict(os.environ, {"WSP_ALLOW_PRIVATE_URLS": "1"}):
            self.assertEqual(
                url_security.validate_outbound_url("http://10.0.0.9/dash"),
                "http://10.0.0.9/dash",
            )

    def test_extract_plus_blocks_private_urls_before_provider_calls(self):
        with mock.patch.dict(os.environ, {"FIRECRAWL_API_KEY": "x" * 20}, clear=True):
            with mock.patch.object(extract, "extract_firecrawl") as fire:
                result = extract.extract_plus(["http://127.0.0.1/admin"], provider="auto")
        fire.assert_not_called()
        self.assertIn("blocked", result["error"])

    def test_extract_plus_allows_private_with_flag(self):
        payload = {"provider": "firecrawl", "results": [{"url": "http://192.168.0.2/x", "title": "t", "content": "c", "raw_content": "c", "provider": "firecrawl"}]}
        with mock.patch.dict(os.environ, {"FIRECRAWL_API_KEY": "x" * 20}, clear=True):
            with mock.patch.object(extract, "extract_firecrawl", return_value=payload):
                result = extract.extract_plus(["http://192.168.0.2/x"], provider="firecrawl", allow_private=True)
        self.assertEqual(result["provider"], "firecrawl")


class CachePermissionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self._tmp.name) / "wsp-cache"
        self._patches = [
            mock.patch.object(search, "CACHE_DIR", self.cache_dir),
            mock.patch.object(search, "PROVIDER_HEALTH_FILE", self.cache_dir / "provider_health.json"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def _mode(self, path: Path) -> int:
        return stat.S_IMODE(path.stat().st_mode)

    def test_cache_dir_created_owner_only(self):
        search._ensure_cache_dir()
        self.assertEqual(self._mode(self.cache_dir), 0o700)

    def test_cache_files_created_owner_only(self):
        search.cache_put("private query", "serper", 5, {"provider": "serper", "results": []})
        entries = list(self.cache_dir.glob("*.json"))
        self.assertEqual(len(entries), 1)
        self.assertEqual(self._mode(entries[0]), 0o600)

    def test_provider_health_file_created_owner_only(self):
        search.mark_provider_failure("serper", "boom")
        health = self.cache_dir / "provider_health.json"
        self.assertTrue(health.exists())
        self.assertEqual(self._mode(health), 0o600)
        self.assertEqual(self._mode(self.cache_dir), 0o700)

    def test_cache_roundtrip(self):
        search.cache_put("q", "serper", 5, {"provider": "serper", "results": [{"url": "https://a.example"}]})
        cached = search.cache_get("q", "serper", 5)
        self.assertIsNotNone(cached)
        self.assertEqual(cached["results"][0]["url"], "https://a.example")


class SecretRedactionTests(unittest.TestCase):
    """Configured credentials must never reach logs or persisted files."""

    SECRET = "sk-test-supersecret-12345"

    def test_redact_secrets_removes_env_credentials(self):
        with mock.patch.dict(os.environ, {"TAVILY_API_KEY": self.SECRET}, clear=True):
            redacted = provider_registry.redact_secrets(f"401 invalid key {self.SECRET} rejected")
        self.assertNotIn(self.SECRET, redacted)
        self.assertIn("***REDACTED***", redacted)

    def test_redact_secrets_removes_extra_config_credentials(self):
        redacted = provider_registry.redact_secrets(
            f"boom {self.SECRET}", extra_secrets=(self.SECRET,)
        )
        self.assertNotIn(self.SECRET, redacted)

    def test_provider_health_file_never_stores_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            health = cache_dir / "provider_health.json"
            with mock.patch.object(search, "CACHE_DIR", cache_dir), \
                    mock.patch.object(search, "PROVIDER_HEALTH_FILE", health), \
                    mock.patch.dict(os.environ, {"SERPER_API_KEY": self.SECRET}, clear=True):
                search.mark_provider_failure("serper", f"HTTP 401: key {self.SECRET} invalid")
            content = health.read_text(encoding="utf-8")
        self.assertNotIn(self.SECRET, content)
        self.assertIn("***REDACTED***", content)

    def test_extract_errors_never_contain_credentials(self):
        with mock.patch.dict(os.environ, {"FIRECRAWL_API_KEY": self.SECRET}, clear=True):
            with mock.patch.object(extract, "extract_firecrawl", side_effect=RuntimeError(f"denied for {self.SECRET}")):
                result = extract.extract_plus(["https://example.com"], provider="firecrawl", allow_private=True)
        serialized = json.dumps(result)
        self.assertNotIn(self.SECRET, serialized)


class CacheDisableTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self._tmp.name) / "wsp-cache"
        self._patches = [
            mock.patch.object(search, "CACHE_DIR", self.cache_dir),
            mock.patch.object(search, "PROVIDER_HEALTH_FILE", self.cache_dir / "provider_health.json"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def test_cache_disabled_by_env_toggle(self):
        with mock.patch.dict(os.environ, {"WSP_DISABLE_CACHE": "1"}):
            self.assertTrue(search.cache_disabled_by_env())
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WSP_DISABLE_CACHE", None)
            self.assertFalse(search.cache_disabled_by_env())

    def _run_main(self, argv, env):
        fake_result = {
            "provider": "serper", "query": "test", "results": [
                {"title": "T", "url": "https://example.com/t", "snippet": "s", "score": 1.0},
            ], "images": [], "answer": "s",
        }
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(search, "search_serper", return_value=dict(fake_result)), \
                contextlib.redirect_stdout(buf):
            search.main()
        return json.loads(buf.getvalue())

    def test_search_results_cached_by_default(self):
        env = {"SERPER_API_KEY": "x" * 20}
        out = self._run_main(["search.py", "-q", "test", "-p", "serper"], env)
        self.assertFalse(out["cached"])
        cache_entries = [p for p in self.cache_dir.glob("*.json") if p.name != "provider_health.json"]
        self.assertEqual(len(cache_entries), 1)

    def test_no_cache_flag_skips_cache_writes(self):
        env = {"SERPER_API_KEY": "x" * 20}
        self._run_main(["search.py", "-q", "test", "-p", "serper", "--no-cache"], env)
        cache_entries = [p for p in self.cache_dir.glob("*.json") if p.name != "provider_health.json"]
        self.assertEqual(cache_entries, [])

    def test_disable_cache_env_skips_cache_writes(self):
        env = {"SERPER_API_KEY": "x" * 20, "WSP_DISABLE_CACHE": "1"}
        self._run_main(["search.py", "-q", "test", "-p", "serper"], env)
        cache_entries = [p for p in self.cache_dir.glob("*.json") if p.name != "provider_health.json"]
        self.assertEqual(cache_entries, [])


if __name__ == "__main__":
    unittest.main()
