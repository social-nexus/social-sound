"""API and sequential worker for long-form VoxCPM2 narrations."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from narration_queue import NarrationQueue, split_for_duration


class EnqueueRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200000)
    voice: str = Field(default="preset:narrador-grave", min_length=1, max_length=180)
    style: str = Field(default="", max_length=500)
    target_seconds: int = Field(default=60, ge=15, le=300)
    chars_per_minute: int = Field(default=850, ge=300, le=1500)
    engine: str = Field(default="voxcpm2", pattern="^(voxcpm2|supertonic3)$")


def create_narration_router(*, lock, run, synth, ensure_preset, preset_by_id,
                            find_mine, parse_text, split_sentences, tighten, data_dir: Path, output_dir: Path):
    router = APIRouter(prefix="/api/narration", tags=["narracao"])
    db = NarrationQueue(data_dir / "narration_queue.sqlite3")
    output_dir.mkdir(parents=True, exist_ok=True)
    worker_guard = threading.Lock()
    worker_started = False

    def job_paths(job_id: str):
        folder = output_dir / job_id
        folder.mkdir(parents=True, exist_ok=True)
        return folder

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
            result = subprocess.run(
                [str(supertonic_python()), str(Path(__file__).resolve().parent / "tts_engines" / "supertonic_worker.py"),
                 str(request_file)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=3600, env=env, check=False,
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "Falha sem detalhes")[-900:]
                raise RuntimeError(f"Falha na geração com Supertonic 3: {detail}")
            if not destination.is_file() or destination.stat().st_size < 44:
                raise RuntimeError("Supertonic 3 terminou sem criar um arquivo WAV válido.")
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
            sf.write(str(destination), np.concatenate(pieces), sample_rate, subtype="PCM_16")
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
        temp = destination.with_name(destination.stem + ".tmp.wav")
        sf.write(str(temp), np.concatenate(audio), sample_rate, subtype="PCM_16")
        os.replace(temp, destination)

    def worker_loop():
        while True:
            job = db.claim_next()
            if job is None:
                time.sleep(0.5)
                continue
            try:
                folder = job_paths(job["id"])
                for index, part in enumerate(job["parts"]):
                    if part.get("status") == "completed" and part.get("audio_path") and Path(part["audio_path"]).is_file():
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

    @router.get("/engines")
    def list_engines():
        from tts_engine_catalog import public_catalog
        return {"engines": public_catalog(supertonic_installed=supertonic_ready())}

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
                          "chars_per_minute": payload.chars_per_minute})
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

    @router.post("/jobs/{job_id}/parts/{part_index}/regenerate")
    def regenerate_part(job_id: str, part_index: int):
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
            render_piece(job, part_index, candidate_path)
            candidate_id = db.stage_candidate(job_id, part_index, str(candidate_path))
            return {"candidate_id": candidate_id, "part_index": part_index,
                    "audio_url": f"/saidas/narracoes/{job_id}/{candidate_path.name}",
                    "status": "awaiting_approval"}
        except Exception as exc:
            candidate_path.unlink(missing_ok=True)
            raise HTTPException(500, f"Não foi possível regenerar a parte: {str(exc)[:400]}") from exc

    @router.post("/candidates/{candidate_id}/approve")
    def approve_candidate(candidate_id: str):
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
        try:
            merge_parts(paths, temp_full)
            approved = db.approve_candidate(candidate_id)
            os.replace(temp_full, full_path)
            return public_job(approved)
        except Exception as exc:
            temp_full.unlink(missing_ok=True)
            raise HTTPException(500, f"Não foi possível aprovar a versão: {str(exc)[:400]}") from exc

    @router.post("/candidates/{candidate_id}/discard")
    def discard_candidate(candidate_id: str):
        try:
            candidate = db.candidate(candidate_id)
            db.discard_candidate(candidate_id)
            if candidate:
                Path(candidate["audio_path"]).unlink(missing_ok=True)
            return {"ok": True}
        except KeyError as exc:
            raise HTTPException(404, "Versão candidata não encontrada ou já analisada.") from exc

    return router
