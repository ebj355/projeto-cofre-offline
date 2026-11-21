@rem ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
@echo off
rem Windows Defender (MpCmdRun): varre SO o CofreSenhas.exe para ver se vira falso positivo. Nunca envie cofre.dat/.key a nenhum scanner.
rem Codigos de saida: 0 = limpo | 1 = ameaca ou erro na varredura | 9 = exe ou Defender indisponivel (pulado)
setlocal
cd /d "%~dp0..\.."
title Cofre - Windows Defender: varredura do exe
set "REL=testes\resultados"
if not exist "%REL%" mkdir "%REL%"
set "LOG=%REL%\defender_exe.txt"
call "%~dp0_achar_exe.bat" "%~1"
set "MP="
for /f "delims=" %%M in ('dir /b /s /o-n "%ProgramData%\Microsoft\Windows Defender\Platform\MpCmdRun.exe" 2^>nul') do if not defined MP set "MP=%%M"
if not defined MP if exist "%ProgramFiles%\Windows Defender\MpCmdRun.exe" set "MP=%ProgramFiles%\Windows Defender\MpCmdRun.exe"
if not defined COFRE_EXE (
  >"%LOG%" echo [PULADO] CofreSenhas.exe compilado ausente; a verificacao do Defender exige o executavel.
  if not defined COFRE_AUTO type "%LOG%"
  if not defined COFRE_AUTO pause
  exit /b 9
)
if not defined MP (
  >"%LOG%" echo [PULADO] MpCmdRun.exe nao encontrado - Defender ausente ou substituido por outro antivirus.
  if not defined COFRE_AUTO type "%LOG%"
  if not defined COFRE_AUTO pause
  exit /b 9
)
powershell.exe -NoProfile -Command "try { $s=Get-MpComputerStatus -ErrorAction Stop; if ($s.AMServiceEnabled -and $s.AntivirusEnabled) { exit 0 } else { exit 9 } } catch { exit 9 }" >nul 2>nul
if errorlevel 1 (
  >"%LOG%" echo [PULADO] Microsoft Defender instalado, mas desativado ou indisponivel; a varredura nao foi executada.
  if not defined COFRE_AUTO type "%LOG%"
  if not defined COFRE_AUTO pause
  exit /b 9
)
echo Projeto: %CD% > "%LOG%"
echo Data: %DATE% %TIME% >> "%LOG%"
echo Arquivo: %COFRE_EXE% >> "%LOG%"
"%MP%" -Scan -ScanType 3 -File "%COFRE_EXE%" -DisableRemediation >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
>> "%LOG%" echo Codigo de saida: %RC%
if not defined COFRE_AUTO type "%LOG%"
echo Relatorio salvo em: %LOG%
echo Nota: o Defender pode demorar para atualizar assinaturas; um resultado limpo vale para hoje e para esta versao dele.
if not defined COFRE_AUTO pause
if not "%RC%"=="0" exit /b 1
exit /b 0
