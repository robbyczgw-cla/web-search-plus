---
name: web-search-plus
version: 5.0.1
description: Search the web and extract URLs with routing across Serper, Brave, Tavily, Querit, Linkup, Exa, Firecrawl, You.com, SearXNG, SerpBase, and Keenable. Returns ranked sources and page text; supports freshness filters and research across providers.
tags: [search, keenable, news, locale, web-search, web-extract, serper, brave, tavily, querit, linkup, exa, firecrawl, you, searxng, serpbase, google, multilingual-search, research, semantic-search, auto-routing, multi-provider, shopping, rag, free-tier, privacy, self-hosted]
metadata: {"openclaw":{"requires":{"bins":["python3","bash"],"env":{"SERPER_API_KEY":"optional","BRAVE_API_KEY":"optional","TAVILY_API_KEY":"optional","QUERIT_API_KEY":"optional","LINKUP_API_KEY":"optional","EXA_API_KEY":"optional","FIRECRAWL_API_KEY":"optional","YOU_API_KEY":"optional","SEARXNG_INSTANCE_URL":"optional","SERPBASE_API_KEY":"optional — explicit/fallback-only Google SERP provider with prepaid credits","KEENABLE_API_KEY":"optional — Keenable independent web index (search + extraction); keyless public tier opt-in via WSP_KEENABLE_ALLOW_PUBLIC=1"},"note":"Only ONE provider key or SEARXNG_INSTANCE_URL is needed for search. Brave, Serper and Exa get the most use from automatic routing. Extraction requires one of Tavily, Exa, Linkup, Firecrawl, You.com, Keenable, or Serper.","permissions":{"network":"outbound HTTPS to the configured provider API hosts only (google.serper.dev, api.search.brave.com, api.tavily.com, api.querit.ai, api.linkup.so, api.exa.ai, api.firecrawl.dev, ydc-index.io, api.serpbase.dev, api.keenable.ai, scrape.serper.dev, plus any user-configured SearXNG instance)","env":"reads provider *_API_KEY vars, SEARXNG_INSTANCE_URL, SEARXNG_ALLOW_PRIVATE, KEENABLE_ALLOW_PUBLIC, WEB_SEARCH_PLUS_CONFIG, WSP_BUDGET_PREFLIGHT_OFF, and WSP_* settings (WSP_CACHE_DIR, WSP_DISABLE_CACHE, WSP_ALLOW_PRIVATE_URLS, WSP_KEENABLE_ALLOW_PUBLIC, WSP_EXTRACT_CHAR_LIMIT, WSP_LOCALE_COUNTRY, WSP_LOCALE_LANGUAGE, WSP_HTTP_KEEPALIVE)","filesystem":"writes to the cache directory (.cache by default, WSP_CACHE_DIR override): search and extraction response cache, full text of long extracted pages, provider state (state.sqlite3, provider_stats.json, provider_health.json) and routing receipts without query text; the setup wizard writes config.json in the skill directory"}}}}
---

# Web Search Plus

**Stop choosing search providers. Let the skill do it for you.**

One command searches across **11 search providers**, and a companion command extracts page text from URLs. Since 5.0 the skill runs the same engine as Web Search Plus 5.0.1: automatic routing picks the first provider by query type and moves on quickly when a provider fails, is slow or returns nothing.

This skill is **source-only**: ranked links and extracted page text, not model-written answers. The native OpenClaw plugin is `web-search-plus-plugin-v2`.

---

## 🔐 Data Handling & Privacy

**Read this before searching with sensitive queries.**

- **Search queries and extraction URLs are sent to third-party providers.** Every search sends your query text to the provider that serves it (Serper, Brave, Tavily, Linkup, Querit, Exa, Firecrawl, SerpBase, Keenable, You.com, or your SearXNG instance). When a provider fails, is slow or returns nothing, the query also goes to the next provider in line. Every extraction sends the target URL to the chosen extraction provider (Tavily, Exa, Linkup, Firecrawl, You.com, Keenable, Serper), whose servers fetch the page. Each provider's own privacy policy and retention rules apply.
- **For sensitive work, select the provider explicitly** (`--provider <name>`) instead of relying on automatic routing, so you control exactly which third party receives the query. An explicit provider does not fall back unless you add `--allow-fallback`. Self-hosted SearXNG keeps queries on infrastructure you control.
- **Do not submit internal or private URLs for extraction.** URLs you extract are forwarded to external services. The skill blocks private, loopback and link-local targets and cloud metadata endpoints by default (see Security below).
- **Local caching is on by default.** Search and extraction answers (including the query text), the full text of long extracted pages (kept up to 7 days), provider state (`v3/state.sqlite3`: circuit breakers, budgets, latency samples; `provider_stats.json`, `provider_health.json`) and routing receipts without query text are stored under the cache directory (`.cache` by default, `WSP_CACHE_DIR` to relocate). Directories are created `0700`, files `0600`.
  - Bypass the answer cache for one call: `--no-cache`
  - Bypass it for every call: `WSP_DISABLE_CACHE=1` (provider state is still kept)
  - Wipe cached answers: `python3 scripts/search.py --clear-cache` (inspect with `--cache-stats`)
- **API keys are never logged or cached**; error text is sanitized before it reaches the cache or stderr.

---

## 🎯 Triggers

To avoid auto-activating on everyday requests, the manifest registers only narrowly scoped trigger phrases:

- `web search plus`
- `wsp search`
- `search the web for`
- `multi-provider web search`
- `extract url content`
- `extract content from url`

Generic words like "search", "find", "look up", or "research" intentionally do **not** trigger this skill.

---

## ✨ What Makes This Different?

- **Just search**: no need to think about which provider to use
- **Routing by query type**: Brave for general, news, local and community queries, Exa for docs and academic queries, Serper for security and shopping queries
- **Fast fallback**: if the first provider fails, answers with nothing, or is slower than usual (at least 2.5 s), the next one starts and the first useful answer wins
- **11 providers, 1 interface**: general web, research, semantic discovery, privacy-first, prepaid-credits, and extraction-capable providers together
- **URL extraction included**: markdown/HTML page text with fallback across seven providers; one bad URL no longer sinks the batch
- **Research mode**: several providers at once, results merged by rank, top sources extracted with short query-ranked passages
- **Works with just 1 credential**: start with any single provider, add more later

---

## 🚀 Quick Start

```bash
# Interactive setup (recommended for first run)
python3 scripts/setup.py

# Or manually
cp .env.example .env
python3 scripts/search.py -q "latest OpenClaw release"
python3 scripts/extract.py --url https://example.com
```

With only one key, Brave is the best single choice for automatic routing; Exa and Serper cover the other query types.

---

## 🔑 Providers

### Search providers

- **Brave**: independent web index; first choice for general, news, local and community queries
- **Serper**: Google-style results; first choice for security and shopping queries
- **Exa**: semantic search with source URLs; first choice for docs and academic queries, also `--similar-url`
- **Tavily**: research-oriented search; fourth in the fallback chain
- **Querit**: multilingual and international search; explicit-only unless allowed in `auto_routing.auto_allow`
- **Linkup**: source-grounded search
- **Firecrawl**: search with scrape-ready metadata
- **You.com**: current-web snippets
- **SearXNG**: private/self-hosted search; no API key, just an instance URL
- **SerpBase**: low-cost Google SERP with prepaid credits; explicit/fallback-only (`--provider serpbase`)
- **Keenable**: independent web index; keyed via `KEENABLE_API_KEY` or keyless against the **opt-in** shared public tier (`WSP_KEENABLE_ALLOW_PUBLIC=1`, no SLA, warning in result metadata). Last in the fallback chain

### Extraction providers

`scripts/extract.py` falls back in this order:

1. **Tavily**
2. **Exa**
3. **Linkup**
4. **Firecrawl**
5. **You.com**
6. **Keenable**
7. **Serper** (webpage scraper via `scrape.serper.dev`)

---

## 🧠 Routing at a Glance

Automatic routing gives each query one of eight types and picks the first provider from that:

```text
academic, docs   → Exa
security, shopping → Serper
everything else  → Brave   (general, news, local, community)
```

A provider without a key is skipped. Fallback then follows `auto_routing.provider_priority`, by default:

```text
brave → serper → exa → tavily → you → firecrawl → linkup → searxng → keenable
```

SerpBase and Querit are in the list too but are only used when named with `--provider` or allowed with `"auto_routing": {"auto_allow": {"querit": true}}`. To use your own order for every query instead, set `"auto_routing": {"order": "custom", "provider_priority": [...]}` in `config.json`.

Examples:

```bash
python3 scripts/search.py -q "weather in Vienna today"                 # local → Brave
python3 scripts/search.py -q "python asyncio TaskGroup documentation"  # docs → Exa
python3 scripts/search.py -q "iPhone 16 Pro Max price"                 # shopping → Serper
python3 scripts/search.py -p firecrawl -q "YC startups web scraping"   # explicit provider
python3 scripts/search.py -p serpbase -q "best laptop 2026"            # explicit SerpBase
```

Show the decision without searching:

```bash
python3 scripts/search.py --explain-routing -q "your query"
```

Queries starting with a dash can use `--query=-foo` or `-q -- "-foo"`. When `-n` is omitted, `defaults.max_results` supplies the count (fallback 5); counts are clamped to 1–20. Long queries are shortened at a word boundary when a provider has a length limit (Brave: 600 characters / 75 words), and the output says so.

`--cache-ttl SECONDS` sets the answer-cache lifetime; recency, date filters and news/security queries (300 s) can only lower it. `--no-cache` bypasses the cache. Set `WSP_HTTP_KEEPALIVE=0` to disable connection reuse; requests through proxies use the standard transport.

### Freshness, news vertical & locale

```bash
python3 scripts/search.py -q "AI regulation" --freshness week
# providers with native date filters receive the mapped value; others run the
# normal search and report freshness.applied=false in metadata

python3 scripts/search.py -p serper --type news -q "quantum computing"
# Serper serves the Google news vertical natively; other providers report
# search_type.applied=false

python3 scripts/search.py -q "beste Kaffeehäuser Wien"
# location hints in the query set the country (at); a clearly German query is
# searched in German. Resolved values appear in metadata.locale.
```

Without a configured language, a clearly detected query language is sent to the provider; unclear queries go out as English. Set a fixed language with `"defaults": {"locale": {"language": "en"}}` in `config.json` or `WSP_LOCALE_LANGUAGE=en`.

### Domain filters and result quality

`--include-domains` / `--exclude-domains` work on every search provider (Brave, Serper, SerpBase and You.com get `site:` / `-site:` operators). Known mirror and spam domains are removed, and one domain fills at most two of the top results; explicit domain filters bypass both. For docs, security and news queries the site of the named vendor or project ranks first.

---

## 📖 Extraction Examples

```bash
python3 scripts/extract.py --url https://example.com
python3 scripts/extract.py --url https://docs.linkup.so --provider linkup
python3 scripts/extract.py --url https://example.com --url https://example.org --include-images
python3 scripts/extract.py --url https://example.com --format html --include-raw-html
python3 scripts/extract.py --url https://example.com --provider serper
python3 scripts/extract.py --url https://example.com --extract-char-limit 30000
python3 scripts/extract.py --url https://example.com --spans --spans-query "pricing"
```

Each URL gets its own result: a blocked or failing URL gets an `error` entry and the others are still extracted, retried on the next provider if needed, in the order you gave them. Long pages return a head/tail window plus a footer with the real page length (default 15,000 characters per page; `WSP_EXTRACT_CHAR_LIMIT` or `--extract-char-limit`). When the engine kept the full text, the footer names the file. Inline base64 images become `[IMAGE: alt]` placeholders. Extraction answers are cached for an hour (`--no-cache` to bypass).

---

## 🔬 Research Mode & Quality Reports

Research mode queries up to three providers at once, merges their results by rank (a page found by several providers ranks higher and lists them in `providers`), then extracts the top sources and adds short query-ranked passages:

```bash
python3 scripts/search.py --mode research -q "EU AI Act obligations for foundation models"
python3 scripts/search.py --mode research -q "..." --research-providers tavily linkup exa
python3 scripts/search.py --mode research -q "..." --research-extract-count 2 --research-time-budget 30
```

Quality reports add routing and result diagnostics, including authority signals:

```bash
python3 scripts/search.py -q "official anthropic claude release notes" --quality-report
```

---

## ⚙️ Configuration Notes

- `.env.example` documents supported env vars; `.env` is read from the skill directory only
- `config.example.json` shows the 5.0 layout; `config.json` is your local config
- 4.x `config.json` files keep working: a top-level `locale` block, provider `country`/`language` keys, the old default provider order and the old SerpBase endpoint are translated when the config is loaded
- SerpBase is **explicit/fallback-only** by default
- Keenable is last in search and extraction fallback; enable keyless use with `WSP_KEENABLE_ALLOW_PUBLIC=1` (or `KEENABLE_ALLOW_PUBLIC=1`, or `"keenable": {"allow_public": true}`)
- Locale defaults: `"defaults": {"locale": {"country": "...", "language": "..."}}` in `config.json` (or `WSP_LOCALE_COUNTRY`/`WSP_LOCALE_LANGUAGE`); `--country`/`--language` always win
- Rate limits: `Retry-After` waits are capped at 30 s; a longer one skips the retry and leaves the provider blocked (at most one hour). Missing keys never block a provider
- Extra commands: `python3 scripts/search.py doctor` (offline configuration check), `python3 scripts/search.py --extract-urls URL ...`

---

## 🔒 Security

**URL SSRF protection (extraction, `--similar-url`):**
- Only `http` / `https` URLs are accepted; URLs that different URL parsers read differently are rejected
- Hostnames are resolved and blocked if they point at private, loopback, link-local or reserved ranges; error messages do not reveal the resolved address
- Cloud metadata endpoints (`169.254.169.254`, `metadata.google.internal`) are always blocked
- Opt out for trusted private networks with `--allow-private-urls` or `WSP_ALLOW_PRIVATE_URLS=1` (off by default; metadata endpoints stay blocked)

**SearXNG SSRF protection:**
- Enforces `http` / `https` only
- A SearXNG URL on a private or LAN address needs `SEARXNG_ALLOW_PRIVATE=1`; without it SearXNG is skipped and other providers keep working

**Local data:**
- Cache directory `0700`, files `0600`
- API keys are never written to the cache or logs
- The skill starts no subprocesses and opens no listening sockets

**Declared permissions** (see `package.json → clawhub.permissions`):
- Outbound network access limited to the listed provider API hosts (plus any user-configured SearXNG instance)
- Environment reads limited to provider `*_API_KEY` vars, `SEARXNG_*`, `KEENABLE_ALLOW_PUBLIC`, `WEB_SEARCH_PLUS_CONFIG` and `WSP_*` settings
- Filesystem writes limited to the cache directory (and `config.json` from the setup wizard)

---

## ✅ Verification

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/search.py --explain-routing -q "find credible sources for climate change impacts"
python3 scripts/search.py doctor
python3 scripts/extract.py --url https://example.com --provider auto --compact
```
