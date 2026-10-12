import json
import numpy as np
import soundfile as sf
from scripts.batch_evaluate import run


def test_batch_runs_real_model_and_keeps_failed_samples(tmp_path):
    audio = tmp_path / "synthetic-A4.wav"
    rate = 22050
    sf.write(audio, .25*np.sin(2*np.pi*440*np.arange(rate*2)/rate), rate)
    gold = tmp_path / "gold.csv"
    gold.write_text("pitch,start,end\n69,0,2\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "dataset":"synthetic-functional-test-not-GuitarSet",
        "purpose":"automated pipeline verification only",
        "selected_ids":["known-A4","missing-file"],
        "accepted":[{"id":"known-A4","audio":str(audio),"gold":str(gold)},
                    {"id":"missing-file","audio":str(tmp_path/'missing.wav'),"gold":str(gold)}],
        "rejected":[],
    }), encoding="utf-8")
    result = run(manifest, tmp_path / "output")
    assert result["status"] == "incomplete"
    assert result["counts"] == {"selected":2,"evaluated":1,"failed":1,"annotation_rejected":0}
    assert result["results"][0]["scores"]["onset_only"]["f1"] == 1
    assert result["failures"][0]["id"] == "missing-file"
    saved = json.loads((tmp_path / "output/results.json").read_text())
    assert saved["source_dataset"] == "synthetic-functional-test-not-GuitarSet"
    assert saved["failures"]
