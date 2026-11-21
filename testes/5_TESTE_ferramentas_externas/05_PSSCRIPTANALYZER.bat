@rem ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
@echo off
rem PSScriptAnalyzer: lint dos .ps1 do projeto (instalador, baixar pacotes, testes). Modulo vem de pacotes\powershell-modules.
rem Codigos de saida: 0 = nada encontrado | 1 = ha achados para revisar | 9 = modulo nao baixado (pulado)
rem Com a variavel COFRE_AUTO definida (bateria geral) nao mostra o relatorio na tela e nao pausa.
setlocal
cd /d "%~dp0..\.."
title Cofre - PSScriptAnalyzer: scripts PowerShell
set "REL=testes\resultados"
if not exist "%REL%" mkdir "%REL%"
set "LOG=%REL%\psscriptanalyzer.txt"
if not exist "pacotes\powershell-modules\PSScriptAnalyzer" (
  >"%LOG%" echo [PULADO] Modulo PSScriptAnalyzer ausente. Rode baixar_psscriptanalyzer.ps1 com internet.
  if not defined COFRE_AUTO type "%LOG%"
  if not defined COFRE_AUTO pause
  exit /b 9
)
echo Analisando os scripts PowerShell...
echo Projeto: %CD% > "%LOG%"
echo Data: %DATE% %TIME% >> "%LOG%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:PSModulePath=(Resolve-Path 'pacotes\powershell-modules').Path+';'+$env:PSModulePath; Import-Module PSScriptAnalyzer; $r=Get-ChildItem -Recurse -Filter *.ps1 | Where-Object { $_.FullName -notmatch 'ambiente_virtual_ferramentas|pacotes' } | ForEach-Object { Invoke-ScriptAnalyzer -Path $_.FullName -Severity Error,Warning }; $r | Format-Table RuleName,Severity,ScriptName,Line,Message -AutoSize -Wrap | Out-String -Width 200; $erros=@($r | Where-Object { $_.Severity -eq 'Error' }); if($erros.Count -gt 0){exit 1}else{exit 0}" >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
echo.>> "%LOG%"
echo Codigo de saida: %RC%>> "%LOG%"
if not defined COFRE_AUTO type "%LOG%"
echo Relatorio salvo em: %LOG%
echo Nota: alertas de estilo (ex.: Write-Host) sao esperados em scripts de instalacao; revise so Error e praticas inseguras.
if not defined COFRE_AUTO pause
exit /b %RC%
