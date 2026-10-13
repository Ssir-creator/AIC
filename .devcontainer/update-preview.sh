#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

git pull --ff-only origin main
if [ -f /tmp/tusu-preview.pid ]; then
  kill "$(cat /tmp/tusu-preview.pid)" 2>/dev/null || true
  rm -f /tmp/tusu-preview.pid
fi
bash .devcontainer/start-preview.sh
echo "图溯预览已更新，请刷新浏览器页面。"
