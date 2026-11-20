@echo off
rem Com o CofreSenhas.exe ABERTO, lista conexoes/portas TCP e UDP que o processo tem. O esperado e nenhuma (programa 100%% local).
rem Codigos de saida: 0 = nenhuma conexao | 1 = ha conexoes | 9 = cofre nao esta aberto (pulado)
setlocal
cd /d "%~dp0..\.."
title Cofre - rede do processo
set "REL=testes\resultados"
if not exist "%REL%" mkdir "%REL%"
set "LOG=%REL%\rede_processo.txt"
echo Projeto: %CD% > "%LOG%"
echo Data: %DATE% %TIME% >> "%LOG%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Get-Process -Name CofreSenhas* -ErrorAction SilentlyContinue; if(-not $p){'[PULADO] Nenhum processo CofreSenhas.exe aberto; abra o executavel e rode de novo.'; exit 9}; $ids=$p.Id; 'PIDs: '+($ids -join ','); $t=Get-NetTCPConnection -OwningProcess $ids -ErrorAction SilentlyContinue; $u=Get-NetUDPEndpoint -OwningProcess $ids -ErrorAction SilentlyContinue; $t|Format-Table LocalAddress,LocalPort,RemoteAddress,RemotePort,State -AutoSize|Out-String; $u|Format-Table LocalAddress,LocalPort -AutoSize|Out-String; if($t -or $u){'[ALERTA] O processo tem conexoes de rede.'; exit 1}else{'[OK] Nenhuma conexao TCP/UDP.'; exit 0}" >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
>> "%LOG%" echo Codigo de saida: %RC%
if not defined COFRE_AUTO type "%LOG%"
echo Relatorio salvo em: %LOG%
if not defined COFRE_AUTO pause
exit /b %RC%
