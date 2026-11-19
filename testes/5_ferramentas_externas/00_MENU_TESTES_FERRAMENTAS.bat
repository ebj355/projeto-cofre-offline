@echo off
rem Menu para rodar cada ferramenta externa separadamente (dois cliques).
setlocal
set "AQUI=%~dp0"
cd /d "%AQUI%..\.."
title Cofre de Senhas - Ferramentas externas

:MENU
cls
echo ============================================================
echo   COFRE DE SENHAS - FERRAMENTAS EXTERNAS
echo ============================================================
echo Pasta do projeto: %CD%
echo.
echo 1 - Analise estatica do codigo (Bandit)
echo 2 - Auditoria das bibliotecas (pip-audit)
echo 3 - Testes automatizados do projeto (pytest - demorado, repete as baterias 1 e 2)
echo 4 - Verificar portas abertas SOMENTE neste computador (Nmap)
echo 5 - Executar todas as automaticas em sequencia (o que a bateria geral roda)
echo 6 - Scripts PowerShell (PSScriptAnalyzer)
echo 7 - Protecoes do CofreSenhas.exe (pefile)
echo 8 - Varredura do CofreSenhas.exe pelo Windows Defender
echo 9 - Segredos e arquivos proibidos no repositorio
echo A - Qualidade extra (Ruff, mypy, Radon, Vulture)
echo B - pip-audit dos testes e SBOM (precisa COFRE_ONLINE_AUDIT=1)
echo C - Conexoes de rede do cofre aberto
echo D - Testes por propriedades (Hypothesis)
echo 0 - Sair
echo.
choice /c 123456789ABCD0 /n /m "Escolha: "
if errorlevel 14 goto FIM
if errorlevel 13 goto RUN_D
if errorlevel 12 goto RUN_C
if errorlevel 11 goto RUN_B
if errorlevel 10 goto RUN_A
if errorlevel 9 goto RUN_9
if errorlevel 8 goto RUN_8
if errorlevel 7 goto RUN_7
if errorlevel 6 goto RUN_6
if errorlevel 5 goto BASICO
if errorlevel 4 goto RUN_NMAP
if errorlevel 3 goto RUN_PYTEST
if errorlevel 2 goto RUN_PIP
if errorlevel 1 goto RUN_BANDIT

:RUN_BANDIT
call "%AQUI%01_BANDIT_CODIGO.bat"
goto MENU
:RUN_PIP
call "%AQUI%02_PIP_AUDIT_DEPENDENCIAS.bat"
goto MENU
:RUN_PYTEST
call "%AQUI%03_PYTEST_PROJETO.bat"
goto MENU
:RUN_NMAP
call "%AQUI%04_NMAP_PORTAS_LOCAIS.bat"
goto MENU
:RUN_6
call "%AQUI%05_PSSCRIPTANALYZER.bat"
goto MENU
:RUN_7
call "%AQUI%06_PEFILE_EXE.bat"
goto MENU
:RUN_8
call "%AQUI%07_DEFENDER_EXE.bat"
goto MENU
:RUN_9
call "%AQUI%08_SEGREDOS_NO_REPOSITORIO.bat"
goto MENU
:RUN_A
call "%AQUI%09_QUALIDADE_EXTRA.bat"
goto MENU
:RUN_B
call "%AQUI%10_PIP_AUDIT_TESTE_E_SBOM.bat"
goto MENU
:RUN_C
call "%AQUI%11_REDE_DO_PROCESSO.bat"
goto MENU
:RUN_D
call "%AQUI%12_HYPOTHESIS_PROPRIEDADES.bat"
goto MENU

:BASICO
set "COFRE_AUTO=1"
for %%F in (01_BANDIT_CODIGO 02_PIP_AUDIT_DEPENDENCIAS 04_NMAP_PORTAS_LOCAIS 05_PSSCRIPTANALYZER 06_PEFILE_EXE 07_DEFENDER_EXE 08_SEGREDOS_NO_REPOSITORIO 09_QUALIDADE_EXTRA 10_PIP_AUDIT_TESTE_E_SBOM 11_REDE_DO_PROCESSO 12_HYPOTHESIS_PROPRIEDADES) do call "%AQUI%%%F.bat" < nul
set "COFRE_AUTO="
echo.
echo Concluido. Relatorios em testes\resultados\
pause
goto MENU

:FIM
echo.
echo Encerrado. Os relatorios ficam diretamente em testes\resultados\
endlocal
