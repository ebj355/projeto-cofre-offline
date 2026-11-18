@echo off
rem pytest: roda a ponte test_pytest.py (cada teste do projeto vira um caso do pytest).
rem ATENCAO: isto REPETE as baterias 1 e 2, entao NAO faz parte da bateria geral (so do menu).
rem Codigos de saida: 0 = passou | outro = falhou | 2 = test_pytest.py nao encontrado | 9 = Python/pytest nao instalado (pulado)
setlocal
cd /d "%~dp0..\.."
title Cofre - pytest: testes automatizados do projeto
if not exist "testes\ferramentas_dos_testes\test_pytest.py" (
  echo ERRO: testes\ferramentas_dos_testes\test_pytest.py nao encontrado.
  if not defined COFRE_AUTO pause
  exit /b 2
)
set "REL=testes\resultados\ferramentas_externas"
if not exist "%REL%" mkdir "%REL%"
set "LOG=%REL%\pytest.txt"
set "PY=py -3.13"
%PY% --version >nul 2>&1
if errorlevel 1 set "PY=py -3.12"
%PY% --version >nul 2>&1
if errorlevel 1 (
  echo AVISO: nao encontrei Python 3.13 nem 3.12 pelo inicializador py.
  if not defined COFRE_AUTO pause
  exit /b 9
)
%PY% -m pytest --version >nul 2>&1
if errorlevel 1 (
  echo AVISO: pytest nao esta instalado. Para instalar: %PY% -m pip install pytest
  if not defined COFRE_AUTO pause
  exit /b 9
)
echo Executando a ponte pytest do projeto - demora, pois roda todos os testes...
echo Projeto: %CD% > "%LOG%"
echo Data: %DATE% %TIME% >> "%LOG%"
echo. >> "%LOG%"
%PY% -m pytest "testes\ferramentas_dos_testes\test_pytest.py" -v >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
echo.>> "%LOG%"
echo Codigo de saida: %RC%>> "%LOG%"
if not defined COFRE_AUTO type "%LOG%"
echo.
echo Relatorio salvo em: %LOG%
echo Codigo de saida: %RC%
echo ATENCAO: os testes do projeto usam pastas temporarias e nao tocam no seu cofre pessoal; mesmo assim, tenha backup separado.
if not defined COFRE_AUTO pause
exit /b %RC%
