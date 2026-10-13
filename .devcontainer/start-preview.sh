#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

if curl -fsS http://127.0.0.1:8765/health >/dev/null 2>&1; then
  echo "图溯预览已在运行：http://127.0.0.1:8765"
  exit 0
fi

if [ -f /tmp/tusu-preview.pid ]; then
  kill "$(cat /tmp/tusu-preview.pid)" 2>/dev/null || true
  rm -f /tmp/tusu-preview.pid
fi

nohup python app.py --host 0.0.0.0 --port 8765 >/tmp/tusu-preview.log 2>&1 &
echo $! >/tmp/tusu-preview.pid

for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS http://127.0.0.1:8765/health >/dev/null 2>&1; then
    echo "图溯预览启动成功：http://127.0.0.1:8765"
    exit 0
  fi
  sleep 1
done

echo "图溯预览启动失败，日志如下："
cat /tmp/tusu-preview.log
exit 1
