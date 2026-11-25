#!/usr/bin/env bash
# Social Sound - instalacao completa para Linux e macOS (equivalente ao instalar.bat)
set -u
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$AQUI/_comum.sh"
. "$AQUI/config.sh"
export HF_HUB_DISABLE_SYMLINKS_WARNING=1
if [ -n "${SOCIAL_NEXUS_MODELS_DIR:-}" ] && [ ! -d "$SOCIAL_NEXUS_MODELS_DIR" ]; then
  echo "ERRO: a biblioteca compartilhada de modelos nao esta disponivel: $SOCIAL_NEXUS_MODELS_DIR"
  echo "Conecte a unidade configurada ou ajuste SOCIAL_NEXUS_MODELS_DIR."
  exit 1
fi

echo "=================================================="
echo " Social Sound - instalacao completa"
echo " (motor de voz, aba Roteiro e aba Legendas)"
echo "=================================================="
cd "$AQUI/server" || exit 1

echo
echo "[1/6] Criando o ambiente Python 3.11..."
PY="$(find_python)" || { dica_python; exit 1; }
"$PY" -m venv .venv || {
  echo "Nao consegui criar o ambiente. No Debian/Ubuntu instale tambem o pacote python3.11-venv."
  exit 1
}
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install --upgrade pip

echo
echo "[2/6] Instalando o motor de voz (PyTorch e VoxCPM, varios GB)..."
if [ "$SISTEMA" = linux ] && command -v nvidia-smi >/dev/null 2>&1; then
  echo "Placa NVIDIA encontrada: instalando PyTorch com CUDA."
  pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124 || { echo "A instalacao falhou."; exit 1; }
elif [ "$SISTEMA" = mac ] && [ "$ARCH" = x86_64 ]; then
  echo "AVISO: Mac com Intel. O PyTorch mais novo nao existe para este Mac; usando a ultima versao compativel (2.2.2)."
  echo "       O VoxCPM pode nao instalar nesta versao. Se falhar, este computador nao e suportado para a narracao."
  pip install "torch==2.2.2" "torchaudio==2.2.2" "numpy<2" || { echo "A instalacao falhou."; exit 1; }
else
  echo "Sem placa NVIDIA: instalando PyTorch para CPU (a narracao fica mais lenta)."
  pip install torch torchaudio || { echo "A instalacao falhou."; exit 1; }
fi
pip install voxcpm fastapi "uvicorn[standard]" python-multipart soundfile httpx "keyring>=25.5,<26" || { echo "A instalacao falhou."; exit 1; }

echo
echo "[3/6] Instalando os complementos das abas Roteiro e Legendas..."
pip install onnxruntime num2words faster-whisper ||
  echo "AVISO: nao consegui instalar algum complemento. As abas Roteiro e Legendas podem ficar limitadas. Rode este instalar.sh de novo mais tarde."

echo
echo "[4/6] Baixando o modelo de voz VoxCPM2 (varios GB, pode demorar)..."
python -c "from huggingface_hub import snapshot_download; snapshot_download('openbmb/VoxCPM2')" ||
  echo "AVISO: o modelo de voz nao terminou de baixar. Ele sera baixado na primeira narracao, ou rode este instalar.sh de novo."

echo
echo "[5/6] Baixando o modelo de acentos da aba Roteiro (cerca de 42 MB)..."
python -c "import roteiro; roteiro._baixar(); print('erro:', roteiro.DOWNLOAD['erro'])"

echo
echo "[6/6] Baixando o modelo Whisper base da aba Legendas (cerca de 150 MB)..."
python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8'); print('Whisper base ok')" ||
  echo "AVISO: o modelo Whisper sera baixado no primeiro uso do modo Preciso."

echo
echo "Pronto! Agora use o iniciar.sh (ou iniciar.command no Mac)."
