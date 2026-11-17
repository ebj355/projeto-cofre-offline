@echo off
rem Cobertura de codigo (coverage.py) no Windows: mede quais linhas/ramificacoes de cofre_senhas.py os testes executam.
rem NAO faz parte do Testar_Tudo (e lenta e e uma ferramenta de analise, nao um teste). Dois cliques para rodar.
rem Resultado: testes\resultados\cobertura_codigo.txt  (+ cobertura_codigo.json e a pasta cobertura_html\index.html)
rem Tudo fica dentro da pasta do projeto: o ambiente Python temporario fica ao lado e e apagado no fim.
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
set "RAIZ=%~dp0..\.."
set "VENV=%~dp0_venv_cobertura_tmp"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONDONTWRITEBYTECODE=1"
echo.
echo  Cobertura de codigo do Cofre de Senhas - aguarde (pode levar 15-30 minutos)...
where py >nul 2>nul || (echo  Python nao encontrado. Instale o Python 3.13 e rode de novo. & pause & exit /b 9)
if exist "%VENV%" rmdir /s /q "%VENV%"
py -3.13 -m venv "%VENV%" || (echo  Falhou criar o ambiente Python 3.13. & pause & exit /b 9)
if exist "%RAIZ%\pacotes\*.whl" (
  "%VENV%\Scripts\python.exe" -m pip install --no-index --find-links "%RAIZ%\pacotes" --disable-pip-version-check -q argon2-cffi cryptography fido2 openpyxl defusedxml coverage
) else (
  "%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check -q argon2-cffi cryptography fido2 openpyxl defusedxml coverage
)
"%VENV%\Scripts\python.exe" -u -X utf8 "%~dp0cobertura_codigo.py" %*
set "RC=%ERRORLEVEL%"
rmdir /s /q "%VENV%" 2>nul
echo.
echo  Resultado: testes\resultados\cobertura_codigo.txt  e  cobertura_html\index.html
echo Pressione uma tecla para fechar esta janela.
pause >nul
exit /b %RC%
