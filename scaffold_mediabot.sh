#!/usr/bin/env bash
# scaffold_mediabot.sh
set -euo pipefail

move_file() {
  local src="$1" dst="$2"
  if [ -f "$src" ]; then
    mv "$src" "$dst" && echo "  ✓ $src → $dst"
  else
    echo "  ⚠ not found: $src"
  fi
}

echo "→ Moving test files..."
move_file test_database.py   tests/unit/test_database.py
move_file test_omdb.py       tests/unit/test_omdb.py
move_file test_watchmode.py  tests/unit/test_watchmode.py
move_file test_handlers.py   tests/unit/test_handlers.py
move_file test_dashboard.py  tests/integration/test_dashboard.py

echo "→ Moving workflow file..."
mkdir -p .github/workflows
move_file ci.yml             .github/workflows/ci.yml

echo "→ Moving setup script..."
move_file setup_launchd.sh   scripts/setup_launchd.sh
[ -f scripts/setup_launchd.sh ] && chmod +x scripts/setup_launchd.sh

echo "→ Creating missing __init__.py files..."
touch src/__init__.py src/api/__init__.py src/bot/__init__.py \
      src/db/__init__.py src/services/__init__.py \
      tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py

echo ""
echo "✅ Done!"
