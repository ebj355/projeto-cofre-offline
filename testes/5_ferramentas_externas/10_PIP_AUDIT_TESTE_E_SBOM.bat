@echo off
rem pip-audit tambem no requirements-test.txt e gera o inventario SBOM (CycloneDX) do requirements.txt. Precisa de internet: COFRE_ONLINE_AUDIT=1.
rem Codigos de saida: 0 = nada encontrado | 1 = achados ou falha de rede | 9 = pulado (offline)
setlocal
cd /d "%~dp0..\.."
title Cofre - pip-audit (testes) e SBOM
set "REL=testes\resultados"
if not exist "%REL%" mkdir "%REL%"
set "LOG=%REL%\pip_audit_testes_sbom.txt"
if not "%COFRE_ONLINE_AUDIT%"=="1" (
  >"%LOG%" echo [PULADO] Defina COFRE_ONLINE_AUDIT=1 para consultar a base atual de vulnerabilidades.
  if not defined COFRE_AUTO type "%LOG%"
  if not defined COFRE_AUTO pause
  exit /b 9
)
call "%~dp0preparar_ambiente_offline.bat"
if errorlevel 1 (
  if not defined COFRE_AUTO pause
  exit /b 9
)
echo Projeto: %CD% > "%LOG%"
echo Data: %DATE% %TIME% >> "%LOG%"
"%COFRE_PYTHON%" -m pip_audit -r requirements-test.txt >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
"%COFRE_PYTHON%" -m pip_audit -r requirements.txt -f cyclonedx-json -o "%REL%\sbom.cdx.json" >> "%LOG%" 2>&1
echo Codigo de saida: %RC%>> "%LOG%"
if not defined COFRE_AUTO type "%LOG%"
echo Relatorio: %LOG%  /  SBOM: %REL%\sbom.cdx.json
if not defined COFRE_AUTO pause
exit /b %RC%
