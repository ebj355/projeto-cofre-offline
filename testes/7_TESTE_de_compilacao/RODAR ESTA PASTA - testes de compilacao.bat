@rem ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
@echo off
rem Roda verificacoes que dependem do CofreSenhas.exe compilado.
rem COFRE_EXE pode apontar para o executavel; sem ele, as verificacoes dependentes serao marcadas como puladas.
setlocal EnableExtensions
chcp 65001 >nul
if not defined COFRE_TEST_MINIMIZADO (
  set "COFRE_TEST_MINIMIZADO=1"
  start "" /min cmd.exe /d /c ""%~f0" %*"
  exit /b
)
set "AQUI=%~dp0"
cd /d "%AQUI%..\.."
set "COFRE_AUTO_ANTES=%COFRE_AUTO%"
set "COFRE_AUTO=1"
call "%AQUI%_achar_exe.bat" "%~1"
if not exist "testes\resultados" mkdir "testes\resultados"
set "LOG=testes\resultados\resultado_cofre_compilado_windows.txt"
set "FALHAS=0"
>"%LOG%" echo ===== Testes de compilacao: verificacoes do executavel compilado =====
echo Data: %DATE% %TIME%>> "%LOG%"
echo Executavel: %COFRE_EXE%>> "%LOG%"
echo.>> "%LOG%"

call :rodar "Protecoes PE (pefile)" "06_PEFILE_EXE.bat" "pefile_exe.txt" "%~1"
call :rodar "Windows Defender" "07_DEFENDER_EXE.bat" "defender_exe.txt" "%~1"
call :rodar "Conexoes de rede do processo" "11_REDE_DO_PROCESSO.bat" "rede_processo.txt" "%~1"

set "SMOKE_LOG=testes\resultados\resultado_smoke_exe_visual.txt"
py -3.13 -X utf8 "%AQUI%teste_exe_visual_smoke_windows.py" "%COFRE_EXE%" > "%SMOKE_LOG%" 2>&1
set "SMOKE_RC=%ERRORLEVEL%"
set "SMOKE_ESTADO=FALHOU"
if "%SMOKE_RC%"=="0" set "SMOKE_ESTADO=OK"
if "%SMOKE_RC%"=="9" set "SMOKE_ESTADO=PULADO"
if not "%SMOKE_RC%"=="0" if not "%SMOKE_RC%"=="9" set /a FALHAS+=1
>>"%LOG%" echo [%SMOKE_ESTADO%] Smoke visual do EXE - codigo %SMOKE_RC%; detalhes em %SMOKE_LOG%
type "%SMOKE_LOG%"

echo.>> "%LOG%"
echo Relatorios individuais: testes\resultados\>> "%LOG%"
echo.
type "%LOG%"
echo.
if "%FALHAS%"=="0" (
  echo Nenhuma verificacao falhou. Confira os itens [PULADO] e os relatorios individuais.
) else (
  echo FALHOU: uma ou mais verificacoes do executavel. Confira os relatorios individuais.
)
echo Relatorio: %LOG%
if not defined COFRE_AUTO_ANTES pause
exit /b %FALHAS%

:rodar
echo ... %~1
set "COFRE_AUTO=1"
call "%AQUI%%~2" "%~4" < nul
set "RC=%ERRORLEVEL%"
set "ESTADO=FALHOU"
if "%RC%"=="0" set "ESTADO=OK"
if "%RC%"=="9" set "ESTADO=PULADO"
>> "%LOG%" echo [%ESTADO%] %~1 - codigo %RC%; detalhes em testes\resultados\%~3
if not "%RC%"=="0" if not "%RC%"=="9" set /a FALHAS+=1
exit /b 0
