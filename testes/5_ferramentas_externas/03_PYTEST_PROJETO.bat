@echo off
rem pytest: roda a ponte test_pytest.py (cada teste do projeto vira um caso do pytest).
rem ATENCAO: isto REPETE as baterias 1 e 2, entao NAO faz parte da bateria geral (so do menu).
rem Codigos de saida: 0 = passou | outro = falhou | 2 = test_pytest.py nao encontrado | 9 = Python/pytest nao instalado (pulado)
setlocal
cd /d "%~dp0..\.."
title Cofre - pytest: testes automatizados do projeto
if not exist "testes\6_ferramentas_dos_testes\test_pytest.py" (
  echo ERRO: testes\6_ferramentas_dos_testes\test_pytest.py nao encontrado.
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
"%COFRE_PYTHON%" -m pytest --version >nul 2>&1
if errorlevel 1 (
  echo ERRO: pytest nao foi instalado pelo wheelhouse local.
  if not defined COFRE_AUTO pause
  exit /b 9
)
echo Executando a ponte pytest do projeto - demora, pois roda todos os testes...
echo Projeto: %CD% > "%LOG%"
echo Data: %DATE% %TIME% >> "%LOG%"
echo. >> "%LOG%"
"%COFRE_PYTHON%" -m pytest "testes\6_ferramentas_dos_testes\test_pytest.py" -v >> "%LOG%" 2>&1
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
