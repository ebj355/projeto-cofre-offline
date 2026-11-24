@rem ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
@echo off
rem pytest: roda a ponte test_pytest.py (cada teste do projeto vira um caso do pytest).
rem ATENCAO: isto REPETE as baterias 1 e 2, entao NAO faz parte da bateria geral (so do menu).
rem Codigos de saida: 0 = passou | outro = falhou | 2 = test_pytest.py nao encontrado | 9 = Python/pytest nao instalado (pulado)
setlocal
cd /d "%~dp0..\.."
set "PYTHONDONTWRITEBYTECODE=1"
title Cofre - pytest: testes automatizados do projeto
if not exist "testes\6_TESTE_ferramentas_dos_testes\test_pytest.py" (
  echo ERRO: testes\6_TESTE_ferramentas_dos_testes\test_pytest.py nao encontrado.
  if not defined COFRE_AUTO pause
  exit /b 2
)
set "REL=testes\resultados"
if not exist "%REL%" mkdir "%REL%"
set "LOG=%REL%\pytest.txt"
call "%~dp0preparar_ambiente_offline.bat"
if errorlevel 1 (
  if not defined COFRE_AUTO pause
  exit /b 9
)
"%COFRE_PYTHON%" -m pytest -p no:cacheprovider --version >nul 2>&1
if errorlevel 1 (
  echo ERRO: pytest nao foi instalado pelo wheelhouse local.
  if not defined COFRE_AUTO pause
  exit /b 9
)
set "CACHE_PROPRIO="
if not defined COFRE_TEST_CACHE_DIR (
  for %%I in ("%~dp0..\..\CACHE_PROJETO_NAO_MEXER\testes\_cache_pytest_%RANDOM%_%RANDOM%") do set "COFRE_TEST_CACHE_DIR=%%~fI"
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
set "COFRE_TEST_PYTEST_CACHE=%COFRE_TEST_CACHE_DIR%\pytest"
set "PYTHONPYCACHEPREFIX=%COFRE_TEST_CACHE_DIR%\pycache"
set "TEMP=%COFRE_TEST_CACHE_DIR%"
set "TMP=%COFRE_TEST_CACHE_DIR%"
set "TMPDIR=%COFRE_TEST_CACHE_DIR%"
set "PYTHONDONTWRITEBYTECODE=1"
echo Executando a ponte pytest do projeto - demora, pois roda todos os testes...
echo Projeto: %CD% > "%LOG%"
echo Data: %DATE% %TIME% >> "%LOG%"
echo. >> "%LOG%"
"%COFRE_PYTHON%" -m pytest -o "cache_dir=%COFRE_TEST_PYTEST_CACHE%" "testes\6_TESTE_ferramentas_dos_testes\test_pytest.py" -v >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
if defined CACHE_PROPRIO if exist "%COFRE_TEST_CACHE_DIR%" (
  rmdir /s /q "%COFRE_TEST_CACHE_DIR%" >nul 2>nul
  if exist "%COFRE_TEST_CACHE_DIR%" (
    echo ERRO: nao consegui remover o cache temporario %COFRE_TEST_CACHE_DIR%.>> "%LOG%"
    set "RC=1"
  )
)
echo.>> "%LOG%"
echo Codigo de saida: %RC%>> "%LOG%"
if not defined COFRE_AUTO type "%LOG%"
echo.
echo Relatorio salvo em: %LOG%
echo Codigo de saida: %RC%
echo ATENCAO: os testes do projeto usam pastas temporarias e nao tocam no seu cofre pessoal; mesmo assim, tenha backup separado.
if not defined COFRE_AUTO pause
exit /b %RC%
