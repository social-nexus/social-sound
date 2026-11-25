@echo off
REM Configuracao compartilhada de modelos usada tambem pelo Social Music Beat.
set "SOCIAL_NEXUS_MODELS_DIR="
if exist "%LOCALAPPDATA%\SocialNexus\model-storage.bat" call "%LOCALAPPDATA%\SocialNexus\model-storage.bat"

if defined SOCIAL_NEXUS_MODELS_DIR (
  REM GGUFs e caches Hugging Face/PyTorch ficam na biblioteca central.
  set "SOCIAL_SOUND_MODELS_DIR=%SOCIAL_NEXUS_MODELS_DIR%\LLM"
  set "HF_HOME=%SOCIAL_NEXUS_MODELS_DIR%\HuggingFace"
  set "HF_HUB_CACHE=%SOCIAL_NEXUS_MODELS_DIR%\HuggingFace\hub"
  set "HUGGINGFACE_HUB_CACHE=%SOCIAL_NEXUS_MODELS_DIR%\HuggingFace\hub"
  set "TRANSFORMERS_CACHE=%SOCIAL_NEXUS_MODELS_DIR%\HuggingFace\hub"
  set "TORCH_HOME=%SOCIAL_NEXUS_MODELS_DIR%\Torch"
)

REM Alternativa manual para a pasta de GGUF, caso nao use a biblioteca global.
REM set "SOCIAL_SOUND_MODELS_DIR=D:\IA_MODELS\LLM"

REM Opcional: forcar CPU para VoxCPM2.
REM set "DEVICE=cpu"
