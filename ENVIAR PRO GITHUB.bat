@rem ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
@echo off
setlocal
cd /d "%~dp0"
set "LOG=%TEMP%\envio_git.log"

echo ===== Enviar projeto para o GitHub =====
echo.

where git >nul 2>nul
if errorlevel 1 goto SEMGIT

rem --- Primeira vez: cria o repositorio local ---
if not exist ".git" git init
if not exist ".git" goto ERRO
git symbolic-ref HEAD refs/heads/main >nul 2>nul

rem --- Se sobrou um rebase travado de antes, cancela ---
if exist ".git\rebase-merge" git rebase --abort
if exist ".git\rebase-apply" git rebase --abort

rem --- Nome (so pergunta se ainda nao estiver configurado) ---
:NOME
set "GNOME="
for /f "delims=" %%A in ('git config user.name') do set "GNOME=%%A"
if defined GNOME goto EMAIL
set /p GNOME=Seu nome para aparecer nos commits: 
if not defined GNOME goto NOME
git config user.name "%GNOME%"

rem --- E-mail (so pergunta se ainda nao estiver configurado) ---
:EMAIL
set "GEMAIL="
for /f "delims=" %%A in ('git config user.email') do set "GEMAIL=%%A"
if defined GEMAIL goto REMOTO
set /p GEMAIL=Seu e-mail do GitHub: 
if not defined GEMAIL goto EMAIL
git config user.email "%GEMAIL%"

rem --- Endereco do repositorio (so pergunta na primeira vez) ---
:REMOTO
set "URL="
for /f "delims=" %%A in ('git remote get-url origin 2^>nul') do set "URL=%%A"
if defined URL goto COMMIT
echo.
echo Primeira vez neste projeto. Crie um repositorio vazio no GitHub e cole o endereco dele.
echo Exemplo: https://github.com/seu-usuario/seu-projeto.git
set /p URL=Endereco do repositorio: 
if not defined URL goto REMOTO
git remote add origin "%URL%"
if errorlevel 1 goto ERRO

rem --- Mensagem e commit ---
:COMMIT
echo.
set "MSG="
set /p MSG=Descreva a mudanca (ou aperte Enter para usar data e hora): 
if "%MSG%"=="" set "MSG=Atualizacao %date% %time:~0,5%"

rem --- Lista autorizada; os dois arquivos de envio ficam fora do commit ---
git add -u -- .gitignore LICENSE README.md cofre_senhas.py instalar_cofre.ps1 baixar_pacotes_offline.ps1 requirements.txt requirements-test-direct.in requirements-test-lock.txt ".github" documentacao testes pacotes/LEIA-ME.txt pacotes/SHA256.txt > "%LOG%" 2>&1
if errorlevel 1 goto ERRO_ADD
git add -- .gitignore LICENSE README.md MARCA_ARCA.txt cofre_senhas.py icones_marcas.py instalar_cofre.ps1 baixar_pacotes_offline.ps1 requirements.txt requirements-test-direct.in requirements-test-lock.txt ruff.toml ".github" documentacao testes pacotes/LEIA-ME.txt pacotes/SHA256.txt >> "%LOG%" 2>&1
if errorlevel 1 goto ERRO_ADD
git diff --cached --quiet
if errorlevel 1 goto CRIAR_COMMIT
goto DEPOIS_COMMIT

:CRIAR_COMMIT
set "ARQUIVO_MSG=%TEMP%\arca_commit_%RANDOM%.txt"
>"%ARQUIVO_MSG%" echo %MSG%
git commit -F "%ARQUIVO_MSG%" > "%LOG%" 2>&1
set "RC=%errorlevel%"
del /q "%ARQUIVO_MSG%" >nul 2>nul
type "%LOG%"
if not "%RC%"=="0" goto ERRO_COMMIT

:DEPOIS_COMMIT
git branch -M main >nul 2>nul
if errorlevel 1 goto ERRO

rem --- Diferencia GitHub vazio de falha de rede/autenticacao ---
git ls-remote --exit-code --heads origin main > "%LOG%" 2>&1
set "RC=%errorlevel%"
if "%RC%"=="0" goto PUXAR
if "%RC%"=="2" goto ENVIAR
type "%LOG%"
goto ERRO

:PUXAR
echo.
echo Sincronizando com o GitHub...
git pull --rebase --autostash origin main > "%LOG%" 2>&1
set "RC=%errorlevel%"
type "%LOG%"
if "%RC%"=="0" goto ENVIAR
if exist ".git\rebase-merge" goto CONFLITO
if exist ".git\rebase-apply" goto CONFLITO
goto ERRO

:CONFLITO
echo.
echo Conflito encontrado. Nenhuma versao sera sobrescrita automaticamente.
git rebase --abort
goto ERRO

:ENVIAR
echo.
git push -u origin main > "%LOG%" 2>&1
set "RC=%errorlevel%"
type "%LOG%"
if not "%RC%"=="0" goto ERRO

echo.
echo ===== Terminado com sucesso! =====
goto FIM

:SEMGIT
echo O Git nao esta instalado. Baixe em https://git-scm.com/download/win e rode de novo.
goto FIM

:ERRO
echo.
echo ===== DEU ERRO. Leia a mensagem acima. =====
goto FIM

:ERRO_ADD
echo.
echo ===== O Git nao conseguiu preparar os arquivos permitidos =====
type "%LOG%"
goto ERRO

:ERRO_COMMIT
echo.
echo ===== O Git nao conseguiu criar o commit =====
goto ERRO

:FIM
echo.
pause
