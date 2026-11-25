@echo off
chcp 65001 >nul
setlocal
call "%~dp0config.bat"

echo ==================================================
echo  Social Sound - instalacao opcional F5-TTS PT-BR
echo ==================================================
echo.
echo ATENCAO - LICENCAS E USO
echo O codigo F5-TTS e MIT, mas os pesos PT-BR sao CC-BY-NC-4.0.
echo Uso somente nao comercial. Nao use em videos monetizados,
echo publicidade, servicos pagos ou outras atividades comerciais.
echo Modelo PT-BR: https://huggingface.co/Cataldir/F5-TTS-pt-br
echo Codigo: https://github.com/SWivid/F5-TTS
echo.
set "CONFIRM="
set /p "CONFIRM=Voce leu e aceita a licenca CC-BY-NC-4.0 e usara somente para fins nao comerciais? (S/N): "
if /i not "%CONFIRM%"=="S" (
  echo Instalacao cancelada. Nenhuma alteracao foi feita.
  pause
  exit /b 0
)

if defined SOCIAL_NEXUS_MODELS_DIR if not exist "%SOCIAL_NEXUS_MODELS_DIR%" (
  echo ERRO: a biblioteca compartilhada nao esta disponivel: %SOCIAL_NEXUS_MODELS_DIR%
  pause
  exit /b 1
)
cd /d "%~dp0server"
if not exist ".venvs\f5tts\Scripts\python.exe" (
  echo.
  echo [1/4] Criando ambiente Python separado...
  py -3.11 -m venv ".venvs\f5tts"
  if errorlevel 1 goto sem_python
)
set "F5_PY=%~dp0server\.venvs\f5tts\Scripts\python.exe"

echo.
echo [2/4] Instalando PyTorch CUDA 12.8 e F5-TTS...
"%F5_PY%" -m pip install --upgrade pip
if errorlevel 1 goto falha
"%F5_PY%" -m pip install "torch==2.8.0" "torchaudio==2.8.0" --index-url https://download.pytorch.org/whl/cu128
if errorlevel 1 goto falha
REM TorchCodec 0.7.x e a familia compativel com PyTorch 2.8.0.
REM Fixar a versao evita combinacoes binariamente incompativeis no Windows.
"%F5_PY%" -m pip install "torchcodec==0.7.0"
if errorlevel 1 goto falha
"%F5_PY%" -m pip install "f5-tts==1.1.22"
if errorlevel 1 goto falha
"%F5_PY%" -m pip check
if errorlevel 1 goto falha

echo.
echo [3/4] Baixando o checkpoint PT-BR e o vocoder...
"%F5_PY%" "%~dp0server\tts_engines\f5tts_worker.py" --download
if errorlevel 1 goto falha

echo.
echo [4/4] Verificando instalacao...
"%F5_PY%" -c "import torch, f5_tts; print('F5-TTS instalado; CUDA disponivel:', torch.cuda.is_available())"
if errorlevel 1 goto falha

echo.
echo F5-TTS PT-BR instalado. O ambiente VoxCPM2 nao foi alterado.
echo Reinicie o Social Sound para atualizar o catalogo de motores.
pause
exit /b 0

:sem_python
echo Python 3.11 nao encontrado. Instale Python 3.11 e tente novamente.
pause
exit /b 1

:falha
echo.
echo A instalacao do F5-TTS falhou. O VoxCPM2 permanece intacto.
echo Verifique a mensagem acima e tente executar este arquivo novamente.
pause
exit /b 1
