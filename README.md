# Web Search Plus

<p align="center">
  <img src="docs/assets/web-search-plus-logo.png" alt="web search plus logo" width="180">
</p>

Unified multi-provider web search and URL extraction for OpenClaw-style agent workflows.

Current version: **3.2.0**

## ⚠️ Data handling & privacy

- **Search queries and extraction URLs are sent to the configured third-party providers** (Serper, Brave, Tavily, Linkup, Querit, Exa, Firecrawl, SerpBase, Perplexity via Kilo, You.com, or your SearXNG instance). Each provider's privacy policy and retention rules apply to what you send.
- **For sensitive queries, pick the provider explicitly** with `--provider <name>` so you control which third party receives them; self-hosted SearXNG keeps queries on your own infrastructure.
- **Avoid submitting internal/private URLs for extraction** — extraction URLs are forwarded to external services. Private/loopback/link-local targets and cloud metadata endpoints are blocked by default (opt out with `--allow-private-urls` / `WSP_ALLOW_PRIVATE_URLS=1` for trusted private networks).
- **Local caching is on by default**: queries, results, and provider failure history (including `provider_health.json`) are persisted under `.cache` (or `WSP_CACHE_DIR`) with owner-only permissions (dir `0700`, files `0600`). Use `--no-cache` per call, `WSP_DISABLE_CACHE=1` globally, `--clear-cache` to wipe, `--cache-stats` to inspect.
- **API keys are never logged or cached.**

## What changed in 3.2.0

- **Research mode** (`--mode research`): up to three providers queried **concurrently** with deterministic result ordering, cross-provider dedup, and top-source extraction for grounding; `--research-time-budget` gates provider launches and extraction (port of hermes-web-search-plus v2.4.0).
- **Canonical-source intent reranking** + `--quality-report` authority signals (`canonical_domain_hits`, `demoted_domain_hits`, `canonical_top_result`) for official-release/docs/policy/finance/security queries (port of hermes v2.3.0).
- **ProviderSpec registry** (`scripts/provider_registry.py`) as the single source of truth for provider metadata.
- **Reliability**: retry backoff jitter (`RETRY_JITTER_FRACTION`), locked + atomic provider-health writes (port of hermes v2.4.0).
- **Security hardening** (SkillSpector findings): narrowly scoped skill triggers, SSRF guard for user-supplied URLs, owner-only cache permissions, `WSP_DISABLE_CACHE`, declared skill permissions, and the privacy disclosures above.

## What changed in 3.1.0

- Add **SerpBase** as the 11th search provider — low-cost Google SERP API with prepaid credits (https://serpbase.dev)
- Explicit/fallback-only by design: NOT in default auto-routing priority. Use `--provider serpbase` or opt-in via `config.json`.
- Closes [#4](https://github.com/robbyczgw-cla/web-search-plus/issues/4); brings skill to parity with `web-search-plus-plugin` v3.0.0

## What changed in 3.0.x

- Add **Brave**, **Linkup**, and **Firecrawl** search providers to the Python skill
- Add **URL extraction** via `scripts/extract.py` with auto fallback across Firecrawl, Linkup, Tavily, Exa, and You.com
- Align routing/fallback behavior and docs more closely with the OpenClaw plugin and Hermes port
- Keep existing **Exa deep** / **deep-reasoning**, cooldown, retry, cache, and SearXNG protections

## Search providers

- **Serper** — shopping, local, broad Google-style web results
- **Brave** — independent general web index, good broad fallback
- **Tavily** — research and explanation queries
- **Querit** — multilingual and international AI search
- **Linkup** — citation/source-grounded search
- **Exa** — semantic discovery and deep synthesis
- **Firecrawl** — search with scrape-ready metadata
- **Perplexity via Kilo** — answer-first web results
- **You.com** — current-web / RAG-ish queries
- **SearXNG** — privacy-first self-hosted metasearch
- **SerpBase** — low-cost Google SERP, prepaid credits, **explicit/fallback-only**

## Extraction providers

`scripts/extract.py` supports:

- Firecrawl
- Linkup
- Tavily
- Exa
- You.com

Auto extraction tries them in that order and falls back when a provider is unconfigured or fails.

## Quick start

```bash
cp .env.example .env
# fill in at least one key or SEARXNG_INSTANCE_URL

python3 scripts/search.py -q "latest OpenClaw release"
python3 scripts/extract.py --url https://example.com
```

Or use the interactive wizard:

```bash
python3 scripts/setup.py
```

## Search examples

```bash
python3 scripts/search.py -q "weather in Vienna today"
# auto-routes to Brave or Serper for broad current-web intent

python3 scripts/search.py -q "find credible sources for AI tutoring outcomes"
# auto-routes to Linkup when available

python3 scripts/search.py -q "latest AI policy updates in Germany"
# often Querit / Tavily depending on configured providers

python3 scripts/search.py -p exa --exa-depth deep -q "LLM scaling laws research"
python3 scripts/search.py -p firecrawl -q "YC startups web scraping"
python3 scripts/search.py -p serpbase -q "best laptop 2026"
# explicit SerpBase call — not used by auto-routing unless added to provider_priority
```

## Extraction examples

```bash
python3 scripts/extract.py --url https://example.com
python3 scripts/extract.py --url https://docs.linkup.so --provider linkup
python3 scripts/extract.py --url https://example.com --url https://example.org --include-images
```

## Research mode & quality reports

```bash
# Concurrent multi-provider search + dedup + top-source extraction
python3 scripts/search.py --mode research -q "EU AI Act obligations for foundation models"
python3 scripts/search.py --mode research -q "..." --research-providers tavily linkup exa --research-time-budget 30

# Transparent routing/result diagnostics with authority signals
python3 scripts/search.py -q "official anthropic claude release notes" --quality-report
```

Research providers run concurrently (wall-clock ≈ slowest provider); result ordering stays deterministic by submission order. For canonical-source query classes (vendor releases, official docs, policy PDFs, finance/IR, security advisories) results are reranked so primary sources beat mirrors — see `metadata.intent_rerank` and `quality_report.authority_signals`.

## Caching

Results are cached under `.cache` (override with `WSP_CACHE_DIR`) for 1 hour by default; provider failure history lives in `.cache/provider_health.json`. The directory is created `0700` and files `0600`.

```bash
python3 scripts/search.py -q "..." --no-cache    # bypass for one call
WSP_DISABLE_CACHE=1 python3 scripts/search.py -q "..."   # disable globally
python3 scripts/search.py --clear-cache          # wipe cached results
python3 scripts/search.py --cache-stats          # inspect
```

## Routing notes

Provider priority now defaults to:

```text
tavily -> linkup -> querit -> exa -> firecrawl -> perplexity -> brave -> serper -> you -> searxng
```

Notable behavior:

- Brave and Serper share generic web/current-info intent and use deterministic tie-breaking
- Linkup gets explicit boosts for citation/source/evidence-style queries
- Firecrawl can win discovery/research-ish queries when configured
- Exa can auto-upgrade to `deep` or `deep-reasoning` based on query signals
- Failing or cooling-down providers are skipped by fallback routing

## Config files

- `.env.example` — provider credentials template
- `config.example.json` — routing and provider settings template
- `config.json` — your live local config (created/edited locally)

## Verification

Suggested local checks:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/search.py --explain-routing -q "find credible sources for climate change impacts"
python3 scripts/extract.py --url https://example.com --provider auto --compact
```

## Related references

- OpenClaw plugin: `../projects/web-search-plus-plugin`
- Hermes port: `../projects/hermes-web-search-plus`
