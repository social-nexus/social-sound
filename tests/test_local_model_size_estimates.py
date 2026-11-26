from pathlib import Path
import sys

SERVER = Path(__file__).resolve().parents[1] / "server"
sys.path.insert(0, str(SERVER))
import ia_local  # noqa: E402

APP_JS = SERVER / "ai_web" / "app.js"


def test_local_model_catalog_shows_qwen_and_gemma_download_sizes():
    catalog = ia_local.MODEL_CATALOG
    qwen = catalog["qwen3-4b-q4km"]
    gemma = catalog["gemma3-4b-it-q4km"]
    assert qwen["download_estimate"] == "2,50 GB (GGUF Q4_K_M)"
    assert gemma["download_estimate"] == "2,49 GB (GGUF Q4_K_M)"
    assert qwen["disk_estimate"] and gemma["disk_estimate"]


def test_local_ai_ui_renders_download_and_disk_estimates():
    source = APP_JS.read_text(encoding="utf-8")
    assert "Peso estimado do arquivo:" in source
    assert "Espaço livre recomendado:" in source
    assert "m.download_estimate" in source
    assert "m.disk_estimate" in source
