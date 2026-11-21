# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
# ============================================================================
#  Verificação de segurança do Windows — SOMENTE LEITURA (não altera nada)
#  Gera relatório na tela e salva uma cópia em: Área de Trabalho\relatorio_seguranca.txt
# ============================================================================
$ErrorActionPreference = 'SilentlyContinue'

# --- Executar como administrador (necessário para ler TPM, Secure Boot, SMB etc.) ---
$ehAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $ehAdmin) {
    Write-Host "Pedindo permissão de administrador (só para LER as configurações)..." -ForegroundColor Cyan
    Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

$global:Relatorio = @()

function Registrar([string]$Area, [string]$Nome, [string]$Status, [string]$Detalhe, [string]$Correcao = '') {
    switch ($Status) {
        'OK'      { $cor = 'Green';  $rot = '[  OK   ]' }
        'ATENCAO' { $cor = 'Yellow'; $rot = '[ATENÇÃO]' }
        'RISCO'   { $cor = 'Red';    $rot = '[ RISCO ]' }
        default   { $cor = 'Cyan';   $rot = '[ INFO  ]' }
    }
    Write-Host $rot -ForegroundColor $cor -NoNewline
    Write-Host " $Nome — $Detalhe"
    if ($Correcao -and $Status -ne 'OK') {
        Write-Host "            Como corrigir: $Correcao" -ForegroundColor DarkGray
    }
    $global:Relatorio += [pscustomobject]@{ Area = $Area; Item = $Nome; Status = $Status; Detalhe = $Detalhe; Correcao = $Correcao }
}

function Ler-Reg([string]$Caminho, [string]$Nome) {
    try { return (Get-ItemProperty -Path $Caminho -Name $Nome -ErrorAction Stop).$Nome } catch { return $null }
}

function Titulo([string]$t) {
    Write-Host ""
    Write-Host ("=== " + $t + " ===") -ForegroundColor White
}

Clear-Host
Write-Host "VERIFICAÇÃO DE SEGURANÇA DO WINDOWS (somente leitura)" -ForegroundColor White
Write-Host ("Computador: " + $env:COMPUTERNAME + "   Data: " + (Get-Date -Format 'dd/MM/yyyy HH:mm'))

# ---------------------------------------------------------------------------
Titulo "SISTEMA"
$so = Get-CimInstance Win32_OperatingSystem
$build = [int]$so.BuildNumber
Registrar 'Sistema' 'Versão do Windows' 'INFO' ("$($so.Caption) (build $build)")
if ($build -ge 19041) {
    Registrar 'Sistema' 'Proteção do cofre contra print' 'OK' 'Windows suporta esconder a janela de prints e gravações'
} else {
    Registrar 'Sistema' 'Proteção do cofre contra print' 'RISCO' 'Windows antigo: a janela do cofre NÃO fica oculta em prints' 'Atualize para Windows 10 versão 2004 ou mais novo / Windows 11'
}

$hf = Get-HotFix | Where-Object { $_.InstalledOn } | Sort-Object InstalledOn -Descending | Select-Object -First 1
if ($hf) {
    $dias = [int]((Get-Date) - $hf.InstalledOn).TotalDays
    if ($dias -le 40) {
        Registrar 'Sistema' 'Windows Update' 'OK' "última atualização instalada há $dias dia(s)"
    } else {
        Registrar 'Sistema' 'Windows Update' 'ATENCAO' "última atualização instalada há $dias dias" 'Configurações > Windows Update > Verificar atualizações'
    }
} else {
    Registrar 'Sistema' 'Windows Update' 'INFO' 'não foi possível ler a data da última atualização' 'Confira em Configurações > Windows Update'
}

# ---------------------------------------------------------------------------
Titulo "ANTIVÍRUS (Windows Defender)"
$outros = Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct
if ($outros) {
    Registrar 'Antivírus' 'Antivírus registrados' 'INFO' (($outros | ForEach-Object { $_.displayName }) -join ', ')
}
$mp = Get-MpComputerStatus
if (-not $mp) {
    Registrar 'Antivírus' 'Windows Defender' 'ATENCAO' 'não respondeu (pode estar desligado ou substituído por outro antivírus)' 'Abra Segurança do Windows e confira o antivírus ativo'
} else {
    if ($mp.AntivirusEnabled -and $mp.AMServiceEnabled) { Registrar 'Antivírus' 'Defender ativo' 'OK' 'serviço e antivírus ligados' }
    else { Registrar 'Antivírus' 'Defender ativo' 'RISCO' 'antivírus desligado' 'Segurança do Windows > Proteção contra vírus e ameaças' }

    if ($mp.RealTimeProtectionEnabled) { Registrar 'Antivírus' 'Proteção em tempo real' 'OK' 'ligada' }
    else { Registrar 'Antivírus' 'Proteção em tempo real' 'RISCO' 'DESLIGADA' 'Segurança do Windows > Proteção contra vírus e ameaças > Gerenciar configurações' }

    if ($mp.BehaviorMonitorEnabled) { Registrar 'Antivírus' 'Monitoramento de comportamento' 'OK' 'ligado (detecta keyloggers e espiões pelo que fazem)' }
    else { Registrar 'Antivírus' 'Monitoramento de comportamento' 'RISCO' 'desligado' 'Religue a proteção em tempo real' }

    if ($mp.IsTamperProtected) { Registrar 'Antivírus' 'Proteção contra adulteração' 'OK' 'ligada (vírus não conseguem desligar o Defender)' }
    else { Registrar 'Antivírus' 'Proteção contra adulteração' 'ATENCAO' 'desligada' 'Segurança do Windows > Proteção contra vírus e ameaças > Gerenciar configurações > Proteção contra adulterações' }

    $idade = $mp.AntivirusSignatureAge
    if ($idade -le 3) { Registrar 'Antivírus' 'Base de vírus' 'OK' "atualizada (há $idade dia(s))" }
    else { Registrar 'Antivírus' 'Base de vírus' 'ATENCAO' "desatualizada há $idade dias" 'Segurança do Windows > Proteção contra vírus e ameaças > Atualizações de proteção' }

    $data = $mp.QuickScanEndTime
    if ($data) { Registrar 'Antivírus' 'Última verificação rápida' 'INFO' ($data.ToString('dd/MM/yyyy HH:mm')) }
}
$pref = Get-MpPreference
if ($pref) {
    if ($pref.MAPSReporting -gt 0) { Registrar 'Antivírus' 'Proteção na nuvem' 'OK' 'ligada (detecção de ameaças novas)' }
    else { Registrar 'Antivírus' 'Proteção na nuvem' 'ATENCAO' 'desligada' 'Gerenciar configurações > Proteção fornecida na nuvem' }

    if ($pref.PUAProtection -eq 1) { Registrar 'Antivírus' 'Bloqueio de apps potencialmente indesejados' 'OK' 'ligado' }
    else { Registrar 'Antivírus' 'Bloqueio de apps potencialmente indesejados' 'ATENCAO' 'desligado' 'Controle de aplicativos e navegador > Proteção baseada em reputação > Bloqueio de aplicativos potencialmente indesejados' }

    if ($pref.EnableNetworkProtection -eq 1) { Registrar 'Antivírus' 'Proteção de rede' 'OK' 'ligada' }
    else { Registrar 'Antivírus' 'Proteção de rede' 'INFO' 'desligada (opcional; bloqueia sites maliciosos em qualquer programa)' }

    if ($pref.EnableControlledFolderAccess -eq 1) { Registrar 'Antivírus' 'Acesso controlado a pastas (anti-ransomware)' 'OK' 'ligado' }
    else { Registrar 'Antivírus' 'Acesso controlado a pastas (anti-ransomware)' 'INFO' 'desligado (opcional)' 'Proteção contra vírus e ameaças > Proteção contra ransomware' }
}

# ---------------------------------------------------------------------------
Titulo "ISOLAMENTO DE NÚCLEO / HARDWARE"
$dg = Get-CimInstance -Namespace root\Microsoft\Windows\DeviceGuard -ClassName Win32_DeviceGuard
if ($dg) {
    if ($dg.SecurityServicesRunning -contains 2) { Registrar 'Núcleo' 'Integridade da memória (HVCI)' 'OK' 'ligada (bloqueia espiões no núcleo do Windows)' }
    else { Registrar 'Núcleo' 'Integridade da memória (HVCI)' 'RISCO' 'desligada' 'Segurança do Windows > Segurança do dispositivo > Isolamento de núcleo > Integridade da memória (reinicie)' }

    if ($dg.VirtualizationBasedSecurityStatus -eq 2) { Registrar 'Núcleo' 'Segurança baseada em virtualização' 'OK' 'em execução' }
    else { Registrar 'Núcleo' 'Segurança baseada em virtualização' 'INFO' 'não está em execução (depende do processador/BIOS)' }

    if ($dg.SecurityServicesRunning -contains 1) { Registrar 'Núcleo' 'Credential Guard' 'OK' 'ligado (protege senhas do Windows na memória)' }
    else { Registrar 'Núcleo' 'Credential Guard' 'INFO' 'desligado (comum em Windows Home)' }
} else {
    Registrar 'Núcleo' 'Integridade da memória (HVCI)' 'INFO' 'não foi possível ler' 'Confira em Segurança do dispositivo > Isolamento de núcleo'
}

$lsa = Ler-Reg 'HKLM:\SYSTEM\CurrentControlSet\Control\Lsa' 'RunAsPPL'
if ($lsa -eq 1 -or $lsa -eq 2) { Registrar 'Núcleo' 'Proteção da Autoridade de Segurança Local (LSA)' 'OK' 'ligada' }
else { Registrar 'Núcleo' 'Proteção da Autoridade de Segurança Local (LSA)' 'ATENCAO' 'desligada (protege senhas do Windows contra roubo)' 'Segurança do dispositivo > Isolamento de núcleo > Proteção da Autoridade de Segurança Local' }

try {
    if (Confirm-SecureBootUEFI -ErrorAction Stop) { Registrar 'Hardware' 'Secure Boot' 'OK' 'ligado (impede vírus de inicialização)' }
    else { Registrar 'Hardware' 'Secure Boot' 'ATENCAO' 'desligado' 'Ativar na BIOS/UEFI do computador' }
} catch {
    Registrar 'Hardware' 'Secure Boot' 'ATENCAO' 'não suportado ou BIOS em modo legado' 'Verifique a BIOS (modo UEFI + Secure Boot)'
}

$tpm = Get-Tpm
if ($tpm -and $tpm.TpmPresent) {
    if ($tpm.TpmReady) { Registrar 'Hardware' 'Chip TPM' 'OK' 'presente e pronto (necessário para BitLocker no futuro)' }
    else { Registrar 'Hardware' 'Chip TPM' 'ATENCAO' 'presente, mas não está pronto' 'Execute tpm.msc ou ative na BIOS' }
} else {
    Registrar 'Hardware' 'Chip TPM' 'INFO' 'não encontrado (BitLocker do PC ficaria limitado)' 'Alguns PCs têm o TPM desligado na BIOS (fTPM / PTT)'
}

# ---------------------------------------------------------------------------
Titulo "REDE E ACESSO REMOTO"
$fw = Get-NetFirewallProfile
foreach ($p in $fw) {
    if ($p.Enabled) { Registrar 'Rede' "Firewall ($($p.Name))" 'OK' 'ligado' }
    else { Registrar 'Rede' "Firewall ($($p.Name))" 'RISCO' 'DESLIGADO' 'Segurança do Windows > Firewall e proteção de rede' }
}

$rdp = Ler-Reg 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server' 'fDenyTSConnections'
if ($rdp -eq 1) { Registrar 'Rede' 'Área de Trabalho Remota' 'OK' 'desativada (ninguém acessa o PC remotamente por ela)' }
else { Registrar 'Rede' 'Área de Trabalho Remota' 'ATENCAO' 'ATIVADA — permite acesso remoto ao PC' 'Configurações > Sistema > Área de Trabalho Remota > Desativar (se não usa)' }

$ra = Ler-Reg 'HKLM:\SYSTEM\CurrentControlSet\Control\Remote Assistance' 'fAllowToGetHelp'
if ($ra -eq 0) { Registrar 'Rede' 'Assistência Remota' 'OK' 'desativada' }
else { Registrar 'Rede' 'Assistência Remota' 'ATENCAO' 'ativada' 'Painel de Controle > Sistema > Configurações remotas > desmarcar "Permitir conexões de Assistência Remota"' }

$smb = Get-SmbServerConfiguration
if ($smb) {
    if (-not $smb.EnableSMB1Protocol) { Registrar 'Rede' 'SMBv1 (protocolo antigo, usado pelo WannaCry)' 'OK' 'desativado' }
    else { Registrar 'Rede' 'SMBv1 (protocolo antigo, usado pelo WannaCry)' 'RISCO' 'ATIVADO' 'Recursos do Windows > desmarcar "Suporte para Compartilhamento de Arquivos SMB 1.0/CIFS"' }
}

$remotos = 'TeamViewer','AnyDesk','rustdesk','UltraViewer_Desktop','UltraViewer_Service','ScreenConnect.ClientService',
           'remoting_host','LogMeIn','SRService','Supremo','AeroAdmin','tvnserver','winvnc','vncserver','Splashtop'
$achados = Get-Process | Where-Object { $remotos -contains $_.ProcessName } | Select-Object -ExpandProperty ProcessName -Unique
if ($achados) {
    Registrar 'Rede' 'Programas de acesso remoto RODANDO' 'ATENCAO' ($achados -join ', ') 'Se você não reconhece ou não usa, feche e desinstale. Feche-os antes de abrir o cofre.'
} else {
    Registrar 'Rede' 'Programas de acesso remoto rodando' 'OK' 'nenhum encontrado (TeamViewer, AnyDesk, UltraViewer, VNC...)'
}

# ---------------------------------------------------------------------------
Titulo "CONTA E PROTEÇÕES DO USUÁRIO"
$uac = Ler-Reg 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' 'EnableLUA'
$uacNivel = Ler-Reg 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' 'ConsentPromptBehaviorAdmin'
if ($uac -eq 1) {
    if ($uacNivel -eq 2) { Registrar 'Conta' 'Controle de Conta de Usuário (UAC)' 'OK' 'ligado no nível máximo (Sempre notificar)' }
    else { Registrar 'Conta' 'Controle de Conta de Usuário (UAC)' 'OK' 'ligado (para mais segurança use "Sempre notificar")' }
} else {
    Registrar 'Conta' 'Controle de Conta de Usuário (UAC)' 'RISCO' 'DESLIGADO — programas ganham poder de administrador sem perguntar' 'Pesquise "UAC" no menu Iniciar e suba a barra'
}

$convidado = Get-LocalUser | Where-Object { $_.SID -like '*-501' }
if ($convidado -and $convidado.Enabled) { Registrar 'Conta' 'Conta Convidado' 'RISCO' 'ativada' 'Desative a conta Convidado' }
else { Registrar 'Conta' 'Conta Convidado' 'OK' 'desativada' }

$admPadrao = Get-LocalUser | Where-Object { $_.SID -like '*-500' }
if ($admPadrao -and $admPadrao.Enabled) { Registrar 'Conta' 'Administrador interno do Windows' 'ATENCAO' 'ativado (alvo comum de ataques)' 'Desative se não usa: lusrmgr.msc' }
else { Registrar 'Conta' 'Administrador interno do Windows' 'OK' 'desativado' }

$ss = Ler-Reg 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer' 'SmartScreenEnabled'
$ssPol = Ler-Reg 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\System' 'EnableSmartScreen'
if ($ss -eq 'Off' -or $ssPol -eq 0) { Registrar 'Conta' 'SmartScreen (bloqueio de programas suspeitos)' 'RISCO' 'desligado' 'Controle de aplicativos e navegador > Proteção baseada em reputação' }
else { Registrar 'Conta' 'SmartScreen (bloqueio de programas suspeitos)' 'OK' 'ligado' }

$sac = Ler-Reg 'HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy' 'VerifiedAndReputablePolicyState'
if ($sac -ne $null) {
    switch ($sac) {
        1 { Registrar 'Conta' 'Controle Inteligente de Aplicativos' 'OK' 'ligado (só deixa rodar programas confiáveis)' }
        2 { Registrar 'Conta' 'Controle Inteligente de Aplicativos' 'INFO' 'em avaliação (o Windows decide se liga)' }
        default { Registrar 'Conta' 'Controle Inteligente de Aplicativos' 'INFO' 'desligado (no Windows 11 só religa reinstalando o Windows)' }
    }
}

$autoplay = Ler-Reg 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\AutoplayHandlers' 'DisableAutoplay'
if ($autoplay -eq 1) { Registrar 'Conta' 'Reprodução automática de pendrives' 'OK' 'desativada' }
else { Registrar 'Conta' 'Reprodução automática de pendrives' 'ATENCAO' 'ativada (pendrive infectado pode agir ao conectar)' 'Configurações > Bluetooth e dispositivos > Reprodução Automática > Desativar' }

$bloqTela = Ler-Reg 'HKCU:\Control Panel\Desktop' 'ScreenSaverIsSecure'
$tempoPol = Ler-Reg 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' 'InactivityTimeoutSecs'
if ($bloqTela -eq '1' -or ($tempoPol -gt 0)) { Registrar 'Conta' 'Bloqueio automático da tela' 'OK' 'configurado' }
else { Registrar 'Conta' 'Bloqueio automático da tela' 'INFO' 'não identificado (use Windows+L ao sair do PC)' 'Configurações > Contas > Opções de entrada > Bloqueio dinâmico, ou proteção de tela com "Ao reiniciar, exibir tela de logon"' }

# ---------------------------------------------------------------------------
Titulo "ÁREA DE TRANSFERÊNCIA E TECLADO"
$hist = Ler-Reg 'HKCU:\Software\Microsoft\Clipboard' 'EnableClipboardHistory'
if ($hist -eq 1) { Registrar 'Teclado' 'Histórico da área de transferência (Win+V)' 'INFO' 'ligado — o cofre já se exclui dele, mas senhas copiadas de OUTROS lugares ficam salvas' 'Configurações > Sistema > Área de transferência > Histórico (desligar)' }
else { Registrar 'Teclado' 'Histórico da área de transferência (Win+V)' 'OK' 'desligado' }

$nuvem = Ler-Reg 'HKCU:\Software\Microsoft\Clipboard' 'EnableCloudClipboard'
if ($nuvem -eq 1) { Registrar 'Teclado' 'Sincronizar área de transferência na nuvem' 'ATENCAO' 'ligado (o que você copia vai para a conta Microsoft)' 'Configurações > Sistema > Área de transferência > Compartilhar entre dispositivos (desligar)' }
else { Registrar 'Teclado' 'Sincronizar área de transferência na nuvem' 'OK' 'desligado' }

$ks = (Test-Path "${env:ProgramFiles(x86)}\KeyScrambler") -or (Test-Path "$env:ProgramFiles\KeyScrambler") -or (Get-Process -Name 'KeyScrambler*')
if ($ks) { Registrar 'Teclado' 'KeyScrambler (anti-keylogger)' 'OK' 'instalado' }
else { Registrar 'Teclado' 'KeyScrambler (anti-keylogger)' 'INFO' 'não instalado (opcional)' 'Baixe SOMENTE em qfxsoftware.com' }

$teclados = Get-PnpDevice -Class Keyboard -PresentOnly | Where-Object { $_.Status -eq 'OK' }
$nTec = @($teclados).Count
Registrar 'Teclado' 'Teclados conectados' 'INFO' "$nTec dispositivo(s) de teclado ativo(s) — confira se o cabo do teclado vai DIRETO no PC, sem peça no meio"

# ---------------------------------------------------------------------------
Titulo "COFRE DE SENHAS"
$py = Get-Command python -ErrorAction SilentlyContinue
if ($py -and ($py.Source -notlike '*WindowsApps*')) {
    $ver = (& $py.Source --version 2>&1 | Out-String).Trim()
    Registrar 'Cofre' 'Python' 'OK' "$ver encontrado"
} else {
    Registrar 'Cofre' 'Python' 'INFO' 'não encontrado no PATH (não precisa se for usar o CofreSenhas.exe)'
}
Registrar 'Cofre' 'BitLocker' 'INFO' 'não verificado (você informou que não ativou)'

# ---------------------------------------------------------------------------
Titulo "PROGRAMAS QUE INICIAM COM O WINDOWS (confira se reconhece todos)"
$inicio = Get-CimInstance Win32_StartupCommand | Select-Object -ExpandProperty Name -Unique
foreach ($n in $inicio) { Write-Host "   - $n" }
$global:Relatorio += [pscustomobject]@{ Area = 'Inicialização'; Item = 'Programas'; Status = 'INFO'; Detalhe = ($inicio -join '; '); Correcao = 'Gerenciador de Tarefas > Inicializar: desative o que não reconhecer' }

# ---------------------------------------------------------------------------
$ok = @($global:Relatorio | Where-Object Status -eq 'OK').Count
$at = @($global:Relatorio | Where-Object Status -eq 'ATENCAO').Count
$ri = @($global:Relatorio | Where-Object Status -eq 'RISCO').Count
Write-Host ""
Write-Host "================ RESUMO ================" -ForegroundColor White
Write-Host ("  OK: $ok") -ForegroundColor Green
Write-Host ("  ATENÇÃO: $at") -ForegroundColor Yellow
Write-Host ("  RISCO: $ri") -ForegroundColor Red

$desk = [Environment]::GetFolderPath('Desktop')
$arq = Join-Path $desk 'relatorio_seguranca.txt'
$texto = "RELATÓRIO DE SEGURANÇA - $(Get-Date -Format 'dd/MM/yyyy HH:mm')`r`n"
$texto += "OK: $ok | ATENÇÃO: $at | RISCO: $ri`r`n`r`n"
foreach ($r in $global:Relatorio) {
    $texto += "[$($r.Status)] $($r.Area) - $($r.Item): $($r.Detalhe)`r`n"
    if ($r.Correcao -and $r.Status -ne 'OK') { $texto += "      Como corrigir: $($r.Correcao)`r`n" }
}
[IO.File]::WriteAllText($arq, $texto, (New-Object System.Text.UTF8Encoding($true)))
Write-Host ""
Write-Host "Relatório salvo em: $arq" -ForegroundColor Cyan
Write-Host "Nada foi alterado no seu computador. Envie o relatório (ou um print) para análise." -ForegroundColor Cyan
Write-Host ""
Read-Host "Pressione ENTER para fechar"
