@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0teste_gui_windows.ps1"
set "COD=%errorlevel%"
echo.
if not "%COD%"=="0" echo ATENCAO: o teste terminou com erro (codigo %COD%). Mande o ..\resultados\resultado_teste_gui_windows.txt mesmo assim.
echo Pronto. Resultado em ..\resultados\resultado_teste_gui_windows.txt
echo Pressione uma tecla para fechar esta janela.
pause >nul
exit /b %COD%
