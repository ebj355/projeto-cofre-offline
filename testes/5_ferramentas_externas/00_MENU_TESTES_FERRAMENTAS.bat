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
echo 5 - Executar 1, 2 e 4 em sequencia (o que a bateria geral roda)
echo 0 - Sair
echo.
choice /c 123450 /n /m "Escolha: "
if errorlevel 6 goto FIM
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

:BASICO
call "%AQUI%01_BANDIT_CODIGO.bat"
call "%AQUI%02_PIP_AUDIT_DEPENDENCIAS.bat"
call "%AQUI%04_NMAP_PORTAS_LOCAIS.bat"
pause
goto MENU

:FIM
echo.
echo Encerrado. Os relatorios ficam em testes\resultados\ferramentas_externas\
endlocal
