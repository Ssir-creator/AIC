"""Import an optional PRIVATE demo bundled separately from the source package."""
import json,sys,uuid,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import DATA,Note,write_project,normalize_audio
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'var/demo-import'
if not (source/'project.json').is_file() or not (source/'audio.wav').is_file():
    raise SystemExit('未找到私有演示数据，请使用完整私有试用包；源码包不包含本人录音。')
# Repeatable: preserve an existing project and its user edits.
pointer=DATA/'demo-project-id.json'
if pointer.is_file():
    prior=json.loads(pointer.read_text())['id']
    try:
        from app import read_project
        read_project(prior)
        print('演示项目已存在，保留已有修改。');raise SystemExit(0)
    except Exception as exc:
        from fastapi import HTTPException
        if not isinstance(exc,HTTPException):raise
p=json.loads((source/'project.json').read_text())
for note in p['notes']+p['original_notes']:Note.model_validate(note)
folder=DATA/str(uuid.uuid4());folder.mkdir()
try:
    duration=normalize_audio(source/'audio.wav',folder/'audio.wav')
    if abs(duration-p['duration'])>.01:raise ValueError('音频与项目时长不一致')
    p['id']=folder.name
    write_project(folder,p)
    pointer.write_text(json.dumps({'id':folder.name},indent=2))
except Exception:
    shutil.rmtree(folder);raise
print('已导入春雨私有试用案例，启动后点“打开春雨试用案例”。参考草稿尚未确认。')
