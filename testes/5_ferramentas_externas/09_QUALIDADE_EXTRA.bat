@echo off
rem Qualidade extra do cofre_senhas.py: Ruff (lint/seguranca), mypy (tipos), Radon (complexidade) e Vulture (codigo morto).
rem Codigos de saida: 0 = Ruff sem achados | 1 = Ruff com achados (mypy/Radon/Vulture so informam) | 9 = ferramentas nao instaladas (pulado)
setlocal
cd /d "%~dp0..\.."
title Cofre - qualidade extra
set "REL=testes\resultados"
if not exist "%REL%" mkdir "%REL%"
set "LOG=%REL%\qualidade_extra.txt"
call "%~dp0preparar_ambiente_offline.bat"
if errorlevel 1 (
  if not defined COFRE_AUTO pause
  exit /b 9
)
"%COFRE_PYTHON%" -m ruff --version >nul 2>&1
if errorlevel 1 (
  echo ERRO: ruff nao esta no wheelhouse. Rode 3 - BAIXAR PACOTES de novo. > "%LOG%"
  if not defined COFRE_AUTO type "%LOG%"
  if not defined COFRE_AUTO pause
  exit /b 9
)
echo Projeto: %CD% > "%LOG%"
echo Data: %DATE% %TIME% >> "%LOG%"
echo. >> "%LOG%"
echo ===== Ruff - regras E,F,S,B,UP ===== >> "%LOG%"
"%COFRE_PYTHON%" -m ruff check cofre_senhas.py --select E,F,S,B,UP --line-length 200 >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
echo. >> "%LOG%"
echo ===== mypy - tipos (informativo) ===== >> "%LOG%"
"%COFRE_PYTHON%" -m mypy cofre_senhas.py --ignore-missing-imports --no-error-summary >> "%LOG%" 2>&1
echo. >> "%LOG%"
echo ===== Radon - funcoes com complexidade C ou pior (informativo) ===== >> "%LOG%"
"%COFRE_PYTHON%" -m radon cc cofre_senhas.py -n C -s >> "%LOG%" 2>&1
echo. >> "%LOG%"
echo ===== Vulture - codigo possivelmente morto, confianca 80%% (informativo) ===== >> "%LOG%"
"%COFRE_PYTHON%" -m vulture cofre_senhas.py --min-confidence 80 >> "%LOG%" 2>&1
echo. >> "%LOG%"
echo Codigo de saida: %RC%>> "%LOG%"
if not defined COFRE_AUTO type "%LOG%"
echo Relatorio salvo em: %LOG%
echo Nota: o arquivo tem ~12.800 linhas; espere muitos avisos do mypy/Radon. Use para achar os piores pontos, nao para zerar.
if not defined COFRE_AUTO pause
exit /b %RC%
