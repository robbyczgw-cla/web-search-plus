# Web Search Plus

<p align="center">
  <img src="docs/assets/web-search-plus-logo.png" alt="web search plus logo" width="180">
</p>

Unified multi-provider web search and URL extraction for OpenClaw-style agent workflows.

Current version: **5.0.1**

> **Status: stable OpenClaw skill — compatibility path, not the main engine-development path.**
> This OpenClaw skill is kept usable and periodically synced for OpenClaw users, but active engine development happens on **[hermes-web-search-plus](https://github.com/robbyczgw-cla/hermes-web-search-plus)** and the **[web-search-plus-mcp](https://github.com/robbyczgw-cla/web-search-plus-mcp)** server. Since 5.0.1 the skill ships that engine itself (`scripts/wsp_core/`), so skill and engine share one version. The CLI stays **source-only**: ranked links and page text, no model-written answers. The native OpenClaw plugin remains `web-search-plus-plugin-v2`.

## ⚠️ Data handling & privacy

- **Search queries and extraction URLs are sent to the configured third-party providers** (Serper, Brave, Tavily, Linkup, Querit, Exa, Firecrawl, SerpBase, Keenable, You.com, or your SearXNG instance). When a provider fails, is slow or answers empty, the query also goes to the next one. Each provider's privacy policy and retention rules apply to what you send.
- **For sensitive queries, pick the provider explicitly** with `--provider <name>` so you control which third party receives them; self-hosted SearXNG keeps queries on your own infrastructure.
- **Avoid submitting internal/private URLs for extraction** — extraction URLs are forwarded to external services. Private/loopback/link-local targets and cloud metadata endpoints are blocked by default (opt out with `--allow-private-urls` / `WSP_ALLOW_PRIVATE_URLS=1` for trusted private networks).
- **Local caching is on by default**: search and extraction answers (with the query text), the full text of long extracted pages (up to 7 days), provider state (`v3/state.sqlite3`, `provider_stats.json`, `provider_health.json`) and routing receipts without query text are stored under `.cache` (or `WSP_CACHE_DIR`) with owner-only permissions (dir `0700`, files `0600`). Use `--no-cache` per call, `WSP_DISABLE_CACHE=1` for every call, `--clear-cache` to wipe, `--cache-stats` to inspect.
- **API keys are never logged or cached.**

## What changed in 5.0.1

The skill now runs the Web Search Plus 5.0.1 engine. Details and the full list of breaking changes are in [CHANGELOG.md](CHANGELOG.md).

- **Routing by query type.** Brave goes first for general, news, local and community queries, Exa for docs and academic queries, Serper for security and shopping queries. A provider without a key is skipped. Expect more Brave usage than before; Querit is no longer picked automatically.
- **Faster fallback.** The next provider starts when the current one fails, answers with nothing, or is slower than usual (at least 2.5 s). The first useful answer wins.
- **Extraction per URL.** A bad URL gets its own error entry; the other URLs are still extracted and retried on the next provider if needed.
- **5.0.1 fixes**: words like "synthesizer" no longer break Exa/Tavily/Linkup searches, long queries are shortened for Brave (600 characters / 75 words) instead of failing, `Retry-After` waits are capped at 30 s, a private SearXNG URL no longer breaks automatic search, and empty answers are not cached.
- **Breaking**: Exa deep / deep-reasoning and Linkup sourced answers are gone (the flags fall back to normal source search with a warning); a clearly detected query language is now sent to providers; the cache layout changed and extraction answers are cached; SerpBase moved to `api.serpbase.dev`; SearXNG is no longer auto-detected on localhost.
- Your 4.x flags, environment variables and `config.json` keep working.

## What changed in 4.3.1

- Queries starting with a dash reach providers unchanged: use `--query=-foo` or `-q -- "-foo"`.
- Exa snippets prefer highlights. Tavily receives native date filters, and Exa receipts reuse the publication bounds sent with each request, including research mode. `--time-range` wins over `--freshness`.
- `--cache-ttl SECONDS` now respects recency caps: live/hour 60 seconds, latest/day 300 seconds, week filters 1800 seconds. Cache hits include their age.
- Adaptive routing records every search-provider attempt, including retries and research members. POSIX file locking prevents concurrent writers from losing samples.
- Omitted counts use `defaults.max_results`; explicit `-n` wins. Both are clamped to 1–20.
- Search and extraction reuse HTTP connections per host within a process. Proxies and `WSP_HTTP_KEEPALIVE=0` use the standard transport. A stale pooled socket gets one retry on a fresh connection.
- The provider list stays unchanged. Jev, Parallel, DonSeTch, Hermes native backends and desktop settings remain outside this skill.

## What changed in 4.0.0

- **Source-only.** Perplexity via Kilo (`PERPLEXITY_API_KEY` / `KILOCODE_API_KEY`) is removed from routing, CLI, config, and docs. Leftover keys and `provider_priority` entries are ignored.
- This is **not** a copy of plugin 4.0.3: no DonSeTch, Parallel, Octen, or TinyFish in this skill runtime.
- Ranked source URLs and extracted page text only — no model-written answers.

## What changed in 3.3.0

Feature sync with `web-search-plus-plugin` v3.2.0 (hermes-web-search-plus v2.5.0–v2.9.0), adapted for the skill's CLI runtime:

- **Keenable** search + extraction provider — independent web index, keyed (`KEENABLE_API_KEY`) or keyless via the **opt-in** shared public tier (`WSP_KEENABLE_ALLOW_PUBLIC=1`, ~1000 req/hour, no SLA). Lowest priority everywhere: it never displaces a configured keyed provider.
- **Unified `--freshness`** (`day`/`week`/`month`/`year`): native date filters where supported, `freshness.applied=false` in metadata otherwise.
- **News vertical** (`--type news`): Serper serves Google News natively with correct parsing (date, source, thumbnail, position); other providers report `search_type.applied=false`.
- **Serper extraction** via the `scrape.serper.dev` webpage scraper — last position in the fallback chain, which is now **Tavily-first**: tavily → exa → linkup → firecrawl → you → keenable → serper.
- **Locale-aware defaults** with lightweight query language detection (`locale.country`/`locale.language` in config, `WSP_LOCALE_COUNTRY`/`WSP_LOCALE_LANGUAGE`, `"auto"` language inference, curated location hints — "mejores restaurantes Madrid" → `es`).
- **Spam/mirror result filtering** (strict domain matching, `quality.blocked_domains`/`quality.allowed_domains`), **domain-diversity reranking** (max 2 head slots per domain), `site:`/`--include-domains` bypass, reported via `metadata.result_filter`.
- **Adaptive provider performance memory**: rolling latency/result/error window (persisted as `provider_stats.json`) feeding bounded ±1.0 routing-score adjustments (`routing.adaptive_adjustments`).
- **Robustness**: `Retry-After` parsing with a single bounded inline retry for 429s, cooldown ladder decay after 30 minutes, configuration errors no longer trigger cooldowns, JSON decode failures surface as provider errors; transient HTTP codes now include 408/425/500/502/504.
- **Security**: extraction SSRF guard extended (CGNAT `100.64/10`, IPv4-mapped IPv6); look-alike domains no longer inherit authority boosts; inline base64 images replaced with `[IMAGE: alt]` placeholders; oversized extractions truncate to a head/tail window (`WSP_EXTRACT_CHAR_LIMIT`, default 15000).

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

- **Brave** — independent web index; first for general, news, local and community queries
- **Serper** — Google-style results; first for security and shopping queries
- **Exa** — semantic search with source URLs; first for docs and academic queries
- **Tavily** — research-oriented search; fourth in the fallback chain
- **Querit** — multilingual and international AI search; explicit-only unless allowed
- **Linkup** — citation/source-grounded search
- **Firecrawl** — search with scrape-ready metadata
- **You.com** — current-web / RAG-ish queries
- **SearXNG** — privacy-first self-hosted metasearch
- **SerpBase** — low-cost Google SERP, prepaid credits, **explicit/fallback-only**
- **Keenable** — independent web index, keyed or opt-in keyless public tier, lowest priority

## Extraction providers

`scripts/extract.py` supports (auto order, Tavily-first):

- Tavily
- Exa
- Linkup
- Firecrawl
- You.com
- Keenable
- Serper (webpage scraper)

Auto extraction tries them in that order; a URL that fails or comes back empty is retried on the next provider. Oversized pages are cut to a head/tail window (default 15,000 chars per page, `WSP_EXTRACT_CHAR_LIMIT`); inline base64 images become `[IMAGE: alt]` placeholders.

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
# local → Brave

python3 scripts/search.py -q "python asyncio TaskGroup documentation"
# docs → Exa

python3 scripts/search.py -q "latest OpenSSH CVE mitigation"
# security → Serper

python3 scripts/search.py -p linkup -q "find credible sources for AI tutoring outcomes"
python3 scripts/search.py -p firecrawl -q "YC startups web scraping"
python3 scripts/search.py -p serpbase -q "best laptop 2026"
# explicit SerpBase call — not used by automatic routing unless allowed
```

## Extraction examples

```bash
python3 scripts/extract.py --url https://example.com
python3 scripts/extract.py --url https://docs.linkup.so --provider linkup
python3 scripts/extract.py --url https://example.com --url https://example.org --include-images
python3 scripts/extract.py --url https://example.com --extract-char-limit 30000
```

Each URL gets its own result or `error` entry. Long pages return a head/tail window (default 15,000 characters per page) with a footer giving the real length and, when kept, the file holding the full text. The command exits 1 only when no URL returned content.

## Research mode & quality reports

```bash
# Several providers at once, results merged by rank, top sources extracted
python3 scripts/search.py --mode research -q "EU AI Act obligations for foundation models"
python3 scripts/search.py --mode research -q "..." --research-providers tavily linkup exa --research-time-budget 30

# Transparent routing/result diagnostics with authority signals
python3 scripts/search.py -q "official anthropic claude release notes" --quality-report
```

Research providers run concurrently. A page found by several providers ranks higher and lists them in `providers`; each extracted source gets up to two short query-ranked passages. For docs, security and news queries the site of the named vendor or project ranks first.

## Caching

Search and extraction answers are cached under `.cache` (override with `WSP_CACHE_DIR`) for up to 1 hour by default. Provider state lives next to them (`v3/state.sqlite3`, `provider_stats.json`, `provider_health.json`), and the full text of long extracted pages under `web/v3/` for up to 7 days. Directories are created `0700` and files `0600`.

```bash
python3 scripts/search.py -q "..." --cache-ttl 120  # shorter result-cache lifetime
python3 scripts/search.py -q "..." --no-cache    # bypass for one call
WSP_DISABLE_CACHE=1 python3 scripts/search.py -q "..."   # disable globally
python3 scripts/search.py --clear-cache          # wipe cached answers
python3 scripts/search.py --cache-stats          # inspect
```

Query recency, date filters and news/security queries (300 s) can only lower the TTL. A search with provider-specific flags (`--depth`, `--exa-type`, `--category`, ...) is not cached. Research mode queries providers directly and does not use the answer cache. 4.x cache entries are not reused.

## Routing notes

The first provider depends on the query type:

```text
academic, docs     -> exa
security, shopping -> serper
everything else    -> brave   (general, news, local, community)
```

Fallback follows `auto_routing.provider_priority`, by default:

```text
brave -> serper -> exa -> tavily -> you -> firecrawl -> linkup -> searxng -> keenable
```

Notable behavior:

- SerpBase and Querit are used only when named with `--provider` or allowed in `auto_routing.auto_allow`
- `"order": "custom"` in `auto_routing` makes `provider_priority` the order for every query
- An explicit `--provider` does not fall back unless you add `--allow-fallback`
- Failing or blocked providers are skipped; a slow or empty one is overtaken by the next

## Config files

- `.env.example` — provider credentials template
- `config.example.json` — routing and provider settings template
- `config.json` — your live local config (created/edited locally)

## Verification

Suggested local checks:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/search.py --explain-routing -q "find credible sources for climate change impacts"
python3 scripts/search.py doctor
python3 scripts/extract.py --url https://example.com --provider auto --compact
```

## Related references

- OpenClaw plugin: `../projects/web-search-plus-plugin`
- Hermes port: `../projects/hermes-web-search-plus`
