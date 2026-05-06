#!/bin/bash

set -e

BASE_DIR="/Users/dig/sakura-rss"
PYTHON="/usr/local/bin/python3"

cd "$BASE_DIR" || exit 1

echo "🚀 GUI起動"
exec "$PYTHON" gui.py