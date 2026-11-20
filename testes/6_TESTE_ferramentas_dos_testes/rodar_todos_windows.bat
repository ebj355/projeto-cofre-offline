@echo off
rem Roda as SEIS baterias obrigatorias de teste do Windows real, UMA VEZ cada, uma depois da outra, chamando o .bat
rem de CADA UMA (nucleo, instalador, nativo, interface, pentest, ferramentas externas). Cada bateria grava o seu PROPRIO resultado,
rem exatamente como se tivesse sido chamada sozinha - nada aqui muda o comportamento dela.
rem
rem Uso: rodar_todos_windows.bat                 (nativo testa o disco do sistema; pip-audit consulta a internet)
rem      rodar_todos_windows.bat H               (nativo testa tambem o pendrive H:)
rem      rodar_todos_windows.bat OFFLINE         (pula consultas online do pip-audit)
rem      rodar_todos_windows.bat H OFFLINE       (pendrive H: e sem consultas online)
rem      rodar_todos_windows.bat POS-COMPILACAO  (inclui a pasta 7; compile o executavel primeiro)
rem      rodar_todos_windows.bat H OFFLINE POS-COMPILACAO
rem
rem Importante (por que todo "call" abaixo tem "< nul" no final):
rem  - cada ...\teste_*.bat termina com um "pause" (espera uma tecla) para quem roda ele sozinho (clicando duas
rem    vezes). Encadeado aqui, sem jeito de apertar nenhuma tecla, o "pause" ia travar o .bat para sempre - o
rem    "< nul" da a ele uma entrada vazia, que o "pause" aceita como se fosse um "Enter" e segue na hora.
rem  - cada .bat chamado muda a pasta atual do processo (faz "cd" para a propria pasta) - por isso ha um
rem    "cd /d %~dp0" antes de cada etapa, voltando para a pasta deste arquivo (testes\6_TESTE_ferramentas_dos_testes\).
rem  - este arquivo fica em testes\6_TESTE_ferramentas_dos_testes\ (junto com rodar_todos.py, test_pytest.py etc. - o que so ORGANIZA os
rem    testes, sem ser um teste em si), um nivel ABAIXO de nucleo\, windows\ e gui\ - por isso todo caminho abaixo
rem    tem um "..\" a mais do que teria se este .bat estivesse solto direto em testes\.
rem  - cada teste_*_windows.bat e chamado com o CAMINHO COMPLETO (%~dp0..\1_TESTE_motor_do_cofre\..., %~dp0..\4_TESTE_so_no_windows\...), nunca
rem    so "..\1_TESTE_motor_do_cofre\..." ou "..\4_TESTE_so_no_windows\...": cada um desses .bat tambem faz "cd /d %%~dp0" logo no inicio, e o
rem    %%~dp0 DELE e calculado de novo a cada uso depois de qualquer "cd" quando foi chamado com caminho RELATIVO -
rem    dai ele somava a propria pasta duas vezes (ex.: testes\4_TESTE_so_no_windows\windows\...) e nem achava o proprio
rem    python.exe. Com caminho completo isso nao acontece.
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
for %%I in ("%~dp0..\CACHE\_cache_bateria_%RANDOM%_%RANDOM%") do set "COFRE_TEST_CACHE_DIR=%%~fI"
if exist "%COFRE_TEST_CACHE_DIR%" (
  echo ERRO: o caminho de cache temporario ja existe; nao vou apagar conteudo preexistente.
  exit /b 1
)
mkdir "%COFRE_TEST_CACHE_DIR%" >nul 2>nul
if not exist "%COFRE_TEST_CACHE_DIR%" (
  echo ERRO: nao consegui criar o cache temporario dentro de testes\.
  exit /b 1
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
rem Roda a bateria UMA vez (RODADAS=1). BATERIA NOVA SUBSTITUI A ANTIGA: apaga os resultados/logs/resumos da rodada anterior (testes\resultados) antes de comecar,
rem para nunca misturar arquivos de "ontem" com os de "hoje". Documentos que estavam ali por engano vao para a pasta certa.
rem O log de depuracao (testes\resultados\log_depuracao.txt) e recriado do zero; cada executor acrescenta nele a saida completa de cada teste.
if not exist "%~dp0..\resultados" mkdir "%~dp0..\resultados"
set "DRIVE="
set "AUDIT_MODO="
set "RODAR_POS_COMPILACAO=0"
if not "%~1"=="" for %%A in (%*) do call :argumento %%~A
set "COFRE_ONLINE_AUDIT="
set "COFRE_OFFLINE=1"
py -3.13 "%~dp0limpar_resultados.py" 2>nul
set "FALHAS=0"
set "RODADAS=1"
for /L %%R in (1,1,%RODADAS%) do (
  echo.
  call :rodada %%R
)
goto :fim

:rodada
echo ============================================================
echo  Cofre de Senhas - bateria COMPLETA no Windows real
echo  1/6 nucleo                2/6 instalador (SO/atributos do instalador)
echo  3/6 nativo (atributos/ACL/DPAPI)   4/6 interface (automatico)
echo  5/6 pentest (injecao, forca bruta, DoS, vazamento de memoria, etc.)
echo  6/6 ferramentas externas (Bandit, pip-audit, Nmap e ferramentas 05, 08-10, 12-13)
echo  Roda UMA vez cada bateria sem baixar dependencias.
echo  O pip-audit consulta dados atuais da internet na etapa 6; use OFFLINE para pular.
if "%RODAR_POS_COMPILACAO%"=="1" echo  IMPORTANTE: etapa 7 opcional; compile o executavel antes de incluir.
echo ============================================================
echo.

echo [1/6] nucleo (testes\1_TESTE_motor_do_cofre\RODAR ESTA PASTA - testes do motor do cofre.bat) ...
cd /d "%~dp0"
call "%~dp0..\1_TESTE_motor_do_cofre\RODAR ESTA PASTA - testes do motor do cofre.bat" < nul
if errorlevel 1 set /a FALHAS+=1
echo.

echo [2/6] instalador (testes\4_TESTE_so_no_windows\A - testar o instalador.bat) ...
cd /d "%~dp0"
call "%~dp0..\4_TESTE_so_no_windows\A - testar o instalador.bat" < nul
if errorlevel 1 set /a FALHAS+=1
echo.

echo [3/6] nativo: atributos/ACL/DPAPI (testes\4_TESTE_so_no_windows\B - testar atributos e permissoes do Windows.bat %DRIVE%) ...
cd /d "%~dp0"
call "%~dp0..\4_TESTE_so_no_windows\B - testar atributos e permissoes do Windows.bat" %DRIVE% < nul
if errorlevel 1 set /a FALHAS+=1
echo.

echo [4/6] interface (testes\2_TESTE_telas_e_botoes\RODAR ESTA PASTA - testes das telas e botoes.bat) ...
cd /d "%~dp0"
call "%~dp0..\2_TESTE_telas_e_botoes\RODAR ESTA PASTA - testes das telas e botoes.bat" < nul
if errorlevel 1 set /a FALHAS+=1
echo.

echo [5/6] pentest (testes\3_TESTE_ataques_simulados\RODAR ESTA PASTA - testes de ataque simulado.bat) ...
cd /d "%~dp0"
call "%~dp0..\3_TESTE_ataques_simulados\RODAR ESTA PASTA - testes de ataque simulado.bat" < nul
if errorlevel 1 set /a FALHAS+=1
echo.

echo [6/6] ferramentas externas (testes\5_TESTE_ferramentas_externas\RODAR ESTA PASTA - ferramentas externas.bat) ...
if /I "%AUDIT_MODO%"=="OFFLINE" (
  set "COFRE_ONLINE_AUDIT="
  echo  Modo OFFLINE: pip-audit sera registrado como PULADO.
) else (
  set "COFRE_ONLINE_AUDIT=1"
  echo  Consultando a base online atual do pip-audit.
)
cd /d "%~dp0"
call "%~dp0..\5_TESTE_ferramentas_externas\RODAR ESTA PASTA - ferramentas externas.bat" < nul
if errorlevel 1 set /a FALHAS+=1
echo.

if "%RODAR_POS_COMPILACAO%"=="1" (
  echo [7 opcional] verificacoes do executavel compilado (testes\7_TESTE_de_compilacao) ...
  echo IMPORTANTE: compile o CofreSenhas.exe antes. Sem ele, as verificacoes dependentes serao marcadas como PULADO.
  cd /d "%~dp0"
  set "COFRE_AUTO=1"
  call "%~dp0..\7_TESTE_de_compilacao\RODAR ESTA PASTA - testes de compilacao.bat" < nul
  if errorlevel 1 set /a FALHAS+=1
  echo.
)

rem relatorios finais: resumo legivel (.md), em JSON, em SARIF e a limpeza de sobras dos testes em %TEMP%.
rem Sao uma conveniencia: se falharem, nada muda no resultado das baterias.
py -3.13 "%~dp0consolidar_resultados.py" >nul 2>nul
py -3.13 "%~dp0limpar_artefatos_testes.py" >nul 2>nul

cd /d "%~dp0"
rem junta os resultados (que cada teste grava em testes\resultados\) num arquivo SO, tambem em testes\resultados\ -
rem assim so precisa entrar numa pasta so (resultados\) para ver tudo, inclusive o resumo junto.
if not exist "%~dp0..\resultados" mkdir "%~dp0..\resultados"
if "%DRIVE%"=="" (set "NATIVO_ARQ=%~dp0..\resultados\resultado_nativo_windows.txt") else (set "NATIVO_ARQ=%~dp0..\resultados\resultado_nativo_windows_%DRIVE%.txt")
set "TUDO=%~dp0..\resultados\resultado_rodar_todos_windows.txt"
echo ====== 1/6 nucleo (RODAR ESTA PASTA - testes do motor do cofre.bat) ====== > "%TUDO%"
type "%~dp0..\resultados\resultado_nucleo_windows.txt" >> "%TUDO%" 2>nul
echo. >> "%TUDO%"
echo ====== 2/6 instalador (A - testar o instalador.bat) ====== >> "%TUDO%"
type "%~dp0..\resultados\resultado_teste_windows.txt" >> "%TUDO%" 2>nul
echo. >> "%TUDO%"
echo ====== 3/6 nativo: atributos/ACL/DPAPI (B - testar atributos e permissoes do Windows.bat) ====== >> "%TUDO%"
type "%NATIVO_ARQ%" >> "%TUDO%" 2>nul
echo. >> "%TUDO%"
echo ====== 4/6 interface (RODAR ESTA PASTA - testes das telas e botoes.bat) ====== >> "%TUDO%"
type "%~dp0..\resultados\resultado_teste_gui_windows.txt" >> "%TUDO%" 2>nul
echo. >> "%TUDO%"
echo ====== 5/6 pentest (RODAR ESTA PASTA - testes de ataque simulado.bat) ====== >> "%TUDO%"
type "%~dp0..\resultados\resultado_pentest_windows.txt" >> "%TUDO%" 2>nul
echo. >> "%TUDO%"
echo ====== 6/6 ferramentas externas (RODAR ESTA PASTA - ferramentas externas.bat) ====== >> "%TUDO%"
type "%~dp0..\resultados\resultado_ferramentas_externas_windows.txt" >> "%TUDO%" 2>nul
if "%RODAR_POS_COMPILACAO%"=="1" (
  echo. >> "%TUDO%"
  echo ====== etapa 7 opcional: testes de compilacao ====== >> "%TUDO%"
  type "%~dp0..\resultados\resultado_cofre_compilado_windows.txt" >> "%TUDO%" 2>nul
) else (
  echo. >> "%TUDO%"
  echo ====== etapa 7 opcional: nao solicitada ====== >> "%TUDO%"
  echo [PULADO] Para executar, compile o CofreSenhas.exe e passe POS-COMPILACAO ao Testar Tudo. >> "%TUDO%"
)
exit /b 0

:fim
if exist "%COFRE_TEST_CACHE_DIR%" (
  rmdir /s /q "%COFRE_TEST_CACHE_DIR%" >nul 2>nul
  if exist "%COFRE_TEST_CACHE_DIR%" (
    echo ERRO: nao consegui remover o cache temporario %COFRE_TEST_CACHE_DIR%.
    set /a FALHAS+=1
  )
  rmdir "%~dp0..\CACHE" >nul 2>nul
)
echo ============================================================
echo  Rodada concluida. Todos os arquivos ficam diretamente em testes\resultados\.
if "%FALHAS%"=="0" (
  if "%RODAR_POS_COMPILACAO%"=="1" (echo  As 6 baterias obrigatorias e a etapa opcional 7 terminaram sem falhas.) else (echo  TUDO PASSOU nas 6 baterias obrigatorias; a etapa 7 e opcional.)
) else (
  echo  Pelo menos uma etapa terminou com erro: confira o resultado abaixo mesmo assim ^(o numero acima
  echo  nem sempre e exato - o que vale e o conteudo do arquivo^).
)
echo.
echo  Resultado (baterias e etapa 7 opcional): testes\resultados\resultado_rodar_todos_windows.txt
echo  Resumo: resumo_testes.md  ^|  Log de depuracao completo: testes\resultados\log_depuracao.txt
echo ============================================================
set "COFRE_OFFLINE="
echo Pressione uma tecla para fechar esta janela.
pause >nul
exit /b %FALHAS%

:argumento
if /I "%~1"=="OFFLINE" (
  set "AUDIT_MODO=OFFLINE"
  exit /b 0
)
if /I "%~1"=="POS-COMPILACAO" (
  set "RODAR_POS_COMPILACAO=1"
  exit /b 0
)
if not defined DRIVE set "DRIVE=%~1"
exit /b 0
