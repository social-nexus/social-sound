"""Isolated F5-TTS PT-BR worker. Official checkpoint is non-commercial."""
import gc, json, os, sys
from pathlib import Path
import numpy as np
import soundfile as sf
import torch
from cached_path import cached_path
from f5_tts.api import F5TTS

CHECKPOINT = "hf://Cataldir/F5-TTS-pt-br/model_last.safetensors"
VOCAB = "hf://Cataldir/F5-TTS-pt-br/vocab.txt"

def cache_dir():
    if os.environ.get("HF_HUB_CACHE"):
        return os.environ["HF_HUB_CACHE"]
    return str(Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub")

def load(force_cpu=False):
    device = "cpu" if force_cpu or not torch.cuda.is_available() else "cuda"
    print(f"Carregando F5-TTS PT-BR em {device}...", file=sys.stderr)
    return F5TTS(device=device, ckpt_file=CHECKPOINT, vocab_file=VOCAB, hf_cache_dir=cache_dir())

def main():
    if len(sys.argv) != 2:
        return 2
    if sys.argv[1] == "--download":
        for uri in (CHECKPOINT, VOCAB,
                    "hf://charactr/vocos-mel-24khz/config.yaml",
                    "hf://charactr/vocos-mel-24khz/pytorch_model.bin"):
            print(cached_path(uri, cache_dir=cache_dir()))
        return 0
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    try:
        model = load()
    except torch.cuda.OutOfMemoryError:
        gc.collect()
        if torch.cuda.is_available(): torch.cuda.empty_cache()
        model = load(force_cpu=True)
    pieces = []
    sample_rate = model.target_sample_rate
    for segment in payload["segments"]:
        if segment["type"] == "pause":
            pieces.append(np.zeros(int(sample_rate * float(segment["seconds"])), dtype=np.float32))
            continue
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        try:
            wav, sr, _ = model.infer(
                ref_file=payload["reference_audio"],
                ref_text=payload["reference_text"],
                gen_text=text,
                nfe_step=int(payload.get("steps", 16)),
                speed=1.0,
                remove_silence=False,
            )
        except torch.cuda.OutOfMemoryError:
            if str(model.device).startswith("cpu"):
                raise
            del model
            gc.collect()
            torch.cuda.empty_cache()
            model = load(force_cpu=True)
            wav, sr, _ = model.infer(
                ref_file=payload["reference_audio"],
                ref_text=payload["reference_text"],
                gen_text=text,
                nfe_step=int(payload.get("steps", 16)),
                speed=1.0,
                remove_silence=False,
            )
        sample_rate = int(sr)
        pieces.append(np.asarray(wav, dtype=np.float32).reshape(-1))
    if not pieces:
        raise RuntimeError("F5-TTS não gerou áudio.")
    output = Path(payload["output"]).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output), np.concatenate(pieces), sample_rate, subtype="PCM_16")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Erro no F5-TTS: {exc}", file=sys.stderr)
        raise SystemExit(1)
