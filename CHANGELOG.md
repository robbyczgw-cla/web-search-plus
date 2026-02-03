# Changelog - Web Search Plus

## [2.4.3] - 2026-02-03

### 📝 Documentation: Updated README

- **Added:** "NEW in v2.4.2" badge for You.com in SKILL.md
- **Impact:** ClawHub README now properly highlights You.com as new feature

## [2.4.2] - 2026-02-03

### 🐛 Critical Fix: You.com API Configuration

- **Fixed:** Incorrect hostname (`api.ydc-index.io` → `ydc-index.io`)
- **Fixed:** Incorrect header name (`X-API-Key` → `X-API-KEY` uppercase)
- **Impact:** You.com now works correctly - was giving 403 Forbidden before
- **Status:** ✅ Fully tested and working

## [2.4.1] - 2026-02-03

### 🐛 Bugfix: You.com URL Encoding

- **Fixed:** URL encoding for You.com queries - spaces and special characters now properly encoded
- **Impact:** Queries with spaces (e.g., "OpenClaw AI framework") work correctly now
- **Technical:** Added `urllib.parse.quote` for parameter encoding

## [2.4.0] - 2026-02-03

### 🆕 New Provider: You.com

Added You.com as the 4th search provider, optimized for RAG applications and real-time information:

#### Features
- **LLM-Ready Snippets**: Pre-extracted, query-aware text excerpts perfect for feeding into AI models
- **Unified Web + News**: Get both web pages and news articles in a single API call
- **Live Crawling**: Fetch full page content on-demand in Markdown format (`--livecrawl`)
- **Automatic News Classification**: Intelligently includes news results based on query intent
- **Freshness Controls**: Filter by recency (day, week, month, year, or date range)
- **SafeSearch Support**: Content filtering (off, moderate, strict)

#### Auto-Routing Signals
New RAG/Real-time intent detection routes to You.com for:
- RAG context queries: "summarize", "key points", "tldr", "context for"
- Real-time info: "latest news", "current status", "right now", "what's happening"
- Information synthesis: "updates on", "situation", "main takeaways"

#### Usage Examples
```bash
# Auto-routed
python3 scripts/search.py -q "summarize key points about AI regulation"  # → You.com

# Explicit
python3 scripts/search.py -p you -q "climate change" --livecrawl all
python3 scripts/search.py -p you -q "tech news" --freshness week
```

#### Configuration
```json
{
  "you": {
    "country": "US",
    "language": "en",
    "safesearch": "moderate",
    "include_news": true
  }
}
```

#### API Key Setup
```bash
export YOU_API_KEY="your-key"  # Get from https://api.you.com
```

### 📊 Updated Provider Comparison

| Feature | Serper | Tavily | Exa | You.com |
|---------|:------:|:------:|:---:|:-------:|
| Speed | ⚡⚡⚡ | ⚡⚡ | ⚡⚡ | ⚡⚡⚡ |
| News Integration | ✓ | ✗ | ✗ | ✓ |
| RAG-Optimized | ✗ | ✓ | ✗ | ✓✓ |
| Full Page Content | ✗ | ✓ | ✓ | ✓ |

---

## [2.1.5] - 2026-01-27

### 📝 Documentation

- Added warning about NOT using Tavily/Serper/Exa in core OpenClaw config
- Core OpenClaw only supports `brave` as the built-in provider
- This skill's providers must be used via environment variables and scripts, not `openclaw.json`

## [2.1.0] - 2026-01-23

### 🧠 Intelligent Multi-Signal Routing

Completely overhauled auto-routing with sophisticated query analysis:

#### Intent Classification
- **Shopping Intent**: Detects price patterns ("how much", "cost of"), purchase signals ("buy", "order"), deal keywords, and product+brand combinations
- **Research Intent**: Identifies explanation patterns ("how does", "why does"), analysis signals ("pros and cons", "compare"), learning keywords, and complex multi-clause queries
- **Discovery Intent**: Recognizes similarity patterns ("similar to", "alternatives"), company discovery signals, URL/domain detection, and academic patterns

#### Linguistic Pattern Detection
- "How much" / "price of" → Shopping (Serper)
- "How does" / "Why does" / "Explain" → Research (Tavily)
- "Companies like" / "Similar to" / "Alternatives" → Discovery (Exa)
- Product + Brand name combos → Shopping (Serper)
- URLs and domains in query → Similar search (Exa)

#### Query Analysis Features
- **Complexity scoring**: Long, multi-clause queries get routed to research providers
- **URL detection**: Automatic detection of URLs/domains triggers Exa similar search
- **Brand recognition**: Tech brands (Apple, Samsung, Sony, etc.) with product terms → shopping
- **Recency signals**: "latest", "2026", "breaking" boost news mode

#### Confidence Scoring
- **HIGH (70-100%)**: Strong signal match, very reliable routing
- **MEDIUM (40-69%)**: Good match, should work well
- **LOW (0-39%)**: Ambiguous query, using fallback provider
- Confidence based on absolute signal strength + relative margin over alternatives

#### Enhanced Debug Mode
```bash
python3 scripts/search.py --explain-routing -q "your query"
```

Now shows:
- Routing decision with confidence level
- All provider scores
- Top matched signals with weights
- Query analysis (complexity, URL detection, recency focus)
- All matched patterns per provider

### 🔧 Technical Changes

#### QueryAnalyzer Class
New `QueryAnalyzer` class with:
- `SHOPPING_SIGNALS`: 25+ weighted patterns for shopping intent
- `RESEARCH_SIGNALS`: 30+ weighted patterns for research intent
- `DISCOVERY_SIGNALS`: 20+ weighted patterns for discovery intent
- `LOCAL_NEWS_SIGNALS`: 25+ patterns for local/news queries
- `BRAND_PATTERNS`: Tech brand detection regex

#### Signal Weighting
- Multi-word phrases get higher weights (e.g., "how much" = 4.0 vs "price" = 3.0)
- Strong signals: price patterns (4.0), similarity patterns (5.0), URLs (5.0)
- Medium signals: product terms (2.5), learning keywords (2.5)
- Bonus scoring: Product+brand combo (+3.0), complex query (+2.5)

#### Improved Output Format
```json
{
  "routing": {
    "auto_routed": true,
    "provider": "serper",
    "confidence": 0.78,
    "confidence_level": "high",
    "reason": "high_confidence_match",
    "top_signals": [{"matched": "price", "weight": 3.0}],
    "scores": {"serper": 7.0, "tavily": 0.0, "exa": 0.0}
  }
}
```

### 📚 Documentation Updates

- **SKILL.md**: Complete rewrite with signal tables and confidence scoring guide
- **README.md**: Updated with intelligent routing examples and confidence levels
- **FAQ**: Updated to explain multi-signal analysis

### 🧪 Test Results

| Query | Provider | Confidence | Signals |
|-------|----------|------------|---------|
| "how much does iPhone 16 cost" | Serper | 68% | "how much", brand+product |
| "how does quantum entanglement work" | Tavily | 86% HIGH | "how does", "what are", "implications" |
| "startups similar to Notion" | Exa | 76% HIGH | "similar to", "Series A" |
| "companies like stripe.com" | Exa | 100% HIGH | URL detected, "companies like" |
| "MacBook Pro M3 specs review" | Serper | 70% HIGH | brand+product, "specs", "review" |
| "Tesla" | Serper | 0% LOW | No signals (fallback) |
| "arxiv papers on transformers" | Exa | 58% | "arxiv" |
| "latest AI news 2026" | Serper | 77% HIGH | "latest", "news", "2026" |

---

## [2.0.0] - 2026-01-23

### 🎉 Major Features

#### Smart Auto-Routing
- **Automatic provider selection** based on query analysis
- No need to manually choose provider - just search!
- Intelligent keyword matching for routing decisions
- Pattern detection for query types (shopping, research, discovery)
- Scoring system for provider selection

#### User Configuration
- **config.json**: Full control over auto-routing behavior
- **Configurable keyword mappings**: Add your own routing keywords
- **Provider priority**: Set tie-breaker order
- **Disable providers**: Turn off providers you don't have API keys for
- **Enable/disable auto-routing**: Opt-in or opt-out as needed

#### Debugging Tools
- **--explain-routing** flag: See exactly why a provider was selected
- Detailed routing metadata in JSON responses
- Shows matched keywords and routing scores

### 📚 Documentation

- **README.md**: Complete auto-routing guide with examples
- **SKILL.md**: Detailed routing logic and configuration reference
- **FAQ section**: Common questions about auto-routing
- **Configuration examples**: Pre-built configs for common use cases

---

## [1.0.x] - Initial Release

- Multi-provider search: Serper, Tavily, Exa
- Manual provider selection with `-p` flag
- Unified JSON output format
- Provider-specific options (--depth, --category, --similar-url, etc.)
- Domain filtering for Tavily/Exa
- Date filtering for Exa
