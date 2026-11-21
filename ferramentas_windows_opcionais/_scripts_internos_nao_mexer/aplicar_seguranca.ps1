# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
# ============================================================================
#  Aplicar ajustes de segurança (mantém o Avast)
#  - Cria ponto de restauração antes de mudar qualquer coisa
#  - Desativa reprodução automática de pendrives
#  - Desativa histórico da área de transferência (Win+V)
#  - Abre a tela de Integridade da Memória (você liga com 1 clique)
#  - Mostra o modelo da placa-mãe para o passo do Secure Boot
#  Para desfazer: execute 3 - DESFAZER os ajustes de seguranca.bat
# ============================================================================
$ErrorActionPreference = 'Stop'

$ehAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $ehAdmin) {
    Write-Host "Pedindo permissão de administrador..." -ForegroundColor Cyan
    Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

function Passo([string]$t) { Write-Host ""; Write-Host ">> $t" -ForegroundColor White }
function Ok([string]$t)    { Write-Host "   [OK] $t" -ForegroundColor Green }
function Aviso([string]$t) { Write-Host "   [!] $t" -ForegroundColor Yellow }

function Definir-Reg([string]$Caminho, [string]$Nome, $Valor, [string]$Tipo = 'DWord') {
    if (-not (Test-Path $Caminho)) { New-Item -Path $Caminho -Force | Out-Null }
    New-ItemProperty -Path $Caminho -Name $Nome -Value $Valor -PropertyType $Tipo -Force | Out-Null
}

Clear-Host
Write-Host "AJUSTES DE SEGURANÇA DO WINDOWS" -ForegroundColor White
Write-Host ""
Write-Host "Este script vai:" -ForegroundColor Cyan
Write-Host "  1. Criar um ponto de restauração do sistema"
Write-Host "  2. Desativar a reprodução automática de pendrives e CDs"
Write-Host "  3. Desativar o histórico da área de transferência (Win+V)"
Write-Host "  4. Abrir a tela de Integridade da Memória (você liga com 1 clique)"
Write-Host "  5. Mostrar o modelo da placa-mãe (para ativar o Secure Boot na BIOS)"
Write-Host ""
Write-Host "O Avast NÃO será alterado." -ForegroundColor Cyan
Write-Host ""
$resp = Read-Host "Digite S e aperte ENTER para continuar (qualquer outra tecla cancela)"
if ($resp -notmatch '^[sS]') { Write-Host "Cancelado. Nada foi alterado."; Read-Host "ENTER para fechar"; exit }

# ---------------------------------------------------------------------------
Passo "1. Ponto de restauração"
try {
    Enable-ComputerRestore -Drive "$env:SystemDrive\" -ErrorAction SilentlyContinue
    Checkpoint-Computer -Description "Antes dos ajustes de seguranca" -RestorePointType MODIFY_SETTINGS
    Ok "ponto de restauração criado"
} catch {
    Aviso "não foi possível criar agora (o Windows só permite 1 por dia). Continuando — os ajustes são simples e reversíveis com 3 - DESFAZER os ajustes de seguranca.bat"
}

# ---------------------------------------------------------------------------
Passo "2. Reprodução automática de pendrives"
try {
    Definir-Reg 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\AutoplayHandlers' 'DisableAutoplay' 1
    Definir-Reg 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer' 'NoDriveTypeAutoRun' 255
    Ok "desativada (pendrives não executam nada sozinhos ao conectar)"
} catch { Aviso "falhou: $($_.Exception.Message)" }

# ---------------------------------------------------------------------------
Passo "3. Histórico da área de transferência"
try {
    Definir-Reg 'HKCU:\Software\Microsoft\Clipboard' 'EnableClipboardHistory' 0
    Definir-Reg 'HKCU:\Software\Microsoft\Clipboard' 'EnableCloudClipboard' 0
    Ok "histórico (Win+V) e sincronização na nuvem desativados"
} catch { Aviso "falhou: $($_.Exception.Message)" }

# ---------------------------------------------------------------------------
Passo "4. Integridade da Memória (proteção contra keyloggers no núcleo)"
Write-Host "   Vou abrir a tela de Isolamento de Núcleo." -ForegroundColor Cyan
Write-Host "   -> Ligue a chave 'Integridade da memória' e reinicie o computador quando o Windows pedir."
Write-Host "   -> Se aparecer 'drivers incompatíveis', clique para ver a lista e me envie os nomes."
Start-Process "windowsdefender://coreisolation"

# ---------------------------------------------------------------------------
Passo "5. Secure Boot (é ativado na BIOS, não pelo Windows)"
$placa = Get-CimInstance Win32_BaseBoard
$bios = Get-CimInstance Win32_BIOS
$pc = Get-CimInstance Win32_ComputerSystem
Write-Host "   Fabricante do PC : $($pc.Manufacturer) $($pc.Model)"
Write-Host "   Placa-mãe        : $($placa.Manufacturer) $($placa.Product)"
Write-Host "   BIOS             : $($bios.Manufacturer) versão $($bios.SMBIOSBIOSVersion)"
Write-Host "   -> Envie essas 3 linhas para receber o passo a passo exato do Secure Boot." -ForegroundColor Cyan

$desk = [Environment]::GetFolderPath('Desktop')
$info = "PC: $($pc.Manufacturer) $($pc.Model)`r`nPlaca-mae: $($placa.Manufacturer) $($placa.Product)`r`nBIOS: $($bios.Manufacturer) $($bios.SMBIOSBIOSVersion)`r`n"
[IO.File]::WriteAllText((Join-Path $desk 'modelo_placa_mae.txt'), $info, (New-Object System.Text.UTF8Encoding($true)))
Write-Host "   (também salvo em Área de Trabalho\modelo_placa_mae.txt)"

# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "================ CONCLUÍDO ================" -ForegroundColor Green
Write-Host "Faça logoff/login ou reinicie para tudo valer."
Write-Host "Depois rode o 1 - VERIFICAR a seguranca do Windows - so le, nao altera.bat de novo para conferir."
Write-Host "Para desfazer estes ajustes: 3 - DESFAZER os ajustes de seguranca.bat"
Write-Host ""
Read-Host "Pressione ENTER para fechar"
