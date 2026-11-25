@echo off
chcp 65001 >nul
call "%~dp0config.bat"
echo Ligando o Social Sound... (a primeira vez demora um pouco)
REM Servidor local principal (voz, roteiro, dialogo e legendas)
cd /d "%~dp0server"
start "Social Sound - servidor" /min cmd /c "call .venv\Scripts\activate && python server.py"
:espera_ini
set /a n=0
:espera
timeout /t 2 /nobreak >nul
curl -s -o nul http://localhost:8000/estudio/
if not errorlevel 1 goto abrir
set /a n+=1
if %n% LSS 60 goto espera
:abrir
start "" msedge --app=http://localhost:8000/estudio/ --window-size=1400,900
exit
