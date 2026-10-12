"""Evaluate confirmed offline annotations only within their declared scope."""
import argparse,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from independent_review import evaluate_review
parser=argparse.ArgumentParser()
parser.add_argument('project');parser.add_argument('review');parser.add_argument('--audio',required=True)
parser.add_argument('--output',default='artifacts/独立核对评测.json')
args=parser.parse_args()
review=json.loads(Path(args.review).read_text(encoding='utf-8'))
project=json.loads(Path(args.project).read_text(encoding='utf-8'))
digest=hashlib.sha256(Path(args.audio).read_bytes()).hexdigest()
try:report=evaluate_review(project,review,digest)
except (ValueError,KeyError,TypeError) as e:raise SystemExit('未生成评测：'+str(e))
report.update(project_file=args.project,review_file=args.review)
out=Path(args.output);out.parent.mkdir(exist_ok=True,parents=True)
out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(out)
