"""Provedores de IA em nuvem para o Social Sound.

As chaves ficam no cofre de credenciais do sistema operacional (keyring).
Somente preferências não secretas são gravadas no diretório de dados.
"""
from __future__ import annotations

import json
import os
import platform
import re
import threading
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from security_config import LOCAL_HOSTS, LOCAL_ORIGINS

try:
    import keyring
except Exception:  # o modo local continua disponível sem backend de credenciais
    keyring = None

router = APIRouter(prefix="/api/ai/providers", tags=["ai-providers"])
SERVICE_NAME = "SocialSound"
PROVIDERS = {
    "openai": {"name": "OpenAI", "models": ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini"], "kind": "openai"},
    "anthropic": {"name": "Anthropic Claude", "models": ["claude-3-5-haiku-latest", "claude-sonnet-4-5", "claude-opus-4-1"], "kind": "anthropic"},
    "gemini": {"name": "Google Gemini", "models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"], "kind": "gemini"},
    "openrouter": {"name": "OpenRouter", "models": ["openai/gpt-4.1-mini", "anthropic/claude-sonnet-4", "google/gemini-2.5-flash"], "kind": "openai", "base_url": "https://openrouter.ai/api/v1"},
    "deepseek": {"name": "DeepSeek", "models": ["deepseek-chat", "deepseek-reasoner"], "kind": "openai", "base_url": "https://api.deepseek.com/v1"},
    "groq": {"name": "Groq", "models": ["llama-3.3-70b-versatile", "openai/gpt-oss-20b"], "kind": "openai", "base_url": "https://api.groq.com/openai/v1"},
    "mistral": {"name": "Mistral AI", "models": ["mistral-small-latest", "mistral-large-latest"], "kind": "openai", "base_url": "https://api.mistral.ai/v1"},
}
DEFAULT_CONFIG = {"provider": "local", "models": {}}


def _data_root() -> Path:
    override = os.environ.get("SOCIAL_SOUND_DATA")
    if override:
        return Path(override).expanduser().resolve()
    if platform.system() == "Windows":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "SocialSound"
    if platform.system() == "Darwin":
        return Path.home() / "Library/Application Support/SocialSound"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "social-sound"


CONFIG_PATH = _data_root() / "ai-provider-config.json"
CONFIG_LOCK = threading.RLock()


def _guard(request: Request) -> None:
    host = (request.headers.get("host") or "").lower()
    if host not in LOCAL_HOSTS:
        raise HTTPException(403, "Acesso permitido somente pela interface local.")
    origin = request.headers.get("origin")
    if origin is not None and origin not in LOCAL_ORIGINS:
        raise HTTPException(403, "Origem não permitida para a API local.")
    if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"} and origin not in LOCAL_ORIGINS:
        raise HTTPException(403, "A origem da requisição local não pôde ser confirmada.")
    fetch_site = (request.headers.get("sec-fetch-site") or "").lower()
    if fetch_site and fetch_site not in {"same-origin", "none"}:
        raise HTTPException(403, "Requisição de outra origem não permitida.")


def _read_config() -> dict:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError()
    except (OSError, ValueError, json.JSONDecodeError):
        data = {}
    models = data.get("models") if isinstance(data.get("models"), dict) else {}
    return {"provider": data.get("provider", "local") if data.get("provider", "local") in ("local", *PROVIDERS) else "local",
            "models": {k: str(v)[:160] for k, v in models.items() if k in PROVIDERS and isinstance(v, str)}}


def _write_config(data: dict) -> None:
    with CONFIG_LOCK:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp = CONFIG_PATH.with_name(CONFIG_PATH.name + ".tmp-" + uuid.uuid4().hex[:8])
        try:
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(CONFIG_PATH)
        finally:
            temp.unlink(missing_ok=True)


def _update_provider_config(provider: str, model: str | None = None) -> dict:
    """Serialize config read-modify-write to avoid losing concurrent provider settings."""
    with CONFIG_LOCK:
        cfg = _read_config()
        cfg["provider"] = provider
        if provider != "local" and model is not None:
            cfg["models"][provider] = model
        _write_config(cfg)
        return cfg


def _keyring_ready() -> bool:
    if keyring is None:
        return False
    secure_backend_modules = {
        "Windows": {"keyring.backends.Windows", "keyring.backends.win32"},
        "Darwin": {"keyring.backends.macOS"},
        "Linux": {"keyring.backends.SecretService", "keyring.backends.kwallet"},
    }
    secure_backend_classes = {
        "Windows": {"WinVaultKeyring", "Win32CryptoKeyring"},
        "Darwin": {"Keyring"},
        "Linux": {"Keyring", "KWallet"},
    }
    system = platform.system()
    try:
        backend = keyring.get_keyring()
        cls = backend.__class__
        module, name = cls.__module__, cls.__name__
        priority = float(getattr(backend, "priority", 0))
        return (
            system in secure_backend_modules
            and module in secure_backend_modules[system]
            and name in secure_backend_classes[system]
            and priority > 0
        )
    except Exception:
        return False


def _get_key(provider: str) -> str | None:
    if not _keyring_ready():
        return None
    try:
        return keyring.get_password(SERVICE_NAME, provider)
    except Exception:
        return None


def _set_key(provider: str, value: str) -> None:
    if not _keyring_ready():
        raise RuntimeError("O cofre de credenciais do sistema não está disponível. Configure o Gerenciador de Credenciais do Windows ou o cofre equivalente.")
    keyring.set_password(SERVICE_NAME, provider, value)


def _delete_key(provider: str) -> None:
    if not _keyring_ready():
        return
    try:
        keyring.delete_password(SERVICE_NAME, provider)
    except Exception:
        pass


def public_config() -> dict:
    cfg = _read_config()
    return {
        "selected_provider": cfg["provider"],
        "providers": [
            {"id": pid, "name": meta["name"], "models": meta["models"],
             "configured": bool(_get_key(pid))}
            for pid, meta in PROVIDERS.items()
        ],
        "secure_storage_available": _keyring_ready(),
        "selected_model": cfg["models"].get(cfg["provider"], ""),
    }


def _validate_provider(provider: str) -> str:
    provider = str(provider or "").strip().lower()
    if provider not in PROVIDERS:
        raise ValueError("Provedor de IA não permitido.")
    return provider


def _extract_response_text(payload: Any, kind: str) -> str:
    """Read text from provider payloads without assuming a successful response shape."""
    if not isinstance(payload, dict):
        return ""
    if kind == "openai":
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            return ""
        message = choices[0].get("message")
        if not isinstance(message, dict):
            return ""
        body = message.get("content")
        if isinstance(body, str):
            return body
        if isinstance(body, list):
            return "".join(item.get("text", "") for item in body
                           if isinstance(item, dict) and isinstance(item.get("text"), str))
        return ""
    if kind == "anthropic":
        blocks = payload.get("content")
        if not isinstance(blocks, list):
            return ""
        return "".join(block.get("text", "") for block in blocks
                       if isinstance(block, dict) and block.get("type") == "text"
                       and isinstance(block.get("text"), str))
    if kind == "gemini":
        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
            return ""
        content = candidates[0].get("content")
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            return ""
        return "".join(part.get("text", "") for part in parts
                       if isinstance(part, dict) and isinstance(part.get("text"), str))
    return ""


async def _request_completion(provider: str, model: str, api_key: str, system: str, user: str, max_tokens: int = 1800) -> str:
    meta = PROVIDERS[provider]
    timeout = httpx.Timeout(120.0, connect=15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if meta["kind"] == "openai":
            base = meta.get("base_url", "https://api.openai.com/v1")
            response = await client.post(
                base + "/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "system", "content": system},
                      {"role": "user", "content": user}], "temperature": 0.7, "max_tokens": max_tokens},
            )
            response.raise_for_status()
            result = _extract_response_text(response.json(), "openai")
        elif meta["kind"] == "anthropic":
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": model, "max_tokens": max_tokens,
                      "system": system, "messages": [{"role": "user", "content": user}]},
            )
            response.raise_for_status()
            result = "".join(part.get("text", "") for part in response.json().get("content", [])
                             if part.get("type") == "text")
        else:
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": api_key, "content-type": "application/json"},
                json={"systemInstruction": {"parts": [{"text": system}]},
                      "contents": [{"role": "user", "parts": [{"text": user}]}],
                      "generationConfig": {"temperature": 0.7, "maxOutputTokens": max_tokens}},
            )
            response.raise_for_status()
            candidates = response.json().get("candidates", [])
            result = "".join(p.get("text", "") for p in candidates[0].get("content", {}).get("parts", [])
                             if "text" in p) if candidates else ""
    if not isinstance(result, str) or not result.strip():
        raise ValueError("O provedor retornou uma resposta vazia.")
    return result.strip()


async def generate_with_provider(provider: str, model: str, system: str, user: str, max_tokens: int = 1800) -> str:
    provider = _validate_provider(provider)
    try:
        max_tokens = max(256, min(int(max_tokens), 6000))
    except (TypeError, ValueError):
        max_tokens = 1800
    key = _get_key(provider)
    if not key:
        raise RuntimeError(f"Cadastre a chave de API de {PROVIDERS[provider]['name']} nas configurações de IA.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}", model) or ".." in model:
        raise ValueError("Informe um identificador de modelo válido.")
    try:
        return await _request_completion(provider, model, key, system, user, max_tokens=max_tokens)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (401, 403):
            raise RuntimeError("A chave foi recusada pelo provedor. Confira a chave e as permissões.")
        if status == 429:
            raise RuntimeError("Limite ou crédito da API atingido. Confira a conta do provedor.")
        detail = exc.response.text[:250]
        raise RuntimeError(f"Erro HTTP {status} do provedor: {detail}")
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Não foi possível conectar ao provedor: {str(exc)[:180]}")


@router.get("/config")
def get_config(request: Request):
    _guard(request)
    return public_config()


@router.put("/config")
def update_config(payload: dict, request: Request):
    _guard(request)
    provider = str(payload.get("provider", "local")).strip().lower()
    if provider not in ("local", *PROVIDERS):
        raise HTTPException(400, "Provedor não permitido.")
    model = None
    if provider != "local":
        model = str(payload.get("model", "")).strip()
        if not model or len(model) > 160:
            raise HTTPException(400, "Informe o identificador do modelo.")
    _update_provider_config(provider, model)
    return public_config()


@router.post("/key")
def save_key(payload: dict, request: Request):
    _guard(request)
    provider = str(payload.get("provider", "")).strip().lower()
    if provider not in PROVIDERS:
        raise HTTPException(400, "Provedor não permitido.")
    api_key = str(payload.get("api_key", "")).strip()
    if len(api_key) < 12 or len(api_key) > 4096:
        raise HTTPException(400, "A chave de API parece inválida.")
    try:
        _set_key(provider, api_key)
    except Exception as exc:
        raise HTTPException(503, str(exc))
    return {"ok": True, "configured": True}


@router.delete("/key/{provider}")
def remove_key(provider: str, request: Request):
    _guard(request)
    if provider not in PROVIDERS:
        raise HTTPException(400, "Provedor não permitido.")
    _delete_key(provider)
    return {"ok": True}


@router.post("/test")
async def test_provider(payload: dict, request: Request):
    _guard(request)
    provider = str(payload.get("provider", "")).strip().lower()
    model = str(payload.get("model", "")).strip()
    try:
        answer = await generate_with_provider(provider, model, "Responda de forma breve.", "Responda apenas: conexão funcionando.")
        return {"ok": True, "message": answer[:160], "provider": provider, "model": model}
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(502, str(exc))
