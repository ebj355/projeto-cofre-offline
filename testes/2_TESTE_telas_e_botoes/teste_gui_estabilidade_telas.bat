@rem ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
@echo off
rem Estabilidade visual: clica em cada opcao das telas e confere que nada pula, anda ou muda de tamanho.
cd /d "%~dp0"
where py >nul 2>nul && (py -3.13 teste_gui_estabilidade_telas.py %*) || (python teste_gui_estabilidade_telas.py %*)
if errorlevel 1 (echo. & echo FALHOU: veja as linhas [FALHOU] acima. & pause & exit /b 1)
exit /b 0
