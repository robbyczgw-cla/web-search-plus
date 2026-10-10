#!/usr/bin/env python3
"""Web Search Plus — command-line search: ``python3 scripts/search.py -q "..."``.

The engine is the vendored Web Search Plus 5.0.1 engine in ``wsp_core/``;
``wsp_skill.py`` keeps this skill's flags, environment variables and provider
set on top of it. Run with ``--help`` for all options.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wsp_skill import run_search  # noqa: E402

if __name__ == "__main__":
    run_search()
