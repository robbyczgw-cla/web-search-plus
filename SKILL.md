---
name: web-search-plus
version: 3.0.1
description: Unified multi-provider web search and URL extraction skill with intelligent auto-routing across Serper, Brave, Tavily, Querit, Linkup, Exa, Firecrawl, Perplexity, You.com, and SearXNG.
tags: [search, web-search, web-extract, serper, brave, tavily, querit, linkup, exa, firecrawl, perplexity, you, searxng, google, multilingual-search, research, semantic-search, auto-routing, multi-provider, shopping, rag, free-tier, privacy, self-hosted, kilo]
metadata: {"openclaw":{"requires":{"bins":["python3","bash"],"env":{"SERPER_API_KEY":"optional","BRAVE_API_KEY":"optional","TAVILY_API_KEY":"optional","QUERIT_API_KEY":"optional","LINKUP_API_KEY":"optional","EXA_API_KEY":"optional","FIRECRAWL_API_KEY":"optional","PERPLEXITY_API_KEY":"optional — direct Perplexity provider credential","KILOCODE_API_KEY":"optional — alternative Perplexity provider via Kilo Gateway","YOU_API_KEY":"optional","SEARXNG_INSTANCE_URL":"optional"},"note":"Only ONE provider key or SEARXNG_INSTANCE_URL is needed for search. Extraction requires one of Firecrawl, Linkup, Tavily, Exa, or You.com."}}}
---

# Web Search Plus

**Stop choosing search providers. Let the skill do it for you.**

This skill now connects you to **10 search providers** and adds a companion extraction flow for pulling content from URLs. Broad web query? → Brave or Serper. Research question? → Tavily or Exa. Need citations and grounding? → Linkup. Want scrape-ready content? → Firecrawl. Prefer privacy? → SearXNG.

---

## ✨ What Makes This Different?

- **Just search** — no need to think about which provider to use
- **Smart routing** — query analysis picks the best provider automatically
- **10 providers, 1 interface** — general web, research, semantic discovery, direct answers, privacy-first, and extraction-capable providers together
- **URL extraction included** — pull markdown/HTML content with fallback across five providers
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

### Extraction providers

`scripts/extract.py` auto-falls back across:

1. **Firecrawl**
2. **Linkup**
3. **Tavily**
4. **Exa**
5. **You.com**

---

## 🧠 Routing at a Glance

Default priority:

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

## ⚙️ Configuration Notes

- `.env.example` documents supported env vars
- `config.example.json` includes provider priority and provider-specific defaults
- `config.json` is your local runtime config
- SearXNG still supports explicit URL config and docker-aware auto-detection

---

## 🔒 Security

**SearXNG SSRF protection:**
- Enforces `http` / `https` only
- Blocks common cloud metadata endpoints
- Blocks private/internal IP resolution unless `SEARXNG_ALLOW_PRIVATE=1`
- Uses operator-controlled config/env only for the instance URL

---

## ✅ Verification

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/search.py --explain-routing -q "find credible sources for climate change impacts"
python3 scripts/extract.py --url https://example.com --provider auto --compact
```
