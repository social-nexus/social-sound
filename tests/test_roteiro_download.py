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
