#!/usr/bin/env bash
# Re-run the #14 indexer and publish channels.json if it changed.
# Usage: ./refresh.sh [max_blocks]   (NODE defaults to Sneg/Tailscale, fast)
set -e
cd "$(dirname "$0")"
NODE="${NODE:-http://100.108.127.3:8080}" python3 indexer.py "${1:-1500}"
git add channels.json
if git diff --cached --quiet; then echo "no change"; exit 0; fi
git commit -q -m "index: refresh channels.json ($(date -u +%FT%TZ))"
git push -q && echo "published"
