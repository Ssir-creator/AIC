"""Real inference, editing, MIDI parsing, persistence and invalid-input checks."""
import io
import json

import numpy as np
import pretty_midi
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA", tmp_path)
    with TestClient(app.app) as client:
        yield client


def wav_bytes(audio, rate=22050):
    output = io.BytesIO()
    sf.write(output, audio, rate, format="WAV")
    return output.getvalue()


@pytest.fixture
def project(client):
    # Synthetic known-pitch test signal, not a real piano/pipa evaluation dataset.
    rate = 22050
    t = np.arange(rate * 2) / rate
    audio = .25 * np.sin(2 * np.pi * 440 * t) * np.minimum(t * 30, 1)
    response = client.post("/api/transcribe", files={"file": ("known-A4.wav", wav_bytes(audio), "audio/wav")})
    assert response.status_code == 200, response.text
    p = response.json()
    assert any(n["pitch"] == 69 for n in p["notes"]), "Actual model failed to detect A4"
    assert p["original_notes"]
    return p


def test_real_inference_edit_export_restore_delete(client, project):
    p = project
    base = "/api/projects/" + p["id"]
    original = client.get(base + "/midi?original=true").content
    assert client.get(base + "/audio").content[:4] == b"RIFF"
    notes = [{k: n[k] for k in ("id", "pitch", "start", "end", "velocity")} for n in p["notes"]]
    notes[0]["pitch"] = 70
    changed = client.put(base + "/notes", json={"revision": 0, "notes": notes})
    assert changed.status_code == 200
    assert changed.json()["revision"] == 1
    assert changed.json()["history"][0]["changes"][0]["before"]["pitch"] != 70
    restored = client.get(base).json()
    assert restored["notes"][0]["pitch"] == 70
    midi = pretty_midi.PrettyMIDI(io.BytesIO(client.get(base + "/midi").content))
    assert midi.instruments[0].notes[0].pitch == 70
    assert client.get(base + "/midi?original=true").content == original
    import xml.etree.ElementTree as ET
    score = client.get(base + "/musicxml?bpm=90&meter=3/4")
    assert score.status_code == 200
    root = ET.fromstring(score.content)
    assert root.findtext(".//time/beats") == "3"
    assert root.find(".//sound").get("tempo") == "90.0"
    assert client.get(base + "/musicxml?meter=7/7").status_code == 422
    assert client.get(base + "/musicxml?bpm=nan").status_code == 422
    report = json.loads(client.get(base + "/report").content)
    assert report["original_notes"] == p["original_notes"]
    assert report["notes"][0]["pitch"] == 70
    assert client.put(base + "/notes", json={"revision": 0, "notes": notes}).status_code == 409
    assert client.delete(base).status_code == 200
    assert client.get(base).status_code == 404


def test_recent_projects_reflect_edits_and_deletion_without_audio_payload(client, project):
    p = project
    items = client.get('/api/projects').json()
    assert len(items) == 1 and items[0]['id'] == p['id']
    assert items[0]['note_count'] == len(p['notes'])
    assert 'notes' not in items[0] and 'audio_sha256' not in items[0]
    notes = [{k: n[k] for k in ('id','pitch','start','end','velocity')} for n in p['notes']]
    notes[0]['pitch'] += 1
    assert client.put('/api/projects/'+p['id']+'/notes',json={'revision':0,'notes':notes}).status_code == 200
    assert client.get('/api/projects').json()[0]['revision'] == 1
    assert client.delete('/api/projects/'+p['id']).status_code == 200
    assert client.get('/api/projects').json() == []


@pytest.mark.parametrize("changes", [
    {"start": 1, "end": .5}, {"end": 3}, {"pitch": 200},
    {"velocity": 0}, {"start": -1}, {"id": "../../escape"},
])
def test_invalid_edits_rejected(client, project, changes):
    n = {k: project["notes"][0][k] for k in ("id", "pitch", "start", "end", "velocity")}
    n.update(changes)
    assert client.put("/api/projects/" + project["id"] + "/notes", json={"revision": 0, "notes": [n]}).status_code == 422


def test_duplicate_ids_rejected(client, project):
    n = {k: project["notes"][0][k] for k in ("id", "pitch", "start", "end", "velocity")}
    assert client.put("/api/projects/" + project["id"] + "/notes", json={"revision": 0, "notes": [n,n]}).status_code == 422


@pytest.mark.parametrize("data", [b"not an audio file", wav_bytes(np.zeros(22050)), wav_bytes(np.ones(100))])
def test_invalid_audio_rejected_and_removed(client, data):
    assert client.post("/api/transcribe", files={"file": ("invalid.wav", data)}).status_code == 422
    assert not list(app.DATA.iterdir())


def test_long_audio_rejected(client):
    signal = np.sin(np.arange(22050*61) * .1) * .2
    assert client.post("/api/transcribe", files={"file": ("long.wav", wav_bytes(signal))}).status_code == 422
    assert not list(app.DATA.iterdir())


def test_busy_model_rejected(client):
    app.INFERENCE_LOCK.acquire()
    try:
        assert client.post("/api/transcribe", files={"file": ("a.wav", b"bad")}).status_code == 429
    finally:
        app.INFERENCE_LOCK.release()


def test_optional_private_demo_discovery(client, project):
    assert client.get("/api/practice-demo").status_code == 404
    (app.DATA / "demo-project-id.json").write_text(json.dumps({"id":project["id"]}))
    response = client.get("/api/practice-demo")
    assert response.status_code == 200
    assert response.json()["original_notes"] == project["original_notes"]
    assert response.json()["revision"] == 0


def test_oversized_upload_rejected(client):
    assert client.post("/api/transcribe", files={"file": ("big.wav", b"0" * (app.MAX_BYTES+1))}).status_code == 413
    assert not list(app.DATA.iterdir())
