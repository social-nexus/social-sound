#!/usr/bin/env bash
# Encerra o servidor local do Social Sound.
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$AQUI/_comum.sh"
encerrar_pidfile "$AQUI/logs/servidor.pid"
encerrar_porta 8000
echo "Social Sound encerrado."
