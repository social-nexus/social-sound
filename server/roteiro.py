"""Social Sound - preparação de roteiro para narração.

Três etapas, todas revisáveis na tela:
  1. Acentos que faltam (modelo Mark em ONNX, na CPU; dicionário de reserva se o modelo não estiver pronto)
  2. Números, valores e abreviações por extenso
  3. Vírgulas de respiração em frases longas
"""
import json
import re
import threading
import time
import unicodedata
import urllib.request
from importlib.util import find_spec
from pathlib import Path

import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel

try:  # opcional: sem ele, a etapa de números fica desligada
    from num2words import num2words
except Exception:  # pragma: no cover
    num2words = None

BASE = Path(__file__).parent
MARK_DIR = BASE / "modelos" / "mark"
MARK_URLS = {
    "tags.json": "https://huggingface.co/Mythologic/mark/resolve/main/tags.json",
    "mark_int8.onnx": "https://huggingface.co/Mythologic/mark/resolve/main/mark_int8.onnx",
}
# Ordem dos idiomas do modelo (o índice é a entrada "lang_ids")
MARK_LANGS = [
    "ak", "ar", "az", "ca", "cs", "cy", "ee", "es", "ff", "fr", "ga", "gn", "ha", "he", "hr", "ht", "hu", "ig",
    "ku", "ln", "lt", "lv", "mi", "pl", "pt", "qu", "ro", "sk", "sl", "sm", "sr", "tk", "tr", "uz", "vi", "wo", "yo",
]
LANG_PT = MARK_LANGS.index("pt")


def sem_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


# ====================================================================== 1) ACENTOS: modelo Mark
def dividir_bytes(texto: str, max_bytes: int = 480):
    """Divide em blocos de até max_bytes (UTF-8), preferindo fim de frase. ''.join(blocos) == texto."""
    pedacos = [p for p in re.split(r"(?<=[.!?\n])", texto) if p != ""]
    blocos, atual = [], ""
    for p in pedacos:
        if len((atual + p).encode("utf-8")) <= max_bytes:
            atual += p
            continue
        if atual:
            blocos.append(atual)
            atual = ""
        if len(p.encode("utf-8")) <= max_bytes:
            atual = p
            continue
        for tok in re.findall(r"\S+|\s+", p):  # frase enorme: quebra por palavras
            if len((atual + tok).encode("utf-8")) <= max_bytes:
                atual += tok
            else:
                if atual:
                    blocos.append(atual)
                    atual = ""
                if len(tok.encode("utf-8")) <= max_bytes:
                    atual = tok
                else:
                    for ch in tok:
                        if len((atual + ch).encode("utf-8")) > max_bytes:
                            blocos.append(atual)
                            atual = ch
                        else:
                            atual += ch
    if atual:
        blocos.append(atual)
    return blocos


def decodificar(bloco: str, previsoes, tags):
    """Aplica as marcas previstas (uma por byte) a cada caractere. Mesma lógica do pacote oficial do Mark."""
    return "".join(decodificar_lista(bloco, previsoes, tags))


def decodificar_lista(bloco: str, previsoes, tags):
    """Como decodificar(), mas devolve uma peça de texto por caractere do bloco."""
    saida, desloc = [], 0
    for ch in bloco:
        tag = "KEEP"
        if desloc < len(previsoes):
            tid = previsoes[desloc]
            tag = tags[tid] if 0 <= tid < len(tags) else "KEEP"
        if tag.startswith("P:") and "->" in tag:
            partes = tag[2:].split("->")
            saida.append(partes[1] if len(partes) > 1 and partes[1] != "" else ch)
        elif tag.startswith("M:"):
            marcas = "".join(chr(int(h, 16)) for h in tag[2:].split("+") if h)
            saida.append(unicodedata.normalize("NFC", ch + marcas))
        else:
            saida.append(ch)
        desloc += len(ch.encode("utf-8"))
    return saida


# Só estes acentos do português são aceitos; qualquer outra mudança prevista pelo modelo é ignorada
ACENTOS_PT = {"a": "áàâã", "e": "éê", "i": "í", "o": "óôõ", "u": "úü", "c": "ç",
              "A": "ÁÀÂÃ", "E": "ÉÊ", "I": "Í", "O": "ÓÔÕ", "U": "ÚÜ", "C": "Ç"}


class Mark:
    def __init__(self):
        self.sess = None
        self.tags = None
        self.erro = None
        self._lock = threading.Lock()

    def baixado(self) -> bool:
        return all((MARK_DIR / n).exists() for n in MARK_URLS)

    def carregar(self) -> bool:
        with self._lock:
            if self.sess is not None:
                return True
            if self.erro or not self.baixado():
                return False
            try:
                import onnxruntime as ort

                tags = json.loads((MARK_DIR / "tags.json").read_text(encoding="utf-8"))
                opts = ort.SessionOptions()
                opts.log_severity_level = 3
                sess = ort.InferenceSession(
                    str(MARK_DIR / "mark_int8.onnx"), sess_options=opts, providers=["CPUExecutionProvider"]
                )
                self.tags, self.sess = tags, sess
                teste, detalhe = self._testar()
                if detalhe.get("tamanho_modelo") != len(tags):
                    self.sess = None
                    self.erro = (f"o modelo tem {detalhe.get('tamanho_modelo')} marcas e o tags.json tem {len(tags)}; "
                                 "arquivos de versões diferentes. Use 'Baixar de novo'")
                else:
                    acertos = sum(1 for esperado in ("Você", "não", "está") if esperado in teste)
                    if acertos < 2:  # autoteste: se o modelo não acerta o básico, não é usado
                        self.sess = None
                        self.erro = f"teste falhou: 'Voce nao esta aqui.' virou {teste!r}; marcas previstas: {detalhe.get('marcas')}"
            except Exception as e:  # noqa: BLE001
                self.sess = None
                self.erro = f"{type(e).__name__}: {e}"[:300]
            return self.sess is not None

    def resetar(self):
        with self._lock:
            self.sess, self.tags, self.erro = None, None, None

    def _previsoes(self, bloco: str, margem: float):
        b = bloco.encode("utf-8")
        n = min(len(b), 512)
        ids = np.zeros((1, 512), dtype=np.int64)
        ids[0, :n] = np.frombuffer(b[:n], dtype=np.uint8)
        lang = np.array([LANG_PT], dtype=np.int64)
        logits = self.sess.run(["logits"], {"input_ids": ids, "lang_ids": lang})[0][0][:n]
        if margem > 0 and logits.shape[1] > 1:
            melhor = 1 + logits[:, 1:].argmax(axis=1)
            valor = logits[np.arange(n), melhor]
            prev = np.where(valor - logits[:, 0] >= margem, melhor, 0)
        else:
            prev = logits.argmax(axis=1)
        return prev.tolist(), int(logits.shape[1])

    def _testar(self):
        frase = "Voce nao esta aqui."
        prev, tamanho = self._previsoes(frase, 0.0)
        pecas = decodificar_lista(frase, prev, self.tags)
        marcas = []
        desloc = 0
        for ch in frase:
            tid = prev[desloc] if desloc < len(prev) else 0
            if 0 < tid < len(self.tags):
                marcas.append(f"{ch}:{self.tags[tid]}")
            desloc += len(ch.encode("utf-8"))
        return self._validar(frase, pecas), {"tamanho_modelo": tamanho, "marcas": marcas[:8]}

    @staticmethod
    def _validar(bloco: str, pecas) -> str:
        """Aceita só mudanças de acento do português, caractere por caractere; o resto fica como estava."""
        saida = []
        for c, o in zip(bloco, pecas):
            saida.append(o if (ord(c) < 128 and o != c and o in ACENTOS_PT.get(c, "")) else c)
        return "".join(saida)

    def _bloco(self, bloco: str, margem: float) -> str:
        prev, _ = self._previsoes(bloco, margem)
        return self._validar(bloco, decodificar_lista(bloco, prev, self.tags))

    def _restaurar(self, texto: str, margem: float) -> str:
        return "".join(self._bloco(b, margem) for b in dividir_bytes(texto))

    def restaurar(self, texto: str, margem: float = 0.0) -> str:
        with self._lock:
            return self._restaurar(texto, margem)


MARK = Mark()


# ====================================================================== 1b) ACENTOS: dicionário de reserva
_SEGUROS_TXT = """
voce=você voces=vocês nao=não sao=são ja=já ate=até tambem=também alem=além porem=porém entao=então so=só
mae=mãe maes=mães apos=após atras=atrás ninguem=ninguém alguem=alguém ola=olá tres=três mes=mês fe=fé pe=pé
ceu=céu historia=história historias=histórias familia=família familias=famílias memoria=memória
gloria=glória vitoria=vitória noticia=notícia noticias=notícias materia=matéria area=área areas=áreas
serie=série especie=espécie agua=água aguas=águas cafe=café forca=força forcas=forças bencao=bênção
bencaos=bênçãos espirito=espírito espiritos=espíritos misericordia=misericórdia paciencia=paciência
ultimo=último ultima=última ultimos=últimos ultimas=últimas unico=único unica=única proprio=próprio
propria=própria proprios=próprios proprias=próprias otimo=ótimo otima=ótima util=útil facil=fácil
dificil=difícil dificeis=difíceis faceis=fáceis pagina=página paginas=páginas maquina=máquina
musica=música musicas=músicas numero=número numeros=números sabado=sábado domingo=domingo
proximo=próximo proxima=próxima proximos=próximos proximas=próximas publico=público
mundo=mundo pais=país paises=países voces=vocês duvida=dúvida duvidas=dúvidas
energia=energia pratica=prática praticas=práticas grafico=gráfico tecnico=técnico tecnica=técnica
tecnicas=técnicas tecnicos=técnicos medico=médico medica=médica medicos=médicos medicas=médicas
politica=política politicas=políticas politico=político politicos=políticos economia=economia
historico=histórico historica=histórica classico=clássico classica=clássica magico=mágico magica=mágica
rapido=rápido rapida=rápida rapidos=rápidos rapidas=rápidas basico=básico basica=básica
unico=único proprio=próprio automatico=automático automatica=automática dramatico=dramático
dramatica=dramática romantico=romântico romantica=romântica fantastico=fantástico fantastica=fantástica
sabio=sábio sabia=sábia sabios=sábios inocencia=inocência
inicio=início exercito=exército exercicio=exercício exercicios=exercícios
orgao=órgão orgaos=órgãos irmao=irmão irmaos=irmãos irma=irmã irmas=irmãs
ferias=férias parabens=parabéns ontem=ontem armazem=armazém
tambem=também refem=refém alguns=alguns
saude=saúde saudade=saudade voo=voo coracao=coração
atencao=atenção cancao=canção cancoes=canções
duvida=dúvida
ceus=céus reu=réu
heroi=herói herois=heróis
estao=estão
vovo=vovô vovos=vovôs
tenho=tenho
quatro=quatro
sera=será serao=serão estara=estará estarao=estarão fara=fará farao=farão
ira=irá irao=irão vira=virá virao=virão podera=poderá poderao=poderão
tera=terá terao=terão dara=dará darao=darão
sabera=saberá saberao=saberão
havera=haverá
"""
SEGUROS = {}
for _par in _SEGUROS_TXT.split():
    _a, _, _b = _par.partition("=")
    if _b and _a != _b:
        SEGUROS[_a] = _b
# palavras que existem sem acento com outro sentido: só trocam com contexto
SEGUROS.pop("pais", None)
SEGUROS.pop("paises", None)
SEGUROS.pop("publico", None)  # "público" x "eu publico": fica para o modelo
SEGUROS.pop("pratica", None)
SEGUROS.pop("praticas", None)
SEGUROS.pop("politica", None)
SEGUROS.pop("politicas", None)
SEGUROS.pop("medica", None)
SEGUROS.pop("medico", None)
SEGUROS.pop("medicas", None)
SEGUROS.pop("medicos", None)
SEGUROS.pop("sabia", None)  # "sabia" (verbo saber) x "sábia"
SEGUROS.pop("inicio", None)
SEGUROS.pop("sera", None)  # "sera" quase não existe, mas mantemos só o futuro com acento via contexto
SEGUROS["sera"] = "será"

SUJEITOS_SINGULAR = {"isso", "isto", "aquilo", "ele", "ela", "quem", "tudo", "nada", "algo"}
SUJEITOS_PLURAL = {"eles", "elas", "vocês", "voces"}
DETERMINANTES_SING = {"o", "um", "este", "esse", "aquele", "nosso", "meu", "seu", "outro", "qualquer", "cada",
                      "do", "no", "pelo", "ao", "neste", "nesse", "naquele", "desse", "deste"}
APOS_ESTA = {"em", "muito", "bem", "mal", "tão", "sempre", "aqui", "ali", "lá", "com", "sendo", "pronto",
             "pronta", "feliz", "triste", "errado", "certo", "vivo", "morto", "cansado", "cansada"}

_EXC_AO = {"ao"}
_SUFIXOS = [  # (terminação sem acento, terminação com acento, tamanho mínimo, vale para maiúscula?)
    ("coes", "ções", 5, True),
    ("soes", "sões", 5, True),
    ("oes", "ões", 4, True),
    ("aes", "ães", 4, True),
    ("cao", "ção", 4, True),
    ("ao", "ão", 3, True),
    ("aos", "ãos", 4, True),
    ("encia", "ência", 6, False),
    ("ancia", "ância", 6, False),
    ("ivel", "ível", 5, False),
    ("avel", "ável", 5, False),
    ("orio", "ório", 6, False),
    ("ario", "ário", 6, False),
]


def _casar_caixa(original: str, novo: str) -> str:
    if len(original) > 1 and original.isupper():
        return novo.upper()
    if original[:1].isupper():
        return novo[:1].upper() + novo[1:]
    return novo


def acentuar_dicionario(texto: str) -> str:
    """Reserva simples: lista de palavras seguras + terminações (-ção, -ões, -ência...) + poucas regras de contexto."""
    toks = list(re.finditer(r"\w+", texto))
    saida = list(texto)
    palavras = [m.group(0) for m in toks]
    for i, m in enumerate(toks):
        w = m.group(0)
        if not (w.isalpha() and w.isascii()):
            continue
        if m.start() > 0 and texto[m.start() - 1] == "-":  # clítico: fazê-la, amá-lo
            continue
        low = w.lower()
        ant = palavras[i - 1].lower() if i > 0 else ""
        prox = palavras[i + 1].lower() if i + 1 < len(palavras) else ""
        novo = None
        # contexto
        if low == "esta" and (prox in APOS_ESTA or ant in SUJEITOS_SINGULAR | {"você", "voce"}):
            novo = "está"
        elif low == "e" and ant in {"isso", "isto", "aquilo", "ele", "ela", "quem"} and prox:
            novo = "é"
        elif low == "tem" and ant in SUJEITOS_PLURAL:
            novo = "têm"
        elif low == "pais" and ant in DETERMINANTES_SING:
            novo = "país"
        elif low == "ha" and prox != "ha" and ant != "ha":
            novo = "há"
        elif low == "la" and ant not in {"a", "o"} and prox not in {"ré", "re", "mi", "si", "sol"}:
            novo = "lá"
        elif low in SEGUROS:
            novo = SEGUROS[low]
        else:
            capital = w[:1].isupper()
            for velho, nova, minimo, vale_maiuscula in _SUFIXOS:
                if low.endswith(velho) and len(low) >= minimo and low not in _EXC_AO and (vale_maiuscula or not capital):
                    novo = low[: -len(velho)] + nova
                    break
        if novo and novo != low:
            novo = _casar_caixa(w, novo)
            saida[m.start():m.end()] = list(novo) + [""] * (len(w) - len(novo))
    return "".join(saida)


def acentuar(texto: str, motor: str, margem: float):
    """Devolve (texto_com_acentos, motor_usado, aviso). O tamanho do texto nunca muda."""
    aviso = None
    if motor in ("auto", "mark"):
        if MARK.carregar():
            novo = MARK.restaurar(texto, margem)
            if len(novo) == len(texto):
                return novo, "mark", None
        elif motor == "mark":
            aviso = "Modelo Mark indisponível" + (f" ({MARK.erro})" if MARK.erro else " (ainda não baixado)") + "; usei o dicionário."
        else:
            aviso = (f"Modelo Mark indisponível ({MARK.erro}); usei o dicionário." if MARK.erro
                     else "Modelo Mark ainda não baixado; usei o dicionário, que é mais simples.")
    novo = acentuar_dicionario(texto)
    if len(novo) != len(texto):  # nunca deve acontecer
        return texto, "nenhum", "Falha interna no dicionário; texto mantido."
    return novo, "dicionario", aviso


# ====================================================================== 2) NÚMEROS E ABREVIAÇÕES
def _n2w(n: int) -> str:
    # o num2words põe vírgula entre os milhares ("mil, novecentos"); na fala isso viraria uma pausa
    return num2words(n, lang="pt_BR").replace(",", "")


def _inteiro_txt(s: str) -> int:
    return int(s.replace(".", ""))


def _decimal_txt(inteiro: str, frac: str) -> str:
    zeros = len(frac) - len(frac.lstrip("0"))
    resto = frac.lstrip("0")
    leitura = ("zero " * zeros) + (_n2w(int(resto)) if resto else "")
    return f"{_n2w(_inteiro_txt(inteiro))} vírgula {leitura.strip() or 'zero'}"


def _ordinal(n: int, feminino: bool) -> str:
    txt = num2words(n, lang="pt_BR", to="ordinal")
    if feminino:
        txt = " ".join(p[:-1] + "a" if p.endswith("o") else p for p in txt.split())
    return txt


GRANDES = {"milhão", "milhões", "bilhão", "bilhões", "trilhão", "trilhões"}
MASC_TERM_A = {
    "dia", "dias", "mapa", "mapas", "problema", "problemas", "sistema", "sistemas", "tema", "temas", "programa",
    "programas", "idioma", "idiomas", "clima", "cinema", "drama", "dramas", "poema", "poemas", "planeta",
    "planetas", "profeta", "profetas", "papa", "papas", "dilema", "dilemas", "lema", "trauma", "diploma",
    "diplomas", "guia", "guias", "sofá", "sofás", "pijama", "esquema", "esquemas", "teorema", "fonema",
}
FEM_SEM_A = {
    "vez", "vezes", "mãe", "mães", "mão", "mãos", "tribo", "tribos", "foto", "fotos", "moto", "motos", "pele",
    "peles", "noite", "noites", "tarde", "tardes", "classe", "classes", "parte", "partes", "fase", "fases", "base",
    "bases", "ponte", "pontes", "chave", "chaves", "carne", "carnes", "gente", "ordem", "ordens", "paz", "luz",
    "luzes", "cruz", "cruzes", "voz", "vozes", "nuvem", "nuvens", "imagem", "imagens", "viagem", "viagens",
    "mensagem", "mensagens", "coragem", "fonte", "fontes", "semana", "semanas",
}


def _eh_feminino(palavra: str) -> bool:
    w = palavra.lower()
    if w in MASC_TERM_A:
        return False
    if w in FEM_SEM_A:
        return True
    return w.endswith(("a", "as", "ção", "ções", "dade", "dades", "agem", "agens"))


def _feminizar(txt: str) -> str:
    p = txt.split(" ")
    for i, w in enumerate(p):
        seguinte = p[i + 1] if i + 1 < len(p) else ""
        if w == "um" and seguinte not in GRANDES:
            p[i] = "uma"
        elif w == "dois" and seguinte not in GRANDES:
            p[i] = "duas"
        elif w.endswith("entos"):
            p[i] = w[:-5] + "entas"
    return " ".join(p)


ABREV_COM_PONTO = {
    "Sr": "Senhor", "Sra": "Senhora", "Srta": "Senhorita", "Dr": "Doutor", "Dra": "Doutora",
    "Prof": "Professor", "Profa": "Professora", "Av": "Avenida", "vs": "versus", "obs": "observação",
    "tel": "telefone", "pág": "página", "págs": "páginas", "Pág": "Página",
}


def _livre(ocupado, a, b):
    return all(b <= x or a >= y for x, y in ocupado)


def expansoes(texto: str, ocupados=()):
    """Lista de (inicio, fim, de, para, tipo). Não mexe em horas, datas e versículos (10:30, 3/12, João 3:16)."""
    ocupado = list(ocupados)
    achados = []
    for m in re.finditer(r"\d{1,2}:\d{2}(?::\d{2})?|\d{1,4}/\d{1,2}(?:/\d{1,4})?", texto):
        ocupado.append((m.start(), m.end()))

    def pegar(m, para, tipo):
        if _livre(ocupado, m.start(), m.end()):
            achados.append((m.start(), m.end(), m.group(0), para, tipo))
            ocupado.append((m.start(), m.end()))

    # abreviações (não dependem de num2words)
    for m in re.finditer(r"(?<![\w])(" + "|".join(sorted(ABREV_COM_PONTO, key=len, reverse=True)) + r")\.", texto):
        pegar(m, ABREV_COM_PONTO[m.group(1)], "abrev")
    for m in re.finditer(r"(?<![\w])etc(?=\.)", texto):
        pegar(m, "etcétera", "abrev")
    for m in re.finditer(r"(?<![\w])[Nn][º°]\.?\s*(?=\d)", texto):
        pegar(m, "número ", "abrev")
    for m in re.finditer(r"(?<=\s)&(?=\s)", texto):
        pegar(m, "e", "abrev")

    if num2words is None:
        return sorted(achados)

    # valores em reais
    for m in re.finditer(r"R\$\s*(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{2}))?(?![\w])", texto):
        reais, cent = _inteiro_txt(m.group(1)), int(m.group(2) or 0)
        partes = []
        if reais or not cent:
            partes.append(f"{_n2w(reais)} {'real' if reais == 1 else 'reais'}")
        if cent:
            partes.append(f"{_n2w(cent)} {'centavo' if cent == 1 else 'centavos'}")
        pegar(m, " e ".join(partes), "numero")
    # porcentagem
    for m in re.finditer(r"(?<![\w,.])(\d+)(?:,(\d+))?\s*%", texto):
        base = _decimal_txt(m.group(1), m.group(2)) if m.group(2) else _n2w(int(m.group(1)))
        pegar(m, base + " por cento", "numero")
    # graus Celsius
    for m in re.finditer(r"(?<![\w,.])(\d+)(?:,(\d+))?\s?°\s?C(?![\w])", texto):
        base = _decimal_txt(m.group(1), m.group(2)) if m.group(2) else _n2w(int(m.group(1)))
        pegar(m, base + (" grau Celsius" if base == "um" else " graus Celsius"), "numero")
    # ordinais: 1º, 2ª
    for m in re.finditer(r"(?<![\w,.])(\d+)\s?([ºª°])(?![\w])", texto):
        pegar(m, _ordinal(int(m.group(1)), m.group(2) == "ª"), "numero")
    # decimais: 3,14
    for m in re.finditer(r"(?<![\w,.])(\d{1,3}(?:\.\d{3})*|\d+),(\d+)(?![\w,])", texto):
        pegar(m, _decimal_txt(m.group(1), m.group(2)), "numero")
    # inteiros: 7, 2025, 1.500
    for m in re.finditer(r"(?<![\w,.])(\d{1,3}(?:\.\d{3})+|\d+)(?![\w])", texto):
        resto = texto[m.end():m.end() + 2]
        if re.match(r"[.,]\d", resto):  # parte de um decimal em outro formato
            continue
        n = _n2w(_inteiro_txt(m.group(1)))
        seguinte = re.match(r"\s+([^\W\d_]+)", texto[m.end():])
        if seguinte and _eh_feminino(seguinte.group(1)):
            n = _feminizar(n)
        pegar(m, n, "numero")
    return sorted(achados)


# ====================================================================== 3) VÍRGULAS DE RESPIRAÇÃO
FRONTEIRAS = set(".!?…;:,—–()\n\"“”")
# categoria: 0 = pausa forte, 1 = média, 2 = fraca
INICIOS = {
    "mas": 0, "porém": 0, "contudo": 0, "todavia": 0, "entretanto": 0, "pois": 0, "porque": 0, "quando": 0,
    "enquanto": 0, "embora": 0, "onde": 0, "portanto": 0, "apesar": 0, "conforme": 0,
    "que": 1, "e": 1, "ou": 1, "como": 1, "então": 1,
    "para": 2, "sem": 2, "até": 2, "depois": 2, "antes": 2, "durante": 2, "sobre": 2, "mesmo": 2,
}
EXCECOES = {
    "que": {"o", "a", "os", "as", "isso", "tudo", "nada", "algo", "mais", "menos", "tão", "tanto", "assim", "ainda",
            "só", "já", "porque", "para", "sem", "um", "uma", "não", "se", "talvez", "quem", "disse", "diz"},
    "como": {"tão", "tanto", "assim", "mesmo", "não"},
    "e": {"e", "ou"},
    "para": {"e", "ou", "que", "como"},
    "mesmo": {"o", "a", "um", "uma", "e"},
}


def _dividir(idxs, atomos, maxp, min_lado, inserir):
    pesos = [max(1, len(atomos[i]["t"].split())) for i in idxs]
    total = sum(pesos)
    if total <= maxp:
        return True
    melhor, acc = None, 0
    for pos in range(1, len(idxs)):
        acc += pesos[pos - 1]
        atual, anterior = atomos[idxs[pos]], atomos[idxs[pos - 1]]
        if atual.get("tipo"):
            continue
        w, ant = atual["t"].lower(), anterior["t"].lower()
        cat = INICIOS.get(w)
        if cat is None or ant in EXCECOES.get(w, ()):
            continue
        esq, dire = acc, total - acc
        if esq < min_lado or dire < min_lado:
            continue
        pontos = abs(esq - dire) + cat * 3
        if melhor is None or pontos < melhor[0]:
            melhor = (pontos, pos)
    if melhor is None:
        return False
    pos = melhor[1]
    inserir.add(idxs[pos - 1])
    a = _dividir(idxs[:pos], atomos, maxp, min_lado, inserir)
    b = _dividir(idxs[pos:], atomos, maxp, min_lado, inserir)
    return a and b


def inserir_virgulas(atomos, max_palavras=14, min_lado=4):
    """Devolve (novos_atomos, quantas_virgulas, frases_longas_sem_ponto_seguro)."""
    frases, atual = [], []
    for i, a in enumerate(atomos):
        if a["k"] == "s" and any(c in FRONTEIRAS for c in a["t"]):
            if atual:
                frases.append(atual)
            atual = []
        elif a["k"] == "w":
            atual.append(i)
    if atual:
        frases.append(atual)
    inserir, sem_quebra = set(), 0
    for idxs in frases:
        if not _dividir(idxs, atomos, max_palavras, min_lado, inserir):
            sem_quebra += 1
    novos = []
    for i, a in enumerate(atomos):
        novos.append(a)
        if i in inserir:
            novos.append({"k": "s", "t": ",", "tipo": "virgula"})
    return novos, len(inserir), sem_quebra


# ====================================================================== montagem do resultado
def _atomizar(texto: str, spans):
    atomos, pos = [], 0

    def simples(trecho):
        for m in re.finditer(r"\w+|\W+", trecho):
            atomos.append({"k": "w" if re.match(r"\w", m.group(0)) else "s", "t": m.group(0)})

    for a, b, tipo, de, para in spans:
        simples(texto[pos:a])
        atomos.append({"k": "w", "t": para, "tipo": tipo, "de": de})
        pos = b
    simples(texto[pos:])
    return atomos


def _agrupar(atomos):
    itens, buf = [], ""
    for a in atomos:
        tipo = a.get("tipo")
        if not tipo:
            buf += a["t"]
            continue
        if buf:
            itens.append({"t": "texto", "v": buf})
            buf = ""
        if tipo == "virgula":
            itens.append({"t": "virgula"})
        else:
            itens.append({"t": tipo, "de": a["de"], "para": a["t"]})
    if buf:
        itens.append({"t": "texto", "v": buf})
    return itens


def texto_do_resultado(itens, desfeitos=()):
    """Reconstrói o texto. 'desfeitos' = índices de itens cuja mudança foi desfeita."""
    partes = []
    for i, it in enumerate(itens):
        off = i in desfeitos
        if it["t"] == "texto":
            partes.append(it["v"])
        elif it["t"] == "virgula":
            partes.append("" if off else ",")
        else:
            partes.append(it["de"] if off else it["para"])
    return "".join(partes)


def humanizar(texto, acentos=True, motor="auto", margem=0.0, numeros=True, virgulas=True, max_palavras=14):
    avisos, motor_usado = [], None
    t1 = texto
    if acentos:
        t1, motor_usado, av = acentuar(texto, motor, margem)
        if av:
            avisos.append(av)
    spans = []
    for m in re.finditer(r"\w+", texto):
        if t1[m.start():m.end()] != texto[m.start():m.end()]:
            spans.append((m.start(), m.end(), "acento", texto[m.start():m.end()], t1[m.start():m.end()]))
    n_acentos = len(spans)
    if numeros:
        if num2words is None:
            avisos.append("Números por extenso desligado: falta o complemento num2words (rode o instalar.bat de novo).")
        for a, b, de, para, tipo in expansoes(t1, [(s[0], s[1]) for s in spans]):
            spans.append((a, b, tipo, de, para))
    spans.sort(key=lambda s: s[0])
    atomos = _atomizar(t1, spans)
    n_virgulas = sem_quebra = 0
    if virgulas:
        atomos, n_virgulas, sem_quebra = inserir_virgulas(atomos, max(6, int(max_palavras)))
        if sem_quebra:
            avisos.append(f"{sem_quebra} frase(s) longa(s) sem ponto seguro para vírgula; revise à mão.")
    itens = _agrupar(atomos)
    return {
        "itens": itens,
        "motor": motor_usado,
        "avisos": avisos,
        "contagem": {
            "acentos": n_acentos,
            "expansoes": sum(1 for i in itens if i["t"] in ("numero", "abrev")),
            "virgulas": n_virgulas,
        },
    }


# ====================================================================== rotas
router = APIRouter()
DOWNLOAD = {"rodando": False, "baixado": 0, "total": 0, "erro": None}


class Pedido(BaseModel):
    texto: str
    acentos: bool = True
    motor: str = "auto"
    margem: float = 0.0
    numeros: bool = True
    virgulas: bool = True
    max_palavras: int = 14


@router.post("/api/roteiro/humanizar")
def rota_humanizar(p: Pedido):
    return humanizar(p.texto, p.acentos, p.motor, max(0.0, min(p.margem, 5.0)), p.numeros, p.virgulas, p.max_palavras)


@router.get("/api/roteiro/status")
def rota_status():
    pronto = MARK.carregar() if MARK.baixado() else False
    return {
        "mark_baixado": MARK.baixado(),
        "mark_pronto": pronto,
        "mark_erro": MARK.erro,
        "onnxruntime": find_spec("onnxruntime") is not None,
        "num2words": num2words is not None,
        "download": DOWNLOAD,
        "pasta": str(MARK_DIR),
    }


def _baixar_arquivo(url: str, tmp: Path, base_progresso: int, tentativas: int = 4):
    """Baixa para arquivo temporário, valida tamanho e repete falhas transitórias."""
    ultimo_erro = None
    total_contabilizado = False
    for tentativa in range(1, tentativas + 1):
        tmp.unlink(missing_ok=True)
        atual = 0
        try:
            with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
                esperado = int(r.headers.get("Content-Length") or 0)
                if esperado and not total_contabilizado:
                    DOWNLOAD["total"] += esperado
                    total_contabilizado = True
                while True:
                    bloco = r.read(1 << 20)
                    if not bloco:
                        break
                    f.write(bloco)
                    atual += len(bloco)
                    DOWNLOAD["baixado"] = base_progresso + atual
            if esperado and atual != esperado:
                raise IOError(f"download incompleto: {atual} de {esperado} bytes")
            if atual == 0:
                raise IOError("download vazio")
            return atual
        except Exception as e:  # noqa: BLE001
            ultimo_erro = e
            tmp.unlink(missing_ok=True)
            DOWNLOAD["baixado"] = base_progresso
            if tentativa < tentativas:
                time.sleep(min(2 ** tentativa, 8))
    raise ultimo_erro


def _baixar(refazer: bool = False):
    DOWNLOAD.update(rodando=True, baixado=0, total=0, erro=None)
    try:
        MARK_DIR.mkdir(parents=True, exist_ok=True)
        if refazer:
            for nome in MARK_URLS:
                (MARK_DIR / nome).unlink(missing_ok=True)
        for nome, url in MARK_URLS.items():
            destino = MARK_DIR / nome
            if destino.exists():
                DOWNLOAD["baixado"] += destino.stat().st_size
                continue
            tmp = destino.with_name(nome + ".baixando")
            base_progresso = DOWNLOAD["baixado"]
            _baixar_arquivo(url, tmp, base_progresso)
            tmp.replace(destino)
        MARK.resetar()
    except Exception as e:  # noqa: BLE001
        DOWNLOAD["erro"] = f"{type(e).__name__}: {e}"[:300]
    finally:
        DOWNLOAD["rodando"] = False


@router.post("/api/roteiro/baixar-modelo")
def rota_baixar(refazer: bool = False):
    if not DOWNLOAD["rodando"]:
        threading.Thread(target=_baixar, args=(refazer,), daemon=True).start()
    return {"ok": True, "pasta": str(MARK_DIR)}
