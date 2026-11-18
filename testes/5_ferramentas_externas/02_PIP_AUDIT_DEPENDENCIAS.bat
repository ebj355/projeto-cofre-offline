@echo off
rem pip-audit: confere as bibliotecas do requirements.txt contra vulnerabilidades conhecidas (precisa de internet).
rem Codigos de saida: 0 = nada encontrado | 1 = ha achados ou falha de rede | 2 = requirements.txt nao encontrado | 9 = Python/pip-audit nao instalado (pulado)
rem Com a variavel COFRE_AUTO definida (bateria geral) nao mostra o relatorio na tela e nao pausa.
setlocal
cd /d "%~dp0..\.."
title Cofre - pip-audit: bibliotecas
if not exist "requirements.txt" (
  echo ERRO: requirements.txt nao encontrado na raiz do projeto.
  if not defined COFRE_AUTO pause
  exit /b 2
)
set "REL=testes\resultados\ferramentas_externas"
if not exist "%REL%" mkdir "%REL%"
set "LOG=%REL%\pip_audit.txt"
set "PY=py -3.13"
%PY% --version >nul 2>&1
if errorlevel 1 set "PY=py -3.12"
%PY% --version >nul 2>&1
if errorlevel 1 (
  echo AVISO: nao encontrei Python 3.13 nem 3.12 pelo inicializador py.
  if not defined COFRE_AUTO pause
  exit /b 9
)
%PY% -m pip_audit --version >nul 2>&1
if errorlevel 1 (
  echo AVISO: pip-audit nao esta instalado. Para instalar: %PY% -m pip install pip-audit
  if not defined COFRE_AUTO pause
  exit /b 9
)
echo Auditando as dependencias declaradas em requirements.txt...
echo Projeto: %CD% > "%LOG%"
echo Data: %DATE% %TIME% >> "%LOG%"
echo. >> "%LOG%"
%PY% -m pip_audit -r "requirements.txt" >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
echo.>> "%LOG%"
echo Codigo de saida: %RC%>> "%LOG%"
if not defined COFRE_AUTO type "%LOG%"
echo.
echo Relatorio salvo em: %LOG%
echo Codigo de saida: %RC%  - 0 = nada encontrado, 1 = ha achados (ou sem internet)
echo Nota: pip-audit consulta avisos conhecidos; isso nao prova ausencia de falhas.
if not defined COFRE_AUTO pause
exit /b %RC%
