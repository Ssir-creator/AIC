"""Cross-platform install; run with Python 3.12. No GPU or API key required."""
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
if sys.version_info[:2] != (3, 12):
    raise SystemExit("请使用 Python 3.12；当前锁定依赖已在3.12验证。")
python = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
if not python.exists():
    venv.EnvBuilder(with_pip=True, symlinks=os.name != "nt").create(root / ".venv")
subprocess.run([str(python), "-c", "import sys; assert sys.version_info[:2] == (3,12), 'existing venv must use Python3.12'"], check=True)
subprocess.run([str(python), "-m", "pip", "install", "-r", str(root / "requirements.lock")], check=True)
# Upstream pins TensorFlow<2.15.1 for Python>=3.11, which has no Python3.12 wheel.
# Use the upstream-supported ONNX model instead. Its full runtime dependencies
# are pinned separately; do not install the TensorFlow-only metadata dependency.
subprocess.run([str(python), "-m", "pip", "install", "--no-deps", "basic-pitch==0.4.0"], check=True)
if not shutil.which("ffmpeg"):
    raise SystemExit("依赖已安装，但缺少ffmpeg。请安装ffmpeg并加入PATH，再重跑此脚本。")
subprocess.run([str(python), "-c", "from app import get_model; print('ONNX model ready:', get_model().model_type)"], cwd=root, check=True)
print("安装完成。启动：", python, root / "scripts/start.py")
