@echo off
rem Confere o .gitignore com arquivos de teste reais e a coerencia dos pins/hashes do build.
rem Codigos: 0 = consistente | 1 = falha ou auditoria incompleta
setlocal
cd /d "%~dp0..\.."
set "REL=testes\resultados"
if not exist "%REL%" mkdir "%REL%"
set "LOG=%REL%\integridade_repositorio.txt"
call "%~dp0preparar_ambiente_offline.bat"
if errorlevel 1 (
  if not defined COFRE_AUTO pause
  exit /b 1
)
echo Projeto: %CD% > "%LOG%"
echo Data: %DATE% %TIME% >> "%LOG%"
"%COFRE_PYTHON%" "%~dp0verificar_integridade_repositorio.py" >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
echo Codigo de saida: %RC%>> "%LOG%"
if not defined COFRE_AUTO type "%LOG%"
echo Relatorio salvo em: %LOG%
if not defined COFRE_AUTO pause
exit /b %RC%
