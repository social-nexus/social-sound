import asyncio
import os
import sys
import tempfile
import time
import httpx
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
    assert by_id["omnivoice"]["tokenizer_url"] == "https://huggingface.co/bosonai/higgs-audio-v2-tokenizer"
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




def test_cloud_generation_rejects_invalid_model_identifier(monkeypatch):
    monkeypatch.setattr(ai_providers, "_get_key", lambda provider: "test-key")
    with pytest.raises(ValueError, match="identificador de modelo válido"):
        asyncio.run(ai_providers.generate_with_provider(
            "openai", "../invalid", "system", "prompt"
        ))


def test_cloud_generation_reports_missing_api_key(monkeypatch):
    monkeypatch.setattr(ai_providers, "_get_key", lambda provider: None)
    with pytest.raises(RuntimeError, match="Cadastre a chave de API"):
        asyncio.run(ai_providers.generate_with_provider(
            "openai", "gpt-4.1-mini", "system", "prompt"
        ))


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"choices": [{"message": {"content": "  texto local  "}}]}, "texto local"),
        ({"choices": [{"message": {"content": ""}}]}, None),
        ({"choices": []}, None),
        ({"choices": [{"message": None}]}, None),
        ({"choices": [{"message": {"content": ["texto"]}}]}, None),
        (None, None),
    ],
)
def test_local_completion_parser_validates_payload(payload, expected):
    if expected is None:
        with pytest.raises(ValueError):
            ia_local._extract_local_completion_text(payload)
    else:
        assert ia_local._extract_local_completion_text(payload) == expected


def test_cloud_generation_uses_guarded_parser_for_each_provider():
    source = Path(ai_providers.__file__).read_text(encoding="utf-8")
    request = source.split("async def _request_completion(", 1)[1].split(
        "async def generate_with_provider(", 1)[0]
    for provider in ("openai", "anthropic", "gemini"):
        assert f'_extract_response_text(response.json(), "{provider}")' in request
    assert 'response.json().get("content", [])' not in request
    assert 'response.json().get("candidates", [])' not in request


def test_local_generation_endpoint_uses_guarded_response_parser():
    source = Path(ia_local.__file__).read_text(encoding="utf-8")
    generation = source.split("async def generate_text(", 1)[1]
    assert "answer = _extract_local_completion_text(data)" in generation
    assert 'data["choices"][0]["message"]["content"]' not in generation


@pytest.mark.parametrize(
    ("kind", "payload", "expected"),
    [
        ("openai", {"choices": [{"message": {"content": "texto"}}]}, "texto"),
        ("openai", {"choices": [{"message": {"content": [{"text": "parte 1"}, {"text": "parte 2"}]}}]}, "parte 1parte 2"),
        ("anthropic", {"content": [{"type": "text", "text": "resposta"}]}, "resposta"),
        ("gemini", {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}, "ok"),
        ("openai", {"unexpected": "shape"}, ""),
        ("anthropic", {"content": "unexpected"}, ""),
        ("gemini", {"candidates": []}, ""),
        ("gemini", {"candidates": [{"content": None}]}, ""),
        ("openai", None, ""),
    ],
)
def test_cloud_provider_response_parser_handles_valid_and_malformed_payloads(kind, payload, expected):
    assert ai_providers._extract_response_text(payload, kind) == expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, "A chave foi recusada pelo provedor"),
        (403, "A chave foi recusada pelo provedor"),
        (429, "Limite ou crédito da API atingido"),
        (500, "Erro HTTP 500 do provedor"),
    ],
)
def test_cloud_generation_maps_provider_http_errors(monkeypatch, status, expected):
    request = httpx.Request("POST", "https://provider.example")
    response = httpx.Response(status, request=request, text="provider error detail")
    error = httpx.HTTPStatusError("provider error", request=request, response=response)
    monkeypatch.setattr(ai_providers, "_get_key", lambda provider: "test-key")
    monkeypatch.setattr(ai_providers, "_request_completion", AsyncMock(side_effect=error))
    with pytest.raises(RuntimeError, match=expected):
        asyncio.run(ai_providers.generate_with_provider(
            "openai", "gpt-4.1-mini", "system", "prompt"
        ))

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


def test_runtime_install_refuses_publish_if_runtime_activated_during_download(monkeypatch, tmp_path):
    variant = "linux-cpu-x64"
    meta = ia_local.RUNTIME_CATALOG[variant]
    monkeypatch.setattr(ia_local, "RUNTIME_DIR", tmp_path / "runtime")
    ia_local.RUNTIME_DIR.mkdir(parents=True)

    class ActiveProcess:
        def poll(self):
            return None

    def fake_download(url, archive, size, job_id):
        archive.write_bytes(b"package")
        # Simulate another request activating this variant during the download.
        monkeypatch.setattr(ia_local, "PROCESS", ActiveProcess())
        monkeypatch.setattr(ia_local, "ACTIVE_VARIANT", variant)
        monkeypatch.setattr(ia_local, "ACTIVE_MODEL", "test-model")

    def fake_extract(archive, destination, kind):
        destination.mkdir(parents=True, exist_ok=True)
        (destination / meta["binary"]).write_bytes(b"fake-runtime")

    monkeypatch.setattr(ia_local, "_download", fake_download)
    monkeypatch.setattr(ia_local, "_extract_archive", fake_extract)
    monkeypatch.setattr(ia_local, "_sha256", lambda path: meta["sha256"])
    jid = ia_local._job("runtime")
    ia_local._install_runtime_worker(jid, variant)

    assert ia_local.JOBS[jid]["status"] == "error"
    assert "ativado durante a instalação" in ia_local.JOBS[jid]["message"]
    assert ia_local._runtime_binary(variant) is None


def test_duplicate_runtime_install_jobs_reuse_installed_runtime(monkeypatch, tmp_path):
    import threading

    variant = "linux-cpu-x64"
    meta = ia_local.RUNTIME_CATALOG[variant]
    monkeypatch.setattr(ia_local, "RUNTIME_DIR", tmp_path / "runtime")
    ia_local.RUNTIME_DIR.mkdir(parents=True)
    downloaded = []

    def fake_download(url, archive, size, job_id):
        downloaded.append(job_id)
        archive.write_bytes(b"package")

    def fake_extract(archive, destination, kind):
        destination.mkdir(parents=True, exist_ok=True)
        (destination / meta["binary"]).write_bytes(b"fake-runtime")

    monkeypatch.setattr(ia_local, "_download", fake_download)
    monkeypatch.setattr(ia_local, "_extract_archive", fake_extract)
    monkeypatch.setattr(ia_local, "_sha256", lambda path: meta["sha256"])
    jobs = [ia_local._job("runtime"), ia_local._job("runtime")]
    workers = [threading.Thread(target=ia_local._install_runtime_worker, args=(jid, variant)) for jid in jobs]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=3)
    assert all(not worker.is_alive() for worker in workers)
    assert len(downloaded) == 1
    assert all(ia_local.JOBS[jid]["status"] == "done" for jid in jobs)
    assert ia_local._runtime_binary(variant) is not None


def test_concurrent_provider_config_writes_remain_valid_json(monkeypatch, tmp_path):
    import threading
    import json

    path = tmp_path / "provider-config.json"
    monkeypatch.setattr(ai_providers, "CONFIG_PATH", path)
    workers = [threading.Thread(target=ai_providers._write_config, args=({
        "provider": "openai", "models": {"openai": f"model-{index}"}
    },)) for index in range(8)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=2)
    assert all(not worker.is_alive() for worker in workers)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["provider"] == "openai"
    assert data["models"]["openai"].startswith("model-")
    assert not list(tmp_path.glob("provider-config.json.tmp-*"))


def test_model_deletion_waits_for_runtime_lifecycle_lock(monkeypatch, tmp_path):
    import threading
    import time

    monkeypatch.setattr(ia_local, "MODELS_DIR", tmp_path)
    finished = threading.Event()
    result = []
    ia_local.RUNTIME_LIFECYCLE_LOCK.acquire()
    try:
        worker = threading.Thread(target=lambda: (result.append(ia_local.delete_model("qwen3-4b-q4km", local_request())), finished.set()))
        worker.start()
        time.sleep(0.05)
        assert not finished.is_set(), "Model deletion must serialize with runtime activation/deactivation"
    finally:
        ia_local.RUNTIME_LIFECYCLE_LOCK.release()
    worker.join(timeout=2)
    assert finished.is_set()
    assert result == [{"ok": True}]


def test_model_deletion_waits_for_model_download_lock(monkeypatch, tmp_path):
    import threading
    import time

    model_id = "qwen3-4b-q4km"
    monkeypatch.setattr(ia_local, "MODELS_DIR", tmp_path)
    model_folder = tmp_path / model_id
    model_folder.mkdir()
    (model_folder / "partial.gguf").write_bytes(b"partial")
    download_lock = ia_local.MODEL_DOWNLOAD_LOCKS.setdefault(model_id, threading.Lock())
    finished = threading.Event()
    result = []
    download_lock.acquire()
    try:
        worker = threading.Thread(target=lambda: (result.append(ia_local.delete_model(model_id, local_request())), finished.set()))
        worker.start()
        time.sleep(0.05)
        assert not finished.is_set(), "Model deletion must wait for an in-progress download"
        assert model_folder.exists()
    finally:
        download_lock.release()
    worker.join(timeout=2)
    assert finished.is_set()
    assert result == [{"ok": True, "removed_bytes": len(b"partial")}]
    assert not model_folder.exists()


def test_concurrent_provider_config_updates_preserve_model_settings(monkeypatch, tmp_path):
    import threading
    import json

    path = tmp_path / "provider-config.json"
    monkeypatch.setattr(ai_providers, "CONFIG_PATH", path)
    updates = [(provider, f"model-{provider}") for provider in ai_providers.PROVIDERS]
    workers = [threading.Thread(target=ai_providers._update_provider_config, args=(provider, model))
               for provider, model in updates]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=3)
    assert all(not worker.is_alive() for worker in workers)
    config = json.loads(path.read_text(encoding="utf-8"))
    assert config["provider"] in ai_providers.PROVIDERS
    assert config["models"] == {provider: model for provider, model in updates}
    assert not list(tmp_path.glob("provider-config.json.tmp-*"))


def test_local_security_middleware_covers_voice_mutation_routes():
    server_source = (Path(__file__).resolve().parents[1] / "server" / "server.py").read_text(encoding="utf-8")
    protected_paths = ("/api/ai", "/api/narration", "/api/dialogo", "/api/legenda", "/api/roteiro", "/voices", "/presets", "/tts")
    assert all(f'"{path}"' in server_source for path in protected_paths)
    # Static UI and audio routes also require an allowed Host to block DNS rebinding.
    assert 'if scope.get("type") != "http":' in server_source
    assert "protected_path = scope.get(\"path\", \"\").startswith(" in server_source
    assert "if host not in AI_LOCAL_HOSTS" in server_source
    assert server_source.index("if host not in AI_LOCAL_HOSTS") < server_source.index("if not protected_path or")


def test_tts_engines_share_inference_lock():
    server_source = (Path(__file__).resolve().parents[1] / "server" / "server.py").read_text(encoding="utf-8")
    narration_source = (Path(__file__).resolve().parents[1] / "server" / "narration_api.py").read_text(encoding="utf-8")
    assert "ENGINE_INFERENCE_LOCK = threading.Lock()" in server_source
    assert "with ENGINE_INFERENCE_LOCK, _lock:" in server_source
    assert "inference_lock=ENGINE_INFERENCE_LOCK" in server_source
    assert "lock=ENGINE_INFERENCE_LOCK, run=run_dialogo" in server_source
    assert "def run_dialogo(fn):" in server_source
    assert "inference_guard = inference_lock or threading.Lock()" in narration_source


def test_gitignore_excludes_optional_engine_venvs():
    gitignore = (Path(__file__).resolve().parents[1] / ".gitignore").read_text(encoding="utf-8")
    assert ".venvs/" in gitignore


def test_linux_installer_reports_optional_download_failures():
    installer = (Path(__file__).resolve().parents[1] / "instalar-linux.sh").read_text(encoding="utf-8")
    assert "pip install --upgrade pip || echo" in installer
    assert "modelo de acentos nao foi baixado" in installer
    assert "faster_whisper" in installer


def test_voice_ui_checks_mutation_http_errors():
    ui_source = (Path(__file__).resolve().parents[1] / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    assert "if (!response.ok) throw new Error" in ui_source
    assert "Falha ao remover a voz:" in ui_source
    assert "Não consegui gerar outra versão desta voz:" in ui_source
    assert "finally {\n      setRegenId(null);" in ui_source


def test_voice_audio_object_urls_are_released_and_stale_previews_cancelled():
    ui_source = (Path(__file__).resolve().parents[1] / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    assert "const previewRequestRef = useRef(0);" in ui_source
    assert "requestId !== previewRequestRef.current" in ui_source
    assert "const releasePreviewUrl = () => {" in ui_source
    assert "URL.revokeObjectURL(url);" in ui_source
    assert "SEGMENTS.delete(url);" in ui_source
    assert "previewAudioRef.current?.pause();" in ui_source
    assert "previewAudioRef.current.src = \"\";" in ui_source
    assert "URL.revokeObjectURL(removed.url);" in ui_source


def test_narration_batch_queue_uses_stable_ids_and_locks_edits():
    ui_source = (Path(__file__).resolve().parents[1] / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    assert "const batchProcessingRef = useRef(false);" in ui_source
    assert "if (batchProcessingRef.current || batchQueue.length === 0) return;" in ui_source
    assert "const itemsToProcess = batchQueue.filter(item => item.status !== 'done');" in ui_source
    assert "item.id === queueItem.id" in ui_source
    assert "disabled={isGenerating}" in ui_source
    assert "batchProcessingRef.current = false;" in ui_source


def test_voice_upload_has_size_limit_atomic_publish_and_rollback():
    server_source = (Path(__file__).resolve().parents[1] / "server" / "server.py").read_text(encoding="utf-8")
    assert "sys, threading, uuid" in server_source
    assert "VOICE_UPLOAD_LIMIT = 50 * 1024 * 1024" in server_source
    assert "await file.read(VOICE_UPLOAD_LIMIT + 1)" in server_source
    assert "with ENGINE_INFERENCE_LOCK, _lock, VOICE_UPLOAD_LOCK:" in server_source
    assert "Serialize deletion with synthesis and upload" in server_source
    assert "os.replace(temp, destination)" in server_source
    assert "Restore both files together" in server_source
    assert "shutil.copy2(destination, audio_backup)" in server_source
    assert "shutil.copy2(transcript_path, transcript_backup)" in server_source
    assert "for leftover in (temp, transcript_temp):" in server_source
    assert "leftover.unlink(missing_ok=True)" in server_source


def test_gguf_import_is_staged_and_published_after_validation():
    source = (Path(__file__).resolve().parents[1] / "server" / "ia_local.py").read_text(encoding="utf-8")
    import_block = source[source.index('@router.post("/models/import")'):source.index('@router.post("/models/activate")')]
    assert 'temporary = folder /' in import_block and '.part' in import_block
    assert 'temporary.replace(target)' in import_block
    assert 'check.read(4) != b"GGUF"' in import_block
    assert 'shutil.rmtree(folder, ignore_errors=True)' in import_block


def test_corrupted_existing_local_model_is_repaired_and_metadata_published_atomically(monkeypatch, tmp_path):
    import hashlib
    import json

    model_id = "qwen3-4b-q4km"
    payload = b"valid-model-fixture"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(ia_local, "MODELS_DIR", tmp_path)
    target_dir = tmp_path / model_id
    target_dir.mkdir()
    target = target_dir / ia_local.MODEL_CATALOG[model_id]["filename"]
    target.write_bytes(b"corrupted-old-model")
    monkeypatch.setattr(ia_local, "_hf_file_digest", lambda repo, filename: (digest, len(payload)))

    def fake_download(url, destination, size, job_id):
        destination.write_bytes(payload)

    monkeypatch.setattr(ia_local, "_download", fake_download)
    jid = ia_local._job("model")
    ia_local._download_model_worker(jid, model_id)

    assert ia_local.JOBS[jid]["status"] == "done"
    assert target.read_bytes() == payload
    metadata = json.loads((target_dir / "model.json").read_text(encoding="utf-8"))
    assert metadata["sha256"] == digest
    assert not list(target_dir.glob(".model.json.*.tmp"))


def test_failed_repair_does_not_leave_corrupted_model_reported_as_installed(monkeypatch, tmp_path):
    import hashlib

    model_id = "qwen3-4b-q4km"
    expected = b"valid-model-fixture"
    digest = hashlib.sha256(expected).hexdigest()
    monkeypatch.setattr(ia_local, "MODELS_DIR", tmp_path)
    target_dir = tmp_path / model_id
    target_dir.mkdir()
    target = target_dir / ia_local.MODEL_CATALOG[model_id]["filename"]
    target.write_bytes(b"corrupted")
    (target_dir / "model.json").write_text("{bad metadata", encoding="utf-8")
    monkeypatch.setattr(ia_local, "_hf_file_digest", lambda repo, filename: (digest, len(expected)))

    def fail_download(url, destination, size, job_id):
        raise OSError("simulated network interruption")

    monkeypatch.setattr(ia_local, "_download", fail_download)
    jid = ia_local._job("model")
    ia_local._download_model_worker(jid, model_id)

    assert ia_local.JOBS[jid]["status"] == "error"
    assert not target.exists()
    assert not (target_dir / "model.json").exists()


def test_local_ai_job_history_is_bounded_and_keeps_active_jobs(monkeypatch):
    now = time.time()
    history = {f"done-{index}": {"id": f"done-{index}", "status": "done", "created_at": now - index}
               for index in range(120)}
    history["running-1"] = {"id": "running-1", "status": "running", "created_at": now - 5000}
    history["running-2"] = {"id": "running-2", "status": "downloading", "created_at": now - 5000}
    monkeypatch.setattr(ia_local, "JOBS", history)
    jid = ia_local._job("model")
    finished = [job for job in ia_local.JOBS.values() if job["status"] in ("done", "error")]
    active = [job for job in ia_local.JOBS.values() if job["status"] not in ("done", "error")]
    assert len(finished) == 100
    assert {job["id"] for job in active} >= {"running-1", "running-2", jid}


def test_background_job_start_failure_marks_job_failed(monkeypatch):
    class FailingThread:
        def __init__(self, *args, **kwargs):
            pass
        def start(self):
            raise RuntimeError("thread resource unavailable")
    monkeypatch.setattr(ia_local.threading, "Thread", FailingThread)
    jid = ia_local._job("runtime")
    with pytest.raises(Exception) as caught:
        ia_local._start_background_job(jid, lambda: None, ())
    assert getattr(caught.value, "status_code", None) == 500
    assert ia_local.JOBS[jid]["status"] == "error"
    assert "resource unavailable" in ia_local.JOBS[jid]["message"]


def test_active_local_model_cannot_be_uninstalled_during_generation(monkeypatch, tmp_path):
    from fastapi import HTTPException

    class RunningProcess:
        @staticmethod
        def poll():
            return None

    model_id = "qwen3-4b-q4km"
    monkeypatch.setattr(ia_local, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(ia_local, "PROCESS", RunningProcess())
    monkeypatch.setattr(ia_local, "ACTIVE_MODEL", model_id)
    monkeypatch.setattr(ia_local, "ACTIVE_GENERATIONS", 1)

    with pytest.raises(HTTPException) as exc:
        ia_local.delete_model(model_id, local_request(method="DELETE"))

    assert exc.value.status_code == 409
    assert "gerando um roteiro" in exc.value.detail


def test_local_model_uninstall_refuses_symlink_outside_model_directory(monkeypatch, tmp_path):
    from fastapi import HTTPException

    models_root = tmp_path / "models"
    outside = tmp_path / "outside"
    models_root.mkdir()
    outside.mkdir()
    protected = outside / "keep.gguf"
    protected.write_bytes(b"keep")
    try:
        (models_root / "qwen3-4b-q4km").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("O sistema de testes não permite criar links simbólicos.")
    monkeypatch.setattr(ia_local, "MODELS_DIR", models_root)
    monkeypatch.setattr(ia_local, "ACTIVE_MODEL", None)
    monkeypatch.setattr(ia_local, "ACTIVE_GENERATIONS", 0)

    with pytest.raises(HTTPException) as exc:
        ia_local.delete_model("qwen3-4b-q4km", local_request(method="DELETE"))

    assert exc.value.status_code == 400
    assert protected.read_bytes() == b"keep"
