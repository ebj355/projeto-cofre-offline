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
call "%~dp0preparar_ambiente_offline.bat" PIP_AUDIT
if errorlevel 1 (
  if not defined COFRE_AUTO pause
  exit /b 9
)
set "PIP_NO_CACHE_DIR=1"
set "PIP_DEFAULT_TIMEOUT=15"
set "PIP_RETRIES=0"
echo Projeto: %CD% > "%LOG%"
echo Data: %DATE% %TIME% >> "%LOG%"
set "REQ_AUDIT=%TEMP%\cofre-requirements-test-%RANDOM%-%RANDOM%.txt"
"%COFRE_PYTHON%" -c "from pathlib import Path; p=Path('requirements-test.txt'); q=Path(r'%REQ_AUDIT%'); linhas=p.read_text(encoding='utf-8-sig').splitlines(); base=lambda l:l.split(';',1)[0].strip(); fixas=[l for l in linhas if l.strip() and not l.lstrip().startswith('#') and '==' in base(l) and not any(op in base(l) for op in ('>=','<=','~=','!=','<','>'))]; pendentes=[base(l) for l in linhas if l.strip() and not l.lstrip().startswith('#') and l not in fixas]; q.write_text('\n'.join(fixas)+'\n',encoding='utf-8'); print('Dependencias de teste fixadas auditadas: '+str(len(fixas))+'; faixas nao fixadas puladas: '+(', '.join(pendentes) or 'nenhuma'))" >> "%LOG%" 2>&1
if errorlevel 1 goto audit_teste_preparacao_falhou
"%COFRE_PYTHON%" -m pip_audit -r "%REQ_AUDIT%" --no-deps --disable-pip --timeout 15 >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
goto audit_teste_preparacao_pronta
:audit_teste_preparacao_falhou
set "RC=1"
:audit_teste_preparacao_pronta
del "%REQ_AUDIT%" >nul 2>nul
"%COFRE_PYTHON%" -m pip_audit -r requirements.txt --no-deps --disable-pip --timeout 15 -f cyclonedx-json -o "%REL%\sbom.cdx.json" >> "%LOG%" 2>&1
set "RC_SBOM=%ERRORLEVEL%"
if "%RC%"=="0" set "RC=%RC_SBOM%"
echo Codigo de saida: %RC%>> "%LOG%"
if not defined COFRE_AUTO type "%LOG%"
echo Relatorio: %LOG%  /  SBOM: %REL%\sbom.cdx.json
if not defined COFRE_AUTO pause
exit /b %RC%
