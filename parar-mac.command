#!/usr/bin/env bash
# Duplo clique no Mac: encerra o Social Sound.
cd "$(dirname "$0")" || exit 1
bash ./parar-linux.sh
echo
read -r -p "Pressione Enter para fechar esta janela..." _
