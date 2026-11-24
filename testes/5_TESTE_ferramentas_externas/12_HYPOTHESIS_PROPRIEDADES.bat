@rem ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
@echo off
rem Hypothesis: roda testes\1_TESTE_motor_do_cofre\teste_propriedades_hypothesis.py (ida e volta do cofre e CSV hostil com milhares de entradas geradas).
rem Codigos de saida: 0 = passou | 1 = falhou | 9 = ambiente/hypothesis ausente (pulado)
setlocal
cd /d "%~dp0..\.."
title Cofre - Hypothesis: testes por propriedades
set "REL=testes\resultados"
if not exist "%REL%" mkdir "%REL%"
set "LOG=%REL%\hypothesis.txt"
call "%~dp0preparar_ambiente_offline.bat"
if errorlevel 1 (
  if not defined COFRE_AUTO pause
  exit /b 9
)
set "CACHE_PROPRIO="
if not defined COFRE_TEST_CACHE_DIR (
  for %%I in ("%~dp0..\..\CACHE_PROJETO_NAO_MEXER\testes\_cache_hypothesis_%RANDOM%_%RANDOM%") do set "COFRE_TEST_CACHE_DIR=%%~fI"
  set "CACHE_PROPRIO=1"
)
if defined CACHE_PROPRIO (
  if exist "%COFRE_TEST_CACHE_DIR%" (
    echo ERRO: o caminho de cache temporario ja existe; nada preexistente sera apagado.
    exit /b 1
  )
  mkdir "%COFRE_TEST_CACHE_DIR%" >nul 2>nul
  if not exist "%COFRE_TEST_CACHE_DIR%" (
    echo ERRO: nao consegui criar o cache temporario dentro de testes\.
    exit /b 1
  )
)
set "COFRE_TEST_HYPOTHESIS_DB=%COFRE_TEST_CACHE_DIR%\hypothesis"
set "HYPOTHESIS_STORAGE_DIRECTORY=%COFRE_TEST_CACHE_DIR%\hypothesis_storage"
set "PYTHONPYCACHEPREFIX=%COFRE_TEST_CACHE_DIR%\pycache"
set "PYTHONDONTWRITEBYTECODE=1"
set "TEMP=%COFRE_TEST_CACHE_DIR%"
set "TMP=%COFRE_TEST_CACHE_DIR%"
set "TMPDIR=%COFRE_TEST_CACHE_DIR%"
echo Projeto: %CD% > "%LOG%"
echo Data: %DATE% %TIME% >> "%LOG%"
"%COFRE_PYTHON%" "testes\1_TESTE_motor_do_cofre\teste_propriedades_hypothesis.py" >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
if defined CACHE_PROPRIO if exist "%COFRE_TEST_CACHE_DIR%" (
  rmdir /s /q "%COFRE_TEST_CACHE_DIR%" >nul 2>nul
  if exist "%COFRE_TEST_CACHE_DIR%" (
    echo AVISO: nao consegui remover o cache temporario %COFRE_TEST_CACHE_DIR%.
    set "RC=1"
  )
)
>> "%LOG%" echo Codigo de saida: %RC%
if not defined COFRE_AUTO type "%LOG%"
echo Relatorio salvo em: %LOG%
echo Nota: trabalha em pastas temporarias; nunca toca no seu cofre.dat. Quando falha, o Hypothesis mostra o menor exemplo que reproduz.
if not defined COFRE_AUTO pause
exit /b %RC%
