# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
# ============================================================================
#  Verificação do NÚCLEO do Windows (drivers e inicialização) — SOMENTE LEITURA
#  Procura sinais de rootkit: drivers sem assinatura, de fabricante desconhecido,
#  em pastas estranhas, ou inicialização do Windows com proteções desligadas.
#  Relatório salvo em: Área de Trabalho\relatorio_nucleo.txt
# ============================================================================
$ErrorActionPreference = 'SilentlyContinue'

$ehAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $ehAdmin) {
    Write-Host "Pedindo permissão de administrador (só para LER)..." -ForegroundColor Cyan
    Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

$linhas = New-Object System.Collections.Generic.List[string]
function Saida([string]$t, [string]$cor = 'Gray') { Write-Host $t -ForegroundColor $cor; $linhas.Add($t) }
$alertas = 0

Clear-Host
Saida "VERIFICAÇÃO DO NÚCLEO DO WINDOWS (somente leitura) - $(Get-Date -Format 'dd/MM/yyyy HH:mm')" 'White'

# ---------------------------------------------------------------------------
Saida "" ; Saida "=== 1. CONFIGURAÇÃO DE INICIALIZAÇÃO (rootkits costumam mexer aqui) ===" 'White'
$bcd = (bcdedit /enum '{current}' 2>$null) -join "`n"
$checks = @(
    @{ Nome = 'Modo de teste de assinatura (testsigning)'; Padrao = '(?im)^testsigning\s+(Yes|Sim)'; Expl = 'permite carregar drivers SEM assinatura' },
    @{ Nome = 'Verificação de integridade desligada (nointegritychecks)'; Padrao = '(?im)^nointegritychecks\s+(Yes|Sim)'; Expl = 'desliga a checagem de drivers' },
    @{ Nome = 'Depurador de kernel ligado (debug)'; Padrao = '(?im)^debug\s+(Yes|Sim)'; Expl = 'permite controlar o núcleo por fora' }
)
if (-not $bcd) {
    Saida "[INFO] não foi possível ler a configuração de inicialização" 'Cyan'
} else {
    foreach ($c in $checks) {
        if ($bcd -match $c.Padrao) { Saida "[ALERTA] $($c.Nome): LIGADO — $($c.Expl)" 'Red'; $alertas++ }
        else { Saida "[  OK  ] $($c.Nome): desligado" 'Green' }
    }
}
try {
    if (Confirm-SecureBootUEFI -ErrorAction Stop) { Saida "[  OK  ] Secure Boot: ligado" 'Green' }
    else { Saida "[ATENÇÃO] Secure Boot: desligado (ative na BIOS)" 'Yellow' }
} catch { Saida "[ATENÇÃO] Secure Boot: não suportado/legado" 'Yellow' }

$ci = Get-CimInstance -Namespace root\Microsoft\Windows\DeviceGuard -ClassName Win32_DeviceGuard
if ($ci -and ($ci.SecurityServicesRunning -contains 2)) { Saida "[  OK  ] Integridade da memória: ligada" 'Green' }
else { Saida "[ATENÇÃO] Integridade da memória: desligada" 'Yellow' }

# ---------------------------------------------------------------------------
Saida "" ; Saida "=== 2. DRIVERS CARREGADOS NO NÚCLEO ===" 'White'
Saida "Verificando assinatura digital de cada driver (pode levar 1-2 minutos)..." 'Cyan'

$drivers = Get-CimInstance Win32_SystemDriver | Where-Object { $_.State -eq 'Running' }
$total = 0; $microsoft = 0
$terceiros = @(); $suspeitos = @(); $foraPadrao = @()

foreach ($d in $drivers) {
    $total++
    $caminho = $d.PathName
    if (-not $caminho) { continue }
    $caminho = $caminho.Trim('"')
    $caminho = $caminho -replace '^\\\?\?\\', ''
    $caminho = $caminho -replace '^\\SystemRoot\\', "$env:SystemRoot\"
    $caminho = $caminho -replace '(?i)^system32\\', "$env:SystemRoot\System32\"

    if (-not (Test-Path -LiteralPath $caminho)) {
        $suspeitos += [pscustomobject]@{ Nome = $d.Name; Caminho = $caminho; Motivo = 'arquivo do driver não encontrado no disco (driver "fantasma")'; Assinante = '' }
        continue
    }
    $sig = Get-AuthenticodeSignature -LiteralPath $caminho
    $assinante = ''
    if ($sig.SignerCertificate) { $assinante = ($sig.SignerCertificate.Subject -replace '^CN=', '' -split ',')[0].Trim('"') }

    $pastaNormal = $caminho -match '(?i)\\Windows\\System32\\(drivers|DriverStore)\\' -or $caminho -match '(?i)\\Windows\\System32\\[^\\]+\.sys$'

    if ($sig.Status -ne 'Valid') {
        if ($assinante -match 'Microsoft') { $microsoft++; continue }
        $suspeitos += [pscustomobject]@{ Nome = $d.Name; Caminho = $caminho; Motivo = "assinatura: $($sig.Status)"; Assinante = $assinante }
    } elseif ($assinante -match 'Microsoft') {
        $microsoft++
    } else {
        $terceiros += [pscustomobject]@{ Nome = $d.Name; Descricao = $d.DisplayName; Assinante = $assinante; Caminho = $caminho }
        if (-not $pastaNormal) {
            $foraPadrao += [pscustomobject]@{ Nome = $d.Name; Caminho = $caminho; Assinante = $assinante }
        }
    }
}

Saida "Drivers rodando no núcleo: $total  (Microsoft: $microsoft | outros fabricantes: $($terceiros.Count))"

Saida "" ; Saida "--- Drivers de OUTROS fabricantes (confira se reconhece) ---" 'White'
foreach ($t in ($terceiros | Sort-Object Assinante)) {
    Saida ("  {0,-28} {1}" -f $t.Assinante, "$($t.Nome) — $($t.Descricao)")
}

Saida "" ; Saida "--- Drivers SUSPEITOS ---" 'White'
$suspReais = @($suspeitos | Where-Object { $_.Motivo -notlike 'arquivo do driver*' -or $_.Caminho -notmatch '(?i)\\Windows\\' })
$fantasmas = @($suspeitos | Where-Object { $_.Motivo -like 'arquivo do driver*' -and $_.Caminho -match '(?i)\\Windows\\' })
if ($suspReais.Count -eq 0) {
    Saida "[  OK  ] Nenhum driver sem assinatura ou em local estranho." 'Green'
} else {
    foreach ($s in $suspReais) {
        Saida "[ALERTA] $($s.Nome)" 'Red'
        Saida "         Motivo: $($s.Motivo)" 'Red'
        Saida "         Arquivo: $($s.Caminho)" 'Red'
        if ($s.Assinante) { Saida "         Assinado por: $($s.Assinante)" 'Red' }
        $alertas++
    }
}
if ($foraPadrao.Count -gt 0) {
    Saida "[VERIFICAR] Drivers ASSINADOS, mas fora da pasta padrão (comum em anti-cheat de jogos e alguns programas):" 'Yellow'
    foreach ($f in $foraPadrao) { Saida "         $($f.Nome) — $($f.Assinante) — $($f.Caminho)" 'Yellow' }
}
if ($fantasmas.Count -gt 0) {
    Saida "[ INFO ] $($fantasmas.Count) driver(s) do Windows com caminho que o script não conseguiu ler (normal em alguns drivers internos):" 'Cyan'
    foreach ($f in $fantasmas) { Saida "         $($f.Nome)" 'Cyan' }
}

# ---------------------------------------------------------------------------
Saida "" ; Saida "=== 3. SERVIÇOS DE NÚCLEO OCULTOS ===" 'White'
# Drivers registrados para iniciar no boot/sistema que não aparecem na lista de drivers carregados
$regDrv = Get-ChildItem 'HKLM:\SYSTEM\CurrentControlSet\Services' | ForEach-Object {
    $p = Get-ItemProperty $_.PSPath
    if (($p.Type -eq 1 -or $p.Type -eq 2) -and ($p.Start -eq 0 -or $p.Start -eq 1)) {
        [pscustomobject]@{ Nome = $_.PSChildName; Imagem = $p.ImagePath }
    }
}
$nomesCarregados = @(Get-CimInstance Win32_SystemDriver | Select-Object -ExpandProperty Name)
$ocultos = @($regDrv | Where-Object { $nomesCarregados -notcontains $_.Nome -and $_.Imagem })
$ocultosExistentes = @()
foreach ($o in $ocultos) {
    $img = ($o.Imagem -replace '^\\SystemRoot\\', "$env:SystemRoot\") -replace '(?i)^system32\\', "$env:SystemRoot\System32\"
    $img = $img -replace '^\\\?\?\\', ''
    if (Test-Path -LiteralPath $img) {
        $s = Get-AuthenticodeSignature -LiteralPath $img
        $ass = ''
        if ($s.SignerCertificate) { $ass = ($s.SignerCertificate.Subject -replace '^CN=', '' -split ',')[0] }
        if ($ass -notmatch 'Microsoft') { $ocultosExistentes += [pscustomobject]@{ Nome = $o.Nome; Imagem = $img; Assinante = $ass; Status = $s.Status } }
    }
}
if ($ocultosExistentes.Count -eq 0) {
    Saida "[  OK  ] Nenhum driver de terceiros escondido da lista oficial." 'Green'
} else {
    foreach ($o in $ocultosExistentes) {
        $cor = 'Yellow'
        if ($o.Status -ne 'Valid') { $cor = 'Red'; $alertas++ }
        Saida "[VERIFICAR] $($o.Nome) — $($o.Imagem) — assinado por: $($o.Assinante) ($($o.Status))" $cor
    }
    Saida "  (Drivers de inicialização registrados mas não listados. Pode ser normal para drivers desativados de programas instalados.)" 'DarkGray'
}

# ---------------------------------------------------------------------------
Saida "" ; Saida "=== RESULTADO ===" 'White'
if ($alertas -eq 0) {
    Saida "Nenhum sinal de rootkit encontrado nesta verificação." 'Green'
} else {
    Saida "$alertas ALERTA(S) encontrado(s). Envie o relatório para análise ANTES de apagar qualquer coisa." 'Red'
}
Saida "Complete com a Verificação na Inicialização do Avast (detecta rootkits antes do Windows carregar)." 'Cyan'

$desk = [Environment]::GetFolderPath('Desktop')
$arq = Join-Path $desk 'relatorio_nucleo.txt'
[IO.File]::WriteAllText($arq, ($linhas -join "`r`n"), (New-Object System.Text.UTF8Encoding($true)))
Write-Host ""
Write-Host "Relatório salvo em: $arq" -ForegroundColor Cyan
Write-Host "Nada foi alterado no computador." -ForegroundColor Cyan
Read-Host "Pressione ENTER para fechar"
