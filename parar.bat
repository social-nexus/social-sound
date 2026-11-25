@echo off
REM Encerra o servidor local do Social Sound.
for %%p in (8000) do (
  for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%%p" ^| findstr "LISTENING"') do taskkill /F /T /PID %%a >nul 2>&1
)
echo Social Sound encerrado.
timeout /t 2 >nul
