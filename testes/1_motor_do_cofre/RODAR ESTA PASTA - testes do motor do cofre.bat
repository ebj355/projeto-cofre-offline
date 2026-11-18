@echo off
chcp 65001 >nul
setlocal
rem Teste do NUCLEO (os teste_*.py desta pasta) no Windows real, com o Python do Windows em vez do Linux.
rem Util para rodar SO essa parte, sem os testes especificos do instalador (esses ficam em
rem testes\4_so_no_windows\A - testar o instalador.bat) nem a bateria de interface (testes\2_telas_e_botoes\RODAR ESTA PASTA - testes das telas e botoes.bat).
rem Offline: usa a pasta pacotes, se existir.
cd /d "%~dp0"
set "RAIZ=%~dp0.."
set "VENV=%~dp0_venv_nucleo_tmp"
rem tudo fica DENTRO desta pasta (nada em %TEMP%\ ou solto no C:): o ambiente de teste fica aqui do lado e e
rem apagado sozinho no fim. So o RESULTADO vai uma pasta acima, em testes\resultados\, junto com o de todos
rem os outros testes.
if not exist "%~dp0..\resultados" mkdir "%~dp0..\resultados"
set "SAIDA=%~dp0..\resultados\resultado_nucleo_windows.txt"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONDONTWRITEBYTECODE=1"
echo.
echo  Teste do nucleo do Cofre de Senhas - aguarde (pode levar alguns minutos)...
where py >nul 2>nul || (echo  Python nao encontrado. Instale o Python 3.13 e rode de novo. & pause & exit /b 9)
if not exist "%RAIZ%\pacotes\*.whl" (echo  Dependencias offline nao encontradas em pacotes\. Rode primeiro 3 - BAIXAR PACOTES. & pause & exit /b 9)
if exist "%VENV%" rmdir /s /q "%VENV%"
py -3.13 -m venv "%VENV%" || (echo  Falhou criar o ambiente Python 3.13. & pause & exit /b 9)
"%VENV%\Scripts\python.exe" -m pip install --no-index --find-links "%RAIZ%\pacotes" --disable-pip-version-check -q argon2-cffi cryptography fido2 openpyxl defusedxml
if errorlevel 1 (echo  Falhou instalar as bibliotecas. & pause & exit /b 9)
rem -u (sem buffer) + -v: mesmo truque de teste_windows.ps1/teste_gui_windows.ps1, para o arquivo de resultado
rem trazer tambem a saida de quem falhar, e nao so o resumo final.
"%VENV%\Scripts\python.exe" -u -X utf8 "%~dp0..\6_ferramentas_dos_testes\rodar_todos.py" --so nucleo --sem-dev -v > "%SAIDA%" 2>&1
set "COD=%errorlevel%"
type "%SAIDA%"
rmdir /s /q "%VENV%" >nul 2>nul
echo.
if "%COD%"=="0" (echo  TUDO PASSOU.) else (echo  ATENCAO: houve falhas. Mande o arquivo de resultado acima.)
echo  Resultado salvo em: %SAIDA%
pause
exit /b %COD%
