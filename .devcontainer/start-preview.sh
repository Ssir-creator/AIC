#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

if [ "${1:-}" = '--restart' ]; then
  python - <<'PY'
import os, signal, time
from pathlib import Path
root = Path.cwd().resolve()
pids = []
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():
        continue
    try:
        args = (proc / 'cmdline').read_bytes().split(b'\0')
        absolute_app = str(root / 'app.py').encode()
        if absolute_app in args:
            pids.append(int(proc.name))
        elif b'app.py' in args and (proc / 'cwd').resolve() == root:
            pids.append(int(proc.name))
    except (OSError, PermissionError):
        continue
for pid in pids:
    try: os.kill(pid, signal.SIGTERM)
    except ProcessLookupError: pass
for _ in range(30):
    if not any(Path('/proc', str(pid)).exists() for pid in pids): break
    time.sleep(.1)
for pid in pids:
    try: os.kill(pid, signal.SIGKILL)
    except ProcessLookupError: pass
PY
  rm -f /tmp/tusu-preview.pid
fi

EXPECTED_VERSION="$(python -c 'import app; print(app.VERSION)')"
check_health() {
  curl -fsS --max-time 3 http://127.0.0.1:8765/health 2>/dev/null |
    python -c 'import sys,json; q=json.load(sys.stdin); sys.exit(0 if q.get("version")==sys.argv[1] else 1)' "$EXPECTED_VERSION" 2>/dev/null
}

if check_health; then
  echo "图溯预览已在运行：http://127.0.0.1:8765"
  exit 0
fi

if [ -f /tmp/tusu-preview.pid ]; then
  kill "$(cat /tmp/tusu-preview.pid)" 2>/dev/null || true
  rm -f /tmp/tusu-preview.pid
fi

nohup python "$PROJECT_DIR/app.py" --host 0.0.0.0 --port 8765 >/tmp/tusu-preview.log 2>&1 &
echo $! >/tmp/tusu-preview.pid

for _ in 1 2 3 4 5 6 7 8 9 10; do
  if check_health; then
    echo "图溯预览启动成功，版本 $EXPECTED_VERSION，端口8765"
    exit 0
  fi
  sleep 1
done

echo "图溯预览启动失败，日志如下："
cat /tmp/tusu-preview.log
exit 1
