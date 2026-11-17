@echo off
rem Roda as CINCO baterias de teste do Windows real, uma depois da outra, sem parar entre elas, chamando o .bat
rem de CADA UMA (nucleo, instalador, nativo, interface, pentest). Cada bateria grava o seu PROPRIO resultado,
rem exatamente como se tivesse sido chamada sozinha - nada aqui muda o comportamento dela.
rem
rem Uso: rodar_todos_windows.bat          (nativo testa so o disco do sistema)
rem      rodar_todos_windows.bat H        (nativo testa tambem o pendrive H: - repassado ao teste nativo)
rem
rem Importante (por que todo "call" abaixo tem "< nul" no final):
rem  - cada ...\teste_*.bat termina com um "pause" (espera uma tecla) para quem roda ele sozinho (clicando duas
rem    vezes). Encadeado aqui, sem jeito de apertar nenhuma tecla, o "pause" ia travar o .bat para sempre - o
rem    "< nul" da a ele uma entrada vazia, que o "pause" aceita como se fosse um "Enter" e segue na hora.
rem  - cada .bat chamado muda a pasta atual do processo (faz "cd" para a propria pasta) - por isso ha um
rem    "cd /d %~dp0" antes de cada etapa, voltando para a pasta deste arquivo (testes\ferramentas_dos_testes\).
rem  - este arquivo fica em testes\ferramentas_dos_testes\ (junto com rodar_todos.py, test_pytest.py etc. - o que so ORGANIZA os
rem    testes, sem ser um teste em si), um nivel ABAIXO de nucleo\, windows\ e gui\ - por isso todo caminho abaixo
rem    tem um "..\" a mais do que teria se este .bat estivesse solto direto em testes\.
rem  - cada teste_*_windows.bat e chamado com o CAMINHO COMPLETO (%~dp0..\1_motor_do_cofre\..., %~dp0..\4_so_no_windows\...), nunca
rem    so "..\1_motor_do_cofre\..." ou "..\4_so_no_windows\...": cada um desses .bat tambem faz "cd /d %%~dp0" logo no inicio, e o
rem    %%~dp0 DELE e calculado de novo a cada uso depois de qualquer "cd" quando foi chamado com caminho RELATIVO -
rem    dai ele somava a propria pasta duas vezes (ex.: testes\4_so_no_windows\windows\...) e nem achava o proprio
rem    python.exe. Com caminho completo isso nao acontece.
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
rem Roda a bateria 3 vezes seguidas (RODADAS). BATERIA NOVA SUBSTITUI A ANTIGA: apaga os resultados/logs/resumos da rodada anterior (testes\resultados) antes de comecar,
rem para nunca misturar arquivos de "ontem" com os de "hoje". Documentos que estavam ali por engano vao para a pasta certa.
rem O log de depuracao (testes\resultados\log_depuracao.txt) e recriado do zero; cada executor acrescenta nele a saida completa de cada teste.
if not exist "%~dp0..\resultados" mkdir "%~dp0..\resultados"
set "DRIVE=%~1"
py -3.13 "%~dp0limpar_resultados.py" 2>nul
set "FALHAS=0"
set "RODADAS=3"
for /L %%R in (1,1,%RODADAS%) do (
  echo.
  echo ######## RODADA %%R de %RODADAS% ########
  call :rodada %%R
)
goto :fim

:rodada
echo ============================================================
echo  Cofre de Senhas - bateria COMPLETA no Windows real
echo  1/5 nucleo                2/5 instalador (SO/atributos do instalador)
echo  3/5 nativo (atributos/ACL/DPAPI)   4/5 interface (automatico)
echo  5/5 pentest (injecao, forca bruta, DoS, vazamento de memoria, etc.)
echo  Sao 3 RODADAS seguidas: pode levar 1 hora e meia ou mais. Precisa de internet.
echo ============================================================
echo.

echo [1/5] nucleo (testes\1_motor_do_cofre\RODAR ESTA PASTA - testes do motor do cofre.bat) ...
cd /d "%~dp0"
call "%~dp0..\1_motor_do_cofre\RODAR ESTA PASTA - testes do motor do cofre.bat" < nul
if errorlevel 1 set /a FALHAS+=1
echo.

echo [2/5] instalador (testes\4_so_no_windows\A - testar o instalador.bat) ...
cd /d "%~dp0"
call "%~dp0..\4_so_no_windows\A - testar o instalador.bat" < nul
if errorlevel 1 set /a FALHAS+=1
echo.

echo [3/5] nativo: atributos/ACL/DPAPI (testes\4_so_no_windows\B - testar atributos e permissoes do Windows.bat %1) ...
cd /d "%~dp0"
call "%~dp0..\4_so_no_windows\B - testar atributos e permissoes do Windows.bat" %DRIVE% < nul
if errorlevel 1 set /a FALHAS+=1
echo.

echo [4/5] interface (testes\2_telas_e_botoes\RODAR ESTA PASTA - testes das telas e botoes.bat) ...
cd /d "%~dp0"
call "%~dp0..\2_telas_e_botoes\RODAR ESTA PASTA - testes das telas e botoes.bat" < nul
if errorlevel 1 set /a FALHAS+=1
echo.

echo [5/5] pentest (testes\3_ataques_simulados\RODAR ESTA PASTA - testes de ataque simulado.bat) ...
cd /d "%~dp0"
call "%~dp0..\3_ataques_simulados\RODAR ESTA PASTA - testes de ataque simulado.bat" < nul
if errorlevel 1 set /a FALHAS+=1
echo.

rem relatorios finais: resumo legivel (.md), em JSON, em SARIF e a limpeza de sobras dos testes em %TEMP%.
rem Sao uma conveniencia: se falharem, nada muda no resultado das baterias.
py -3.13 "%~dp0consolidar_resultados.py" >nul 2>nul
py -3.13 "%~dp0limpar_artefatos_testes.py" >nul 2>nul

cd /d "%~dp0"
rem junta os 5 resultados (que cada teste grava em testes\resultados\) num arquivo SO, tambem em testes\resultados\ -
rem assim so precisa entrar numa pasta so (resultados\) para ver tudo, inclusive o resumo junto.
if not exist "%~dp0..\resultados" mkdir "%~dp0..\resultados"
if "%DRIVE%"=="" (set "NATIVO_ARQ=%~dp0..\resultados\resultado_nativo_windows.txt") else (set "NATIVO_ARQ=%~dp0..\resultados\resultado_nativo_windows_%DRIVE%.txt")
set "TUDO=%~dp0..\resultados\resultado_rodar_todos_windows.txt"
echo ====== 1/5 nucleo (RODAR ESTA PASTA - testes do motor do cofre.bat) ====== > "%TUDO%"
type "%~dp0..\resultados\resultado_nucleo_windows.txt" >> "%TUDO%" 2>nul
echo. >> "%TUDO%"
echo ====== 2/5 instalador (A - testar o instalador.bat) ====== >> "%TUDO%"
type "%~dp0..\resultados\resultado_teste_windows.txt" >> "%TUDO%" 2>nul
echo. >> "%TUDO%"
echo ====== 3/5 nativo: atributos/ACL/DPAPI (B - testar atributos e permissoes do Windows.bat) ====== >> "%TUDO%"
type "%NATIVO_ARQ%" >> "%TUDO%" 2>nul
echo. >> "%TUDO%"
echo ====== 4/5 interface (RODAR ESTA PASTA - testes das telas e botoes.bat) ====== >> "%TUDO%"
type "%~dp0..\resultados\resultado_teste_gui_windows.txt" >> "%TUDO%" 2>nul
echo. >> "%TUDO%"
echo ====== 5/5 pentest (RODAR ESTA PASTA - testes de ataque simulado.bat) ====== >> "%TUDO%"
type "%~dp0..\resultados\resultado_pentest_windows.txt" >> "%TUDO%" 2>nul
rem guarda os arquivos desta rodada em testes\resultados\rodada_N (a proxima rodada sobrescreve os de cima)
if not exist "%~dp0..\resultados\rodada_%~1" mkdir "%~dp0..\resultados\rodada_%~1"
copy /y "%~dp0..\resultados\*.txt" "%~dp0..\resultados\rodada_%~1\" >nul 2>nul
copy /y "%~dp0..\resultados\*.json" "%~dp0..\resultados\rodada_%~1\" >nul 2>nul
copy /y "%~dp0..\resultados\*.md" "%~dp0..\resultados\rodada_%~1\" >nul 2>nul
exit /b 0

:fim
echo ============================================================
echo  3 rodadas concluidas. Cada rodada fica guardada em testes\resultados\rodada_1, rodada_2 e rodada_3.
if "%FALHAS%"=="0" (
  echo  TUDO PASSOU nas 5 baterias, nas 3 rodadas.
) else (
  echo  Pelo menos uma etapa terminou com erro: confira o resultado abaixo mesmo assim (o numero acima
  echo  nem sempre e exato - o que vale e o conteudo do arquivo).
)
echo.
echo  Resultado da ultima rodada (as 5 baterias juntas): testes\resultados\resultado_rodar_todos_windows.txt
echo  Resumo: resumo_testes.md  ^|  Log de depuracao completo: testes\resultados\log_depuracao.txt
echo ============================================================
echo Pressione uma tecla para fechar esta janela.
pause >nul
exit /b %FALHAS%
