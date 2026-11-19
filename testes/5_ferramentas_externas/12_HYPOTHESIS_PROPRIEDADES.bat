@echo off
rem Hypothesis: roda testes\1_motor_do_cofre\teste_propriedades_hypothesis.py (ida e volta do cofre e CSV hostil com milhares de entradas geradas).
rem Codigos de saida: 0 = passou | 1 = falhou | 9 = ambiente/hypothesis ausente (pulado)
setlocal
cd /d "%~dp0..\.."
title Cofre - Hypothesis: testes por propriedades
set "REL=testes\resultados"
if not exist "%REL%" mkdir "%REL%"
set "LOG=%REL%\hypothesis.txt"
call "%~dp0preparar_ambiente_offline.bat"
if errorlevel 1 (
  if not defined COFRE_AUTO pause
  exit /b 9
)
echo Projeto: %CD% > "%LOG%"
echo Data: %DATE% %TIME% >> "%LOG%"
"%COFRE_PYTHON%" "testes\1_motor_do_cofre\teste_propriedades_hypothesis.py" >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
echo Codigo de saida: %RC%>> "%LOG%"
if not defined COFRE_AUTO type "%LOG%"
echo Relatorio salvo em: %LOG%
echo Nota: trabalha em pastas temporarias; nunca toca no seu cofre.dat. Quando falha, o Hypothesis mostra o menor exemplo que reproduz.
if not defined COFRE_AUTO pause
exit /b %RC%
