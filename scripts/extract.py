#!/usr/bin/env python3
"""Web Search Plus — URL extraction with automatic provider fallback.

Usage:
    python3 scripts/extract.py --url https://example.com
    python3 scripts/extract.py --url https://example.com --provider firecrawl --format markdown
    python3 scripts/extract.py --url https://example.com --url https://example.org --include-images

The engine is the vendored Web Search Plus 5.0.1 engine in ``wsp_core/``;
``wsp_skill.py`` keeps this skill's flags and environment variables.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wsp_skill import extract_urls as extract_plus, run_extract  # noqa: E402,F401

if __name__ == "__main__":
    run_extract()
