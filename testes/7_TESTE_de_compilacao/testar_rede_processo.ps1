# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
param([Parameter(Mandatory = $true)][string]$Executavel)
$ErrorActionPreference = 'Stop'

function Obter-ArvoreProcessos([int]$Raiz) {
    $todos = @(Get-CimInstance -ClassName Win32_Process -ErrorAction Stop)
    $ids = @($Raiz)
    do {
        $novos = @($todos | Where-Object {
            $ids -contains [int]$_.ParentProcessId -and $ids -notcontains [int]$_.ProcessId
        } | ForEach-Object { [int]$_.ProcessId })
        if ($novos.Count) { $ids += $novos }
    } while ($novos.Count)
    return $ids
}

function Testar-AcessoNegado($erro) {
    $ex = $erro.Exception
    while ($ex) {
        if ($ex -is [System.ComponentModel.Win32Exception] -and $ex.NativeErrorCode -eq 5) { return $true }
        if ($ex.Message -match '(?i)\baccess denied\b|\bacesso negado\b') { return $true }
        $ex = $ex.InnerException
    }
    return $false
}

function Pedir-Fechamento([int]$ProcessoId) {
    # Manda WM_CLOSE a todas as janelas do processo (o mesmo que clicar no X). Nao depende de permissao para
    # ENCERRAR o processo, que o proprio cofre pode negar de proposito.
    if (-not ('CofreRedeTeste.Janelas' -as [type])) {
        Add-Type -Namespace CofreRedeTeste -Name Janelas -MemberDefinition @'
public delegate bool EnumProc(IntPtr h, IntPtr l);
[System.Runtime.InteropServices.DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
[System.Runtime.InteropServices.DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
[System.Runtime.InteropServices.DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
public static void Fechar(uint alvo) {
    EnumWindows(delegate(IntPtr h, IntPtr l) {
        uint p; GetWindowThreadProcessId(h, out p);
        if (p == alvo) { PostMessage(h, 0x0010, IntPtr.Zero, IntPtr.Zero); }
        return true;
    }, IntPtr.Zero);
}
'@
    }
    [CofreRedeTeste.Janelas]::Fechar([uint32]$ProcessoId)
}

function Encerrar-Processo([int]$ProcessoId) {
    # Fecha pela janela; so forca se for preciso. Se o Windows negar, vira AVISO: o resultado do teste de rede
    # (o que importa) ja foi decidido e nao pode ser trocado por um erro ao arrumar a casa.
    $alvo = Get-Process -Id $ProcessoId -ErrorAction SilentlyContinue
    if (-not $alvo -or $alvo.HasExited) { return }
    try { [void]$alvo.CloseMainWindow() } catch { }
    try { Pedir-Fechamento $ProcessoId } catch { }
    if ($alvo.WaitForExit(10000)) { return }
    try {
        Stop-Process -Id $ProcessoId -Force -ErrorAction Stop
    } catch {
        & "$env:SystemRoot\System32\taskkill.exe" /PID $ProcessoId /T /F 2>&1 | Out-Null
    }
    $alvo.Refresh()
    if (-not $alvo.HasExited -and -not $alvo.WaitForExit(5000)) {
        Write-Output "[AVISO] Nao consegui encerrar o processo $ProcessoId (acesso negado). Feche-o pelo Gerenciador de Tarefas."
    }
}

function Limpar-Sobras {
    # Remove restos de rodadas anteriores deste teste: processos do cofre abertos com a pasta 'cofre_rede_teste_*'.
    # So mexe no que foi aberto POR este teste (confere a linha de comando); o cofre de uso normal nunca e tocado.
    $achados = @(Get-CimInstance -ClassName Win32_Process -Filter "Name like 'CofreSenhas%'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 'cofre_rede_teste_' })
    foreach ($p in $achados) {
        & "$env:SystemRoot\System32\taskkill.exe" /PID $p.ProcessId /T /F 2>&1 | Out-Null
        Write-Output "[INFO] Processo sobrado de teste anterior encerrado: PID $($p.ProcessId)"
    }
}

if (-not (Test-Path -LiteralPath $Executavel -PathType Leaf)) {
    Write-Output "[FALHOU] Executavel inexistente: $Executavel"
    exit 1
}

try { Limpar-Sobras } catch { }

$pasta = Join-Path $env:TEMP ("cofre_rede_teste_" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $pasta -ErrorAction Stop | Out-Null
$cofreTeste = Join-Path $pasta 'cofre.dat'
$processo = $null
$codigo = 1
$backgroundOriginal = $env:COFRE_GUI_TESTS_BACKGROUND
if ($null -eq $backgroundOriginal) {
    $tinhaBackground = $false
} else {
    $tinhaBackground = $true
}
$env:COFRE_GUI_TESTS_BACKGROUND = '1'
try {
    $argumento = '"' + $cofreTeste + '"'
    try {
        $processo = Start-Process -FilePath $Executavel -ArgumentList $argumento `
            -WorkingDirectory (Split-Path -Parent $Executavel) -PassThru -ErrorAction Stop
    } catch {
        if (Testar-AcessoNegado $_) {
            Write-Output '[PULADO] O Windows ou uma politica de seguranca bloqueou a inicializacao do executavel (acesso negado); nenhum bloqueio foi contornado.'
            $codigo = 9
        } else {
            throw
        }
    }
    if ($processo) {
        # O onefile se descompacta antes de iniciar o processo da aplicacao; em pendrive lento (e com o Defender varrendo)
        # isso leva mais de 60 s (o smoke visual mediu 59 s ate a janela). Em vez de esperar um tempo fixo, espera
        # ATE o processo-filho aparecer (limite de 240 s) e depois mais alguns segundos para a aplicacao montar a tela.
        $inicioEspera = Get-Date
        $fim = $inicioEspera.AddSeconds(240)
        $pids = @($processo.Id)
        do {
            Start-Sleep -Milliseconds 500
            $processo.Refresh()
            if ($processo.HasExited) { break }
            $pids = @(Obter-ArvoreProcessos $processo.Id)
        } while ($pids.Count -le 1 -and (Get-Date) -lt $fim)
        if (-not $processo.HasExited -and $pids.Count -gt 1) {
            Start-Sleep -Seconds 10          # deixa a janela abrir; conexao de rede indevida apareceria nesse intervalo
            $processo.Refresh()
            if (-not $processo.HasExited) { $pids = @(Obter-ArvoreProcessos $processo.Id) }
        }
        $esperouS = [int]((Get-Date) - $inicioEspera).TotalSeconds

        if ($processo.HasExited) {
            Write-Output "[FALHOU] CofreSenhas.exe encerrou antes da verificacao (codigo $($processo.ExitCode))."
            $codigo = 1
        } else {
            if ($pids.Count -le 1) {
                Write-Output "[PULADO] O executavel onefile nao iniciou o processo da aplicacao em $esperouS s; conexoes nao foram verificadas."
                $codigo = 9
            } else {
                Write-Output "[INFO] Processo da aplicacao apareceu apos ~$esperouS s (inclui os 10 s finais de espera)."
                $tcp = @()
                $udp = @()
                foreach ($pidTeste in $pids) {
                    try {
                        $tcp += @(Get-NetTCPConnection -OwningProcess $pidTeste -ErrorAction Stop)
                    } catch {
                        if ($_.FullyQualifiedErrorId -notlike 'CmdletizationQuery_NotFound_OwningProcess,*') { throw }
                    }
                    try {
                        $udp += @(Get-NetUDPEndpoint -OwningProcess $pidTeste -ErrorAction Stop)
                    } catch {
                        if ($_.FullyQualifiedErrorId -notlike 'CmdletizationQuery_NotFound_OwningProcess,*') { throw }
                    }
                }
                Write-Output "PIDs de teste: $($pids -join ', ')"
                if ($tcp.Count -or $udp.Count) {
                    $tcp | Format-Table OwningProcess, LocalAddress, LocalPort, RemoteAddress, RemotePort, State -AutoSize | Out-String | Write-Output
                    $udp | Format-Table OwningProcess, LocalAddress, LocalPort -AutoSize | Out-String | Write-Output
                    Write-Output '[FALHOU] O processo abriu conexoes TCP/UDP.'
                    $codigo = 1
                } else {
                    Write-Output '[OK] Nenhuma conexao TCP/UDP.'
                    $codigo = 0
                }
            }
        }
    }
} catch {
    Write-Output "[FALHOU] Nao foi possivel testar a rede do processo: $($_.Exception.Message)"
    $codigo = 1
} finally {
    if ($tinhaBackground) { $env:COFRE_GUI_TESTS_BACKGROUND = $backgroundOriginal }
    else { Remove-Item Env:\COFRE_GUI_TESTS_BACKGROUND -ErrorAction SilentlyContinue }
    if ($processo) {
        $pids = @(Obter-ArvoreProcessos $processo.Id)
        [array]::Reverse($pids)
        foreach ($pidTeste in $pids) {
            try { Encerrar-Processo $pidTeste } catch { Write-Output "[AVISO] Falha ao encerrar o processo ${pidTeste}: $($_.Exception.Message)" }
        }
        # ultima garantia: encerra a arvore inteira pelo processo raiz (o filho pode negar o encerramento direto)
        $raizVivo = Get-Process -Id $processo.Id -ErrorAction SilentlyContinue
        if ($raizVivo -and -not $raizVivo.HasExited) {
            & "$env:SystemRoot\System32\taskkill.exe" /PID $processo.Id /T /F 2>&1 | Out-Null
        }
    }
    if (Test-Path -LiteralPath $pasta) {
        Remove-Item -LiteralPath $pasta -Recurse -Force -ErrorAction SilentlyContinue
    }
}
exit $codigo
