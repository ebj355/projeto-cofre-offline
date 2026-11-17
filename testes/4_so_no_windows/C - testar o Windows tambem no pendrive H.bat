@echo off
rem Atalho: roda o teste nativo testando TAMBEM os atributos no pendrive H:. So funciona com o pendrive plugado.
rem Se a letra do seu pendrive nao for H, troque o "H" abaixo pela letra certa (ex.: "I").
cd /d "%~dp0"
call B - testar atributos e permissoes do Windows.bat H
