#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

git pull --ff-only origin main
python -m pip install -r requirements.txt
bash .devcontainer/start-preview.sh --restart
echo "图溯预览已更新，请刷新浏览器页面。"
