"""Central provider metadata registry for Web Search Plus.

This module is deliberately data-only: search, extraction, setup, and the
permission/documentation surfaces import it so provider metadata has one
source of truth instead of one copy per surface.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class ProviderSpec:
    """Public, non-secret metadata for one provider."""

    provider: str
    env_var: str
    display_name: str
    description: str
    config_section: str
    supports_search: bool
    supports_extract: bool
    capability_labels: Tuple[str, ...]
    api_hosts: Tuple[str, ...]
    auto_allowed_by_default: bool = True
    recommended: bool = False
    free_tier: str = "API key required"
    signup_url: str = ""
    alt_env_vars: Tuple[str, ...] = ()


_PROVIDER_SPECS = (
    ProviderSpec(
        provider="serper",
        env_var="SERPER_API_KEY",
        display_name="Serper",
        description="Google-like SERP results for facts, shopping, local and news queries.",
        config_section="serper",
        supports_search=True,
        supports_extract=False,
        capability_labels=("search", "news", "shopping", "local"),
        api_hosts=("google.serper.dev",),
        free_tier="2,500 one-time credits",
        signup_url="https://serper.dev",
    ),
    ProviderSpec(
        provider="brave",
        env_var="BRAVE_API_KEY",
        display_name="Brave Search",
        description="Independent general web index; strong non-Google complement.",
        config_section="brave",
        supports_search=True,
        supports_extract=False,
        capability_labels=("search", "news", "local"),
        api_hosts=("api.search.brave.com",),
        free_tier="$5 free monthly credits",
        signup_url="https://brave.com/search/api/",
    ),
    ProviderSpec(
        provider="tavily",
        env_var="TAVILY_API_KEY",
        display_name="Tavily",
        description="Research/tutorial-focused search with extraction support.",
        config_section="tavily",
        supports_search=True,
        supports_extract=True,
        capability_labels=("search", "extract", "research"),
        api_hosts=("api.tavily.com",),
        recommended=True,
        free_tier="1,000 free searches/month",
        signup_url="https://tavily.com",
    ),
    ProviderSpec(
        provider="querit",
        env_var="QUERIT_API_KEY",
        display_name="Querit",
        description="Multilingual and real-time AI search.",
        config_section="querit",
        supports_search=True,
        supports_extract=False,
        capability_labels=("search", "multilingual"),
        api_hosts=("api.querit.ai",),
        free_tier="1,000 free searches/month",
        signup_url="https://querit.ai",
    ),
    ProviderSpec(
        provider="linkup",
        env_var="LINKUP_API_KEY",
        display_name="Linkup",
        description="Citation-grounded retrieval and cheap clean extraction.",
        config_section="linkup",
        supports_search=True,
        supports_extract=True,
        capability_labels=("search", "extract", "citations"),
        api_hosts=("api.linkup.so",),
        recommended=True,
        free_tier="€5 free monthly credits",
        signup_url="https://app.linkup.so",
    ),
    ProviderSpec(
        provider="exa",
        env_var="EXA_API_KEY",
        display_name="Exa",
        description="Semantic discovery, alternatives, deep and deep-reasoning synthesis.",
        config_section="exa",
        supports_search=True,
        supports_extract=True,
        capability_labels=("search", "extract", "semantic"),
        api_hosts=("api.exa.ai",),
        free_tier="1,000 free searches/month",
        signup_url="https://exa.ai",
    ),
    ProviderSpec(
        provider="firecrawl",
        env_var="FIRECRAWL_API_KEY",
        display_name="Firecrawl",
        description="Search with scrape-ready metadata; robust extraction fallback for JS-heavy pages.",
        config_section="firecrawl",
        supports_search=True,
        supports_extract=True,
        capability_labels=("search", "extract", "js"),
        api_hosts=("api.firecrawl.dev",),
        free_tier="500 one-time credits",
        signup_url="https://www.firecrawl.dev/app/api-keys",
    ),
    ProviderSpec(
        provider="perplexity",
        env_var="PERPLEXITY_API_KEY",
        display_name="Perplexity (via Kilo Gateway)",
        description="Direct answer-style search with citations through the Kilo gateway.",
        config_section="perplexity",
        supports_search=True,
        supports_extract=False,
        capability_labels=("search", "answer"),
        api_hosts=("api.kilo.ai",),
        free_tier="Depends on Kilo plan",
        signup_url="https://api.kilo.ai",
        alt_env_vars=("KILOCODE_API_KEY",),
    ),
    ProviderSpec(
        provider="you",
        env_var="YOU_API_KEY",
        display_name="You.com",
        description="Current-web, RAG-friendly snippets with combined web + news.",
        config_section="you",
        supports_search=True,
        supports_extract=True,
        capability_labels=("search", "extract", "rag"),
        api_hosts=("ydc-index.io",),
        free_tier="Limited free tier",
        signup_url="https://api.you.com",
    ),
    ProviderSpec(
        provider="searxng",
        env_var="SEARXNG_INSTANCE_URL",
        display_name="SearXNG",
        description="Self-hosted, privacy-preserving metasearch instance.",
        config_section="searxng",
        supports_search=True,
        supports_extract=False,
        capability_labels=("search", "self-hosted", "privacy"),
        api_hosts=("user-configured SearXNG instance",),
        free_tier="Free if self-hosted",
        signup_url="https://docs.searxng.org/admin/installation.html",
    ),
    ProviderSpec(
        provider="serpbase",
        env_var="SERPBASE_API_KEY",
        display_name="SerpBase",
        description="Low-cost Google SERP via prepaid credits; explicit/fallback-only by default.",
        config_section="serpbase",
        supports_search=True,
        supports_extract=False,
        capability_labels=("search",),
        api_hosts=("api.serpbase.com",),
        auto_allowed_by_default=False,
        free_tier="100 free searches, paid packs available",
        signup_url="https://serpbase.dev",
    ),
)

PROVIDER_SPECS: Dict[str, ProviderSpec] = {spec.provider: spec for spec in _PROVIDER_SPECS}
SEARCH_PROVIDER_IDS = tuple(spec.provider for spec in _PROVIDER_SPECS if spec.supports_search)
# Extraction order matches scripts/extract.py's benchmarked fallback chain.
EXTRACT_PROVIDER_IDS = ("firecrawl", "linkup", "tavily", "exa", "you")
DEFAULT_PROVIDER_PRIORITY = (
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
    # serpbase is intentionally absent: explicit/fallback-only by design.
)
PROVIDER_ENV_KEYS = tuple(spec.env_var for spec in _PROVIDER_SPECS)
ALL_PROVIDER_ENV_KEYS = tuple(
    env for spec in _PROVIDER_SPECS for env in (spec.env_var,) + spec.alt_env_vars
)
PROVIDER_API_HOSTS = tuple(
    host for spec in _PROVIDER_SPECS for host in spec.api_hosts
)


def known_secret_values(extra_secrets=()) -> tuple:
    """Collect configured credential values (from env) for log/persist redaction.

    SEARXNG_INSTANCE_URL is excluded: it is an endpoint, not a secret, and is
    legitimately part of error messages.
    """
    secrets = set()
    for env_var in ALL_PROVIDER_ENV_KEYS:
        if env_var == "SEARXNG_INSTANCE_URL":
            continue
        value = os.environ.get(env_var, "")
        if len(value) >= 8:
            secrets.add(value)
    for value in extra_secrets:
        if isinstance(value, str) and len(value) >= 8:
            secrets.add(value)
    return tuple(secrets)


def redact_secrets(text: str, extra_secrets=()) -> str:
    """Replace any configured credential values appearing in text.

    Defense in depth: provider error bodies should never echo credentials,
    but if one does, it must not reach logs, stderr, or the on-disk
    provider-health/cache files.
    """
    if not text:
        return text
    for secret in known_secret_values(extra_secrets):
        if secret in text:
            text = text.replace(secret, "***REDACTED***")
    return text


def env_var_for(provider: str) -> str:
    """Primary credential env var for a provider."""
    return PROVIDER_SPECS[provider].env_var


def signup_url_for(provider: str) -> str:
    return PROVIDER_SPECS[provider].signup_url
