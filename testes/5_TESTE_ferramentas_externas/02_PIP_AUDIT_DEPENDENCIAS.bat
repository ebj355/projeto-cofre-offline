@rem ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
@echo off
rem pip-audit: confere as bibliotecas do requirements.txt contra vulnerabilidades conhecidas (precisa de internet).
rem Offline: por padrao pula, pois uma base local desatualizada daria uma falsa garantia. Para consultar a base atual, defina COFRE_ONLINE_AUDIT=1.
rem Codigos de saida: 0 = nada encontrado | 1 = ha achados ou falha de rede | 2 = requirements.txt nao encontrado | 9 = pulado
rem Com a variavel COFRE_AUTO definida (bateria geral) nao mostra o relatorio na tela e nao pausa.
setlocal
cd /d "%~dp0..\.."
title Cofre - pip-audit: bibliotecas
if not exist "requirements.txt" (
  echo ERRO: requirements.txt nao encontrado na raiz do projeto.
  if not defined COFRE_AUTO pause
  exit /b 2
)
set "REL=testes\resultados"
if not exist "%REL%" mkdir "%REL%"
set "LOG=%REL%\pip_audit.txt"
if not "%COFRE_ONLINE_AUDIT%"=="1" (
  >"%LOG%" echo [PULADO] pip-audit requer uma consulta online atualizada a vulnerabilidades.
  >>"%LOG%" echo Nenhuma base local foi incluida, para evitar apresentar dados antigos como atuais.
  if not defined COFRE_AUTO type "%LOG%"
  echo Auditoria de dependencias pulada. Defina COFRE_ONLINE_AUDIT=1 para consultar a internet.
  if not defined COFRE_AUTO pause
  exit /b 9
)
call "%~dp0preparar_ambiente_offline.bat" PIP_AUDIT
if errorlevel 1 (
  if not defined COFRE_AUTO pause
  exit /b 9
)
echo Auditando as dependencias declaradas em requirements.txt...
echo Projeto: %CD% > "%LOG%"
echo Data: %DATE% %TIME% >> "%LOG%"
echo. >> "%LOG%"
"%COFRE_PYTHON%" "%~dp0..\6_TESTE_ferramentas_dos_testes\rodar_pip_audit.py" --python "%COFRE_PYTHON%" --requirements "requirements.txt" --log "%LOG%" --timeout 60
set "RC=%ERRORLEVEL%"
echo.>> "%LOG%"
echo Codigo de saida: %RC%>> "%LOG%"
if not defined COFRE_AUTO type "%LOG%"
echo.
echo Relatorio salvo em: %LOG%
echo Codigo de saida: %RC%  - 0 = nada encontrado, 1 = ha achados ou falha de rede
echo Nota: pip-audit consulta avisos conhecidos; isso nao prova ausencia de falhas.
if not defined COFRE_AUTO pause
exit /b %RC%
