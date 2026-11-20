@echo off
rem pefile: confere ASLR, DEP, High-Entropy ASLR e CFG do CofreSenhas.exe compilado.
rem Uso: 06_PEFILE_EXE.bat [caminho\CofreSenhas.exe]  (ou defina COFRE_EXE)
rem Codigos de saida: 0 = ASLR e DEP ok | 1 = falta protecao obrigatoria | 9 = exe ou pefile ausente (pulado)
setlocal
cd /d "%~dp0..\.."
title Cofre - pefile: protecoes do executavel
set "REL=testes\resultados"
if not exist "%REL%" mkdir "%REL%"
set "LOG=%REL%\pefile_exe.txt"
call "%~dp0_achar_exe.bat" "%~1"
if not defined COFRE_EXE (
  >"%LOG%" echo [PULADO] CofreSenhas.exe compilado ausente. Compile com o 1 - INSTALAR ou informe o caminho.
  if not defined COFRE_AUTO type "%LOG%"
  if not defined COFRE_AUTO pause
  exit /b 9
)
call "%~dp0..\5_TESTE_ferramentas_externas\preparar_ambiente_offline.bat"
if errorlevel 1 (
  if not defined COFRE_AUTO pause
  exit /b 9
)
echo Projeto: %CD% > "%LOG%"
echo Data: %DATE% %TIME% >> "%LOG%"
"%COFRE_PYTHON%" "%~dp0verificar_pe.py" "%COFRE_EXE%" >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
>> "%LOG%" echo Codigo de saida: %RC%
if not defined COFRE_AUTO type "%LOG%"
echo Relatorio salvo em: %LOG%
if not defined COFRE_AUTO pause
exit /b %RC%
