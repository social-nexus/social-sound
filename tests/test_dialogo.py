from pathlib import Path
import sys
import time
import threading

from fastapi import FastAPI
from fastapi.testclient import TestClient

SERVER = Path(__file__).resolve().parents[1] / "server"
sys.path.insert(0, str(SERVER))
import dialogo  # noqa: E402


def test_detect_dialogue_speakers_counts_and_preserves_order():
    result = dialogo.detectar_personagens(
        "Maria: Olá!\nJoão: Bom dia.\nMaria: Tudo bem?\n10:30 reunião\nhttp://site"
    )
    assert result == [{"nome": "Maria", "falas": 2}, {"nome": "João", "falas": 1}]


def test_parse_dialogue_uses_known_names_and_tracks_blank_blocks():
    lines = dialogo.parse_roteiro(
        "Narrador: Começou.\nMaria: Oi!\n\nJoão: Tudo certo?\nLinha sem personagem",
        {"narrador", "maria", "joao"},
    )
    assert lines == [
        {"nome": "Narrador", "texto": "Começou.", "par": False},
        {"nome": "Maria", "texto": "Oi!", "par": False},
        {"nome": "João", "texto": "Tudo certo?", "par": True},
        {"nome": None, "texto": "Linha sem personagem", "par": False},
    ]


def test_dialogue_job_cleanup_preserves_running_and_caps_finished_history():
    dialogo.JOBS.clear()
    now = time.time()
    dialogo.JOBS["running"] = {"status": "rodando", "t": now - 5000}
    dialogo.JOBS["old"] = {"status": "pronto", "t": now - 90000}
    dialogo.JOBS["new-a"] = {"status": "pronto", "t": now - 20}
    dialogo.JOBS["new-b"] = {"status": "erro", "t": now - 10}
    dialogo.limpar_jobs(max_finished=1, max_age_seconds=86400)
    assert "running" in dialogo.JOBS
    assert "old" not in dialogo.JOBS
    assert "new-a" not in dialogo.JOBS
    assert "new-b" in dialogo.JOBS
    dialogo.JOBS.clear()


def _client(tmp_path):
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    app = FastAPI()
    model = type("Model", (), {"tts_model": type("TTS", (), {"sample_rate": 24000})()})()
    app.include_router(dialogo.criar_router({
        "lock": threading.Lock(),
        "run": lambda fn: fn(model),
        "synth": lambda *args, **kwargs: None,
        "tighten": lambda wav, sr: wav,
        "make_cues": lambda text, start, end, maximum: [{"text": text, "start": start, "end": end}],
        "parse_text": lambda text, pause=0.0: [("text", text)],
        "split_sentences": lambda text: [text],
        "ensure_preset": lambda *args: outputs / "voice.wav",
        "find_mine": lambda name: None,
        "preset_by_id": lambda name: {"id": name},
        "saidas": outputs,
    }))
    return TestClient(app)


def test_dialogue_api_rejects_oversized_script_and_detection_payload(tmp_path):
    client = _client(tmp_path)
    oversized = "x" * 200001
    assert client.post("/api/dialogo/gerar", json={"texto": oversized}).status_code == 413
    assert client.post("/api/dialogo/detectar", json={"texto": oversized}).status_code == 413
    invalid_options = client.post("/api/dialogo/gerar", json={
        "texto": "Narrador: Olá.",
        "narrador": {"voz": "preset:default"},
        "pausa_falas": "não é número",
    })
    assert invalid_options.status_code == 400


def test_dialogue_frontend_enforces_script_size_and_line_limits():
    ui = SERVER / "dialogo_web" / "index.html"
    source = ui.read_text(encoding="utf-8")
    assert 'maxlength="200000"' in source
    assert "split(/\\r?\\n/)" in source
    assert "2.000 linhas" in source


def test_dialogue_worker_updates_progress_and_finishes_job(tmp_path, monkeypatch):
    import numpy as np

    outputs = tmp_path / "outputs"
    outputs.mkdir()
    jid = "worker-progress-test"
    dialogo.JOBS[jid] = {"status": "rodando", "msg": "Começando...", "atual": 0, "total": 1, "t": time.time()}
    model = type("Model", (), {"tts_model": type("TTS", (), {"sample_rate": 24000})()})()
    ctx = {
        "lock": threading.Lock(),
        "run": lambda fn: fn(model),
        "synth": lambda *args, **kwargs: np.zeros(2400, dtype=np.float32),
        "tighten": lambda wav, sr: wav,
        "make_cues": lambda text, start, end, maximum: [{"text": text, "start": start, "end": end}],
        "parse_text": lambda text, pause=0.0: [("text", text)],
        "split_sentences": lambda text: [text],
        "ensure_preset": lambda *args: outputs / "voice.wav",
        "find_mine": lambda name: None,
        "preset_by_id": lambda name: {"id": name},
        "saidas": outputs,
    }
    falas = [{"nome": None, "texto": "Olá", "par": False}]
    narrador = {"voz": "preset:default", "estilo": ""}
    dialogo._trabalho(ctx, jid, falas, narrador, {}, {
        "pausa_falas": 0.5, "para_pause": 0.8, "max_chars": 42, "nome_na_legenda": True,
    })
    assert dialogo.JOBS[jid]["status"] == "pronto"
    assert dialogo.JOBS[jid]["audio"] == f"/saidas/{jid}.wav"
    assert (outputs / f"{jid}.wav").is_file()
    assert not list(outputs.glob(f".{jid}.*.tmp.wav"))
    assert "Carregando o modelo" not in dialogo.JOBS[jid]["msg"]
    dialogo.JOBS.pop(jid, None)

    # A subtitle-conversion failure must not leave an apparently published WAV.
    failed_jid = "worker-subtitle-failure"
    dialogo.JOBS[failed_jid] = {"status": "rodando", "msg": "Começando...", "atual": 0, "total": 1, "t": time.time()}
    monkeypatch.setattr(dialogo, "montar_srt", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("falha SRT simulada")))
    dialogo._trabalho(ctx, failed_jid, falas, narrador, {}, {
        "pausa_falas": 0.5, "para_pause": 0.8, "max_chars": 42, "nome_na_legenda": True,
    })
    assert dialogo.JOBS[failed_jid]["status"] == "erro"
    assert not (outputs / f"{failed_jid}.wav").exists()
    dialogo.JOBS.pop(failed_jid, None)
