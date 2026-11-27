"""Social Sound - legenda SRT a partir de um áudio pronto e do texto do roteiro.

Formatos: frases (SRT normal), palavras (SRT com 1, 2 ou 3 palavras por vez) e timestamps ([mm:ss] frase, em .txt).

Dois modos:
  rapido  : usa só as pausas do próprio áudio (sem baixar nada). Bom para as narrações geradas aqui.
  whisper : o Whisper (faster-whisper, na CPU) ouve o áudio e o roteiro é casado com o que ele ouviu.
"""
import bisect
import difflib
import re
import tempfile
import threading
import time
import unicodedata
import uuid
from importlib.util import find_spec
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

BASE = Path(__file__).parent
TMP = BASE / "tmp"
ABREVIACOES = {"sr", "sra", "srta", "dr", "dra", "prof", "profa", "av", "vs", "obs", "tel", "etc", "pag", "pags"}


def sem_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


# ====================================================================== roteiro -> legendas (sem tempos)
def quebrar_linhas(texto: str, max_chars: int):
    linhas, cur = [], ""
    for w in texto.split():
        if cur and len(cur) + 1 + len(w) > max_chars:
            linhas.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
        if cur[-1] in ".!?…" and len(cur) >= max_chars * 0.4:
            linhas.append(cur)
            cur = ""
        elif cur[-1] in ",;:" and len(cur) >= max_chars * 0.7:
            linhas.append(cur)
            cur = ""
    if cur:
        linhas.append(cur)
    if len(linhas) > 1 and len(linhas[-1]) < 8 and len(linhas[-2]) + 1 + len(linhas[-1]) <= max_chars * 1.3:
        linhas[-2] = f"{linhas[-2]} {linhas[-1]}"
        linhas.pop()
    return linhas


def _frases(paragrafo: str):
    """Divide em frases sem cortar depois de abreviações (Sr., Dra., etc.)."""
    partes, ini = [], 0
    for m in re.finditer(r"(?<=[.!?…])\s+", paragrafo):
        antes = re.findall(r"\w+", paragrafo[ini:m.start()])
        ultima = sem_acentos(antes[-1]).lower() if antes else ""
        if paragrafo[m.start() - 1] == "." and ultima in ABREVIACOES:
            continue
        partes.append(paragrafo[ini:m.start()])
        ini = m.end()
    partes.append(paragrafo[ini:])
    return [p.strip() for p in partes if p.strip()]


def preparar_cues(roteiro: str, max_chars: int = 42):
    """Cada legenda: texto, peso (letras e números) e se termina uma frase."""
    limpo = re.sub(r"<[^>]+>|\[[^\]]*\]", " ", roteiro)
    cues = []
    for par in (p.strip() for p in re.split(r"\n+", limpo)):
        for frase in _frases(re.sub(r"[ \t]+", " ", par)) if par else []:
            linhas = quebrar_linhas(frase, max_chars)
            for j, linha in enumerate(linhas):
                cues.append({"texto": linha, "peso": max(1, sum(c.isalnum() for c in linha)), "fim_frase": j == len(linhas) - 1})
        if cues:
            cues[-1]["fim_par"] = True
    return cues


# ====================================================================== modo rápido: pausas do áudio
def _runs(mask):
    """[(inicio, fim_exclusivo, valor)] de uma lista booleana."""
    if len(mask) == 0:
        return []
    mudancas = np.flatnonzero(mask[1:] != mask[:-1]) + 1
    inicios = np.concatenate([[0], mudancas])
    fins = np.concatenate([mudancas, [len(mask)]])
    return [(int(a), int(b), bool(mask[a])) for a, b in zip(inicios, fins)]


def _limiar_otsu(db):
    """Separa 'silêncio' de 'fala' pelo histograma de volume. Devolve (limiar_dB, distância entre os dois grupos em dB)."""
    topo = np.percentile(db, 99)
    v = np.clip(db, topo - 80, topo)
    hist, bins = np.histogram(v, bins=120)
    p = hist / hist.sum()
    w0 = np.cumsum(p)
    w1 = 1 - w0
    cent = (bins[:-1] + bins[1:]) / 2
    m = np.cumsum(p * cent)
    with np.errstate(divide="ignore", invalid="ignore"):
        entre = (m[-1] * w0 - m) ** 2 / (w0 * w1)
    k = int(np.nanargmax(entre))
    return float(cent[k]), float(((m[-1] - m[k]) / w1[k]) - (m[k] / w0[k]))


def blocos_de_fala(x, sr, pausa_min=0.20):
    """Blocos de fala (em segundos) separados por pausas de pelo menos pausa_min."""
    hop, win = int(sr * 0.010), int(sr * 0.025)
    if len(x) < win * 8:
        raise ValueError("O áudio é curto demais.")
    cs = np.concatenate([[0.0], np.cumsum(x.astype(np.float64) ** 2)])
    n = (len(x) - win) // hop + 1
    idx = np.arange(n) * hop
    db = 10 * np.log10((cs[idx + win] - cs[idx]) / win + 1e-10)
    limiar, separacao = _limiar_otsu(db)
    topo = np.percentile(db, 99)
    if topo < -60:
        raise ValueError("O áudio está quase mudo.")
    if separacao < 15:  # sem pausas claras: só corta o silêncio do começo e do fim
        limiar = topo - 30
    mascara = db > limiar
    quadro = hop / sr
    # 1) junta silêncios curtos (< pausa_min) dentro da fala; 2) descarta estalos curtos de fala
    runs = _runs(mascara)
    for a, b, v in runs:
        if not v and a > 0 and b < len(mascara) and (b - a) * quadro < pausa_min:
            mascara[a:b] = True
    runs = _runs(mascara)
    for a, b, v in runs:
        if v and (b - a) * quadro < 0.08:
            mascara[a:b] = False
    blocos = [(a * quadro, b * quadro) for a, b, v in _runs(mascara) if v]
    if not blocos:
        raise ValueError("Não encontrei fala no áudio.")
    return blocos


class Linha:
    """Mapeia tempo real <-> tempo de fala (sem as pausas) dentro de [t0, t1]."""

    def __init__(self, blocos, t0, t1):
        self.b = [(max(a, t0), min(b, t1)) for a, b in blocos if min(b, t1) - max(a, t0) > 1e-6]
        self.cum = [0.0]
        for a, b in self.b:
            self.cum.append(self.cum[-1] + (b - a))
        self.total = self.cum[-1]

    def real(self, s):
        if not self.b:
            return None
        s = min(max(s, 0.0), self.total)
        j = min(bisect.bisect_right(self.cum, s) - 1, len(self.b) - 1)
        return self.b[j][0] + (s - self.cum[j])

    def na_pausa(self, t):
        """Se t cai dentro de uma pausa entre blocos, devolve (fim_do_bloco_anterior, inicio_do_proximo)."""
        for k in range(len(self.b) - 1):
            if self.b[k][1] < t < self.b[k + 1][0]:
                return self.b[k][1], self.b[k + 1][0]
        return None


def ancorar_duracoes(pesos, duracoes, taxa, max_texto=4, max_blocos=6, folga=40):
    """Alinha os trechos de texto (entre pontuações) aos blocos de fala do áudio comparando DURAÇÕES, e não horários:
    assim a velocidade da voz pode variar sem que o erro se acumule. Um bloco pode cobrir vários trechos de texto
    (a voz não pausou) e um trecho pode ter várias pausas (respiração). Devolve [(fim_trecho_texto, pausa)]."""
    n, m = len(pesos), len(duracoes)
    cw = np.concatenate([[0.0], np.cumsum(pesos)])
    cd = np.concatenate([[0.0], np.cumsum(duracoes)])
    INF = float("inf")
    dp = np.full((n + 1, m + 1), INF)
    volta = {}
    dp[0, 0] = 0.0
    for i in range(1, n + 1):
        centro = i * m / n
        for j in range(max(1, int(centro - folga - max_blocos)), min(m, int(centro + folga + max_blocos)) + 1):
            melhor, ref = INF, None
            for a in range(1, min(max_texto, i) + 1):
                W = cw[i] - cw[i - a]
                for b in range(1, min(max_blocos, j) + 1):
                    ant = dp[i - a, j - b]
                    if ant == INF:
                        continue
                    D = cd[j] - cd[j - b]
                    c = ant + abs(D - taxa * W) + 0.15 * (a - 1 + b - 1)
                    if c < melhor:
                        melhor, ref = c, (a, b)
            if ref:
                dp[i, j] = melhor
                volta[(i, j)] = ref
    if dp[n, m] == INF:
        return [], 0.0
    ancoras, i, j, erro_rel, total_d = [], n, m, 0.0, 0.0
    while i > 0:
        a, b = volta[(i, j)]
        W, D = cw[i] - cw[i - a], cd[j] - cd[j - b]
        erro_rel += abs(D - taxa * W)
        total_d += D
        if i - a > 0:
            ancoras.append((i - a, j - b - 1))   # (nº de trechos de texto antes da fronteira, pausa antes do bloco j-b)
        i, j = i - a, j - b
    ancoras.reverse()
    return ancoras, max(0.0, 1.0 - erro_rel / max(total_d, 1e-9))


def pontos_de_pausa(cues):
    """Posições (peso acumulado de texto) onde se espera uma pausa, e o peso acumulado no fim de cada legenda."""
    cum, slots, fim_cue = 0, {}, []
    for c in cues:
        palavras = c["texto"].split()
        for k, w in enumerate(palavras):
            cum += sum(ch.isalnum() for ch in w)
            tipo = "frase" if w[-1] in ".!?…" else "virgula" if w[-1] in ",;:" else None
            if k == len(palavras) - 1 and c.get("fim_par"):
                tipo = "par"
            if tipo and (cum not in slots or ESPERADO[tipo] > ESPERADO[slots[cum]]):
                slots[cum] = tipo
        fim_cue.append(cum)
    slots.pop(cum, None)  # a pausa depois da última palavra não é pausa interna
    return sorted(slots.items()), fim_cue, cum


def alinhar_rapido(cues, blocos):
    """Devolve (inicios, fins, info). Pausas do áudio ancoram as pontuações do texto; entre elas, tempo proporcional."""
    n = len(cues)
    slots, fim_cue, total_w = pontos_de_pausa(cues)
    total_w = max(total_w, 1)
    pausas = [(blocos[i][1], blocos[i + 1][0]) for i in range(len(blocos) - 1)]
    dur_blocos = np.array([b - a for a, b in blocos])
    taxa = dur_blocos.sum() / total_w                        # segundos de fala por unidade de texto
    limites = [0] + [w for w, _ in slots] + [total_w]
    pesos_seg = np.diff(limites).astype(float)
    liga, qualidade = ancorar_duracoes(np.maximum(pesos_seg, 0.5), dur_blocos, taxa) if len(blocos) > 1 else ([], 0.0)
    ancoras = [(slots[k - 1][0], p) for k, p in liga]        # (peso acumulado, índice da pausa)
    pesos_anc = [a[0] for a in ancoras]

    regs, w0, t0 = [], 0, blocos[0][0]
    for w, p in ancoras:
        regs.append((w0, w, t0, pausas[p][0]))
        w0, t0 = w, pausas[p][1]
    regs.append((w0, total_w, t0, blocos[-1][1]))
    lins = [Linha(blocos, r[2], r[3]) for r in regs]

    inicios, fins = [0.0] * n, [0.0] * n
    inicios[0], fins[n - 1] = blocos[0][0], blocos[-1][1]
    for i in range(n - 1):
        w = fim_cue[i]
        if w in pesos_anc:                                   # a legenda termina numa pausa ancorada
            fins[i], inicios[i + 1] = pausas[ancoras[pesos_anc.index(w)][1]]
            continue
        r = min(bisect.bisect_left(pesos_anc, w), len(regs) - 1)
        w_ini, w_fim, t_ini, t_fim = regs[r]
        lin = lins[r]
        frac = (w - w_ini) / max(w_fim - w_ini, 1)
        tb = lin.real(frac * lin.total) if lin.total > 0 else t_ini + (t_fim - t_ini) * frac
        gap = lin.na_pausa(tb)
        fins[i], inicios[i + 1] = gap if gap else (tb, tb)
    return inicios, fins, {"pausas_ancoradas": len(ancoras), "pausas_no_texto": len(slots), "confianca": float(qualidade)}


# ====================================================================== modo Whisper: casar o roteiro com o que foi ouvido
def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", sem_acentos(w).lower())


def alinhar_com_palavras(cues, palavras_ouvidas):
    """palavras_ouvidas: [(texto, inicio, fim)]. Devolve (inicios, fins, info)."""
    script = [(_norm(w), ci, len(w)) for ci, c in enumerate(cues) for w in c["texto"].split() if _norm(w)]
    ouvidas = [(_norm(t), a, b) for t, a, b in palavras_ouvidas if _norm(t)]
    if not script or not ouvidas:
        raise ValueError("Não consegui ouvir palavras no áudio.")
    sm = difflib.SequenceMatcher(None, [s[0] for s in script], [o[0] for o in ouvidas], autojunk=False)
    ini, fim = [None] * len(script), [None] * len(script)
    casadas = 0
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            ini[blk.a + k], fim[blk.a + k] = ouvidas[blk.b + k][1], ouvidas[blk.b + k][2]
            casadas += 1
    if casadas < max(3, 0.15 * len(script)):
        raise ValueError("O texto do roteiro não parece ser o do áudio (quase nada casou).")
    # preenche as palavras sem par, repartindo o tempo entre vizinhas casadas pelo tamanho das palavras
    ids = [i for i in range(len(script)) if ini[i] is not None]
    limites = [(-1, ouvidas[0][1])] + [(i, fim[i]) for i in ids] + [(len(script), ouvidas[-1][2])]
    prox_ini = {i: ini[i] for i in ids}
    for (i_ant, t_ant), (i_dep, _) in zip(limites[:-1], limites[1:]):
        lacuna = list(range(i_ant + 1, i_dep))
        if not lacuna:
            continue
        t_fim_lacuna = prox_ini[i_dep] if i_dep in prox_ini else limites[-1][1]
        total = sum(script[i][2] for i in lacuna) or 1
        t = t_ant
        for i in lacuna:
            d = max(0.0, t_fim_lacuna - t_ant) * script[i][2] / total
            ini[i], fim[i] = t, t + d
            t += d
    inicios, fins = [None] * len(cues), [0.0] * len(cues)
    for i, (_, ci, _) in enumerate(script):
        if inicios[ci] is None:
            inicios[ci] = ini[i]
        fins[ci] = max(fins[ci], fim[i])
    tempos = [(ini[i], fim[i]) for i in range(len(script))]
    return inicios, fins, {"confianca": casadas / len(script), "palavras_casadas": casadas, "palavras": len(script),
                           "tempos_palavras": tempos}



# ====================================================================== tempo de cada palavra
def _pontuacao(w: str):
    """'frase' se a palavra fecha uma frase, 'virgula' se fecha um trecho, senão None."""
    w = w.rstrip("\"'”’»)]")
    if not w:
        return None
    return "frase" if w[-1] in ".!?…" else "virgula" if w[-1] in ",;:" else None


def palavras_com_tempo(cues, inicios, fins, blocos=None, tempos_whisper=None):
    """Lista [{texto, ini, fim}] com o tempo de cada palavra do roteiro.
    Com Whisper usa o tempo ouvido; no modo rápido reparte o tempo de fala de cada legenda pelo tamanho das palavras,
    pulando as pausas do áudio."""
    out = []
    if tempos_whisper is not None:
        k = 0
        for c in cues:
            for w in c["texto"].split():
                if _norm(w) and k < len(tempos_whisper):
                    a, b = tempos_whisper[k]
                    k += 1
                    out.append({"texto": w, "ini": float(a), "fim": float(b)})
                elif out:                      # símbolo solto (—, …): gruda na palavra anterior
                    out[-1]["texto"] += " " + w
        return out
    for c, t0, t1 in zip(cues, inicios, fins):
        ws = c["texto"].split()
        pesos = [max(1, sum(ch.isalnum() for ch in w)) for w in ws]
        total = sum(pesos)
        lin = Linha(blocos, t0, t1) if blocos else None
        acum = 0
        for w, p in zip(ws, pesos):
            if lin and lin.total > 0:
                a, b = lin.real(lin.total * acum / total), lin.real(lin.total * (acum + p) / total)
            else:
                a, b = t0 + (t1 - t0) * acum / total, t0 + (t1 - t0) * (acum + p) / total
            out.append({"texto": w, "ini": float(a), "fim": float(b)})
            acum += p
    return out


def agrupar_palavras(palavras, por_vez=1):
    """Junta de 1 a 3 palavras por legenda, sem atravessar o fim de uma frase ou uma vírgula."""
    grupos, cur = [], []
    for p in palavras:
        cur.append(p)
        if len(cur) >= por_vez or _pontuacao(p["texto"]):
            grupos.append(cur)
            cur = []
    if cur:
        grupos.append(cur)
    return [{"texto": " ".join(p["texto"] for p in g), "ini": g[0]["ini"], "fim": g[-1]["fim"]} for g in grupos]


def tempo_curto(t: float) -> str:
    s = int(max(t, 0.0))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def montar_timestamps(cues, inicios):
    """[mm:ss] Frase — uma linha por frase do roteiro."""
    return "\n".join(f"[{tempo_curto(t)}] {c['texto']}" for c, t in zip(cues, inicios)) + "\n"


# ====================================================================== SRT
def tempo_srt(t: float) -> str:
    ms = int(round(max(t, 0.0) * 1000))
    return f"{ms // 3600000:02d}:{ms % 3600000 // 60000:02d}:{ms % 60000 // 1000:02d},{ms % 1000:03d}"


def montar_srt(cues, inicios, fins, duracao=None):
    n = len(cues)
    ini = [float(t) for t in inicios]
    fim = [float(t) for t in fins]
    for i in range(n):
        if i > 0 and ini[i] < ini[i - 1]:
            ini[i] = ini[i - 1]
        if fim[i] < ini[i] + 0.2:
            fim[i] = ini[i] + 0.2
    for i in range(n - 1):  # pausas curtas: a legenda fica até a próxima entrar (evita piscar)
        if 0 <= ini[i + 1] - fim[i] < 0.35:
            fim[i] = ini[i + 1]
        if fim[i] > ini[i + 1]:
            fim[i] = max(ini[i] + 0.05, ini[i + 1])
    if duracao:
        fim[-1] = min(fim[-1], duracao)
    return "\n".join(f"{i + 1}\n{tempo_srt(ini[i])} --> {tempo_srt(fim[i])}\n{cues[i]['texto']}\n" for i in range(n))


# ====================================================================== tarefas e rotas
router = APIRouter()
JOBS = {}
_whisper = {}
_whisper_lock = threading.Lock()


def whisper_instalado() -> bool:
    return find_spec("faster_whisper") is not None


def ouvir_palavras(caminho: str, modelo: str):
    from faster_whisper import WhisperModel

    with _whisper_lock:
        if modelo not in _whisper:
            _whisper[modelo] = WhisperModel(modelo, device="cpu", compute_type="int8")
    segs, _ = _whisper[modelo].transcribe(
        caminho, language="pt", word_timestamps=True, beam_size=1, condition_on_previous_text=False
    )
    return [(w.word, w.start, w.end) for s in segs for w in (s.words or [])]


def _trabalho(jid, caminho, roteiro, modo, max_chars, modelo, formato="frases", por_vez=1):
    job = JOBS[jid]
    try:
        # timestamps: uma linha por frase inteira; nos outros formatos, legendas do tamanho escolhido
        cues = preparar_cues(roteiro, 100000 if formato == "timestamps" else max_chars)
        if not cues:
            raise ValueError("O roteiro está vazio.")
        x, sr = sf.read(caminho, dtype="float32", always_2d=False)
        if x.ndim > 1:
            x = x.mean(axis=1)
        duracao = len(x) / sr
        avisos = []
        if modo == "whisper":
            if not whisper_instalado():
                raise ValueError("O Whisper ainda não foi instalado. Rode o instalar.bat de novo.")
            job["msg"] = "Ouvindo o áudio com o Whisper (na primeira vez baixa o modelo; pode levar alguns minutos)..."
            palavras = ouvir_palavras(caminho, modelo)
            job["msg"] = "Casando o roteiro com o que foi ouvido..."
            ini, fim, info = alinhar_com_palavras(cues, palavras)
            if info["confianca"] < 0.6:
                avisos.append(f"Só {info['confianca']:.0%} das palavras casaram com o áudio; confira o roteiro e a legenda.")
        else:
            job["msg"] = "Analisando as pausas do áudio..."
            blocos = blocos_de_fala(x, sr)
            ini, fim, info = alinhar_rapido(cues, blocos)
            if info["confianca"] < 0.7 or not info["pausas_ancoradas"]:
                avisos.append("O áudio e o texto não combinam muito bem nas pausas, então a sincronia pode variar. "
                              "Se ficar fora de lugar, tente o modo com Whisper.")
        if formato == "timestamps":
            texto, qtd, ext = montar_timestamps(cues, ini), len(cues), "txt"
        elif formato == "palavras":
            palavras = palavras_com_tempo(cues, ini, fim, blocos=None if modo == "whisper" else blocos,
                                          tempos_whisper=info.get("tempos_palavras"))
            grupos = agrupar_palavras(palavras, por_vez)
            texto = montar_srt(grupos, [g["ini"] for g in grupos], [g["fim"] for g in grupos], duracao)
            qtd, ext = len(grupos), "srt"
        else:
            texto, qtd, ext = montar_srt(cues, ini, fim, duracao), len(cues), "srt"
        job.update(status="pronto", srt=texto, ext=ext, avisos=avisos,
                   info={"duracao": round(duracao, 1), "legendas": qtd, "modo": modo, "formato": formato,
                         "confianca": round(float(info["confianca"]), 3)})
    except Exception as e:  # noqa: BLE001
        job.update(status="erro", msg=f"{type(e).__name__}: {e}"[:400])
    finally:
        try:
            Path(caminho).unlink()
        except OSError:
            pass


def _trabalho_transcricao_referencia(jid: str, caminho: str, modelo: str):
    job = JOBS[jid]
    try:
        if not whisper_instalado():
            raise ValueError("O Whisper ainda não foi instalado. Rode o instalar.bat de novo.")
        from faster_whisper import WhisperModel
        with _whisper_lock:
            if modelo not in _whisper:
                _whisper[modelo] = WhisperModel(modelo, device="cpu", compute_type="int8")
            engine = _whisper[modelo]
        job["msg"] = "Transcrevendo áudio com Whisper…"
        segmentos, info = engine.transcribe(
            caminho, beam_size=1, condition_on_previous_text=False, vad_filter=True
        )
        texto = " ".join(segmento.text.strip() for segmento in segmentos if segmento.text.strip()).strip()
        if not texto:
            raise ValueError("Não foi possível identificar fala no áudio.")
        job.update(status="pronto", msg="Transcrição concluída.", texto=texto,
                   idioma=getattr(info, "language", None))
    except Exception as exc:  # noqa: BLE001
        job.update(status="erro", msg=f"{type(exc).__name__}: {exc}"[:400])
    finally:
        try:
            Path(caminho).unlink()
        except OSError:
            pass


@router.post("/api/legenda/transcrever")
async def rota_transcrever_referencia(audio: UploadFile = File(...), modelo: str = Form("base")):
    if modelo not in ("base", "small"):
        raise HTTPException(400, "Modelo Whisper inválido.")
    if not whisper_instalado():
        raise HTTPException(503, "O Whisper não está instalado. Rode instalar.bat novamente.")
    conteudo = await audio.read(50 * 1024 * 1024 + 1)
    if not conteudo or len(conteudo) > 50 * 1024 * 1024:
        raise HTTPException(400 if not conteudo else 413, "Áudio vazio ou maior que 50 MB.")
    TMP.mkdir(exist_ok=True)
    caminho = TMP / f"{uuid.uuid4().hex}.wav"
    caminho.write_bytes(conteudo)
    jid = uuid.uuid4().hex[:8]
    JOBS[jid] = {"status": "rodando", "msg": "Preparando a transcrição…", "t": time.time()}
    try:
        threading.Thread(target=_trabalho_transcricao_referencia, args=(jid, str(caminho), modelo),
                         daemon=True).start()
    except Exception:
        caminho.unlink(missing_ok=True)
        JOBS.pop(jid, None)
        raise HTTPException(500, "Não foi possível iniciar a transcrição.")
    return {"job": jid}


@router.get("/api/legenda/transcrever/{jid}")
def rota_status_transcricao_referencia(jid: str):
    if jid not in JOBS:
        raise HTTPException(404, "Transcrição não encontrada.")
    return JOBS[jid]


@router.get("/api/legenda/status")
def rota_status():
    return {"whisper": whisper_instalado()}


@router.post("/api/legenda/gerar")
async def rota_gerar(audio: UploadFile = File(...), roteiro: str = Form(...), modo: str = Form("rapido"),
                     max_chars: int = Form(42), modelo: str = Form("base"),
                     formato: str = Form("frases"), palavras_por_vez: int = Form(1)):
    if formato not in ("frases", "palavras", "timestamps"):
        raise HTTPException(400, "Formato inválido.")
    if modo not in ("rapido", "whisper"):
        raise HTTPException(400, "Modo inválido.")
    if modelo not in ("base", "small"):
        raise HTTPException(400, "Modelo inválido.")
    TMP.mkdir(exist_ok=True)
    caminho = TMP / f"{uuid.uuid4().hex}.wav"
    caminho.write_bytes(await audio.read())
    jid = uuid.uuid4().hex[:8]
    JOBS[jid] = {"status": "rodando", "msg": "Começando...", "t": time.time()}
    threading.Thread(target=_trabalho, args=(jid, str(caminho), roteiro, modo, max(15, min(max_chars, 120)), modelo,
                                                    formato, max(1, min(palavras_por_vez, 3))),
                     daemon=True).start()
    return {"job": jid}


@router.get("/api/legenda/job/{jid}")
def rota_job(jid: str):
    if jid not in JOBS:
        raise HTTPException(404, "Tarefa não encontrada.")
    return JOBS[jid]
