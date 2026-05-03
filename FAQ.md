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

## Caching

### How does caching work?

Search results are cached locally by query, provider, result count, and relevant params.

Default TTL: 3600 seconds.

### Where are cached results stored?

In `.cache/` inside the skill folder by default.

Override with:

```bash
export WSP_CACHE_DIR="/path/to/custom/cache"
```

### How do I inspect or clear cache?

```bash
python3 scripts/search.py --cache-stats
python3 scripts/search.py --clear-cache
```

### How do I skip cache?

```bash
python3 scripts/search.py -q "query" --no-cache
```

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
- rate-limit handling
- provider cooldowns
- local cache
- SSRF protections for SearXNG
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
