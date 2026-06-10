# Frequently Asked Questions

## General

### What is Web Search Plus 3.0.0?

A Python OpenClaw skill for unified web search plus URL extraction.

It supports 10 search providers:

- Serper
- Brave
- Tavily
- Querit
- Linkup
- Exa
- Firecrawl
- Perplexity via direct API or Kilo gateway
- You.com
- SearXNG

It also adds URL extraction through `scripts/extract.py` with fallback across:

- Firecrawl
- Linkup
- Tavily
- Exa
- You.com

### Is this the same as the OpenClaw plugin?

No.

- The **plugin** registers native OpenClaw tools like `web_search_plus` and `web_extract_plus`.
- The **skill** provides scripts and instructions for agent workflows: `scripts/search.py` and `scripts/extract.py`.

The 3.0.0 skill release brings the old skill much closer to plugin/Hermes provider parity, but the plugin is still the cleaner native OpenClaw route for tool registration.

### Which should I use?

Use the plugin for new OpenClaw setups.

Use this skill when you want:

- portable scripts
- manual CLI control
- an inspectable Python implementation
- skill-style instructions for agents
- compatibility with older workflows that already call `scripts/search.py`

## Setup

### Which API keys do I need?

Only one search provider is required to start.

Any one of these is enough for search:

- `SERPER_API_KEY`
- `BRAVE_API_KEY`
- `TAVILY_API_KEY`
- `QUERIT_API_KEY`
- `LINKUP_API_KEY`
- `EXA_API_KEY`
- `FIRECRAWL_API_KEY`
- `PERPLEXITY_API_KEY`
- `KILOCODE_API_KEY`
- `YOU_API_KEY`
- `SEARXNG_INSTANCE_URL`

Extraction needs one of:

- `FIRECRAWL_API_KEY`
- `LINKUP_API_KEY`
- `TAVILY_API_KEY`
- `EXA_API_KEY`
- `YOU_API_KEY`

### Where do I get keys?

- Serper: <https://serper.dev>
- Brave: <https://brave.com/search/api/>
- Tavily: <https://tavily.com>
- Querit: <https://querit.ai>
- Linkup: <https://linkup.so>
- Exa: <https://exa.ai>
- Firecrawl: <https://firecrawl.dev>
- Perplexity: <https://www.perplexity.ai/settings/api>
- Kilo gateway: <https://kilo.ai>
- You.com: <https://api.you.com>
- SearXNG: <https://docs.searxng.org/admin/installation.html>

### How do I configure keys?

Use `.env`:

```bash
cp .env.example .env
# edit .env
```

Or use `config.json` for provider-specific settings.

Priority order for credentials is generally:

- `config.json`
- `.env`
- process environment

## Routing

### How does auto-routing decide?

The skill scores query signals and chooses among configured providers only.

Typical routing:

- shopping, product, local, broad Google-style web → Serper or Brave
- generic current web → Brave or Serper
- research/explanation → Tavily
- source/citation/evidence queries → Linkup
- multilingual/international updates → Querit or Tavily
- semantic discovery, similar sites, papers → Exa
- scrape-ready discovery → Firecrawl
- direct answer / cited summary → Perplexity via direct API or Kilo gateway
- RAG/current-web snippets → You.com
- private/self-hosted search → SearXNG

### How do I see the routing decision?

```bash
python3 scripts/search.py --explain-routing -q "your query"
```

### What if it picks the wrong provider?

Force a provider:

```bash
python3 scripts/search.py -p linkup -q "credible sources for AI tutoring outcomes"
python3 scripts/search.py -p firecrawl -q "YC startups web scraping"
```

Or adjust `auto_routing.provider_priority` / `disabled_providers` in `config.json`.

### What does low confidence mean?

The query did not strongly match one provider. The skill may fall back to the configured fallback provider, usually Serper.

## Extraction

### How do I extract URL content?

```bash
python3 scripts/extract.py --url https://example.com
```

Multiple URLs:

```bash
python3 scripts/extract.py --url https://example.com --url https://example.org
```

Force a provider:

```bash
python3 scripts/extract.py --provider firecrawl --url https://example.com
```

### Which extraction provider is tried first?

Auto extraction tries:

- Firecrawl
- Linkup
- Tavily
- Exa
- You.com

Missing credentials are skipped. Failed providers fall through to the next configured provider.

### Can extraction return HTML?

Yes, when the provider supports it:

```bash
python3 scripts/extract.py --url https://example.com --format html --include-raw-html
```

## Data handling & privacy

### Where do my queries and URLs go?

**Every search query is transmitted to the third-party provider that serves it** — Serper, Brave, Tavily, Linkup, Querit, Exa, Firecrawl, SerpBase, Perplexity (via the Kilo gateway), You.com, or your SearXNG instance. **Every extraction URL is forwarded to the chosen extraction provider** (Firecrawl, Linkup, Tavily, Exa, You.com), whose servers fetch the page. Each provider's own privacy policy and data retention apply.

### How do I keep sensitive queries under control?

- Use explicit provider selection (`--provider <name>`) instead of auto-routing so you decide which third party receives the query.
- Use a self-hosted SearXNG instance to keep queries on infrastructure you control.
- Don't submit internal/private URLs for extraction — they are sent to external services. The skill blocks private/loopback/link-local targets and cloud metadata endpoints by default anyway.

### What is stored locally?

Queries, results, and provider failure history are persisted under the cache directory: result cache entries (which include the raw query text) and `provider_health.json` (provider error messages and cooldown state). The directory is created with mode `0700` and files with `0600`. Disable with `WSP_DISABLE_CACHE=1`, bypass per call with `--no-cache`, wipe with `--clear-cache`.

### Are API keys ever logged or cached?

No. Keys are read from `config.json`/`.env`/environment, used for requests, and never written to the cache, the health file, or logs. Provider error messages are sanitized.

## Caching

### How does caching work?

Search results are cached locally by query, provider, result count, and relevant params. **Note: cache entries include the raw query text and results on disk** — see "Data handling & privacy" above.

Default TTL: 3600 seconds.

### Where are cached results stored?

In `.cache/` inside the skill folder by default (created mode `0700`; files `0600`). Provider failure history is stored alongside in `.cache/provider_health.json`.

Override with:

```bash
export WSP_CACHE_DIR="/path/to/custom/cache"
```

### How do I inspect or clear cache?

```bash
python3 scripts/search.py --cache-stats
python3 scripts/search.py --clear-cache
```

### How do I skip or disable cache?

```bash
python3 scripts/search.py -q "query" --no-cache   # one call
export WSP_DISABLE_CACHE=1                        # disable globally
```

## Research mode & quality reports

### What does `--mode research` do?

It queries up to three configured providers **concurrently**, deduplicates results with deterministic ordering (submission order, regardless of which provider finishes first), then extracts the top URLs for grounding. `--research-time-budget` (default 55s) gates which providers launch and whether extraction runs; skipped steps are reported as diagnostics instead of failing.

```bash
python3 scripts/search.py --mode research -q "your question" --research-providers tavily linkup exa
```

### What is `--quality-report`?

It attaches transparent diagnostics to the output: providers considered, domain diversity, duplicate/thin-snippet counts, extract recommendations, and **authority signals** for canonical-source query classes (`canonical_domain_hits`, `demoted_domain_hits`, `canonical_top_result`).

### What is intent reranking?

For query classes where source authority beats snippet luck (official vendor releases, official docs, policy PDFs, finance/IR, security advisories), results are reranked so primary sources rank above mirror/aggregator domains. `metadata.intent_rerank` shows when ordering changed.

## SearXNG

### Do I need my own SearXNG instance?

Usually yes. Most public SearXNG instances disable JSON API.

### Is SearXNG free?

Yes, the software is free and self-hosted. You only pay for hosting if you run it on a VPS.

### Is private-network access allowed?

Blocked by default for safety. Only set `SEARXNG_ALLOW_PRIVATE=1` when you intentionally use a trusted private SearXNG instance.

## Production use

### Is this production-ready?

Yes, with normal API caveats:

- automatic fallback
- rate-limit handling with jittered retry backoff
- provider cooldowns (locked, atomic health-file writes)
- local cache (owner-only permissions, disable-able)
- SSRF protections for SearXNG and all user-supplied URLs (extraction, `--similar-url`)
- configurable provider priority

For native OpenClaw tool usage, prefer the plugin. For script-based skill workflows, this skill is ready once tests pass.

### What if a provider is rate-limited?

The skill tries fallback providers when available. You can also temporarily disable exhausted providers in `config.json`.

## Updating

### How do I update?

Via ClawHub:

```bash
clawhub update web-search-plus --registry "https://www.clawhub.ai" --no-input
```

Manual git workflow:

```bash
cd /path/to/skills/web-search-plus
git pull origin main
python3 scripts/setup.py
```
