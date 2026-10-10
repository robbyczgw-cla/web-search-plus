"""OpenClaw skill adapter over the vendored Web Search Plus engine.

The engine in ``scripts/wsp_core/`` is a copy of the ``wsp_core`` package of
hermes-web-search-plus v5.0.1 (commit 82cceb3) plus the follow-up Brave query
limit fix (600 characters / 75 words, commit 3115de6). Not copied: the Operator
Console server (``ui.py``, ``web/``) and the TypeSafe setup helper
(``jev_setup.py``); ``providers.d`` is not shipped. No engine file is edited.
This module keeps the skill's own interface on top of the engine:

- environment variable aliases from the 4.x skill (``WSP_KEENABLE_ALLOW_PUBLIC``,
  ``WSP_LOCALE_COUNTRY``/``WSP_LOCALE_LANGUAGE``, ``WSP_DISABLE_CACHE``,
  ``WSP_ALLOW_PRIVATE_URLS``, ``WSP_EXTRACT_CHAR_LIMIT``);
- 4.x ``config.json`` layouts (top-level ``locale``, provider country/language
  keys, the old default provider order, the old SerpBase endpoint);
- the skill's provider set: Parallel ships in the engine but is not part of this
  skill, so it is removed from every automatic chain and refused when named;
- the skill's file and network footprint: ``.env`` files are read from the skill
  directory only (not from a Hermes profile), an invalid ``config.json`` is
  reported instead of renamed, and the optional TypeSafe (JEV) helper stays off;
- the CLI flags of ``scripts/search.py`` and ``scripts/extract.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

SCRIPTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# --- Provider plugins are not part of the skill -----------------------------
# The engine imports every module in scripts/providers.d when its provider
# registry loads. The skill ships no such directory and runs no provider code
# beyond the vendored engine, so refuse to start while one exists instead of
# executing it.
PROVIDERS_D = SCRIPTS_DIR / "providers.d"
if PROVIDERS_D.exists():
    sys.stderr.write(
        f"Web Search Plus skill: {PROVIDERS_D} is not supported in the skill and would "
        "load extra provider code. Remove it, or use the Hermes plugin for "
        "providers.d providers.\n"
    )
    raise SystemExit(2)

# --- Bootstrap: must run before wsp_core.config is imported -----------------
# wsp_core.config loads .env files when it is imported: scripts/.env, the skill
# directory's .env and the Hermes profile .env. The skill reads only its own
# directory, so the Hermes profile path is pointed at the skill .env (deduped).
from wsp_core import env_loader as _env_loader  # noqa: E402

_env_loader.get_hermes_env_path = lambda: SKILL_DIR / ".env"

from wsp_core import config as _config  # noqa: E402
from wsp_core.provider_registry import DEFAULT_PROVIDER_PRIORITY  # noqa: E402

from url_security import BLOCKED_METADATA_HOSTS, validate_outbound_url  # noqa: E402

# Providers the engine ships but this skill does not offer.
EXCLUDED_PROVIDERS = ("parallel",)
EXCLUDED_ENV_VARS = ("PARALLEL_API_KEY",)

# 4.x skill name -> engine name. The old name is copied over only when the
# engine name is unset, so an explicit engine setting always wins.
ENV_ALIASES = {
    "WSP_KEENABLE_ALLOW_PUBLIC": "KEENABLE_ALLOW_PUBLIC",
}

DISABLE_CACHE_ENV = "WSP_DISABLE_CACHE"
ALLOW_PRIVATE_ENV = "WSP_ALLOW_PRIVATE_URLS"
LOCALE_COUNTRY_ENV = "WSP_LOCALE_COUNTRY"
LOCALE_LANGUAGE_ENV = "WSP_LOCALE_LANGUAGE"
EXTRACT_CHAR_LIMIT_ENV = "WSP_EXTRACT_CHAR_LIMIT"
DEFAULT_EXTRACT_CHAR_LIMIT = 15000

# Default provider order written by every 4.x skill setup (config.example.json).
SKILL_4X_DEFAULT_PRIORITY = [
    "tavily", "linkup", "querit", "exa", "firecrawl", "brave", "serper", "you", "searxng", "keenable",
]
# 4.x skill SerpBase endpoint; the engine uses SerpBase's current API.
SKILL_4X_SERPBASE_URLS = {"https://api.serpbase.com/search"}
# Provider sections whose country/language keys the 4.x skill ignored (only
# serper.country/language seeded the global locale). In the engine these keys
# pin the provider's locale, so they are moved out of the way.
_PROVIDER_LOCALE_KEYS = {
    "serper": ("country", "language"),
    "serpbase": ("country", "language"),
    "brave": ("country", "search_lang"),
    "querit": ("country", "language"),
    "firecrawl": ("country",),
    "you": ("country", "language"),
    "searxng": ("language",),
}

# 4.x synthesis options that the source-only engine no longer runs.
LEGACY_EXA_DEPTHS = ("deep", "deep-reasoning")
LEGACY_LINKUP_OUTPUT_TYPES = ("sourcedAnswer",)


def _env_on(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _notice(message: str) -> None:
    print(json.dumps({"warning": message}, ensure_ascii=False), file=sys.stderr)


def apply_env_aliases() -> None:
    """Map 4.x env names to the engine and drop credentials of excluded providers."""
    for old, new in ENV_ALIASES.items():
        value = os.environ.get(old)
        if value is not None and not os.environ.get(new):
            os.environ[new] = value
    for name in EXCLUDED_ENV_VARS:
        os.environ.pop(name, None)


def _warn_invalid_config(config_path: Path, reason: str) -> None:
    """Report an invalid config.json without renaming it (the engine moves it aside)."""
    _notice(f"Invalid config ignored ({config_path.name}): {reason}")


_config._quarantine_runtime_config = _warn_invalid_config
apply_env_aliases()

# --- Setup guidance: point at this skill instead of the Hermes plugin --------
_HERMES_SETUP_RE = re.compile(r"python3 ~/\.hermes/plugins/web-search-plus/setup\.py setup(?: --preset [\w-]+| [\w-]+)?")
_GUIDANCE_REPLACEMENTS = (
    ("to your Hermes profile .env", "to the skill's .env file"),
    ("Store API keys in your Hermes profile .env, not inline in config.json.",
     "Store API keys in the skill's .env file or the environment, not inline in config.json."),
)
SKILL_SETUP_COMMAND = "python3 scripts/setup.py"


def skill_guidance(value: Any) -> Any:
    """Rewrite the engine's Hermes setup hints for this skill, recursively."""
    if isinstance(value, str):
        text = _HERMES_SETUP_RE.sub(SKILL_SETUP_COMMAND, value)
        for old, new in _GUIDANCE_REPLACEMENTS:
            text = text.replace(old, new)
        return text
    if isinstance(value, list):
        return [skill_guidance(item) for item in value]
    if isinstance(value, dict):
        return {key: skill_guidance(item) for key, item in value.items()}
    return value


def _install_guidance_patches() -> None:
    from wsp_core import errors_v3, extract as extract_module, search as search_module

    original_missing = errors_v3.missing_key_guidance
    errors_v3.missing_key_guidance = lambda provider: skill_guidance(original_missing(provider))

    original_add = _config.add_provider_setup_guidance

    def add_provider_setup_guidance(payload, *args, **kwargs):
        original_add(payload, *args, **kwargs)
        payload.update(skill_guidance(dict(payload)))

    for module in (_config, search_module, extract_module):
        module.add_provider_setup_guidance = add_provider_setup_guidance


_install_guidance_patches()


def _section(config: Dict[str, Any], *path: str) -> Dict[str, Any]:
    node = config
    for key in path:
        child = node.get(key)
        if not isinstance(child, dict):
            child = {}
            node[key] = child
        node = child
    return node


def _adapt_locale(config: Dict[str, Any]) -> None:
    locale = _section(config, "defaults", "locale")
    legacy = config.get("locale")
    legacy = legacy if isinstance(legacy, dict) else {}
    serper = config.get("serper") if isinstance(config.get("serper"), dict) else {}
    seeds = {
        "country": [legacy.get("country"), os.environ.get(LOCALE_COUNTRY_ENV),
                    serper.get("country") if str(serper.get("country") or "").lower() != "us" else None],
        "language": [legacy.get("language"), os.environ.get(LOCALE_LANGUAGE_ENV),
                     serper.get("language") if str(serper.get("language") or "").lower() != "en" else None],
    }
    for key, candidates in seeds.items():
        if locale.get(key):
            continue
        for value in candidates:
            text = str(value or "").strip().lower()
            if text:
                locale[key] = text
                break
    for provider, keys in _PROVIDER_LOCALE_KEYS.items():
        section = config.get(provider)
        if isinstance(section, dict):
            for key in keys:
                section.pop(key, None)


def _adapt_routing(config: Dict[str, Any]) -> None:
    auto = _section(config, "auto_routing")
    priority = [str(p) for p in auto.get("provider_priority") or []]
    if auto.get("order") != "custom" and priority[: len(SKILL_4X_DEFAULT_PRIORITY)] == SKILL_4X_DEFAULT_PRIORITY:
        priority = list(DEFAULT_PROVIDER_PRIORITY)
    auto["provider_priority"] = [p for p in priority if p not in EXCLUDED_PROVIDERS]
    auto["extract_provider_priority"] = [
        p for p in auto.get("extract_provider_priority") or [] if p not in EXCLUDED_PROVIDERS
    ]
    disabled = [p for p in auto.get("disabled_providers") or [] if p not in EXCLUDED_PROVIDERS]
    auto["disabled_providers"] = disabled + list(EXCLUDED_PROVIDERS)
    allow = auto.get("auto_allow") if isinstance(auto.get("auto_allow"), dict) else {}
    allow.update({p: False for p in EXCLUDED_PROVIDERS})
    auto["auto_allow"] = allow
    if auto.get("fallback_provider") in EXCLUDED_PROVIDERS:
        auto["fallback_provider"] = "serper"
    if config.get("default_provider") in EXCLUDED_PROVIDERS:
        config["default_provider"] = None
    # 4.x: with auto-routing off every query went to defaults.provider.
    if auto.get("enabled", True) is False and not config.get("default_provider"):
        legacy_default = (config.get("defaults") or {}).get("provider")
        if legacy_default and legacy_default not in EXCLUDED_PROVIDERS and legacy_default not in disabled:
            config["default_provider"] = legacy_default
    for provider in EXCLUDED_PROVIDERS:
        section = config.get(provider)
        if isinstance(section, dict):
            section.pop("api_key", None)
            section.pop("apiKey", None)


def adapt_config(config: Dict[str, Any], *, allow_private_urls: bool = False) -> Dict[str, Any]:
    """Apply the skill's compatibility rules to an engine config in place."""
    _adapt_locale(config)
    _adapt_routing(config)
    serpbase = config.get("serpbase")
    if isinstance(serpbase, dict) and serpbase.get("api_url") in SKILL_4X_SERPBASE_URLS:
        serpbase["api_url"] = _config.DEFAULT_CONFIG["serpbase"]["api_url"]
    if allow_private_urls or _env_on(ALLOW_PRIVATE_ENV):
        _section(config, "extract")["allow_private_urls"] = True
    raw_limit = str(os.environ.get(EXTRACT_CHAR_LIMIT_ENV, "")).strip()
    if raw_limit:
        try:
            limit = int(raw_limit)
        except ValueError:
            limit = 0
        if limit > 0:
            _section(config, "web")["extract_char_limit"] = limit
    # The optional TypeSafe (JEV) helper calls a service outside the declared
    # host list; the skill keeps it off.
    _section(config, "jev")["enabled"] = False
    return config


def load_config() -> Dict[str, Any]:
    """Engine config from the skill's config.json, adapted for the skill."""
    return adapt_config(_config.load_config())


def prepare_cache_dir() -> None:
    """Keep everything the engine writes owner-only (dir 0700, files 0600).

    The engine creates some state files (``v3/state.sqlite3``) with the process
    umask; the CLI entry points tighten it instead of editing engine code.
    """
    from wsp_core.cache import CACHE_DIR

    os.umask(0o077)
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError:
        pass


def cache_disabled() -> bool:
    return str(os.environ.get(DISABLE_CACHE_ENV, "")).strip() == "1"


def private_urls_allowed() -> bool:
    return _env_on(ALLOW_PRIVATE_ENV)


# --- search.py ---------------------------------------------------------------


def _patch_search_parser(search_module) -> None:
    original_build_parser = getattr(search_module, "_skill_original_build_parser", search_module.build_parser)
    search_module._skill_original_build_parser = original_build_parser

    def build_parser(config: Dict[str, Any]) -> argparse.ArgumentParser:
        parser = original_build_parser(config)
        for action in parser._actions:
            if action.dest == "provider" and action.choices:
                action.choices = [c for c in action.choices if c not in EXCLUDED_PROVIDERS]
            elif action.dest == "bench_providers" and action.choices:
                action.choices = [c for c in action.choices if c not in EXCLUDED_PROVIDERS]
            elif action.dest == "exa_depth":
                action.choices = list(action.choices or ["normal"]) + list(LEGACY_EXA_DEPTHS)
            elif action.dest == "linkup_output_type":
                action.choices = list(action.choices or ["searchResults"]) + list(LEGACY_LINKUP_OUTPUT_TYPES)
        parser.add_argument(
            "--allow-private-urls",
            action="store_true",
            help=f"Allow URLs (--similar-url, research extraction) on private/internal networks; "
                 f"cloud metadata endpoints stay blocked (see {ALLOW_PRIVATE_ENV})",
        )
        original_parse_args = parser.parse_args

        def parse_args(args=None, namespace=None):
            ns = original_parse_args(args, namespace)
            return _finish_search_args(parser, ns, config)

        parser.parse_args = parse_args
        return parser

    search_module.build_parser = build_parser


def _finish_search_args(parser, ns, config: Dict[str, Any]):
    for provider in [ns.provider, *(ns.research_providers or [])]:
        if provider and str(provider).strip().lower() in EXCLUDED_PROVIDERS:
            parser.error(f"provider '{provider}' is not part of this skill")
    if ns.exa_depth in LEGACY_EXA_DEPTHS:
        _notice(f"--exa-depth {ns.exa_depth} is no longer supported (source-only results); using normal")
        ns.exa_depth = "normal"
    if ns.linkup_output_type in LEGACY_LINKUP_OUTPUT_TYPES:
        _notice("--linkup-output-type sourcedAnswer is no longer supported (source-only results); using searchResults")
        ns.linkup_output_type = "searchResults"
    if isinstance(ns.max_results, int):
        ns.max_results = max(1, min(20, ns.max_results))
    allow_private = bool(ns.allow_private_urls) or private_urls_allowed()
    if allow_private:
        _section(config, "extract")["allow_private_urls"] = True
    if ns.similar_url:
        try:
            ns.similar_url = validate_outbound_url(ns.similar_url, allow_private=allow_private, label="--similar-url")
        except ValueError as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
            sys.exit(1)
    if cache_disabled():
        ns.no_cache = True
    return ns


# Search options the v3 request carries itself. Every other parsed CLI option
# is copied onto the per-attempt arguments from the CLI invocation.
_V3_REQUEST_OPTIONS = frozenset({
    "query", "provider", "max_results", "exa_depth", "time_range", "freshness", "search_type",
    "quality_report", "include_domains", "exclude_domains", "mode", "research_time_budget",
    "language", "country", "allow_fallback", "no_cache", "cache_ttl",
})
_cli_args_template = None


def _run_cli_search_v3(search_module, args, config: Dict[str, Any]):
    """Run a normal CLI search through the engine's v3 path (hedged fallback).

    Upstream ``python search.py`` runs providers one after another; the Hermes
    tool uses the v3 path, which starts the next provider when one fails, is
    slow or answers empty. The skill CLI uses the v3 path too and carries the
    remaining CLI options (provider-specific flags) into each attempt.
    """
    global _cli_args_template
    from wsp_core import providers as providers_module
    from wsp_core.compat_v3 import legacy_request_to_v3, v3_response_to_legacy_search
    from wsp_core.contract_v3 import Capability
    from wsp_core.orchestrator_v3 import execute_v3_request
    from wsp_core.query_limits import MAX_QUERY_CHARS
    from wsp_core.urls import domain_filter_tokens

    defaults = vars(search_module.default_search_args(config))
    custom_options = any(
        getattr(args, name, None) != value for name, value in defaults.items() if name not in _V3_REQUEST_OPTIONS
    )
    runtime_config = config
    requested = str(args.provider or "auto").strip().lower()
    if requested == "auto" and providers_module.public_suffix_entries(args.include_domains, args.exclude_domains):
        runtime_config = json.loads(json.dumps(config))
        auto = runtime_config.setdefault("auto_routing", {})
        auto["disabled_providers"] = sorted(
            set(auto.get("disabled_providers") or []) | set(providers_module.DOMAIN_SUFFIX_FILTER_UNSUPPORTED)
        )
    request = legacy_request_to_v3(
        Capability.SEARCH,
        policy_mode=str((runtime_config.get("routing") or {}).get("policy_mode", "classic")),
        payload={
            "query": args.query[:MAX_QUERY_CHARS],
            "provider": requested,
            "count": args.max_results,
            "depth": args.exa_depth,
            "time_range": args.time_range,
            "freshness": args.freshness,
            "search_type": args.search_type,
            "include_domains": domain_filter_tokens(args.include_domains) or None,
            "exclude_domains": domain_filter_tokens(args.exclude_domains) or None,
            "mode": "normal",
            "quality_report": bool(args.quality_report),
            "language": args.language,
            "country": args.country,
            "allow_fallback": bool(args.allow_fallback) if requested != "auto" else True,
            # The response cache keys on the request options above. A search
            # with other provider flags is not served from or written to it.
            "no_cache": bool(args.no_cache or custom_options),
            "cache_ttl": int(args.cache_ttl),
        },
    )
    _cli_args_template = args
    execution = execute_v3_request(request, search_module._search_adapter(), runtime_config)
    payload = v3_response_to_legacy_search(execution)
    return payload, (1 if payload.get("error") else 0)


def _patch_search_execution(search_module) -> None:
    if getattr(search_module, "_skill_execution_patched", False):
        return
    original_core = search_module._execute_search_request_core
    original_args_from_v3 = search_module._search_args_from_v3

    def search_args_from_v3(request, config):
        args = original_args_from_v3(request, config)
        template = _cli_args_template
        if template is not None:
            for name, value in vars(template).items():
                if name not in _V3_REQUEST_OPTIONS and not name.startswith("_"):
                    setattr(args, name, value)
        return args

    def execute_search_request_core(args, config):
        if (
            getattr(args, "_v3_engine_owned_attempt", False)
            or getattr(args, "mode", "normal") != "normal"
            or not getattr(args, "query", None)
        ):
            return original_core(args, config)
        return _run_cli_search_v3(search_module, args, config)

    def extract_plus(urls, provider="auto", output_format="markdown", include_images=False,
                     include_raw_html=False, render_js=False, spans=False, spans_query=None,
                     config=None, max_wall_time_ms=None):
        # search.py --extract-urls and research-mode extraction get the same
        # guards and per-page budget as scripts/extract.py.
        return extract_urls(
            list(urls or []), provider=provider, output_format=output_format, include_images=include_images,
            include_raw_html=include_raw_html, render_js=render_js, spans=spans, spans_query=spans_query,
            config=config, max_wall_time_ms=max_wall_time_ms,
        )

    search_module._search_args_from_v3 = search_args_from_v3
    search_module._execute_search_request_core = execute_search_request_core
    search_module.extract_plus = extract_plus
    search_module._skill_execution_patched = True


def run_search() -> None:
    """``python3 scripts/search.py`` entry point."""
    from wsp_core import search as search_module

    prepare_cache_dir()
    search_module.load_config = load_config
    _patch_search_parser(search_module)
    _patch_search_execution(search_module)
    search_module.main()


# --- extract.py --------------------------------------------------------------


def extract_char_limit(override: Optional[int] = None, config: Optional[Dict[str, Any]] = None) -> int:
    if override and override > 0:
        return override
    try:
        value = int(((config or {}).get("web") or {}).get("extract_char_limit") or 0)
    except (TypeError, ValueError):
        value = 0
    return value if value > 0 else DEFAULT_EXTRACT_CHAR_LIMIT


def _split_content(content: str, limit: int):
    head_chars = min(max(1, (limit * 2) // 3), max(1, limit - 1))
    tail_chars = min(max(1, limit // 5), max(1, limit - head_chars))
    if head_chars + tail_chars >= len(content):
        return content, "", 0
    head = content[:head_chars].rstrip()
    tail = content[-tail_chars:].lstrip()
    return head, tail, max(0, len(content) - len(head) - len(tail))


_BASE64_MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(\s*data:image/[^)]+\)", re.IGNORECASE)
_BASE64_HTML_IMAGE_RE = re.compile(r"<img\b(?=[^>]*\bsrc=[\"']data:image/)[^>]*>", re.IGNORECASE)
_HTML_ALT_RE = re.compile(r"\balt=[\"']([^\"']*)[\"']", re.IGNORECASE)


def sanitize_extract_content(content: str) -> str:
    """Replace inline base64 images with ``[IMAGE: alt]`` placeholders."""

    def markdown_image(match):
        return f"[IMAGE: {(match.group(1) or 'image').strip() or 'image'}]"

    def html_image(match):
        alt = _HTML_ALT_RE.search(match.group(0))
        return f"[IMAGE: {((alt.group(1) if alt else '') or 'image').strip() or 'image'}]"

    return _BASE64_HTML_IMAGE_RE.sub(html_image, _BASE64_MARKDOWN_IMAGE_RE.sub(markdown_image, content))


def apply_char_limit(item: Dict[str, Any], limit: int) -> None:
    """Sanitize one extracted page and cut it to a head/tail window when over ``limit``.

    The engine caps the whole batch to its context budget; this adds the
    skill's per-URL inline budget. The footer reports the page's real length
    and the stored full-text file when the engine kept one.
    """
    content = item.get("content")
    if not isinstance(content, str):
        return
    raw_same = item.get("raw_content") == content
    content = sanitize_extract_content(content)
    item["content"] = content
    if raw_same:
        item["raw_content"] = content
    elif isinstance(item.get("raw_content"), str):
        item["raw_content"] = sanitize_extract_content(item["raw_content"])
    full_text = item.get("full_text") if isinstance(item.get("full_text"), dict) else {}
    original = full_text.get("original_chars")
    if not isinstance(original, int):
        original = item.get("original_content_length") if isinstance(item.get("original_content_length"), int) else len(content)
    if len(content) <= limit:
        if original > len(content):
            item["truncated"] = True
            item["original_chars"] = original
        return
    head, tail, _omitted = _split_content(content, limit)
    shown = len(head) + len(tail)
    footer = [
        "",
        "---",
        f"[Content truncated: original {original} chars; {max(0, original - shown)} chars omitted; showing head and tail.]",
    ]
    if full_text.get("stored") and full_text.get("path"):
        footer.append(f"Full cleaned text stored at: {full_text['path']}")
    else:
        footer.append(f"Raise {EXTRACT_CHAR_LIMIT_ENV} (or --extract-char-limit) for a larger inline budget, "
                      "or extract a more specific URL for the omitted section.")
    new_content = f"{head}\n\n[... omitted middle ...]\n\n{tail}\n" + "\n".join(footer)
    if item.get("raw_content") == content:
        item["raw_content"] = new_content
    item["content"] = new_content
    item["truncated"] = True
    item["original_chars"] = original


def _metadata_host(url: str) -> bool:
    from urllib.parse import urlparse

    try:
        host = (urlparse(url.strip()).hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    return host in BLOCKED_METADATA_HOSTS


def extract_urls(
    urls: List[str],
    provider: str = "auto",
    output_format: str = "markdown",
    include_images: bool = False,
    include_raw_html: bool = False,
    render_js: bool = False,
    spans: bool = False,
    spans_query: Optional[str] = None,
    allow_private: bool = False,
    char_limit: Optional[int] = None,
    no_cache: bool = False,
    config: Optional[Dict[str, Any]] = None,
    max_wall_time_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """Extract URLs through the engine with the skill's guards and inline budget."""
    from wsp_core import extract as extract_module
    from wsp_core.compat_v3 import legacy_request_to_v3, v3_response_to_legacy_extract
    from wsp_core.contract_v3 import Capability
    from wsp_core.orchestrator_v3 import execute_v3_request

    selected = provider or "auto"
    if str(selected).lower() in EXCLUDED_PROVIDERS:
        return {"provider": selected, "results": [], "error": f"Provider {selected} is not part of this skill",
                "requested_provider": selected}
    urls = [u.strip() for u in urls if isinstance(u, str) and u.strip()]
    if not urls:
        return {"provider": selected, "results": [], "error": "No URLs provided", "requested_provider": selected}
    runtime_config = adapt_config(config if config is not None else _config.load_config(),
                                  allow_private_urls=allow_private)
    no_cache = no_cache or cache_disabled()

    # With private targets allowed the engine skips its network checks; cloud
    # metadata endpoints stay blocked here, per URL.
    blocked = {}
    if runtime_config.get("extract", {}).get("allow_private_urls") is True:
        blocked = {u: f"Extraction URL blocked: {u} is a cloud metadata endpoint" for u in urls if _metadata_host(u)}
    to_fetch = [u for u in urls if u not in blocked]

    if to_fetch:
        request = legacy_request_to_v3(
            Capability.EXTRACT,
            {
                "urls": to_fetch,
                "provider": selected,
                "output_format": output_format,
                "include_images": include_images,
                "include_raw_html": include_raw_html,
                "render_js": render_js,
                "spans": spans,
                "spans_query": spans_query,
                "no_cache": no_cache,
                "max_wall_time_ms": max_wall_time_ms,
            },
        )
        execution = execute_v3_request(request, extract_module._extract_adapter(), runtime_config)
        result = v3_response_to_legacy_extract(execution)
        extract_module._resolve_full_text_paths(result, runtime_config)
    else:
        result = {"provider": selected, "results": [], "error": "; ".join(blocked.values())}

    if blocked and to_fetch:
        by_url = {item.get("url"): item for item in result.get("results") or [] if isinstance(item, dict)}
        merged = []
        for url in urls:
            if url in blocked:
                merged.append({"url": url, "error": blocked[url]})
            elif url in by_url:
                merged.append(by_url.pop(url))
        merged.extend(by_url.values())
        result["results"] = merged

    limit = extract_char_limit(char_limit, runtime_config)
    for item in result.get("results") or []:
        if isinstance(item, dict) and not item.get("error"):
            apply_char_limit(item, limit)
    return result


def extract_succeeded(result: Dict[str, Any]) -> bool:
    return not result.get("error") and any(
        isinstance(item, dict) and not item.get("error")
        and any(item.get(field) for field in ("content", "text", "raw_content", "markdown", "html"))
        for item in result.get("results", [])
    )


def build_extract_parser() -> argparse.ArgumentParser:
    from wsp_core.provider_registry import EXTRACT_PROVIDER_IDS

    providers = [p for p in EXTRACT_PROVIDER_IDS if p not in EXCLUDED_PROVIDERS]
    parser = argparse.ArgumentParser(description="Extract URL content with automatic provider fallback")
    parser.add_argument("--url", dest="urls", action="append", help="URL to extract (repeatable)")
    parser.add_argument("--provider", default="auto", type=str.lower, choices=["auto"] + providers)
    parser.add_argument("--format", default="markdown", choices=["markdown", "html"])
    parser.add_argument("--include-images", action="store_true")
    parser.add_argument("--include-raw-html", action="store_true")
    parser.add_argument("--render-js", action="store_true")
    parser.add_argument("--spans", action="store_true", help="Select query-ranked passages from the extracted text")
    parser.add_argument("--spans-query", help="Query used to rank --spans passages")
    parser.add_argument("--allow-private-urls", action="store_true",
                        help=f"Allow URLs that resolve to private/internal networks (off by default; see {ALLOW_PRIVATE_ENV}); "
                             "cloud metadata endpoints stay blocked")
    parser.add_argument("--extract-char-limit", type=int,
                        help=f"Inline content budget per URL in characters (default {DEFAULT_EXTRACT_CHAR_LIMIT}; "
                             f"longer pages return a head/tail window). Set {EXTRACT_CHAR_LIMIT_ENV} to change the default.")
    parser.add_argument("--no-cache", action="store_true",
                        help=f"Do not read or write the extraction cache (set {DISABLE_CACHE_ENV}=1 to disable it globally)")
    parser.add_argument("--compact", action="store_true", help="Print compact JSON")
    return parser


def run_extract(argv: Optional[List[str]] = None) -> None:
    """``python3 scripts/extract.py`` entry point."""
    args = build_extract_parser().parse_args(argv)
    prepare_cache_dir()
    result = extract_urls(
        args.urls or [],
        provider=args.provider,
        output_format=args.format,
        include_images=args.include_images,
        include_raw_html=args.include_raw_html,
        render_js=args.render_js,
        spans=args.spans,
        spans_query=args.spans_query,
        allow_private=args.allow_private_urls,
        char_limit=args.extract_char_limit,
        no_cache=args.no_cache,
    )
    print(json.dumps(result, ensure_ascii=False, indent=None if args.compact else 2))
    if not extract_succeeded(result):
        sys.exit(1)
