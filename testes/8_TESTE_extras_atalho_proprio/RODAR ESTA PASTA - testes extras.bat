@rem ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
@echo off
rem Pasta 8: testes EXTRAS, com atalho PROPRIO. NAO fazem parte do "2 - TESTAR TUDO" (ele nao chama esta pasta).
rem   1) teste_gui_integridade_ao_entrar.py: a janela de integridade abre sozinha ao desbloquear (roda sempre).
rem   2) 14_COBERTURA_DO_CODIGO.py: quanto do cofre_senhas.py os testes do nucleo executam (LENTO; informativo).
rem A pasta pode ficar em qualquer lugar dentro do projeto: o atalho sobe ate achar o cofre_senhas.py.
rem Como a bateria oficial, cria um ambiente TEMPORARIO com as bibliotecas do lock (usa a pasta pacotes\ se houver
rem wheels nela; senao baixa, sempre conferindo hash) e apaga o ambiente no fim. Nada e instalado no seu Python.
rem Uso: RODAR ESTA PASTA - testes extras.bat                 (roda o 1 e PERGUNTA se roda tambem o 2)
rem      RODAR ESTA PASTA - testes extras.bat COBERTURA       (roda o 1 e o 2, sem perguntar)
rem      RODAR ESTA PASTA - testes extras.bat SO-INTEGRIDADE  (roda so o 1, sem perguntar)
rem Resultados basicos: testes\resultados\resultado_testes_extras.txt e os relatorios individuais.
rem Uma copia consolidada fica em testes\resultados\resultados completos\RESULTADO COMPLETO - TESTES EXTRAS.txt.
chcp 65001 >nul
setlocal EnableExtensions

rem --- acha a RAIZ do projeto subindo pastas ate achar o cofre_senhas.py ---
set "RAIZ=%~dp0"
:sobe
if exist "%RAIZ%cofre_senhas.py" goto :achou
for %%I in ("%RAIZ%..") do set "PAI=%%~fI\"
if /i "%PAI%"=="%RAIZ%" (
  echo ERRO: nao achei o cofre_senhas.py acima de %~dp0
  echo Deixe esta pasta dentro do projeto, em qualquer nivel abaixo da raiz.
  pause
  exit /b 1
)
set "RAIZ=%PAI%"
goto :sobe
:achou
set "AQUI=%~dp0"
cd /d "%RAIZ%"
set "RES=testes\resultados"
if not exist "%RES%" mkdir "%RES%"
set "SAIDA=%RES%\resultado_testes_extras.txt"
set "PASTA_COMPLETOS=%RES%\resultados completos"
set "COMPLETO=%PASTA_COMPLETOS%\RESULTADO COMPLETO - TESTES EXTRAS.txt"
rem Apaga restos de rodadas anteriores, para o arquivo final nunca misturar resultado velho com novo.
del /q "%RES%\integridade_ao_entrar.txt" "%RES%\cobertura_codigo.txt" "%RES%\cobertura_saida_testes.txt" >nul 2>nul
set "CACHE=%RAIZ%CACHE_PROJETO_NAO_MEXER\testes\_cache_extras_%RANDOM%"
if exist "%CACHE%" (
  echo ERRO: o caminho de cache temporario ja existe; nao vou apagar conteudo preexistente.
  exit /b 1
)
mkdir "%CACHE%" >nul 2>nul
if not exist "%CACHE%" (
  echo ERRO: nao consegui criar o cache temporario em %CACHE%
  exit /b 1
)
set "PYTHONPYCACHEPREFIX=%CACHE%\pycache"
set "PYTHONDONTWRITEBYTECODE=1"
set "TEMP=%CACHE%"
set "TMP=%CACHE%"
set "COFRE_AUTO=1"
rem Nada pode prender a rodada esperando um clique: um aviso fatal do programa vai para o texto, nao para uma janela.
set "COFRE_TESTE_SEM_JANELA_FATAL=1"
set "PYTHONPATH=%RAIZ%"
set "FALHAS=0"
set "FAZ_COBERTURA="
set "SO_INTEGRIDADE="
for %%A in (%*) do (
  if /i "%%A"=="COBERTURA" set "FAZ_COBERTURA=1"
  if /i "%%A"=="SO-INTEGRIDADE" set "SO_INTEGRIDADE=1"
)

echo ===== Testes extras (pasta 8) ===== > "%SAIDA%"
echo Data: %DATE% %TIME% >> "%SAIDA%"
echo Projeto: %RAIZ% >> "%SAIDA%"
echo. >> "%SAIDA%"

rem --- Python base (o mesmo 3.13 do instalador; cai para outro se nao houver) ---
set "PYBASE="
where py >nul 2>nul && (py -3.13 -c "import sys" >nul 2>nul && set "PYBASE=py -3.13")
if not defined PYBASE where py >nul 2>nul && (py -3 -c "import sys" >nul 2>nul && set "PYBASE=py -3")
if not defined PYBASE where python >nul 2>nul && set "PYBASE=python"
if not defined PYBASE (
  echo ERRO: nao achei o Python. Instale o Python 3.13 ou rode o "1 - INSTALAR O COFRE" primeiro.
  echo [FALHOU] Python nao encontrado >> "%SAIDA%"
  set /a FALHAS+=1
  goto :fim
)
echo Python: %PYBASE% >> "%SAIDA%"

rem --- ambiente temporario com as bibliotecas do lock (hash obrigatorio) ---
if not exist "%RAIZ%requirements-test-lock.txt" (
  echo ERRO: falta requirements-test-lock.txt na raiz do projeto.
  echo [FALHOU] requirements-test-lock.txt ausente >> "%SAIDA%"
  set /a FALHAS+=1
  goto :fim
)
set "VENV=%CACHE%\venv"
echo ... Criando ambiente temporario e instalando as bibliotecas do lock (alguns minutos)
%PYBASE% -m venv "%VENV%"
if errorlevel 1 (
  echo [FALHOU] nao consegui criar o ambiente temporario >> "%SAIDA%"
  set /a FALHAS+=1
  goto :fim
)
set "PY=%VENV%\Scripts\python.exe"
set "ORIGEM=--require-hashes"
dir /b "%RAIZ%pacotes\*.whl" >nul 2>nul && set "ORIGEM=--no-index --find-links "%RAIZ%pacotes" --require-hashes"
"%PY%" -m pip install --disable-pip-version-check --quiet %ORIGEM% -r "%RAIZ%requirements-test-lock.txt"
if errorlevel 1 (
  echo [FALHOU] nao consegui instalar as bibliotecas de teste. Rode o "3 - BAIXAR PACOTES" com internet ou confira a rede. >> "%SAIDA%"
  set /a FALHAS+=1
  goto :fim
)
echo [OK] ambiente temporario pronto >> "%SAIDA%"

echo ... 1) Verificacao de integridade ao entrar (abre janelas, leva alguns minutos por causa do Argon2)
"%PY%" "%AQUI%teste_gui_integridade_ao_entrar.py" > "%RES%\integridade_ao_entrar.txt" 2>&1
set "RC=%errorlevel%"
type "%RES%\integridade_ao_entrar.txt"
if "%RC%"=="0" (
  echo [OK] Integridade ao entrar >> "%SAIDA%"
) else (
  echo [FALHOU] Integridade ao entrar - codigo %RC%. Texto completo no fim deste arquivo. >> "%SAIDA%"
  set /a FALHAS+=1
)

if defined SO_INTEGRIDADE goto :fim
if not defined FAZ_COBERTURA (
  echo.
  choice /c SN /n /m "  Rodar tambem a COBERTURA do codigo? E lenta (roda todos os testes do nucleo). S = sim, N = nao: "
  if not errorlevel 2 set "FAZ_COBERTURA=1"
)
if not defined FAZ_COBERTURA (
  echo [PULADO] Cobertura do codigo - nao pedida nesta rodada >> "%SAIDA%"
  goto :fim
)
echo ... 2) Cobertura do codigo (demora)
"%PY%" "%AQUI%14_COBERTURA_DO_CODIGO.py"
set "RC=%errorlevel%"
if "%RC%"=="0" (
  echo [OK] Cobertura do codigo - relatorio no fim deste arquivo >> "%SAIDA%"
) else if "%RC%"=="2" (
  echo [PULADO] Cobertura do codigo - pre-requisito ausente, veja a mensagem acima >> "%SAIDA%"
) else (
  echo [ALERTA] Cobertura do codigo - codigo %RC% >> "%SAIDA%"
)
if exist "%RES%\cobertura_saida_testes.txt" echo [ALERTA] Houve teste do nucleo com erro durante a cobertura - texto no fim deste arquivo >> "%SAIDA%"

:fim
rem --- junta os textos completos no MESMO arquivo, para voce mandar um so ---
for %%F in (integridade_ao_entrar.txt cobertura_saida_testes.txt cobertura_codigo.txt) do (
  if exist "%RES%\%%F" (
    echo. >> "%SAIDA%"
    echo ===== %%F ===== >> "%SAIDA%"
    type "%RES%\%%F" >> "%SAIDA%"
  )
)
echo. >> "%SAIDA%"
echo Copia completa: %COMPLETO% >> "%SAIDA%"
if not exist "%PASTA_COMPLETOS%" mkdir "%PASTA_COMPLETOS%" >nul 2>nul
if not exist "%PASTA_COMPLETOS%" goto :falha_copia
copy /y "%SAIDA%" "%COMPLETO%" >nul
if errorlevel 1 goto :falha_copia
goto :depois_copia

:falha_copia
echo [FALHOU] Nao foi possivel copiar o relatorio para "%COMPLETO%". >> "%SAIDA%"
set /a FALHAS+=1
echo ERRO: nao foi possivel criar a copia completa em "%COMPLETO%".

:depois_copia
echo.
echo Resumo (o texto completo esta em %SAIDA%):
findstr /b /c:"[OK]" /c:"[FALHOU]" /c:"[PULADO]" /c:"[ALERTA]" "%SAIDA%"
echo.
cd /d "%RAIZ%"
if exist "%CACHE%" rmdir /s /q "%CACHE%" >nul 2>nul
if exist "%CACHE%" echo [AVISO] nao consegui apagar %CACHE% - apague essa pasta depois.
if "%FALHAS%"=="0" (echo Nenhum teste extra falhou.) else (echo FALHOU: veja as linhas [FALHOU] acima.)
echo Para me mandar o resultado, envie so este arquivo: %RAIZ%%SAIDA%
if exist "%COMPLETO%" echo Copia completa salva em: %RAIZ%%COMPLETO%
if not defined COFRE_TEST_SEM_PAUSA (
  echo Pressione uma tecla para fechar esta janela.
  pause >nul
)
exit /b %FALHAS%
