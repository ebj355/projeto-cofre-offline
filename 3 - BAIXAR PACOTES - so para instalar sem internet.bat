@echo off
rem Baixa (com hash conferido) tudo o que a instalacao usa para a pasta "pacotes" ao lado deste arquivo.
rem Depois disso o 1 - INSTALAR O COFRE - compila e instala.bat instala SEM internet. Precisa de internet SO AGORA.
cd /d "%~dp0"
set "COFRE_BAIXAR_PACOTES=1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar_cofre.ps1" H
set "COFRE_BAIXAR_PACOTES="
if errorlevel 1 (
  echo.
  echo O download terminou com ERRO. Leia as mensagens acima.
  pause
)
exit /b %errorlevel%
