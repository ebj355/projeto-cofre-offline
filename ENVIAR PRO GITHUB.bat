@echo off
cd /d "%~dp0"

echo ===== Enviando projeto para o GitHub =====
echo.
set "MSG="
set /p MSG=Descreva a mudanca (ou aperte Enter para usar data e hora): 
if "%MSG%"=="" set "MSG=Atualizacao %date% %time:~0,5%"

git add .
git commit -m "%MSG%"
git push

echo.
echo ===== Terminado. Confira acima se nao deu erro =====
pause
