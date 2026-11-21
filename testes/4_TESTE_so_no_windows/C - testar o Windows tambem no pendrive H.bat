@rem ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
@echo off
setlocal
if not defined COFRE_TEST_MINIMIZADO (
  set "COFRE_TEST_MINIMIZADO=1"
  start "" /min cmd.exe /d /c ""%~f0" %*"
  exit /b
)
rem Atalho: roda o teste nativo testando TAMBEM os atributos no pendrive H:. So funciona com o pendrive plugado.
rem Se a letra do seu pendrive nao for H, troque o "H" abaixo pela letra certa (ex.: "I").
cd /d "%~dp0"
call B - testar atributos e permissoes do Windows.bat H
