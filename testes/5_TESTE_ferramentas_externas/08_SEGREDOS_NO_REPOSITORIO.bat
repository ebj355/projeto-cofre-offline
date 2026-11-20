@echo off
rem Procura cofre.dat, .key, .bak, .diag e segredos em texto (detect-secrets) antes de enviar ao GitHub.
rem Codigos de saida: 0 = limpo | 1 = achados ou auditoria incompleta
setlocal
cd /d "%~dp0..\.."
title Cofre - segredos no repositorio
set "REL=testes\resultados"
if not exist "%REL%" mkdir "%REL%"
set "LOG=%REL%\segredos_repositorio.txt"
call "%~dp0preparar_ambiente_offline.bat"
if errorlevel 1 (
  if not defined COFRE_AUTO pause
  exit /b 1
)
echo Projeto: %CD% > "%LOG%"
echo Data: %DATE% %TIME% >> "%LOG%"
"%COFRE_PYTHON%" "%~dp0verificar_segredos.py" "%CD%" >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
echo Codigo de saida: %RC%>> "%LOG%"
if not defined COFRE_AUTO type "%LOG%"
echo Relatorio salvo em: %LOG%
if not defined COFRE_AUTO pause
exit /b %RC%
