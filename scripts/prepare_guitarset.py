"""Prepare diagnostic audio/independent note annotations from official GuitarSet.

Download the official audio_mono-mic.zip and annotation.zip first. This script
does not treat mirdata's modified test fixtures as an evaluation dataset.
"""
import argparse
import csv
import hashlib
import json
import math
import random
from pathlib import Path

import soundfile as sf


def convert_annotations(document, actual_duration):
    declared = document.get("file_metadata", {}).get("duration")
    if declared is not None and abs(float(declared) - actual_duration) > .1:
        raise ValueError("标注时长与音频不匹配；不能使用截短或修改过的测试fixture")
    notes = []
    for annotation in document.get("annotations", []):
        if annotation.get("namespace") != "note_midi":
            continue
        events = annotation.get("data", [])
        if not isinstance(events, list):
            raise ValueError("未知的note_midi格式")
        for event in events:
            start = float(event["time"])
            end = start + float(event["duration"])
            pitch = float(event["value"])
            if not all(math.isfinite(x) for x in (start,end,pitch)):
                raise ValueError("非有限标注值")
            if not 21 <= pitch <= 108 or start < 0 or end <= start or end > actual_duration + .02:
                raise ValueError("标注音高或区间异常，需人工核查，不能静默丢弃")
            notes.append({"pitch":pitch,"start":start,"end":end})
    if not notes:
        raise ValueError("缺少note_midi标注")
    intervals = [(n["pitch"],n["start"],n["end"]) for n in notes]
    if len(set(intervals)) != len(intervals):
        raise ValueError("存在完全重复标注，需核查官方已知问题")
    return sorted(notes, key=lambda n:(n["start"],n["pitch"]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio_dir", help="extracted audio_mono-mic directory")
    parser.add_argument("annotation_dir", help="extracted annotation directory")
    parser.add_argument("--output", default="artifacts/guitarset")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    if args.limit < 1:
        raise SystemExit("limit必须为正数")
    audio_dir, annotation_dir = Path(args.audio_dir).resolve(), Path(args.annotation_dir).resolve()
    pairs = []
    for audio in sorted(audio_dir.rglob("*_mic.wav")):
        id_ = audio.stem.removesuffix("_mic")
        labels = list(annotation_dir.rglob(id_ + ".jams"))
        if len(labels) == 1:
            pairs.append((id_,audio,labels[0]))
    if not pairs:
        raise SystemExit("未找到匹配音频与JAMS；请检查两个官方压缩包的解压目录")
    # Fix the sample before model inference. Do not replace poor-scoring examples.
    selected = random.Random(args.seed).sample(pairs, min(args.limit,len(pairs)))
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"dataset":"GuitarSet","source":"https://zenodo.org/records/3371780",
                "purpose":"diagnostic, not independently held-out generalization benchmark",
                "training_overlap_warning":"Basic Pitch's repository includes GuitarSet training pipelines; membership in its model's held-out split has not been verified",
                "seed":args.seed,"selected_ids":[p[0] for p in selected],"accepted":[],"rejected":[]}
    for id_,audio,label in selected:
        try:
            info = sf.info(audio)
            if not .2 <= info.duration <= 60:
                raise ValueError("音频超出当前产品时长范围")
            notes = convert_annotations(json.loads(label.read_text(encoding="utf-8")),info.duration)
            gold = output / (id_ + "-gold.csv")
            with gold.open("w",encoding="utf-8",newline="") as f:
                writer = csv.DictWriter(f,fieldnames=["pitch","start","end"])
                writer.writeheader(); writer.writerows(notes)
            manifest["accepted"].append({"id":id_,"audio":str(audio),"gold":str(gold.resolve()),
                  "duration":info.duration,"notes":len(notes),
                  "annotation_sha256":hashlib.sha256(label.read_bytes()).hexdigest()})
        except (ValueError,KeyError,TypeError,RuntimeError) as error:
            manifest["rejected"].append({"id":id_,"reason":str(error)})
    (output / "manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(manifest,ensure_ascii=False,indent=2))
    if not manifest["accepted"]:
        raise SystemExit("没有可用配对，请人工检查原始数据")


if __name__ == "__main__":
    main()
