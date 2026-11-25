import sys
import time
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from narration_api import create_narration_router


def test_voxcpm_queue_generates_parts_and_requires_candidate_approval(tmp_path):
    model = SimpleNamespace(tts_model=SimpleNamespace(sample_rate=24000))

    def fake_run(fn):
        return fn(model)

    def fake_synth(model, text, style="", ref=None, transcript=None):
        # Distinct deterministic samples make the generated WAV non-empty.
        return np.full(2400, min(len(text) / 100, 0.8), dtype=np.float32)

    app = FastAPI()
    app.include_router(create_narration_router(
        lock=threading.Lock(),
        run=fake_run,
        synth=fake_synth,
        ensure_preset=lambda model, preset: tmp_path / "preset.wav",
        preset_by_id=lambda pid: {"id": pid},
        find_mine=lambda name: None,
        parse_text=lambda text: [("text", text)],
        split_sentences=lambda text: [text],
        tighten=lambda wav, sample_rate: wav,
        data_dir=tmp_path / "data",
        output_dir=tmp_path / "audio",
    ))
    client = TestClient(app)
    catalogue = client.get("/api/narration/engines")
    assert catalogue.status_code == 200
    assert len(catalogue.json()["engines"]) == 4
    engines = {item["id"]: item for item in catalogue.json()["engines"]}
    assert engines["voxcpm2"]["installed"] is True
    assert engines["supertonic3"]["installed"] is False
    unavailable = client.post("/api/narration/jobs", json={
        "text": "Teste Supertonic.",
        "engine": "supertonic3",
        "voice": "supertonic:M1",
    })
    assert unavailable.status_code == 409
    text = "Esta é uma frase de teste para a narração. " * 12

    paused = client.post("/api/narration/queue/pause")
    assert paused.status_code == 200
    assert client.get("/api/narration/queue/status").json()["paused"] is True

    created = client.post("/api/narration/jobs", json={
        "text": text,
        "voice": "preset:narrador-grave",
        "target_seconds": 15,
        "chars_per_minute": 300,
    })
    assert created.status_code == 200
    job_id = created.json()["id"]

    second = client.post("/api/narration/jobs", json={
        "text": text,
        "voice": "preset:narrador-grave",
        "target_seconds": 15,
        "chars_per_minute": 300,
    })
    assert second.status_code == 200
    second_id = second.json()["id"]
    assert client.post(f"/api/narration/jobs/{second_id}/move-up").status_code == 200
    ordered = client.get("/api/narration/jobs").json()["jobs"]
    queued_ids = [item["id"] for item in ordered if item["status"] == "queued"]
    assert queued_ids[:2] == [second_id, job_id]
    assert client.delete(f"/api/narration/jobs/{second_id}").status_code == 200
    resumed = client.post("/api/narration/queue/resume")
    assert resumed.status_code == 200
    assert client.get("/api/narration/queue/status").json()["paused"] is False

    finished = None
    for _ in range(100):
        response = client.get(f"/api/narration/jobs/{job_id}")
        assert response.status_code == 200
        finished = response.json()
        if finished["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)

    assert finished["status"] == "completed", finished.get("error")
    assert len(finished["parts"]) > 1
    original_path = finished["parts"][0]["audio_path"]
    assert Path(original_path).is_file()
    assert Path(tmp_path / "audio" / job_id / "completo.wav").is_file()

    regenerated = client.post(f"/api/narration/jobs/{job_id}/parts/0/regenerate")
    assert regenerated.status_code == 200
    candidate = regenerated.json()
    restored = client.get(f"/api/narration/jobs/{job_id}/candidates")
    assert restored.status_code == 200
    assert restored.json()["candidates"][0]["id"] == candidate["candidate_id"]
    duplicate = client.post(f"/api/narration/jobs/{job_id}/parts/0/regenerate")
    assert duplicate.status_code == 409
    still_original = client.get(f"/api/narration/jobs/{job_id}").json()
    assert still_original["parts"][0]["audio_path"] == original_path

    approved = client.post(f"/api/narration/candidates/{candidate['candidate_id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["parts"][0]["audio_path"] != original_path
    assert Path(tmp_path / "audio" / job_id / "completo.wav").is_file()
