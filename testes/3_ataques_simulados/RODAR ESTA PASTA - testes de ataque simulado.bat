@echo off
chcp 65001 >nul
setlocal
rem Bateria de PENTEST (os teste_pentest_*.py desta pasta) no Windows real, com o Python do Windows.
rem Independente das outras baterias (nucleo/windows/gui): roda so o pentest, sozinho.
rem Offline: usa a pasta pacotes, se existir, para as bibliotecas OBRIGATORIAS (as mesmas do nucleo).
rem bandit/flake8/pip-audit sao OPCIONAIS (teste_pentest_sast.py e teste_pentest_dependencias.py pulam direto,
rem com aviso, se nao estiverem instalados) - por isso a instalacao delas aqui e so "melhor esforco", nunca
rem trava o script se nao tiver internet.
cd /d "%~dp0"
set "RAIZ=%~dp0.."
set "VENV=%~dp0_venv_pentest_tmp"
rem tudo fica DENTRO desta pasta (nada em %TEMP%\ ou solto no C:): o ambiente de teste fica aqui do lado e e
rem apagado sozinho no fim. So o RESULTADO vai uma pasta acima, em testes\resultados\, junto com os outros.
if not exist "%~dp0..\resultados" mkdir "%~dp0..\resultados"
set "SAIDA=%~dp0..\resultados\resultado_pentest_windows.txt"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONDONTWRITEBYTECODE=1"
echo.
echo  Bateria de PENTEST do Cofre de Senhas - aguarde (pode levar alguns minutos)...
where py >nul 2>nul || (echo  Python nao encontrado. Instale o Python 3.13 e rode de novo. & pause & exit /b 9)
if exist "%VENV%" rmdir /s /q "%VENV%"
py -3.13 -m venv "%VENV%" || (echo  Falhou criar o ambiente Python 3.13. & pause & exit /b 9)
if exist "%RAIZ%\pacotes\*.whl" (
  "%VENV%\Scripts\python.exe" -m pip install --no-index --find-links "%RAIZ%\pacotes" --disable-pip-version-check -q argon2-cffi cryptography fido2 openpyxl defusedxml
) else (
  "%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check -q argon2-cffi cryptography fido2 openpyxl defusedxml
)
if errorlevel 1 (echo  Falhou instalar as bibliotecas obrigatorias. & pause & exit /b 9)
rem melhor esforco (sem internet, so segue sem elas: os testes correspondentes avisam e pulam sozinhos)
"%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check -q bandit flake8 pip-audit >nul 2>nul
rem -u (sem buffer) + -v: mesmo truque das outras baterias, para o arquivo de resultado trazer tambem a saida
rem de quem falhar, e nao so o resumo final.
"%VENV%\Scripts\python.exe" -u -X utf8 "%~dp0rodar_pentest.py" -v > "%SAIDA%" 2>&1
set "COD=%errorlevel%"
type "%SAIDA%"
rmdir /s /q "%VENV%" >nul 2>nul
echo.
if "%COD%"=="0" (echo  TUDO PASSOU.) else (echo  ATENCAO: houve falhas. Mande o arquivo de resultado acima.)
echo  Resultado salvo em: %SAIDA%
pause
exit /b %COD%
