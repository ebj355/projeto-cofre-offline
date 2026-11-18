@echo off
rem Bandit: analise estatica do cofre_senhas.py. Fica em testes\5_ferramentas_externas\ e entra sozinho na RAIZ do projeto.
rem Codigos de saida: 0 = nada encontrado | 1 = ha achados para revisar | 2 = cofre_senhas.py nao encontrado | 9 = Python/Bandit nao instalado (pulado)
rem Com a variavel COFRE_AUTO definida (bateria geral) nao mostra o relatorio na tela e nao pausa.
setlocal
cd /d "%~dp0..\.."
title Cofre - Bandit: analise estatica
if not exist "cofre_senhas.py" (
  echo ERRO: cofre_senhas.py nao encontrado na raiz do projeto.
  if not defined COFRE_AUTO pause
  exit /b 2
)
set "REL=testes\resultados\ferramentas_externas"
if not exist "%REL%" mkdir "%REL%"
set "LOG=%REL%\bandit.txt"
set "PY=py -3.13"
%PY% --version >nul 2>&1
if errorlevel 1 set "PY=py -3.12"
%PY% --version >nul 2>&1
if errorlevel 1 (
  echo AVISO: nao encontrei Python 3.13 nem 3.12 pelo inicializador py.
  if not defined COFRE_AUTO pause
  exit /b 9
)
%PY% -m bandit --version >nul 2>&1
if errorlevel 1 (
  echo AVISO: Bandit nao esta instalado. Para instalar: %PY% -m pip install bandit
  if not defined COFRE_AUTO pause
  exit /b 9
)
echo Analisando cofre_senhas.py com Bandit...
echo Projeto: %CD% > "%LOG%"
echo Data: %DATE% %TIME% >> "%LOG%"
echo. >> "%LOG%"
%PY% -m bandit -r "cofre_senhas.py" -f txt >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
echo.>> "%LOG%"
echo Codigo de saida: %RC%>> "%LOG%"
if not defined COFRE_AUTO type "%LOG%"
echo.
echo Relatorio salvo em: %LOG%
echo Codigo de saida: %RC%  - 0 = nada encontrado, 1 = ha achados para revisar
echo Nota: achados do Bandit precisam de revisao; nem todo alerta e vulnerabilidade.
if not defined COFRE_AUTO pause
exit /b %RC%
