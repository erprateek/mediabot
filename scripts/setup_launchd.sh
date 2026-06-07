#!/usr/bin/env bash
# scripts/setup_launchd.sh
#
# One-time script to register a GitHub Actions self-hosted runner on your
# Mac Mini and install it as a launchd service so it auto-starts on login.
#
# USAGE
#   1. Generate a runner token in GitHub:
#      Repo → Settings → Actions → Runners → "New self-hosted runner" → macOS
#   2. Set the two variables below (or export them before running this script)
#   3. chmod +x scripts/setup_launchd.sh && ./scripts/setup_launchd.sh

set -euo pipefail

# ── EDIT THESE ──────────────────────────────────────────────────────────────
GITHUB_REPO_URL="${GITHUB_REPO_URL:-https://github.com/YOUR_USERNAME/mediabot}"
RUNNER_TOKEN="${RUNNER_TOKEN:-PASTE_YOUR_TOKEN_HERE}"
# ────────────────────────────────────────────────────────────────────────────

RUNNER_DIR="$HOME/actions-runner"
RUNNER_VERSION="2.316.0"
RUNNER_ARCHIVE="actions-runner-osx-arm64-${RUNNER_VERSION}.tar.gz"
RUNNER_URL="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${RUNNER_ARCHIVE}"

echo "→ Creating runner directory: $RUNNER_DIR"
mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

echo "→ Downloading GitHub Actions runner v${RUNNER_VERSION}..."
curl -fsSL -o "$RUNNER_ARCHIVE" "$RUNNER_URL"
tar xzf "$RUNNER_ARCHIVE"
rm "$RUNNER_ARCHIVE"

echo "→ Configuring runner for $GITHUB_REPO_URL ..."
./config.sh \
  --url "$GITHUB_REPO_URL" \
  --token "$RUNNER_TOKEN" \
  --name "mac-mini-runner" \
  --labels "self-hosted,macOS,arm64" \
  --work "_work" \
  --unattended \
  --replace

echo "→ Installing as launchd service..."
./svc.sh install
./svc.sh start

echo ""
echo "✅ Done! The runner will now start automatically on login."
echo "   Check status with:  cd $RUNNER_DIR && ./svc.sh status"
echo "   View logs in:       ~/Library/Logs/actions.runner.*"
