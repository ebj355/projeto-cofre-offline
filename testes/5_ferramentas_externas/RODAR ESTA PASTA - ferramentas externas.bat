@echo off
rem Bateria 5 (ferramentas externas) SEM menu e SEM pausas: Bandit, pip-audit e Nmap, um depois do outro.
rem E o que o rodar_todos_windows.bat chama. O pytest (03) fica so no menu, porque repete as baterias 1 e 2.
rem Ferramenta nao instalada = [PULADO] (nao conta como falha). Achados = [ALERTA] (precisam de revisao humana, nao contam como falha).
rem Resultado: testes\resultados\resultado_ferramentas_externas_windows.txt  (relatorios completos tambem em testes\resultados\)
chcp 65001 >nul
setlocal EnableExtensions
set "AQUI=%~dp0"
set "COFRE_AUTO=1"
cd /d "%AQUI%..\.."
set "RES=testes\resultados"
if not exist "%RES%" mkdir "%RES%"
set "SAIDA=%RES%\resultado_ferramentas_externas_windows.txt"
echo ===== Ferramentas externas: Bandit, pip-audit e Nmap ===== > "%SAIDA%"
echo Data: %DATE% %TIME% >> "%SAIDA%"
echo. >> "%SAIDA%"
call :rodar "Bandit - analise estatica" "01_BANDIT_CODIGO.bat" bandit.txt
call :rodar "pip-audit - bibliotecas" "02_PIP_AUDIT_DEPENDENCIAS.bat" pip_audit.txt
call :rodar "Nmap - portas locais" "04_NMAP_PORTAS_LOCAIS.bat" nmap_localhost.txt
echo. >> "%SAIDA%"
echo Relatorios completos: testes\resultados\ >> "%SAIDA%"
echo.
type "%SAIDA%"
echo.
echo Pressione uma tecla para fechar esta janela.
pause >nul
exit /b 0

:rodar
echo ... %~1
call "%AQUI%%~2" < nul
set "RC=%errorlevel%"
set "TXT=[ALERTA] %~1 - ha achados ou erro, codigo %RC%. Revise testes\resultados\%~3"
if "%RC%"=="0" set "TXT=[OK] %~1 - sem alertas. Detalhes em testes\resultados\%~3"
if "%RC%"=="9" set "TXT=[PULADO] %~1 - ferramenta nao instalada"
echo %TXT% >> "%SAIDA%"
exit /b 0
