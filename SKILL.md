---
name: web-search-plus
version: 2.5.2
description: Unified search skill with Intelligent Auto-Routing. Uses multi-signal analysis to automatically select between Serper (Google), Tavily (Research), Exa (Neural), You.com (RAG/Real-time), and SearXNG (Privacy/Self-hosted) with confidence scoring.
tags: [search, web-search, serper, tavily, exa, you, searxng, google, research, semantic-search, auto-routing, multi-provider, shopping, rag, free-tier, privacy, self-hosted]
metadata: {"clawdbot":{"requires":{"bins":["python3","bash"],"env":["SERPER_API_KEY","TAVILY_API_KEY","EXA_API_KEY","YOU_API_KEY","SEARXNG_INSTANCE_URL"]},"primaryEnv":"SERPER_API_KEY"}}
---

# Web Search Plus

Multi-provider web search with **Intelligent Auto-Routing**: Serper (Google), Tavily (Research), Exa (Neural), You.com (RAG/Real-time), SearXNG (Privacy/Self-hosted).

**NEW in v2.5.0**: 🔒 **SearXNG provider added!** Privacy-first meta-search, 70+ upstream engines, $0 API cost, self-hosted — perfect for privacy-conscious users and multi-source aggregation.

**NEW in v2.3.0**: Interactive setup wizard! Run `python3 scripts/setup.py` for guided configuration.

**NEW in v2.2.5**: Automatic error fallback — if one provider fails (rate limit, timeout, etc.), automatically tries the next provider in priority order!

---

## 🚀 First Run (Setup Wizard)

New to web-search-plus? The interactive setup wizard guides you through configuration:

```bash
python3 scripts/setup.py
```

The wizard will:
1. **Explain each provider** — What they're best for, free tier limits, signup links
2. **Ask which providers to enable** — You can use 1, 2, 3, 4, or all 5
3. **Collect API keys/URLs** — Stored locally in `config.json` (gitignored)
4. **Configure defaults** — Default provider, auto-routing, result count

### What Each Provider Is Best For

| Provider | Best For | Free Tier |
|----------|----------|-----------|
| **Serper** | Google results, shopping, prices, local businesses, news | 2,500/month |
| **Tavily** | Research questions, explanations, academic, full-page content | 1,000/month |
| **Exa** | Semantic search, "similar to X", startup discovery, papers | 1,000/month |
| **You.com** | RAG/AI context, real-time info, combined web+news, LLM-ready snippets | Limited free |
| **SearXNG** | Privacy-preserving search, multi-source aggregation, $0 API cost | FREE (self-hosted) |

### Reconfigure Anytime

```bash
python3 scripts/setup.py --reset
```

---

## 🔑 API Keys Setup (Manual)

**NEW in v2.2.0**: The script **auto-loads** API keys from `.env` in the skill directory!

### Quick Setup

**Option A: .env file** (recommended)
```bash
# /path/to/skills/web-search-plus/.env
export SERPER_API_KEY="your-key"   # https://serper.dev
export TAVILY_API_KEY="your-key"   # https://tavily.com  
export EXA_API_KEY="your-key"      # https://exa.ai
export YOU_API_KEY="your-key"      # https://api.you.com
export SEARXNG_INSTANCE_URL="https://your-instance.example.com"  # Self-hosted
```

**Option B: config.json** (NEW in v2.2.1)
```bash
# Copy the example config
cp config.example.json config.json
```
Then add your keys:
```json
{
  "serper": { "api_key": "your-serper-key" },
  "tavily": { "api_key": "your-tavily-key" },
  "exa": { "api_key": "your-exa-key" },
  "you": { "api_key": "your-you-key" },
  "searxng": { "instance_url": "https://your-instance.example.com" }
}
```
⚠️ `config.json` is gitignored — your keys stay safe!

Just run — keys load automatically:
```bash
python3 scripts/search.py -q "your query"
# No need for 'source .env' anymore! ✨
```

**Priority:** config.json > .env > environment variable

### Get Free API Keys

| Provider | Free Tier | Sign Up |
|----------|-----------|---------|
| Serper | 2,500 queries/mo | https://serper.dev |
| Tavily | 1,000 queries/mo | https://tavily.com |
| Exa | 1,000 queries/mo | https://exa.ai |
| You.com | Limited free tier | https://api.you.com |
| SearXNG | **Unlimited** (self-hosted) | https://docs.searxng.org/admin/installation.html |

---

## ⚠️ Don't Modify Core OpenClaw Config

**Tavily, Serper, and Exa are NOT core OpenClaw providers.**

❌ **DON'T** add to `~/.openclaw/openclaw.json`:
```json
"tools": { "web": { "search": { "provider": "tavily" }}}  // WRONG!
```

✅ **DO** use this skill's scripts — keys auto-load from `.env`

Core OpenClaw only supports `brave` as the built-in web search provider. This skill adds Serper, Tavily, and Exa as **additional** options via its own scripts.

---

## 🧠 Intelligent Auto-Routing

No need to choose a provider — just search! The skill uses **multi-signal analysis** to understand your query intent:

```bash
# These queries are intelligently routed with confidence scoring:
python3 scripts/search.py -q "how much does iPhone 16 cost"     # → Serper (68% MEDIUM)
python3 scripts/search.py -q "how does quantum entanglement work"  # → Tavily (86% HIGH)
python3 scripts/search.py -q "startups similar to Notion"       # → Exa (76% HIGH)
python3 scripts/search.py -q "MacBook Pro M3 specs review"      # → Serper (70% HIGH)
python3 scripts/search.py -q "explain pros and cons of React"   # → Tavily (85% HIGH)
python3 scripts/search.py -q "companies like stripe.com"        # → Exa (100% HIGH)
python3 scripts/search.py -q "what's the latest on AI regulation" # → You.com (72% HIGH)
python3 scripts/search.py -q "summarize current events in tech"   # → You.com (78% HIGH)
python3 scripts/search.py -q "search privately without tracking"  # → SearXNG (90% HIGH)
python3 scripts/search.py -q "results from multiple search engines" # → SearXNG (80% HIGH)
```

### How It Works

The routing engine analyzes multiple signals:

#### 🛒 Shopping Intent → Serper
| Signal Type | Examples | Weight |
|-------------|----------|--------|
| Price patterns | "how much", "price of", "cost of" | HIGH |
| Purchase intent | "buy", "purchase", "order", "where to buy" | HIGH |
| Deal signals | "deal", "discount", "cheap", "best price" | MEDIUM |
| Product + Brand | "iPhone 16", "Sony headphones" + specs/review | HIGH |
| Local business | "near me", "restaurants", "hotels" | HIGH |

#### 📚 Research Intent → Tavily
| Signal Type | Examples | Weight |
|-------------|----------|--------|
| Explanation | "how does", "why does", "explain", "what is" | HIGH |
| Analysis | "compare", "pros and cons", "difference between" | HIGH |
| Learning | "tutorial", "guide", "understand", "learn" | MEDIUM |
| Depth | "in-depth", "comprehensive", "detailed" | MEDIUM |
| Complex queries | Long, multi-clause questions | BONUS |

#### 🔍 Discovery Intent → Exa
| Signal Type | Examples | Weight |
|-------------|----------|--------|
| Similarity | "similar to", "alternatives to", "competitors" | VERY HIGH |
| Company discovery | "companies like", "startups doing", "who else" | HIGH |
| URL detection | Any URL or domain (stripe.com) | VERY HIGH |
| Academic | "arxiv", "research papers", "github projects" | HIGH |
| Funding | "Series A", "YC", "funded startup" | HIGH |

#### 🤖 RAG/Real-time Intent → You.com
| Signal Type | Examples | Weight |
|-------------|----------|--------|
| RAG context | "context for", "rag", "summarize", "tldr" | VERY HIGH |
| Information synthesis | "key points", "main takeaways", "quick overview" | HIGH |
| Real-time needs | "latest news", "current status", "right now" | HIGH |
| Combined sources | "what's happening", "updates on", "situation" | HIGH |
| Freshness | "as of today", "up to date", "real time" | HIGH |

#### 🔒 Privacy/Multi-Source Intent → SearXNG
| Signal Type | Examples | Weight |
|-------------|----------|--------|
| Privacy signals | "private", "anonymous", "without tracking", "no tracking" | VERY HIGH |
| Privacy-focused | "privacy-first", "duckduckgo alternative", "private search" | VERY HIGH |
| Multi-source | "aggregate results", "multiple sources", "diverse perspectives" | HIGH |
| Meta-search | "meta search", "all engines", "from multiple engines" | VERY HIGH |
| Budget/free | "free search", "no api cost", "self-hosted search", "zero cost" | HIGH |
| German | "privat", "anonym", "ohne tracking", "verschiedene quellen" | HIGH |

### Confidence Scoring

Every routing decision includes a confidence level:

| Confidence | Level | Meaning |
|------------|-------|---------|
| 70-100% | **HIGH** | Strong signal match, very reliable |
| 40-69% | **MEDIUM** | Good match, should work well |
| 0-39% | **LOW** | Ambiguous query, using fallback |

### Debug Routing Decisions

See the full analysis:

```bash
python3 scripts/search.py --explain-routing -q "how much does iPhone 16 Pro cost"
```

Output:
```json
{
  "query": "how much does iPhone 16 Pro cost",
  "routing_decision": {
    "provider": "serper",
    "confidence": 0.68,
    "confidence_level": "medium",
    "reason": "moderate_confidence_match"
  },
  "scores": {"serper": 7.0, "tavily": 0.0, "exa": 0.0},
  "top_signals": [
    {"matched": "how much", "weight": 4.0},
    {"matched": "brand + product detected", "weight": 3.0}
  ],
  "query_analysis": {
    "word_count": 7,
    "is_complex": false,
    "has_url": null,
    "recency_focused": false
  }
}
```

---

## 🔍 When to Use This Skill vs Built-in Brave Search

### Use **Built-in Brave Search** when:
- ✅ General web searches (news, info, questions)
- ✅ Privacy is important
- ✅ Quick lookups without specific requirements

### Use **web-search-plus** when:

#### → **Serper** (Google results):
- 🛍️ **Product specs, prices, shopping** - "Compare iPhone 16 vs Samsung S24"
- 📍 **Local businesses, places** - "Best pizza in Berlin"
- 🎯 **"Google it"** - Explicitly wants Google results
- 📰 **Shopping/images/news** - `--type shopping/images/news`
- 🏆 **Knowledge Graph** - Structured info (prices, ratings, etc.)

#### → **Tavily** (AI-optimized research):
- 📚 **Research questions** - "How does quantum computing work?"
- 🔬 **Deep dives** - Complex multi-part questions
- 📄 **Full page content** - Not just snippets (`--raw-content`)
- 🎓 **Academic research** - Synthesized answers
- 🔒 **Domain filtering** - `--include-domains` for trusted sources

#### → **Exa** (Neural semantic search):
- 🔗 **Similar pages** - "Sites like OpenAI.com" (`--similar-url`)
- 🏢 **Company discovery** - "AI companies like Anthropic"
- 📝 **Research papers** - `--category "research paper"`
- 💻 **GitHub projects** - `--category github`
- 📅 **Date-specific** - `--start-date` / `--end-date`

#### → **You.com** (RAG/Real-time):
- 🤖 **RAG applications** - Pre-extracted LLM-ready snippets
- 📰 **Combined web + news** - Single API call for both
- ⚡ **Real-time info** - Current events, status updates
- 📋 **Summarization context** - "What's the latest on..."
- 🔄 **Live crawling** - Full page content on demand (`--livecrawl`)

#### → **SearXNG** (Privacy-First/Self-Hosted):
- 🔒 **Privacy-preserving search** - No tracking, no profiling
- 🌐 **Multi-source aggregation** - 70+ upstream engines
- 💰 **$0 API cost** - Self-hosted, unlimited queries
- 🎯 **Diverse perspectives** - Results from multiple engines
- 🏠 **Self-hosted environments** - Full control over your search

---

## Provider Comparison

| Feature | Serper | Tavily | Exa | You.com | SearXNG |
|---------|:------:|:------:|:---:|:-------:|:-------:|
| Speed | ⚡⚡⚡ | ⚡⚡ | ⚡⚡ | ⚡⚡⚡ | ⚡⚡ |
| Factual Accuracy | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| Semantic Understanding | ⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐ |
| Research Quality | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐ |
| Full Page Content | ✗ | ✓ | ✓ | ✓ | ✗ |
| Shopping/Local | ✓ | ✗ | ✗ | ✗ | ✓ |
| Similar Pages | ✗ | ✗ | ✓ | ✗ | ✗ |
| Knowledge Graph | ✓ | ✗ | ✗ | ✗ | ✗ |
| News Integration | ✓ | ✗ | ✗ | ✓ | ✓ |
| RAG-Optimized | ✗ | ✓ | ✗ | ✓✓ | ✗ |
| Privacy-First | ✗ | ✗ | ✗ | ✗ | ✓✓ |
| Self-Hosted | ✗ | ✗ | ✗ | ✗ | ✓ |
| API Cost | $$ | $$ | $$ | $ | **FREE** |

---

## Usage Examples

### Auto-Routed (Recommended)

```bash
python3 scripts/search.py -q "iPhone 16 Pro Max price"          # → Serper
python3 scripts/search.py -q "how does HTTPS encryption work"   # → Tavily
python3 scripts/search.py -q "startups similar to Notion"       # → Exa
python3 scripts/search.py -q "latest updates on AI regulation"  # → You.com
python3 scripts/search.py -q "search privately without tracking" # → SearXNG
```

### Explicit Provider

```bash
python3 scripts/search.py -p serper -q "weather Berlin" --type weather
python3 scripts/search.py -p tavily -q "quantum computing" --depth advanced
python3 scripts/search.py -p exa --similar-url "https://stripe.com" --category company
python3 scripts/search.py -p you -q "current tech news" --include-news
python3 scripts/search.py -p you -q "climate change" --livecrawl all --freshness week
python3 scripts/search.py -p searxng -q "linux distros" --engines "google,bing,duckduckgo"
```

---

## Configuration

### config.json

```json
{
  "auto_routing": {
    "enabled": true,
    "fallback_provider": "serper",
    "confidence_threshold": 0.3,
    "disabled_providers": []
  },
  "serper": {"country": "us", "language": "en"},
  "tavily": {"depth": "advanced"},
  "exa": {"type": "neural"},
  "you": {"country": "US", "safesearch": "moderate", "include_news": true},
  "searxng": {"instance_url": "https://your-instance.example.com", "safesearch": 0}
}
```

---

## Output Format

```json
{
  "provider": "serper",
  "query": "iPhone 16 price",
  "results": [{"title": "...", "url": "...", "snippet": "...", "score": 0.95}],
  "answer": "Synthesized answer...",
  "routing": {
    "auto_routed": true,
    "provider": "serper",
    "confidence": 0.78,
    "confidence_level": "high",
    "reason": "high_confidence_match",
    "top_signals": [{"matched": "price", "weight": 3.0}]
  }
}
```

---

## FAQ

### General

**Q: How does auto-routing decide which provider to use?**
> Multi-signal analysis scores each provider based on: price patterns, explanation phrases, similarity keywords, URLs, product+brand combos, and query complexity. Highest score wins. Use `--explain-routing` to see the decision breakdown.

**Q: What if it picks the wrong provider?**
> Override with `-p serper/tavily/exa`. Check `--explain-routing` to understand why it chose differently.

**Q: What does "low confidence" mean?**
> Query is ambiguous (e.g., "Tesla" could be cars, stock, or company). Falls back to Serper. Results may vary.

**Q: Can I disable a provider?**
> Yes! In config.json: `"disabled_providers": ["exa"]`

### API Keys

**Q: Which API keys do I need?**
> At minimum ONE key (or SearXNG instance). You can use just Serper, just Tavily, just Exa, just You.com, or just SearXNG. Missing keys = that provider is skipped.

**Q: Where do I get API keys?**
> - Serper: https://serper.dev (2,500 free queries, no credit card)
> - Tavily: https://tavily.com (1,000 free searches/month)
> - Exa: https://exa.ai (1,000 free searches/month)
> - You.com: https://api.you.com (Limited free tier for testing)
> - SearXNG: Self-hosted, no key needed! https://docs.searxng.org/admin/installation.html

**Q: How do I set API keys?**
> Two options (both auto-load):
> 
> **Option A: .env file**
> ```bash
> export SERPER_API_KEY="your-key"
> ```
> 
> **Option B: config.json** (v2.2.1+)
> ```json
> { "serper": { "api_key": "your-key" } }
> ```

### Routing Details

**Q: How do I know which provider handled my search?**
> Check `routing.provider` in JSON output, or `[🔍 Searched with: Provider]` in chat responses.

**Q: Why does it sometimes choose Serper for research questions?**
> If the query has brand/product signals (e.g., "how does Tesla FSD work"), shopping intent may outweigh research intent. Override with `-p tavily`.

**Q: What's the confidence threshold?**
> Default: 0.3 (30%). Below this = low confidence, uses fallback. Adjustable in config.json.

### You.com Specific

**Q: When should I use You.com over other providers?**
> You.com excels at:
> - **RAG applications**: Pre-extracted snippets ready for LLM consumption
> - **Real-time information**: Current events, breaking news, status updates
> - **Combined sources**: Web + news results in a single API call
> - **Summarization tasks**: "What's the latest on...", "Key points about..."

**Q: What's the livecrawl feature?**
> You.com can fetch full page content on-demand. Use `--livecrawl web` for web results, `--livecrawl news` for news articles, or `--livecrawl all` for both. Content is returned in Markdown format.

**Q: Does You.com include news automatically?**
> Yes! You.com's intelligent classification automatically includes relevant news results when your query has news intent. You can also use `--include-news` to explicitly enable it.

### SearXNG Specific

**Q: Do I need my own SearXNG instance?**
> Yes! SearXNG is self-hosted. Most public instances disable the JSON API to prevent bot abuse. You need to run your own instance with JSON format enabled. See: https://docs.searxng.org/admin/installation.html

**Q: How do I set up SearXNG?**
> Docker is the easiest way:
> ```bash
> docker run -d -p 8080:8080 searxng/searxng
> ```
> Then enable JSON in `settings.yml`:
> ```yaml
> search:
>   formats:
>     - html
>     - json
> ```

**Q: Why am I getting "403 Forbidden"?**
> The JSON API is disabled on your instance. Enable it in `settings.yml` under `search.formats`.

**Q: What's the API cost for SearXNG?**
> **$0!** SearXNG is free and open-source. You only pay for hosting (~$5/month VPS). Unlimited queries.

**Q: When should I use SearXNG?**
> - **Privacy-sensitive queries**: No tracking, no profiling
> - **Budget-conscious**: $0 API cost
> - **Diverse results**: Aggregates 70+ search engines
> - **Self-hosted requirements**: Full control over your search infrastructure
> - **Fallback provider**: When paid APIs are rate-limited

**Q: Can I limit which search engines SearXNG uses?**
> Yes! Use `--engines google,bing,duckduckgo` to specify engines, or configure defaults in `config.json`.

### Troubleshooting

**Q: "No API key found" error?**
> 1. Check `.env` exists in skill folder with `export VAR=value` format
> 2. Keys auto-load from skill's `.env` since v2.2.0
> 3. Or set in system environment: `export SERPER_API_KEY="..."`

**Q: Getting empty results?**
> 1. Check API key is valid
> 2. Try a different provider with `-p`
> 3. Some queries have no results (very niche topics)

**Q: Rate limited?**
> **NEW in v2.2.5**: Automatic fallback! If one provider hits rate limits, the script automatically tries the next provider in priority order (serper → tavily → exa). You'll see fallback info in stderr and the response will include `routing.fallback_used: true`.
> 
> Provider limits: Serper 2,500 free total, Tavily 1,000/month free, Exa 1,000/month free.

### For OpenClaw Users

**Q: How do I use this in chat?**
> Just ask! OpenClaw auto-detects search intent. Or explicitly: "search with web-search-plus for..."

**Q: Does it replace built-in Brave Search?**
> No, it's complementary. Use Brave for quick lookups, web-search-plus for research/shopping/discovery.

**Q: Can I see which provider was used?**
> Yes! SOUL.md can include attribution: `[🔍 Searched with: Serper/Tavily/Exa]`

---

## ❓ Frequently Asked Questions

### Which provider should I use?

It depends on your query intent:

| Query Type | Best Provider | Why |
|------------|---------------|-----|
| **Shopping** ("buy laptop", "cheap shoes") | **Serper** | Google Shopping, price comparisons, local stores |
| **Research** ("how does X work?", "explain Y") | **Tavily** | Deep research, academic quality, full-page content |
| **Startups/Papers** ("companies like X", "arxiv papers") | **Exa** | Semantic/neural search, startup discovery |
| **RAG/Real-time** ("summarize latest", "current events") | **You.com** | LLM-ready snippets, combined web+news |
| **Privacy** ("search without tracking") | **SearXNG** | No tracking, multi-source, self-hosted |

**Tip:** Enable auto-routing and let the skill choose automatically! 🎯

### Do I need all 5 providers?

**No!** All providers are optional. You can use:
- **1 provider** (e.g., just Serper for everything)
- **2-3 providers** (e.g., Serper + You.com for most needs)
- **All 5** (maximum flexibility + fallback options)

Set `disabled_providers` in `config.json` to control which ones are active.

### How much do the APIs cost?

| Provider | Free Tier | Paid Plan |
|----------|-----------|-----------|
| **Serper** | 2,500 queries/mo | $50/mo (5,000 queries) |
| **Tavily** | 1,000 queries/mo | $150/mo (10,000 queries) |
| **Exa** | 1,000 queries/mo | $1,000/mo (100,000 queries) |
| **You.com** | Limited free | ~$10/mo (varies by usage) |
| **SearXNG** | **FREE** ✅ | Only VPS cost (~$5/mo if self-hosting) |

**Budget tip:** Use SearXNG as primary + others as fallback for specialized queries!

### How do I set up SearXNG?

SearXNG requires a self-hosted instance. Quick setup:

**Option 1: Docker (5 minutes)**
```bash
docker run -d -p 8080:8080 searxng/searxng
```

**Option 2: Full installation**
See: https://docs.searxng.org/admin/installation.html

**Enable JSON format:**
Edit `settings.yml`:
```yaml
search:
  formats: [html, json]  # Add 'json'!
```

**Then in web-search-plus:**
```bash
export SEARXNG_INSTANCE_URL="http://localhost:8080"
python3 scripts/setup.py  # Or edit config.json directly
```

### Can I use public SearXNG instances?

**Not recommended.** Most public instances (searx.space) disable JSON API to prevent abuse. You'll get `403 Forbidden` errors.

**Solution:** Self-host on a VPS (~$5/mo) or use Docker locally.

### Is SearXNG slower than paid APIs?

**Yes, typically.** SearXNG queries multiple engines in parallel:
- **SearXNG:** 1-3 seconds (aggregates 70+ engines)
- **Paid APIs:** 0.5-1 second (direct access)

**Trade-off:** Slower but privacy-preserving + multi-source + $0 cost.

### What if my SearXNG instance is down?

Auto-routing automatically falls back to the next provider in `provider_priority`. If Searx NG is first:
```json
"provider_priority": ["searxng", "serper", "tavily", "exa", "you"]
```
→ Failed SearXNG request → tries Serper → tries Tavily → etc.

**Tip:** Put SearXNG **last** in priority for best reliability (use paid APIs first, SearXNG as fallback).

### Can I limit which engines SearXNG uses?

**Yes!** Set `engines` in `config.json`:
```json
{
  "searxng": {
    "engines": ["google", "duckduckgo", "qwant", "wikipedia"]
  }
}
```

Or via CLI:
```bash
python3 scripts/search.py -p searxng -q "linux" --engines "google,bing"
```

### How private is SearXNG really?

**Depends on your instance!**

| Setup | Privacy Level |
|-------|---------------|
| **Self-hosted (your VPS)** | ⭐⭐⭐⭐⭐ You control everything |
| **Self-hosted (Docker local)** | ⭐⭐⭐⭐⭐ Fully private |
| **Public instance** | ⭐⭐⭐ Depends on operator's logging policy |

**Best practice:** Self-host if privacy is critical. Check your instance's logs/settings.

### Which provider has the best results?

**There's no "best" — it depends!**

| Metric | Winner |
|--------|--------|
| **Most accurate for facts** | Serper (Google) |
| **Best for research depth** | Tavily |
| **Best for semantic queries** | Exa |
| **Best for RAG/AI context** | You.com |
| **Most diverse sources** | SearXNG (70+ engines) |
| **Most private** | SearXNG (self-hosted) |

**Recommendation:** Enable multiple providers + auto-routing for best overall experience.

### How does auto-routing work?

The skill analyzes your query for keywords and patterns:

```python
"buy cheap laptop"     → Serper (shopping signals)
"how does AI work?"    → Tavily (research/explanation)
"companies like X"     → Exa (semantic/similar)
"summarize latest news" → You.com (RAG/real-time)
"search privately"     → SearXNG (privacy signals)
```

**Confidence threshold:** Only routes if confidence > 30%. Otherwise uses default provider.

**Override:** Use `-p provider` to force a specific provider.

### Can I use this in production?

**Yes!** Web-search-plus is production-ready:
- ✅ Error handling with automatic fallback
- ✅ Rate limit protection
- ✅ Timeout handling (30s per provider)
- ✅ API key security (.env + config.json gitignored)
- ✅ 5 providers for redundancy

**Tip:** Monitor API usage to avoid exceeding free tiers!

### What if I run out of API credits?

1. **Fallback chain:** Other enabled providers automatically take over
2. **Use SearXNG:** Switch to self-hosted (unlimited queries)
3. **Upgrade plan:** Paid tiers have higher limits
4. **Rate limit:** Use `disabled_providers` to skip exhausted APIs temporarily

### How do I update to v2.5.0?

**Via ClawHub (recommended):**
```bash
clawhub update web-search-plus --registry "https://www.clawhub.ai" --no-input
```

**Manually:**
```bash
cd /root/clawd/skills/web-search-plus
git pull origin main
python3 scripts/setup.py  # Re-run to add SearXNG
```

### Where can I report bugs or request features?

- **GitHub Issues:** https://github.com/robbyczgw-cla/web-search-plus/issues
- **ClawHub:** https://www.clawhub.ai/skills/web-search-plus

---

**Still have questions?** Check the full documentation in `README.md` or run:
```bash
python3 scripts/search.py --help
python3 scripts/setup.py  # Interactive wizard
```
