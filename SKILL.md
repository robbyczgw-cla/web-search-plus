---
name: web-search-plus
version: 2.6.1
description: Unified search skill with Intelligent Auto-Routing. Uses multi-signal analysis to automatically select between Serper (Google), Tavily (Research), Exa (Neural), You.com (RAG/Real-time), and SearXNG (Privacy/Self-hosted) with confidence scoring.
tags: [search, web-search, serper, tavily, exa, you, searxng, google, research, semantic-search, auto-routing, multi-provider, shopping, rag, free-tier, privacy, self-hosted]
metadata: {"clawdbot":{"requires":{"bins":["python3","bash"],"env":["SERPER_API_KEY","TAVILY_API_KEY","EXA_API_KEY","YOU_API_KEY","SEARXNG_INSTANCE_URL"]},"primaryEnv":"SERPER_API_KEY"}}
---

# Web Search Plus

Multi-provider web search with **Intelligent Auto-Routing**: Serper (Google), Tavily (Research), Exa (Neural), You.com (RAG/Real-time), SearXNG (Privacy/Self-hosted).

---

## 🚀 Quick Start

```bash
# Interactive setup (recommended for first run)
python3 scripts/setup.py

# Or manual: copy config and add your keys
cp config.example.json config.json
```

The wizard explains each provider, collects API keys, and configures defaults.

---

## 🔑 API Keys

**Option A: .env file** (recommended)
```bash
# /path/to/skills/web-search-plus/.env
export SERPER_API_KEY="your-key"   # https://serper.dev
export TAVILY_API_KEY="your-key"   # https://tavily.com  
export EXA_API_KEY="your-key"      # https://exa.ai
export YOU_API_KEY="your-key"      # https://api.you.com
export SEARXNG_INSTANCE_URL="https://your-instance.example.com"
```

**Option B: config.json**
```json
{
  "serper": { "api_key": "your-serper-key" },
  "tavily": { "api_key": "your-tavily-key" },
  "exa": { "api_key": "your-exa-key" },
  "you": { "api_key": "your-you-key" },
  "searxng": { "instance_url": "https://your-instance.example.com" }
}
```

**Priority:** config.json > .env > environment variable

| Provider | Free Tier | Sign Up |
|----------|-----------|---------|
| Serper | 2,500/mo | https://serper.dev |
| Tavily | 1,000/mo | https://tavily.com |
| Exa | 1,000/mo | https://exa.ai |
| You.com | Limited | https://api.you.com |
| SearXNG | **Unlimited** | Self-hosted |

---

## 🧠 Intelligent Auto-Routing

Just search — the skill picks the best provider:

```bash
python3 scripts/search.py -q "iPhone 16 Pro Max price"          # → Serper
python3 scripts/search.py -q "how does HTTPS encryption work"   # → Tavily
python3 scripts/search.py -q "startups similar to Notion"       # → Exa
python3 scripts/search.py -q "latest updates on AI regulation"  # → You.com
python3 scripts/search.py -q "search privately without tracking" # → SearXNG
```

### Provider Strengths

| Provider | Best For |
|----------|----------|
| **Serper** | Google results, shopping, prices, local businesses, news |
| **Tavily** | Research questions, explanations, academic, full-page content |
| **Exa** | Semantic search, "similar to X", startup discovery, papers |
| **You.com** | RAG/AI context, real-time info, combined web+news |
| **SearXNG** | Privacy-preserving, multi-source aggregation, $0 cost |

### Debug Routing

```bash
python3 scripts/search.py --explain-routing -q "your query"
```

---

## 📖 Usage Examples

### Auto-Routed (Recommended)

```bash
python3 scripts/search.py -q "iPhone 16 Pro Max price"
python3 scripts/search.py -q "how does quantum computing work"
python3 scripts/search.py -q "companies like stripe.com"
```

### Explicit Provider

```bash
python3 scripts/search.py -p serper -q "weather Berlin" --type weather
python3 scripts/search.py -p tavily -q "quantum computing" --depth advanced
python3 scripts/search.py -p exa --similar-url "https://stripe.com" --category company
python3 scripts/search.py -p you -q "current tech news" --include-news
python3 scripts/search.py -p searxng -q "linux distros" --engines "google,bing"
```

---

## ⚙️ Configuration

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

## 📊 Provider Comparison

| Feature | Serper | Tavily | Exa | You.com | SearXNG |
|---------|:------:|:------:|:---:|:-------:|:-------:|
| Speed | ⚡⚡⚡ | ⚡⚡ | ⚡⚡ | ⚡⚡⚡ | ⚡⚡ |
| Factual Accuracy | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| Semantic Understanding | ⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐ |
| Full Page Content | ✗ | ✓ | ✓ | ✓ | ✗ |
| Shopping/Local | ✓ | ✗ | ✗ | ✗ | ✓ |
| Similar Pages | ✗ | ✗ | ✓ | ✗ | ✗ |
| RAG-Optimized | ✗ | ✓ | ✗ | ✓✓ | ✗ |
| Privacy-First | ✗ | ✗ | ✗ | ✗ | ✓✓ |
| API Cost | $$ | $$ | $$ | $ | **FREE** |

---

## 📤 Output Format

```json
{
  "provider": "serper",
  "query": "iPhone 16 price",
  "results": [{"title": "...", "url": "...", "snippet": "...", "score": 0.95}],
  "routing": {
    "auto_routed": true,
    "provider": "serper",
    "confidence": 0.78,
    "confidence_level": "high"
  }
}
```

---

## ⚠️ Important Notes

**Tavily, Serper, and Exa are NOT core OpenClaw providers.**

❌ Don't modify `~/.openclaw/openclaw.json` for these providers  
✅ Use this skill's scripts — keys auto-load from `.env`

---

## 📚 Additional Documentation

- **[FAQ.md](FAQ.md)** — Frequently asked questions about providers, routing, costs
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** — Solutions for common errors and issues
- **[README.md](README.md)** — Full technical documentation

---

## 🔄 Automatic Fallback (v2.2.5+)

If one provider fails (rate limit, timeout, etc.), automatically tries the next provider in priority order. Response includes `routing.fallback_used: true` when fallback was used.
