@rem ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
@echo off
rem Roda verificacoes que dependem do CofreSenhas.exe compilado.
rem COFRE_EXE pode apontar para o executavel; sem ele, as verificacoes dependentes serao marcadas como puladas.
setlocal EnableExtensions
chcp 65001 >nul
rem Procura o .exe (e pergunta onde esta, se nao achar) AGORA, na janela visivel: a execucao seguinte roda
rem minimizada e herda COFRE_EXE. Chamado pelo Testar Tudo (COFRE_AUTO definido), nunca pergunta.
if defined COFRE_TEST_MINIMIZADO goto :ja_minimizado
cd /d "%~dp0..\.."
call "%~dp0_achar_exe.bat" "%~1"
:ja_minimizado
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
if defined COFRE_PULAR_EXE goto :pulado_usuario

call :rodar "Protecoes PE (pefile)" "06_PEFILE_EXE.bat" "pefile_exe.txt" "%~1"
call :rodar "Windows Defender" "07_DEFENDER_EXE.bat" "defender_exe.txt" "%~1"
call :rodar "Conexoes de rede do processo" "11_REDE_DO_PROCESSO.bat" "rede_processo.txt" "%~1"

set "SMOKE_LOG=testes\resultados\resultado_smoke_exe_visual.txt"
if not defined COFRE_EXE goto :smoke_sem_exe
py -3.13 -X utf8 "%AQUI%teste_exe_visual_smoke_windows.py" "%COFRE_EXE%" > "%SMOKE_LOG%" 2>&1
set "SMOKE_RC=%ERRORLEVEL%"
goto :smoke_fim
:smoke_sem_exe
>"%SMOKE_LOG%" echo [PULADO] CofreSenhas.exe nao encontrado; o smoke visual nao foi executado.
set "SMOKE_RC=9"
:smoke_fim
set "SMOKE_ESTADO=FALHOU"
if "%SMOKE_RC%"=="0" set "SMOKE_ESTADO=OK"
if "%SMOKE_RC%"=="9" set "SMOKE_ESTADO=PULADO"
if not "%SMOKE_RC%"=="0" if not "%SMOKE_RC%"=="9" set /a FALHAS+=1
>>"%LOG%" echo [%SMOKE_ESTADO%] Smoke visual do EXE - codigo %SMOKE_RC%; detalhes em %SMOKE_LOG%
type "%SMOKE_LOG%"

echo.>> "%LOG%"
echo Relatorios individuais: testes\resultados\>> "%LOG%"
call :consolidar
echo.
type "%LOG%"
echo.
if "%FALHAS%"=="0" (
  echo Nenhuma verificacao falhou. Confira os itens [PULADO] e os relatorios individuais.
) else (
  echo FALHOU: uma ou mais verificacoes do executavel. Confira os relatorios individuais.
)
echo Relatorio: %LOG%
echo Resultado completo (tudo junto): %COMPLETO%
if not defined COFRE_AUTO_ANTES pause
exit /b %FALHAS%

:pulado_usuario
rem Voce escolheu NAO testar o .exe no inicio do Testar Tudo: registra e termina sem rodar nada.
>>"%LOG%" echo [PULADO] Protecoes PE (pefile) - escolha do usuario no inicio do Testar Tudo
>>"%LOG%" echo [PULADO] Windows Defender - escolha do usuario no inicio do Testar Tudo
>>"%LOG%" echo [PULADO] Conexoes de rede do processo - escolha do usuario no inicio do Testar Tudo
>>"%LOG%" echo [PULADO] Smoke visual do EXE - escolha do usuario no inicio do Testar Tudo
echo.>> "%LOG%"
echo Relatorios individuais: testes\resultados\>> "%LOG%"
call :consolidar
type "%LOG%"
if not defined COFRE_AUTO_ANTES pause
exit /b 0

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

:consolidar
rem Junta o resumo e os 4 relatorios individuais num arquivo so, igual ao RESULTADO COMPLETO.txt dos outros testes.
rem Os arquivos individuais continuam separados em testes\resultados\.
set "PASTA_COMPLETOS=testes\resultados\resultados completos"
if not exist "%PASTA_COMPLETOS%" mkdir "%PASTA_COMPLETOS%"
set "COMPLETO=%PASTA_COMPLETOS%\RESULTADO COMPLETO DE COMPILACAO.txt"
set "NOK=0"
set "NPUL=0"
set "NFAL=0"
for /f %%N in ('findstr /b /c:"[OK]" "%LOG%" ^| find /c /v ""') do set "NOK=%%N"
for /f %%N in ('findstr /b /c:"[PULADO]" "%LOG%" ^| find /c /v ""') do set "NPUL=%%N"
for /f %%N in ('findstr /b /c:"[FALHOU]" "%LOG%" ^| find /c /v ""') do set "NFAL=%%N"
>"%COMPLETO%" echo RESULTADO COMPLETO DE COMPILACAO - Cofre de Senhas
>>"%COMPLETO%" echo Gerado em: %DATE% %TIME%
>>"%COMPLETO%" echo Executavel: %COFRE_EXE%
>>"%COMPLETO%" echo Verificacoes [OK]: %NOK%; puladas: %NPUL%; com falha: %NFAL%
>>"%COMPLETO%" echo Este arquivo reune os relatorios individuais desta rodada; cada arquivo original continua separado.
set "NARQ=0"
call :anexar "resultado_cofre_compilado_windows.txt"
call :anexar "pefile_exe.txt"
call :anexar "defender_exe.txt"
call :anexar "rede_processo.txt"
call :anexar "resultado_smoke_exe_visual.txt"
exit /b 0

:anexar
set /a NARQ+=1
>>"%COMPLETO%" echo.
>>"%COMPLETO%" echo ==============================================================================
>>"%COMPLETO%" echo ARQUIVO %NARQ%/5: %~1
>>"%COMPLETO%" echo ------------------------------------------------------------------------------
if exist "testes\resultados\%~1" (type "testes\resultados\%~1" >> "%COMPLETO%") else (>>"%COMPLETO%" echo [arquivo nao gerado nesta rodada])
exit /b 0
