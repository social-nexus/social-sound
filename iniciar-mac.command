#!/usr/bin/env bash
# Duplo clique no Mac: inicia o Social Sound.
cd "$(dirname "$0")" || exit 1
bash ./iniciar-linux.sh
echo
read -r -p "Pressione Enter para fechar esta janela..." _
