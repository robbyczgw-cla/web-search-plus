"""Shared test setup: no network, no real keys, a throwaway cache directory.

Import this module before anything from ``scripts/``. The engine fixes its
cache directory when it is imported, and it loads ``.env`` files from the skill
directory, so both are neutralised here first.
"""

import atexit
import contextlib
import io
import os
import shutil
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"

CACHE_DIR = Path(tempfile.mkdtemp(prefix="wsp-skill-tests-"))
atexit.register(shutil.rmtree, CACHE_DIR, True)
os.environ["WSP_CACHE_DIR"] = str(CACHE_DIR)
# Never read the developer's own config.json.
os.environ["WEB_SEARCH_PLUS_CONFIG"] = str(CACHE_DIR / "no-config.json")

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import wsp_skill  # noqa: E402
from wsp_core import providers  # noqa: E402
from wsp_core.provider_registry import PROVIDER_SPECS, keyless_public_env_var  # noqa: E402

PROVIDER_ENV_VARS = sorted(
    {spec.env_var for spec in PROVIDER_SPECS.values()}
    | {keyless_public_env_var(p) for p, spec in PROVIDER_SPECS.items() if spec.keyless}
    | {
        "WSP_KEENABLE_ALLOW_PUBLIC", "WSP_DISABLE_CACHE", "WSP_ALLOW_PRIVATE_URLS",
        "WSP_LOCALE_COUNTRY", "WSP_LOCALE_LANGUAGE", "WSP_EXTRACT_CHAR_LIMIT",
        "SEARXNG_INSTANCE_URL", "SEARXNG_ALLOW_PRIVATE", "TYPESAFE_API_KEY", "TYPESAFE_API_KEY_FILE",
    }
)

FAKE_KEYS = {
    "BRAVE_API_KEY": "brave-test-key-1234567",
    "SERPER_API_KEY": "serper-test-key-123456",
    "EXA_API_KEY": "exa-test-key-123456789",
    "TAVILY_API_KEY": "tvly-test-key-12345678",
    "LINKUP_API_KEY": "linkup-test-key-123456",
    "FIRECRAWL_API_KEY": "fc-test-key-1234567890",
}

FAKE_DNS = {
    "example.com": "93.184.216.34",
    "example.org": "93.184.216.34",
    "internal.example.test": "10.1.2.3",
}


def fake_getaddrinfo(host, port, *args, **kwargs):
    """Resolve the fixture hosts; every other lookup fails (tests stay offline)."""
    address = FAKE_DNS.get(host) or ("93.184.216.34" if str(host).endswith(".example.com") else None)
    if address:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]
    raise socket.gaierror(f"no DNS in tests: {host}")


def _no_network(*_args, **_kwargs):
    raise AssertionError("a test tried to open a network connection")


def search_answer(name, calls=None, count=3, url_prefix=None):
    def search_fn(query, api_key=None, max_results=5, **_kwargs):
        if calls is not None:
            calls.append((name, query))
        prefix = url_prefix or f"https://{name}"
        return {"provider": name, "query": query, "results": [
            {"title": f"{name} result {i}", "url": f"{prefix}{i}.example.com/page", "snippet": f"from {name}"}
            for i in range(count)
        ]}
    return search_fn


def search_empty(name, calls=None):
    def search_fn(query, api_key=None, max_results=5, **_kwargs):
        if calls is not None:
            calls.append((name, query))
        return {"provider": name, "query": query, "results": []}
    return search_fn


class SkillTestCase(unittest.TestCase):
    """Clean environment, fake DNS, no sockets, empty cache for every test."""

    keys = {}

    def setUp(self):
        for child in CACHE_DIR.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink()
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        for name in PROVIDER_ENV_VARS:
            os.environ.pop(name, None)
        os.environ.update(self.keys)
        for target, attr, value in (
            (socket, "getaddrinfo", fake_getaddrinfo),
            (socket, "create_connection", _no_network),
            (socket.socket, "connect", _no_network),
        ):
            patcher = mock.patch.object(target, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def patch_provider(self, name, fn):
        patcher = mock.patch.object(providers, name, fn)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cli(self, entry, argv):
        """Run a skill entry point in-process; return (exit_code, stdout, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with mock.patch.object(sys, "argv", [entry.__name__] + list(argv)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                if entry is wsp_skill.run_extract:
                    entry(list(argv))
                else:
                    entry()
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
        return code, out.getvalue(), err.getvalue()
