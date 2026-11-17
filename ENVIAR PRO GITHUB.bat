@echo off
setlocal
cd /d "%~dp0"

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

rem --- Mensagem e commit ---
:COMMIT
echo.
set "MSG="
set /p MSG=Descreva a mudanca (ou aperte Enter para usar data e hora): 
if "%MSG%"=="" set "MSG=Atualizacao %date% %time:~0,5%"

git add -A
git diff --cached --quiet
if errorlevel 1 git commit -m "%MSG%"
git branch -M main >nul 2>nul

rem --- Se o GitHub ainda esta vazio, nao ha o que buscar ---
git ls-remote --exit-code --heads origin main >nul 2>nul
if errorlevel 1 goto ENVIAR

echo.
echo Sincronizando com o GitHub...
git pull --rebase --autostash origin main
if not errorlevel 1 goto ENVIAR

echo.
echo Conflito encontrado. Mantendo a versao deste computador...
set /a TENT=0

:RESOLVER
set /a TENT+=1
if %TENT% GTR 10 goto ERRO
for /f "delims=" %%F in ('git diff --name-only --diff-filter=U') do (
    echo   Resolvendo: "%%F"
    git checkout --theirs -- "%%F"
)
git add -A
set "GIT_EDITOR=true"
git rebase --continue
if exist ".git\rebase-merge" goto RESOLVER
if exist ".git\rebase-apply" goto RESOLVER

:ENVIAR
echo.
git push -u origin main
if errorlevel 1 goto ERRO

echo.
echo ===== Terminado com sucesso! =====
goto FIM

:SEMGIT
echo O Git nao esta instalado. Baixe em https://git-scm.com/download/win e rode de novo.
goto FIM

:ERRO
echo.
echo ===== DEU ERRO. Leia a mensagem acima. =====

:FIM
echo.
pause
