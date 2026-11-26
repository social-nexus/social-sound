import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
import roteiro


class FakeResponse(io.BytesIO):
    def __init__(self, payload: bytes):
        super().__init__(payload)
        self.headers = {"Content-Length": str(len(payload))}


def test_mark_download_retries_connection_reset_and_completes_atomically(tmp_path, monkeypatch):
    calls = []
    payload = b"model-data"

    def fake_urlopen(url, timeout):
        calls.append((url, timeout))
        if len(calls) == 1:
            raise ConnectionResetError("connection reset by remote host")
        return FakeResponse(payload)

    monkeypatch.setattr(roteiro, "MARK_DIR", tmp_path)
    monkeypatch.setattr(roteiro, "MARK_URLS", {"mark.bin": "https://example.invalid/mark.bin"})
    monkeypatch.setattr(roteiro.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(roteiro.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(roteiro.MARK, "resetar", lambda: None)

    roteiro._baixar()

    assert len(calls) == 2
    assert (tmp_path / "mark.bin").read_bytes() == payload
    assert not (tmp_path / "mark.bin.baixando").exists()
    assert roteiro.DOWNLOAD["erro"] is None
    assert roteiro.DOWNLOAD["baixado"] == len(payload)
    assert roteiro.DOWNLOAD["total"] == len(payload)
    assert roteiro.DOWNLOAD["rodando"] is False


def test_mark_download_removes_partial_file_after_repeated_failures(tmp_path, monkeypatch):
    calls = []

    def fake_urlopen(url, timeout):
        calls.append(url)
        # The first attempt writes some bytes and then fails while reading.
        if len(calls) == 1:
            class BrokenResponse:
                headers = {"Content-Length": "20"}

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return False

                def read(self, _size):
                    if not hasattr(self, "done"):
                        self.done = True
                        return b"partial"
                    raise ConnectionResetError("remote host reset connection")
            return BrokenResponse()
        raise ConnectionResetError("remote host reset connection")

    monkeypatch.setattr(roteiro, "MARK_DIR", tmp_path)
    monkeypatch.setattr(roteiro, "MARK_URLS", {"mark.bin": "https://example.invalid/mark.bin"})
    monkeypatch.setattr(roteiro.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(roteiro.time, "sleep", lambda _seconds: None)

    roteiro._baixar()

    assert len(calls) == 4
    assert not (tmp_path / "mark.bin").exists()
    assert not (tmp_path / "mark.bin.baixando").exists()
    assert roteiro.DOWNLOAD["erro"] is not None
    assert roteiro.DOWNLOAD["rodando"] is False



def test_mark_model_can_be_uninstalled_and_download_state_is_reset(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setattr(roteiro, "MARK_DIR", tmp_path / "mark")
    monkeypatch.setattr(roteiro, "MARK_URLS", {"tags.json": "unused", "mark_int8.onnx": "unused"})
    monkeypatch.setattr(roteiro, "DOWNLOAD_LOCK", __import__("threading").Lock())
    roteiro.MARK_DIR.mkdir()
    (roteiro.MARK_DIR / "tags.json").write_text("{}", encoding="utf-8")
    (roteiro.MARK_DIR / "mark_int8.onnx").write_bytes(b"onnx")
    (roteiro.MARK_DIR / "mark_int8.onnx.baixando").write_bytes(b"partial")
    roteiro.DOWNLOAD.update(rodando=False, baixado=12, total=34, erro="previous error")
    roteiro.MARK.sess = object()
    roteiro.MARK.tags = {"loaded": True}

    app = FastAPI()
    app.include_router(roteiro.router)
    response = TestClient(app).delete("/api/roteiro/modelo")

    assert response.status_code == 200, response.text
    assert response.json()["removed_bytes"] > 0
    assert not roteiro.MARK_DIR.exists()
    assert roteiro.MARK.sess is None
    assert roteiro.MARK.tags is None
    assert roteiro.DOWNLOAD == {"rodando": False, "baixado": 0, "total": 0, "erro": None}


def test_mark_model_uninstall_refuses_while_download_lock_is_held(tmp_path, monkeypatch):
    import threading
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    lock = threading.Lock()
    lock.acquire()
    monkeypatch.setattr(roteiro, "MARK_DIR", tmp_path / "mark")
    monkeypatch.setattr(roteiro, "DOWNLOAD_LOCK", lock)
    app = FastAPI()
    app.include_router(roteiro.router)
    try:
        response = TestClient(app).delete("/api/roteiro/modelo")
        assert response.status_code == 409
    finally:
        lock.release()


def test_mark_validation_accepts_language_specific_diacritics_only():
    assert roteiro.MARK._validar("a", ["à"]) == "à"
    assert roteiro.MARK._validar("e", ["é"]) == "é"
    assert roteiro.MARK._validar("a", ["b"]) == "a"
    assert roteiro.MARK._validar("a", ["áx"]) == "a"
    assert roteiro.MARK._validar("a", ["a"]) == "a"


def test_mark_multilingual_language_id_is_forwarded(monkeypatch):
    import numpy as np

    seen = {}

    class FakeSession:
        def run(self, _outputs, inputs):
            seen["language"] = int(inputs["lang_ids"][0])
            return [np.zeros((1, 512, 2), dtype=np.float32)]

    monkeypatch.setattr(roteiro.MARK, "sess", FakeSession())
    monkeypatch.setattr(roteiro.MARK, "tags", ["KEEP", "M:00E0"])
    predictions, size = roteiro.MARK._previsoes("a", 0.0, "fr")
    assert seen["language"] == roteiro.MARK_LANGS.index("fr")
    assert size == 2
    assert predictions == [0]


def test_mark_unknown_language_falls_back_to_portuguese(monkeypatch):
    calls = []

    def fake_restore(_text, _margin, language):
        calls.append(language)
        return "texto"

    monkeypatch.setattr(roteiro.MARK, "_restaurar", fake_restore)
    assert roteiro.MARK.restaurar("texto", 0.0, "invalid") == "texto"
    assert calls == ["pt"]


def test_humanization_ui_exposes_multilingual_mark_language_selector():
    page = (Path(__file__).resolve().parents[1] / "server" / "roteiro_web" / "index.html").read_text(encoding="utf-8")
    assert 'id="mark-language"' in page
    assert 'id="mark-language-help"' in page
    assert 'id="mark-language-note"' in page
    assert "Portuguese-focused" in page
    assert "Mark does not support English" in page
    assert '<option value="en">English</option>' not in page
    assert 'idioma_mark: $("mark-language").value' in page
    for code in ("pt", "es", "fr", "vi", "ar", "he", "ht", "yo"):
        assert f'<option value="{code}">' in page


def test_mark_language_dropdown_matches_model_supported_languages():
    import re

    page = (Path(__file__).resolve().parents[1] / "server" / "roteiro_web" / "index.html").read_text(encoding="utf-8")
    select = re.search(r'<select id="mark-language"[^>]*>(.*?)</select>', page, re.S)
    assert select
    options = re.findall(r'<option value="([a-z]{2})">', select.group(1))
    assert set(options) == set(roteiro.MARK_LANGS)
    assert len(options) == len(roteiro.MARK_LANGS)
    assert options[0] == "pt"
    assert "en" not in options
