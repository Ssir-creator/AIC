"""Bundle measured evidence and two preselected public examples, with attribution."""
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import pretty_midi

ROOT=Path(__file__).resolve().parents[1]
manifest=json.loads((ROOT/"artifacts/guitarset/manifest.json").read_text(encoding="utf-8"))
directory=ROOT/"artifacts/guitarset-baseline-20261011"
results=json.loads((directory/"results.json").read_text(encoding="utf-8"))
samples={s["id"]:s for s in manifest["accepted"]}
items={r["id"]:r for r in results["results"]}
output=ROOT/"artifacts/谱易改-实测与示例包.zip"
with ZipFile(output,"w",ZIP_DEFLATED) as z:
    for file in directory.iterdir():
        if file.is_file() and file.suffix in (".json",".csv",".svg",".png"):
            z.write(file,"diagnostic/"+file.name)
    calibration=ROOT/"artifacts/decoder-calibration-20261011"
    for file in calibration.iterdir():
        if file.is_file() and file.suffix in (".json",".csv"):
            z.write(file,"decoder-calibration/"+file.name)
    for name in ("阶段评测报告.md","公开数据选择.md"):
        z.write(ROOT/"docs"/name,name)
    z.write(ROOT/"third_party/GUITARSET_ATTRIBUTION.md","GUITARSET_ATTRIBUTION.md")
    pdf=ROOT/"artifacts/阶段评测报告-非提交定稿.pdf"
    if pdf.is_file():z.write(pdf,pdf.name)
    # These are the first two preselected samples, not chosen by favorable scores.
    for id_ in manifest["selected_ids"][:2]:
        sample=samples[id_];item=items[id_]
        prefix="examples/"+id_+"/"
        z.write(sample["audio"],prefix+"audio-original.wav")
        z.write(sample["gold"],prefix+"independent-gold.csv")
        notes_file=directory/item["notes_file"]
        z.write(notes_file,prefix+"baseline-notes.json")
        midi=pretty_midi.PrettyMIDI(initial_tempo=120)
        instrument=pretty_midi.Instrument(program=0)
        for note in json.loads(notes_file.read_text()):
            instrument.notes.append(pretty_midi.Note(note["velocity"],note["pitch"],note["start"],note["end"]))
        midi.instruments.append(instrument)
        import io
        buffer=io.BytesIO();midi.write(buffer);z.writestr(prefix+"baseline.mid",buffer.getvalue())
    z.writestr("使用说明.txt","先阅读署名与许可。examples包含预先固定样本的前两段公开吉他录音、独立标注和基础模型MIDI。可用于试用软件，不是琵琶样本，也不是本项目原创音乐或原创模型成果。诊断和参数校准没有证明算法提升。人工校对和用户反馈仍须真实完成。")
with ZipFile(output) as z:
    assert z.testzip() is None
print(output,output.stat().st_size,"bytes")
