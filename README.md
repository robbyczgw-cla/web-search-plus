# Web Search Plus

Unified multi-provider web search and URL extraction for OpenClaw-style agent workflows.

Current version: **3.0.0**

## What changed in 3.0.0

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
```

## Extraction examples

```bash
python3 scripts/extract.py --url https://example.com
python3 scripts/extract.py --url https://docs.linkup.so --provider linkup
python3 scripts/extract.py --url https://example.com --url https://example.org --include-images
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
