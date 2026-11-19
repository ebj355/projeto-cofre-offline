@echo off
rem Bateria 5 (ferramentas externas) SEM menu e SEM pausas: todas as ferramentas automaticas (01, 02, 04 a 12), uma depois da outra.
rem E o que o rodar_todos_windows.bat chama. O pytest (03) fica so no menu, porque repete as baterias 1 e 2.
rem Ferramenta nao instalada = [PULADO]. Achados = [ALERTA] (revisao humana). Falha real do teste Hypothesis reprova esta bateria.
rem Resultado: testes\resultados\resultado_ferramentas_externas_windows.txt  (relatorios completos tambem em testes\resultados\)
chcp 65001 >nul
setlocal EnableExtensions
set "AQUI=%~dp0"
set "COFRE_AUTO=1"
set "FALHAS_TESTES=0"
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
call :rodar "pefile - protecoes do exe" "06_PEFILE_EXE.bat" pefile_exe.txt
call :rodar "Defender - varredura do exe" "07_DEFENDER_EXE.bat" defender_exe.txt
call :rodar "Segredos no repositorio" "08_SEGREDOS_NO_REPOSITORIO.bat" segredos_repositorio.txt
call :rodar "Qualidade extra - Ruff, mypy, Radon, Vulture" "09_QUALIDADE_EXTRA.bat" qualidade_extra.txt
call :rodar "pip-audit dos testes e SBOM" "10_PIP_AUDIT_TESTE_E_SBOM.bat" pip_audit_testes_sbom.txt
call :rodar "Rede do processo" "11_REDE_DO_PROCESSO.bat" rede_processo.txt
call :rodar "Hypothesis - propriedades" "12_HYPOTHESIS_PROPRIEDADES.bat" hypothesis.txt teste
echo. >> "%SAIDA%"
echo Relatorios completos: testes\resultados\ >> "%SAIDA%"
echo.
type "%SAIDA%"
echo.
if "%FALHAS_TESTES%"=="0" (
  echo Nenhum teste automatizado desta pasta falhou; confira [PULADO] e [ALERTA] nos relatorios.
) else (
  echo FALHOU: o teste Hypothesis reportou erro. Confira testes\resultados\hypothesis.txt.
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
if "%RC%"=="9" set "TXT=[PULADO] %~1 - ferramenta, arquivo ou base ausente"
if /i "%~4"=="teste" if not "%RC%"=="0" if not "%RC%"=="9" (
  set "TXT=[FALHOU] %~1 - codigo %RC%. Revise testes\resultados\%~3"
  set /a FALHAS_TESTES+=1
)
echo %TXT% >> "%SAIDA%"
exit /b 0
