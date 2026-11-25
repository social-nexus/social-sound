"""Optional OmniVoice inference worker (non-commercial model weights)."""
import gc, json, os, sys
from pathlib import Path
import numpy as np
import soundfile as sf
import torch
from huggingface_hub import snapshot_download
from omnivoice import OmniVoice

MODEL = "k2-fsa/OmniVoice"
TOKENIZER = "bosonai/higgs-audio-v2-tokenizer"

def load(force_cpu=False):
    use_cuda = not force_cpu and os.environ.get("SOCIAL_SOUND_OMNIVOICE_DEVICE", "auto").lower() != "cpu" and torch.cuda.is_available()
    device = "cuda:0" if use_cuda else "cpu"
    return OmniVoice.from_pretrained(MODEL, device_map=device, dtype=torch.float16 if use_cuda else torch.float32)

def generate(model, item):
    args = {"text": item["text"], "language": "Portuguese", "num_step": 32, "speed": 1.0}
    if item["mode"] == "clone":
        args.update(ref_audio=item["reference_audio"], ref_text=item["reference_text"])
    elif item["mode"] == "design":
        args["instruct"] = item["instruction"]
    elif item["mode"] != "auto":
        raise ValueError("Modo OmniVoice inválido.")
    audio = model.generate(**args)
    if not audio:
        raise RuntimeError("OmniVoice não retornou áudio.")
    return np.asarray(audio[0], dtype=np.float32).reshape(-1)

def main():
    if len(sys.argv) != 2:
        return 2
    if sys.argv[1] == "--download":
        print(snapshot_download(repo_id=MODEL))
        print(snapshot_download(repo_id=TOKENIZER))
        return 0
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    try:
        model = load()
    except torch.cuda.OutOfMemoryError:
        gc.collect()
        if torch.cuda.is_available(): torch.cuda.empty_cache()
        model = load(force_cpu=True)
    chunks = []
    for segment in payload["segments"]:
        if segment["type"] == "pause":
            chunks.append(np.zeros(int(model.sampling_rate * float(segment["seconds"])), dtype=np.float32))
            continue
        item = dict(payload)
        item["text"] = str(segment.get("text", "")).strip()
        if not item["text"]: continue
        try:
            chunks.append(generate(model, item))
        except torch.cuda.OutOfMemoryError:
            if str(model.device).startswith("cpu"): raise
            del model
            gc.collect()
            torch.cuda.empty_cache()
            model = load(force_cpu=True)
            chunks.append(generate(model, item))
    if not chunks: raise RuntimeError("OmniVoice não gerou áudio.")
    output = Path(payload["output"]).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output), np.concatenate(chunks), model.sampling_rate, subtype="PCM_16")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Erro no OmniVoice: {exc}", file=sys.stderr)
        raise SystemExit(1)
