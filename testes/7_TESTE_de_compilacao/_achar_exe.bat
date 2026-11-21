@rem ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
@echo off
rem Define COFRE_EXE: variavel/argumento explicito, raiz do drive indicado ou do script, depois caminhos do projeto.
if defined COFRE_EXE if exist "%COFRE_EXE%" goto :fim
set "COFRE_EXE="
if not "%~1"=="" if exist "%~1" set "COFRE_EXE=%~1"
if not defined COFRE_EXE if defined COFRE_USB_DRIVE if exist "%COFRE_USB_DRIVE%\CofreSenhas.exe" set "COFRE_EXE=%COFRE_USB_DRIVE%\CofreSenhas.exe"
if not defined COFRE_EXE if exist "%~d0\CofreSenhas.exe" set "COFRE_EXE=%~d0\CofreSenhas.exe"
if not defined COFRE_EXE if exist "%CD%\CofreSenhas.exe" set "COFRE_EXE=%CD%\CofreSenhas.exe"
if not defined COFRE_EXE if exist "%CD%\CofreSenhas\CofreSenhas.exe" set "COFRE_EXE=%CD%\CofreSenhas\CofreSenhas.exe"
:fim
exit /b 0
