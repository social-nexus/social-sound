@echo off
chcp 65001 >nul
setlocal
call "%~dp0config.bat"

echo ==================================================
echo  Social Sound - instalacao opcional OmniVoice
echo ==================================================
echo.
echo ATENCAO - LICENCAS E USO
echo Os pesos do OmniVoice sao CC-BY-NC: somente uso nao comercial.
echo Nao use para videos monetizados, publicidade ou servicos pagos.
echo O tokenizer Higgs Audio V2 tem uma licenca comunitaria separada.
echo Leia os termos antes de continuar:
echo https://huggingface.co/k2-fsa/OmniVoice
echo https://huggingface.co/bosonai/higgs-audio-v2-tokenizer
echo.
if not "%SOCIAL_SOUND_INSTALL_FROM_UI%"=="1" (
  set "CONFIRM="
  set /p "CONFIRM=Voce leu e aceita as licencas e usara somente para fins nao comerciais? (S/N): "
  if /i not "%CONFIRM%"=="S" (
    echo Instalacao cancelada. Nenhuma alteracao foi feita.
    if not "%SOCIAL_SOUND_INSTALL_FROM_UI%"=="1" pause
    exit /b 0
  )
) else if not "%SOCIAL_SOUND_LICENSE_ACCEPTED%"=="1" (
  echo ERRO: aceite da licenca nao foi confirmado pela interface.
  exit /b 1
)

if defined SOCIAL_NEXUS_MODELS_DIR if not exist "%SOCIAL_NEXUS_MODELS_DIR%" (
  echo ERRO: a biblioteca compartilhada nao esta disponivel: %SOCIAL_NEXUS_MODELS_DIR%
  if not "%SOCIAL_SOUND_INSTALL_FROM_UI%"=="1" pause
  exit /b 1
)
cd /d "%~dp0server"
if not exist ".venvs\omnivoice\Scripts\python.exe" (
  echo.
  echo [1/4] Criando ambiente Python separado...
  py -3.11 -m venv ".venvs\omnivoice"
  if errorlevel 1 goto sem_python
)
set "OMNI_PY=%~dp0server\.venvs\omnivoice\Scripts\python.exe"

echo.
echo [2/4] Instalando PyTorch CUDA 12.8 e OmniVoice...
"%OMNI_PY%" -m pip install --upgrade pip
if errorlevel 1 goto falha
"%OMNI_PY%" -m pip install "torch==2.8.0" "torchaudio==2.8.0" --index-url https://download.pytorch.org/whl/cu128
if errorlevel 1 goto falha
"%OMNI_PY%" -m pip install "omnivoice==0.2.1"
if errorlevel 1 goto falha
"%OMNI_PY%" -m pip check
if errorlevel 1 goto falha

echo.
echo [3/4] Baixando modelo e tokenizer para o cache compartilhado...
"%OMNI_PY%" "%~dp0server\tts_engines\omnivoice_worker.py" --download
if errorlevel 1 goto falha

echo.
echo [4/4] Verificando instalacao...
"%OMNI_PY%" -c "import torch, omnivoice; print('OmniVoice instalado; CUDA disponivel:', torch.cuda.is_available())"
if errorlevel 1 goto falha

echo.
echo OmniVoice instalado. O ambiente VoxCPM2 nao foi alterado.
echo Reinicie o Social Sound para atualizar o catalogo.
if not "%SOCIAL_SOUND_INSTALL_FROM_UI%"=="1" pause
exit /b 0

:sem_python
echo Python 3.11 nao encontrado. Instale Python 3.11 e tente novamente.
if not "%SOCIAL_SOUND_INSTALL_FROM_UI%"=="1" pause
exit /b 1

:falha
echo.
echo A instalacao do OmniVoice falhou. O VoxCPM2 permanece intacto.
echo Verifique a mensagem acima. Voce pode executar este arquivo novamente.
if not "%SOCIAL_SOUND_INSTALL_FROM_UI%"=="1" pause
exit /b 1
