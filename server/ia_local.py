"""IA local: runtime llama.cpp, modelos GGUF e compositor de letras.

Os downloads são limitados a artefatos fixados no catálogo e verificados por SHA-256.
O servidor do llama.cpp escuta somente em 127.0.0.1.
"""
from __future__ import annotations

import atexit
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import tarfile
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from urllib.request import Request as URLRequest, urlopen

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from ai_providers import generate_with_provider
from security_config import LOCAL_HOSTS, LOCAL_ORIGINS

router = APIRouter(prefix="/api/ai", tags=["ia-local"])
LOCK = threading.RLock()
RUNTIME_LIFECYCLE_LOCK = threading.RLock()
JOBS: dict[str, dict] = {}
MODEL_DOWNLOAD_LOCKS: dict[str, threading.Lock] = {}
PROCESS: subprocess.Popen | None = None
ACTIVE_MODEL: str | None = None
ACTIVE_VARIANT: str | None = None
PORT = 8010

def data_root() -> Path:
    override = os.environ.get("SOCIAL_SOUND_DATA")
    if override:
        return Path(override).expanduser().resolve()
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return base / "SocialSound"
    if system == "Darwin":
        return Path.home() / "Library/Application Support/SocialSound"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "social-sound"

ROOT = data_root()
RUNTIME_DIR = ROOT / "runtime"

def models_dir() -> Path:
    """GGUFs usam a subpasta LLM da biblioteca Social Nexus quando configurada."""
    shared_root = os.environ.get("SOCIAL_NEXUS_MODELS_DIR")
    if shared_root:
        return (Path(shared_root).expanduser() / "LLM")
    return Path(os.environ.get("SOCIAL_SOUND_MODELS_DIR", str(ROOT / "models"))).expanduser()

# O runtime llama.cpp e os logs continuam locais a esta instalacao.
MODELS_DIR = models_dir()
LOG_DIR = ROOT / "logs"
for directory in (RUNTIME_DIR, MODELS_DIR, LOG_DIR):
    directory.mkdir(parents=True, exist_ok=True)

RUNTIME_CATALOG = {
    "win-cpu-x64": {
        "label": "Windows x64 — CPU",
        "system": "Windows", "machine": "AMD64", "backend": "cpu",
        "url": "https://github.com/ggml-org/llama.cpp/releases/download/b12359/llama-b12359-bin-win-cpu-x64.zip",
        "sha256": "837c1655e87df3b66989f4be33a792a1399c785bf259038dc75c900096683e69",
        "size": 25097509, "archive": "zip", "binary": "llama-server.exe"
    },
    "win-cuda124-x64": {
        "label": "Windows x64 — NVIDIA CUDA 12.4",
        "system": "Windows", "machine": "AMD64", "backend": "cuda",
        "url": "https://github.com/ggml-org/llama.cpp/releases/download/b12359/llama-b12359-bin-win-cuda-12.4-x64.zip",
        "sha256": "e9c0abf442e8339c06728366c1ad2c711332f9939c0c00603fb75d85fd44c914",
        "size": 318976332, "archive": "zip", "binary": "llama-server.exe",
        "extras": [{"url": "https://github.com/ggml-org/llama.cpp/releases/download/b12359/cudart-llama-bin-win-cuda-12.4-x64.zip",
                    "sha256": "8c79a9b226de4b3cacfd1f83d24f962d0773be79e1f7b75c6af4ded7e32ae1d6",
                    "size": 391443627, "archive": "zip"}]
    },
    "win-vulkan-x64": {
        "label": "Windows x64 — Vulkan",
        "system": "Windows", "machine": "AMD64", "backend": "vulkan",
        "url": "https://github.com/ggml-org/llama.cpp/releases/download/b12359/llama-b12359-bin-win-vulkan-x64.zip",
        "sha256": "e8d18c6e4210cca87e7307c2ea78363ac8d158e4e1397358ec96ab70b53a0d5e",
        "size": 38090643, "archive": "zip", "binary": "llama-server.exe"
    },
    "linux-cpu-x64": {
        "label": "Linux x64 — CPU (Ubuntu)",
        "system": "Linux", "machine": "x86_64", "backend": "cpu",
        "url": "https://github.com/ggml-org/llama.cpp/releases/download/b12359/llama-b12359-bin-ubuntu-x64.tar.gz",
        "sha256": "0bc1f091e8916102b6d8f2cf944233a620e90a0f856c72d0ce41150c65c2e72e",
        "size": 23311084, "archive": "tar.gz", "binary": "llama-server"
    },
    "linux-cuda128-x64": {
        "label": "Linux x64 — NVIDIA CUDA 12.8",
        "system": "Linux", "machine": "x86_64", "backend": "cuda",
        "url": "https://github.com/ggml-org/llama.cpp/releases/download/b12359/llama-b12359-bin-ubuntu-cuda-12.8-x64.tar.gz",
        "sha256": "50c937bec5bbd9f74c99138034f7403283ee21f1943f2429d7b1e4c079eafc11",
        "size": 199223370, "archive": "tar.gz", "binary": "llama-server",
        "extras": [{"url": "https://github.com/ggml-org/llama.cpp/releases/download/b12359/cudart-llama-b12359-bin-ubuntu-cuda-12.8-x64.tar.gz",
                    "sha256": "75a12d227f44a391608992329241765343bd143ee9445b90dc62e154ee726e5d",
                    "size": 594371571, "archive": "tar.gz"}]
    },
    "linux-vulkan-x64": {
        "label": "Linux x64 — Vulkan",
        "system": "Linux", "machine": "x86_64", "backend": "vulkan",
        "url": "https://github.com/ggml-org/llama.cpp/releases/download/b12359/llama-b12359-bin-ubuntu-vulkan-x64.tar.gz",
        "sha256": "19b60f00395a3f4954e46a5037695bc1d843404fc9d3124f82a612ecd8fbe9f0",
        "size": 36153377, "archive": "tar.gz", "binary": "llama-server"
    },
    "mac-arm64": {
        "label": "macOS Apple Silicon — Metal",
        "system": "Darwin", "machine": "arm64", "backend": "metal",
        "url": "https://github.com/ggml-org/llama.cpp/releases/download/b12359/llama-b12359-bin-macos-arm64.tar.gz",
        "sha256": "82b00abc740160e1b9980e6cc79c117345fa34af058c80e6c0a69aa8ddccde75",
        "size": 16907811, "archive": "tar.gz", "binary": "llama-server"
    },
    "mac-x64": {
        "label": "macOS Intel — CPU",
        "system": "Darwin", "machine": "x86_64", "backend": "cpu",
        "url": "https://github.com/ggml-org/llama.cpp/releases/download/b12359/llama-b12359-bin-macos-x64.tar.gz",
        "sha256": "25320d529077ef5a3d16e7b5da26438f221d88c8c0930a32b0c79457f5eede56",
        "size": 12661621, "archive": "tar.gz", "binary": "llama-server"
    }
}

MODEL_CATALOG = {
    "qwen3-4b-q4km": {
        "name": "Qwen3 4B Instruct — Q4_K_M",
        "family": "Qwen3", "repo": "Qwen/Qwen3-4B-GGUF",
        "filename": "Qwen3-4B-Q4_K_M.gguf",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0",
        "model_url": "https://huggingface.co/Qwen/Qwen3-4B-GGUF",
        "approx_size_gb": 2.5, "requires_license_acceptance": False,
        "description": "Modelo multilíngue de 4B parâmetros, quantização Q4_K_M. Download direto do repositório oficial Qwen."
    },
    "gemma3-4b-it-q4km": {
        "name": "Gemma 3 4B Instruct — Q4_K_M",
        "family": "Gemma 3", "repo": "ggml-org/gemma-3-4b-it-GGUF",
        "filename": "gemma-3-4b-it-Q4_K_M.gguf",
        "license": "Gemma Terms of Use",
        "license_url": "https://ai.google.dev/gemma/terms",
        "model_url": "https://huggingface.co/ggml-org/gemma-3-4b-it-GGUF",
        "approx_size_gb": 2.49, "requires_license_acceptance": True,
        "description": "Gemma 3 4B Instruct em GGUF Q4_K_M. Requer leitura e aceite dos Gemma Terms of Use antes do download."
    }
}

def _guard_local_request(request):
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

def _job(kind: str) -> str:
    jid = uuid.uuid4().hex[:12]
    now = time.time()
    with LOCK:
        for old_id, old in list(JOBS.items()):
            if old.get("status") in ("done", "error") and now - old.get("created_at", now) > 3600:
                JOBS.pop(old_id, None)
        JOBS[jid] = {"id": jid, "kind": kind, "status": "queued", "progress": 0,
                     "message": "Na fila", "created_at": now}
    return jid

def _update_job(jid: str, **values):
    with LOCK:
        if jid in JOBS:
            JOBS[jid].update(values)

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def _download(url: str, dest: Path, expected_size: int | None, jid: str):
    if not isinstance(expected_size, int) or expected_size <= 0:
        raise ValueError("O download não possui tamanho esperado válido.")
    req = URLRequest(url, headers={"User-Agent": "SocialSound/1.0"})
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.unlink(missing_ok=True)
    total = 0
    try:
        with urlopen(req, timeout=45) as response, tmp.open("wb") as out:
            header_length = response.headers.get("Content-Length")
            if header_length:
                try:
                    advertised = int(header_length)
                except ValueError:
                    raise ValueError("O servidor informou Content-Length inválido.")
                if advertised != expected_size:
                    raise ValueError(f"Tamanho informado pelo servidor divergente: {advertised} bytes (esperado {expected_size}).")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > expected_size:
                    raise ValueError(f"Download excedeu o tamanho esperado de {expected_size} bytes; interrompido.")
                out.write(chunk)
                pct = int(total * 100 / expected_size)
                _update_job(jid, status="downloading", progress=min(pct, 99),
                            message=f"Baixando: {pct}% ({total / (1024**2):.0f} MB)")
        if total != expected_size:
            raise ValueError(f"Tamanho inesperado: {total} bytes (esperado {expected_size}).")
        tmp.replace(dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

def _safe_member_path(root: Path, member_name: str) -> Path:
    pure = PurePosixPath(member_name.replace("\\", "/"))
    if pure.is_absolute() or any(part in ("..", "") for part in pure.parts):
        raise ValueError("Arquivo inseguro no pacote do runtime.")
    target = (root / Path(*pure.parts)).resolve()
    if root.resolve() not in target.parents and target != root.resolve():
        raise ValueError("Caminho fora da pasta de instalação.")
    return target

def _extract_archive(archive: Path, dest: Path, kind: str):
    dest.mkdir(parents=True, exist_ok=True)
    if kind == "zip":
        with zipfile.ZipFile(archive) as zf:
            members = zf.infolist()
            if len(members) > 20000 or sum(x.file_size for x in members) > 2 * 1024**3:
                raise ValueError("O pacote compactado excede os limites de extração.")
            for item in members:
                target = _safe_member_path(dest, item.filename)
                if item.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(item) as src, target.open("wb") as out:
                    shutil.copyfileobj(src, out)
    else:
        with tarfile.open(archive, "r:gz") as tf:
            members = tf.getmembers()
            if len(members) > 20000 or sum(x.size for x in members if x.isfile()) > 2 * 1024**3:
                raise ValueError("O pacote compactado excede os limites de extração.")
            for item in members:
                target = _safe_member_path(dest, item.name)
                if item.isdev() or item.islnk():
                    continue
                if item.issym():
                    link = PurePosixPath(item.linkname.replace("\\", "/"))
                    if link.is_absolute():
                        raise ValueError("Link simbólico inseguro no pacote.")
                    resolved_link = (target.parent / Path(*link.parts)).resolve()
                    if dest.resolve() not in resolved_link.parents and resolved_link != dest.resolve():
                        raise ValueError("Link simbólico fora da pasta de instalação.")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.symlink_to(item.linkname)
                elif item.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif item.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    src = tf.extractfile(item)
                    if src:
                        with src, target.open("wb") as out:
                            shutil.copyfileobj(src, out)

def _runtime_binary(variant: str) -> Path | None:
    meta = RUNTIME_CATALOG.get(variant)
    if not meta:
        return None
    root = RUNTIME_DIR / variant
    candidates = list(root.rglob(meta["binary"])) if root.exists() else []
    return candidates[0] if candidates else None

def _install_runtime_worker(jid: str, variant: str):
    meta = RUNTIME_CATALOG[variant]
    try:
        _update_job(jid, status="downloading", progress=0, message="Baixando runtime oficial llama.cpp…")
        with tempfile.TemporaryDirectory(prefix="smb-llama-") as td:
            temp = Path(td)
            extracted = temp / "extracted"
            extracted.mkdir()
            packages = [meta, *meta.get("extras", [])]
            for index, package in enumerate(packages, start=1):
                archive = temp / (f"runtime-{index}.zip" if package["archive"] == "zip" else f"runtime-{index}.tar.gz")
                _update_job(jid, status="downloading", message=f"Baixando pacote {index} de {len(packages)} do runtime…")
                _download(package["url"], archive, package["size"], jid)
                _update_job(jid, status="verifying", progress=99, message=f"Verificando SHA-256 do pacote {index}…")
                actual = _sha256(archive)
                if actual.lower() != package["sha256"].lower():
                    raise ValueError(f"A verificação SHA-256 do pacote {index} falhou. O pacote foi descartado.")
                _extract_archive(archive, extracted, package["archive"])
            binary = next(iter(extracted.rglob(meta["binary"])), None)
            if binary is None:
                raise ValueError("O pacote não contém llama-server.")
            final = RUNTIME_DIR / variant
            if final.exists():
                shutil.rmtree(final)
            shutil.copytree(extracted, final)
            installed = final / binary.relative_to(extracted)
            if os.name != "nt":
                installed.chmod(installed.stat().st_mode | 0o111)
        _update_job(jid, status="done", progress=100, message="Runtime instalado e verificado.")
    except Exception as exc:
        _update_job(jid, status="error", message=str(exc)[:350])

def _model_file(model_id: str) -> Path:
    if model_id not in MODEL_CATALOG:
        raise ValueError("Modelo não encontrado no catálogo.")
    return MODELS_DIR / model_id / MODEL_CATALOG[model_id]["filename"]

def _normalize_sha256(value: str) -> str:
    digest = str(value or "").lower().removeprefix("sha256:")
    if len(digest) != 64 or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("O Hugging Face não forneceu um SHA-256 válido para este modelo.")
    return digest


def _hf_file_digest(repo: str, filename: str) -> tuple[str, int]:
    url = f"https://huggingface.co/api/models/{repo}/tree/main?recursive=false"
    req = URLRequest(url, headers={"User-Agent": "SocialSound/1.0"})
    with urlopen(req, timeout=30) as response:
        files = json.loads(response.read().decode("utf-8"))
    item = next((x for x in files if x.get("path") == filename), None)
    if not item:
        raise ValueError("O arquivo do modelo não foi encontrado no repositório oficial.")
    lfs = item.get("lfs") or {}
    digest = _normalize_sha256(lfs.get("oid") or item.get("oid"))
    size = item.get("size") or lfs.get("size")
    if not isinstance(size, int) or size <= 0:
        raise ValueError("O repositório não forneceu um tamanho verificável para este modelo.")
    return digest, size

def _download_model_worker(jid: str, model_id: str):
    with LOCK:
        model_lock = MODEL_DOWNLOAD_LOCKS.setdefault(model_id, threading.Lock())
    with model_lock:
        try:
            meta = MODEL_CATALOG[model_id]
            _update_job(jid, status="verifying", message="Consultando hash e tamanho no Hugging Face…")
            digest, size = _hf_file_digest(meta["repo"], meta["filename"])
            target_dir = MODELS_DIR / model_id
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / meta["filename"]
            if target.is_file() and target.stat().st_size == size and _sha256(target).lower() == digest.lower():
                (target_dir / "model.json").write_text(json.dumps({
                    "model_id": model_id, "repo": meta["repo"], "filename": meta["filename"],
                    "sha256": digest, "license": meta["license"], "installed_at": int(time.time())
                }, indent=2), encoding="utf-8")
                _update_job(jid, status="done", progress=100, message="Modelo já instalado e verificado.")
                return
            url = f"https://huggingface.co/{meta['repo']}/resolve/main/{meta['filename']}"
            _download(url, target, size, jid)
            _update_job(jid, status="verifying", progress=99, message="Validando SHA-256 do modelo…")
            if _sha256(target).lower() != digest.lower():
                target.unlink(missing_ok=True)
                raise ValueError("Hash SHA-256 do modelo não confere; arquivo removido.")
            (target_dir / "model.json").write_text(json.dumps({
                "model_id": model_id, "repo": meta["repo"], "filename": meta["filename"],
                "sha256": digest, "license": meta["license"], "installed_at": int(time.time())
            }, indent=2), encoding="utf-8")
            _update_job(jid, status="done", progress=100, message="Modelo baixado e verificado.")
        except Exception as exc:
            _update_job(jid, status="error", message=str(exc)[:350])

def _installed_models():
    found = []
    for model_id, meta in MODEL_CATALOG.items():
        p = _model_file(model_id)
        if p.is_file():
            found.append({"id": model_id, "name": meta["name"], "path": str(p),
                          "size_bytes": p.stat().st_size, "license": meta["license"]})
    for p in MODELS_DIR.glob("imported-*/**/*.gguf"):
        found.append({"id": p.parent.name, "name": p.name, "path": str(p),
                      "size_bytes": p.stat().st_size, "license": "Licença definida pelo usuário"})
    return found

def _stop_runtime():
    with RUNTIME_LIFECYCLE_LOCK:
        global PROCESS, ACTIVE_MODEL, ACTIVE_VARIANT
        with LOCK:
            proc = PROCESS
            PROCESS = None
            ACTIVE_MODEL = None
            ACTIVE_VARIANT = None
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
        return True
    

def _runtime_args(binary: Path, model_path: Path, gpu_layers: int = 0) -> list[str]:
    return [str(binary), "--host", "127.0.0.1", "--port", str(PORT),
            "--model", str(model_path), "--alias", "social-sound-local", "--ctx-size", "4096", "--jinja",
            "--n-gpu-layers", str(max(0, min(int(gpu_layers), 200))),
            "--parallel", "1", "--no-webui", "--cors-origins", "localhost"]


def _start_runtime(model_id: str, variant: str, gpu_layers: int = 0):
    with RUNTIME_LIFECYCLE_LOCK:
        global PROCESS, ACTIVE_MODEL, ACTIVE_VARIANT
        if variant not in RUNTIME_CATALOG or _runtime_binary(variant) is None:
            raise ValueError("Instale primeiro o runtime escolhido.")
        if model_id not in {m["id"] for m in _installed_models()}:
            raise ValueError("Baixe ou importe um modelo GGUF antes de ativá-lo.")
        model_path = _model_file(model_id) if model_id in MODEL_CATALOG else next(
            Path(m["path"]) for m in _installed_models() if m["id"] == model_id)
        if not model_path.is_file() or model_path.suffix.lower() != ".gguf":
            raise ValueError("Arquivo GGUF inválido.")
        _stop_runtime()
        time.sleep(0.25)
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", PORT)) == 0:
                raise RuntimeError(f"A porta local {PORT} já está sendo usada por outro programa.")
        binary = _runtime_binary(variant)
        log = (LOG_DIR / "llama-server.log").open("ab")
        args = _runtime_args(binary, model_path, gpu_layers)
        try:
            proc = subprocess.Popen(args, cwd=str(binary.parent), stdout=log,
                                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        finally:
            log.close()
        with LOCK:
            PROCESS, ACTIVE_MODEL, ACTIVE_VARIANT = proc, model_id, variant
        deadline = time.time() + 180
        while time.time() < deadline:
            if proc.poll() is not None:
                _stop_runtime()
                raise RuntimeError("llama-server encerrou durante a inicialização. Consulte logs/llama-server.log.")
            try:
                r = httpx.get(f"http://127.0.0.1:{PORT}/health", timeout=2)
                if r.status_code == 200:
                    return True
            except httpx.HTTPError:
                pass
            time.sleep(1)
        _stop_runtime()
        raise RuntimeError("O modelo demorou demais para iniciar. Verifique memória RAM/VRAM e o log.")
    

@router.get("/status")
def ai_status():
    proc = PROCESS
    running = bool(proc and proc.poll() is None)
    return {"runtime_installed": any(_runtime_binary(k) for k in RUNTIME_CATALOG),
            "runtime_running": running, "active_model": ACTIVE_MODEL,
            "active_variant": ACTIVE_VARIANT, "port": PORT,
            "data_directory": str(ROOT),
            "jobs": list(JOBS.values())[-8:]}

@router.get("/catalog")
def ai_catalog():
    system, machine = platform.system(), platform.machine().lower()
    runtimes = [{"id": k, "label": v["label"], "backend": v["backend"],
                 "size_bytes": v["size"] + sum(x["size"] for x in v.get("extras", [])), "installed": _runtime_binary(k) is not None,
                 "compatible": v["system"] == system and v["machine"].lower() == machine}
                for k, v in RUNTIME_CATALOG.items()]
    models = [{"id": k, **{x: v[x] for x in ("name", "family", "repo", "filename", "license",
               "license_url", "model_url", "approx_size_gb", "description", "requires_license_acceptance")},
               "installed": _model_file(k).is_file()} for k, v in MODEL_CATALOG.items()]
    return {"runtimes": runtimes, "models": models, "installed_models": _installed_models()}

@router.post("/runtime/install")
def install_runtime(payload: dict, request: Request):
    _guard_local_request(request)
    variant = str(payload.get("variant", ""))
    meta = RUNTIME_CATALOG.get(variant)
    if not meta:
        raise HTTPException(400, "Runtime não permitido.")
    if meta["system"] != platform.system() or meta["machine"].lower() != platform.machine().lower():
        raise HTTPException(400, "Este pacote não corresponde ao sistema e arquitetura detectados.")
    if _runtime_binary(variant):
        return {"installed": True, "message": "Runtime já instalado."}
    jid = _job("runtime")
    threading.Thread(target=_install_runtime_worker, args=(jid, variant), daemon=True).start()
    return {"job_id": jid}

@router.post("/models/download")
def download_model(payload: dict, request: Request):
    _guard_local_request(request)
    model_id = str(payload.get("model_id", ""))
    if model_id not in MODEL_CATALOG:
        raise HTTPException(400, "Modelo não permitido pelo catálogo.")
    if MODEL_CATALOG[model_id].get("requires_license_acceptance") and payload.get("accept_license") is not True:
        raise HTTPException(400, "Leia e aceite os termos de uso do modelo antes de baixar.")
    if _model_file(model_id).is_file():
        return {"installed": True}
    jid = _job("model")
    threading.Thread(target=_download_model_worker, args=(jid, model_id), daemon=True).start()
    return {"job_id": jid}

@router.post("/models/import")
async def import_model(request: Request, file: UploadFile = File(...)):
    _guard_local_request(request)
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".gguf"):
        raise HTTPException(400, "Selecione um arquivo .gguf.")
    model_id = "imported-" + uuid.uuid4().hex[:10]
    folder = MODELS_DIR / model_id
    folder.mkdir(parents=True, exist_ok=False)
    target = folder / filename
    total = 0
    try:
        with target.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > 30 * 1024**3:
                    raise HTTPException(413, "O modelo excede o limite de 30 GB.")
                out.write(chunk)
        if total < 1024 * 1024:
            raise HTTPException(400, "O arquivo GGUF parece incompleto.")
        with target.open("rb") as check:
            if check.read(4) != b"GGUF":
                raise HTTPException(400, "O arquivo selecionado não tem cabeçalho GGUF válido.")
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    finally:
        await file.close()
    (folder / "model.json").write_text(json.dumps({"model_id": model_id, "filename": filename,
        "license": "Não verificada — confirme os termos do modelo original"}, indent=2), encoding="utf-8")
    return {"id": model_id, "name": filename, "size_bytes": total,
            "warning": "A licença do arquivo importado não foi verificada."}

@router.post("/models/activate")
def activate_model(payload: dict, request: Request):
    _guard_local_request(request)
    model_id = str(payload.get("model_id", ""))
    variant = str(payload.get("variant", ""))
    try:
        gpu_layers = int(payload.get("gpu_layers", 0))
        if gpu_layers < 0 or gpu_layers > 200:
            raise ValueError("Camadas GPU deve ficar entre 0 e 200.")
        _start_runtime(model_id, variant, gpu_layers)
        return {"ok": True, "active_model": model_id, "port": PORT}
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc))

@router.post("/runtime/stop")
def stop_runtime(request: Request):
    _guard_local_request(request)
    _stop_runtime()
    return {"ok": True}

@router.get("/jobs/{jid}")
def ai_job(jid: str):
    if jid not in JOBS:
        raise HTTPException(404, "Tarefa não encontrada.")
    return JOBS[jid]

@router.delete("/models/{model_id}")
def delete_model(model_id: str, request: Request):
    _guard_local_request(request)
    if model_id == ACTIVE_MODEL:
        _stop_runtime()
    if model_id in MODEL_CATALOG:
        folder = MODELS_DIR / model_id
    elif re.fullmatch(r"imported-[0-9a-f]{10}", model_id):
        folder = MODELS_DIR / model_id
    else:
        raise HTTPException(400, "Modelo inválido.")
    if folder.exists():
        shutil.rmtree(folder)
    return {"ok": True}

@router.post("/generate")
async def generate_text(payload: dict, request: Request):
    _guard_local_request(request)
    provider = str(payload.get("provider", "local")).strip().lower()
    system = str(payload.get("system_prompt", "")).strip()[:12000]
    prompt = str(payload.get("prompt", "")).strip()[:24000]
    if not prompt:
        raise HTTPException(400, "Digite o pedido de geração.")
    if not system:
        system = "Você é um assistente profissional de criação de conteúdo. Siga as instruções do usuário, responda de forma clara e não invente fatos."
    try:
        max_tokens = int(payload.get("max_tokens", 1800))
    except (TypeError, ValueError):
        max_tokens = 1800
    max_tokens = max(256, min(max_tokens, 6000))
    if provider != "local":
        model = str(payload.get("provider_model", "")).strip()
        try:
            answer = await generate_with_provider(provider, model, system, prompt, max_tokens=max_tokens)
            return {"text": answer, "model": f"{provider}/{model}", "provider": provider}
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(502, str(exc)[:350])
    if not PROCESS or PROCESS.poll() is not None or not ACTIVE_MODEL:
        raise HTTPException(503, "Ative um modelo local antes de gerar.")
    body = {"model": "social-sound-local", "messages": [
        {"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "temperature": 0.7, "top_p": 0.8, "max_tokens": max_tokens, "stream": False}
    try:
        async with httpx.AsyncClient(timeout=240) as client:
            response = await client.post(f"http://127.0.0.1:{PORT}/v1/chat/completions", json=body)
            response.raise_for_status()
            data = response.json()
        answer = data["choices"][0]["message"]["content"].strip()
        if not answer:
            raise ValueError("O modelo local retornou uma resposta vazia.")
        return {"text": answer, "model": ACTIVE_MODEL, "provider": "local"}
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise HTTPException(502, f"Falha ao gerar com o modelo local: {str(exc)[:250]}")


atexit.register(_stop_runtime)
