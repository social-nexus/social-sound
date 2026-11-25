#!/usr/bin/env bash
# Social Sound - inicia servidor local e abre janela do aplicativo.
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$AQUI/_comum.sh"
mkdir -p "$AQUI/logs"
if [ ! -x "$AQUI/server/.venv/bin/python" ]; then
  echo "O Social Sound ainda nao foi instalado. Rode o instalar-linux.sh primeiro."
  exit 1
fi
echo "Ligando o Social Sound... (a primeira vez demora um pouco)"
if porta_aberta 8000; then
  echo "O servidor local ja esta ligado."
else
  ( cd "$AQUI/server" && nohup .venv/bin/python server.py >"$AQUI/logs/servidor.log" 2>&1 & echo $! >"$AQUI/logs/servidor.pid" )
fi
if esperar_porta 8000 120; then
  abrir_janela "http://localhost:8000/estudio/"
  echo "Pronto. Para encerrar e liberar a memoria, rode parar-linux.sh."
else
  echo "O servidor nao respondeu a tempo. Veja: $AQUI/logs/servidor.log"
  exit 1
fi
