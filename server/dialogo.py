"""Social Sound - diálogo com várias vozes.

Cada linha "Nome: fala" é narrada com a voz escolhida para aquele personagem; linhas sem nome (ou com um nome que
não foi configurado como personagem) usam a voz do narrador. Tudo é gerado fala por fala e juntado num áudio só.
"""
import re
import threading
import time
import uuid

import numpy as np
import soundfile as sf
from fastapi import APIRouter, HTTPException

from legenda import montar_srt, sem_acentos

# "Nome: fala". O nome começa com letra, tem até 30 caracteres e precisa de espaço depois dos dois-pontos
# (assim "10:30" e "http://site" não viram personagem).
RE_FALA = re.compile(r"^\s*([^\W\d_][\w .'\-]{0,29}?)\s*:\s+(\S.*)$", re.UNICODE)
JOBS = {}
JOBS_LOCK = threading.Lock()


def _job_update(jid: str, **values):
    with JOBS_LOCK:
        job = JOBS.get(jid)
        if job is not None:
            job.update(values)


def limpar_jobs(max_finished: int = 100, max_age_seconds: int = 86400):
    """Keep active jobs intact, prune finished jobs older than a day and cap history."""
    agora = time.time()
    with JOBS_LOCK:
        finished = [(jid, job) for jid, job in JOBS.items() if job.get("status") != "rodando"]
        for jid, job in finished:
            if agora - float(job.get("t", agora)) > max_age_seconds:
                JOBS.pop(jid, None)
        finished = [(jid, job) for jid, job in JOBS.items() if job.get("status") != "rodando"]
        if len(finished) > max_finished:
            finished.sort(key=lambda pair: float(pair[1].get("t", 0)))
            for jid, _ in finished[:len(finished) - max_finished]:
                JOBS.pop(jid, None)


def chave(nome: str) -> str:
    return re.sub(r"\s+", " ", sem_acentos(nome).strip().lower())


def detectar_personagens(texto: str):
    """Nomes que aparecem antes dos dois-pontos, na ordem em que aparecem, com a quantidade de falas."""
    achados = {}
    for linha in texto.splitlines():
        m = RE_FALA.match(linha)
        if not m or chave(m.group(1)) in ("http", "https"):
            continue
        k = chave(m.group(1))
        achados.setdefault(k, {"nome": m.group(1).strip(), "falas": 0})["falas"] += 1
    return list(achados.values())


def parse_roteiro(texto: str, conhecidos):
    """Lista de falas {nome|None, texto, par}. 'par' = havia linha em branco antes (bloco novo)."""
    falas, vazia = [], False
    for linha in texto.splitlines():
        if not linha.strip():
            vazia = True
            continue
        m = RE_FALA.match(linha)
        if m and chave(m.group(1)) in conhecidos:
            nome, fala = m.group(1).strip(), m.group(2).strip()
        else:
            nome, fala = None, linha.strip()
        falas.append({"nome": nome, "texto": fala, "par": vazia and bool(falas)})
        vazia = False
    return falas


def _referencia(ctx, model, voz, cache):
    if voz in cache:
        return cache[voz]
    tipo, _, nome = voz.partition(":")
    if tipo == "mine":
        ref = ctx["find_mine"](nome)
        if not ref:
            raise ValueError(f"A voz '{nome}' não foi encontrada.")
        txt = ref.with_suffix(".txt")
        cache[voz] = (ref, txt.read_text(encoding="utf-8") if txt.exists() else None)
    elif tipo == "preset":
        cache[voz] = (ctx["ensure_preset"](model, ctx["preset_by_id"](nome)), None)
    else:
        raise ValueError("Voz inválida.")
    return cache[voz]


def _trabalho(ctx, jid, falas, narrador, personagens, opts):
    try:
        n = len(falas)
        _job_update(jid, total=n)

        def work(model):
            sr = model.tts_model.sample_rate
            cache, pecas, cues, info, pos = {}, [], [], [], 0.0
            for i, f in enumerate(falas):
                _job_update(jid, atual=i, msg=f"Fala {i + 1} de {n}: {f['nome'] or 'Narrador'}")
                cfg = personagens.get(chave(f["nome"])) if f["nome"] else None
                cfg = cfg or narrador
                ref, transcript = _referencia(ctx, model, cfg["voz"], cache)
                if i > 0:
                    gap = max(opts["pausa_falas"], opts["para_pause"] if f["par"] else 0.0)
                    if gap > 0:
                        silencio = np.zeros(int(sr * gap), dtype=np.float32)
                        pecas.append(silencio)
                        pos += len(silencio) / sr
                inicio, primeiro = pos, True
                for tipo, v in ctx["parse_text"](f["texto"], 0.0):
                    if tipo == "pause":
                        silencio = np.zeros(int(sr * v), dtype=np.float32)
                        pecas.append(silencio)
                        pos += len(silencio) / sr
                        continue
                    for trecho in ctx["split_sentences"](v) if v else []:
                        wav = ctx["tighten"](ctx["synth"](model, trecho, style=cfg["estilo"], ref=ref, transcript=transcript), sr)
                        dur = len(wav) / sr
                        novas = ctx["make_cues"](trecho, pos, pos + dur, opts["max_chars"])
                        if primeiro and novas and opts["nome_na_legenda"] and f["nome"]:
                            novas[0]["text"] = f"{f['nome']}: {novas[0]['text']}"
                        primeiro = False
                        cues += novas
                        pecas.append(wav)
                        pos += dur
                info.append({"nome": f["nome"], "inicio": round(inicio, 3), "fim": round(pos, 3)})
            if not pecas:
                raise ValueError("Não há texto para narrar.")
            return sr, np.concatenate(pecas), cues, info

        job["msg"] = "Carregando o modelo de voz (na primeira vez demora alguns minutos)..."
        with ctx["lock"]:
            sr, saida, cues, info = ctx["run"](work)
        caminho = ctx["saidas"] / f"{jid}.wav"
        sf.write(str(caminho), saida, sr, subtype="PCM_16")
        duracao = len(saida) / sr
        srt = montar_srt([{"texto": c["text"]} for c in cues], [c["start"] for c in cues], [c["end"] for c in cues], duracao)
        _job_update(jid, status="pronto", atual=n, msg="Pronto.", audio=f"/saidas/{jid}.wav", srt=srt, falas=info, duracao=round(duracao, 1))
    except HTTPException as e:
        _job_update(jid, status="erro", msg=str(e.detail)[:400])
    except Exception as e:  # noqa: BLE001
        _job_update(jid, status="erro", msg=f"{type(e).__name__}: {e}"[:400])


def limpar_antigas(pasta, dias=14):
    limite = time.time() - dias * 86400
    for p in pasta.glob("*.wav"):
        try:
            if p.stat().st_mtime < limite:
                p.unlink()
        except OSError:
            pass


def criar_router(ctx):
    """ctx: funções e objetos do servidor de voz (modelo, vozes, pausas, legendas), para não duplicar o modelo."""
    router = APIRouter()
    limpar_antigas(ctx["saidas"])

    @router.post("/api/dialogo/detectar")
    def rota_detectar(dados: dict):
        return {"personagens": detectar_personagens(str(dados.get("texto", "")))}

    @router.post("/api/dialogo/gerar")
    def rota_gerar(dados: dict):
        texto = str(dados.get("texto", ""))
        narr = dados.get("narrador") or {}
        if not texto.strip():
            raise HTTPException(400, "Escreva o roteiro.")
        if not narr.get("voz"):
            raise HTTPException(400, "Escolha a voz do narrador (linhas sem nome).")
        narrador = {"voz": str(narr["voz"]), "estilo": str(narr.get("estilo", "")).strip()}
        personagens = {}
        for p in dados.get("personagens", []):
            if p.get("nome") and p.get("voz"):
                personagens[chave(str(p["nome"]))] = {"voz": str(p["voz"]), "estilo": str(p.get("estilo", "")).strip()}
        for cfg in [narrador, *personagens.values()]:  # confere as vozes antes de começar
            tipo, _, nome = cfg["voz"].partition(":")
            if tipo == "mine" and not ctx["find_mine"](nome):
                raise HTTPException(404, f"A voz '{nome}' não foi encontrada.")
            if tipo == "preset":
                ctx["preset_by_id"](nome)
            if tipo not in ("mine", "preset"):
                raise HTTPException(400, "Voz inválida.")
        falas = parse_roteiro(texto, set(personagens))
        if not falas:
            raise HTTPException(400, "Não encontrei nenhuma fala.")
        opts = {
            "pausa_falas": max(0.0, min(float(dados.get("pausa_falas", 0.5)), 5.0)),
            "para_pause": max(0.0, min(float(dados.get("para_pause", 0.8)), 5.0)),
            "max_chars": max(15, min(int(dados.get("srt_chars", 42)), 120)),
            "nome_na_legenda": bool(dados.get("nome_na_legenda", True)),
        }
        limpar_jobs()
        jid = uuid.uuid4().hex[:8]
        with JOBS_LOCK:
            JOBS[jid] = {"status": "rodando", "msg": "Começando...", "atual": 0, "total": len(falas), "t": time.time()}
        threading.Thread(target=_trabalho, args=(ctx, jid, falas, narrador, personagens, opts), daemon=True).start()
        return {"job": jid}

    @router.get("/api/dialogo/job/{jid}")
    def rota_job(jid: str):
        with JOBS_LOCK:
            job = JOBS.get(jid)
            if job is None:
                raise HTTPException(404, "Tarefa não encontrada.")
            return dict(job)

    return router
