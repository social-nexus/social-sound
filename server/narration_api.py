"""API and sequential worker for long-form VoxCPM2 narrations."""
from __future__ import annotations

import json
import queue
import os
import subprocess
import shutil
import sys
import threading
import time
import uuid
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from narration_queue import NarrationQueue, split_for_duration


def _terminate_process_tree(process):
    """Stop a live worker and descendants, including children that keep pipes open."""
    if process is None:
        return
    # Never signal a PID/PGID after its parent has exited: the identifier may
    # already have been reused by an unrelated process.
    try:
        if process.poll() is not None:
            return
    except Exception:
        pass
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            pass
    elif getattr(process, "_social_sound_new_session", False):
        try:
            import signal
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    if process.poll() is None:
        try:
            process.kill()
        except Exception:
            pass
    try:
        process.wait(timeout=10)
    except Exception:
        pass


def _run_worker_process(command, *, timeout, env):
    """Run a model worker in an isolated process group and reap it on timeout."""
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", env=env,
        start_new_session=(os.name != "nt"),
    )
    process._social_sound_new_session = os.name != "nt"
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_tree(process)
        stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(
            command, timeout, output=stdout or exc.output, stderr=stderr or exc.stderr
        ) from exc
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


class EnqueueRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200000)
    voice: str = Field(default="preset:narrador-grave", min_length=1, max_length=180)
    style: str = Field(default="", max_length=500)
    target_seconds: int = Field(default=60, ge=15, le=300)
    chars_per_minute: int = Field(default=850, ge=300, le=1500)
    engine: str = Field(default="voxcpm2", pattern="^(voxcpm2|supertonic3|omnivoice|f5tts)$")
    mode: str = Field(default="auto", pattern="^(auto|clone|design)$")
    reference_audio: str = Field(default="", max_length=1000)
    reference_text: str = Field(default="", max_length=5000)


def create_narration_router(*, lock, run, synth, ensure_preset, preset_by_id,
                            find_mine, parse_text, split_sentences, tighten, data_dir: Path, output_dir: Path, unload_engine=None, inference_lock=None):
    router = APIRouter(prefix="/api/narration", tags=["narracao"])
    db = NarrationQueue(data_dir / "narration_queue.sqlite3")
    output_dir.mkdir(parents=True, exist_ok=True)
    reference_dir = data_dir / "narration_references"
    reference_dir.mkdir(parents=True, exist_ok=True)
    worker_guard = threading.Lock()
    approval_guard = threading.Lock()
    candidate_guard = threading.Lock()
    inference_guard = inference_lock or threading.Lock()
    worker_started = False

    def job_paths(job_id: str):
        folder = output_dir / job_id
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def valid_audio_file(path: Path) -> bool:
        try:
            info = sf.info(str(path))
            return info.frames > 0 and info.samplerate >= 8000 and info.channels in (1, 2)
        except Exception:
            return False

    def supertonic_python() -> Path:
        configured = os.environ.get("SOCIAL_SOUND_SUPERTONIC_PYTHON")
        if configured:
            return Path(configured).expanduser()
        root = Path(__file__).resolve().parent / ".venvs" / "supertonic"
        return root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    def supertonic_cache() -> Path:
        configured = os.environ.get("SUPERTONIC_CACHE_DIR")
        if configured:
            return Path(configured).expanduser()
        return data_dir / "models" / "Narradores" / "Supertonic3"

    def supertonic_ready() -> bool:
        python = supertonic_python()
        cache = supertonic_cache()
        return (python.is_file() and (cache / "onnx").is_dir()
                and any((cache / "onnx").glob("*.onnx"))
                and (cache / "voice_styles").is_dir()
                and any((cache / "voice_styles").glob("*.json")))

    def render_supertonic_piece(job, part_index: int, destination: Path):
        if not supertonic_ready():
            raise RuntimeError("Supertonic 3 não está instalado. Feche o Social Sound e execute instalar-supertonic.bat.")
        _, _, voice = job["voice"].partition(":")
        segments = []
        for segment_type, value in parse_text(job["parts"][part_index]["text"]):
            if segment_type == "pause":
                segments.append({"type": "pause", "seconds": float(value)})
                continue
            for chunk in split_sentences(value):
                if chunk.strip():
                    segments.append({"type": "text", "text": chunk})
        if not any(item["type"] == "text" for item in segments):
            raise RuntimeError("Esta parte não contém texto para sintetizar.")
        request_file = destination.with_name(f".supertonic_{uuid.uuid4().hex}.json")
        payload = {
            "output": str(destination),
            "voice": voice,
            "language": "pt",
            "steps": 8,
            "speed": 1.0,
            "segments": segments,
        }
        env = os.environ.copy()
        env["SUPERTONIC_CACHE_DIR"] = str(supertonic_cache())
        try:
            request_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            result = _run_worker_process(
                [str(supertonic_python()), str(Path(__file__).resolve().parent / "tts_engines" / "supertonic_worker.py"),
                 str(request_file)],
                timeout=3600, env=env,
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "Falha sem detalhes")[-900:]
                raise RuntimeError(f"Falha na geração com Supertonic 3: {detail}")
            if not destination.is_file() or destination.stat().st_size < 44:
                raise RuntimeError("Supertonic 3 terminou sem criar um arquivo WAV válido.")
        finally:
            request_file.unlink(missing_ok=True)

    def omnivoice_python() -> Path:
        configured = os.environ.get("SOCIAL_SOUND_OMNIVOICE_PYTHON")
        if configured:
            return Path(configured).expanduser()
        root = Path(__file__).resolve().parent / ".venvs" / "omnivoice"
        return root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    def omnivoice_ready() -> bool:
        python = omnivoice_python()
        hf_cache = Path(os.environ.get(
            "HF_HUB_CACHE",
            Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub",
        ))
        model_cache = hf_cache / "models--k2-fsa--OmniVoice" / "snapshots"
        tokenizer_cache = hf_cache / "models--bosonai--higgs-audio-v2-tokenizer" / "snapshots"
        runtime_root = python.parent.parent
        package_dir = runtime_root / ("Lib/site-packages/omnivoice" if os.name == "nt" else "lib/python3.11/site-packages/omnivoice")
        return (python.is_file() and package_dir.is_dir() and model_cache.is_dir()
                and any(model_cache.iterdir()) and tokenizer_cache.is_dir() and any(tokenizer_cache.iterdir()))

    def render_omnivoice_piece(job, part_index: int, destination: Path):
        if not omnivoice_ready():
            raise RuntimeError("OmniVoice não está instalado. Execute instalar-omnivoice.bat e aceite as licenças para uso não comercial.")
        settings = job.get("settings") or {}
        mode = settings.get("mode", "auto")
        reference_audio = settings.get("reference_audio", "")
        reference_text = settings.get("reference_text", "")
        instruction = settings.get("style", "")
        if mode == "clone":
            candidate = Path(reference_audio).resolve()
            if reference_dir.resolve() not in candidate.parents or not candidate.is_file():
                raise RuntimeError("O áudio de referência não foi encontrado na pasta segura do Social Sound.")
            if not reference_text.strip():
                raise RuntimeError("Informe a transcrição do áudio de referência.")
            reference_audio = str(candidate)
        elif mode == "design" and not instruction.strip():
            raise RuntimeError("Descreva a voz desejada para usar o modo de criação de voz.")
        segments = []
        for segment_type, value in parse_text(job["parts"][part_index]["text"]):
            if segment_type == "pause":
                segments.append({"type": "pause", "seconds": float(value)})
            else:
                for chunk in split_sentences(value):
                    if chunk.strip():
                        segments.append({"type": "text", "text": chunk})
        if not any(item["type"] == "text" for item in segments):
            raise RuntimeError("Esta parte não contém texto para sintetizar.")
        request_file = destination.with_name(f".omnivoice_{uuid.uuid4().hex}.json")
        payload = {"output": str(destination), "mode": mode, "reference_audio": reference_audio,
                   "reference_text": reference_text, "instruction": instruction, "segments": segments}
        try:
            request_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            result = _run_worker_process(
                [str(omnivoice_python()), str(Path(__file__).resolve().parent / "tts_engines" / "omnivoice_worker.py"), str(request_file)],
                timeout=7200, env=os.environ.copy())
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "Falha sem detalhes")[-1200:]
                raise RuntimeError(f"Falha na geração com OmniVoice: {detail}")
            if not destination.is_file() or destination.stat().st_size < 44:
                raise RuntimeError("OmniVoice terminou sem criar um arquivo WAV válido.")
        finally:
            request_file.unlink(missing_ok=True)

    def f5tts_python() -> Path:
        configured = os.environ.get("SOCIAL_SOUND_F5TTS_PYTHON")
        if configured:
            return Path(configured).expanduser()
        root = Path(__file__).resolve().parent / ".venvs" / "f5tts"
        return root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    def f5tts_ready() -> bool:
        python = f5tts_python()
        cache = Path(os.environ.get("HF_HUB_CACHE", Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"))
        model_cache = cache / "models--Cataldir--F5-TTS-pt-br" / "snapshots"
        vocoder_cache = cache / "models--charactr--vocos-mel-24khz" / "snapshots"
        root = python.parent.parent
        package_dir = root / ("Lib/site-packages/f5_tts" if os.name == "nt" else "lib/python3.11/site-packages/f5_tts")
        def contains_required_files(snapshot_root, required):
            if not snapshot_root.is_dir():
                return False
            return any(
                snapshot.is_dir() and all((snapshot / name).is_file() for name in required)
                for snapshot in snapshot_root.iterdir()
            )

        return (
            python.is_file()
            and package_dir.is_dir()
            and contains_required_files(model_cache, ("model_last.safetensors", "vocab.txt"))
            and contains_required_files(vocoder_cache, ("config.yaml", "pytorch_model.bin"))
        )


    def external_segments(text: str):
        segments = []
        for segment_type, value in parse_text(text):
            if segment_type == "pause":
                segments.append({"type": "pause", "seconds": float(value)})
            else:
                for chunk in split_sentences(value):
                    if chunk.strip():
                        segments.append({"type": "text", "text": chunk})
        if not any(item["type"] == "text" for item in segments):
            raise RuntimeError("Esta parte não contém texto para sintetizar.")
        return segments

    def render_external_job(job, folder: Path):
        """Run OmniVoice/F5-TTS once for the whole job, keeping successful part files."""
        engine = job.get("engine")
        settings = job.get("settings") or {}
        if engine == "omnivoice":
            if not omnivoice_ready():
                raise RuntimeError("OmniVoice não está instalado. Execute instalar-omnivoice.bat e aceite as licenças para uso não comercial.")
            mode = settings.get("mode", "auto")
            reference_audio = settings.get("reference_audio", "")
            reference_text = settings.get("reference_text", "")
            instruction = settings.get("style", "")
            if mode == "clone":
                candidate = Path(reference_audio).resolve()
                if reference_dir.resolve() not in candidate.parents or not candidate.is_file():
                    raise RuntimeError("O áudio de referência não foi encontrado na pasta segura do Social Sound.")
                if not reference_text.strip():
                    raise RuntimeError("Informe a transcrição do áudio de referência.")
                reference_audio = str(candidate)
            elif mode == "design" and not instruction.strip():
                raise RuntimeError("Descreva a voz desejada para usar o modo de criação de voz.")
            python, worker, prefix = omnivoice_python(), "omnivoice_worker.py", ".omnivoice_"
            base = {"mode": mode, "reference_audio": reference_audio,
                    "reference_text": reference_text, "instruction": instruction}
        elif engine == "f5tts":
            if not f5tts_ready():
                raise RuntimeError("F5-TTS PT-BR não está instalado. Execute instalar-f5tts.bat e aceite a licença para uso não comercial.")
            candidate = Path(settings.get("reference_audio", "")).resolve()
            if reference_dir.resolve() not in candidate.parents or not candidate.is_file():
                raise RuntimeError("O áudio de referência não foi encontrado na pasta segura do Social Sound.")
            reference_text = settings.get("reference_text", "")
            if not reference_text.strip():
                raise RuntimeError("Informe a transcrição do áudio de referência.")
            python, worker, prefix = f5tts_python(), "f5tts_worker.py", ".f5tts_"
            base = {"reference_audio": str(candidate), "reference_text": reference_text, "steps": 16}
        else:
            raise RuntimeError("Motor externo não reconhecido.")

        pending = []
        for index, part in enumerate(job["parts"]):
            if part.get("status") == "completed" and part.get("audio_path") and valid_audio_file(Path(part["audio_path"])):
                continue
            target = folder / f"parte_{index + 1:03d}.wav"
            db.update_part(job["id"], index, status="processing")
            pending.append({"index": index, "output": str(target),
                            "segments": external_segments(part["text"])})
        if not pending:
            return

        request_file = folder / f"{prefix}{uuid.uuid4().hex}.json"
        payload = {**base, "parts": pending}
        try:
            request_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            result = None
            run_error = None
            try:
                result = _run_worker_process(
                    [str(python), str(Path(__file__).resolve().parent / "tts_engines" / worker), str(request_file)],
                    timeout=7200, env=os.environ.copy())
            except Exception as exc:
                run_error = exc
            # Workers write each part as soon as it finishes. Record those files
            # even if a later part fails or the process times out.
            for item in pending:
                target = Path(item["output"])
                if valid_audio_file(target):
                    db.update_part(job["id"], item["index"], status="completed", audio_path=str(target))
            if run_error is not None:
                raise RuntimeError(f"Falha ao executar {engine}: {run_error}") from run_error
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "Falha sem detalhes")[-1200:]
                raise RuntimeError(f"Falha na geração com {engine}: {detail}")
            missing = [Path(item["output"]).name for item in pending
                       if not valid_audio_file(Path(item["output"]))]
            if missing:
                raise RuntimeError(f"{engine} terminou sem criar WAV válido para: {', '.join(missing)}")
        finally:
            request_file.unlink(missing_ok=True)

    def render_f5tts_piece(job, part_index: int, destination: Path):
        if not f5tts_ready():
            raise RuntimeError("F5-TTS PT-BR não está instalado. Execute instalar-f5tts.bat e aceite a licença para uso não comercial.")
        settings = job.get("settings") or {}
        candidate = Path(settings.get("reference_audio", "")).resolve()
        if reference_dir.resolve() not in candidate.parents or not candidate.is_file():
            raise RuntimeError("O áudio de referência não foi encontrado na pasta segura do Social Sound.")
        reference_text = settings.get("reference_text", "")
        if not reference_text.strip():
            raise RuntimeError("Informe a transcrição do áudio de referência.")
        segments = []
        for segment_type, value in parse_text(job["parts"][part_index]["text"]):
            if segment_type == "pause":
                segments.append({"type": "pause", "seconds": float(value)})
            else:
                for chunk in split_sentences(value):
                    if chunk.strip():
                        segments.append({"type": "text", "text": chunk})
        if not any(item["type"] == "text" for item in segments):
            raise RuntimeError("Esta parte não contém texto para sintetizar.")
        request_file = destination.with_name(f".f5tts_{uuid.uuid4().hex}.json")
        payload = {"output": str(destination), "reference_audio": str(candidate),
                   "reference_text": reference_text, "segments": segments, "steps": 16}
        try:
            request_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            result = _run_worker_process(
                [str(f5tts_python()), str(Path(__file__).resolve().parent / "tts_engines" / "f5tts_worker.py"), str(request_file)],
                timeout=7200, env=os.environ.copy())
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "Falha sem detalhes")[-1200:]
                raise RuntimeError(f"Falha na geração com F5-TTS: {detail}")
            if not destination.is_file() or destination.stat().st_size < 44:
                raise RuntimeError("F5-TTS terminou sem criar um arquivo WAV válido.")
        finally:
            request_file.unlink(missing_ok=True)

    def public_job(job):
        if not job:
            return None
        item = dict(job)
        item["audio_url"] = f"/saidas/narracoes/{job['id']}/completo.wav" if (output_dir / job["id"] / "completo.wav").exists() else None
        for part in item["parts"]:
            path = part.get("audio_path")
            part["audio_url"] = f"/saidas/narracoes/{job['id']}/{Path(path).name}" if path and Path(path).is_file() else None
        return item

    def render_piece(job, part_index: int, destination: Path):
        if job.get("engine") == "supertonic3":
            render_supertonic_piece(job, part_index, destination)
            return
        if job.get("engine") == "omnivoice":
            render_omnivoice_piece(job, part_index, destination)
            return
        if job.get("engine") == "f5tts":
            render_f5tts_piece(job, part_index, destination)
            return
        if job.get("engine") != "voxcpm2":
            raise RuntimeError("Motor de narração não reconhecido.")
        kind, _, key = job["voice"].partition(":")
        style = (job.get("settings") or {}).get("style", "")
        def generate(model):
            if kind == "mine":
                ref = find_mine(key)
                if not ref:
                    raise RuntimeError("A voz salva não foi encontrada.")
                transcript_file = ref.with_suffix(".txt")
                transcript = transcript_file.read_text(encoding="utf-8") if transcript_file.exists() else None
            elif kind == "preset":
                ref = ensure_preset(model, preset_by_id(key))
                transcript = None
            else:
                raise RuntimeError("Tipo de voz inválido.")
            sample_rate = model.tts_model.sample_rate
            pieces = []
            for segment_type, value in parse_text(job["parts"][part_index]["text"]):
                if segment_type == "pause":
                    pieces.append(np.zeros(int(sample_rate * value), dtype=np.float32))
                    continue
                for chunk in split_sentences(value):
                    if not chunk.strip():
                        continue
                    wav = np.asarray(synth(model, chunk, style=style, ref=ref,
                                           transcript=transcript), dtype=np.float32).reshape(-1)
                    wav = np.asarray(tighten(wav, sample_rate), dtype=np.float32).reshape(-1)
                    if wav.size:
                        pieces.append(wav)
            if not pieces:
                raise RuntimeError("O motor não retornou áudio para esta parte.")
            temporary = destination.with_name(f".{destination.stem}.{uuid.uuid4().hex}.tmp.wav")
            try:
                sf.write(str(temporary), np.concatenate(pieces), sample_rate, subtype="PCM_16")
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        with lock:
            run(generate)

    def merge_parts(paths: list[Path], destination: Path):
        audio = []
        sample_rate = None
        for path in paths:
            if not path.is_file():
                raise RuntimeError(f"Arquivo de uma parte não encontrado: {path.name}")
            wav, sr = sf.read(str(path), dtype="float32", always_2d=False)
            if sample_rate is None:
                sample_rate = sr
            elif sr != sample_rate:
                raise RuntimeError("As partes estão com taxas de amostragem diferentes.")
            if wav.ndim > 1:
                wav = wav.mean(axis=1)
            audio.append(wav)
        if not audio:
            raise RuntimeError("Não há partes de áudio para juntar.")
        temp = destination.with_name("." + destination.stem + "." + uuid.uuid4().hex + ".tmp.wav")
        try:
            sf.write(str(temp), np.concatenate(audio), sample_rate, subtype="PCM_16")
            if not valid_audio_file(temp):
                raise RuntimeError("O áudio completo temporário não passou na validação WAV.")
            os.replace(temp, destination)
        finally:
            temp.unlink(missing_ok=True)

    def worker_loop():
        while True:
            job = db.claim_next()
            if job is None:
                time.sleep(0.5)
                continue
            try:
                folder = job_paths(job["id"])
                with inference_guard:
                    if job.get("engine") != "voxcpm2" and unload_engine is not None:
                        unload_engine()
                    if job.get("engine") in {"omnivoice", "f5tts"}:
                        render_external_job(job, folder)
                    else:
                        for index, part in enumerate(job["parts"]):
                            if part.get("status") == "completed" and part.get("audio_path") and valid_audio_file(Path(part["audio_path"])):
                                continue
                            db.update_part(job["id"], index, status="processing")
                            target = folder / f"parte_{index + 1:03d}.wav"
                            render_piece(job, index, target)
                            db.update_part(job["id"], index, status="completed", audio_path=str(target))
                current = db.get(job["id"])
                merge_parts([Path(p["audio_path"]) for p in current["parts"]],
                            folder / "completo.wav")
                db.finish(job["id"])
            except Exception as exc:
                try:
                    db.finish(job["id"], error=str(exc)[:1000])
                except Exception:
                    pass

    def start_worker():
        nonlocal worker_started
        with worker_guard:
            if not worker_started:
                worker_started = True
                threading.Thread(target=worker_loop, name="social-sound-narration-queue", daemon=True).start()

    # A running job from a previous process is not silently resumed.
    db.recover_interrupted()
    start_worker()

    engine_install_lock = threading.Lock()
    engine_install_state = {"job_id": None, "engine": None, "status": "idle", "message": "", "started_at": None, "finished_at": None}
    engine_install_state_guard = threading.Lock()
    engine_install_shutdown = threading.Event()
    engine_install_process_guard = threading.Lock()
    engine_install_process = {"process": None}
    engine_install_thread = {"thread": None}

    def shutdown_engine_installer():
        # A daemon installer must not leave cmd/pip children running after the API exits.
        engine_install_shutdown.set()
        with engine_install_process_guard:
            active_process = engine_install_process["process"]
        if active_process is not None:
            _terminate_process_tree(active_process)
        thread = engine_install_thread["thread"]
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=20)

    router.add_event_handler("shutdown", shutdown_engine_installer)

    def run_engine_installer(engine_id: str, job_id: str, license_accepted: bool):
        scripts = {"supertonic3": "instalar-supertonic.bat", "omnivoice": "instalar-omnivoice.bat", "f5tts": "instalar-f5tts.bat"}
        script_path = Path(__file__).resolve().parent.parent / scripts[engine_id]
        output_tail = []
        process = None
        try:
            if os.name != "nt":
                raise RuntimeError("Instalação automatizada pela interface está disponível no Windows. No Linux, use o instalador correspondente.")
            if not script_path.is_file():
                raise RuntimeError(f"Instalador não encontrado: {script_path.name}")
            env = os.environ.copy()
            env["SOCIAL_SOUND_INSTALL_FROM_UI"] = "1"
            env["SOCIAL_SOUND_LICENSE_ACCEPTED"] = "1" if license_accepted else "0"
            with engine_install_state_guard:
                engine_install_state.update(status="running", message="Preparando instalador…", log_tail="")
            if engine_install_shutdown.is_set():
                raise RuntimeError("Servidor encerrado antes do início da instalação.")
            process = subprocess.Popen(["cmd.exe", "/d", "/c", 'call "' + str(script_path) + '"'], cwd=str(script_path.parent),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                errors="replace", env=env, bufsize=1)
            with engine_install_process_guard:
                engine_install_process["process"] = process
            if engine_install_shutdown.is_set():
                _terminate_process_tree(process)
                raise RuntimeError("Instalação interrompida porque o servidor está sendo encerrado.")
            # Monitorar timeout sem bloquear em readline quando o instalador não emite logs.
            output_queue = queue.Queue()
            def read_output():
                try:
                    for line in process.stdout or ():
                        output_queue.put(line)
                finally:
                    output_queue.put(None)
            reader = threading.Thread(target=read_output, name=f"engine-installer-output-{engine_id}", daemon=True)
            reader.start()
            deadline = time.monotonic() + 14400
            reader_finished = False
            while process.poll() is None or not output_queue.empty() or not reader_finished:
                if engine_install_shutdown.is_set():
                    _terminate_process_tree(process)
                    raise RuntimeError("Instalação interrompida porque o servidor está sendo encerrado.")
                if time.monotonic() > deadline:
                    _terminate_process_tree(process)
                    raise RuntimeError("Instalação excedeu o limite de 4 horas e foi interrompida.")
                try:
                    line = output_queue.get(timeout=0.2)
                except queue.Empty:
                    continue
                if line is None:
                    reader_finished = True
                    continue
                clean = line.strip()
                if clean:
                    output_tail.append(clean)
                    output_tail = output_tail[-40:]
                    with engine_install_state_guard:
                        engine_install_state.update(message=clean[:500], log_tail="\\n".join(output_tail))
            reader.join(timeout=2)
            code = process.wait()
            if code != 0:
                detail = "\\n".join(output_tail[-12:]) or f"Instalador terminou com código {code}"
                raise RuntimeError(detail)
            with engine_install_state_guard:
                engine_install_state.update(status="completed", message="Instalação concluída e verificada.", log_tail="\\n".join(output_tail), finished_at=time.time())
        except Exception as exc:
            with engine_install_state_guard:
                engine_install_state.update(status="error", message=str(exc)[:1500], log_tail="\\n".join(output_tail[-40:]), finished_at=time.time())
        finally:
            _terminate_process_tree(process)
            with engine_install_process_guard:
                if engine_install_process["process"] is process:
                    engine_install_process["process"] = None
            engine_install_lock.release()

    @router.post("/engines/{engine_id}/install")
    def install_engine(engine_id: str, payload: dict):
        if engine_id not in {"supertonic3", "omnivoice", "f5tts"}:
            raise HTTPException(status_code=400, detail="Motor não permitido para instalação opcional.")
        accepted = payload.get("license_accepted") is True
        if not accepted:
            raise HTTPException(status_code=400, detail="Confirme a leitura e aceitação dos avisos/licenças antes de instalar.")
        if engine_id in {"omnivoice", "f5tts"} and payload.get("non_commercial_ack") is not True:
            raise HTTPException(status_code=400, detail="Este motor é restrito a uso não comercial. Confirme essa condição para continuar.")
        if not engine_install_lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="Outra instalação de motor está em andamento. Aguarde.")
        job_id = uuid.uuid4().hex
        with engine_install_state_guard:
            engine_install_state.update(job_id=job_id, engine=engine_id, status="queued", message="Instalação enfileirada.", started_at=time.time(), finished_at=None)
        installer_thread = threading.Thread(target=run_engine_installer, args=(engine_id, job_id, accepted), daemon=True)
        engine_install_thread["thread"] = installer_thread
        try:
            installer_thread.start()
        except Exception as exc:
            with engine_install_state_guard:
                engine_install_state.update(status="error", message=f"Não foi possível iniciar a instalação: {str(exc)[:500]}", finished_at=time.time())
            engine_install_lock.release()
            raise HTTPException(status_code=500, detail="Não foi possível iniciar o processo de instalação.") from exc
        return {"job_id": job_id, "status": "queued"}

    @router.get("/engines/install/{job_id}")
    def engine_install_status(job_id: str):
        with engine_install_state_guard:
            if engine_install_state.get("job_id") != job_id:
                raise HTTPException(status_code=404, detail="Instalação não encontrada.")
            return dict(engine_install_state)

    @router.get("/engines")
    def list_engines():
        from tts_engine_catalog import public_catalog
        return {"engines": public_catalog(supertonic_installed=supertonic_ready(), omnivoice_installed=omnivoice_ready(), f5tts_installed=f5tts_ready())}

    @router.post("/split")
    def split_text(payload: EnqueueRequest):
        return {"parts": split_for_duration(payload.text, payload.target_seconds, payload.chars_per_minute),
                "target_seconds": payload.target_seconds,
                "estimated": True}

    @router.get("/jobs")
    def list_jobs():
        return {"jobs": [public_job(job) for job in db.list_jobs()]}

    @router.get("/queue/status")
    def queue_status():
        return {"paused": db.is_paused(), "pause_behavior": "after_current_job"}

    @router.post("/queue/pause")
    def pause_queue():
        db.set_paused(True)
        return {"paused": True, "message": "A fila pausa depois que a narração atual terminar."}

    @router.post("/queue/resume")
    def resume_queue():
        db.set_paused(False)
        return {"paused": False}

    @router.post("/omnivoice/reference")
    async def upload_omnivoice_reference(file: UploadFile = File(...)):
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".wav", ".flac", ".ogg"}:
            raise HTTPException(400, "Use um arquivo de áudio WAV, FLAC ou OGG.")
        raw = await file.read(25 * 1024 * 1024 + 1)
        if len(raw) > 25 * 1024 * 1024:
            raise HTTPException(413, "O áudio de referência deve ter no máximo 25 MB.")
        destination = reference_dir / f"{uuid.uuid4().hex}{suffix}"
        try:
            destination.write_bytes(raw)
            info = sf.info(str(destination))
            if info.frames <= 0 or info.samplerate < 8000 or info.channels > 2:
                raise ValueError("Áudio inválido ou com formato não suportado.")
        except Exception as exc:
            destination.unlink(missing_ok=True)
            raise HTTPException(400, f"Não foi possível ler o áudio de referência: {exc}")
        return {"reference_audio": str(destination), "filename": Path(file.filename or "referencia").name}

    @router.post("/jobs")
    def enqueue(payload: EnqueueRequest):
        parts = split_for_duration(payload.text, payload.target_seconds, payload.chars_per_minute)
        if not parts:
            raise HTTPException(400, "Digite um texto antes de adicionar à fila.")
        if payload.engine == "voxcpm2":
            if payload.voice.startswith("preset:"):
                preset_by_id(payload.voice.split(":", 1)[1])
            elif payload.voice.startswith("mine:"):
                if not find_mine(payload.voice.split(":", 1)[1]):
                    raise HTTPException(404, "A voz salva não foi encontrada.")
            else:
                raise HTTPException(400, "Selecione uma voz válida para o VoxCPM2.")
        elif payload.engine == "f5tts":
            if not f5tts_ready():
                raise HTTPException(409, "F5-TTS PT-BR não está instalado. Execute instalar-f5tts.bat.")
            candidate = Path(payload.reference_audio).resolve()
            if reference_dir.resolve() not in candidate.parents or not candidate.is_file():
                raise HTTPException(400, "Envie um áudio de referência válido pelo campo próprio do F5-TTS.")
            if not payload.reference_text.strip():
                raise HTTPException(400, "Informe a transcrição do áudio de referência.")
        elif payload.engine == "omnivoice":
            if not omnivoice_ready():
                raise HTTPException(409, "OmniVoice não está instalado. Execute instalar-omnivoice.bat.")
            if payload.mode == "clone":
                candidate = Path(payload.reference_audio).resolve()
                if reference_dir.resolve() not in candidate.parents or not candidate.is_file():
                    raise HTTPException(400, "Envie um áudio de referência válido pelo campo próprio do OmniVoice.")
                if not payload.reference_text.strip():
                    raise HTTPException(400, "Informe a transcrição do áudio de referência.")
            elif payload.mode == "design" and not payload.style.strip():
                raise HTTPException(400, "Descreva a voz desejada para usar o modo de criação de voz.")
        elif payload.engine == "supertonic3":
            if not supertonic_ready():
                raise HTTPException(409, "Supertonic 3 não está instalado. Execute instalar-supertonic.bat.")
            voice_id = payload.voice.removeprefix("supertonic:")
            if payload.voice != f"supertonic:{voice_id}" or voice_id not in {"M1","M2","M3","M4","M5","F1","F2","F3","F4","F5"}:
                raise HTTPException(400, "Selecione uma voz predefinida válida do Supertonic 3.")
        else:
            raise HTTPException(400, "Motor de narração inválido.")
        job = db.enqueue(payload.text, payload.voice, payload.engine, parts,
                         {"style": payload.style, "target_seconds": payload.target_seconds,
                          "chars_per_minute": payload.chars_per_minute, "mode": payload.mode,
                          "reference_audio": payload.reference_audio, "reference_text": payload.reference_text})
        return public_job(job)

    @router.get("/jobs/{job_id}")
    def get_job(job_id: str):
        job = db.get(job_id)
        if not job:
            raise HTTPException(404, "Narração não encontrada.")
        return public_job(job)

    @router.get("/jobs/{job_id}/candidates")
    def list_candidates(job_id: str):
        if not db.get(job_id):
            raise HTTPException(404, "Narração não encontrada.")
        items = []
        for candidate in db.list_candidates(job_id):
            candidate["audio_url"] = f"/saidas/narracoes/{job_id}/{Path(candidate['audio_path']).name}"
            items.append(candidate)
        return {"candidates": items}

    @router.delete("/jobs/{job_id}")
    def remove_job(job_id: str):
        if not db.remove_queued(job_id):
            raise HTTPException(409, "Só é possível remover narrações que ainda estão na fila.")
        return {"ok": True}

    @router.post("/jobs/{job_id}/move-up")
    def move_job_up(job_id: str):
        try:
            return public_job(db.move(job_id, "up"))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/jobs/{job_id}/move-down")
    def move_job_down(job_id: str):
        try:
            return public_job(db.move(job_id, "down"))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/jobs/{job_id}/requeue")
    def requeue(job_id: str):
        try:
            return public_job(db.requeue(job_id))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    def _regenerate_part(job_id: str, part_index: int):
        job = db.get(job_id)
        if not job:
            raise HTTPException(404, "Narração não encontrada.")
        if job["status"] != "completed":
            raise HTTPException(409, "Conclua a narração antes de regenerar uma parte.")
        if not 0 <= part_index < len(job["parts"]):
            raise HTTPException(404, "Parte não encontrada.")
        if any(item["part_index"] == part_index for item in db.list_candidates(job_id)):
            raise HTTPException(409, "Esta parte já tem uma versão aguardando aprovação.")
        candidate_path = job_paths(job_id) / f"candidata_{part_index + 1:03d}_{uuid.uuid4().hex[:8]}.wav"
        try:
            # Keep the duplicate-candidate check, rendering, and staging under
            # the same inference lock. Otherwise concurrent requests can both
            # pass the initial check and create multiple pending candidates.
            with inference_guard:
                if any(item["part_index"] == part_index for item in db.list_candidates(job_id)):
                    raise HTTPException(409, "Esta parte já tem uma versão aguardando aprovação.")
                job = db.get(job_id)
                if not job or job["status"] != "completed":
                    raise HTTPException(409, "A narração não está mais concluída.")
                if job.get("engine") != "voxcpm2" and unload_engine is not None:
                    unload_engine()
                render_piece(job, part_index, candidate_path)
                candidate_id = db.stage_candidate(job_id, part_index, str(candidate_path))
            return {"candidate_id": candidate_id, "part_index": part_index,
                    "audio_url": f"/saidas/narracoes/{job_id}/{candidate_path.name}",
                    "status": "awaiting_approval"}
        except HTTPException:
            candidate_path.unlink(missing_ok=True)
            raise
        except Exception as exc:
            candidate_path.unlink(missing_ok=True)
            raise HTTPException(500, f"Não foi possível regenerar a parte: {str(exc)[:400]}") from exc

    @router.post("/jobs/{job_id}/parts/{part_index}/regenerate")
    def regenerate_part(job_id: str, part_index: int):
        # Prevent concurrent requests from staging multiple pending candidates
        # for the same part while preserving approval concurrency separately.
        with candidate_guard:
            return _regenerate_part(job_id, part_index)

    def _approve_candidate(candidate_id: str):
        candidate = db.candidate(candidate_id)
        if not candidate or candidate["status"] != "awaiting_approval":
            raise HTTPException(404, "Versão candidata não encontrada ou já analisada.")
        job = db.get(candidate["job_id"])
        if not job:
            raise HTTPException(404, "Narração não encontrada.")
        paths = [Path(part["audio_path"]) for part in job["parts"]]
        paths[candidate["part_index"]] = Path(candidate["audio_path"])
        full_path = job_paths(job["id"]) / "completo.wav"
        temp_full = full_path.with_name("completo_aprovacao.tmp.wav")
        backup_full = full_path.with_name(f".completo_rollback_{uuid.uuid4().hex}.wav")
        backup_created = False
        try:
            merge_parts(paths, temp_full)
            # Keep the published audio intact until the replacement file is ready.
            if full_path.is_file():
                shutil.copy2(full_path, backup_full)
                backup_created = True
            os.replace(temp_full, full_path)
            try:
                approved = db.approve_candidate(candidate_id)
            except Exception:
                # If the database update fails, restore the previously published audio.
                if backup_created:
                    os.replace(backup_full, full_path)
                    backup_created = False
                else:
                    full_path.unlink(missing_ok=True)
                raise
            if backup_created:
                try:
                    backup_full.unlink(missing_ok=True)
                except OSError:
                    # Cleanup must not turn a completed approval into a reported failure.
                    pass
                backup_created = False
            return public_job(approved)
        except Exception as exc:
            temp_full.unlink(missing_ok=True)
            # Preserve the rollback copy if restoration itself failed; it may be
            # needed to recover the user's previously published narration.
            detail = str(exc)
            if backup_created and backup_full.is_file():
                detail += f" (cópia de segurança preservada em {backup_full.name})"
            raise HTTPException(500, f"Não foi possível aprovar a versão: {detail[:600]}") from exc

    @router.post("/candidates/{candidate_id}/approve")
    def approve_candidate(candidate_id: str):
        # Lock regeneration first, then approval, so no new candidate can be
        # staged between sibling invalidation and file cleanup.
        with candidate_guard:
            with approval_guard:
                candidate = db.candidate(candidate_id)
                if not candidate or candidate["status"] != "awaiting_approval":
                    raise HTTPException(404, "Versão candidata não encontrada ou já analisada.")
                siblings = db.list_candidates(candidate["job_id"])
                approved = _approve_candidate(candidate_id)
                # Approval discards sibling candidates in SQLite; remove their files too.
                job_folder = job_paths(candidate["job_id"]).resolve()
                for sibling in siblings:
                    if sibling["id"] == candidate_id:
                        continue
                    try:
                        stale_path = Path(sibling["audio_path"]).resolve()
                        if stale_path.parent == job_folder and stale_path.is_file():
                            stale_path.unlink(missing_ok=True)
                    except OSError as cleanup_error:
                        print(f"Warning: stale candidate cleanup failed: {cleanup_error}", file=sys.stderr)
                return approved

    @router.post("/candidates/{candidate_id}/discard")
    def discard_candidate(candidate_id: str):
        # Serialize with regeneration and approval so candidate files/state cannot
        # be deleted or invalidated while another request is staging/publishing.
        with candidate_guard:
            with approval_guard:
                try:
                    candidate = db.candidate(candidate_id)
                    db.discard_candidate(candidate_id)
                    if candidate:
                        try:
                            Path(candidate["audio_path"]).unlink(missing_ok=True)
                        except OSError as cleanup_error:
                            # The discard is committed; report cleanup only as a warning.
                            print(f"Warning: discarded candidate file cleanup failed: {cleanup_error}", file=sys.stderr)
                    return {"ok": True}
                except KeyError as exc:
                    raise HTTPException(404, "Versão candidata não encontrada ou já analisada.") from exc

    return router
