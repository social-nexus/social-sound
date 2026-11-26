@echo off
chcp 65001 >nul
setlocal
call "%~dp0config.bat"

echo ==================================================
echo  Social Sound - instalacao opcional Supertonic 3
echo ==================================================
if defined SOCIAL_NEXUS_MODELS_DIR if not exist "%SOCIAL_NEXUS_MODELS_DIR%" (
  echo ERRO: a biblioteca compartilhada nao esta disponivel:
  echo %SOCIAL_NEXUS_MODELS_DIR%
  if not "%SOCIAL_SOUND_INSTALL_FROM_UI%"=="1" pause
  exit /b 1
)
if not defined SUPERTONIC_CACHE_DIR (
  echo ERRO: a pasta de modelos Supertonic nao foi configurada.
  if not "%SOCIAL_SOUND_INSTALL_FROM_UI%"=="1" pause
  exit /b 1
)
if not exist "%SUPERTONIC_CACHE_DIR%" mkdir "%SUPERTONIC_CACHE_DIR%"
if errorlevel 1 goto falha

cd /d "%~dp0server"
if not exist ".venvs\supertonic\Scripts\python.exe" (
  echo.
  echo [1/3] Criando ambiente Python isolado do VoxCPM2...
  py -3.11 -m venv ".venvs\supertonic"
  if errorlevel 1 goto sem_python
)
set "SUPER_PY=%~dp0server\.venvs\supertonic\Scripts\python.exe"

echo.
echo [2/3] Instalando Supertonic 3 e dependencias ONNX...
"%SUPER_PY%" -m pip install --upgrade pip
if errorlevel 1 goto falha
"%SUPER_PY%" -m pip install "supertonic==1.3.1"
if errorlevel 1 goto falha
"%SUPER_PY%" -m pip check
if errorlevel 1 goto falha

echo.
echo [3/3] Baixando os modelos e as vozes predefinidas (aprox. 400 MB)...
echo Destino: %SUPERTONIC_CACHE_DIR%
"%SUPER_PY%" "%~dp0server\tts_engines\supertonic_worker.py" --download
if errorlevel 1 goto falha

echo.
echo Supertonic 3 instalado. O VoxCPM2 e seu ambiente nao foram alterados.
echo Reinicie o Social Sound para atualizar a lista de motores.
if not "%SOCIAL_SOUND_INSTALL_FROM_UI%"=="1" pause
exit /b 0

:sem_python
echo.
echo Python 3.11 nao encontrado. Instale Python 3.11 e tente novamente.
if not "%SOCIAL_SOUND_INSTALL_FROM_UI%"=="1" pause
exit /b 1

:falha
echo.
echo A instalacao do Supertonic 3 falhou. O VoxCPM2 permanece intacto.
echo Verifique a mensagem acima e tente executar este arquivo novamente.
if not "%SOCIAL_SOUND_INSTALL_FROM_UI%"=="1" pause
exit /b 1
