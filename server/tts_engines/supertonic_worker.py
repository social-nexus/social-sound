"""Isolated Supertonic 3 runtime entry point.

This script is executed only by the optional Supertonic virtual environment.
It never imports PyTorch or VoxCPM modules.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

import numpy as np
import soundfile as sf
from supertonic import TTS


def main() -> int:
    if len(sys.argv) != 2:
        print("Uso: supertonic_worker.py --download | payload.json", file=sys.stderr)
        return 2

    configured_cache = os.environ.get("SUPERTONIC_CACHE_DIR")
    if not configured_cache:
        print("SUPERTONIC_CACHE_DIR não foi configurado.", file=sys.stderr)
        return 2
    cache_dir = Path(configured_cache).expanduser()
    cache_dir.mkdir(parents=True, exist_ok=True)

    if sys.argv[1] == "--download":
        tts = TTS(model="supertonic-3", model_dir=cache_dir, auto_download=True)
        print("Modelo Supertonic 3 instalado. Vozes: " + ", ".join(tts.voice_style_names))
        return 0

    payload_path = Path(sys.argv[1])
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    output_path = Path(payload["output"]).resolve()
    tts = TTS(model="supertonic-3", model_dir=cache_dir, auto_download=False)
    voice = str(payload.get("voice", "M1"))
    if voice not in tts.voice_style_names:
        raise ValueError(f"Voz Supertonic inválida: {voice}")
    style = tts.get_voice_style(voice)
    language = str(payload.get("language", "pt"))
    chunks: list[np.ndarray] = []
    for segment in payload["segments"]:
        if segment["type"] == "pause":
            chunks.append(np.zeros(int(tts.sample_rate * float(segment["seconds"])), dtype=np.float32))
            continue
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        wav, _duration = tts.synthesize(
            text=text,
            voice_style=style,
            lang=language,
            total_steps=int(payload.get("steps", 8)),
            speed=float(payload.get("speed", 1.0)),
        )
        audio = np.asarray(wav, dtype=np.float32).reshape(-1)
        if audio.size:
            chunks.append(audio)

    if not chunks:
        raise RuntimeError("O Supertonic não retornou áudio para esta parte.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.stem}.{uuid.uuid4().hex}.tmp.wav")
    try:
        sf.write(str(temporary), np.concatenate(chunks), tts.sample_rate, subtype="PCM_16")
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Erro no Supertonic 3: {exc}", file=sys.stderr)
        raise SystemExit(1)
