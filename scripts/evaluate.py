"""Evaluate exported notes against independently annotated ground truth.

Gold CSV fields: pitch,start,end. Do not create gold from the prediction itself.
"""
import argparse
import csv
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation import PROTOCOL, evaluate_notes

parser = argparse.ArgumentParser()
parser.add_argument("project", help="downloaded review-record.json")
parser.add_argument("gold", help="independent annotated pitch,start,end CSV")
parser.add_argument("--output", default="artifacts/evaluation.json")
args = parser.parse_args()
project = json.loads(Path(args.project).read_text(encoding="utf-8"))
with open(args.gold, encoding="utf-8-sig", newline="") as f:
    gold = sorted([{k:float(row[k]) for k in ("pitch","start","end")} for row in csv.DictReader(f)], key=lambda n:n["start"])
if not gold:
    raise SystemExit("标注不能为空")
for n in gold:
    if n["end"] <= n["start"] or n["start"] < 0 or not 21 <= n["pitch"] <= 108:
        raise SystemExit("标注包含无效音符")


result = {"source":args.project,"gold":args.gold,"reference_notes":len(gold),
          "protocol":PROTOCOL,
          "warning":"人工校对后指标不代表基础模型精度提升；单段结果不可推广到全部琵琶录音。"}
for name,key in [("model_draft","original_notes"),("human_reviewed","notes")]:
    result[name] = evaluate_notes(gold, project[key])

output = Path(args.output)
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(result,ensure_ascii=False,indent=2))
