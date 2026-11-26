from pathlib import Path
import sys
import time

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


def test_dialogue_job_cleanup_preserves_running_and_caps_finished_history(monkeypatch):
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
