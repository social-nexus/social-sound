#!/usr/bin/env bash
# Social Sound - inicia servidor local e abre janela do aplicativo.
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$AQUI/_comum.sh"
. "$AQUI/config.sh"
if [ -n "${SOCIAL_NEXUS_MODELS_DIR:-}" ] && [ ! -d "$SOCIAL_NEXUS_MODELS_DIR" ]; then
  echo "ERRO: a biblioteca compartilhada de modelos nao esta disponivel: $SOCIAL_NEXUS_MODELS_DIR"
  echo "Conecte a unidade configurada ou ajuste SOCIAL_NEXUS_MODELS_DIR."
  exit 1
fi
mkdir -p "$AQUI/logs"
if [ ! -x "$AQUI/server/.venv/bin/python" ]; then
  echo "O Social Sound ainda nao foi instalado. Rode o instalar-linux.sh primeiro."
  exit 1
fi
echo "Ligando o Social Sound... (a primeira vez demora um pouco)"
if porta_aberta 8000; then
  if social_sound_responde; then
    echo "Social Sound ja esta ligado."
  else
    echo "ERRO: a porta 8000 esta sendo usada por outro programa. Social Sound nao sera iniciado."
    exit 1
  fi
else
  ( cd "$AQUI/server" && nohup .venv/bin/python "$AQUI/server/server.py" >"$AQUI/logs/servidor.log" 2>&1 & echo $! >"$AQUI/logs/servidor.pid" )
fi
if esperar_social_sound 120; then
  abrir_janela "http://localhost:8000/estudio/"
  echo "Pronto. Para encerrar e liberar a memoria, rode parar-linux.sh."
else
  echo "O servidor nao respondeu a tempo. Veja: $AQUI/logs/servidor.log"
  exit 1
fi
