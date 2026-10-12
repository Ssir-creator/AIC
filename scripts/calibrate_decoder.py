"""Calibrate on observed diagnostics; lock one setting before new validation.

This is decoder parameter selection, not new model training or a novel model.
GuitarSet may overlap Basic Pitch training, even for this local validation set.
"""
import argparse
import csv
import hashlib
import json
import os
import random
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.setdefault("OMP_NUM_THREADS","2")
os.environ.setdefault("OPENBLAS_NUM_THREADS","2")
os.environ.setdefault("NUMBA_CACHE_DIR",str(ROOT/".cache"/"numba"))
import soundfile as sf
from app import get_model, midi_to_events, normalize_audio
from evaluation import PROTOCOL, evaluate_notes
from scripts.prepare_guitarset import convert_annotations

CANDIDATES = [.15,.2,.25,.3,.35]


def read_gold(sample):
    with Path(sample["gold"]).open(encoding="utf-8-sig",newline="") as f:
        return [{k:float(row[k]) for k in ("pitch","start","end")} for row in csv.DictReader(f)]


def prepare_validation(calibration, data, output):
    excluded = set(calibration["selected_ids"])
    audio = sorted(p for p in (data/"audio_mono-mic").rglob("*_mic.wav") if p.stem.removesuffix("_mic") not in excluded)
    selected = random.Random(20261011).sample(audio,12)
    samples=[]
    for path in selected:
        id_=path.stem.removesuffix("_mic")
        labels=list((data/"annotation").rglob(id_+".jams"))
        if len(labels)!=1:
            raise ValueError("标注配对异常，停止，不替换样本")
        duration=sf.info(path).duration
        if not .2<=duration<=60:
            raise ValueError("样本超出范围，停止，不替换样本")
        gold=convert_annotations(json.loads(labels[0].read_text(encoding="utf-8")),duration)
        target=output/(id_+"-gold.csv")
        with target.open("w",encoding="utf-8",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=["pitch","start","end"]);writer.writeheader();writer.writerows(gold)
        samples.append({"id":id_,"audio":str(path.resolve()),"gold":str(target.resolve()),"duration":duration})
    return samples


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("calibration_manifest")
    parser.add_argument("data_root")
    parser.add_argument("--output",default="artifacts/decoder-calibration-20261011")
    args=parser.parse_args()
    output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=False)
    cal=json.loads(Path(args.calibration_manifest).read_text(encoding="utf-8"))
    if cal.get("rejected") or len(cal["accepted"])!=12:
        raise ValueError("校准样本需完整12段")
    validation=prepare_validation(cal,Path(args.data_root).resolve(),output)
    protocol={"created_utc":datetime.now(timezone.utc).isoformat(),"objective":"maximize calibration macro onset+offset F1, with onset F1 degradation <=0.01",
      "candidates":CANDIDATES,"baseline":.3,"onset_threshold":.5,"minimum_note_frames":11,
      "calibration_ids":[s["id"] for s in cal["accepted"]],"validation_ids":[s["id"] for s in validation],
      "split_seed":20261011,"metrics":PROTOCOL,
      "warning":"Calibration includes previously observed diagnostics. Local validation is disjoint from calibration, but overlap with Basic Pitch's original training is unknown. Not a pipa evaluation."}
    (output/"protocol.json").write_text(json.dumps(protocol,indent=2),encoding="utf-8")
    from basic_pitch.inference import run_inference
    from basic_pitch.note_creation import model_output_to_notes
    cal_scores={t:[] for t in CANDIDATES}
    result={"protocol":protocol,"calibration":[],"validation":[]}

    def process(sample,thresholds):
        with tempfile.TemporaryDirectory() as temp:
            wav=Path(temp)/"normalized.wav"
            duration=normalize_audio(Path(sample["audio"]),wav)
            raw=run_inference(wav,get_model())
        gold=read_gold(sample);scores={}
        for threshold in thresholds:
            midi,_=model_output_to_notes(raw,onset_thresh=.5,frame_thresh=threshold,min_note_len=11,
                min_freq=27.5,max_freq=4186.01,include_pitch_bends=False)
            notes=midi_to_events(midi,duration)
            scores[str(threshold)]=evaluate_notes(gold,notes)
        return {"id":sample["id"],"scores":scores}

    for s in cal["accepted"]:
        print("calibration",s["id"],flush=True)
        item=process(s,CANDIDATES);result["calibration"].append(item)
        for threshold in CANDIDATES:
            cal_scores[threshold].append(item["scores"][str(threshold)])
    means={t:{metric:sum(s[metric]["f1"] for s in scores)/len(scores)
        for metric in ("onset_only","onset_and_offset")} for t,scores in cal_scores.items()}
    eligible=[t for t in CANDIDATES if means[t]["onset_only"]>=means[.3]["onset_only"]-.01]
    selected=max(eligible,key=lambda t:(means[t]["onset_and_offset"],-abs(t-.3)))
    selection={"selected_frame_threshold":selected,"calibration_means":means,
       "locked_before_validation_utc":datetime.now(timezone.utc).isoformat()}
    (output/"selection.json").write_text(json.dumps(selection,indent=2),encoding="utf-8")
    result["selection"]=selection
    for s in validation:
        print("validation",s["id"],flush=True)
        result["validation"].append(process(s,sorted({.3,selected})))
    result["validation_means"]={str(t):{metric:sum(s["scores"][str(t)][metric]["f1"] for s in result["validation"])/len(validation)
      for metric in ("onset_only","onset_and_offset")} for t in sorted({.3,selected})}
    result["completed_utc"]=datetime.now(timezone.utc).isoformat()
    result["status"]="complete"
    (output/"results.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps({"selected":selected,"calibration_means":means,"validation_means":result["validation_means"]},indent=2))


if __name__=="__main__":
    main()
