@echo off
rem Bateria 5 (ferramentas externas) SEM menu e SEM pausas: ferramentas automaticas (01, 02, 04, 05 e 08 a 10, 12 e 13).
rem E o que o rodar_todos_windows.bat chama. O pytest (03) fica so no menu, porque repete as baterias 1 e 2.
rem Ferramenta nao instalada = [PULADO]. Achados = [ALERTA] (revisao humana). Hypothesis, segredos e integridade reprovam a bateria em caso de falha.
rem Resultado: testes\resultados\resultado_ferramentas_externas_windows.txt  (relatorios completos tambem em testes\resultados\)
chcp 65001 >nul
setlocal EnableExtensions
set "AQUI=%~dp0"
set "COFRE_AUTO=1"
set "FALHAS_TESTES=0"
set "CACHE_PROPRIO="
if not defined COFRE_TEST_CACHE_DIR (
  for %%I in ("%~dp0..\CACHE\_cache_ferramentas_%RANDOM%_%RANDOM%") do set "COFRE_TEST_CACHE_DIR=%%~fI"
  set "CACHE_PROPRIO=1"
)
if defined CACHE_PROPRIO (
  if exist "%COFRE_TEST_CACHE_DIR%" (
    echo ERRO: o caminho de cache temporario ja existe; nao vou apagar conteudo preexistente.
    exit /b 1
  )
  mkdir "%COFRE_TEST_CACHE_DIR%" >nul 2>nul
  if not exist "%COFRE_TEST_CACHE_DIR%" (
    echo ERRO: nao consegui criar o cache temporario dentro de testes\.
    exit /b 1
  )
)
set "COFRE_TEST_HYPOTHESIS_DB=%COFRE_TEST_CACHE_DIR%\hypothesis"
set "HYPOTHESIS_STORAGE_DIRECTORY=%COFRE_TEST_CACHE_DIR%\hypothesis_storage"
set "COFRE_TEST_RUFF_CACHE=%COFRE_TEST_CACHE_DIR%\ruff"
set "RUFF_CACHE_DIR=%COFRE_TEST_RUFF_CACHE%"
set "COFRE_TEST_MYPY_CACHE=%COFRE_TEST_CACHE_DIR%\mypy"
set "COFRE_TEST_PYTEST_CACHE=%COFRE_TEST_CACHE_DIR%\pytest"
set "PYTHONPYCACHEPREFIX=%COFRE_TEST_CACHE_DIR%\pycache"
set "PYTHONDONTWRITEBYTECODE=1"
set "TEMP=%COFRE_TEST_CACHE_DIR%"
set "TMP=%COFRE_TEST_CACHE_DIR%"
set "TMPDIR=%COFRE_TEST_CACHE_DIR%"
cd /d "%AQUI%..\.."
set "RES=testes\resultados"
if not exist "%RES%" mkdir "%RES%"
set "SAIDA=%RES%\resultado_ferramentas_externas_windows.txt"
echo ===== Ferramentas externas: Bandit, pip-audit, Nmap e verificacoes novas ===== > "%SAIDA%"
echo Data: %DATE% %TIME% >> "%SAIDA%"
echo. >> "%SAIDA%"
call :rodar "Bandit - analise estatica" "01_BANDIT_CODIGO.bat" bandit.txt
call :rodar "pip-audit - bibliotecas" "02_PIP_AUDIT_DEPENDENCIAS.bat" pip_audit.txt
call :rodar "Nmap - portas locais" "04_NMAP_PORTAS_LOCAIS.bat" nmap_localhost.txt
call :rodar "PSScriptAnalyzer - scripts PowerShell" "05_PSSCRIPTANALYZER.bat" psscriptanalyzer.txt
call :rodar "Segredos no repositorio" "08_SEGREDOS_NO_REPOSITORIO.bat" segredos_repositorio.txt teste
call :rodar "Qualidade extra - Ruff, mypy, Radon, Vulture" "09_QUALIDADE_EXTRA.bat" qualidade_extra.txt
call :rodar "pip-audit dos testes e SBOM" "10_PIP_AUDIT_TESTE_E_SBOM.bat" pip_audit_testes_sbom.txt
call :rodar "Hypothesis - propriedades" "12_HYPOTHESIS_PROPRIEDADES.bat" hypothesis.txt teste
call :rodar "Integridade do repositorio" "13_INTEGRIDADE_REPOSITORIO.bat" integridade_repositorio.txt teste
echo. >> "%SAIDA%"
echo Relatorios completos: testes\resultados\ >> "%SAIDA%"
echo.
type "%SAIDA%"
echo.
if defined CACHE_PROPRIO if exist "%COFRE_TEST_CACHE_DIR%" (
  rmdir /s /q "%COFRE_TEST_CACHE_DIR%" >nul 2>nul
  if exist "%COFRE_TEST_CACHE_DIR%" (
    echo [ERRO] nao consegui remover o cache temporario %COFRE_TEST_CACHE_DIR%.>> "%SAIDA%"
    set /a FALHAS_TESTES+=1
  )
  rmdir "%~dp0..\CACHE" >nul 2>nul
)
if "%FALHAS_TESTES%"=="0" (
  echo Nenhum teste automatizado desta pasta falhou; confira [PULADO] e [ALERTA] nos relatorios.
) else (
  echo FALHOU: um ou mais testes automatizados desta pasta. Confira as linhas [FALHOU] em %SAIDA%.
)
echo Pressione uma tecla para fechar esta janela.
pause >nul
exit /b %FALHAS_TESTES%

:rodar
echo ... %~1
call "%AQUI%%~2" < nul
set "RC=%errorlevel%"
set "TXT=[ALERTA] %~1 - ha achados ou erro, codigo %RC%. Revise testes\resultados\%~3"
if "%RC%"=="0" set "TXT=[OK] %~1 - sem alertas. Detalhes em testes\resultados\%~3"
if "%RC%"=="9" set "TXT=[PULADO] %~1 - veja o pre-requisito registrado em testes\resultados\%~3"
if /i "%~4"=="teste" if not "%RC%"=="0" if not "%RC%"=="9" (
  set "TXT=[FALHOU] %~1 - codigo %RC%. Revise testes\resultados\%~3"
  set /a FALHAS_TESTES+=1
)
echo %TXT% >> "%SAIDA%"
exit /b 0
