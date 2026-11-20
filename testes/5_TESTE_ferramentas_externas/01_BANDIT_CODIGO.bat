@echo off
rem Bandit: analise estatica do cofre_senhas.py. Fica em testes\5_TESTE_ferramentas_externas\ e entra sozinho na RAIZ do projeto.
rem Codigos de saida: 0 = nada encontrado | 1 = ha achados para revisar | 2 = cofre_senhas.py nao encontrado | 9 = Python/Bandit nao instalado (pulado)
rem Com a variavel COFRE_AUTO definida (bateria geral) nao mostra o relatorio na tela e nao pausa.
setlocal
cd /d "%~dp0..\.."
title Cofre - Bandit: analise estatica
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
if not exist "cofre_senhas.py" (
  echo ERRO: cofre_senhas.py nao encontrado na raiz do projeto.
  if not defined COFRE_AUTO pause
  exit /b 2
)
set "REL=testes\resultados"
if not exist "%REL%" mkdir "%REL%"
set "LOG=%REL%\bandit.txt"
call "%~dp0preparar_ambiente_offline.bat"
if errorlevel 1 (
  if not defined COFRE_AUTO pause
  exit /b 9
)
"%COFRE_PYTHON%" -m bandit --version >nul 2>&1
if errorlevel 1 (
  echo ERRO: Bandit nao foi instalado pelo wheelhouse local.
  if not defined COFRE_AUTO pause
  exit /b 9
)
echo Analisando cofre_senhas.py com Bandit...
echo Projeto: %CD% > "%LOG%"
echo Data: %DATE% %TIME% >> "%LOG%"
echo. >> "%LOG%"
"%COFRE_PYTHON%" -m bandit -r "cofre_senhas.py" -f txt >> "%LOG%" 2>&1
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
