"""Describe actual matching errors and review hints without tuning on test scores."""
import argparse
import csv
import json
import sys
from pathlib import Path

import mir_eval
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import review_reasons
from evaluation import arrays


def analyze(gold, predicted):
    gold = sorted(gold, key=lambda n: (n["start"], n["pitch"]))
    predicted = sorted(predicted, key=lambda n: (n["start"], n["pitch"]))
    ref_i, ref_p = arrays(gold)
    est_i, est_p = arrays(predicted)
    matches = mir_eval.transcription.match_notes(ref_i, ref_p, est_i, est_p, offset_ratio=None)
    matched_pred = {j for _,j in matches}
    matched_ref = {i for i,_ in matches}
    unmatched_pred = set(range(len(predicted))) - matched_pred
    flagged = {j for j,n in enumerate(predicted) if review_reasons(n)}
    short = {j for j,n in enumerate(predicted) if n["end"]-n["start"] < .18}
    weak = {j for j,n in enumerate(predicted) if n["velocity"] < 45}
    timing = [{"reference":gold[i], "prediction":predicted[j],
               "start_error_seconds":predicted[j]["start"]-gold[i]["start"],
               "end_error_seconds":predicted[j]["end"]-gold[i]["end"]}
              for i,j in matches]
    offset_mismatch = [x for x in timing if abs(x["end_error_seconds"]) > max(.05,.2*(x["reference"]["end"]-x["reference"]["start"]))]
    return {"reference_notes":len(gold),"predicted_notes":len(predicted),
            "onset_pitch_matched":len(matches),"unmatched_predictions":len(unmatched_pred),
            "unmatched_references":len(gold)-len(matched_ref),
            "matched_notes_with_offset_mismatch":len(offset_mismatch),
            "median_start_error_seconds":float(np.median([x["start_error_seconds"] for x in timing])) if timing else None,
            "review_hints":{"flagged":len(flagged),"short":len(short),"weak":len(weak),
              "flagged_unmatched":len(flagged & unmatched_pred),
              "unmatched_fraction_among_flagged":len(flagged & unmatched_pred)/len(flagged) if flagged else None,
              "unmatched_fraction_overall":len(unmatched_pred)/len(predicted) if predicted else None},
            "examples":{"unmatched_predictions":[predicted[j] for j in sorted(unmatched_pred)[:5]],
              "unmatched_references":[gold[i] for i in sorted(set(range(len(gold)))-matched_ref)[:5]],
              "offset_mismatch":offset_mismatch[:5]}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("results")
    parser.add_argument("--output")
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    path = Path(args.results)
    results = json.loads(path.read_text(encoding="utf-8"))
    samples = {s["id"]:s for s in manifest["accepted"]}
    analysis = {"dataset":results["source_dataset"],"source_results":str(path),
      "warning":"Unmatched means unmatched under the stated annotation/timing metric; hints are not calibrated error probabilities, and guitar findings do not establish pipa behavior.","samples":[]}
    for item in results["results"]:
        sample = samples[item["id"]]
        with Path(sample["gold"]).open(encoding="utf-8-sig",newline="") as f:
            gold = [{k:float(row[k]) for k in ("pitch","start","end")} for row in csv.DictReader(f)]
        predicted = json.loads((path.parent/item["notes_file"]).read_text(encoding="utf-8"))
        analysis["samples"].append({"id":item["id"],**analyze(gold,predicted)})
    total_keys = ("reference_notes","predicted_notes","onset_pitch_matched","unmatched_predictions","unmatched_references","matched_notes_with_offset_mismatch")
    analysis["totals"] = {k:sum(s[k] for s in analysis["samples"]) for k in total_keys}
    flagged = sum(s["review_hints"]["flagged"] for s in analysis["samples"])
    flagged_unmatched = sum(s["review_hints"]["flagged_unmatched"] for s in analysis["samples"])
    total = analysis["totals"]
    analysis["review_hints_totals"] = {"flagged":flagged,"flagged_unmatched":flagged_unmatched,
      "unmatched_fraction_among_flagged":flagged_unmatched/flagged if flagged else None,
      "unmatched_fraction_overall":total["unmatched_predictions"]/total["predicted_notes"] if total["predicted_notes"] else None}
    output = Path(args.output) if args.output else path.parent/"error-analysis.json"
    output.write_text(json.dumps(analysis,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"totals":analysis["totals"],"hints":analysis["review_hints_totals"]},indent=2))


if __name__ == "__main__":
    main()
