@echo off
rem Define COFRE_EXE: variavel de ambiente COFRE_EXE, ou 1o argumento, ou CofreSenhas.exe na raiz / pasta CofreSenhas.
if defined COFRE_EXE if exist "%COFRE_EXE%" goto :fim
set "COFRE_EXE="
if not "%~1"=="" if exist "%~1" set "COFRE_EXE=%~1"
if not defined COFRE_EXE if exist "%CD%\CofreSenhas.exe" set "COFRE_EXE=%CD%\CofreSenhas.exe"
if not defined COFRE_EXE if exist "%CD%\CofreSenhas\CofreSenhas.exe" set "COFRE_EXE=%CD%\CofreSenhas\CofreSenhas.exe"
:fim
exit /b 0
