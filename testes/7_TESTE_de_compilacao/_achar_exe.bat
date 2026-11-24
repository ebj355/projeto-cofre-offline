@rem ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
@echo off
rem Define COFRE_EXE. Procura, nesta ordem: variavel COFRE_EXE, argumento (arquivo ou pasta), COFRE_USB_DRIVE,
rem a PROPRIA pasta deste script (testes\7_TESTE_de_compilacao), a raiz do projeto, a raiz do drive e as pastas
rem CofreSenhas, a pasta de compilacao do projeto e a raiz de cada unidade D: a Z:. Se nao achar e ninguem estiver automatizando (COFRE_AUTO nao definido), PERGUNTA onde esta o
rem arquivo: arraste o CofreSenhas.exe para a janela e aperte Enter. Enter sem nada = pular.
if defined COFRE_PULAR_EXE set "COFRE_EXE="
if defined COFRE_PULAR_EXE goto :fim
if defined COFRE_EXE if exist "%COFRE_EXE%" goto :fim
set "COFRE_EXE="
call :tentar "%~1"
call :tentar "%COFRE_USB_DRIVE%"
call :tentar "%~dp0"
call :tentar "%~dp0..\.."
call :tentar "%~dp0..\..\CofreSenhas"
call :tentar "%~d0\"
call :tentar "%CD%"
call :tentar "%CD%\CofreSenhas"
rem o .exe recem-compilado fica na pasta de compilacao do projeto (cache permanente)
call :tentar "%~dp0..\..\CACHE_PROJETO_NAO_MEXER\compilacao"
rem o .exe instalado no pendrive/disco: procura na raiz de cada letra de unidade existente (D: a Z:)
for %%D in (D E F G H I J K L M N O P Q R S T U V W X Y Z) do if not defined COFRE_EXE if exist "%%D:\CofreSenhas.exe" call :tentar "%%D:\"
if defined COFRE_EXE goto :fim
if defined COFRE_AUTO goto :fim
if defined COFRE_NAO_PERGUNTAR goto :fim
set "TENT=0"
:perguntar
echo.
echo  Nao achei o CofreSenhas.exe nas pastas do projeto.
echo  Arraste o arquivo CofreSenhas.exe (ou a pasta dele) para esta janela e aperte Enter.
echo  Para pular as verificacoes do executavel, aperte so Enter.
set "RESP="
set /p "RESP=  Caminho do CofreSenhas.exe: "
if not defined RESP goto :fim
set "RESP=%RESP:"=%"
call :tentar "%RESP%"
if defined COFRE_EXE goto :achou
set /a TENT+=1
echo  Nao encontrei o CofreSenhas.exe nesse caminho.
if %TENT% LSS 3 goto :perguntar
goto :fim
:achou
echo  Usando: %COFRE_EXE%
:fim
exit /b 0

:tentar
rem Aceita o caminho do .exe ou de uma pasta que o contenha; so define COFRE_EXE se o arquivo existir.
if defined COFRE_EXE exit /b 0
if "%~1"=="" exit /b 0
if exist "%~1\CofreSenhas.exe" set "COFRE_EXE=%~f1\CofreSenhas.exe"
if defined COFRE_EXE set "COFRE_EXE=%COFRE_EXE:\\CofreSenhas.exe=\CofreSenhas.exe%"
if defined COFRE_EXE exit /b 0
if exist "%~1\" exit /b 0
if exist "%~1" set "COFRE_EXE=%~f1"
exit /b 0
