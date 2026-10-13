#!/usr/bin/env bash
set -euo pipefail

if [ -f /tmp/tusu-preview.pid ] && kill -0 "$(cat /tmp/tusu-preview.pid)" 2>/dev/null; then
  exit 0
fi

nohup python app.py --host 0.0.0.0 --port 8765 >/tmp/tusu-preview.log 2>&1 &
echo $! >/tmp/tusu-preview.pid
