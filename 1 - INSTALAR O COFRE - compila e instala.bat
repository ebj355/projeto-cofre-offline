@echo off
setlocal
cd /d "%~dp0"
title Cofre de Senhas - compilar e instalar
echo.
echo  === COFRE DE SENHAS: iniciar a compilacao ===
echo  Pasta: %CD%
echo.
rem --- 1) conferencias antes de comecar (nada e instalado aqui) ---
if not exist "%~dp0cofre_senhas.py" (echo  ERRO: falta o cofre_senhas.py nesta pasta. & goto :erro)
if not exist "%~dp0instalar_cofre.ps1" (echo  ERRO: falta o instalar_cofre.ps1 nesta pasta. & goto :erro)
echo  ---------------------------------------------------------------
echo  Modo de instalacao das bibliotecas:
set "NPAC=0"
if exist "%~dp0pacotes\" for /f %%A in ('dir /b /a-d "%~dp0pacotes" 2^>nul ^| find /c /v ""') do set "NPAC=%%A"
if %NPAC% GTR 2 (echo    OFFLINE: %NPAC% arquivos na pasta pacotes - nao baixa nada, so confere os hashes.) else (echo    ONLINE: a pasta pacotes esta vazia; as bibliotecas serao baixadas e conferidas por hash.)
echo.
echo  ---------------------------------------------------------------
echo  Python:
where py >nul 2>nul && (py -3.13 -c "import sys;print('   ',sys.version.split()[0],'encontrado')" 2>nul || echo    3.13 nao encontrado: o instalador oferece instalar.) || (where python >nul 2>nul && (python -c "import sys;print('   ',sys.version.split()[0],'encontrado')") || echo    nao encontrado: o instalador oferece instalar.)
echo.
echo  ---------------------------------------------------------------
echo  SHA-256 do cofre_senhas.py (o instalador vai pedir os 16 primeiros caracteres):
certutil -hashfile "%~dp0cofre_senhas.py" SHA256 | findstr /v ":"
echo.
rem --- 2) registro de depuracao desta execucao (so texto da tela; nenhuma senha e digitada aqui) ---
set "LOGDIR=%~dp0logs_de_compilacao"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "STAMP=%%T"
set "LOG=%LOGDIR%\compilar-%STAMP%.log"
echo  ---------------------------------------------------------------
echo  Registro desta execucao: %LOG%
echo.
echo  O instalador vai perguntar PRIMEIRO onde instalar: 1 = portatil (pendrive) ou 2 = no computador.
echo  ---------------------------------------------------------------
echo.
rem --- 3) chama o instalador (aceita a letra do pendrive: 1 - INSTALAR O COFRE - compila e instala.bat H) ---
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Transcript -LiteralPath '%LOG%' -Force | Out-Null; try { & '%~dp0instalar_cofre.ps1' %* ; $c = $LASTEXITCODE } finally { Stop-Transcript | Out-Null }; exit $c"
set "COD=%errorlevel%"
if not "%COD%"=="0" goto :erro
echo.
echo  Concluido. O registro desta execucao ficou em: %LOG%
echo  O instalador tambem grava logs\instalacao-*.log e instalacao_detalhada.log na pasta CofreSenhas do destino.
pause
exit /b 0
:erro
echo.
echo  A compilacao terminou com ERRO (codigo %COD%). Veja as mensagens acima, o registro em %LOG%
echo  e o instalacao_detalhada.log na pasta CofreSenhas do destino.
pause
exit /b 1
