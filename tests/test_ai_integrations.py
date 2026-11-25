import asyncio
import os
import sys
import tempfile
import pytest
from pathlib import Path
from unittest.mock import AsyncMock

from starlette.requests import Request

TEST_ROOT = tempfile.mkdtemp(prefix="social-sound-ai-tests-")
os.environ["SOCIAL_SOUND_DATA"] = TEST_ROOT
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

import ai_providers
import ia_local


def local_request(method="POST", origin="http://localhost:8000", host="localhost:8000", fetch_site="same-origin"):
    headers = [(b"host", host.encode())]
    if origin:
        headers.append((b"origin", origin.encode()))
    if fetch_site:
        headers.append((b"sec-fetch-site", fetch_site.encode()))
    return Request({"type": "http", "method": method, "headers": headers})


def test_shared_local_cors_allowlist_is_exact():
    from security_config import LOCAL_HOSTS, LOCAL_ORIGINS
    assert LOCAL_HOSTS == {"localhost:8000", "127.0.0.1:8000"}
    assert LOCAL_ORIGINS == {"http://localhost:8000", "http://127.0.0.1:8000"}


def test_cloud_provider_catalog_has_expected_services():
    expected = {"openai", "anthropic", "gemini", "openrouter", "deepseek", "groq", "mistral"}
    assert expected.issubset(ai_providers.PROVIDERS)


def test_ai_provider_guard_rejects_external_origin():
    with pytest.raises(ai_providers.HTTPException):
        ai_providers._guard(local_request(origin="https://attacker.example"))


def test_ai_provider_guard_accepts_local_same_origin():
    ai_providers._guard(local_request())


def test_local_ai_guard_rejects_external_origin():
    with pytest.raises(ia_local.HTTPException):
        ia_local._guard_local_request(local_request(origin="https://attacker.example"))


def test_local_ai_guard_rejects_untrusted_host():
    with pytest.raises(ia_local.HTTPException):
        ia_local._guard_local_request(local_request(host="attacker.example"))


def test_local_ai_guard_requires_origin_for_mutating_request():
    with pytest.raises(ia_local.HTTPException):
        ia_local._guard_local_request(local_request(origin=None))


def test_config_stores_provider_preferences_without_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_providers, "CONFIG_PATH", tmp_path / "provider-config.json")
    ai_providers._write_config({"provider": "openai", "models": {"openai": "gpt-4.1-mini"}})
    raw = ai_providers.CONFIG_PATH.read_text(encoding="utf-8")
    assert "api_key" not in raw.lower()
    assert "secret" not in raw.lower()
    assert ai_providers._read_config()["provider"] == "openai"


def test_provider_validation_rejects_unknown_provider():
    with pytest.raises(ValueError):
        ai_providers._validate_provider("not-a-provider")


def test_api_key_storage_uses_os_credential_service(monkeypatch):
    monkeypatch.setattr(ai_providers, "_keyring_ready", lambda: True)
    saved = []
    monkeypatch.setattr(ai_providers.keyring, "set_password", lambda service, username, secret: saved.append((service, username, secret)))
    ai_providers._set_key("openai", "test-key-value")
    assert saved == [("SocialSound", "openai", "test-key-value")]


def test_llama_runtime_args_disable_web_ui_and_restrict_cors(tmp_path):
    args = ia_local._runtime_args(Path("llama-server"), tmp_path / "model.gguf", 12)
    assert args[args.index("--host") + 1] == "127.0.0.1"
    assert "--no-webui" in args
    assert args[args.index("--cors-origins") + 1] == "localhost"
    assert args[args.index("--n-gpu-layers") + 1] == "12"


def test_runtime_catalog_urls_and_hashes_are_pinned():
    assert ia_local.RUNTIME_CATALOG
    for runtime in ia_local.RUNTIME_CATALOG.values():
        assert runtime["url"].startswith("https://github.com/ggml-org/llama.cpp/")
        assert len(runtime["sha256"]) == 64
        assert runtime["size"] > 1_000_000
        for extra in runtime.get("extras", []):
            assert extra["url"].startswith("https://github.com/ggml-org/llama.cpp/")
            assert len(extra["sha256"]) == 64
            assert extra["size"] > 1_000_000


def test_sha256_normalization():
    digest = "a" * 64
    assert ia_local._normalize_sha256(digest) == digest
    assert ia_local._normalize_sha256("sha256:" + digest) == digest
    with pytest.raises(ValueError):
        ia_local._normalize_sha256("invalid")


def test_archive_path_rejects_traversal(tmp_path):
    with pytest.raises(ValueError):
        ia_local._safe_member_path(tmp_path, "../outside")
    with pytest.raises(ValueError):
        ia_local._safe_member_path(tmp_path, "/absolute/file")


def test_models_directory_override(monkeypatch, tmp_path):
    shared = tmp_path / "shared-models"
    monkeypatch.delenv("SOCIAL_NEXUS_MODELS_DIR", raising=False)
    monkeypatch.setenv("SOCIAL_SOUND_MODELS_DIR", str(shared))
    assert ia_local.models_dir() == shared


def test_global_social_nexus_models_directory_uses_llm_subfolder(monkeypatch, tmp_path):
    root = tmp_path / "IA_MODELS"
    monkeypatch.setenv("SOCIAL_NEXUS_MODELS_DIR", str(root))
    monkeypatch.setenv("SOCIAL_SOUND_MODELS_DIR", str(tmp_path / "legacy-models"))
    assert ia_local.models_dir() == root / "LLM"


def test_tts_engine_catalog_separates_commercial_and_noncommercial_weights():
    from tts_engine_catalog import ENGINES
    by_id = {engine["id"]: engine for engine in ENGINES}
    assert by_id["voxcpm2"]["commercial_use"] is True
    assert by_id["supertonic3"]["weights_license"] == "OpenRAIL-M"
    assert by_id["omnivoice"]["commercial_use"] is False
    assert by_id["omnivoice"]["weights_license"] == "CC-BY-NC"
    assert by_id["f5tts"]["commercial_use"] is False
    assert by_id["f5tts"]["weights_license"] == "CC-BY-NC-4.0"
    assert by_id["voxcpm2"]["installed"] is True
    assert all(not by_id[name]["installed"] for name in ("supertonic3", "omnivoice", "f5tts"))


def test_omnivoice_catalog_is_optional_and_noncommercial():
    from tts_engine_catalog import public_catalog
    items = {item["id"]: item for item in public_catalog()}
    assert items["omnivoice"]["installed"] is False
    assert items["omnivoice"]["commercial_use"] is False
    assert items["omnivoice"]["weights_license"] == "CC-BY-NC"
    installed = {item["id"]: item for item in public_catalog(omnivoice_installed=True)}
    assert installed["omnivoice"]["installed"] is True


def test_f5tts_catalog_uses_ptbr_checkpoint_and_noncommercial_license():
    from tts_engine_catalog import ENGINES, public_catalog
    item = next(engine for engine in ENGINES if engine["id"] == "f5tts")
    assert item["model"] == "Cataldir/F5-TTS-pt-br"
    assert item["weights_license"] == "CC-BY-NC-4.0"
    assert item["commercial_use"] is False
    assert next(engine for engine in public_catalog() if engine["id"] == "f5tts")["installed"] is False
    assert next(engine for engine in public_catalog(f5tts_installed=True) if engine["id"] == "f5tts")["installed"] is True


def test_local_model_catalog_includes_qwen_and_license_flag_for_gemma():
    qwen = ia_local.MODEL_CATALOG["qwen3-4b-q4km"]
    gemma = ia_local.MODEL_CATALOG["gemma3-4b-it-q4km"]
    assert qwen["repo"] == "Qwen/Qwen3-4B-GGUF"
    assert qwen["license"] == "Apache-2.0"
    assert not qwen["requires_license_acceptance"]
    assert gemma["requires_license_acceptance"] is True


def test_generic_cloud_generation_works_without_local_runtime(monkeypatch):
    async def run_test():
        monkeypatch.setattr(ia_local, "generate_with_provider", AsyncMock(return_value="Roteiro teste"))
        payload = {"provider": "openai", "provider_model": "gpt-4.1-mini", "system_prompt": "Escreva.", "prompt": "Crie um texto."}
        result = await ia_local.generate_text(payload, local_request())
        assert result["provider"] == "openai"
        assert result["text"] == "Roteiro teste"
        ia_local.generate_with_provider.assert_awaited_once()
    asyncio.run(run_test())



def test_f5tts_worker_resolves_custom_huggingface_uris_before_loading(monkeypatch, tmp_path):
    import importlib.util
    import numpy as np
    import types

    resolved = []
    loaded = {}
    def fake_cached_path(uri, cache_dir=None):
        resolved.append((uri, cache_dir))
        target = tmp_path / Path(uri).name
        target.write_bytes(b"model-file")
        return target

    class FakeF5TTS:
        def __init__(self, **kwargs):
            loaded.update(kwargs)

    fake_torch = types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: False))
    fake_cached = types.ModuleType("cached_path")
    fake_cached.cached_path = fake_cached_path
    fake_api = types.ModuleType("f5_tts.api")
    fake_api.F5TTS = FakeF5TTS
    fake_package = types.ModuleType("f5_tts")
    fake_package.__path__ = []

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "cached_path", fake_cached)
    monkeypatch.setitem(sys.modules, "f5_tts", fake_package)
    monkeypatch.setitem(sys.modules, "f5_tts.api", fake_api)
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hub-cache"))

    worker_path = Path(__file__).resolve().parents[1] / "server" / "tts_engines" / "f5tts_worker.py"
    spec = importlib.util.spec_from_file_location("f5tts_worker_test", worker_path)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)

    model = worker.load()
    assert isinstance(model, FakeF5TTS)
    assert [item[0] for item in resolved] == [worker.CHECKPOINT, worker.VOCAB]
    assert all(item[1] == str(tmp_path / "hub-cache") for item in resolved)
    assert Path(loaded["ckpt_file"]).is_file()
    assert Path(loaded["vocab_file"]).is_file()
    assert loaded["device"] == "cpu"

    import soundfile as sf
    reference = tmp_path / "reference.wav"
    sf.write(str(reference), np.zeros(2400, dtype=np.float32), 24000)
    normalized = worker.prepare_reference_audio(reference)
    try:
        audio, sample_rate = sf.read(str(normalized))
        assert sample_rate == 24000
        assert audio.size == 2400
    finally:
        normalized.unlink(missing_ok=True)



def test_f5_installer_pins_torchcodec_to_pytorch_28_compatible_release():
    installer = (Path(__file__).resolve().parents[1] / "instalar-f5tts.bat").read_text(encoding="utf-8")
    torch_install = installer.index('"torch==2.8.0" "torchaudio==2.8.0"')
    codec_install = installer.index('"torchcodec==0.7.0"')
    f5_install = installer.index('"f5-tts==1.1.22"')
    assert torch_install < codec_install < f5_install
    assert "assert m.version('torchcodec') == '0.7.0'" in installer
    assert "assert torch.__version__.startswith('2.8.0')" in installer


def test_local_runtime_stop_waits_for_lifecycle_lock(monkeypatch):
    import threading
    import time

    monkeypatch.setattr(ia_local, "PROCESS", None)
    finished = threading.Event()
    ia_local.RUNTIME_LIFECYCLE_LOCK.acquire()
    try:
        worker = threading.Thread(target=lambda: (ia_local._stop_runtime(), finished.set()))
        worker.start()
        time.sleep(0.05)
        assert not finished.is_set(), "Runtime stop should serialize with lifecycle operations"
    finally:
        ia_local.RUNTIME_LIFECYCLE_LOCK.release()
    worker.join(timeout=2)
    assert finished.is_set()


def test_duplicate_model_download_jobs_serialize_and_reuse_verified_file(monkeypatch, tmp_path):
    import hashlib
    import threading

    model_id = "qwen3-4b-q4km"
    payload = b"verified-model-fixture"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(ia_local, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(ia_local, "_hf_file_digest", lambda repo, filename: (digest, len(payload)))
    download_calls = []
    calls_lock = threading.Lock()

    def fake_download(url, target, size, job_id):
        with calls_lock:
            download_calls.append(job_id)
        target.write_bytes(payload)

    monkeypatch.setattr(ia_local, "_download", fake_download)
    jobs = [ia_local._job("model"), ia_local._job("model")]
    threads = [threading.Thread(target=ia_local._download_model_worker, args=(jid, model_id)) for jid in jobs]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)
    assert all(not thread.is_alive() for thread in threads)
    assert len(download_calls) == 1
    assert all(ia_local.JOBS[jid]["status"] == "done" for jid in jobs)
