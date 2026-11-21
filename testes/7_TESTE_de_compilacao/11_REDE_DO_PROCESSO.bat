@rem ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
@echo off
rem Inicia uma instancia de teste temporaria do CofreSenhas.exe, confere TCP/UDP e fecha so o PID criado.
rem Codigos de saida: 0 = nenhuma conexao | 1 = processo/rede inesperados | 9 = exe ou execucao indisponivel (pulado)
setlocal
cd /d "%~dp0..\.."
title Cofre - rede do processo
set "REL=testes\resultados"
if not exist "%REL%" mkdir "%REL%"
set "LOG=%REL%\rede_processo.txt"
echo Projeto: %CD% > "%LOG%"
echo Data: %DATE% %TIME% >> "%LOG%"
call "%~dp0_achar_exe.bat" "%~1"
if not defined COFRE_EXE (
  >> "%LOG%" echo [PULADO] CofreSenhas.exe ausente; informe o caminho ou defina COFRE_EXE.
  set "RC=9"
  goto :fim
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0testar_rede_processo.ps1" -Executavel "%COFRE_EXE%" >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
:fim
>> "%LOG%" echo Codigo de saida: %RC%
if not defined COFRE_AUTO type "%LOG%"
echo Relatorio salvo em: %LOG%
if not defined COFRE_AUTO pause
exit /b %RC%
