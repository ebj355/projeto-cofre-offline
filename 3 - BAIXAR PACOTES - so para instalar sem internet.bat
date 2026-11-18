@echo off
rem Prepara dependencias de instalacao e de teste para uso offline. Precisa de internet somente nesta etapa.
cd /d "%~dp0"
set "COFRE_BAIXAR_PACOTES=1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar_cofre.ps1" H
set "COFRE_BAIXAR_PACOTES="
if errorlevel 1 (
  echo.
  echo O download terminou com ERRO. Leia as mensagens acima.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0baixar_pacotes_offline.ps1"
if errorlevel 1 (
  echo.
  echo A preparacao das ferramentas offline terminou com ERRO. Leia as mensagens acima.
  pause
  exit /b 1
)
exit /b 0
