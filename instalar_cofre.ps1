# ============================================================================
#  INSTALADOR AUTOMÁTICO DO COFRE DE SENHAS
#  Faz tudo sozinho:
#   1. confere o cofre_senhas.py que está AO LADO deste instalador (SHA-256 digitado por você)
#   2. instala o Python 3.13 se não houver (winget ou python.org, com assinatura e SHA-256 conferidos)
#   3. instala as bibliotecas em versões FIXAS e com hash (pip --require-hashes)
#   4. compila o CofreSenhas.exe (código nativo) DENTRO DO PENDRIVE, a partir de uma pasta limpa
#   5. deixa o .exe no destino escolhido e mostra o SHA-256; ao detectar a instalação antiga em
#      <pendrive>:\CofreSenhas, oferece atualizá-la no mesmo local sem apagar os dados
#  O instalador PERGUNTA onde instalar: (1) pendrive/disco externo, recomendado, ou (2) uma pasta no computador.
#  Em qualquer dos dois a compilação roda DENTRO do destino escolhido (e não em %LOCALAPPDATA%): nada do cofre,
#  nem restos de compilação, vai parar em outro lugar. No pendrive ela é mais lenta (veja os tempos).
#  No pendrive, NADA do cofre fica no disco do Windows (C:): nem a compilação, nem o programa,
#  nem os arquivos que o programa descompacta ao abrir.
#  Reaproveitamento: o ambiente (Python virtual, Zig, ferramentas) é refeito do zero a cada execução, a partir de
#  arquivos conferidos por hash. Só sobrevive entre execuções a pasta _cb_cache (downloads conferidos por hash e o
#  resultado parcial da compilação), para a instalação seguinte ser rápida e para uma falha NÃO recomeçar do zero.
#  Pode ser executado com dois cliques no 1 - INSTALAR O COFRE - compila e instala.bat
# ============================================================================

# ----------------------------------------------------------------------------
#  Funções auxiliares PURAS (sem efeito colateral): são testadas pelo Pester em testes\4_TESTE_so_no_windows\instalador.Tests.ps1.
#  Carregar este arquivo com ". .\instalar_cofre.ps1" só define as funções; não instala nada.
# ----------------------------------------------------------------------------
function Confirmar-PalavraApagar([string]$valor) {
    return $valor -ieq 'APAGAR'
}

function Test-PrefixoSha256([string]$hashCompleto, [string]$digitado) {
    # Confere o que foi digitado (mín. 16 caracteres) com o início do SHA-256 calculado.
    $d = "$digitado".Trim()
    if ($d.Length -lt 16 -or $d -notmatch '^[0-9A-Fa-f]+$') { return $false }
    return ("$hashCompleto").StartsWith($d, [System.StringComparison]::OrdinalIgnoreCase)
}
function Test-ArquiteturaArm([string]$arq) { return ("$arq" -match 'arm64') }
function Get-AvisoSistemaArquivos([string]$fs) {
    # Devolve o texto do aviso, ou '' quando o sistema de arquivos suporta permissões (NTFS/ReFS).
    $f = "$fs".Trim().ToUpper()
    if ($f -in 'NTFS', 'REFS') { return '' }
    if (-not $f) { return 'Não consegui identificar o sistema de arquivos (disco trancado pelo BitLocker?).' }
    return "O pendrive está em $f, que NÃO guarda permissões de arquivo (ACL): qualquer programa ou usuário deste PC pode ler, copiar ou trocar o que está nele."
}
function Get-EspacoLivreBytes([string]$letra, $volumeCim) {
    # Espaço livre da unidade: pelo WMI e, se ele não informar (disco trancado/lento), por [IO.DriveInfo].
    if ($volumeCim -and $volumeCim.FreeSpace) { return [double]$volumeCim.FreeSpace }
    try { return [double]([IO.DriveInfo]::new("$($letra):\").AvailableFreeSpace) } catch { return $null }
}
function Test-EspacoSuficiente($livreBytes, [double]$minimoBytes) {
    # 'ok', 'pouco' ou 'desconhecido'
    if ($null -eq $livreBytes) { return 'desconhecido' }
    if ([double]$livreBytes -lt $minimoBytes) { return 'pouco' }
    return 'ok'
}
function Test-Thumbprint([string]$t) { return ("$t".Trim() -match '^[0-9A-Fa-f]{40}$') }
function Remove-Caminhos([string]$texto) {
    # tira caminhos (C:\..., \\servidor\...) e o nome do usuário de uma mensagem antes de ir para o log
    $r = "$texto" -replace '(?i)[A-Z]:\\[^\s"''<>|]*', '<caminho>' -replace '\\\\[^\s"''<>|]+', '<caminho>'
    if ($env:USERNAME) { $r = $r -replace [regex]::Escape($env:USERNAME), '<usuario>' }
    return $r
}
function Limitar-Arquivo([string]$arq, [int]$maxBytes) {
    # mantém só o final do log quando passa do limite (o mais recente é o que importa)
    try {
        if ((Test-Path -LiteralPath $arq) -and (Get-Item -LiteralPath $arq).Length -gt $maxBytes) {
            $linhas = @(Get-Content -LiteralPath $arq -Encoding UTF8)
            $manter = $linhas[([int]($linhas.Count / 2))..($linhas.Count - 1)]
            Set-Content -LiteralPath $arq -Value $manter -Encoding UTF8
        }
    } catch {}
}
function Add-LogDetalhado([string]$arq, [string[]]$linhas) {
    # Log estruturado (uma linha por fato, 'chave=valor'). Sem caminhos, sem nome de usuário, sem senhas.
    try {
        $carimbo = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss')
        $texto = $linhas | ForEach-Object { "$carimbo $_" }
        Add-Content -LiteralPath $arq -Value $texto -Encoding UTF8 -ErrorAction Stop
        Limitar-Arquivo $arq 300000
    } catch {}
}

# Arquivos do cofre que ficam escondidos e protegidos na pasta (Oculto + Sistema + Somente leitura). Só o
# CofreSenhas.exe (e qualquer .bat, por segurança) continua visível -- é a ÚNICA coisa que deve aparecer na pasta:
# não existe mais nenhum .bat nem .sha256 "ao lado" do programa (versões antigas tinham Abrir_Cofre.bat +
# CofreSenhas.sha256; removidos de propósito -- ver comentário de NOMES_APOIO_FIXOS em cofre_senhas.py). É camada
# de discrição/anti-acidente: quem ligar "mostrar ocultos" ainda vê os arquivos; o conteúdo é protegido pela cifra
# e pelo BitLocker. Mesma lista do programa (arquivos_de_apoio em cofre_senhas.py).
function Nomes-De-Apoio([string]$pasta) {
    try {
        Get-ChildItem -LiteralPath $pasta -Force -ErrorAction Stop | Where-Object {
            $n = $_.Name
            ($n -ne 'CofreSenhas.exe') -and ($n -notlike '*.bat') -and
            ($n -like 'cofre.dat*' -or $n -like 'CofreSenhas*' -or $n -in @('avisos_vistos.json', 'instalacao_detalhada.log', 'logs', 'exigir_ntfs.txt', '.tmp_cofre'))
        }
    } catch { @() }
}
function Revelar-Apoio([string]$pasta) {
    # Tira Oculto/Sistema/Somente leitura (7 = 1+2+4): o instalador precisa gravar por cima dos arquivos.
    $n = 0
    foreach ($i in (Nomes-De-Apoio $pasta)) {
        try { $i.Attributes = [IO.FileAttributes]([int]$i.Attributes -band (-bnot 7)); $n++ } catch {}
    }
    return $n
}
function Ocultar-Apoio([string]$pasta) {
    # Arquivos: Oculto+Sistema+Somente leitura (7). Pastas: Oculto+Sistema (6).
    # Repete cada item até 5x (meio segundo entre tentativas): o antivírus costuma travar por um instante
    # um .exe RECÉM-ESCRITO para escaneá-lo, e nesse instante alterar atributos falha (achado real: o usuário
    # viu CofreSenhas.exe/.sha256 ainda visíveis logo depois da instalação terminar). Sem essa espera, uma
    # falha assim ficava silenciosa (o catch{} engolia o erro) e o arquivo nunca mais era escondido.
    $n = 0; $falhou = @()
    foreach ($i in (Nomes-De-Apoio $pasta)) {
        $marca = if ($i.PSIsContainer) { 6 } else { 7 }
        $ok = $false
        for ($t = 0; $t -lt 5 -and -not $ok; $t++) {
            try { $i.Attributes = [IO.FileAttributes]([int]$i.Attributes -bor $marca); $ok = $true }
            catch { Start-Sleep -Milliseconds 500 }
        }
        if ($ok) { $n++ } else { $falhou += $i.Name }
    }
    return @{ n = $n; falhou = $falhou }
}
function Get-InstalacaoLegada([string]$destino) {
    $pasta = Join-Path $destino 'CofreSenhas'
    if (-not (Test-Path -LiteralPath $pasta -PathType Container)) { return $null }
    $itemPasta = Get-Item -LiteralPath $pasta -Force -ErrorAction Stop
    $itens = @(Get-ChildItem -LiteralPath $pasta -Force -File -ErrorAction Stop)
    $nomesPrograma = @('CofreSenhas.exe', 'CofreSenhas-arm64.exe', 'Abrir_Cofre.bat',
                       'CofreSenhas.sha256', 'CofreSenhas-arm64.sha256', 'cofre_senhas.py')
    $programas = @($itens | Where-Object { $_.Name -in $nomesPrograma } | ForEach-Object { $_.Name })
    $cofres = @($itens | Where-Object { $_.Name -like 'cofre.dat*' } | ForEach-Object { $_.Name })
    $chaves = @($itens | Where-Object { $_.Extension -ieq '.key' } | ForEach-Object { $_.Name })
    if ($programas.Count -eq 0 -and $cofres.Count -eq 0 -and $chaves.Count -eq 0) { return $null }
    return [pscustomobject]@{
        Path = $pasta
        Programas = $programas
        Cofres = $cofres
        Chaves = $chaves
        ReparsePoint = [bool]($itemPasta.Attributes -band [IO.FileAttributes]::ReparsePoint)
    }
}
function Remove-ProgramaLegado([string]$pasta) {
    $nomes = @('CofreSenhas.exe', 'CofreSenhas-arm64.exe', 'Abrir_Cofre.bat',
               'CofreSenhas.sha256', 'CofreSenhas-arm64.sha256', 'cofre_senhas.py')
    $removidos = @()
    $falhas = @()
    foreach ($nome in $nomes) {
        $caminho = Join-Path $pasta $nome
        if (-not (Test-Path -LiteralPath $caminho -PathType Leaf)) { continue }
        try {
            Remove-Item -LiteralPath $caminho -Force -ErrorAction Stop
            if (Test-Path -LiteralPath $caminho) { $falhas += $nome }
            else { $removidos += $nome }
        } catch {
            $falhas += "$nome ($($_.Exception.Message))"
        }
    }
    return [pscustomobject]@{ Removidos = @($removidos); Falhas = @($falhas) }
}

function Instalar-Cofre([string]$LetraPedida = '') {
    $ErrorActionPreference = 'Continue'
    $ProgressPreference = 'SilentlyContinue'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    # Nunca deixa __pycache__\ para trás em nenhum Python chamado por este instalador (o teste do passo 4
    # já roda dentro de _cb, que é apagado no fim, mas isso garante que nada escape em nenhum cenário).
    $env:PYTHONDONTWRITEBYTECODE = '1'

    # Título de etapa + BARRA DE PROGRESSO em texto (funciona em qualquer console, mesmo com a saída redirecionada).
    # O título vem como "n/5  Texto": a barra mostra quantas etapas já foram concluídas antes desta.
    function Barra([int]$feitas, [int]$total) {
        $largura = 30
        $pct = [int][math]::Floor(100 * $feitas / [math]::Max(1, $total))
        $cheio = [int][math]::Floor($largura * $feitas / [math]::Max(1, $total))
        Write-Host ("   [{0}{1}] {2}%" -f ('#' * $cheio), ('.' * ($largura - $cheio)), $pct) -ForegroundColor Cyan
    }
    function Etapa([string]$t) {
        Write-Host ""
        $m = [regex]::Match($t, '^(\d+)/(\d+)\s+(.*)$')
        if ($m.Success) {
            $n = [int]$m.Groups[1].Value; $tot = [int]$m.Groups[2].Value
            Barra ([math]::Max(0, $n - 1)) $tot
            if ($n -ge 1) { Write-Host (">> Etapa {0} de {1}: {2}" -f $n, $tot, $m.Groups[3].Value) -ForegroundColor White }
            else          { Write-Host (">> {0}" -f $m.Groups[3].Value) -ForegroundColor White }
        } else { Write-Host ">> $t" -ForegroundColor White }
    }
    function Ok([string]$t)    { Write-Host "   [OK] $t" -ForegroundColor Green }
    function Info([string]$t)  { Write-Host "   $t" -ForegroundColor Gray }
    function Erro([string]$t)  { try { $estadoT.erro = $t } catch {}; Write-Host ""; Write-Host "   [ERRO] $t" -ForegroundColor Red }
    # Separador visual simples: usado para respirar o texto entre blocos de informação e a pergunta que vem a
    # seguir, para não virar uma parede de texto só (achado de usabilidade 2026-11-13: usuário relatou dificuldade
    # de entender a tela por tudo vir grudado -- aqui é só espaçamento/organização, nenhuma pergunta de segurança
    # foi removida nem simplificada).
    function Sep() { Write-Host "   ----------------------------------------------------------------" -ForegroundColor DarkGray }

    # Ambiente limpo: variáveis do Python/pip/compilador de quem chamou não influenciam a compilação
    Get-ChildItem Env: | Where-Object { $_.Name -match '^(PYTHON|PIP_|NUITKA_|CC$|CXX$|CFLAGS$|CXXFLAGS$|CPPFLAGS$|LDFLAGS$)' } |
        ForEach-Object { Remove-Item -LiteralPath "Env:$($_.Name)" -ErrorAction SilentlyContinue }
    # QuickEdit do console: um clique na janela PAUSA toda a saída até você apertar ENTER, o que parece
    # travamento total numa compilação longa. Desligado aqui e RESTAURADO ao terminar (qualquer que seja o motivo).
    $modoConsoleOriginal = $null; $hc = $null
    try {
        Add-Type -Namespace W -Name C -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern IntPtr GetStdHandle(int h);
[DllImport("kernel32.dll")] public static extern bool GetConsoleMode(IntPtr h, out uint m);
[DllImport("kernel32.dll")] public static extern bool SetConsoleMode(IntPtr h, uint m);
'@ -ErrorAction Stop
        $hc = [W.C]::GetStdHandle(-10); $mc = [uint32]0
        if ([W.C]::GetConsoleMode($hc, [ref]$mc)) {
            $modoConsoleOriginal = $mc          # restaurado no 'finally' (o console do usuário volta como estava)
            [void][W.C]::SetConsoleMode($hc, [uint32](($mc -band [uint32]4294967231) -bor [uint32]128))
        }
    } catch {}
    Clear-Host
    Write-Host "INSTALADOR DO COFRE DE SENHAS" -ForegroundColor Cyan
    Write-Host "Não feche esta janela. A 1ª compilação leva de 5 a 20 minutos; as seguintes são bem mais rápidas." -ForegroundColor Cyan
    Write-Host "Se algo falhar, é só rodar de novo: o que já foi baixado e compilado fica guardado e é aproveitado." -ForegroundColor Cyan
    Write-Host "A cada 15 segundos a compilação mostra que está viva (tempo, uso do processador)." -ForegroundColor Cyan
    # MODO TESTE (opt-in, NUNCA ligado por padrão): só existe para testar em máquina virtual/Sandbox descartável,
    # onde quem aperta ENTER e quem "entregou" o arquivo são a MESMA pessoa -- aí as perguntas de segurança (pasta,
    # SIM, SHA-256) não defendem contra ninguém, só atrasam o teste. Numa instalação de verdade (pendrive, PC do
    # usuário) essa variável nunca é definida, então o fluxo todo continua 100% interativo como sempre foi.
    # NUNCA defina COFRE_TESTE_SANDBOX=1 fora de uma VM/Sandbox jogável fora.
    $testeSandbox = ("$env:COFRE_TESTE_SANDBOX" -eq '1')
    if ($testeSandbox) {
        Write-Host ""
        Write-Host "   ======================== MODO TESTE (COFRE_TESTE_SANDBOX=1) ========================" -ForegroundColor Magenta
        Write-Host "   As perguntas de local/pasta/SIM/SHA-256 serão respondidas SOZINHAS (sem pedir nada a você)." -ForegroundColor Magenta
        Write-Host "   Isso só é seguro aqui porque é uma máquina de teste descartável. NUNCA use isto numa instalação real." -ForegroundColor Magenta
        Write-Host "   ======================================================================================" -ForegroundColor Magenta
    }

    # Cronômetro por etapa: a tabela com os tempos aparece no fim (ou quando algo falha)
    $cron = [Diagnostics.Stopwatch]::StartNew()
    $tempos = New-Object System.Collections.ArrayList
    $estadoT = @{ ultimo = 0.0 }
    function Marca([string]$nome) {
        $agora = $cron.Elapsed.TotalSeconds
        [void]$tempos.Add([pscustomobject]@{ Etapa = $nome; Tempo = ('{0:N0} s' -f ($agora - $estadoT.ultimo)) })
        $estadoT.ultimo = $agora
    }
    function Mostrar-Tempos {
        if ($tempos.Count -gt 0) {
            Write-Host ""
            Write-Host "Tempo de cada etapa (total $([math]::Round($cron.Elapsed.TotalMinutes, 1)) min):" -ForegroundColor Cyan
            ($tempos | Format-Table -AutoSize | Out-String).TrimEnd() | Write-Host
        }
    }

    # ------------------------------------------------------------------
    Etapa "0/5  Onde instalar o cofre"
    $sistema = $env:SystemDrive.TrimEnd(':').ToUpper()
    $discos = @(Get-CimInstance Win32_LogicalDisk -ErrorAction SilentlyContinue |
                Where-Object { $_.DeviceID.TrimEnd(':').ToUpper() -ne $sistema -and $_.DriveType -in 2, 3 })
    if ($discos.Count -gt 0) {
        Info "Discos removíveis/externos encontrados neste computador:"
        foreach ($dsk in $discos) {
            $tipo = if ($dsk.DriveType -eq 2) { 'pendrive' } else { 'disco externo/fixo' }
            $livre = if ($dsk.FreeSpace) { '{0:N1} GB livres' -f ($dsk.FreeSpace / 1GB) } else { 'TRANCADO (BitLocker?)' }
            Info "  - $($dsk.DeviceID)  $($dsk.VolumeName)  [$tipo, $livre]"
        }
    } else {
        Info "Nenhum pendrive/disco externo encontrado agora."
    }
    $padrao = if ($discos | Where-Object { $_.DeviceID -eq 'H:' }) { 'H' }
              elseif ($discos | Where-Object { $_.DriveType -eq 2 }) { ($discos | Where-Object { $_.DriveType -eq 2 } | Select-Object -First 1).DeviceID.TrimEnd(':') }
              else { '' }
    if ($LetraPedida) { $padrao = "$LetraPedida".Trim().TrimEnd(':', '\').ToUpper() }   # a letra do .bat é só a SUGESTÃO
    # Sempre pergunta onde instalar: pendrive (recomendado) ou uma pasta no computador.
    $modoPc = $false; $pastaPc = $null
    $onde = ''
    if ($testeSandbox) {
        $onde = '2'
        Info "[MODO TESTE] respondendo sozinho: 2 = NO COMPUTADOR"
    } else {
        for ($q = 0; $q -lt 5 -and $onde -notin '1', '2'; $q++) {
            Write-Host ""
            Sep
            Write-Host "   Onde você quer instalar o cofre?" -ForegroundColor White
            Write-Host ""
            Write-Host "     1 = PORTÁTIL" -ForegroundColor Cyan
            Write-Host "         pendrive ou disco externo. RECOMENDADO: você leva o cofre com você"
            Write-Host "         e protege com BitLocker To Go."
            Write-Host ""
            Write-Host "     2 = NO COMPUTADOR" -ForegroundColor Cyan
            Write-Host "         uma pasta neste PC, trancada pelas permissões do Windows"
            Write-Host "         (só a sua conta acessa)."
            Sep
            $onde = "$(Read-Host '   Digite 1 ou 2  [ENTER = 1, recomendado]')".Trim()
            if (-not $onde) { $onde = '1' }
        }
    }
    if ($onde -notin '1', '2') { Erro "Escolha 1 (pendrive) ou 2 (pasta no computador) e rode de novo."; return }
    $letra = $null
    if ($onde -eq '2') {
        $modoPc = $true
        $padraoPasta = Join-Path $env:USERPROFILE 'CofreSenhas'
        Write-Host ""
        Sep
        Write-Host "   ATENÇÃO - instalação no computador:" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "   A pasta será trancada para a SUA conta do Windows (permissões NTFS)." -ForegroundColor Yellow
        Write-Host "   Quem usar a sua conta, ou tiver acesso ao disco desligado, ainda poderá" -ForegroundColor Yellow
        Write-Host "   copiar o cofre.dat (que continua CIFRADO) e trocar o programa por um falso." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "   Recomendado:" -ForegroundColor Yellow
        Write-Host "     - Ligue o BitLocker no disco" -ForegroundColor Yellow
        Write-Host "     - Use senha forte no Windows" -ForegroundColor Yellow
        Write-Host "     - No cofre, ative 'Computadores autorizados' com o reforço do Windows" -ForegroundColor Yellow
        Write-Host "     - Guarde a chave de acesso (.key) separada, num pendrive à parte" -ForegroundColor Yellow
        Sep
        for ($i = 0; $i -lt 5 -and -not $letra; $i++) {
            # Pasta padrão + confirmação num SÓ passo: um ENTER aceita e já confirma a pasta recomendada (achado de
            # usabilidade 2026-11-13: ter uma pergunta de pasta e DEPOIS uma pergunta "SIM" separada só pra confirmar
            # o mesmo valor padrão era um clique a mais sem ganho de segurança nenhum). Só quando a pessoa digita uma
            # pasta DIFERENTE da padrão é que ainda pede uma confirmação extra (SIM) -- aí sim vale a pena perguntar de
            # novo, porque é um destino que ela escreveu, não um que o próprio instalador sugeriu.
            if ($testeSandbox) {
                $resp = $padraoPasta
                $usouPadrao = $true
                Info "[MODO TESTE] usando a pasta padrão sozinho: $resp"
            } else {
                $resp = "$(Read-Host "   Instalar o cofre em $padraoPasta ? [ENTER = sim / digite outra pasta / N = cancelar]")".Trim().Trim('"')
                if ($resp -match '^[nN]$') { Erro "Cancelado pelo usuário."; return }
                $usouPadrao = (-not $resp)
                if ($usouPadrao) { $resp = $padraoPasta }
            }
            if ($resp -match '^\\\\' -or -not [IO.Path]::IsPathRooted($resp) -or $resp -match '\.\.') { Info "Digite um caminho completo de um disco local, por exemplo: D:\CofreSenhas"; continue }
            $resp = $resp.TrimEnd('\')
            if ($resp.Length -gt 40) { Info "Caminho comprido demais ($($resp.Length) caracteres; máximo 40): a compilação usa muitos subníveis e o Windows limita o caminho. Use uma pasta mais curta."; continue }
            $raizResp = [IO.Path]::GetPathRoot($resp)
            if ($resp.TrimEnd('\') -eq $raizResp.TrimEnd('\')) { Info "Escolha uma PASTA (por exemplo $($raizResp)CofreSenhas), não a raiz do disco."; continue }
            if (-not (Test-Path -LiteralPath $raizResp)) { Info "O disco $raizResp não está acessível."; continue }
            if ($testeSandbox) { Info "[MODO TESTE] confirmando sozinho a instalação em $resp" }
            elseif ($usouPadrao) { Ok "pasta padrão confirmada: $resp" }
            elseif ((Read-Host "   Confirma: digite SIM para instalar em $resp") -ne 'SIM') { Info "Não confirmado. Escolha outra pasta."; continue }
            try { New-Item -ItemType Directory -Path $resp -Force -ErrorAction Stop | Out-Null }
            catch { Info "Não consegui criar a pasta: $($_.Exception.Message)"; continue }
            # Permissões reais do Windows (ACL): só a SUA conta e o SISTEMA acessam a pasta; outras contas recebem "Acesso negado".
            # Os arquivos criados depois herdam isso. Em disco FAT/exFAT não existe ACL: aí o aviso acima continua valendo.
            try {
                $meuSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
                $saidaAcl = & icacls.exe $resp /inheritance:r /grant:r "*${meuSid}:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" 2>&1 | Out-String
                if ($LASTEXITCODE -eq 0) { Ok "pasta trancada: só a sua conta do Windows (e o sistema) acessa $resp" }
                else { Info "aviso: não consegui restringir as permissões da pasta (disco sem NTFS?): $($saidaAcl.Trim())" }
            } catch { Info "aviso: não consegui restringir as permissões da pasta: $($_.Exception.Message)" }
            $pastaPc = $resp
            $letra = $raizResp.Substring(0, 1).ToUpper()
        }
        if (-not $letra) { Erro "Nenhuma pasta válida escolhida."; return }
    }
    for ($i = 0; $i -lt 5 -and -not $letra; $i++) {
        if ($i -eq 0 -and $LetraPedida -and -not $padrao) { $resp = $LetraPedida; Info "pendrive informado: $resp" }
        else {
            $resp = Read-Host "Letra do pendrive onde o cofre vai ficar$(if ($padrao) { " [ENTER = $padrao]" })"
            if (-not $resp) { $resp = $padrao }
        }
        $resp = "$resp".Trim().TrimEnd(':', '\').ToUpper()
        if ($resp -notmatch '^[A-Z]$') { Info "Digite só a letra, por exemplo: H"; continue }
        if ($resp -eq $sistema) { Info "O cofre NUNCA vai para o disco do Windows ($($sistema):). Escolha o pendrive."; continue }
        $dsk = $discos | Where-Object { $_.DeviceID.TrimEnd(':').ToUpper() -eq $resp }
        if (-not $dsk) { Info "$($resp): não é um disco removível/externo desta lista. Escolha uma das letras mostradas acima."; continue }
        if (-not (Test-Path "$($resp):\")) { Info "O disco $($resp): não está acessível. Se tiver BitLocker, desbloqueie-o e digite de novo."; continue }
        if ($dsk.DriveType -ne 2) {
            # SSD portátil aparece como disco fixo: permitido, mas só com confirmação explícita
            Write-Host "   $($resp): é um disco FIXO/externo (não um pendrive). Um SSD portátil serve; um disco interno do PC não." -ForegroundColor Yellow
            if ((Read-Host "   Digite SIM para instalar o cofre em $($resp): mesmo assim") -ne 'SIM') { Info "Não confirmado. Escolha outra letra."; continue }
        }
        $letra = $resp
    }
    if (-not $letra) { Erro "Nenhum pendrive válido escolhido."; return }
    $dskEsc = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$($letra):'" -ErrorAction SilentlyContinue | Select-Object -First 1
    $fsEsc = if ($dskEsc) { "$($dskEsc.FileSystem)" } else { '' }
    $avisoFs = Get-AvisoSistemaArquivos $fsEsc
    if ($avisoFs -and -not $modoPc) {
        Write-Host ""
        Write-Host "   ============================ ATENÇÃO ============================" -ForegroundColor Red
        Write-Host "   $avisoFs" -ForegroundColor Red
        Write-Host "   O cofre.dat é CIFRADO (isso continua valendo), mas o programa (.exe -- a única coisa de fora" -ForegroundColor Yellow
        Write-Host "   dele nesta pasta) poderia ser trocado por um programa falso. O BITLOCKER TO GO É OBRIGATÓRIO neste caso (cifra o" -ForegroundColor Yellow
        Write-Host "   pendrive inteiro quando removido e impede trocar o programa). NTFS é recomendado, mas não substitui o BitLocker." -ForegroundColor Yellow
        Write-Host "   Conferir o SHA-256 anotado em papel antes de abrir o cofre continua sendo a defesa principal." -ForegroundColor Yellow
        Write-Host "   =================================================================" -ForegroundColor Red
        Write-Host ""
    }
    $destino = if ($modoPc) { $pastaPc } else { "$($letra):\" }
    $confirmouVersaoAnterior = $false
    $instalacaoLegada = Get-InstalacaoLegada $destino
    if ($instalacaoLegada) {
        if ($instalacaoLegada.ReparsePoint) {
            Info "Encontrei $($instalacaoLegada.Path), mas ela é um link/junção. Por segurança, não vou atualizar nem apagar o conteúdo dela."
        } else {
            Write-Host ""
            Write-Host "   Encontrei uma versão/pasta antiga em $($instalacaoLegada.Path)." -ForegroundColor Yellow
            if ($instalacaoLegada.Cofres.Count -gt 0 -or $instalacaoLegada.Chaves.Count -gt 0) {
                Write-Host "   Há $($instalacaoLegada.Cofres.Count) arquivo(s) do cofre e $($instalacaoLegada.Chaves.Count) chave(s)." -ForegroundColor Yellow
                Write-Host "   Atualizar não apaga o cofre, os backups nem as chaves; a próxima tela oferece separadamente a opção APAGAR." -ForegroundColor Green
            }
            Write-Host "     1 = ATUALIZAR nessa pasta (ENTER = 1): substitui o programa antigo e mantém os dados"
            Write-Host "     2 = Instalar em $destino e deixar a pasta antiga intacta"
            if ($instalacaoLegada.Programas.Count -gt 0) {
                Write-Host "     3 = Apagar só os arquivos antigos do programa; manter cofre, backups e chaves"
            }
            if ($testeSandbox) {
                $opcaoLegada = '1'
                Info "[MODO TESTE] atualizando no local antigo; dados preservados."
            } else {
                $opcaoLegada = (Read-Host "   Escolha 1, 2 ou 3").Trim()
                if (-not $opcaoLegada) { $opcaoLegada = '1' }
            }
            if ($opcaoLegada -eq '1') {
                $destino = $instalacaoLegada.Path
                $confirmouVersaoAnterior = $true
                [void](Revelar-Apoio $destino)
                Ok "a instalação antiga será atualizada no mesmo local; os arquivos do cofre serão mantidos"
            } elseif ($opcaoLegada -eq '2') {
                Info "A pasta antiga será mantida intacta; o novo programa será instalado em $destino."
            } elseif ($opcaoLegada -eq '3' -and $instalacaoLegada.Programas.Count -gt 0) {
                if (-not $testeSandbox -and -not (Confirmar-PalavraApagar (Read-Host "Para apagar somente o programa antigo, digite APAGAR"))) {
                    Info "Cancelado: a versão antiga, o cofre, os backups e as chaves foram mantidos. Instalação interrompida."
                    return
                }
                [void](Revelar-Apoio $instalacaoLegada.Path)
                $remocao = Remove-ProgramaLegado $instalacaoLegada.Path
                if ($remocao.Falhas.Count -gt 0) {
                    Erro "Não consegui remover todos os arquivos antigos do programa: $($remocao.Falhas -join ', '). Nada do cofre foi apagado."
                    return
                }
                Ok "arquivos antigos do programa removidos; cofre, backups e chaves permanecem em $($instalacaoLegada.Path)"
            } else {
                Erro "Escolha inválida. Nada da instalação antiga foi alterado."
                return
            }
        }
    }
    $exeExistente = Join-Path $destino 'CofreSenhas.exe'
    if (-not $confirmouVersaoAnterior -and (Test-Path -LiteralPath $exeExistente -PathType Leaf)) {
        Write-Host ""
        Write-Host "   Já existe uma versão do programa em $destino." -ForegroundColor Yellow
        Write-Host "   A atualização substituirá somente o CofreSenhas.exe; o cofre e as cópias serão mantidos."
        if (-not $testeSandbox -and (Read-Host "   Continuar e atualizar? [ENTER = sim, N = cancelar]").Trim() -match '^[nN]$') {
            Info "Atualização cancelada; nenhum arquivo existente foi alterado."
            return
        }
        if ($testeSandbox) { Info "[MODO TESTE] confirmando atualização do executável existente." }
    }
    $raizObra = if ($modoPc) { $pastaPc } else { "$($letra):" }
    # Compilação dentro do pendrive, numa pasta de nome CURTO na raiz: o compilador C tem arquivos de nome
    # muito comprido, e caminhos longos passam do limite de 260 caracteres do Windows.
    $base = "$raizObra\_cb"
    $velha = Join-Path $destino '_compilacao'
    if (Test-Path $velha) { Remove-Item $velha -Recurse -Force -ErrorAction SilentlyContinue }
    # A pasta _cb (ambiente virtual, zig.exe, módulos, cópia do fonte) é apagada por inteiro e refeita a cada vez:
    # um .exe, zig.exe ou módulo Python plantado ali nunca é executado nem embutido no programa.
    # O que fica entre execuções está em _cb_cache e só tem o que é conferido por hash (downloads do pip),
    # o cache do compilador (endereçado pelo conteúdo) e o resultado parcial da compilação.
    if (Test-Path $base) {
        Info "Apagando a pasta de compilação anterior ($base): nada dela é reaproveitado..."
        # Achado real (rodada 2026-11-13, Sandbox limpa): logo depois do instalador do Python sair (mesmo após o
        # UAC ser aceito), o processo dele ainda pode levar alguns segundos para soltar o handle de um arquivo
        # dentro de _cb (instalador msi/exe filho ainda finalizando, ou antivírus varrendo o Python recém-instalado).
        # Por isso repete por até ~10s antes de desistir, em vez de falhar na primeira tentativa.
        for ($t = 0; $t -lt 5 -and (Test-Path $base); $t++) {
            Remove-Item $base -Recurse -Force -ErrorAction SilentlyContinue
            if (Test-Path $base) { Start-Sleep -Seconds 2 }
        }
        if (Test-Path $base) { Erro "Não consegui apagar $base (algum programa ainda está usando, mesmo repetindo por alguns segundos). Feche tudo, reinicie o PC e rode de novo."; return }
    }
    try { New-Item -ItemType Directory -Path $base -Force -ErrorAction Stop | Out-Null }
    catch { Erro "Não consegui criar $base : $($_.Exception.Message)"; return }
    # Oculto + Sistema (não só Oculto): assim a pasta só aparece se a pessoa ligar DUAS opções do Explorer
    # ("Mostrar itens ocultos" e também "Mostrar arquivos protegidos do sistema operacional", que quase
    # ninguém liga) - menos coisa de bastidor da compilação exposta na tela para alguém mexer por engano
    # ou tentar adulterar. Isso é só discrição (como os arquivos de apoio do cofre já instalado, ver 5.4);
    # quem souber mostrar arquivos de sistema ainda os vê, e a defesa de verdade continua sendo o
    # BitLocker do pendrive e a conferência de hash de cada arquivo usado na compilação.
    try { $pasta = Get-Item $base -Force; $pasta.Attributes = $pasta.Attributes -bor [IO.FileAttributes]::Hidden -bor [IO.FileAttributes]::System } catch {}
    $cache = "$raizObra\_cb_cache"
    $obra = Join-Path $cache 'obra'
    foreach ($d in 'pip', 'zig', 'nk', 'obra') { try { New-Item -ItemType Directory -Path (Join-Path $cache $d) -Force -ErrorAction Stop | Out-Null } catch {} }
    try { $pc = Get-Item $cache -Force; $pc.Attributes = $pc.Attributes -bor [IO.FileAttributes]::Hidden -bor [IO.FileAttributes]::System } catch {}
    function Limpar-Obra { Get-ChildItem -LiteralPath $obra -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue }
    $logsDir = Join-Path $destino 'logs'
    $log = Join-Path $base 'log.txt'
    $saidaNk = Join-Path $base 'nuitka-saida.txt'
    $erroNk = Join-Path $base 'nuitka-erros.txt'
    $okFinal = $false
    try {   # tudo daqui até o fim: o 'finally' apaga a pasta de compilação e guarda só o LOG no pendrive
    $env:NUITKA_CACHE_DIR = Join-Path $cache 'nk'
    $env:ZIG_GLOBAL_CACHE_DIR = Join-Path $cache 'zig'
    $env:ZIG_LOCAL_CACHE_DIR = Join-Path $cache 'zig\l'
    # arquivos temporários da instalação e da compilação também ficam no pendrive
    $tmp = Join-Path $base 't'
    New-Item -ItemType Directory -Path $tmp -Force | Out-Null
    $env:TEMP = $tmp; $env:TMP = $tmp
    try { Start-Transcript -Path $log -Force | Out-Null } catch {}
    Ok "o cofre vai ficar diretamente em $destino"

    # Já existe um cofre neste destino? Pergunta se MANTÉM (padrão) ou APAGA TUDO para recomeçar do zero.
    # Apagar exige digitar a palavra APAGAR; qualquer outra resposta mantém o cofre. Nada é apagado sem isso.
    if (Test-Path -LiteralPath $destino) { [void](Revelar-Apoio $destino) }   # arquivos de uma instalação anterior estão ocultos e somente leitura: libera para atualizar
    $arqsCofre = @(Get-ChildItem -LiteralPath $destino -Force -File -ErrorAction SilentlyContinue |
                   Where-Object { $_.Name -like 'cofre.dat*' -or $_.Name -eq 'avisos_vistos.json' })
    if ($arqsCofre.Count -gt 0) {
        Write-Host ""
        Write-Host "   Já existe um cofre em $destino ($($arqsCofre.Count) arquivo(s): cofre, cópias de segurança e registro)." -ForegroundColor Yellow
        Write-Host "     1 = MANTER o cofre e só atualizar o programa  (recomendado)"
        Write-Host "     2 = APAGAR TUDO e começar do ZERO: cofre, cópias e registro. NÃO TEM VOLTA." -ForegroundColor Red
        $respZero = Read-Host "   Digite 1 ou 2 [ENTER = 1]"
        if ($respZero.Trim() -eq '2') {
            Write-Host "   Isso apaga TODAS as suas senhas guardadas neste cofre. Se tem backup, ótimo; se não tem, pare agora." -ForegroundColor Red
            $confZero = Read-Host "   Para confirmar digite a palavra APAGAR (qualquer outra coisa mantém o cofre)"
            if (Confirmar-PalavraApagar $confZero) {
                $faltou = @()
                foreach ($arq in $arqsCofre) {
                    try {
                        if ($arq.Length -gt 0 -and $arq.Length -lt 4MB) { [IO.File]::WriteAllBytes($arq.FullName, (New-Object byte[] ([int]$arq.Length))) }   # sobrescreve com zeros
                    } catch {}
                    try { Remove-Item -LiteralPath $arq.FullName -Force -ErrorAction Stop } catch { $faltou += $arq.Name }
                }
                if ($faltou.Count -gt 0) {
                    Erro "Não consegui apagar: $($faltou -join ', '). Feche o cofre (e o antivírus que estiver lendo o pendrive) e rode de novo."
                    return
                }
                Ok "cofre antigo APAGADO: você vai criar um cofre novo, do zero, quando abrir o programa"
            } else { Info "Cancelado: o cofre foi MANTIDO." }
        } else { Info "O cofre atual foi mantido; só o programa será atualizado." }
    }

    # Verificações antes de gastar tempo: espaço, memória, velocidade de escrita do pendrive
    $volume = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$($letra):'" -ErrorAction SilentlyContinue
    $livreBytes = Get-EspacoLivreBytes $letra $volume
    $situacaoEspaco = Test-EspacoSuficiente $livreBytes 3GB
    if ($situacaoEspaco -eq 'pouco') {
        Erro ("Só há {0:N1} GB livres em {1}: (a compilação precisa de pelo menos 3 GB). Libere espaço e rode de novo." -f ($livreBytes / 1GB), $letra)
        return
    } elseif ($situacaoEspaco -eq 'desconhecido') {
        Info "Não consegui medir o espaço livre do pendrive; seguindo (a compilação precisa de pelo menos 3 GB)."
    } else {
        Info ("Espaço livre no pendrive: {0:N1} GB (mínimo 3 GB)" -f ($livreBytes / 1GB))
    }
    $sistemaOp = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
    $ramLivreGB = if ($sistemaOp) { [math]::Round($sistemaOp.FreePhysicalMemory / 1MB, 1) } else { 0 }
    if ($ramLivreGB -gt 0) {
        Info "Memória livre: $ramLivreGB GB"
        if ($ramLivreGB -lt 2) { Write-Host "   [AVISO] Pouca memória livre. Feche o navegador e outros programas pesados, senão a compilação pode falhar." -ForegroundColor Yellow }
    }
    try {
        $arqVel = Join-Path $base 'velocidade.tmp'
        $blocoVel = New-Object byte[] (32MB)
        (New-Object Random).NextBytes($blocoVel)
        $tv = [Diagnostics.Stopwatch]::StartNew()
        $fs = [IO.File]::Create($arqVel); $fs.Write($blocoVel, 0, $blocoVel.Length); $fs.Flush($true); $fs.Dispose()
        $tv.Stop()
        Remove-Item $arqVel -Force -ErrorAction SilentlyContinue
        $mbs = [math]::Round(32 / [math]::Max($tv.Elapsed.TotalSeconds, 0.01), 1)
        Info "Velocidade de escrita do pendrive: cerca de $mbs MB/s"
        if ($mbs -lt 15) {
            Write-Host "   [AVISO] Escrita lenta (abaixo de 15 MB/s): pode ser porta USB 2.0 ou pendrive barato. A compilação grava milhares de" -ForegroundColor Yellow
            Write-Host "           arquivos pequenos e pode levar bem mais de 20 minutos. Se puder, use uma porta USB 3 (azul)." -ForegroundColor Yellow
        }
    } catch {}
    Marca 'Preparação (pendrive, limpeza, verificações)'

    # restos de instalações antigas no disco do Windows
    $antigo = Join-Path $env:SystemDrive 'CofreBuild'
    if ((Test-Path $antigo) -and ((Read-Host "Existe uma pasta antiga de instalação do cofre em $antigo (no disco do Windows). Apagar? [ENTER = sim, N = não]") -notmatch '^[nN]')) {
        Remove-Item $antigo -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path $antigo) { Info "aviso: não consegui apagar $antigo (apague manualmente)." }
        else { Ok "pasta antiga $antigo removida do disco do Windows" }
    }
    $mesa = Join-Path ([Environment]::GetFolderPath('Desktop')) 'CofreSenhas'
    if (Test-Path $mesa) {
        $itens = @(Get-ChildItem $mesa -Force -ErrorAction SilentlyContinue)
        if ($itens | Where-Object { $_.Extension -in '.dat', '.key' }) {
            Write-Host ""
            Write-Host "   ATENÇÃO: há um cofre (.dat) ou chave (.key) em $mesa (disco do Windows)." -ForegroundColor Yellow
            Write-Host "   Ele NÃO foi apagado. Mova-o para o pendrive ($destino) e apague da Área de Trabalho." -ForegroundColor Yellow
        } elseif (-not ($itens | Where-Object { $_.Name -ne 'CofreSenhas.exe' })) {
            Remove-Item $mesa -Recurse -Force -ErrorAction SilentlyContinue
            if (-not (Test-Path $mesa)) { Ok "cópia antiga do programa removida da Área de Trabalho" }
        }
    }

    # ------------------------------------------------------------------
    Etapa "1/5  Conferindo o arquivo cofre_senhas.py"
    # Só o arquivo AO LADO do instalador: nada de procurar em Downloads/Documentos, onde qualquer programa
    # do seu usuário poderia plantar um "cofre" falso para ser compilado.
    $pasta = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
    $fonte = Get-Item -LiteralPath (Join-Path $pasta 'cofre_senhas.py') -ErrorAction SilentlyContinue
    if (-not $fonte) {
        Erro "Não achei o cofre_senhas.py na MESMA pasta do instalador ($pasta). Coloque os dois juntos e rode de novo."
        return
    }
    function Versao-Do-Cofre($arq) {
        $m = Select-String -LiteralPath $arq.FullName -Pattern 'VERSAO_PROGRAMA = "([0-9.]+)"' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($m) { try { return [version]$m.Matches[0].Groups[1].Value } catch {} }
        return [version]'0.0'
    }
    $hashFonteTxt = (Get-FileHash -LiteralPath $fonte.FullName -Algorithm SHA256).Hash
    Write-Host ""
    Sep
    Write-Host "   Arquivo que será compilado:" -ForegroundColor White
    Write-Host "     $($fonte.FullName)" -ForegroundColor Gray
    Write-Host "     Versão: $(Versao-Do-Cofre $fonte)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "   SHA-256 deste arquivo:" -ForegroundColor White
    Write-Host "     $hashFonteTxt" -ForegroundColor Yellow
    Sep
    Write-Host ""
    Write-Host "   Por que confirmar isso:" -ForegroundColor White
    Write-Host "     Esse SHA-256 identifica exatamente o código que vai virar o seu cofre." -ForegroundColor Gray
    Write-Host "     Compare com o que foi informado a você (por quem entregou o arquivo)." -ForegroundColor Gray
    Write-Host ""
    Write-Host "   DICA:" -ForegroundColor White
    Write-Host "     Copie o número da MENSAGEM de quem entregou e COLE aqui (botão direito do mouse)." -ForegroundColor Gray
    Write-Host "     Não copie da tela acima: colar o número calculado pelo próprio arquivo não prova nada." -ForegroundColor Gray
    Write-Host ""
    if ($testeSandbox) {
        $resp = $hashFonteTxt.Substring(0, 16)
        Sep
        Write-Host "   [MODO TESTE] conferência SOZINHA (o próprio script leu o hash acima -- isso NÃO prova nada contra" -ForegroundColor Magenta
        Write-Host "   adulteração; só é aceitável numa VM/Sandbox descartável que você mesmo controla)." -ForegroundColor Magenta
        Sep
    } else {
        Sep
        $resp = "$(Read-Host '   Cole (ou digite) os 16 primeiros caracteres do SHA-256 informado  (obrigatório; N = cancelar)')".Trim()
        Sep
        if ($resp -match '^[nN]?$') { Erro "Cancelado: a conferência do SHA-256 é obrigatória."; return }
    }
    if (-not (Test-PrefixoSha256 $hashFonteTxt $resp)) {
        Erro "O SHA-256 digitado NÃO confere com o arquivo (ou tem menos de 16 caracteres). Pode ser outro arquivo. Nada foi compilado."
        return
    }
    Ok "SHA-256 conferido com o que você informou"
    $conteudo = Get-Content -LiteralPath $fonte.FullName -Raw -Encoding UTF8
    if ($conteudo -notmatch 'class Cofre' -or $conteudo -notmatch 'MAGIC = b"COFRE0[4-9]' -or $conteudo -notmatch 'VERSAO_PROGRAMA = "') {
        Erro "O arquivo $($fonte.FullName) não é a versão atual do cofre. Baixe novamente o cofre_senhas.py."
        return
    }
    # Pasta de compilação SÓ com o fonte: o compilador embute o que estiver ao lado dele (um argon2.py plantado
    # ali iria para dentro do .exe).
    $src = Join-Path $base 'src'
    New-Item -ItemType Directory -Path $src -Force | Out-Null
    $fonteCopia = Join-Path $src 'cofre_senhas.py'
    Copy-Item -LiteralPath $fonte.FullName -Destination $fonteCopia -Force
    function Conferir-Copia {
        $h = (Get-FileHash -LiteralPath $fonteCopia -Algorithm SHA256).Hash
        if ($h -ne $hashFonteTxt) {
            Erro "O arquivo copiado para $src MUDOU depois da conferência do SHA-256 (alguém ou algum programa o alterou). Nada foi compilado."
            return $false
        }
        return $true
    }
    if (-not (Conferir-Copia)) { return }
    # somente leitura logo após a conferência (dificulta troca entre a conferência e a compilação); o hash é refeito antes do compilador
    try { Set-ItemProperty -LiteralPath $fonteCopia -Name IsReadOnly -Value $true -ErrorAction Stop } catch { Info "aviso: não consegui marcar a cópia como somente leitura (a conferência do hash continua valendo)." }
    Ok "usando $($fonte.FullName) (versão $(Versao-Do-Cofre $fonte), modificado em $($fonte.LastWriteTime.ToString('dd/MM/yyyy HH:mm')))"
    $exe = Join-Path $obra 'CofreSenhas.exe'
    $final = Join-Path $destino 'CofreSenhas.exe'
    Marca '1/5 Conferência do cofre_senhas.py'

    # ------------------------------------------------------------------
    Etapa "2/5  Verificando o Python"
    # O build usa Python x64 em todas as máquinas. No Windows ARM64, o x64 roda por emulação; o pacote ARM64
    # de cryptography disponível tem vulnerabilidades corrigidas apenas em versões sem wheel ARM64 publicado.
    $osArq = ''
    try { $osArq = [string][System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture } catch {}
    if (-not $osArq) { $osArq = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE } }
    $hostArm = (Test-ArquiteturaArm $osArq)
    function Achar-Python([string]$exigir) {
        $cands = @()
        $py = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($py) {
            foreach ($v in '3.13', '3.12', '3.11') {
                $exe = & $py.Source "-$v" -c "import sys; print(sys.executable)" 2>$null
                if ($LASTEXITCODE -eq 0 -and $exe) { $cands += $exe.Trim() }
            }
        }
        foreach ($v in '313', '312', '311') {
            $cands += Join-Path $env:LOCALAPPDATA "Programs\Python\Python$v\python.exe"
            $cands += Join-Path $env:LOCALAPPDATA "Programs\Python\Python$v-arm64\python.exe"
            $cands += Join-Path $env:ProgramFiles "Python$v\python.exe"
        }
        $cmd = Get-Command python.exe -All -ErrorAction SilentlyContinue | Where-Object { $_.Source -notlike '*WindowsApps*' }
        foreach ($c in $cmd) { $cands += $c.Source }
        foreach ($c in ($cands | Select-Object -Unique)) {
            if ($c -and (Test-Path -LiteralPath $c)) {
                $r = & $c -I -c "import sys, sysconfig, tkinter; print(sysconfig.get_platform() if (3,11) <= sys.version_info[:2] <= (3,13) else 'x')" 2>$null
                $plataforma = "$r".Trim()
                if ($LASTEXITCODE -eq 0 -and $plataforma -eq 'win-amd64' -and (-not $exigir -or $plataforma -eq $exigir)) { return $c }
            }
        }
        return $null
    }
    # Usa Python x64 também em hosts ARM64 para manter a mesma dependência criptográfica corrigida.
    function Achar-Preferido {
        return Achar-Python 'win-amd64'
    }

    $python = Achar-Preferido
    if (-not $python) {
        $sufixo = 'amd64'
        $shaPython = '5da012101ba2e17113a9a1cd901e9ce1441086f2b7ecb5de06ec94163899a190'
        $instLocal = Join-Path (Join-Path $pasta 'pacotes') "python-3.13.17-$sufixo.exe"
        if (Test-Path -LiteralPath $instLocal) {
            $shaLocal = (Get-FileHash -LiteralPath $instLocal -Algorithm SHA256).Hash
            $sigLocal = Get-AuthenticodeSignature -LiteralPath $instLocal
            if ($shaLocal -ne $shaPython.ToUpper() -or $sigLocal.Status -ne 'Valid' -or $sigLocal.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
                Erro "O instalador local do Python NÃO confere (SHA-256 ou assinatura). Instalação cancelada por segurança."
                return
            }
            Info "Python ausente; usando o instalador verificado de pacotes (modo offline)..."
            $pi = Start-Process -FilePath $instLocal -ArgumentList '/quiet', 'InstallAllUsers=0', 'PrependPath=1', 'Include_tcltk=1', 'Include_launcher=1', 'Include_pip=1', 'Include_test=0' -PassThru
            if (-not $pi.WaitForExit(600000)) { try { $pi.Kill() } catch {}; Info "A instalação do Python passou de 10 minutos e foi interrompida." }
            $python = Achar-Preferido
        }
        if (-not $python) {
            Info "Python 3.13 não encontrado. Instalando (pode aparecer um pedido de permissão do Windows)..."
            $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
            if ($winget) {
                # Tempo limite de 5 min: o winget pode ficar esperando uma janela de permissão (UAC) escondida atrás desta
                Info "Se aparecer (ou piscar na barra de tarefas) um pedido de permissão do Windows, aceite. Esperando até 5 minutos..."
                try {
                    $pw = Start-Process -FilePath $winget.Source -ArgumentList 'install', '-e', '--id', 'Python.Python.3.13', '--scope', 'user', '--silent', '--accept-package-agreements', '--accept-source-agreements' -PassThru -NoNewWindow
                    if (-not $pw.WaitForExit(300000)) {
                        try { $pw.Kill() } catch {}
                        Info "O winget não terminou em 5 minutos (provável janela de permissão escondida). Seguindo para o download direto."
                    }
                } catch { Info "winget indisponível: $($_.Exception.Message)" }
            }
            $python = Achar-Preferido
            if (-not $python) {
                Info "Baixando o instalador oficial em python.org..."
                # 3.13.17: última versão 3.13 com instalador para Windows (as seguintes só têm código-fonte)
                $url = "https://www.python.org/ftp/python/3.13.17/python-3.13.17-$sufixo.exe"
                $inst = Join-Path $base "python-3.13.17-$sufixo.exe"
                $baixou = $false
                for ($t = 1; $t -le 3 -and -not $baixou; $t++) {
                    try { Invoke-WebRequest -Uri $url -OutFile $inst -UseBasicParsing -TimeoutSec 300; $baixou = $true }
                    catch { Info "Download do Python falhou (tentativa $t de 3): $($_.Exception.Message)"; if ($t -lt 3) { Start-Sleep -Seconds (5 * $t) } }
                }
                if (-not $baixou) { Erro "Não consegui baixar o Python depois de 3 tentativas. Verifique a internet e rode de novo."; return }
                $shaBaixado = (Get-FileHash -LiteralPath $inst -Algorithm SHA256).Hash
                $sig = Get-AuthenticodeSignature -LiteralPath $inst
                if ($shaBaixado -ne $shaPython.ToUpper() -or $sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
                    Remove-Item $inst -Force -ErrorAction SilentlyContinue
                    Erro "O instalador baixado NÃO confere (SHA-256 ou assinatura da Python Software Foundation). Instalação cancelada por segurança."
                    return
                }
                Ok "instalador do Python: SHA-256 e assinatura oficial verificados"
                $pi = Start-Process -FilePath $inst -ArgumentList '/quiet', 'InstallAllUsers=0', 'PrependPath=1', 'Include_tcltk=1', 'Include_launcher=1', 'Include_pip=1', 'Include_test=0' -PassThru
                if (-not $pi.WaitForExit(600000)) { try { $pi.Kill() } catch {}; Info "A instalação do Python passou de 10 minutos e foi interrompida." }
                Remove-Item $inst -Force -ErrorAction SilentlyContinue
                $python = Achar-Preferido
            }
        }
        if (-not $python) {
            Erro "Não foi possível instalar o Python automaticamente. Instale pelo site python.org (marque 'Add python.exe to PATH') e rode este instalador de novo."
            return
        }
    }
    $versao = (& $python -I --version 2>&1 | Out-String).Trim()
    Ok "$versao em $python"
    $plat = (& $python -I -c "import sysconfig; print(sysconfig.get_platform())" 2>$null | Out-String).Trim()
    if ($plat -ne 'win-amd64') { Erro "Este build requer Python x64 (win-amd64); no Windows ARM64, use o x64 sob emulação."; return }
    $arq = 'amd64'
    # O nome do programa é SEMPRE CofreSenhas.exe (sem sufixo de arquitetura nem arquivo nenhum ao lado dele):
    # reinstalar numa outra arquitetura substitui o programa anterior. Não há mais nada "de fora" que precise
    # escolher entre dois arquivos -- o único arquivo fora do cofre.dat nesta pasta é o próprio programa.
    $nomeFinal = 'CofreSenhas.exe'
    $final = Join-Path $destino $nomeFinal
    Info "Arquitetura: programa para $arq (computador: $osArq) -> $nomeFinal"
    if ($hostArm) { Info "Windows ARM64: o programa x64 será executado por emulação; build nativo ARM64 não é suportado." }
    Marca '2/5 Python'

    # ------------------------------------------------------------------
    Etapa "3/5  Instalando as bibliotecas (ambiente isolado, versões fixas, com verificação de hash)"
    # O Python do sistema NÃO é alterado: tudo vai para um ambiente virtual novo dentro do pendrive (_cb\venv).
    # Cada arquivo baixado é conferido contra o hash gravado aqui (pip --require-hashes): se o PyPI ou a rede
    # entregarem qualquer outra coisa, a instalação é recusada. O Zig (compilador C) também vem com versão e hash fixos.
    $venv = Join-Path $base 'venv'
    & $python -I -m venv $venv
    $pyVenv = Join-Path $venv 'Scripts\python.exe'
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pyVenv)) { Erro "Não consegui criar o ambiente isolado em $venv."; return }
    $python = $pyVenv
    $req = Join-Path $base 'req'
    New-Item -ItemType Directory -Path $req -Force | Out-Null
    $reqBin = Join-Path $req 'bibliotecas.txt'
    $reqBuild = Join-Path $req 'montagem.txt'
    $reqNuitka = Join-Path $req 'nuitka.txt'
    $reqZig = Join-Path $req 'zig.txt'
    @'
cryptography==50.0.2 --hash=sha256:7afa5a6602a9f29af1f3a2965f831bae7c9d5d597b7cbb716d41ab3b7d89879c
argon2-cffi==25.1.0 --hash=sha256:fdc8b074db390fccb6eb4a3604ae7231f219aa669a2652e0f20e16ba513d5741
argon2-cffi-bindings==26.1.0 --hash=sha256:2c36ff87b5dfaa477d0bd51e9d7f6abdae7c8955d2983c97419085d842154b3e --hash=sha256:f9c4420a7a864fe1b86ce35befc95b8e39fb852493b81cf798671ddc265de638
openpyxl==3.1.5 --hash=sha256:5282c12b107bffeef825f4617dc029afaf41d0ea60823bbb665ef3079dc79de2
defusedxml==0.7.1 --hash=sha256:a352e7e428770286cc899e2542b6cdaedb2b4953ff269a210103ec58f6198a61
fido2==2.2.1 --hash=sha256:ed397da981b9ab133da6ead7309e41f924b566b749956129efe286fae097749f
ordered-set==4.1.0 --hash=sha256:046e1132c71fcf3330438a539928932caf51ddbc582496833e23de611de14562
zstandard==0.25.0 --hash=sha256:daab68faadb847063d0c56f361a289c4f268706b598afbf9ad113cbe5c38b6b2 --hash=sha256:ffef5a74088f1e09947aecf91011136665152e0b4b359c42be3373897fb39b01 --hash=sha256:1f830a0dac88719af0ae43b8b2d6aef487d437036468ef3c2ea59c51f9d55fd5 --hash=sha256:22a06c5df3751bb7dc67406f5374734ccee8ed37fc5981bf1ad7041831fa1137 --hash=sha256:181eb40e0b6a29b3cd2849f825e0fa34397f649170673d385f3598ae17cca2e9 --hash=sha256:85304a43f4d513f5464ceb938aa02c1e78c2943b29f44a750b48b25ac999a049
cffi==2.1.1 --hash=sha256:42f6930c31dc7f50732c9ae793c2786c7b6b044195967bbdde40bb9be81c4cc0 --hash=sha256:f53e442b08449d42821fa4a4fba000095af9f62742a500f978a9f557ec44339a --hash=sha256:1aa5645c30469b09530c4ebca77ebf8f17618293c58f8549cb1a543a50236e7d --hash=sha256:c7659f22557c5a0bc4855cd635f55edec690cc008a40768527762cb9fb263455 --hash=sha256:7bde5e4cc5c10140859842b9d383af292b22639a4dffb725314baf45968cef80 --hash=sha256:63bbfd5ded17c4840ac07cd8f1c21ba9d9708141f840b324f422f41b207e3973
et-xmlfile==2.0.0 --hash=sha256:7a91720bc756843502c3b7504c77b8fe44217c85c537d85037f0f536151b2caa
pycparser==3.12 --hash=sha256:a076f3f489b39b43ed13563a1dafe42447445bec2e294154ec5c57fcdda4c85e
'@ | Set-Content -Path $reqBin -Encoding ASCII
    @'
setuptools==84.2.1 --hash=sha256:ca140b45d5325a9478f880e351484f62fef15f336462e449ca0c03c873d589c2
wheel==0.48.0 --hash=sha256:3217dcc807155e45db462d7ef2431f5ddda0d7273b700d05a67b271ceb1287ab
'@ | Set-Content -Path $reqBuild -Encoding ASCII
    @'
nuitka==4.3.5 --hash=sha256:ca1dabc274b95efa7a46597f464ec27484b30f32cb89872d14d66541284d4f01
'@ | Set-Content -Path $reqNuitka -Encoding ASCII
    @'
ziglang==0.16.0 --hash=sha256:089a16a4eb5a2f45151993342f8fabad24ff1a0723dc146642895c29208a3939 --hash=sha256:e44a5271f7b72f7980017bb615823ed52e765f96b6482d93a2fd338cd53101bf
'@ | Set-Content -Path $reqZig -Encoding ASCII
    # --cache-dir: os arquivos baixados ficam em _cb_cache\pip (e continuam sendo conferidos por hash a cada uso).
    $pip = @('-I', '-m', 'pip', 'install', '--progress-bar', 'off', '--disable-pip-version-check', '--isolated', '--require-hashes', '--no-deps',
             '--retries', '5', '--timeout', '60', '--cache-dir', (Join-Path $cache 'pip'))
    function Pip-Tentar([string[]]$resto, [string]$oque) {
        for ($t = 1; $t -le 3; $t++) {
            & $python @pip @resto | Out-Host
            if ($LASTEXITCODE -eq 0) { return $true }
            if ($t -lt 3) { Info "Falhou ao instalar $oque (tentativa $t de 3). Tentando de novo em $(5 * $t) s; o que já foi baixado fica guardado..."; Start-Sleep -Seconds (5 * $t) }
        }
        return $false
    }
    # Pasta 'pacotes' (ao lado deste instalador): instalação SEM internet. Os arquivos continuam sendo conferidos por hash.
    $pacotes = Join-Path $pasta 'pacotes'
    if ("$env:COFRE_BAIXAR_PACOTES" -eq '1') {
        # Modo 'baixar pacotes': só baixa (com hash conferido) tudo o que a instalação usa para a pasta 'pacotes' e termina.
        Info "Baixando os pacotes para a pasta 'pacotes' (depois a instalação funciona SEM internet, neste tipo de computador)..."
        New-Item -ItemType Directory -Path $pacotes -Force | Out-Null
        if (-not (Pip-Tentar @('--only-binary=:all:', '-r', $reqBuild) 'as ferramentas de montagem')) { Erro "Falha ao preparar o download."; return }
        foreach ($par in @(@($reqBin, '--only-binary=:all:'), @($reqBuild, '--only-binary=:all:'), @($reqZig, '--only-binary=:all:'), @($reqNuitka, '--no-build-isolation'))) {
            & $python -I -m pip download --disable-pip-version-check --isolated --require-hashes --no-deps --retries 5 --timeout 60 -d $pacotes $par[1] -r $par[0] | Out-Host
            if ($LASTEXITCODE -ne 0) { Erro "Falha ao baixar os pacotes (veja as mensagens acima). Verifique a internet e rode de novo."; return }
        }
        $nPac = @(Get-ChildItem -LiteralPath $pacotes -File -ErrorAction SilentlyContinue).Count
        Ok "$nPac arquivo(s) guardados em $pacotes. Agora o 1 - INSTALAR O COFRE - compila e instala.bat funciona sem internet (precisa do Python 3.13 já instalado)."
        $okFinal = $true
        return
    }
    function Testar-Pacotes-Offline([string]$arquivo, [string[]]$opcoes) {
        $argumentos = @(
            '-I', '-m', 'pip', 'install', '--dry-run', '--disable-pip-version-check',
            '--isolated', '--no-index', '--find-links', $pacotes, '--require-hashes', '--no-deps'
        ) + $opcoes + @('-r', $arquivo)
        $saidaTeste = & $python @argumentos 2>&1
        if ($LASTEXITCODE -eq 0) { return $true }
        foreach ($linha in ($saidaTeste | Select-Object -Last 3)) {
            Info "Wheelhouse: $linha"
        }
        return $false
    }

    $offlineCompleto = $false
    if (Test-Path -LiteralPath $pacotes) {
        $offlineCompleto = (Testar-Pacotes-Offline $reqBin @('--only-binary=:all:')) `
            -and (Testar-Pacotes-Offline $reqBuild @('--only-binary=:all:')) `
            -and (Testar-Pacotes-Offline $reqNuitka @('--no-build-isolation')) `
            -and (Testar-Pacotes-Offline $reqZig @('--only-binary=:all:'))
    }
    if ($offlineCompleto) {
        $pip += @('--no-index', '--find-links', $pacotes)
        Info "Modo OFFLINE: todos os pacotes exigidos foram encontrados e conferidos em 'pacotes'."
    } elseif (Test-Path -LiteralPath $pacotes) {
        Info "Wheelhouse incompleto para esta arquitetura/Python; continuarei com o indice online."
    }
    if (-not (Pip-Tentar @('--only-binary=:all:', '-r', $reqBin) 'as bibliotecas')) { Erro "Falha ao instalar as bibliotecas (veja as mensagens acima). Verifique a internet e rode de novo: o que já baixou fica guardado."; return }
    # ferramentas de montagem do Nuitka (que só existe como código-fonte), também com hash; sem baixar nada na montagem
    if (-not (Pip-Tentar @('--only-binary=:all:', '-r', $reqBuild) 'as ferramentas de montagem')) { Erro "Falha ao instalar as ferramentas de montagem."; return }
    if (-not (Pip-Tentar @('--no-build-isolation', '-r', $reqNuitka) 'o compilador Nuitka')) { Erro "Falha ao instalar o compilador Nuitka (veja as mensagens acima)."; return }
    $zdir = Join-Path $base 'z'
    if (-not (Pip-Tentar @('--only-binary=:all:', '--target', $zdir, '-r', $reqZig) 'o compilador C (Zig)')) { Erro "Falha ao instalar o compilador C (Zig)."; return }
    $zigExe = Join-Path $zdir 'ziglang\zig.exe'
    if (-not (Test-Path -LiteralPath $zigExe)) { Erro "O zig.exe não foi encontrado em $zdir."; return }
    $env:PATH = (Split-Path $zigExe) + ';' + $env:PATH        # o Nuitka usa o zig que está no PATH (e não baixa outro)
    & $python -I -c "import cryptography, argon2, openpyxl, defusedxml, fido2, tkinter, nuitka" 2>$null
    if ($LASTEXITCODE -ne 0) { Erro "As bibliotecas não carregaram corretamente."; return }
    Ok "ambiente isolado pronto (Zig $((& $zigExe version 2>&1 | Out-String).Trim()))"
    Marca '3/5 Ambiente isolado e bibliotecas'

    # ------------------------------------------------------------------
    Etapa "4/5  Testando o cofre antes de compilar"
    if (-not (Conferir-Copia)) { return }
    Push-Location $base
    $arqTeste = Join-Path $tmp 'teste_cofre.dat'
    & $python -I -c "import sys; sys.path.insert(0, sys.argv[1]); import cofre_senhas as c; p=sys.argv[2]; v=c.Cofre.criar(p,'frase de teste bem longa 123',3,0,'alto'); assert c.Cofre.abrir(p,senha='frase de teste bem longa 123'); c.destruir(p); print('ok')" $src $arqTeste
    if ($LASTEXITCODE -ne 0) { Pop-Location; Erro "O teste do cofre falhou (veja as mensagens acima)."; return }
    Ok "criptografia funcionando neste computador"
    Marca '4/5 Teste do cofre'

    # ------------------------------------------------------------------
    Etapa "5/5  Compilando o CofreSenhas.exe (5 a 20 minutos)"
    Info "Tudo acontece dentro do pendrive, por isso pode demorar um pouco mais."
    # Um ajuste no compilador (não muda o programa gerado): ele cria um 'scons-debug.bat' só para depuração;
    # o Avast bloqueia .bat e a compilação quebra.
    $patch = Join-Path $base 'ajustar_compilador.py'
    @'
import re
def ajustar(caminho, achar, trocar, marca):
    t = open(caminho, encoding="utf-8").read()
    if marca in t:
        return "ja"
    m = re.search(achar, t, re.M)
    if not m:
        return "nao"
    t = t[:m.start()] + trocar(m) + t[m.end():]
    open(caminho, "w", encoding="utf-8").write(t)
    return "ok"
try:
    import nuitka.build.SconsInterface as S
    a = ajustar(S.__file__, r"^def _createSconsDebugScript\([^)]*\):[^\n]*\n",
                lambda m: m.group(0) + "    return  # desativado pelo instalador do cofre (antivirus bloqueia .bat)\n",
                "# desativado pelo instalador do cofre")
except Exception:
    a = "nao"
print(a)
'@ | Set-Content -Path $patch -Encoding ASCII
    $r = "$(& $python -I $patch)".Trim()
    Remove-Item $patch -Force -ErrorAction SilentlyContinue
    $nuitkaVer = (& $python -I -m nuitka --version 2>&1 | Select-Object -First 1 | Out-String).Trim()
    Info "Compilador: Nuitka $nuitkaVer (remendo anti-bloqueio=$r)"
    if ($r -in 'ok', 'ja') { Ok "ajuste anti-bloqueio do antivírus aplicado no compilador" }
    else { Info "aviso: não consegui aplicar o ajuste anti-bloqueio do compilador; seguindo assim mesmo." }
    Info "Se o compilador tentar baixar alguma coisa, a compilação falha de propósito (nada é baixado sem verificação)."
    Info "O aviso do Nuitka sobre '{PROGRAM_BASE}' é esperado (é o que mantém tudo no pendrive)."
    # Ícone do programa (gerado aqui, sem baixar nada) + dados do arquivo (nome, versão): o .exe não sai com o ícone do Python
    $ico = Join-Path $base 'cofre.ico'
    [IO.File]::WriteAllBytes($ico, [Convert]::FromBase64String('AAABAAMAEBAAAAEAIABoBAAANgAAACAgAAABACAAqBAAAJ4EAAAwMAAAAQAgAKglAABGFQAAKAAAABAAAAAgAAAAAQAgAAAAAABABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOpRWkDqUVpA6lFaQOpRWkDqUVpA6lFaQOpRWkDqUVpA6lFaQOpRWkAAAAAAAAAAAAAAAAAAAAAA6lFaMOpRWt/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa3+pRWjAAAAAAAAAAAOpRWt/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVrfAAAAAOpRWkDqUVr/6lFa/+pRWv/vfIP/9Kis//SorP/0qKz/9Kis//SorP/0qKz/73yD/+pRWv/qUVr/6lFa/+pRWkDqUVpA6lFa/+pRWv/qUVr/9Kis/////////////vT1//709f////////////SorP/qUVr/6lFa/+pRWv/qUVpA6lFaQOpRWv/qUVr/6lFa//SorP////////////azt//2s7f////////////0qKz/6lFa/+pRWv/qUVr/6lFaQOpRWkDqUVr/6lFa/+pRWv/0qKz////////////rXGT/61xk////////////9Kis/+pRWv/qUVr/6lFa/+pRWkDqUVpA6lFa/+pRWv/qUVr/9Kis////////////+97g//ve4P////////////SorP/qUVr/6lFa/+pRWv/qUVpA6lFaQOpRWv/qUVr/6lFa//SorP/73uD/73yD/+98g//vfIP/73yD//ve4P/0qKz/6lFa/+pRWv/qUVr/6lFaQOpRWkDqUVr/6lFa/+pRWv/xh47//////+5yef/qUVr/6lFa/+5yef//////8YeO/+pRWv/qUVr/6lFa/+pRWkDqUVpA6lFa/+pRWv/qUVr/6lFa//rU1v/+9PX/9Kis//SorP/+9PX/+tTW/+pRWv/qUVr/6lFa/+pRWv/qUVpA6lFaQOpRWv/qUVr/6lFa/+pRWv/rXGT/9Kis//rU1v/61Nb/9Kis/+tcZP/qUVr/6lFa/+pRWv/qUVr/6lFaQOpRWkDqUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWkAAAAAA6lFa3+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWt8AAAAAAAAAAOpRWjDqUVrf6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWt/qUVowAAAAAAAAAAAAAAAAAAAAAOpRWkDqUVpA6lFaQOpRWkDqUVpA6lFaQOpRWkDqUVpA6lFaQOpRWkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAKAAAACAAAABAAAAAAQAgAAAAAACAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADqUVog6lFacOpRWq/qUVq/6lFav+pRWr/qUVq/6lFav+pRWr/qUVq/6lFav+pRWr/qUVq/6lFav+pRWr/qUVq/6lFav+pRWr/qUVq/6lFar+pRWnDqUVogAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADqUVoQ6lFaj+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVqP6lFaEAAAAAAAAAAAAAAAAAAAAAAAAAAA6lFaEOpRWs/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVrP6lFaEAAAAAAAAAAAAAAAAAAAAADqUVqP6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVqPAAAAAAAAAAAAAAAA6lFaIOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVogAAAAAAAAAADqUVpw6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWnAAAAAAAAAAAOpRWq/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr////////////////////////////////////////////////////////////////////////////qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFarwAAAAAAAAAA6lFav+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv///////////////////////////////////////////////////////////////////////////+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVq/AAAAAAAAAADqUVq/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa//////////////////////////////////rU1v/61Nb/////////////////////////////////6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWr8AAAAAAAAAAOpRWr/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/////////////////////////////////9Kis//SorP/////////////////////////////////qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFavwAAAAAAAAAA6lFav+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv////////////////////////////e+wf/qUVr/6lFa//e+wf///////////////////////////+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVq/AAAAAAAAAADqUVq/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa////////////////////////////7Wdv/+pRWv/qUVr/7Wdv////////////////////////////6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWr8AAAAAAAAAAOpRWr/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr////////////////////////////vfIP/6lFa/+pRWv/vfIP////////////////////////////qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFavwAAAAAAAAAA6lFav+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv////////////////////////////zp6v/ykpj/8pKY//zp6v///////////////////////////+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVq/AAAAAAAAAADqUVq/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa////////////////////////////////////////////////////////////////////////////6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWr8AAAAAAAAAAOpRWr/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr////////////86er/+tTW//rU1v/61Nb/+tTW//rU1v/61Nb/+tTW//rU1v/86er////////////qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFavwAAAAAAAAAA6lFav+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv////////////e+wf/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa//e+wf///////////+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVq/AAAAAAAAAADqUVq/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa//ve4P///////Onq/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr//Onq///////73uD/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWr8AAAAAAAAAAOpRWr/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/852i////////////977B/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa//e+wf////////////Odov/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFavwAAAAAAAAAA6lFav+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/+97g////////////+MnL/+1nb//qUVr/6lFa/+1nb//4ycv////////////73uD/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVq/AAAAAAAAAADqUVq/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/ucnn//vT1/////////////////////////////////////////////vT1/+5yef/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWr8AAAAAAAAAAOpRWr/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/tZ2//+tTW//////////////////////////////////rU1v/tZ2//6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFavwAAAAAAAAAA6lFav+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/7nJ5//SorP/61Nb/+tTW//SorP/ucnn/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVq/AAAAAAAAAADqUVqv6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWq8AAAAAAAAAAOpRWnDqUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFacAAAAAAAAAAA6lFaIOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVogAAAAAAAAAAAAAAAA6lFaj+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFajwAAAAAAAAAAAAAAAAAAAADqUVoQ6lFaz+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWs/qUVoQAAAAAAAAAAAAAAAAAAAAAAAAAADqUVoQ6lFaj+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVqP6lFaEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA6lFaIOpRWnDqUVqv6lFav+pRWr/qUVq/6lFav+pRWr/qUVq/6lFav+pRWr/qUVq/6lFav+pRWr/qUVq/6lFav+pRWr/qUVq/6lFav+pRWq/qUVpw6lFaIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACgAAAAwAAAAYAAAAAEAIAAAAAAAgCUAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOpRWlDqUVqf6lFa3+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa3+pRWp/qUVpQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADqUVpA6lFaz+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFaz+pRWkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOpRWmDqUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVpgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA6lFaYOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFaYAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADqUVpA6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADqUVrP6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWs8AAAAAAAAAAAAAAAAAAAAAAAAAAOpRWlDqUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVpQAAAAAAAAAAAAAAAAAAAAAOpRWp/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVqfAAAAAAAAAAAAAAAAAAAAAOpRWt/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/73yD//SorP/0qKz/9Kis//SorP/0qKz/9Kis//SorP/0qKz/9Kis//SorP/0qKz/9Kis//SorP/0qKz/9Kis//SorP/0qKz/9Kis//SorP/0qKz/73yD/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVrfAAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/9Kis////////////////////////////////////////////////////////////////////////////////////////////////////////////9Kis/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/9Kis////////////////////////////////////////////////////////////////////////////////////////////////////////////9Kis/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/9Kis////////////////////////////////////////////////////////////////////////////////////////////////////////////9Kis/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/9Kis//////////////////////////////////////////////////e+wf/3vsH/////////////////////////////////////////////////9Kis/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/9Kis/////////////////////////////////////////////////+98g//vfIP/////////////////////////////////////////////////9Kis/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/9Kis////////////////////////////////////////////+tTW/+1nb//tZ2//+tTW////////////////////////////////////////////9Kis/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/9Kis///////////////////////////////////////4ycv/6lFa/+pRWv/qUVr/6lFa//jJy///////////////////////////////////////9Kis/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/9Kis///////////////////////////////////////vfIP/6lFa/+pRWv/qUVr/6lFa/+98g///////////////////////////////////////9Kis/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/9Kis///////////////////////////////////////ucnn/6lFa/+pRWv/qUVr/6lFa/+5yef//////////////////////////////////////9Kis/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/9Kis///////////////////////////////////////znaL/6lFa/+pRWv/qUVr/6lFa//Odov//////////////////////////////////////9Kis/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/9Kis///////////////////////////////////////+9PX/8pKY/+pRWv/qUVr/8pKY//709f//////////////////////////////////////9Kis/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/9Kis////////////////////////////////////////////////////////////////////////////////////////////////////////////9Kis/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/9Kis////////////////////////////////////////////////////////////////////////////////////////////////////////////9Kis/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/9Kis////////////////////////////////////////////////////////////////////////////////////////////////////////////9Kis/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/9Kis/////////////////+98g//qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/vfIP/////////////////9Kis/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/9Kis//////////////////SorP/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/0qKz/////////////////9Kis/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/73yD//////////////////ve4P/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/73uD/////////////////73yD/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa//709f/////////////////vfIP/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+98g//////////////////+9PX/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa//SorP/////////////////+9PX/7nJ5/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/7nJ5//709f/////////////////0qKz/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+tcZP/+9PX//////////////////vT1//GHjv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/xh47//vT1//////////////////709f/rXGT/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/xh47////////////////////////////73uD/9Kis//GHjv/xh47/9Kis//ve4P////////////////////////////GHjv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/8pKY////////////////////////////////////////////////////////////////////////////8pKY/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa//GHjv/+9PX///////////////////////////////////////////////////////709f/xh47/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/rXGT/9Kis//709f/////////////////////////////////+9PX/9Kis/+tcZP/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/ucnn/852i//SorP/0qKz/852i/+5yef/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/AAAAAAAAAAAAAAAAAAAAAOpRWt/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVrfAAAAAAAAAAAAAAAAAAAAAOpRWp/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVqfAAAAAAAAAAAAAAAAAAAAAOpRWlDqUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVpQAAAAAAAAAAAAAAAAAAAAAAAAAADqUVrP6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWs8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADqUVpA6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA6lFaYOpRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFaYAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOpRWmDqUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVpgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADqUVpA6lFaz+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFaz+pRWkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOpRWlDqUVqf6lFa3+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa/+pRWv/qUVr/6lFa3+pRWp/qUVpQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='))
    $verTxt = "$(Versao-Do-Cofre $fonte)"
    if ($verTxt -notmatch '^\d+(\.\d+){0,3}$') { $verTxt = '1.0.0.0' }
    # núcleos x memória: cada compilação em paralelo usa ~1 GB
    $nuc = [Environment]::ProcessorCount
    $jobs = [int][math]::Max(1, [math]::Min($nuc, [math]::Floor($(if ($ramLivreGB -gt 0) { $ramLivreGB } else { 2 }) / 1.0)))
    Info "Compilando com $jobs processo(s) em paralelo ($nuc núcleos, $ramLivreGB GB livres)."
    $relato = Join-Path $base 'nuitka-crash-report.xml'
    # última conferência: o arquivo a compilar é exatamente o que você conferiu
    if (-not (Conferir-Copia)) { Pop-Location; return }
    function Q([string]$s) { return '"' + $s + '"' }
    $args_nk = @(
        '-I', '-u', '-m', 'nuitka', '--onefile', '--zig', '--windows-console-mode=disable', '--enable-plugin=tk-inter',
        '--include-package=openpyxl', '--include-package=defusedxml',
        '--include-module=fido2.client.windows', '--include-module=fido2.client.win_api', '--include-package-data=fido2',
        '--onefile-no-compression', '--lto=no', '--python-flag=no_docstrings', "--jobs=$jobs",
        '--onefile-tempdir-spec={PROGRAM_BASE}_em_uso_{PID}_{TIME}',
        '--noinclude-data-files=tcl/tzdata', '--noinclude-data-files=tcl/msgs', '--noinclude-data-files=tk/msgs',
        ('--output-dir=' + (Q $obra)), '--output-filename=CofreSenhas.exe',
        ('--windows-icon-from-ico=' + (Q $ico)),
        '--product-name="Cofre de Senhas"', "--file-version=$verTxt", "--product-version=$verTxt",
        '--file-description="Cofre de Senhas local"', '--company-name="Uso pessoal"',
        (Q $fonteCopia)
    )
    # Compilação incremental: se o Nuitka, o Zig, o Python ou as opções são os mesmos da vez anterior, o que já foi
    # compilado em _cb_cache\obra é reaproveitado (só o que mudou é recompilado). Se algo mudou, começa limpo.
    $zigVer = (& $zigExe version 2>&1 | Out-String).Trim()
    $textoOpcoes = (@($args_nk | Where-Object { "$_" -notlike '--jobs=*' }) -join ' ')
    $chaveObra = "$nuitkaVer|zig $zigVer|$versao|$plat|$textoOpcoes"
    $arqChave = Join-Path $cache 'obra.chave'
    $chaveVelha = if (Test-Path -LiteralPath $arqChave) { "$(Get-Content -LiteralPath $arqChave -Raw -ErrorAction SilentlyContinue)".Trim() } else { '' }
    if ($chaveVelha -eq $chaveObra) {
        if (@(Get-ChildItem -LiteralPath $obra -Force -ErrorAction SilentlyContinue).Count -gt 0) { Info "Reaproveitando a compilação anterior de $obra (só o que mudou é recompilado)." }
    } else {
        if ($chaveVelha) { Info "Compilador, Python ou opções mudaram desde a última vez: compilação limpa." }
        Limpar-Obra
    }
    try { Set-Content -LiteralPath $arqChave -Value $chaveObra -Encoding UTF8 } catch {}
    Remove-Item $saidaNk, $erroNk -Force -ErrorAction SilentlyContinue
    function Cpu-Arvore([int]$raiz) {
        # soma do tempo de CPU do Nuitka e de todos os processos filhos (zig, compilador C...) + quais PIDs existem
        $res = @{ cpu = 0.0; pids = '' }
        try {
            $todos = @(Get-CimInstance Win32_Process -ErrorAction Stop | Select-Object ProcessId, ParentProcessId)
            $ids = New-Object 'System.Collections.Generic.HashSet[int]'
            [void]$ids.Add($raiz)
            $mudou = $true
            while ($mudou) {
                $mudou = $false
                foreach ($p in $todos) { if ($ids.Contains([int]$p.ParentProcessId) -and $ids.Add([int]$p.ProcessId)) { $mudou = $true } }
            }
            foreach ($i in $ids) {
                $pr = Get-Process -Id $i -ErrorAction SilentlyContinue
                if ($pr) { try { $res.cpu += $pr.TotalProcessorTime.TotalSeconds } catch {} }
            }
            $res.pids = (($ids | Sort-Object) -join ',')
        } catch {}
        return $res
    }
    function Novas-Linhas([string]$arq, [hashtable]$pos, [string]$chave) {
        if (-not (Test-Path -LiteralPath $arq)) { return @() }
        try {
            $fs = [IO.File]::Open($arq, 'Open', 'Read', 'ReadWrite')
            try {
                [void]$fs.Seek([long]$pos[$chave], 'Begin')
                $sr = New-Object IO.StreamReader($fs, [Text.Encoding]::UTF8)
                $txt = $sr.ReadToEnd()
                $pos[$chave] = $fs.Position
            } finally { $fs.Dispose() }
            return @($txt -split "\r?\n" | Where-Object { $_.Trim() })
        } catch { return @() }
    }
    $jobsInicial = $jobs
    # Estimativa de tempo restante da Etapa 5, guardada em _cb_cache (sobrevive entre instalações) para virar uma
    # contagem REGRESSIVA em vez de só "tempo decorrido" (pedido do usuário 2026-11-13: mostrar quanto falta,
    # não só quanto já passou). Sem histórico (1ª vez), usa 600s (10 min) como chute inicial, dentro da faixa
    # documentada de 5 a 20 minutos. É só uma estimativa: se passar do previsto, a tela avisa e conta para cima.
    $arqDuracao = Join-Path $cache 'ultima_duracao_s.txt'
    $estimativaS = 600.0
    if (Test-Path -LiteralPath $arqDuracao) {
        try { $v = [double](Get-Content -LiteralPath $arqDuracao -Raw -ErrorAction Stop).Trim(); if ($v -ge 10) { $estimativaS = $v } } catch {}
    }
    $inicioNk = [Diagnostics.Stopwatch]::StartNew()
    for ($tent = 1; $tent -le 3; $tent++) {
    # Até 3 tentativas: a 2ª continua de onde parou (com menos processos, se faltou memória); a 3ª recomeça do zero.
    # Nunca entrega um .exe antigo: o de uma compilação anterior é apagado antes de cada tentativa.
    if (Test-Path -LiteralPath $exe) { Remove-Item -LiteralPath $exe -Force -ErrorAction SilentlyContinue }
    if ($tent -gt 1) {
        $jobs = [int][math]::Max(1, [math]::Floor($jobsInicial / [math]::Pow(2, $tent - 1)))
        $args_nk = @($args_nk | ForEach-Object { if ("$_" -like '--jobs=*') { "--jobs=$jobs" } else { $_ } })
        if ($tent -eq 3) { Info "Tentativa 3 de 3: recomeçando a compilação do zero (os downloads guardados continuam valendo)."; Limpar-Obra }
        else { Info "Tentativa $tent de 3: continuando de onde parou, com $jobs processo(s)." }
    }
    Remove-Item $saidaNk, $erroNk -Force -ErrorAction SilentlyContinue
    $pos = @{ o = 0L; e = 0L }
    $proc = Start-Process -FilePath $python -ArgumentList $args_nk -WorkingDirectory $base -PassThru -NoNewWindow `
        -RedirectStandardOutput $saidaNk -RedirectStandardError $erroNk
    $null = $proc.Handle            # necessário para ler o ExitCode depois
    # Sinal imediato de que o compilador realmente começou a rodar: sem isso, a tela fica muda entre o
    # cabeçalho da Etapa 5 e o primeiro "[vivo]" (que só vinha depois de 15s) - tempo suficiente para
    # parecer travado logo de cara. Achado da sessão de 2026-11-13: usuário reportou "parece ter travado"
    # bem no início da Etapa 5, quando na verdade só não havia nenhum sinal na tela ainda.
    Write-Host "   Compilador iniciado (processo $($proc.Id)). A partir daqui a tela mostra sinal de vida a cada poucos segundos." -ForegroundColor DarkGray
    $melhorCpu = 0.0; $ultimosPids = ''; $semAtividade = 0
    $tique = 0
    $giro = @('.', '..', '...')
    # Texto do "quanto falta" (contagem REGRESSIVA a partir da estimativa $estimativaS; ver comentário lá em
    # cima). Fica positivo e some perto do fim: nenhuma estimativa é exata, então quando passa do previsto
    # troca sozinho para "já passou da estimativa" em vez de mostrar um número negativo sem sentido.
    function Texto-Faltam([double]$decorridoS) {
        $faltam = $estimativaS - $decorridoS
        if ($faltam -gt 5) { "faltam uns {0} min (estimativa)" -f [math]::Ceiling($faltam / 60) }
        else { "já passou da estimativa de $([math]::Round($estimativaS / 60, 1)) min: pode ser a etapa final (mais lenta e muda)" }
    }
    while (-not $proc.WaitForExit(5000)) {
        $tique++
        $decorridoS = $inicioNk.Elapsed.TotalSeconds
        $min = [math]::Floor($inicioNk.Elapsed.TotalMinutes); $seg = $inicioNk.Elapsed.Seconds
        if ($tique % 3 -ne 0) {
            # Pulso leve a cada ~5s: só para garantir que a tela NUNCA fique mais de 5s sem nenhuma linha
            # nova (evita a sensação de travamento). O diagnóstico completo (CPU, saída do Nuitka, detecção
            # de travamento de verdade) continua vindo a cada ~15s, exatamente como antes, logo abaixo.
            Write-Host ("   ainda compilando{0} ({1} min {2:00} s decorridos — {3})" -f $giro[$tique % 3], $min, $seg, (Texto-Faltam $decorridoS)) -ForegroundColor DarkGray
            continue
        }
        $c = Cpu-Arvore $proc.Id
        $ativo = ($c.cpu -gt $melhorCpu + 0.5) -or ($c.pids -ne $ultimosPids)
        if ($c.cpu -gt $melhorCpu) { $melhorCpu = $c.cpu }
        $ultimosPids = $c.pids
        if ($ativo) { $semAtividade = 0 } else { $semAtividade++ }
        foreach ($linha in @((Novas-Linhas $saidaNk $pos 'o') + (Novas-Linhas $erroNk $pos 'e') | Select-Object -Last 25)) { Write-Host "   | $linha" -ForegroundColor DarkGray }
        $estado = if ($semAtividade -ge 40) { 'SEM ATIVIDADE HÁ 10 MIN: provável travamento real (veja o antivírus)' }
                  elseif ($semAtividade -ge 8) { "sem atividade há $([math]::Floor($semAtividade / 4)) min (pode ser a etapa final, que fica muda)" }
                  else { 'trabalhando' }
        $corE = if ($semAtividade -ge 40) { 'Red' } elseif ($semAtividade -ge 8) { 'Yellow' } else { 'Green' }
        Write-Host ("   [vivo] {0} min {1:00} s | CPU do compilador: {2:N0} s | {3} | {4}" -f $min, $seg, $melhorCpu, $estado, (Texto-Faltam $decorridoS)) -ForegroundColor $corE
    }
    foreach ($linha in @((Novas-Linhas $saidaNk $pos 'o') + (Novas-Linhas $erroNk $pos 'e') | Select-Object -Last 60)) { Write-Host "   | $linha" -ForegroundColor DarkGray }
    Info "Nuitka terminou (código $($proc.ExitCode)) em $([math]::Round($inicioNk.Elapsed.TotalMinutes, 1)) min."
    if (Test-Path -LiteralPath $exe) {
        # Guarda a duração de verdade para a PRÓXIMA instalação já nascer com uma estimativa melhor (não é
        # usado para nada de segurança, só para a contagem regressiva ficar mais precisa com o tempo).
        try { Set-Content -LiteralPath $arqDuracao -Value ([math]::Round($inicioNk.Elapsed.TotalSeconds)) -Encoding ASCII -ErrorAction Stop } catch {}
        break
    }
    if ($tent -lt 3) {
        Write-Host "   A compilação falhou na tentativa $tent. Últimas linhas:" -ForegroundColor Yellow
        foreach ($af in $erroNk, $saidaNk) { if (Test-Path -LiteralPath $af) { Get-Content -LiteralPath $af -Tail 12 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "   | $_" -ForegroundColor DarkYellow } } }
        Start-Sleep -Seconds 5
    }
    }
    Marca '5/5 Compilação (Nuitka)'
    Pop-Location
    if (-not (Test-Path $exe)) {
        $motivo = if (Test-Path $relato) { "$(Get-Content $relato -Raw -ErrorAction SilentlyContinue)" } else { '' }
        foreach ($af in $erroNk, $saidaNk) { if (Test-Path -LiteralPath $af) { $motivo += "`n" + (Get-Content -LiteralPath $af -Tail 80 -ErrorAction SilentlyContinue | Out-String) } }
        Erro "O CofreSenhas.exe não foi criado."
        if ($motivo -match 'not enough memory|MemoryError|Allocation error') {
            Info "Causa: faltou memória livre no fim da compilação (não é o Avast)."
            Info "Feche o navegador e outros programas pesados e rode este instalador de novo."
        } elseif ($motivo -match 'Permission ?denied|PermissionError|WinError 5|Acesso negado') {
            Info "Causa: o antivírus bloqueou um arquivo no pendrive."
            Info "Abra o antivírus > Quarentena/Histórico e veja se algum arquivo de $base ou $destino foi bloqueado."
        } else {
            Info "Causa mais comum: o antivírus bloqueou a compilação ou colocou um arquivo em quarentena."
            Info "Se a mensagem acima tiver 'Permission denied', é o antivírus bloqueando o pendrive."
            Info "Abra o antivírus > Quarentena e veja se o CofreSenhas.exe está lá."
        }
        Info "Log completo em: $log"
        return
    }

    # ------------------------------------------------------------------
    try {
        if (-not (Test-Path -LiteralPath $destino -PathType Container)) {
            New-Item -ItemType Directory -Path $destino -Force -ErrorAction Stop | Out-Null
        }
        Move-Item $exe $final -Force -ErrorAction Stop
    }
    catch {
        Erro "Não consegui colocar o programa em $final ($($_.Exception.Message))."
        Info "Se o cofre estiver aberto, feche-o e rode de novo. O programa compilado ficou em $exe."
        return
    }
    # o pendrive guarda só o programa compilado: remove qualquer código-fonte solto de instalações antigas
    $fonteSolta = Join-Path $destino 'cofre_senhas.py'
    if (Test-Path -LiteralPath $fonteSolta) { Remove-Item -LiteralPath $fonteSolta -Force -ErrorAction SilentlyContinue; Info "removido o código-fonte antigo de $destino (o pendrive guarda só o programa compilado)" }
    # Assinatura digital (OPCIONAL, desligada por padrão). Só roda se a variável de ambiente COFRE_ASSINAR_SHA1 tiver a
    # impressão digital (40 caracteres hex) de um certificado de assinatura de código do SEU repositório de certificados.
    # COFRE_ASSINAR_TS (opcional) = endereço https do servidor de carimbo de tempo (sem ele, nada é enviado pela internet).
    # O programa sem assinatura fica guardado em _cb_cache\sem_assinatura e volta sozinho se a assinatura falhar.
    # Certificado próprio (autoassinado) NÃO remove o alerta do SmartScreen/Defender: só um certificado de uma
    # autoridade reconhecida muda isso.
    $assinatura = 'nao'
    $thumbAss = "$env:COFRE_ASSINAR_SHA1".Trim()
    if ($thumbAss) {
        if (-not (Test-Thumbprint $thumbAss)) { Info "COFRE_ASSINAR_SHA1 inválida (precisa de 40 caracteres hexadecimais): o programa fica SEM assinatura."; $assinatura = 'invalida' }
        else {
            $st = $null
            $kits = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
            if (Test-Path -LiteralPath $kits) {
                $todos = @(Get-ChildItem -LiteralPath $kits -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue)
                $pref = if ($arq -eq 'arm64') { 'arm64' } else { 'x64' }
                $st = $todos | Where-Object { $_.FullName -match "\\$pref\\signtool\.exe$" } | Sort-Object FullName -Descending | Select-Object -First 1
                if (-not $st) { $st = $todos | Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } | Sort-Object FullName -Descending | Select-Object -First 1 }
            }
            if (-not $st) { Info "signtool.exe não encontrado (instale o Windows SDK): o programa fica SEM assinatura."; $assinatura = 'sem_signtool' }
            else {
                $semAss = Join-Path $cache 'sem_assinatura'
                New-Item -ItemType Directory -Path $semAss -Force | Out-Null
                Copy-Item -LiteralPath $final -Destination (Join-Path $semAss $nomeFinal) -Force
                $argsSt = @('sign', '/sha1', $thumbAss, '/fd', 'SHA256')
                $ts = "$env:COFRE_ASSINAR_TS".Trim()
                if ($ts -match '^https://') { $argsSt += @('/tr', $ts, '/td', 'SHA256') }
                $argsSt += $final
                $saidaSt = & $st.FullName @argsSt 2>&1 | Out-String
                $codSt = $LASTEXITCODE
                $sig = Get-AuthenticodeSignature -LiteralPath $final -ErrorAction SilentlyContinue
                if ($codSt -eq 0 -and $sig -and $sig.SignerCertificate -and $sig.SignerCertificate.Thumbprint -eq $thumbAss.ToUpper()) {
                    Ok "programa assinado digitalmente (a primeira abertura deve ser testada: se não abrir, use a cópia sem assinatura em $semAss)"
                    $assinatura = 'ok'
                } else {
                    Copy-Item -LiteralPath (Join-Path $semAss $nomeFinal) -Destination $final -Force
                    Info "A assinatura falhou (código $codSt): o programa foi mantido SEM assinatura. $($saidaSt.Trim())"
                    $assinatura = 'falhou'
                }
            }
        }
    }
    $hash = (Get-FileHash $final -Algorithm SHA256).Hash
    # Limpa qualquer Abrir_Cofre.bat/.sha256/variante ARM64 de uma instalação ANTERIOR (versão antiga deste
    # instalador): o pacote final não deixa mais NENHUM arquivo "de fora" do programa -- só o CofreSenhas.exe e o
    # cofre.dat. Um arquivo solto na mesma pasta podia ser trocado JUNTO com o .exe por quem já tivesse acesso de
    # escrita ali, então não protegia contra ninguém (ver verificar_integridade() no programa e MODELO_DE_AMEACAS.md).
    foreach ($velho in 'Abrir_Cofre.bat', 'CofreSenhas.sha256', 'CofreSenhas-arm64.exe', 'CofreSenhas-arm64.sha256') {
        $pVelho = Join-Path $destino $velho
        if (Test-Path -LiteralPath $pVelho) {
            try { Remove-Item -LiteralPath $pVelho -Force -ErrorAction Stop; Info "removido $velho de uma instalação antiga (não existe mais nesta versão)" } catch {}
        }
    }
    Marca '6 Finalização (hash)'

    Write-Host ""
    Barra 5 5
    Write-Host "================ PRONTO ================" -ForegroundColor Green
    Write-Host "$nomeFinal criado em: $destino" -ForegroundColor Green
    Write-Host "Nada mais fica ao lado dele (sem .bat, sem .sha256): tudo o que é do programa está dentro deste" -ForegroundColor Green
    Write-Host "único arquivo compilado -- não há nada de fora para ser mexido ou copiado." -ForegroundColor Green
    Write-Host ""
    Write-Host "CÓDIGO SHA256 DO PROGRAMA (anote em PAPEL -- é a ÚNICA cópia confiável deste número):" -ForegroundColor Yellow
    Write-Host ("  " + ($hash -replace '(.{8})', '$1 ').Trim()) -ForegroundColor Yellow
    Write-Host "  Inteiro, numa linha só (para copiar):" -ForegroundColor Gray
    Write-Host "$hash" -ForegroundColor Yellow
    try { Set-Clipboard -Value $hash; Write-Host "  (já copiado para a área de transferência: cole onde precisar guardar)" -ForegroundColor Gray } catch {}
    Write-Host ""
    Write-Host "De propósito, o programa NÃO grava este número em nenhum arquivo ao lado dele: um arquivo solto" -ForegroundColor Gray
    Write-Host "podia ser trocado JUNTO com o .exe por quem já tivesse acesso de escrita na pasta, e não protegeria" -ForegroundColor Gray
    Write-Host "contra ninguém. Para conferir depois, abra o cofre e use o menu '...' > Verificar integridade do" -ForegroundColor Gray
    Write-Host "programa, e compare à mão com o que você anotou agora em papel. Fora isso, o que vale é:" -ForegroundColor Gray
    Write-Host "  Get-FileHash '$final'" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Próximos passos:" -ForegroundColor Cyan
    $ondeTxt = if ($modoPc) { 'na pasta do computador' } else { 'no pendrive' }
    Write-Host "  1. Dê dois cliques no $nomeFinal em $destino e crie o cofre (se quiser dois fatores: 'Senha E chave')."
    Write-Host "     O cofre (cofre.dat) é criado ao lado do programa, $ondeTxt."
    Write-Host "     O cofre.dat e seus arquivos de apoio ficam ocultos e somente leitura: só o $nomeFinal aparece na pasta."
    if ($modoPc) {
        Write-Host "  2. Se usar chave de acesso, salve o arquivo .key num pendrive à parte e anote a chave em papel."
        Write-Host "  3. Ao abrir, o programa se descompacta numa pasta temporária AO LADO dele (CofreSenhas_em_uso_...),"
        Write-Host "     que é apagada sozinha ao fechar."
        Write-Host "  4. Ligue o BitLocker no disco do computador e faça backup do cofre.dat num pendrive."
    } else {
        Write-Host "  2. Se usar chave de acesso, salve o arquivo .key em OUTRO pendrive (nunca no disco $($sistema):) e anote a chave em papel."
        Write-Host "  3. Ao abrir, o programa se descompacta numa pasta temporária AO LADO dele no pendrive"
        Write-Host "     (CofreSenhas_em_uso_...), que é apagada sozinha ao fechar. Nada vai para o $($sistema):."
        Write-Host "  4. Mantenha o BitLocker To Go ligado no pendrive inteiro (programa e cofre)."
    }
    Write-Host "  5. Na PRIMEIRA abertura o Windows pode mostrar 'O Windows protegeu o computador' (SmartScreen): clique em"
    Write-Host "     'Mais informações' > 'Executar mesmo assim'. É normal para programa novo e sem assinatura paga."
    Write-Host "     Se o antivírus colocar o CofreSenhas.exe em quarentena, restaure-o pelo próprio antivírus (ele é um"
    Write-Host "     falso alarme comum em programas compilados) e confira o SHA256 acima antes de usar."
    $okFinal = $true
    } finally {
        $script:CodigoSaida = if ($okFinal) { 0 } else { 1 }     # código de saída do script (o .bat repassa e avisa se der erro)
        # Em QUALQUER saída (sucesso, erro, Ctrl+C): mostra os tempos, guarda só o LOG no pendrive e apaga a pasta
        # de trabalho (_cb: ambiente, restos). Só o _cb_cache fica. Nada da compilação vai para o C:.
        try { Mostrar-Tempos } catch {}
        try { Stop-Transcript | Out-Null } catch {}
        # Log detalhado e estruturado (uma linha por fato; sem caminhos, sem nome de usuário): útil para auditar e para
        # descobrir por que a compilação falhou em outro computador. Fica em <pendrive>:\CofreSenhas\instalacao_detalhada.log
        try {
            if ($destino -and (Test-Path -LiteralPath $destino)) {
                $verCofre = ''; try { if ($fonte) { $verCofre = (Versao-Do-Cofre $fonte).ToString() } } catch {}
                $hashCurto = ''; try { if ($hashFonteTxt) { $hashCurto = $hashFonteTxt.Substring(0, 16) } } catch {}
                $linhasLog = New-Object System.Collections.ArrayList
                [void]$linhasLog.Add(("INSTALACAO resultado={0} cofre_versao={1} cofre_sha256={2} plataforma={3} so={4} powershell={5} fs={6} livre_gb={7} assinatura={8} total_s={9}" -f
                    $(if ($okFinal) { 'ok' } else { 'falha' }), $verCofre, $hashCurto, $plat, [Environment]::OSVersion.Version, $PSVersionTable.PSVersion, $fsEsc,
                    $(if ($null -ne $livreBytes) { [math]::Round($livreBytes / 1GB, 1) } else { '?' }), $assinatura, [math]::Round($cron.Elapsed.TotalSeconds)))
                foreach ($t in $tempos) { [void]$linhasLog.Add(("  etapa=`"{0}`" tempo={1}" -f $t.Etapa, $t.Tempo)) }
                if (-not $okFinal -and $estadoT.erro) { [void]$linhasLog.Add("  erro=`"" + (Remove-Caminhos $estadoT.erro) + "`"") }
                Add-LogDetalhado (Join-Path $destino 'instalacao_detalhada.log') $linhasLog.ToArray()
            }
        } catch {}
        try {
            if (Test-Path -LiteralPath $log) {
                New-Item -ItemType Directory -Path $logsDir -Force -ErrorAction Stop | Out-Null
                $carimbo = Get-Date -Format 'yyyyMMdd-HHmmss'
                Copy-Item -LiteralPath $log -Destination (Join-Path $logsDir "instalacao-$carimbo.log") -Force
                if (-not $okFinal) {
                    foreach ($af in $saidaNk, $erroNk) {
                        if (Test-Path -LiteralPath $af) { Copy-Item -LiteralPath $af -Destination (Join-Path $logsDir ("instalacao-$carimbo-" + (Split-Path $af -Leaf))) -Force }
                    }
                }
                Info "Log guardado em $logsDir (instalacao-$carimbo.log)"
            }
        } catch {}
        try {
            if ($destino -and (Test-Path -LiteralPath $destino)) {
                $res = Ocultar-Apoio $destino
                $nomeVisivel = if ($nomeFinal) { $nomeFinal } else { 'o programa' }
                if ($res.n -gt 0) { Info "Arquivos do cofre ocultos e protegidos ($($res.n) itens): só o $nomeVisivel aparece na pasta." }
                if ($res.falhou.Count -gt 0) {
                    Write-Host "   [ATENÇÃO] Não consegui esconder: $($res.falhou -join ', '). Provável antivírus segurando o arquivo " -NoNewline -ForegroundColor Yellow
                    Write-Host "agora há pouco (normal em .exe recém-criado). Feche e abra a pasta de novo (ou aperte F5): " -NoNewline -ForegroundColor Yellow
                    Write-Host "costuma já aparecer certo." -ForegroundColor Yellow
                } elseif ($res.n -gt 0) {
                    Info "Se ainda aparecerem na pasta, é só o Explorer não ter atualizado a tela: feche e abra a pasta de novo (ou aperte F5)."
                }
            }
        } catch {}
        try { Set-Location -LiteralPath $env:USERPROFILE } catch {}
        if ($cache -and (Test-Path -LiteralPath $cache)) {
            Info "Cache guardado em ${cache}: deixa a próxima instalação bem mais rápida e permite continuar se algo falhar. Para liberar espaço no pendrive, apague essa pasta."
            if (-not $modoPc) { Info "Essa pasta e a _cb ficam na RAIZ do pendrive (não dentro de $(Split-Path $destino -Leaf)) de propósito: um caminho mais fundo passaria do limite de 260 caracteres do Windows com os nomes compridos que o compilador C usa. Já ficam ocultas (Oculto+Sistema); só aparecem para quem ligar as duas opções de mostrar ocultos/protegidos do Explorer." }
        }
        Remove-Item $base -Recurse -Force -ErrorAction SilentlyContinue
        try { if ($null -ne $modoConsoleOriginal -and $hc) { [void][W.C]::SetConsoleMode($hc, [uint32]$modoConsoleOriginal) } } catch {}   # QuickEdit volta ao que era
        if (Test-Path $base) { Info "aviso: não consegui apagar $base inteira (pode apagar à mão; ela só guarda restos da compilação)." }
    }
}

# Só instala quando o arquivo é EXECUTADO. Carregado com ". .\instalar_cofre.ps1" (como faz o Pester) só define as funções.
if ($MyInvocation.InvocationName -ne '.') {
    $script:CodigoSaida = 1                                   # só vira 0 quando a instalação termina com sucesso
    Instalar-Cofre ([string]($args | Select-Object -First 1))
    Write-Host ""
    Read-Host "Pressione ENTER para fechar"
    exit $script:CodigoSaida
}
