@rem ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
@echo off
chcp 65001 >nul
setlocal
if not defined COFRE_TEST_MINIMIZADO (
  set "COFRE_TEST_MINIMIZADO=1"
  start "" /min cmd.exe /d /c ""%~f0" %*"
  exit /b
)
rem Teste NATIVO no Windows (atributos, ACL, SMBIOS, DPAPI, PC autorizado, DLLs). Offline: usa a pasta pacotes.
rem Uso: B - testar atributos e permissoes do Windows.bat          (so o disco do sistema)
rem      B - testar atributos e permissoes do Windows.bat H        (testa tambem os atributos no pendrive H:)
cd /d "%~dp0"
set "RAIZ=%~dp0..\.."
set "VENV=%~dp0_venv_nativo_tmp"
rem tudo fica DENTRO desta pasta (nada em %TEMP%\ ou solto no C:): o ambiente e os arquivos de teste
rem ficam aqui do lado e sao apagados sozinhos no fim. So o RESULTADO vai uma pasta acima, em testes\resultados\,
rem junto com o de todos os outros testes.
rem nome do resultado muda sozinho conforme o uso, para nunca sobrescrever o resultado de outro teste:
rem sem pendrive = resultado_nativo_windows.txt | com letra (ex.: H) = resultado_nativo_windows_H.txt
if not exist "%~dp0..\resultados" mkdir "%~dp0..\resultados"
if "%~1"=="" (set "SAIDA=%~dp0..\resultados\resultado_nativo_windows.txt") else (set "SAIDA=%~dp0..\resultados\resultado_nativo_windows_%~1.txt")
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONDONTWRITEBYTECODE=1"
echo.
echo  Teste nativo do Cofre de Senhas - aguarde (1 a 3 minutos)...
where py >nul 2>nul || (echo  Python nao encontrado. Instale o Python 3.13 e rode de novo. & pause & exit /b 9)
if not exist "%RAIZ%\pacotes\*.whl" (echo  Dependencias offline nao encontradas em pacotes\. Rode primeiro 3 - BAIXAR PACOTES. & pause & exit /b 9)
if exist "%VENV%" rmdir /s /q "%VENV%"
py -3.13 -m venv "%VENV%" || (echo  Falhou criar o ambiente Python 3.13. & pause & exit /b 9)
"%VENV%\Scripts\python.exe" -m pip install --no-index --find-links "%RAIZ%\pacotes" --disable-pip-version-check -q argon2-cffi cryptography fido2 openpyxl defusedxml pillow
if errorlevel 1 (echo  Falhou instalar as bibliotecas. & pause & exit /b 9)
"%VENV%\Scripts\python.exe" -X utf8 "%~dp0teste_nativo_windows.py" %* > "%SAIDA%" 2>&1
set "COD=%errorlevel%"
type "%SAIDA%"
rmdir /s /q "%VENV%" >nul 2>nul
echo.
if "%COD%"=="0" (echo  TUDO PASSOU.) else (echo  ATENCAO: houve falhas. Mande o arquivo de resultado acima.)
echo  Resultado salvo em: %SAIDA%
pause
exit /b %COD%
