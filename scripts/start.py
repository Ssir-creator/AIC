"""Start one local worker. Put authentication in front before public deployment."""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
os.chdir(root)
sys.path.insert(0, str(root))
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("NUMBA_CACHE_DIR", str(root / ".cache" / "numba"))
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=os.environ.get("AIC_HOST", "127.0.0.1"),
                port=int(os.environ.get("PORT", os.environ.get("AIC_PORT", "8000"))), workers=1)
