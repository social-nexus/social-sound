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


def test_voxcpm_queue_generates_parts_and_requires_candidate_approval(tmp_path, monkeypatch):
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
    assert engines["omnivoice"]["installed"] is False
    assert engines["f5tts"]["installed"] is False
    unavailable = client.post("/api/narration/jobs", json={
        "text": "Teste Supertonic.",
        "engine": "supertonic3",
        "voice": "supertonic:M1",
    })
    assert unavailable.status_code == 409
    omni_unavailable = client.post("/api/narration/jobs", json={"text": "Teste OmniVoice.", "engine": "omnivoice", "voice": "omnivoice:auto"})
    assert omni_unavailable.status_code == 409
    f5_unavailable = client.post("/api/narration/jobs", json={"text": "Teste F5.", "engine": "f5tts", "voice": "f5tts:clone"})
    assert f5_unavailable.status_code == 409
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

    # A failed final file replacement must not publish the candidate in SQLite
    # or damage the previously completed narration.
    import narration_api
    full_audio = tmp_path / "audio" / job_id / "completo.wav"
    original_full_audio = full_audio.read_bytes()
    original_replace = narration_api.os.replace

    def fail_published_audio_replace(source, destination):
        if Path(source).name == "completo_aprovacao.tmp.wav" and Path(destination) == full_audio:
            raise OSError("falha simulada ao substituir áudio completo")
        return original_replace(source, destination)

    monkeypatch.setattr(narration_api.os, "replace", fail_published_audio_replace)
    failed_approval = client.post(f"/api/narration/candidates/{candidate['candidate_id']}/approve")
    assert failed_approval.status_code == 500
    after_failure = client.get(f"/api/narration/jobs/{job_id}").json()
    assert after_failure["parts"][0]["audio_path"] == original_path
    assert full_audio.read_bytes() == original_full_audio
    assert client.get(f"/api/narration/jobs/{job_id}/candidates").json()["candidates"][0]["status"] == "awaiting_approval"

    monkeypatch.setattr(narration_api.os, "replace", original_replace)
    # Simulate an older pending sibling from a concurrent/previous regen request.
    from narration_queue import NarrationQueue
    queue_db = NarrationQueue(tmp_path / "data" / "narration_queue.sqlite3")
    sibling_audio = Path(candidate["audio_url"].split("/")[-1])
    sibling_path = Path(tmp_path / "audio" / job_id / "stale_sibling.wav")
    sibling_path.write_bytes(Path(tmp_path / "audio" / job_id / candidate["audio_url"].split("/")[-1]).read_bytes())
    sibling_id = queue_db.stage_candidate(job_id, 0, str(sibling_path))
    approved = client.post(f"/api/narration/candidates/{candidate['candidate_id']}/approve")
    assert approved.status_code == 200
    assert queue_db.candidate(sibling_id)["status"] == "discarded"
    assert not sibling_path.exists()
    assert approved.status_code == 200
    assert approved.json()["parts"][0]["audio_path"] != original_path
    assert Path(tmp_path / "audio" / job_id / "completo.wav").is_file()

    # A filesystem cleanup error after discard should not undo/report failure.
    second_candidate = client.post(f"/api/narration/jobs/{job_id}/parts/1/regenerate")
    assert second_candidate.status_code == 200
    second_id = second_candidate.json()["candidate_id"]
    import pathlib
    original_unlink = pathlib.Path.unlink
    def fail_candidate_cleanup(self, *args, **kwargs):
        if self.name.startswith("candidata_002_"):
            raise OSError("cleanup test failure")
        return original_unlink(self, *args, **kwargs)
    monkeypatch.setattr(pathlib.Path, "unlink", fail_candidate_cleanup)
    discarded = client.post(f"/api/narration/candidates/{second_id}/discard")
    assert discarded.status_code == 200
    assert client.get(f"/api/narration/jobs/{job_id}/candidates").json()["candidates"] == []
    monkeypatch.setattr(pathlib.Path, "unlink", original_unlink)


def test_f5tts_job_reuses_one_worker_and_preserves_completed_parts_on_retry(tmp_path, monkeypatch):
    import json
    import soundfile as sf
    import narration_api

    runtime = tmp_path / "f5-runtime"
    python = runtime / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"fake python")
    (runtime / "Lib" / "site-packages" / "f5_tts").mkdir(parents=True)
    (runtime / "lib" / "python3.11" / "site-packages" / "f5_tts").mkdir(parents=True)
    cache = tmp_path / "hf-cache"
    (cache / "models--Cataldir--F5-TTS-pt-br" / "snapshots" / "model").mkdir(parents=True)
    (cache / "models--charactr--vocos-mel-24khz" / "snapshots" / "vocoder").mkdir(parents=True)
    monkeypatch.setenv("SOCIAL_SOUND_F5TTS_PYTHON", str(python))
    monkeypatch.setenv("HF_HUB_CACHE", str(cache))

    calls = []
    def fake_run(command, **kwargs):
        request = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
        calls.append(request)
        completed = request["parts"] if len(calls) > 1 else request["parts"][:1]
        for item in completed:
            target = Path(item["output"])
            target.parent.mkdir(parents=True, exist_ok=True)
            sf.write(str(target), np.zeros(2400, dtype=np.float32), 24000)
        return SimpleNamespace(returncode=0 if len(calls) > 1 else 1,
                               stderr="" if len(calls) > 1 else "falha simulada",
                               stdout="")

    monkeypatch.setattr(narration_api.subprocess, "run", fake_run)
    data_dir = tmp_path / "data"
    references = data_dir / "narration_references"
    references.mkdir(parents=True)
    reference = references / "reference.wav"
    sf.write(str(reference), np.zeros(2400, dtype=np.float32), 24000)

    app = FastAPI()
    app.include_router(create_narration_router(
        lock=threading.Lock(),
        run=lambda fn: fn(SimpleNamespace(tts_model=SimpleNamespace(sample_rate=24000))),
        synth=lambda *args, **kwargs: np.zeros(2400, dtype=np.float32),
        ensure_preset=lambda *args: reference,
        preset_by_id=lambda pid: {"id": pid},
        find_mine=lambda name: None,
        parse_text=lambda text: [("text", text)],
        split_sentences=lambda text: [text],
        tighten=lambda wav, sample_rate: wav,
        data_dir=data_dir,
        output_dir=tmp_path / "audio",
    ))
    client = TestClient(app)
    response = client.post("/api/narration/jobs", json={
        "text": ("Primeira frase para teste. Segunda frase para teste. "
                 "Terceira frase para teste. Quarta frase para teste."),
        "engine": "f5tts", "voice": "f5tts:clone",
        "reference_audio": str(reference), "reference_text": "Texto de referência.",
        "target_seconds": 15, "chars_per_minute": 300,
    })
    assert response.status_code == 200, response.text
    job_id = response.json()["id"]
    failed = None
    for _ in range(100):
        failed = client.get(f"/api/narration/jobs/{job_id}").json()
        if failed["status"] == "failed":
            break
        time.sleep(0.05)
    assert failed["status"] == "failed"
    assert len(calls) == 1
    assert len(calls[0]["parts"]) == len(failed["parts"])
    completed = [part for part in failed["parts"] if part["status"] == "completed"]
    assert len(completed) == 1
    first_audio = Path(completed[0]["audio_path"])
    # Corrupt a previously completed WAV; retry must validate and regenerate it.
    first_audio.write_bytes(b"broken wav")
    assert client.post(f"/api/narration/jobs/{job_id}/requeue").status_code == 200
    finished = None
    for _ in range(100):
        finished = client.get(f"/api/narration/jobs/{job_id}").json()
        if finished["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)
    assert finished["status"] == "completed", finished.get("error")
    assert len(calls) == 2
    assert len(calls[1]["parts"]) == len(failed["parts"])
    assert first_audio.read_bytes() != b"broken wav"
    assert sf.info(str(first_audio)).frames > 0
    assert all(part["status"] == "completed" for part in finished["parts"])


def test_omnivoice_catalog_uses_explicit_huggingface_hub_cache(tmp_path, monkeypatch):
    runtime = tmp_path / "omni-runtime"
    python = runtime / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"fake python")
    (runtime / "Lib" / "site-packages" / "omnivoice").mkdir(parents=True)
    (runtime / "lib" / "python3.11" / "site-packages" / "omnivoice").mkdir(parents=True)
    cache = tmp_path / "custom-hf-cache"
    (cache / "models--k2-fsa--OmniVoice" / "snapshots" / "model").mkdir(parents=True)
    (cache / "models--bosonai--higgs-audio-v2-tokenizer" / "snapshots" / "tokenizer").mkdir(parents=True)
    monkeypatch.setenv("SOCIAL_SOUND_OMNIVOICE_PYTHON", str(python))
    monkeypatch.setenv("HF_HOME", str(tmp_path / "different-hf-home"))
    monkeypatch.setenv("HF_HUB_CACHE", str(cache))

    app = FastAPI()
    app.include_router(create_narration_router(
        lock=threading.Lock(),
        run=lambda fn: fn(SimpleNamespace(tts_model=SimpleNamespace(sample_rate=24000))),
        synth=lambda *args, **kwargs: np.zeros(2400, dtype=np.float32),
        ensure_preset=lambda *args: tmp_path / "preset.wav",
        preset_by_id=lambda pid: {"id": pid},
        find_mine=lambda name: None,
        parse_text=lambda text: [("text", text)],
        split_sentences=lambda text: [text],
        tighten=lambda wav, sample_rate: wav,
        data_dir=tmp_path / "data",
        output_dir=tmp_path / "audio",
    ))
    engines = {item["id"]: item for item in TestClient(app).get("/api/narration/engines").json()["engines"]}
    assert engines["omnivoice"]["installed"] is True
