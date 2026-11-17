@echo off
rem Atalho na RAIZ do projeto (fora da pasta testes\) para rodar a bateria COMPLETA de testes (as 5 baterias:
rem nucleo, instalador, nativo, interface e pentest) sem precisar entrar em testes\ferramentas_dos_testes\. So CHAMA o
rem rodar_todos_windows.bat de la - nao duplica nenhuma logica, so facilita o acesso.
rem
rem Cada pasta de teste (testes\1_motor_do_cofre\, testes\4_so_no_windows\, testes\2_telas_e_botoes\, testes\3_ataques_simulados\) ja tem o seu PROPRIO
rem .bat individual, para rodar so aquela bateria sozinha (dois cliques direto na pasta dela). Este .bat
rem aqui e so o atalho GERAL, para rodar as cinco de uma vez, sem precisar abrir cada uma.
rem
rem Uso: 2 - TESTAR TUDO - roda todos os testes.bat          (nativo testa so o disco do sistema)
rem      2 - TESTAR TUDO - roda todos os testes.bat H        (nativo testa tambem o pendrive H: - repassado ao teste nativo)
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
if not exist "%~dp0testes\ferramentas_dos_testes\rodar_todos_windows.bat" (
  echo ERRO: nao achei testes\ferramentas_dos_testes\rodar_todos_windows.bat
  echo Este atalho precisa estar na RAIZ do projeto, do lado da pasta "testes".
  pause
  exit /b 1
)
call "%~dp0testes\ferramentas_dos_testes\rodar_todos_windows.bat" %1
exit /b %errorlevel%
