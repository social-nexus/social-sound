"""Isolated F5-TTS PT-BR worker. Official checkpoint is non-commercial."""
import gc, json, os, sys, tempfile, uuid
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
    # F5TTS accepts local checkpoint/vocabulary paths. Resolve hf:// URIs
    # explicitly; unlike its default model path, custom ckpt_file/vocab_file
    # values are not resolved by the constructor.
    checkpoint_path = cached_path(CHECKPOINT, cache_dir=cache_dir())
    vocab_path = cached_path(VOCAB, cache_dir=cache_dir())
    return F5TTS(device=device, ckpt_file=str(checkpoint_path),
                 vocab_file=str(vocab_path), hf_cache_dir=cache_dir())

def prepare_reference_audio(source):
    """Normalize supported uploads to WAV so F5-TTS does not need FFmpeg codecs."""
    audio, sample_rate = sf.read(str(source), dtype="float32", always_2d=True)
    handle = tempfile.NamedTemporaryFile(prefix="social_sound_f5_ref_", suffix=".wav", delete=False)
    handle.close()
    try:
        sf.write(handle.name, audio, int(sample_rate), subtype="PCM_16")
    except Exception:
        Path(handle.name).unlink(missing_ok=True)
        raise
    return Path(handle.name)


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
    reference_wav = prepare_reference_audio(payload["reference_audio"])
    try:
        def render_segments(segments):
            nonlocal model
            pieces = []
            sample_rate = model.target_sample_rate
            for segment in segments:
                if segment["type"] == "pause":
                    pieces.append(np.zeros(int(sample_rate * float(segment["seconds"])), dtype=np.float32))
                    continue
                text = str(segment.get("text", "")).strip()
                if not text:
                    continue
                try:
                    wav, sr, _ = model.infer(
                        ref_file=str(reference_wav), ref_text=payload["reference_text"],
                        gen_text=text, nfe_step=int(payload.get("steps", 16)),
                        speed=1.0, remove_silence=False)
                except torch.cuda.OutOfMemoryError:
                    if str(model.device).startswith("cpu"):
                        raise
                    del model
                    gc.collect()
                    torch.cuda.empty_cache()
                    model = load(force_cpu=True)
                    wav, sr, _ = model.infer(
                        ref_file=str(reference_wav), ref_text=payload["reference_text"],
                        gen_text=text, nfe_step=int(payload.get("steps", 16)),
                        speed=1.0, remove_silence=False)
                sample_rate = int(sr)
                pieces.append(np.asarray(wav, dtype=np.float32).reshape(-1))
            if not pieces:
                raise RuntimeError("F5-TTS não gerou áudio para uma das partes.")
            return np.concatenate(pieces), sample_rate

        jobs = payload.get("parts") or [{"output": payload["output"], "segments": payload["segments"]}]
        for part in jobs:
            audio, sample_rate = render_segments(part["segments"])
            output = Path(part["output"]).resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.tmp.wav")
            try:
                sf.write(str(temporary), audio, sample_rate, subtype="PCM_16")
                os.replace(temporary, output)
            finally:
                temporary.unlink(missing_ok=True)
    finally:
        reference_wav.unlink(missing_ok=True)
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Erro no F5-TTS: {exc}", file=sys.stderr)
        raise SystemExit(1)
