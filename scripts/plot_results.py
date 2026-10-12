"""Generate standalone diagnostic plots; needs matplotlib (optional tooling)."""
import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parents[1]/".cache"/"matplotlib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("results")
args = parser.parse_args()
path = Path(args.results)
results = json.loads(path.read_text(encoding="utf-8"))
items = results["results"]
if not items:
    raise SystemExit("No completed samples to plot")
labels = [r["id"] for r in items]
x = np.arange(len(items))
plt.rcParams.update({"font.family":"DejaVu Sans", "font.size":10,"axes.spines.top":False,"axes.spines.right":False})
fig, ax = plt.subplots(figsize=(13,5.5), layout="constrained")
fig.patch.set_facecolor("#fafbf7")
ax.set_facecolor("#fafbf7")
ax.bar(x-.18,[r["scores"]["onset_only"]["f1"] for r in items],width=.36,color="#658867",label="Pitch + onset F1")
ax.bar(x+.18,[r["scores"]["onset_and_offset"]["f1"] for r in items],width=.36,color="#c49a5d",label="Pitch + onset + offset F1")
ax.set_xticks(x,labels,rotation=35,ha="right",fontsize=8)
ax.set_ylim(0,1)
ax.set_ylabel("Note-level F1 (0 to 1)")
ax.set_title("GuitarSet / Basic Pitch baseline diagnostics",loc="left",weight="bold",pad=18)
ax.yaxis.grid(True,alpha=.2)
ax.set_axisbelow(True)
ax.legend(loc="upper right",frameon=False)
fig.suptitle("Fixed sample selection; training overlap unresolved; not a pipa evaluation",fontsize=10,color="#666666",x=.5,y=1.04)
fig.savefig(path.parent/"baseline-diagnostics.png",dpi=180,bbox_inches="tight")
fig.savefig(path.parent/"baseline-diagnostics.svg",bbox_inches="tight")
plt.close(fig)
print(path.parent/"baseline-diagnostics.png")
