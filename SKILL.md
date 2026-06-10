---
name: web-search-plus
version: 3.2.0
description: Unified multi-provider web search and URL extraction skill with intelligent auto-routing across Serper, Brave, Tavily, Querit, Linkup, Exa, Firecrawl, Perplexity, You.com, SearXNG, and SerpBase. Sends queries/URLs to the configured third-party provider APIs and caches results plus provider failure history locally under .cache (configurable, can be disabled).
tags: [search, web-search, web-extract, serper, brave, tavily, querit, linkup, exa, firecrawl, perplexity, you, searxng, serpbase, google, multilingual-search, research, semantic-search, auto-routing, multi-provider, shopping, rag, free-tier, privacy, self-hosted, kilo]
metadata: {"openclaw":{"requires":{"bins":["python3","bash"],"env":{"SERPER_API_KEY":"optional","BRAVE_API_KEY":"optional","TAVILY_API_KEY":"optional","QUERIT_API_KEY":"optional","LINKUP_API_KEY":"optional","EXA_API_KEY":"optional","FIRECRAWL_API_KEY":"optional","PERPLEXITY_API_KEY":"optional — direct Perplexity provider credential","KILOCODE_API_KEY":"optional — alternative Perplexity provider via Kilo Gateway","YOU_API_KEY":"optional","SEARXNG_INSTANCE_URL":"optional","SERPBASE_API_KEY":"optional — explicit/fallback-only Google SERP provider with prepaid credits"},"note":"Only ONE provider key or SEARXNG_INSTANCE_URL is needed for search. Extraction requires one of Firecrawl, Linkup, Tavily, Exa, or You.com.","permissions":{"network":"outbound HTTPS to the configured provider API hosts only (google.serper.dev, api.search.brave.com, api.tavily.com, api.querit.ai, api.linkup.so, api.exa.ai, api.firecrawl.dev, api.kilo.ai, ydc-index.io, api.serpbase.com, plus any user-configured SearXNG instance)","env":"reads provider *_API_KEY vars, SEARXNG_INSTANCE_URL, SEARXNG_ALLOW_PRIVATE, and WSP_* settings (WSP_CACHE_DIR, WSP_DISABLE_CACHE, WSP_ALLOW_PRIVATE_URLS)","filesystem":"writes only to the cache directory (.cache by default, WSP_CACHE_DIR override): cached search results and provider_health.json"}}}
---

# Web Search Plus

**Stop choosing search providers. Let the skill do it for you.**

This skill now connects you to **11 search providers** and adds a companion extraction flow for pulling content from URLs. Broad web query? → Brave or Serper. Research question? → Tavily or Exa. Need citations and grounding? → Linkup. Want scrape-ready content? → Firecrawl. Prefer privacy? → SearXNG. Need low-cost Google SERP with prepaid credits? → SerpBase (explicit/fallback-only).

---

## 🔐 Data Handling & Privacy

**Read this before searching with sensitive queries.**

- **Search queries and extraction URLs are sent to third-party providers.** Every search transmits your query text to whichever configured provider is selected (Serper, Brave, Tavily, Linkup, Querit, Exa, Firecrawl, Parallel-family gateways, SerpBase, Perplexity via Kilo, You.com, or your SearXNG instance). Every extraction transmits the target URL to the chosen extraction provider (Firecrawl, Linkup, Tavily, Exa, You.com), whose infrastructure then fetches the page. Each provider's own privacy policy and retention rules apply.
- **For sensitive work, select the provider explicitly** (`--provider <name>`) instead of relying on auto-routing, so you control exactly which third party receives the query. Self-hosted SearXNG keeps queries on infrastructure you control.
- **Do not submit internal or private URLs for extraction.** URLs you extract are forwarded to external services. The skill additionally blocks private/loopback/link-local targets and cloud metadata endpoints by default (see Security below).
- **Local caching is on by default.** Queries, results, and provider failure history are persisted under the cache directory (`.cache` by default, `WSP_CACHE_DIR` to relocate), including `provider_health.json` with provider error messages. Cache files are written with owner-only permissions (dir `0700`, files `0600`).
  - Bypass for one call: `--no-cache`
  - Disable globally: `WSP_DISABLE_CACHE=1`
  - Wipe: `python3 scripts/search.py --clear-cache` (inspect with `--cache-stats`)
- **API keys are never logged or persisted** by the skill; errors are sanitized before they reach the cache or stderr.

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

- **Just search** — no need to think about which provider to use
- **Smart routing** — query analysis picks the best provider automatically
- **11 providers, 1 interface** — general web, research, semantic discovery, direct answers, privacy-first, prepaid-credits, and extraction-capable providers together
- **URL extraction included** — pull markdown/HTML content with fallback across five providers
- **Research mode** — concurrent multi-provider search + dedup + top-source extraction in one call
- **Canonical-source reranking** — official/primary sources beat mirror domains for release/docs/policy/finance/security queries
- **Works with just 1 credential** — start with any single provider, add more later
- **Free/self-hosted options available** — SearXNG can run at $0 API cost

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

The wizard explains providers, collects keys, and sets defaults.

---

## 🔑 Providers

### Search providers

- **Serper** — shopping, prices, local, and general Google-style results; fast broad fallback
- **Brave** — independent web index and generic current-web queries; strong non-Google complement
- **Tavily** — research, explanations, and synthesis; strong research routing
- **Querit** — multilingual and international updates; good for cross-language recency
- **Linkup** — source-grounded/citation-heavy search; evidence-first queries
- **Exa** — semantic discovery, similar sites, and deep research; supports `deep` + `deep-reasoning`
- **Firecrawl** — search with scrape-ready metadata; also strong extraction provider
- **Perplexity** — direct answers with citations; via `PERPLEXITY_API_KEY` or `KILOCODE_API_KEY`
- **You.com** — current-web / RAG-friendly snippets; also supports extraction
- **SearXNG** — private/self-hosted search; no API key, just instance URL
- **SerpBase** — low-cost Google SERP with prepaid credits; explicit/fallback-only (opt-in via `--provider serpbase` or add to `provider_priority` in `config.json`)

### Extraction providers

`scripts/extract.py` auto-falls back across:

1. **Firecrawl**
2. **Linkup**
3. **Tavily**
4. **Exa**
5. **You.com**

---

## 🧠 Routing at a Glance

Default priority (SerpBase excluded by design — opt-in only):

```text
tavily → linkup → querit → exa → firecrawl → perplexity → brave → serper → you → searxng
```

Examples:

```bash
python3 scripts/search.py -q "weather in Vienna today"
# generic current-web intent → Brave or Serper

python3 scripts/search.py -q "find credible sources for AI tutoring outcomes"
# citation/evidence intent → Linkup

python3 scripts/search.py -q "latest AI policy updates in Germany"
# multilingual + recency → Querit or Tavily

python3 scripts/search.py -p exa --exa-depth deep -q "LLM scaling laws research"
python3 scripts/search.py -p firecrawl -q "YC startups web scraping"
python3 scripts/search.py -p serpbase -q "best laptop 2026"   # explicit SerpBase
```

Debug routing:

```bash
python3 scripts/search.py --explain-routing -q "your query"
```

---

## 📖 Extraction Examples

```bash
python3 scripts/extract.py --url https://example.com
python3 scripts/extract.py --url https://docs.linkup.so --provider linkup
python3 scripts/extract.py --url https://example.com --url https://example.org --include-images
python3 scripts/extract.py --url https://example.com --format html --include-raw-html
```

---

## 🔬 Research Mode & Quality Reports

Research mode queries up to three providers **concurrently** (wall-clock cost ≈ slowest provider, not the sum), deduplicates across providers with deterministic ordering, then extracts the top sources for grounding:

```bash
python3 scripts/search.py --mode research -q "EU AI Act obligations for foundation models"
python3 scripts/search.py --mode research -q "..." --research-providers tavily linkup exa
python3 scripts/search.py --mode research -q "..." --research-extract-count 2 --research-time-budget 30
```

The time budget gates which providers launch and whether extraction runs; exhausted steps are reported in `routing.provider_errors` / `routing.extraction_error` instead of failing the call.

Quality reports add transparent routing/result diagnostics, including **authority signals** for canonical-source routing classes (`canonical_domain_hits`, `demoted_domain_hits`, `canonical_top_result`):

```bash
python3 scripts/search.py -q "official anthropic claude release notes" --quality-report
```

For those canonical classes (official vendor releases, official docs, policy PDFs, finance/IR, security advisories) results are also **reranked for intent**: primary sources are boosted, mirror/aggregator domains demoted (`metadata.intent_rerank` shows what changed).

---

## ⚙️ Configuration Notes

- `.env.example` documents supported env vars
- `config.example.json` includes provider priority and provider-specific defaults
- `config.json` is your local runtime config
- SearXNG still supports explicit URL config and docker-aware auto-detection
- SerpBase is **explicit/fallback-only** by default; to include in auto-routing, append `"serpbase"` to `auto_routing.provider_priority` in `config.json`

---

## 🔒 Security

**URL SSRF protection (extraction, `--similar-url`):**
- Only `http` / `https` URLs are accepted
- Hostnames are resolved and blocked if they point at private/loopback/link-local/reserved ranges (`10/8`, `127/8`, `169.254/16`, `172.16/12`, `192.168/16`, `::1`, `fc00::/7`, `fe80::/10`, `0.0.0.0`)
- Cloud metadata endpoints (`169.254.169.254`, `metadata.google.internal`) are always blocked
- Opt out for trusted private networks with `--allow-private-urls` or `WSP_ALLOW_PRIVATE_URLS=1` (off by default; metadata endpoints stay blocked)

**SearXNG SSRF protection:**
- Enforces `http` / `https` only
- Blocks common cloud metadata endpoints
- Blocks private/internal IP resolution unless `SEARXNG_ALLOW_PRIVATE=1`
- Uses operator-controlled config/env only for the instance URL

**Local data:**
- Cache directory is created `0700`; cache and provider-health files are written `0600` via atomic temp-file replace
- API keys are never written to the cache or logs

**Declared permissions** (see `package.json → clawhub.permissions`):
- Outbound network access limited to the listed provider API hosts (plus any user-configured SearXNG instance)
- Environment reads limited to provider `*_API_KEY` vars, `SEARXNG_*`, and `WSP_*` settings
- Filesystem writes limited to the cache directory

---

## ✅ Verification

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/search.py --explain-routing -q "find credible sources for climate change impacts"
python3 scripts/extract.py --url https://example.com --provider auto --compact
```
