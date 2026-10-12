"""谱易改：本地单乐器转谱与人工校对。基础模型来自 Spotify。"""
from __future__ import annotations

import io
import hashlib
import json
import os
import subprocess
import threading
import time
import uuid
from functools import lru_cache
from pathlib import Path

import numpy as np
import pretty_midi
import soundfile as sf
from fastapi import FastAPI, HTTPException, UploadFile, Query
from notation import export_musicxml
from practice import parse_reference, compare_reference
from alignment import auto_align
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator
from site_security import access_gate
from jianpu import parse_jianpu,KEYS
from project_backup import make_backup,unpack_backup
from independent_review import evaluate_review
from typing import Literal

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("AIC_DATA_DIR", ROOT / "var"))
DATA.mkdir(parents=True, exist_ok=True)
MAX_SECONDS = 60
MAX_BYTES = 20 * 1024 * 1024
INFERENCE_LOCK = threading.Lock()
EDIT_LOCK = threading.Lock()
app = FastAPI(title="谱易改", version="0.2.0")
app.middleware('http')(access_gate)
app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")


class Note(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    pitch: int = Field(ge=21, le=108, strict=True)
    start: float = Field(ge=0, le=MAX_SECONDS)
    end: float = Field(gt=0, le=MAX_SECONDS)
    velocity: int = Field(ge=1, le=127, strict=True)

    @model_validator(mode="after")
    def valid_interval(self):
        if self.end <= self.start:
            raise ValueError("音符结束时间必须晚于开始时间")
        return self


class Edit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)
    notes: list[Note] = Field(max_length=2000)


class Alignment(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    scale: float = Field(default=1, ge=.5, le=2)
    shift: float = Field(default=0, ge=-60, le=60)
    window: float = Field(default=.3, ge=.05, le=1)
    timing_tolerance: float = Field(default=.08, ge=.02, le=.5)
    duration_tolerance: float = Field(default=.12, ge=.02, le=1)

    @model_validator(mode="after")
    def check_window(self):
        if self.timing_tolerance > self.window:
            raise ValueError("起音容差不能大于匹配时间窗口")
        return self


class NumberedReference(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    text: str=Field(min_length=1,max_length=12000)
    key: str='D'
    octave: int=Field(default=4,ge=3,le=5)
    bpm: float=Field(default=60,ge=30,le=240)
    confirmed: bool=False


class IssueDecision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision: int=Field(ge=0)
    issue_id: str=Field(pattern=r'^[a-f0-9]{24}$')
    verdict: Literal['recognition_error','performance_difference','alignment_problem','reference_problem','uncertain']
    comment: str=Field(default='',max_length=500)


class ReferenceNote(Note):
    start: float=Field(ge=0,le=120)
    end: float=Field(gt=0,le=120)


def session_path(session_id: str) -> Path:
    try:
        if str(uuid.UUID(session_id)) != session_id:
            raise ValueError
    except ValueError:
        raise HTTPException(404, "项目不存在")
    path = DATA / session_id
    if not (path / "project.json").is_file():
        raise HTTPException(404, "项目不存在")
    return path


def read_project(session_id: str) -> dict:
    return json.loads((session_path(session_id) / "project.json").read_text(encoding="utf-8"))


def write_project(path: Path, project: dict) -> None:
    temporary = path / "project.tmp"
    temporary.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path / "project.json")


def normalize_audio(source: Path, destination: Path) -> float:
    # Decode only the allowed duration plus one second, limiting memory and output.
    try:
        subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-y", "-protocol_whitelist", "file,pipe", "-i", str(source),
             "-t", str(MAX_SECONDS + 1), "-ac", "1", "-ar", "22050", str(destination)],
            check=True, capture_output=True, timeout=30,
        )
        audio, rate = sf.read(destination)
    except (subprocess.SubprocessError, RuntimeError, OSError):
        raise HTTPException(422, "无法读取音频，请使用有效的 WAV、MP3、FLAC、OGG 或 M4A 文件")
    duration = len(audio) / rate
    if not 0.2 <= duration <= MAX_SECONDS:
        raise HTTPException(422, "请上传0.2—60秒的短音频，不会自动截断长录音")
    if not np.isfinite(audio).all() or np.max(np.abs(audio)) < 1e-5:
        raise HTTPException(422, "音频为空或接近静音，请检查录音")
    return duration


@lru_cache(maxsize=1)
def get_model():
    from basic_pitch import FilenameSuffix, build_icassp_2022_model_path
    from basic_pitch.inference import Model
    import onnxruntime as ort
    # Basic Pitch's ONNX runtime is officially supported; limit CPU concurrency.
    model = Model(build_icassp_2022_model_path(FilenameSuffix.onnx))
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    model.model = ort.InferenceSession(
        str(build_icassp_2022_model_path(FilenameSuffix.onnx)), options,
        providers=["CPUExecutionProvider"],
    )
    return model


def midi_to_events(midi, duration: float) -> list[dict]:
    """Serialize model MIDI notes consistently for UI and experiments."""
    notes = []
    for instrument in midi.instruments:
        for n in instrument.notes:
            start, end = max(0, n.start), min(duration, n.end)
            if end > start and 21 <= n.pitch <= 108:
                notes.append({"id": uuid.uuid4().hex[:12], "pitch": int(n.pitch),
                              "start": round(float(start), 4), "end": round(float(end), 4),
                              "velocity": int(max(1, n.velocity))})
    return sorted(notes, key=lambda n: (n["start"], n["pitch"]))


def transcribe(path: Path, duration: float, frame_threshold: float = .3) -> list[dict]:
    from basic_pitch.inference import predict
    _, midi, _ = predict(path, get_model(), frame_threshold=frame_threshold, minimum_frequency=27.5,
                         maximum_frequency=4186.01, multiple_pitch_bends=False)
    return midi_to_events(midi, duration)


def review_reasons(note: dict) -> list[str]:
    # Heuristics for listening priority, not calibrated error probabilities.
    reasons = []
    if note["end"] - note["start"] < 0.18:
        reasons.append("短音符：建议检查是否为装饰音或误识别")
    if note["velocity"] < 45:
        reasons.append("弱音符：建议对照原音确认")
    return reasons


def public_project(project: dict) -> dict:
    result = {**project, "notes": [{**n, "review_reasons": review_reasons(n)}
                                  for n in project["notes"]]}
    if project.get("reference"):
        result["practice"] = compare_reference(project["notes"], project["reference"], project["duration"])
        for issue in result['practice']['issues']:
            issue['human_review']=project.get('issue_reviews',{}).get(issue['id'])
    return result


@app.get("/")
def home():
    return FileResponse(ROOT / "web" / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "model": "Basic Pitch 0.4.0 / ONNX CPU",
            "ephemeral_storage": os.environ.get('AIC_EPHEMERAL_STORAGE')=='1',
            "max_seconds": MAX_SECONDS, "model_loaded": get_model.cache_info().currsize > 0}


@app.get("/api/practice-demo")
def practice_demo():
    pointer = DATA / "demo-project-id.json"
    if not pointer.is_file():
        raise HTTPException(404, "尚未导入私有试用案例")
    session_id = json.loads(pointer.read_text())["id"]
    return public_project(read_project(session_id))


@app.post("/api/transcribe")
def upload(file: UploadFile):
    import shutil
    if not INFERENCE_LOCK.acquire(blocking=False):
        raise HTTPException(429, "已有音频正在识别，请稍后重试")
    folder = DATA / str(uuid.uuid4())
    folder.mkdir()
    success = False
    try:
        content = file.file.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise HTTPException(413, "文件超过20MB，请使用更短的录音")
        source = folder / "source"
        source.write_bytes(content)
        duration = normalize_audio(source, folder / "audio.wav")
        started = time.perf_counter()
        notes = transcribe(folder / "audio.wav", duration)
        if len(notes) > 2000:
            raise HTTPException(422, "识别音符过多，请使用更短或更清晰的独奏录音")
        project = {"id": folder.name, "filename": Path(file.filename or "audio").name,
                   "audio_sha256": hashlib.sha256(content).hexdigest(),
                   "duration": round(duration, 4), "inference_seconds": round(time.perf_counter()-started, 3),
                   "model": "Spotify Basic Pitch 0.4.0 / ONNX CPU", "revision": 0,
                   "notes": notes, "original_notes": notes.copy(), "history": [],
                   "limitations": "琵琶滑音、轮指、泛音及混合伴奏尚未专项验证；MIDI不是排版五线谱。"}
        write_project(folder, project)
        success = True
        return public_project(project)
    finally:
        file.file.close()
        INFERENCE_LOCK.release()
        if not success:
            shutil.rmtree(folder, ignore_errors=True)


@app.get("/api/projects/{session_id}")
def project(session_id: str):
    return public_project(read_project(session_id))


@app.get("/api/projects")
def recent_projects():
    """Metadata only, same trusted single-user service scope as project access."""
    items = []
    for path in DATA.glob("*/project.json"):
        try:
            p = read_project(path.parent.name)
            items.append({"id": p["id"], "filename": p["filename"],
                          "duration": p["duration"], "note_count": len(p["notes"]),
                          "revision": p["revision"], "updated": path.stat().st_mtime})
        except (HTTPException, ValueError, KeyError, OSError):
            continue
    return sorted(items, key=lambda p: p["updated"], reverse=True)[:20]


@app.put("/api/projects/{session_id}/notes")
def edit_notes(session_id: str, edit: Edit):
    with EDIT_LOCK:
        path = session_path(session_id)
        p = read_project(session_id)
        if edit.revision != p["revision"]:
            raise HTTPException(409, "项目已更新，请重新载入后修改")
        ids = [n.id for n in edit.notes]
        if len(set(ids)) != len(ids):
            raise HTTPException(422, "音符编号重复")
        if any(n.end > p["duration"] + 0.001 for n in edit.notes):
            raise HTTPException(422, "音符不能超出原音频时长")
        updated = sorted([n.model_dump() for n in edit.notes], key=lambda n: (n["start"], n["pitch"]))
        old = {n["id"]: n for n in p["notes"]}
        new = {n["id"]: n for n in updated}
        changes = [{"id": id_, "before": old.get(id_), "after": new.get(id_)}
                   for id_ in sorted(old.keys() | new.keys()) if old.get(id_) != new.get(id_)]
        if changes:
            p["revision"] += 1
            p["history"].append({"revision": p["revision"], "timestamp": time.time(), "changes": changes})
            p["notes"] = updated
            write_project(path, p)
        return public_project(p)


@app.get("/api/projects/{session_id}/audio")
def audio(session_id: str):
    return FileResponse(session_path(session_id) / "audio.wav", media_type="audio/wav")


@app.post("/api/projects/{session_id}/reference")
def reference_upload(session_id: str, file: UploadFile):
    try:
        content = file.file.read(1024 * 1024 + 1)
        if len(content) > 1024 * 1024:
            raise HTTPException(413, "参考MIDI超过1MB，请导出短片段")
        try:
            notes = parse_reference(content)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        with EDIT_LOCK:
            path = session_path(session_id)
            p = read_project(session_id)
            before = p.get("reference")
            p["reference"] = {"filename":Path(file.filename or "reference.mid").name,
                              "notes":notes, "settings":Alignment().model_dump()}
            p.setdefault("reference_history", []).append({"timestamp":time.time(), "before":before,
                                                         "after":p["reference"]})
            write_project(path, p)
        return public_project(p)
    finally:
        file.file.close()


@app.post('/api/projects/{session_id}/reference/jianpu')
def reference_numbered(session_id: str,entry: NumberedReference):
    try:notes=parse_jianpu(entry.text,entry.key,entry.octave,entry.bpm)
    except ValueError as exc:raise HTTPException(422,str(exc))
    with EDIT_LOCK:
        path=session_path(session_id);p=read_project(session_id)
        before=p.get('reference')
        p['reference']={'filename':'简谱文字录入','notes':notes,'settings':Alignment().model_dump(),
                        'status':'user_confirmed_reference' if entry.confirmed else 'human_entered_unverified',
                        'source':{'kind':'manual_numbered_notation','entry':entry.model_dump(),
                                  'independent_ground_truth':False,'confirmation':'user declaration only'}}
        p.setdefault('reference_history',[]).append({'timestamp':time.time(),'before':before,'after':p['reference']})
        write_project(path,p)
    return public_project(p)


@app.put('/api/projects/{session_id}/issue-review')
def review_issue(session_id: str,decision: IssueDecision):
    with EDIT_LOCK:
        path=session_path(session_id);p=read_project(session_id)
        if decision.revision!=p['revision']:raise HTTPException(409,'音符结果已更新，请重新载入再核对')
        if not p.get('reference'):raise HTTPException(422,'请先录入或导入参考')
        comparison=compare_reference(p['notes'],p['reference'],p['duration'])
        issue=next((i for i in comparison['issues'] if i['id']==decision.issue_id),None)
        if issue is None:raise HTTPException(409,'差异或对齐已改变，请针对当前差异重新核对')
        before=p.setdefault('issue_reviews',{}).get(decision.issue_id)
        value={**decision.model_dump(),'timestamp':time.time(),'source':'human_listening_decision','issue_snapshot':issue}
        p['issue_reviews'][decision.issue_id]=value
        p.setdefault('issue_review_history',[]).append({'before':before,'after':value})
        write_project(path,p)
    return public_project(p)


@app.get('/api/projects/{session_id}/backup')
def backup_project(session_id: str):
    with EDIT_LOCK:
        try:data=make_backup(session_path(session_id),read_project(session_id))
        except ValueError as exc:raise HTTPException(422,str(exc))
    return Response(data,media_type='application/zip',headers={'Content-Disposition':'attachment; filename="puyigai-project-backup.zip"'})


@app.post('/api/projects/restore')
def restore_project(file: UploadFile):
    import shutil
    folder=None
    success=False
    try:
        content=file.file.read(32*1024*1024+1)
        if len(content)>32*1024*1024:raise HTTPException(413,'备份不能超过32MB')
        p,files=unpack_backup(content)
        if not isinstance(p.get('filename'),str) or not 1<=len(p['filename'])<=255:
            raise ValueError('备份文件名无效')
        if not isinstance(p.get('model'),str) or not isinstance(p.get('inference_seconds'),(int,float)) or not 0<=p['inference_seconds']<=3600:
            raise ValueError('备份模型信息无效')
        if type(p.get('revision')) is not int or not 0<=p['revision']<=100000:
            raise ValueError('备份版本无效')
        for key in ['notes','original_notes']:
            if not isinstance(p.get(key),list) or len(p[key])>2000:raise ValueError('备份音符无效')
            p[key]=[Note.model_validate(n).model_dump() for n in p[key]]
            if len({n['id'] for n in p[key]})!=len(p[key]):raise ValueError('备份音符编号重复')
        if not isinstance(p.get('history'),list) or len(p['history'])>2000:raise ValueError('备份编辑历史无效')
        ref=p.get('reference')
        if ref:
            if not isinstance(ref,dict):raise ValueError('备份参考格式无效')
            if not isinstance(ref.get('notes'),list) or not 1<=len(ref['notes'])<=500:raise ValueError('备份参考无效')
            ref['notes']=[ReferenceNote.model_validate(n).model_dump() for n in ref['notes']]
            ref['settings']=Alignment.model_validate(ref['settings']).model_dump()
            if ref.get('automatic_alignment'):
                ref['automatic_alignment']=auto_align(ref['notes'],p['original_notes'])
        reviews=p.get('issue_reviews',{})
        if not isinstance(reviews,dict) or len(reviews)>3000:raise ValueError('备份核对记录无效')
        for key,value in reviews.items():
            IssueDecision.model_validate({field:value[field] for field in ['revision','issue_id','verdict','comment']})
            if key!=value['issue_id']:raise ValueError('核对记录编号不匹配')
        folder=DATA/str(uuid.uuid4());folder.mkdir()
        stored=folder/'restoring.wav';stored.write_bytes(files['audio.wav'])
        duration=normalize_audio(stored,folder/'audio.wav');stored.unlink()
        if abs(duration-float(p['duration']))>.01:raise ValueError('备份录音时长不匹配')
        if any(n['end']>duration+.001 for key in ['notes','original_notes'] for n in p[key]):raise ValueError('备份音符超出录音')
        if 'source.audio' in files:(folder/'source').write_bytes(files['source.audio'])
        old_id=p.get('id');p['id']=folder.name;p['restored_from']={'id':old_id,'timestamp':time.time(),'verification':'file hashes and structure, not musical correctness'}
        if ref:compare_reference(p['notes'],ref,duration)
        write_project(folder,p)
        success=True
        return public_project(p)
    except (ValueError,KeyError,TypeError) as exc:
        if folder:shutil.rmtree(folder,ignore_errors=True)
        raise HTTPException(422,'备份恢复失败：'+str(exc))
    finally:
        file.file.close()
        if folder and not success:shutil.rmtree(folder,ignore_errors=True)


@app.post('/api/projects/{session_id}/evaluation')
def independent_evaluation(session_id: str,file: UploadFile):
    try:
        content=file.file.read(1024*1024+1)
        if len(content)>1024*1024:raise HTTPException(413,'独立核对记录不能超过1MB')
        review=json.loads(content)
        if not isinstance(review,dict):raise ValueError('核对记录须为JSON对象')
        with EDIT_LOCK:
            path=session_path(session_id);p=read_project(session_id)
            digest=p.get('audio_sha256')
            if not digest or not (path/'source').is_file():raise ValueError('旧项目未保存原始上传来源，请重新上传对应原音生成项目')
            if hashlib.sha256((path/'source').read_bytes()).hexdigest()!=digest:raise ValueError('原始音频来源校验失败')
            scope=review.get('scope')
            if not isinstance(scope,dict) or not isinstance(scope.get('end'),(int,float)) or scope['end']>p['duration']+.001:
                raise ValueError('完整核对范围不能超出原录音')
            result=evaluate_review(p,review,digest)
            result.update(note_revision=p['revision'],timestamp=time.time())
            p['independent_evaluation']=result
            write_project(path,p)
        return result
    except (ValueError,KeyError,TypeError) as exc:raise HTTPException(422,'不能进行独立评测：'+str(exc))
    finally:file.file.close()


@app.put("/api/projects/{session_id}/reference/alignment")
def reference_align(session_id: str, alignment: Alignment):
    with EDIT_LOCK:
        path = session_path(session_id)
        p = read_project(session_id)
        if not p.get("reference"):
            raise HTTPException(422, "请先导入参考MIDI曲谱")
        before = p["reference"]["settings"].copy()
        before_auto = p["reference"].pop("automatic_alignment", None)
        p["reference"]["settings"] = alignment.model_dump()
        p.setdefault("reference_history", []).append({"timestamp":time.time(),
                                                     "before_settings":before,
                                                     "before_automatic_alignment":before_auto,
                                                     "after_settings":alignment.model_dump()})
        write_project(path, p)
    return public_project(p)


@app.post("/api/projects/{session_id}/reference/auto-align")
def reference_auto_align(session_id: str):
    with EDIT_LOCK:
        path = session_path(session_id)
        p = read_project(session_id)
        if not p.get("reference"):
            raise HTTPException(422, "请先导入参考曲谱")
        try:
            automatic = auto_align(p["reference"]["notes"], p["original_notes"])
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        before = p["reference"].get("automatic_alignment")
        p["reference"]["automatic_alignment"] = automatic
        p.setdefault("reference_history", []).append({"timestamp":time.time(),
                                                     "before_automatic_alignment":before,
                                                     "after_automatic_alignment":automatic})
        write_project(path, p)
    return public_project(p)


@app.delete("/api/projects/{session_id}/reference")
def remove_reference(session_id: str):
    with EDIT_LOCK:
        path = session_path(session_id)
        p = read_project(session_id)
        if p.get("reference"):
            p.setdefault("reference_history", []).append({"timestamp":time.time(),
                                                         "before":p.pop("reference"), "after":None})
            write_project(path, p)
    return public_project(p)


@app.get("/api/projects/{session_id}/midi")
def export_midi(session_id: str, original: bool = False):
    p = read_project(session_id)
    midi = pretty_midi.PrettyMIDI(initial_tempo=120)
    instrument = pretty_midi.Instrument(program=0, name="Reviewed notes")
    for n in p["original_notes"] if original else p["notes"]:
        instrument.notes.append(pretty_midi.Note(n["velocity"], n["pitch"], n["start"], n["end"]))
    midi.instruments.append(instrument)
    output = io.BytesIO()
    midi.write(output)
    return Response(output.getvalue(), media_type="audio/midi",
                    headers={"Content-Disposition": 'attachment; filename="pu-yigai.mid"'})


@app.get("/api/projects/{session_id}/report")
def report(session_id: str):
    p = read_project(session_id)
    if p.get("reference"):
        p["practice"] = compare_reference(p["notes"], p["reference"], p["duration"])
        p["original_practice"] = compare_reference(p["original_notes"], p["reference"], p["duration"])
    return Response(json.dumps(p, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="review-record.json"'})


@app.get("/api/projects/{session_id}/musicxml")
def score(session_id: str, bpm: float = Query(120, ge=30, le=240),
          meter: str = "4/4", origin: float = Query(0, ge=0, le=60), original: bool = False, grid: str='sixteenth'):
    p = read_project(session_id)
    try:
        content = export_musicxml(p["original_notes"] if original else p["notes"], bpm, meter, origin,grid=grid)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return Response(content, media_type="application/vnd.recordare.musicxml+xml",
                    headers={"Content-Disposition": 'attachment; filename="pu-yigai-draft.musicxml"'})


@app.delete("/api/projects/{session_id}")
def delete(session_id: str):
    import shutil
    with EDIT_LOCK:
        shutil.rmtree(session_path(session_id))
    return {"deleted": True}
