# Teste de fumaça (do INSTALADOR/SO, não do núcleo) no Windows REAL. Não cria cofre e não mexe no pendrive. Cria um
# ambiente Python TEMPORÁRIO ao lado deste arquivo (apagado no fim) para instalar as bibliotecas do cofre; não altera
# o Python do sistema. A bateria do núcleo tem seu próprio teste separado: testes\1_motor_do_cofre\RODAR ESTA PASTA - testes do motor do cofre.bat.
# Escreve o resultado em resultados\resultado_teste_windows.txt (uma pasta acima, junto com o de todos os outros testes).
$ErrorActionPreference = 'Continue'
# UTF-8 de ponta a ponta: o Python (PYTHONUTF8) escreve em UTF-8 e o PowerShell lê em UTF-8 (senão cp850 estraga os acentos)
$env:PYTHONDONTWRITEBYTECODE = '1'      # o teste não deixa __pycache__ na pasta
$env:PYTHONUTF8 = '1'; $env:PYTHONIOENCODING = 'utf-8'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$aqui = $PSScriptRoot
$pai = Split-Path (Split-Path $aqui -Parent) -Parent    # testes\4_so_no_windows -> raiz do projeto
$resultados = Join-Path (Split-Path $aqui -Parent) 'resultados'   # testes\4_so_no_windows -> testes\resultados
New-Item -ItemType Directory -Force -Path $resultados | Out-Null
$saida = Join-Path $resultados 'resultado_teste_windows.txt'
$linhas = New-Object System.Collections.ArrayList
function L([string]$t) { [void]$linhas.Add($t); Write-Host $t }
function Teste([string]$nome, [bool]$ok, [string]$extra = '') { L ("[{0}] {1} {2}" -f ($(if ($ok) { 'OK' } else { 'FALHOU' }), $nome, $extra)) }
# apaga uma pasta tentando algumas vezes: logo após rodar python.exe de dentro dela, o Windows (ou o antivírus,
# que examina o .exe recém-criado) pode mantê-la bloqueada por um instante; sem isto a pasta ficava "presa" e
# sobrava lixo em venv_teste_tmp de uma execução para a outra.
function Apagar-ComTentativas([string]$caminho) {
    for ($i = 1; $i -le 3; $i++) {
        if (-not (Test-Path $caminho)) { return }
        Remove-Item $caminho -Recurse -Force -ErrorAction SilentlyContinue
        if (-not (Test-Path $caminho)) { return }
        Start-Sleep -Seconds 2
    }
}
$venvT = Join-Path $aqui 'venv_teste_tmp'     # declarado aqui em cima para o "finally" conseguir limpar mesmo se algo falhar antes
# tudo dentro de um try/finally: qualquer erro inesperado (mesmo um que pararia o script) ainda deixa o resultado_teste_windows.txt
# gravado até aquele ponto, em vez de não gerar relatório nenhum.
try {
L "== Windows: $([Environment]::OSVersion.VersionString) | PowerShell $($PSVersionTable.PSVersion) | $(Get-Date -Format s)"
$osArqT = ''; try { $osArqT = [string][System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture } catch {}
L "== Arquitetura do computador: $osArqT (processo: $env:PROCESSOR_ARCHITECTURE)  <- o instalador usa isto para escolher x64 ou ARM64"

# 1) o instalador é PowerShell válido? (nunca foi analisado por um parser de verdade)
$ps1 = Join-Path $pai 'instalar_cofre.ps1'
if (Test-Path $ps1) {
    $tokens = $null; $erros = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($ps1, [ref]$tokens, [ref]$erros)
    Teste 'instalar_cofre.ps1: sintaxe PowerShell válida' ($erros.Count -eq 0) "($($erros.Count) erro(s))"
    foreach ($e in ($erros | Select-Object -First 10)) { L "    linha $($e.Extent.StartLineNumber): $($e.Message)" }
} else { L '[PULADO] instalar_cofre.ps1 não está na pasta acima' }

# 2) QuickEdit: o trecho do instalador compila e roda?
try {
    Add-Type -Namespace W -Name C -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern IntPtr GetStdHandle(int h);
[DllImport("kernel32.dll")] public static extern bool GetConsoleMode(IntPtr h, out uint m);
[DllImport("kernel32.dll")] public static extern bool SetConsoleMode(IntPtr h, uint m);
'@ -ErrorAction Stop
    $hc = [W.C]::GetStdHandle(-10); $mc = [uint32]0
    $okc = [W.C]::GetConsoleMode($hc, [ref]$mc)
    if ($okc) { [void][W.C]::SetConsoleMode($hc, [uint32](($mc -band [uint32]4294967231) -bor [uint32]128)) }
    Teste 'QuickEdit: Add-Type e SetConsoleMode executam sem erro' $true "(GetConsoleMode=$okc)"
} catch { Teste 'QuickEdit: Add-Type e SetConsoleMode executam sem erro' $false $_.Exception.Message }

# 3) Abrir_Cofre.bat com um .exe de teste inofensivo (nada do cofre)
$bat = Join-Path $pai 'Abrir_Cofre.bat'
if (Test-Path $bat) {
    $t = Join-Path $aqui 'bat_tmp'
    Remove-Item $t -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $t -Force | Out-Null
    Copy-Item $bat $t
    Copy-Item (Join-Path $env:SystemRoot 'System32\whoami.exe') (Join-Path $t 'CofreSenhas.exe')
    $env:COFRE_SO_CONFERIR = '1'
    function Roda { (Start-Process cmd.exe -ArgumentList '/c', 'Abrir_Cofre.bat' -WorkingDirectory $t -Wait -PassThru -WindowStyle Hidden).ExitCode }
    Teste 'bat: sem .sha256 -> código 2' ((Roda) -eq 2)
    (Get-FileHash (Join-Path $t 'CofreSenhas.exe') -Algorithm SHA256).Hash | Set-Content (Join-Path $t 'CofreSenhas.sha256') -Encoding ASCII
    Teste 'bat: .exe íntegro -> código 0' ((Roda) -eq 0)
    $b = [IO.File]::ReadAllBytes((Join-Path $t 'CofreSenhas.exe')); $m = [int][math]::Floor($b.Length / 2); $b[$m] = $b[$m] -bxor 1
    [IO.File]::WriteAllBytes((Join-Path $t 'CofreSenhas.exe'), $b)
    Teste 'bat: .exe com 1 byte alterado -> código 3 (RECUSA)' ((Roda) -eq 3)
    Remove-Item (Join-Path $t 'CofreSenhas.exe') -Force
    Teste 'bat: sem .exe -> código 1 (e NÃO abre .py)' ((Roda) -eq 1)
    # versão ARM64: com o computador ARM64 e o CofreSenhas-arm64.exe presente, o bat confere ESSE programa
    Copy-Item (Join-Path $env:SystemRoot 'System32\whoami.exe') (Join-Path $t 'CofreSenhas-arm64.exe')
    (Get-FileHash (Join-Path $t 'CofreSenhas-arm64.exe') -Algorithm SHA256).Hash | Set-Content (Join-Path $t 'CofreSenhas-arm64.sha256') -Encoding ASCII
    Teste 'bat: só há a versão ARM64 num computador x64 -> código 1 (não tenta abrir)' ((Roda) -eq 1)
    $arqOriginal = $env:PROCESSOR_ARCHITECTURE
    $env:PROCESSOR_ARCHITECTURE = 'ARM64'
    Teste 'bat (ARM64): programa ARM64 íntegro -> código 0' ((Roda) -eq 0)
    $b = [IO.File]::ReadAllBytes((Join-Path $t 'CofreSenhas-arm64.exe')); $m = [int][math]::Floor($b.Length / 2); $b[$m] = $b[$m] -bxor 1
    [IO.File]::WriteAllBytes((Join-Path $t 'CofreSenhas-arm64.exe'), $b)
    Teste 'bat (ARM64): programa ARM64 com 1 byte alterado -> código 3 (RECUSA)' ((Roda) -eq 3)
    $env:PROCESSOR_ARCHITECTURE = $arqOriginal
    Remove-Item Env:COFRE_SO_CONFERIR -ErrorAction SilentlyContinue
    Remove-Item $t -Recurse -Force -ErrorAction SilentlyContinue
} else { L '[PULADO] Abrir_Cofre.bat não está na pasta acima' }

# 4) cofre_senhas.py importa e inicializa no Windows real? (sem criar cofre, sem janela visível)
$py = $null
# o instalador usa o Python 3.13: prefere o mesmo
foreach ($c in @('py -3.13', 'py -3', 'python')) { try { $v = & cmd /c "$c --version 2>&1"; if ($LASTEXITCODE -eq 0 -and $v -match 'Python 3') { $py = $c; L "Python: $v ($c)"; break } } catch {} }
$fonte = Join-Path $pai 'cofre_senhas.py'
# O Python do sistema costuma NÃO ter as bibliotecas do cofre (o instalador usa um ambiente isolado). Para o teste ser
# de verdade, cria um ambiente TEMPORÁRIO ao lado deste arquivo, instala só as bibliotecas de execução (as mesmas
# versões do requirements.txt) e apaga tudo no fim. Não mexe no Python do sistema nem no pendrive.
$usouVenv = $false
if ($py -and (Test-Path $fonte)) {
    $req = Join-Path $pai 'requirements.txt'
    if (-not (Test-Path $req)) { L "[info] requirements.txt não está em ${pai}: copie-o para lá para os testes 4 e 6 rodarem" }
    if (Test-Path $req) {
        $pins = Get-Content $req | Where-Object { $_ -match '^(cryptography|argon2-cffi|argon2-cffi-bindings|openpyxl|defusedxml|fido2|cffi|pycparser|et-xmlfile)==' }
        $reqT = Join-Path $aqui 'req_teste_tmp.txt'
        Set-Content -Path $reqT -Value $pins -Encoding ASCII
        L 'Criando ambiente temporário e instalando as bibliotecas (precisa de internet, ~1 min)...'
        Apagar-ComTentativas $venvT   # por segurança: apaga um venv_teste_tmp que tenha sobrado de uma execução anterior
        & cmd /c "$py -m venv `"$venvT`" 2>&1" | Out-Null
        $pyV = Join-Path $venvT 'Scripts\python.exe'
        $cfgV = Join-Path $venvT 'pyvenv.cfg'
        # o antivírus às vezes examina os arquivos recém-criados do ambiente (o mesmo motivo de venv_teste_tmp ficar
        # preso ao apagar); dá um tempo para o pyvenv.cfg "assentar" antes de chamar o pip, senão o pip falha com
        # "failed to locate pyvenv.cfg" mesmo com o ambiente criado corretamente.
        for ($i = 1; $i -le 5; $i++) { if (Test-Path $cfgV) { break }; Start-Sleep -Seconds 1 }
        if ((Test-Path $pyV) -and (Test-Path $cfgV)) {
            $pipOut = & cmd /c "`"$pyV`" -m pip install --disable-pip-version-check --progress-bar off -r `"$reqT`" 2>&1"
            $okPip = ($LASTEXITCODE -eq 0)
            Teste 'bibliotecas instaladas no ambiente temporário' $okPip
            if (-not $okPip) { foreach ($o in ($pipOut | Select-Object -Last 15)) { L "    pip> $o" } }
            else { $env:PATH = (Join-Path $venvT 'Scripts') + ';' + $env:PATH; $py = 'python'; $usouVenv = $true }
        } else { Teste 'ambiente temporário criado' $false }
        Remove-Item $reqT -Force -ErrorAction SilentlyContinue
    }
}
if ($usouVenv) { $libsOk = $true } else { $libsOk = $false; L '[PULADO] sem as bibliotecas do cofre neste Python: testes 4 e 6 não rodam (não é defeito do programa)' }
if ($py -and $libsOk -and (Test-Path $fonte)) {
    $cod = @"
import sys, ast
sys.path.insert(0, r'$pai')
with open(r'$fonte', encoding='utf-8') as _f:
    ast.parse(_f.read())
print('sintaxe OK')
import cofre_senhas as c
print('import OK, versao', c.VERSAO_PROGRAMA, 'EH_WINDOWS', c.EH_WINDOWS)
print('blindagem:', c.blindar_processo())
import tkinter as tk
r = tk.Tk(); r.withdraw()
c.aplicar_tema(r)                       # já prepara as fontes
c.preparar_fontes(r)                    # chamada repetida não pode quebrar
print('tema/fontes OK; DPI escala', getattr(c, 'ESCALA', '?'))
print('espias:', sorted(c.ferramentas_espias())[:5])
r.destroy()
print('FIM-OK')
"@
    $arq = Join-Path $aqui 'py_tmp.py'
    Set-Content -Path $arq -Value $cod -Encoding UTF8
    # sem -X dev: neste PC o modo dev trava até um "print(1)" (veja a sonda abaixo), o que não tem relação com o cofre
    $out = & cmd /c "$py `"$arq`" 2>&1"
    Remove-Item $arq -Force -ErrorAction SilentlyContinue
    foreach ($o in $out) { L "    py> $o" }
    Teste 'cofre_senhas.py inicializa no Windows (import, blindagem, tema)' (($out -join "`n") -match 'FIM-OK')
} else { L '[PULADO] Python 3 ou cofre_senhas.py ausente: teste de import não rodou' }

# 5) o pendrive deve guardar só o programa compilado: remove o código-fonte solto em <pendrive>:\CofreSenhas (só esse arquivo)
foreach ($d in Get-CimInstance Win32_LogicalDisk -ErrorAction SilentlyContinue | Where-Object { $_.DriveType -eq 2 -and $_.FreeSpace }) {
    $alvo = Join-Path ($d.DeviceID + '\') 'CofreSenhas\cofre_senhas.py'
    if (Test-Path -LiteralPath $alvo) {
        Remove-Item -LiteralPath $alvo -Force -ErrorAction SilentlyContinue
        Teste "código-fonte removido do pendrive ($alvo)" (-not (Test-Path -LiteralPath $alvo))
    }
}
# 5b) SONDA do modo desenvolvedor (-X dev) do Python deste PC: serve para separar "defeito do cofre" de "defeito deste Python".
#     Cada linha roda um comando mínimo, sem o cofre. Código 0 = ok; 3221225477 (0xC0000005) = o PRÓPRIO Python travou.
if ($py) {
    $tmpf = Join-Path $aqui 'sonda_tmp.txt'; Set-Content -Path $tmpf -Value 'x'
    $sondas = [ordered]@{
        'python -X dev (vazio)'                       = "$py -X dev -c `"print(1)`""
        'python -X dev -W error + arquivo não fechado' = "$py -X dev -W error -c `"open(r'$tmpf').read()`""
        'python -X dev + tkinter abre e fecha'        = "$py -X dev -c `"import tkinter; r=tkinter.Tk(); r.withdraw(); r.destroy()`""
        'python -X dev + ctypes.windll'               = "$py -X dev -c `"import ctypes; ctypes.windll.user32.GetForegroundWindow()`""
    }
    foreach ($k in $sondas.Keys) {
        $o = & cmd /c "$($sondas[$k]) 2>&1"; $cod = $LASTEXITCODE
        L ("    sonda [{0}] -> código {1}" -f $k, $cod)
    }
    Remove-Item $tmpf -Force -ErrorAction SilentlyContinue
}
# (a bateria de testes do núcleo NÃO roda mais aqui: tem o seu próprio bat dedicado em
#  testes\1_motor_do_cofre\RODAR ESTA PASTA - testes do motor do cofre.bat, para poder rodar separada dos testes do instalador abaixo)
# 6) testes unitários (Pester) das funções auxiliares do instalador
$pt = Join-Path $aqui 'instalador.Tests.ps1'
if ((Get-Command Invoke-Pester -ErrorAction SilentlyContinue) -and (Test-Path $pt)) {
    try {
        $rp = Invoke-Pester -Path $pt -PassThru | Select-Object -Last 1
        Teste 'Pester: funções auxiliares do instalador' ($rp.FailedCount -eq 0 -and $rp.PassedCount -gt 0) "(passaram $($rp.PassedCount), falharam $($rp.FailedCount))"
    } catch { Teste 'Pester: funções auxiliares do instalador' $false $_.Exception.Message }
} else { L '[PULADO] Pester não encontrado neste Windows (o instalador não depende dele)' }
L '== FIM'
}
catch {
    L "== ERRO FATAL (o script parou antes do fim): $($_.Exception.Message)"
    L "    linha $($_.InvocationInfo.ScriptLineNumber): $($_.InvocationInfo.Line.Trim())"
}
finally {
    # SEMPRE grava o relatório até aqui, mesmo que algo acima tenha travado o script — assim nunca fica sem nada.
    Apagar-ComTentativas $venvT      # apaga o ambiente temporário (com novas tentativas se algo o tiver bloqueado)
    Set-Content -Path $saida -Value $linhas -Encoding UTF8
}
