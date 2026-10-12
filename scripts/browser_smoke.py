"""Browser workflow verification; requires Playwright and a running server.

Use a temporary synthetic WAV, never label this as a real musician trial.
"""
import argparse
import json
import math
import struct
import tempfile
import wave
import xml.etree.ElementTree as ET
from pathlib import Path

from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:8000")
parser.add_argument("--chromium", default="/usr/bin/chromium")
parser.add_argument("--output", default="artifacts/browser-smoke")
args = parser.parse_args()
output = Path(args.output)
output.mkdir(parents=True, exist_ok=True)

with tempfile.TemporaryDirectory() as folder:
    source = Path(folder) / "synthetic-A4.wav"
    with wave.open(str(source), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(22050)
        f.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2*math.pi*440*i/22050))) for i in range(44100)))
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.chromium, headless=True,
                                   args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(args.base_url)
        page.locator("#file").set_input_files(str(source))
        page.locator("#upload-button").click()
        page.wait_for_selector("#workspace:not([hidden])", timeout=90000)
        assert int(page.locator("#note-count").inner_text()) > 0
        page.locator("#notes-body tr.selectable").first.click()
        page.locator("#pitch").fill("70")
        page.locator("#save-note").click()
        page.wait_for_function("document.querySelector('#revision').textContent === 'v1'")
        assert page.locator("#notes-body").inner_text().find("A♯4") >= 0
        page.locator("#undo").click()
        page.wait_for_function("document.querySelector('#revision').textContent === 'v2'")
        page.locator("#add-note").click()
        page.locator("#pitch").fill("72")
        page.locator("#start").fill("0.2")
        page.locator("#end").fill("0.4")
        page.locator("#save-note").click()
        page.wait_for_function("document.querySelector('#revision').textContent === 'v3'")
        page.locator("#delete-note").click()
        page.wait_for_function("document.querySelector('#revision').textContent === 'v4'")
        with page.expect_download() as download:
            page.locator("#export-midi").click()
        download.value.save_as(str(output / "browser-export.mid"))
        assert (output / "browser-export.mid").read_bytes()[:4] == b"MThd"
        with page.expect_download() as download:
            page.locator("#export-report").click()
        download.value.save_as(str(output / "browser-report.json"))
        report = json.loads((output / "browser-report.json").read_text(encoding="utf-8"))
        assert len(report["history"]) == 4
        # A deliberately changed synthetic reference tests UI differences;
        # it is not a real pipa score or a musician trial.
        def vlq(value):
            parts = [value & 127]
            while value >> 7:
                value >>= 7
                parts.insert(0, (value & 127) | 128)
            return bytes(parts)
        note = report["notes"][0]
        start = round(note["start"] * 960)
        length = max(1, round((note["end"]-note["start"]) * 960))
        track = b'\x00\xff\x51\x03\x07\xa1\x20' + vlq(start) + bytes([0x90,note["pitch"]+1,80])
        track += vlq(length) + bytes([0x80,note["pitch"]+1,0]) + b'\x00\xff\x2f\x00'
        reference = Path(folder) / "synthetic-reference.mid"
        reference.write_bytes(b'MThd' + struct.pack('>IHHH',6,0,1,480) + b'MTrk' + struct.pack('>I',len(track)) + track)
        page.locator('[data-tab="reference"]').click()
        page.locator("#reference-file").set_input_files(str(reference))
        page.locator("#reference-upload").click()
        page.wait_for_selector("#reference-workspace:not([hidden])")
        assert "音高差异 1" in page.locator("#practice-summary").inner_text()
        assert page.locator("#revision").inner_text() == "v4"
        page.locator("#practice-body button").first.click()
        assert int(page.locator("#pitch").input_value()) == note["pitch"]
        page.locator("#alignment-advanced summary").click()
        page.locator("#reference-scale").fill("0.9")
        page.locator("#reference-shift").fill("0.1")
        page.locator("#alignment-form button[type=submit]").click()
        page.wait_for_function("document.querySelector('#practice-summary').textContent.includes('起音差异 1')")
        with page.expect_download() as download:
            page.locator("#export-report").click()
        download.value.save_as(str(output / "browser-practice-report.json"))
        practice_report = json.loads((output / "browser-practice-report.json").read_text())
        assert practice_report["reference"]["settings"]["shift"] == .1
        assert practice_report["original_notes"] == report["original_notes"]
        assert page.locator('#timeline rect[stroke="#8872ae"]').count() == 1
        page.evaluate("document.querySelector('#original-audio').currentTime = 0.2")
        page.locator("#align-first-note").click()
        expected_shift = .2 - note["start"]*.9
        page.wait_for_function("Math.abs(Number(document.querySelector('#reference-shift').value) - .1) > .01")
        assert abs(float(page.locator("#reference-shift").input_value()) - expected_shift) < .003
        page.locator('[data-tab="score"]').click()
        page.locator("#score-bpm").fill("90")
        page.locator("#score-meter").select_option("3/4")
        with page.expect_download() as download:
            page.locator("#export-score").click()
        download.value.save_as(str(output / "browser-draft.musicxml"))
        score = ET.parse(output / "browser-draft.musicxml")
        assert score.findtext(".//time/beats") == "3"
        assert score.find(".//sound").get("tempo") == "90.0"
        page.locator('#preview-score').click()
        page.wait_for_selector('#score-preview svg',timeout=30000)
        assert '90 BPM' in page.locator('#score-preview-status').inner_text()
        page.locator('#score-bpm').fill('100')
        assert page.locator('#score-preview').is_hidden()
        page.locator("#play-synth").click()
        page.locator("#stop-synth").click()
        page.reload()
        page.wait_for_selector("#workspace:not([hidden])")
        assert page.locator("#revision").inner_text() == "v4"
        page.locator('[data-tab="reference"]').click()
        assert "音高差异 1" in page.locator("#practice-summary").inner_text()
        page.screenshot(path=str(output / "desktop.png"), full_page=True)
        page.set_viewport_size({"width":390,"height":844})
        page.screenshot(path=str(output / "mobile.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.on("dialog", lambda dialog: dialog.accept())
        page.locator('.provenance summary').click()
        page.locator("#delete-project").click()
        page.wait_for_function("document.querySelector('#workspace').hidden")
        assert not errors, errors
        browser.close()
        result = {"status":"passed", "source":"synthetic-A4, not real pipa", "js_errors":errors,
                  "verified":["upload and actual inference","edit","undo","add","delete note", "MIDI download", "reference MIDI upload", "reference difference navigation", "alignment update", "reference history export and persistence", "MusicXML download with selected tempo/meter", "history download", "audio synthesis invocation", "reload persistence", "mobile layout", "delete project"]}
        (output / "result.json").write_text(json.dumps(result,indent=2), encoding="utf-8")
        print(json.dumps(result,indent=2))
