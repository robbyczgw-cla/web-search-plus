"""Manifest, shipped-file footprint and URL guard checks."""

import json
import os
import re
import unittest
from unittest import mock

import _support
from _support import SKILL_DIR, SCRIPTS_DIR

import url_security

MANIFEST = json.loads((SKILL_DIR / "package.json").read_text(encoding="utf-8"))
SHIPPED_PY = sorted(SCRIPTS_DIR.rglob("*.py"))


class TriggerScopeTests(unittest.TestCase):
    """The skill manifest must not register generic auto-activation triggers."""

    GENERIC_TRIGGERS = {"search", "find", "look up", "lookup", "research", "browse", "web"}

    def test_no_generic_single_word_triggers(self):
        for trigger in MANIFEST["clawhub"]["triggers"]:
            self.assertNotIn(trigger.strip().lower(), self.GENERIC_TRIGGERS)

    def test_triggers_are_narrowly_scoped(self):
        triggers = MANIFEST["clawhub"]["triggers"]
        self.assertTrue(triggers)
        for trigger in triggers:
            words = trigger.strip().lower().split()
            self.assertTrue(len(words) >= 2 or "wsp" in words, trigger)

    def test_expected_scoped_triggers_present(self):
        triggers = {t.strip().lower() for t in MANIFEST["clawhub"]["triggers"]}
        for expected in ("web search plus", "wsp search", "search the web for", "extract url content"):
            self.assertIn(expected, triggers)


class ManifestTests(unittest.TestCase):
    def test_versions_are_aligned(self):
        skill_md = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        version = re.search(r"^version:\s*(\S+)", skill_md, re.M).group(1)
        engine = re.search(r"Version:\s*(\S+)", (SCRIPTS_DIR / "wsp_core" / "search.py").read_text()).group(1)
        self.assertEqual(MANIFEST["version"], "5.0.1")
        self.assertEqual(version, MANIFEST["version"])
        self.assertEqual(engine, MANIFEST["version"])

    def test_skill_md_metadata_is_valid_json(self):
        skill_md = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        line = re.search(r"^metadata:\s*(\{.*\})\s*$", skill_md, re.M).group(1)
        metadata = json.loads(line)
        self.assertIn("openclaw", metadata)

    def test_declared_hosts_cover_engine_endpoints(self):
        declared = set(MANIFEST["clawhub"]["permissions"]["network"]["outbound_hosts"])
        # Parallel ships inside the vendored engine but has no credential path in
        # this skill; api.you.com only appears as a signup link; api.serpbase.com
        # is the 4.x endpoint that wsp_skill rewrites to api.serpbase.dev.
        not_called = {"api.parallel.ai", "api.you.com", "api.serpbase.com"}
        found = set()
        pattern = re.compile(r"https://((?:api|google|scrape)\.[a-z0-9.-]+|ydc-index\.io)")
        for path in SHIPPED_PY:
            found.update(pattern.findall(path.read_text(encoding="utf-8")))
        self.assertEqual(sorted(found - declared - not_called), [])
        self.assertIn("api.serpbase.dev", declared)

    def test_declared_env_vars_cover_skill_settings(self):
        env = set(MANIFEST["clawhub"]["permissions"]["env"]["read"])
        for name in ("WSP_CACHE_DIR", "WSP_DISABLE_CACHE", "WSP_ALLOW_PRIVATE_URLS", "WSP_KEENABLE_ALLOW_PUBLIC",
                     "KEENABLE_ALLOW_PUBLIC", "WSP_EXTRACT_CHAR_LIMIT", "WSP_LOCALE_COUNTRY", "WSP_LOCALE_LANGUAGE",
                     "WSP_HTTP_KEEPALIVE", "WEB_SEARCH_PLUS_CONFIG"):
            self.assertIn(name, env)


class ShippedFootprintTests(unittest.TestCase):
    FORBIDDEN = re.compile(
        r"\bimport subprocess\b|\bsubprocess\.[A-Za-z_]|\bos\.system\(|\bos\.popen\(|\bPopen\(|\bos\.exec\w*\(|"
        r"\bos\.spawn\w*\(|\bhttp\.server\b|\bsocketserver\b|\.listen\(|\.bind\(\(|\bwebbrowser\b|"
        r"\bmultiprocessing\b|\bpty\.spawn"
    )

    def test_no_subprocess_or_listening_socket_code(self):
        offenders = []
        for path in SHIPPED_PY:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                code = line.split("#", 1)[0]
                if self.FORBIDDEN.search(code):
                    offenders.append(f"{path.relative_to(SKILL_DIR)}:{number}: {line.strip()}")
        self.assertEqual(offenders, [])

    def test_cli_only_engine_parts_are_not_shipped(self):
        core = SCRIPTS_DIR / "wsp_core"
        for name in ("ui.py", "web", "jev_setup.py"):
            self.assertFalse((core / name).exists(), name)
        self.assertFalse((SCRIPTS_DIR / "providers.d").exists())
        self.assertFalse((SKILL_DIR / "providers.d").exists())

    def test_no_providers_d_discovery_target(self):
        from wsp_core import provider_registry

        self.assertFalse(provider_registry.PROVIDERS_DIRECTORY.exists())
        for excluded in ("donsetch", "octen", "tinyfish"):
            self.assertNotIn(excluded, provider_registry.PROVIDER_SPECS)


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
            self.assertEqual(url_security.validate_outbound_url("https://example.com/page"),
                             "https://example.com/page")

    def test_private_opt_in_allows_private_targets(self):
        self.assertEqual(url_security.validate_outbound_url("http://192.168.1.10/status", allow_private=True),
                         "http://192.168.1.10/status")


if __name__ == "__main__":
    unittest.main()
