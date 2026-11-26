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
