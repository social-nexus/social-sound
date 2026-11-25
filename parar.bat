@echo off
REM Encerra apenas o processo server.py desta instalacao do Social Sound.
set "SERVER_SCRIPT=%~dp0server\server.py"
powershell -NoProfile -Command "$target=$env:SERVER_SCRIPT; $listeners=Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue; foreach($l in $listeners){$p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$l.OwningProcess); if($p -and $p.CommandLine -like ('*'+$target+'*')){taskkill.exe /F /T /PID $p.ProcessId | Out-Null; Write-Host 'Servidor Social Sound encerrado.'} elseif($p){Write-Host 'A porta 8000 pertence a outro programa; ele nao sera encerrado.'}}"
echo Social Sound encerrado (se estava ativo).
timeout /t 2 >nul
