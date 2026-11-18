@echo off
setlocal EnableExtensions
cd /d "%~dp0..\.."
set "RAIZ=%CD%"
set "VENV=%RAIZ%\testes\_venv_ferramentas"
set "PY=%VENV%\Scripts\python.exe"

if not exist "%RAIZ%\requirements-test.txt" (
  echo ERRO: requirements-test.txt nao encontrado.
  exit /b 1
)
if not exist "%RAIZ%\pacotes\*.whl" (
  echo ERRO: wheelhouse offline ausente. Rode 3 - BAIXAR PACOTES com internet antes de copiar o projeto.
  exit /b 1
)
where py >nul 2>nul || (
  echo ERRO: Python nao encontrado. Use o instalador python-3.13.17-*.exe em pacotes\.
  exit /b 1
)
if not exist "%PY%" (
  py -3.13 -m venv "%VENV%"
  if errorlevel 1 (
    echo ERRO: nao foi possivel criar o ambiente Python de ferramentas.
    exit /b 1
  )
)
"%PY%" -m pip install --disable-pip-version-check --no-index --find-links "%RAIZ%\pacotes" -q -r "%RAIZ%\requirements-test.txt"
if errorlevel 1 (
  echo ERRO: faltam pacotes de teste em pacotes\. Rode 3 - BAIXAR PACOTES novamente.
  exit /b 1
)
endlocal & set "COFRE_PYTHON=%PY%"
exit /b 0
