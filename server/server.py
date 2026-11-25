"""Social Sound - servidor local de voz (VoxCPM2: clonagem + vozes padrão por Voice Design)."""
import base64, gc, io, os, random, re, threading
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

BASE = Path(__file__).parent
VOICES_DIR = BASE / "voices"
PRESETS_DIR = VOICES_DIR / "_padrao"
VOICES_DIR.mkdir(exist_ok=True)
PRESETS_DIR.mkdir(exist_ok=True)
SAIDAS = BASE / "saidas"  # áudios gerados na aba Diálogo
SAIDAS.mkdir(exist_ok=True)
EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}

CFG = float(os.environ.get("CFG", "2.0"))
STEPS = int(os.environ.get("STEPS", "10"))
MAX_CHUNK = 250
DEVICE = os.environ.get("DEVICE", "cuda" if torch.cuda.is_available() else "cpu")

SAMPLE_TEXT = "Olá! Esta é a minha voz. Eu vou narrar a sua história com clareza, ritmo e emoção, do começo ao fim."

# O VoxCPM2 não traz vozes prontas. As vozes padrão são criadas uma vez por Voice Design
# (descrição em texto), salvas em voices/_padrao e depois reutilizadas como referência.
PRESETS = [
    dict(id="narrador-grave", label="Narrador Grave", gender="Masc", desc="Grave e firme, estilo documentário",
         design="adult man, deep and steady voice, documentary narrator, calm pace"),
    dict(id="narradora-suave", label="Narradora Suave", gender="Fem", desc="Suave e acolhedora, ritmo calmo",
         design="adult woman, soft and warm voice, calm and soothing pace"),
    dict(id="locutor-energico", label="Locutor Energético", gender="Masc", desc="Jovem, animado, estilo YouTube",
         design="young man, energetic and clear voice, upbeat YouTuber presenter"),
    dict(id="locutora-animada", label="Locutora Animada", gender="Fem", desc="Jovem, alegre e expressiva",
         design="young woman, cheerful and expressive voice, lively pace"),
    dict(id="contador-historias", label="Contador de Histórias", gender="Masc", desc="Caloroso e envolvente",
         design="middle-aged man, warm and engaging voice, captivating storyteller"),
    dict(id="voz-epica", label="Voz Épica", gender="Masc", desc="Profunda e dramática, estilo trailer",
         design="man, very deep and dramatic voice, epic movie trailer narrator"),
]

_model = None
_device = DEVICE
_lock = threading.Lock()


def get_model():
    global _model
    if _model is None:
        from voxcpm import VoxCPM
        print(f"Carregando VoxCPM2 em {_device}...")
        # optimize=False evita o torch.compile, que costuma dar problema no Windows
        _model = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False, optimize=False, device=_device)
    return _model


def run(fn):
    """Executa fn(model); se faltar memória na GPU, recarrega na CPU e tenta de novo."""
    global _model, _device
    try:
        return fn(get_model())
    except torch.cuda.OutOfMemoryError:
        print("Sem memória na GPU. Mudando para a CPU (mais lento)...")
        _model, _device = None, "cpu"
        gc.collect()
        torch.cuda.empty_cache()
        return fn(get_model())


def synth(model, text, style="", ref=None, transcript=None, seed=None):
    t = f"({style}){text}" if style else text
    kw = dict(text=t, cfg_value=CFG, inference_timesteps=STEPS)
    if ref:
        if transcript and not style:  # clonagem máxima (referência + transcrição)
            kw.update(prompt_wav_path=str(ref), prompt_text=transcript, reference_wav_path=str(ref))
        else:  # clonagem controlável (aceita estilo)
            kw.update(reference_wav_path=str(ref))
    if seed is not None:
        # O VoxCPM.generate() não aceita o argumento "seed": fixamos a semente direto no random/numpy/torch.
        random.seed(seed)
        np.random.seed(seed % (2**32))
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    return np.asarray(model.generate(**kw), dtype=np.float32).reshape(-1)


def preset_by_id(pid):
    for p in PRESETS:
        if p["id"] == pid:
            return p
    raise HTTPException(404, "Voz padrão não encontrada.")


def ensure_preset(model, preset, force=False):
    path = PRESETS_DIR / f"{preset['id']}.wav"
    if force or not path.exists():
        wav = synth(model, SAMPLE_TEXT, style=preset["design"], seed=random.randint(1, 10**6))
        sf.write(str(path), wav, model.tts_model.sample_rate)
    return path


def find_mine(name):
    for p in VOICES_DIR.iterdir():
        if p.is_file() and p.suffix.lower() in EXTS and p.stem == name:
            return p
    return None


app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/voices")
def voices():
    mine = [
        dict(name=p.stem, has_transcript=p.with_suffix(".txt").exists())
        for p in sorted(VOICES_DIR.iterdir())
        if p.is_file() and p.suffix.lower() in EXTS
    ]
    presets = [dict(id=p["id"], label=p["label"], gender=p["gender"], desc=p["desc"]) for p in PRESETS]
    return dict(presets=presets, mine=mine, device=_device)


@app.post("/voices")
async def upload_voice(file: UploadFile = File(...), name: str = Form(""), transcript: str = Form("")):
    stem = re.sub(r"[^\w\- ]", "", name or Path(file.filename).stem).strip() or "voz"
    ext = Path(file.filename).suffix.lower()
    if ext not in EXTS:
        raise HTTPException(400, "Formato não suportado. Use WAV ou MP3.")
    for old in VOICES_DIR.glob(f"{stem}.*"):
        if old.is_file():
            old.unlink()
    (VOICES_DIR / f"{stem}{ext}").write_bytes(await file.read())
    if transcript.strip():
        (VOICES_DIR / f"{stem}.txt").write_text(transcript.strip(), encoding="utf-8")
    return dict(name=stem)


@app.delete("/voices/{name}")
def delete_voice(name: str):
    p = find_mine(name)
    if not p:
        raise HTTPException(404, "Voz não encontrada.")
    p.unlink()
    p.with_suffix(".txt").unlink(missing_ok=True)
    return dict(ok=True)


@app.post("/presets/{pid}/regenerate")
def regenerate_preset(pid: str):
    preset = preset_by_id(pid)
    with _lock:
        run(lambda m: ensure_preset(m, preset, force=True))
    return dict(ok=True)


def split_sentences(text):
    sents = re.findall(r"[^.!?]+[.!?]+(?:\s+|$)|[^.!?]+$", text) or [text]
    chunks, cur = [], ""
    for s in (x.strip() for x in sents):
        if not s:
            continue
        if len(cur) + len(s) + 1 <= MAX_CHUNK:
            cur = f"{cur} {s}".strip()
        else:
            if cur:
                chunks.append(cur)
            cur = s
    if cur:
        chunks.append(cur)
    return chunks


PAUSE_RE = re.compile(
    r"<(short|long) pause>|<pause\s+(\d+(?:[.,]\d+)?)\s*s(?:ec(?:onds?)?)?>|\[(pausa[^\]]*)\]", re.I
)


def parse_text(text, para_pause=0.8):
    """Pausas: <short pause> 0,5 s, <long pause> 1,2 s, <pause 1s> (qualquer valor) e [pausa ...].
    Cada quebra de linha vira uma pausa de parágrafo (para_pause). Outras tags são removidas."""
    parts, pos = [], 0
    for m in PAUSE_RE.finditer(text):
        parts.append(("text", text[pos:m.start()]))
        if m.group(1):
            secs = 0.5 if m.group(1).lower() == "short" else 1.2
        elif m.group(2):
            secs = float(m.group(2).replace(",", "."))
        else:
            tag = m.group(3).lower()
            num = re.search(r"(\d+(?:[.,]\d+)?)\s*segundo", tag)
            secs = float(num.group(1).replace(",", ".")) if num else (1.2 if "longa" in tag else 0.5)
        parts.append(("pause", min(secs, 10.0)))
        pos = m.end()
    parts.append(("text", text[pos:]))

    clean = lambda v: re.sub(r"<[^>]+>|\[[^\]]*\]", "", v).strip()
    out = []
    for kind, val in parts:
        if kind == "pause":
            out.append((kind, val))
            continue
        lines = [clean(l) for l in re.split(r"\n+", val)]
        for i, line in enumerate(lines):
            if line:
                out.append(("text", line))
                if para_pause > 0 and any(lines[i + 1:]):
                    out.append(("pause", para_pause))
    # pausas seguidas viram uma só (vale a maior)
    merged = []
    for kind, val in out:
        if kind == "pause" and merged and merged[-1][0] == "pause":
            merged[-1] = ("pause", max(merged[-1][1], val))
        else:
            merged.append((kind, val))
    return merged


def tighten(wav, sr, keep=0.15):
    """Apara o silêncio que o modelo deixa no começo/fim de cada trecho, para as pausas ficarem exatas."""
    if len(wav) == 0:
        return wav
    peak = float(np.max(np.abs(wav)))
    if peak <= 0:
        return wav
    idx = np.where(np.abs(wav) > max(0.004, peak * 0.015))[0]
    if len(idx) == 0:
        return wav
    k = int(sr * keep)
    return wav[max(0, idx[0] - k): min(len(wav), idx[-1] + k + 1)]


def make_cues(text, start, end, max_chars):
    """Quebra um trecho em legendas curtas e reparte o tempo de forma proporcional ao tamanho."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
        # prefere quebrar em pontuação quando a linha já tem tamanho razoável
        if cur[-1] in ".!?…" and len(cur) >= max_chars * 0.4:
            lines.append(cur)
            cur = ""
        elif cur[-1] in ",;:" and len(cur) >= max_chars * 0.7:
            lines.append(cur)
            cur = ""
    if cur:
        lines.append(cur)
    # evita legenda final minúscula: junta com a anterior se couber com folga
    if len(lines) > 1 and len(lines[-1]) < 8 and len(lines[-2]) + 1 + len(lines[-1]) <= max_chars * 1.3:
        lines[-2] = f"{lines[-2]} {lines[-1]}"
        lines.pop()
    total = sum(len(l) for l in lines) or 1
    cues, t = [], start
    for l in lines:
        d = (end - start) * len(l) / total
        cues.append(dict(start=round(t, 3), end=round(t + d, 3), text=l))
        t += d
    return cues


@app.post("/tts")
def tts(text: str = Form(...), voice: str = Form(""), style: str = Form(""), srt_chars: int = Form(42), para_pause: float = Form(0.8)):
    kind, _, key = (voice or f"preset:{PRESETS[0]['id']}").partition(":")
    max_chars = max(15, min(srt_chars, 120))
    para_pause = max(0.0, min(para_pause, 5.0))
    with _lock:
        def job(model):
            ref, transcript = None, None
            if kind == "mine":
                ref = find_mine(key)
                if not ref:
                    raise HTTPException(404, "Voz não encontrada.")
                txt = ref.with_suffix(".txt")
                transcript = txt.read_text(encoding="utf-8") if txt.exists() else None
            else:
                ref = ensure_preset(model, preset_by_id(key))
            sr = model.tts_model.sample_rate
            pieces, cues, pos = [], [], 0.0
            for k, v in parse_text(text, para_pause):
                if k == "pause":
                    silence = np.zeros(int(sr * v), dtype=np.float32)
                    pieces.append(silence)
                    pos += len(silence) / sr
                    continue
                for chunk in split_sentences(v) if v else []:
                    wav = tighten(synth(model, chunk, style=style.strip(), ref=ref, transcript=transcript), sr)
                    dur = len(wav) / sr
                    cues += make_cues(chunk, pos, pos + dur, max_chars)
                    pieces.append(wav)
                    pos += dur
            if not pieces:
                raise HTTPException(400, "Texto vazio.")
            out = np.concatenate(pieces)
            buf = io.BytesIO()
            sf.write(buf, out, sr, format="WAV", subtype="PCM_16")
            return dict(audio=base64.b64encode(buf.getvalue()).decode("ascii"), cues=cues, duration=round(len(out) / sr, 3))

        data = run(job)
    return JSONResponse(data)


# Interface compilada (pasta server/web): aberta em http://localhost:8000
from fastapi.staticfiles import StaticFiles  # noqa: E402

# Aba Roteiro: acentos, números por extenso e vírgulas de respiração (veja roteiro.py)
from roteiro import router as roteiro_router  # noqa: E402

app.include_router(roteiro_router)
ROTEIRO_WEB = BASE / "roteiro_web"
if ROTEIRO_WEB.is_dir():
    app.mount("/roteiro", StaticFiles(directory=str(ROTEIRO_WEB), html=True), name="roteiro")

# Aba Legendas: SRT a partir de um áudio pronto e do roteiro (veja legenda.py)
from legenda import router as legenda_router  # noqa: E402

app.include_router(legenda_router)
LEGENDA_WEB = BASE / "legenda_web"
if LEGENDA_WEB.is_dir():
    app.mount("/legenda", StaticFiles(directory=str(LEGENDA_WEB), html=True), name="legenda")

# Aba Diálogo: várias vozes no mesmo áudio (veja dialogo.py). Usa o mesmo modelo carregado aqui.
import dialogo  # noqa: E402

app.include_router(dialogo.criar_router(dict(
    lock=_lock, run=run, synth=synth, tighten=tighten, make_cues=make_cues, parse_text=parse_text,
    split_sentences=split_sentences, ensure_preset=ensure_preset, find_mine=find_mine, preset_by_id=preset_by_id,
    saidas=SAIDAS,
)))
app.mount("/saidas", StaticFiles(directory=str(SAIDAS)), name="saidas")
DIALOGO_WEB = BASE / "dialogo_web"
if DIALOGO_WEB.is_dir():
    app.mount("/dialogo", StaticFiles(directory=str(DIALOGO_WEB), html=True), name="dialogo")

# Janela principal com navegação lateral (Roteiro, Narração, Diálogo, Legendas e áreas de IA): http://localhost:8000/estudio/
ESTUDIO = BASE / "estudio"
if ESTUDIO.is_dir():
    app.mount("/estudio", StaticFiles(directory=str(ESTUDIO), html=True), name="estudio")

WEB = BASE / "web"
if WEB.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB), html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    print(f"Social Sound - servidor de voz em http://localhost:8000 (dispositivo: {_device})")
    uvicorn.run(app, host="127.0.0.1", port=8000)
