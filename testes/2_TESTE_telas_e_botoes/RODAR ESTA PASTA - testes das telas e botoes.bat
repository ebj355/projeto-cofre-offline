@rem ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not defined COFRE_TEST_MINIMIZADO (
  set "COFRE_TEST_MINIMIZADO=1"
  start "" /min cmd.exe /d /c ""%~f0" %*"
  exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0teste_gui_windows.ps1"
set "COD=%errorlevel%"
echo.
if not "%COD%"=="0" echo ATENCAO: o teste terminou com erro (codigo %COD%). Mande o ..\resultados\resultado_teste_gui_windows.txt mesmo assim.
echo Pronto. Resultado em ..\resultados\resultado_teste_gui_windows.txt
echo Pressione uma tecla para fechar esta janela.
pause >nul
exit /b %COD%
