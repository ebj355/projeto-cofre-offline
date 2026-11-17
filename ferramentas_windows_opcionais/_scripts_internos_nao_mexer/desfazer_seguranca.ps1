# ============================================================================
#  Desfaz os ajustes do aplicar_seguranca.ps1 (volta ao padrão de fábrica do Windows)
#  - Liga de novo a reprodução automática de pendrives/CDs (autoplay)
#  - Liga de novo o histórico da área de transferência (Win+V)
#  - A Integridade da Memória e o Secure Boot NÃO são desfeitos por aqui: são telas do
#    Windows/BIOS que o próprio aplicar_seguranca.ps1 só abriu, sem ligar nada sozinho,
#    então quem desliga (se quiser) é você, pelas mesmas telas.
#  Pede confirmação (S/ENTER) antes de mudar qualquer coisa.
# ============================================================================
$ErrorActionPreference = 'SilentlyContinue'

# Precisa de administrador porque os ajustes foram gravados em chaves de registro do sistema.
$ehAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $ehAdmin) {
    Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

$resp = Read-Host "Desfazer os ajustes de segurança? Digite S e ENTER"
if ($resp -notmatch '^[sS]') { exit }

# Reverte exatamente as 2 chaves de registro que o aplicar_seguranca.ps1 gravou (passos 2 e 3 dele).
Set-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\AutoplayHandlers' 'DisableAutoplay' 0
Remove-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer' 'NoDriveTypeAutoRun'
Set-ItemProperty 'HKCU:\Software\Microsoft\Clipboard' 'EnableClipboardHistory' 1

Write-Host "Ajustes desfeitos (a Integridade da Memória e o Secure Boot você desliga pelas mesmas telas, se quiser)." -ForegroundColor Green
Read-Host "ENTER para fechar"
