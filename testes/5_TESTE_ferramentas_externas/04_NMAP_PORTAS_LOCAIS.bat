@echo off
rem Nmap: lista as 100 portas TCP mais comuns SOMENTE em 127.0.0.1 (este proprio computador).
rem Codigos de saida: 0 = concluido | outro = erro do Nmap | 9 = Nmap nao instalado (pulado)
rem Com a variavel COFRE_AUTO definida (bateria geral) nao mostra o relatorio na tela e nao pausa.
setlocal
cd /d "%~dp0..\.."
title Cofre - Nmap: portas locais
set "NMAP="
for /f "delims=" %%N in ('where nmap.exe 2^>nul') do if not defined NMAP set "NMAP=%%N"
if not defined NMAP if exist "%ProgramFiles%\Nmap\nmap.exe" set "NMAP=%ProgramFiles%\Nmap\nmap.exe"
if not defined NMAP if exist "%ProgramFiles(x86)%\Nmap\nmap.exe" set "NMAP=%ProgramFiles(x86)%\Nmap\nmap.exe"
if not defined NMAP (
  echo AVISO: Nmap nao esta instalado. Use pacotes\nmap-7.993-setup.exe sem internet; o instalador pode exigir permissao.
  if not defined COFRE_AUTO pause
  exit /b 9
)
set "REL=testes\resultados"
if not exist "%REL%" mkdir "%REL%"
set "LOG=%REL%\nmap_localhost.txt"
echo Verificando apenas o proprio computador: 127.0.0.1
echo Nenhum outro computador ou rede sera escaneado.
echo Projeto: %CD% > "%LOG%"
echo Data: %DATE% %TIME% >> "%LOG%"
echo Alvo: 127.0.0.1 >> "%LOG%"
echo. >> "%LOG%"
"%NMAP%" -sT -sV --top-ports 100 127.0.0.1 >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
echo.>> "%LOG%"
echo Codigo de saida: %RC%>> "%LOG%"
if not defined COFRE_AUTO type "%LOG%"
echo.
echo Relatorio salvo em: %LOG%
echo IMPORTANTE: Nmap verifica servicos de rede do Windows, nao analisa o codigo Python.
if not defined COFRE_AUTO pause
exit /b %RC%
