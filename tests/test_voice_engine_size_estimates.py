from pathlib import Path
import sys

SERVER = Path(__file__).resolve().parents[1] / "server"
sys.path.insert(0, str(SERVER))
from tts_engine_catalog import ENGINES  # noqa: E402

APP_JS = SERVER / "narracoes" / "app.js"


def test_optional_voice_engine_catalog_has_download_and_disk_estimates():
    engines = {item["id"]: item for item in ENGINES}
    for engine_id in ("supertonic3", "omnivoice", "f5tts"):
        engine = engines[engine_id]
        assert engine["download_estimate"]
        assert engine["disk_estimate"]
        assert engine["size_notes"]


def test_voice_engine_cards_display_size_estimates():
    source = APP_JS.read_text(encoding="utf-8")
    assert "Download estimado:" in source
    assert "Espaço recomendado:" in source
    assert "esc(T(e.download_estimate))" in source
    assert "esc(T(e.disk_estimate))" in source


def test_main_installer_does_not_install_llama_cpp_runtime():
    installer = (SERVER.parent / "instalar.bat").read_text(encoding="utf-8")
    assert "llama.cpp" not in installer.lower()
    assert "llama-cpp-python" not in installer.lower()
