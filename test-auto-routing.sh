#!/bin/bash

# Live check of automatic routing (uses real provider quota).
# Offline alternative: python3 scripts/search.py --explain-routing -q "..."

# Load from environment or .env file
if [ -f .env ]; then
  source .env
fi

if [ -z "$BRAVE_API_KEY$SERPER_API_KEY$EXA_API_KEY" ]; then
  echo "Error: set at least one of BRAVE_API_KEY, SERPER_API_KEY, EXA_API_KEY. Copy .env.example to .env and add your keys."
  exit 1
fi

echo "Testing auto-routing..."
python3 scripts/search.py -q "weather in Vienna today" --compact          # general/local -> Brave
python3 scripts/search.py -q "python asyncio TaskGroup documentation" --compact  # docs -> Exa
python3 scripts/search.py -q "iPhone 16 Pro Max price" --compact          # shopping -> Serper
