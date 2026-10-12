"""Actual batch inference. Preserve failures and never drop low-scoring samples."""
import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("NUMBA_CACHE_DIR", str(ROOT / ".cache" / "numba"))
from app import normalize_audio, transcribe
from evaluation import PROTOCOL, evaluate_notes


def digest(path):
    sha = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def run(manifest_path, output):
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    samples = manifest.get("accepted", [])
    if not samples:
        raise ValueError("没有可评测样本")
    output = Path(output)
    # A fresh directory prevents old results masquerading as this run.
    output.mkdir(parents=True, exist_ok=False)
    result = {"started_utc": datetime.now(timezone.utc).isoformat(),
              "manifest_sha256": digest(manifest_path), "protocol": PROTOCOL,
              "source_dataset": manifest.get("dataset", "unspecified"),
              "purpose": manifest.get("purpose", "diagnostic"),
              "training_overlap_warning": manifest.get("training_overlap_warning", "unknown"),
              "python": sys.version.split()[0], "platform": platform.platform(),
              "dependencies": {p: importlib.metadata.version(p) for p in ("basic-pitch", "onnxruntime", "mir-eval")},
              "selected_ids": manifest.get("selected_ids", [s["id"] for s in samples]),
              "annotation_rejections": manifest.get("rejected", []), "results": [], "failures": []}
    for index, sample in enumerate(samples):
        print(f"[{index+1}/{len(samples)}] {sample['id']}", flush=True)
        try:
            with Path(sample["gold"]).open(encoding="utf-8-sig", newline="") as f:
                gold = [{k: float(row[k]) for k in ("pitch", "start", "end")} for row in csv.DictReader(f)]
            with tempfile.TemporaryDirectory() as temp:
                wav = Path(temp) / "normalized.wav"
                duration = normalize_audio(Path(sample["audio"]), wav)
                started = time.perf_counter()
                notes = transcribe(wav, duration)
                elapsed = time.perf_counter() - started
            scores = evaluate_notes(gold, notes)
            item = {"id": sample["id"], "duration": duration, "inference_seconds": elapsed,
                    "real_time_factor": elapsed / duration,
                    "audio_sha256": digest(sample["audio"]), "gold_sha256": digest(sample["gold"]),
                    "scores": scores, "notes_file": f"{index:03d}-notes.json"}
            (output / item["notes_file"]).write_text(json.dumps(notes, indent=2), encoding="utf-8")
            result["results"].append(item)
        except Exception as error:
            result["failures"].append({"id": sample.get("id"), "type": type(error).__name__, "reason": str(error)})
    successful = result["results"]
    result["completed_utc"] = datetime.now(timezone.utc).isoformat()
    result["status"] = "complete" if successful and not result["failures"] and not result["annotation_rejections"] else "incomplete"
    result["counts"] = {"selected": len(result["selected_ids"]), "evaluated": len(successful),
                        "failed": len(result["failures"]), "annotation_rejected": len(result["annotation_rejections"])}
    result["macro_average_over_successful_only"] = {
        metric: {name: sum(r["scores"][metric][name] for r in successful) / len(successful)
                 for name in ("precision", "recall", "f1")}
        for metric in ("onset_only", "onset_and_offset")} if successful else None
    (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output / "per_sample.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["sample", "duration", "inference_seconds", "onset_f1", "onset_offset_f1"])
        for r in successful:
            writer.writerow([r["id"], r["duration"], r["inference_seconds"], r["scores"]["onset_only"]["f1"], r["scores"]["onset_and_offset"]["f1"]])
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--output", default="artifacts/batch-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    args = parser.parse_args()
    result = run(args.manifest, args.output)
    print(json.dumps({"status": result["status"], "counts": result["counts"], "output": args.output}, indent=2))
    if result["status"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
