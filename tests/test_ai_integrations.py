import asyncio
import os
import sys
import tempfile
import pytest
import os
import sys
import tempfile
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


def test_cloud_provider_catalog_has_expected_services():
    expected = {"openai", "anthropic", "gemini", "openrouter", "deepseek", "groq", "mistral"}
    assert expected.issubset(ai_providers.PROVIDERS)


def test_ai_provider_guard_rejects_external_origin():
    with pytest.raises(ai_providers.HTTPException):
        ai_providers._guard(local_request(origin="https://attacker.example"))


def test_ai_provider_guard_accepts_local_same_origin():
    ai_providers._guard(local_request())


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
    monkeypatch.setenv("SOCIAL_SOUND_MODELS_DIR", str(shared))
    assert ia_local.models_dir() == shared


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
