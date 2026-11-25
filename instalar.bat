@echo off
chcp 65001 >nul
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
call "%~dp0config.bat"
if defined SOCIAL_NEXUS_MODELS_DIR if not exist "%SOCIAL_NEXUS_MODELS_DIR%" (
  echo.
  echo ERRO: A biblioteca compartilhada de modelos nao esta disponivel:
  echo %SOCIAL_NEXUS_MODELS_DIR%
  echo Conecte a unidade configurada ou ajuste o armazenamento pelo Social Music Beat.
  pause
  exit /b 1
)
echo ==================================================
echo  Social Sound - instalacao completa
echo  (motor de voz, aba Roteiro e aba Legendas)
echo ==================================================
cd /d "%~dp0server"

echo.
echo [1/6] Criando o ambiente Python 3.11...
py -3.11 -m venv .venv
if errorlevel 1 goto sem_python
if not exist ".venv\Scripts\python.exe" goto sem_python
call .venv\Scripts\activate
python -m pip install --upgrade pip
if errorlevel 1 goto falha

echo.
echo [2/6] Instalando o motor de voz (PyTorch e VoxCPM, varios GB)...
python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
if errorlevel 1 goto falha
python -m pip install voxcpm fastapi "uvicorn[standard]" python-multipart soundfile httpx "keyring>=25.5,<26"
if errorlevel 1 goto falha
python -m pip check
if errorlevel 1 goto falha

echo.
echo [3/6] Instalando os complementos das abas Roteiro e Legendas...
python -m pip install onnxruntime num2words faster-whisper
if errorlevel 1 echo AVISO: nao consegui instalar algum complemento. As abas Roteiro e Legendas podem ficar limitadas. Rode este instalar.bat de novo mais tarde.
python -m python -m pip check
if errorlevel 1 echo AVISO: foram encontrados conflitos nas dependencias opcionais. Consulte a mensagem acima.

echo.
echo [4/6] Baixando o modelo de voz VoxCPM2 (varios GB, pode demorar)...
python -c "from huggingface_hub import snapshot_download; snapshot_download('openbmb/VoxCPM2')"
if errorlevel 1 echo AVISO: o modelo de voz nao terminou de baixar. Ele sera baixado na primeira narracao, ou rode este instalar.bat de novo.

echo.
echo [5/6] Baixando o modelo de acentos da aba Roteiro (cerca de 42 MB)...
python -c "import roteiro; roteiro._baixar(); print('erro:', roteiro.DOWNLOAD['erro'])"

echo.
echo [6/6] Baixando o modelo Whisper base da aba Legendas (cerca de 150 MB)...
python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8'); print('Whisper base ok')"
if errorlevel 1 echo AVISO: o modelo Whisper sera baixado no primeiro uso do modo Preciso.

echo.
echo Pronto! Agora use o iniciar.bat
pause
exit /b 0

:sem_python
echo.
echo Python 3.11 nao encontrado. Instale em python.org e marque "Add python.exe to PATH". Depois rode este instalar.bat de novo.
pause
exit /b 1

:falha
echo.
echo A instalacao falhou. Leia a mensagem acima e tente de novo.
pause
exit /b 1
