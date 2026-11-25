#!/usr/bin/env bash
# Funcoes comuns usadas por instalar.sh, iniciar.sh e parar.sh (nao precisa rodar direto).

OS="$(uname -s)"
ARCH="$(uname -m)"
case "$OS" in
  Darwin) SISTEMA=mac ;;
  Linux)  SISTEMA=linux ;;
  *) echo "Sistema nao suportado: $OS. No Windows, use os arquivos .bat."; exit 1 ;;
esac

# O instalador do uv grava aqui
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

# Python 3.11: procura no sistema e, se nao achar, usa o uv (se existir) para baixar um.
python_ok() { "$1" -c 'import sys; sys.exit(0 if sys.version_info[:2]==(3,11) else 1)' >/dev/null 2>&1; }
find_python() {
  local c p
  for c in python3.11 python3 python; do
    if command -v "$c" >/dev/null 2>&1 && python_ok "$c"; then command -v "$c"; return 0; fi
  done
  if command -v uv >/dev/null 2>&1; then
    uv python install 3.11 >&2 || return 1
    p="$(uv python find 3.11 2>/dev/null)"
    [ -n "$p" ] && { echo "$p"; return 0; }
  fi
  return 1
}

dica_python() {
  echo
  echo "Python 3.11 nao encontrado."
  if [ "$SISTEMA" = mac ]; then
    echo "Instale com:  brew install python@3.11   (ou baixe em python.org)"
  else
    echo "Debian/Ubuntu:  sudo apt install python3.11 python3.11-venv"
    echo "Se a sua distribuicao nao tiver o 3.11, instale o uv (https://docs.astral.sh/uv/) e rode este script de novo: ele baixa o Python 3.11 sozinho."
  fi
  echo "Depois rode este script de novo."
}

# Porta aberta? (usa so recursos do bash, sem curl)
porta_aberta() { (exec 3<>"/dev/tcp/127.0.0.1/$1") >/dev/null 2>&1; }

# Espera a porta abrir (ate $2 segundos; padrao 120)
esperar_porta() {
  local n=0 max="${2:-120}"
  while [ "$n" -lt "$max" ]; do
    porta_aberta "$1" && return 0
    sleep 2; n=$((n+2))
  done
  return 1
}

# Abre uma janela propria do navegador (sem barra de endereco) quando possivel
abrir_janela() {
  local url="$1" b app
  if [ "$SISTEMA" = mac ]; then
    for app in "Google Chrome" "Microsoft Edge" "Brave Browser" "Chromium"; do
      if [ -d "/Applications/$app.app" ] || [ -d "$HOME/Applications/$app.app" ]; then
        open -na "$app" --args --app="$url" --window-size=1400,900 && return 0
      fi
    done
    open "$url"
  else
    for b in google-chrome google-chrome-stable chromium chromium-browser microsoft-edge microsoft-edge-stable brave-browser; do
      if command -v "$b" >/dev/null 2>&1; then
        nohup "$b" --app="$url" --window-size=1400,900 >/dev/null 2>&1 &
        return 0
      fi
    done
    if command -v xdg-open >/dev/null 2>&1; then xdg-open "$url" >/dev/null 2>&1 & else echo "Abra no navegador: $url"; fi
  fi
}

# Encerra apenas o processo do Social Sound registrado no PID file.
# A linha de comando precisa apontar para o server.py desta instalação.
encerrar_pidfile() {
  local f="$1" esperado="$2" pid cmd
  [ -f "$f" ] || return 0
  pid="$(cat "$f" 2>/dev/null)"
  if ! [[ "$pid" =~ ^[0-9]+$ ]]; then
    echo "PID file invalido; removendo sem encerrar processos."
    rm -f "$f"
    return 0
  fi
  cmd="$(ps -p "$pid" -o command= 2>/dev/null)"
  if [ -z "$cmd" ] || [[ "$cmd" != *"$esperado"* ]]; then
    echo "PID $pid nao corresponde ao server.py desta instalacao; nao sera encerrado."
    rm -f "$f"
    return 0
  fi
  pkill -TERM -P "$pid" 2>/dev/null
  kill -TERM "$pid" 2>/dev/null
  sleep 2
  if kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid" 2>/dev/null
  fi
  rm -f "$f"
}
