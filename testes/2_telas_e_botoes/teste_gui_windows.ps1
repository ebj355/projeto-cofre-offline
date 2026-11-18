# Bateria de testes de INTERFACE (GUI) no Windows REAL. Cada teste abre e fecha janelas do Tkinter por alguns
# segundos (é normal ver a tela "piscar" várias vezes) - não precisa clicar em nada, é tudo automático.
# Não cria cofre de verdade na pasta do usuário (cada teste usa sua própria pasta temporária, apagada ao final).
# Cria um ambiente Python TEMPORÁRIO ao lado deste arquivo (apagado no fim) para instalar as bibliotecas do cofre;
# não altera o Python do sistema. Escreve o resultado em resultados\resultado_teste_gui_windows.txt (uma pasta
# acima) - um arquivo SEPARADO do resultado_teste_windows.txt (cada bateria tem o seu próprio resultado).
$ErrorActionPreference = 'Continue'
# UTF-8 de ponta a ponta: o Python (PYTHONUTF8) escreve em UTF-8 e o PowerShell lê em UTF-8 (senão cp850 estraga os acentos)
$env:PYTHONDONTWRITEBYTECODE = '1'      # o teste não deixa __pycache__ na pasta
$env:PYTHONUTF8 = '1'; $env:PYTHONIOENCODING = 'utf-8'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$aqui = $PSScriptRoot
$pai = Split-Path (Split-Path $aqui -Parent) -Parent    # testes\2_telas_e_botoes -> raiz do projeto
$resultados = Join-Path (Split-Path $aqui -Parent) 'resultados'   # testes\2_telas_e_botoes -> testes\resultados
New-Item -ItemType Directory -Force -Path $resultados | Out-Null
$saida = Join-Path $resultados 'resultado_teste_gui_windows.txt'
$linhas = New-Object System.Collections.ArrayList
function L([string]$t) { [void]$linhas.Add($t); Write-Host $t }
function Teste([string]$nome, [bool]$ok, [string]$extra = '') { L ("[{0}] {1} {2}" -f ($(if ($ok) { 'OK' } else { 'FALHOU' }), $nome, $extra)) }
# apaga uma pasta tentando algumas vezes: logo após rodar python.exe de dentro dela, o Windows (ou o antivírus,
# que examina os arquivos recém-criados) pode mantê-la bloqueada por um instante; sem isto a pasta ficava "presa"
# e sobrava lixo em venv_gui_tmp de uma execução para a outra.
function Apagar-ComTentativas([string]$caminho) {
    for ($i = 1; $i -le 3; $i++) {
        if (-not (Test-Path $caminho)) { return }
        Remove-Item $caminho -Recurse -Force -ErrorAction SilentlyContinue
        if (-not (Test-Path $caminho)) { return }
        Start-Sleep -Seconds 2
    }
}
$venvT = Join-Path $aqui 'venv_gui_tmp'     # declarado aqui em cima para o "finally" conseguir limpar mesmo se algo falhar antes
# tudo dentro de um try/finally: qualquer erro inesperado ainda deixa o resultado_teste_gui_windows.txt gravado
# até aquele ponto, em vez de não gerar relatório nenhum.
try {
L "== Windows: $([Environment]::OSVersion.VersionString) | PowerShell $($PSVersionTable.PSVersion) | $(Get-Date -Format s)"

# 1) localiza o Python (o instalador usa o 3.13: prefere o mesmo) e confirma que tem o Tkinter
$py = $null
foreach ($c in @('py -3.13', 'py -3', 'python')) {
    try {
        $v = & cmd /c "$c --version 2>&1"
        if ($LASTEXITCODE -eq 0 -and $v -match 'Python 3') {
            $tk = & cmd /c "$c -c `"import tkinter`" 2>&1"
            if ($LASTEXITCODE -eq 0) { $py = $c; L "Python: $v ($c, com Tkinter)"; break }
            else { L "[info] $c ($v) não tem Tkinter instalado - pulando" }
        }
    } catch {}
}
if (-not $py) { L '[PULADO] nenhum Python 3 com Tkinter foi encontrado: a bateria de interface não pode rodar' }

# 2) ambiente temporário com as mesmas bibliotecas do cofre (o Python do sistema normalmente não as tem)
$usouVenv = $false
$fonte = Join-Path $pai 'cofre_senhas.py'
$rodar = Join-Path $aqui '..\6_ferramentas_dos_testes\rodar_todos.py'
if ($py -and (Test-Path $fonte) -and (Test-Path $rodar)) {
    $req = Join-Path $pai 'requirements.txt'
    if (-not (Test-Path $req)) { L "[info] requirements.txt não está em ${pai}: copie-o para lá para a bateria rodar" }
    if (Test-Path $req) {
        $pins = Get-Content $req | Where-Object { $_ -match '^(cryptography|argon2-cffi|argon2-cffi-bindings|openpyxl|defusedxml|fido2|cffi|pycparser|et-xmlfile)==' }
        $reqT = Join-Path $aqui 'req_gui_tmp.txt'
        Set-Content -Path $reqT -Value $pins -Encoding ASCII
        L 'Criando ambiente temporário e instalando as bibliotecas do wheelhouse local...'
        Apagar-ComTentativas $venvT   # por segurança: apaga um venv_gui_tmp que tenha sobrado de uma execução anterior
        & cmd /c "$py -m venv `"$venvT`" 2>&1" | Out-Null
        $pyV = Join-Path $venvT 'Scripts\python.exe'
        $cfgV = Join-Path $venvT 'pyvenv.cfg'
        # o antivírus às vezes examina os arquivos recém-criados do ambiente; dá um tempo para o pyvenv.cfg
        # "assentar" antes de chamar o pip, senão o pip falha com "failed to locate pyvenv.cfg" mesmo com o
        # ambiente criado corretamente.
        for ($i = 1; $i -le 5; $i++) { if (Test-Path $cfgV) { break }; Start-Sleep -Seconds 1 }
        if ((Test-Path $pyV) -and (Test-Path $cfgV)) {
            $wheelhouse = Join-Path $pai 'pacotes'
            $pipOut = & cmd /c "`"$pyV`" -m pip install --disable-pip-version-check --no-index --find-links `"$wheelhouse`" --progress-bar off -r `"$reqT`" 2>&1"
            $okPip = ($LASTEXITCODE -eq 0)
            Teste 'bibliotecas instaladas no ambiente temporário' $okPip
            if (-not $okPip) {
                L '    [info] Rode 3 - BAIXAR PACOTES antes de testar sem internet.'
                foreach ($o in ($pipOut | Select-Object -Last 15)) { L "    pip> $o" }
            }
            else { $env:PATH = (Join-Path $venvT 'Scripts') + ';' + $env:PATH; $py = 'python'; $usouVenv = $true }
        } else { Teste 'ambiente temporário criado' $false }
        Remove-Item $reqT -Force -ErrorAction SilentlyContinue
    }
}
if (-not $usouVenv) { L '[PULADO] sem as bibliotecas do cofre neste Python: a bateria de interface não rodou (não é defeito do programa)' }

# 3) bateria de interface (cada teste abre e fecha janelas por alguns segundos; é automático, nada para clicar)
#    --sem-dev: o "-X dev" do Python TRAVA de verdade neste tipo de PC (já visto na bateria do núcleo: código
#    -1073741819/STATUS_ACCESS_VIOLATION) - sem relação com o cofre, é um problema do próprio modo dev do Python
#    aqui, então a bateria de interface já nasce sem ele.
if ($usouVenv) {
    L 'Rodando a bateria de interface (cada teste abre e fecha janelas por alguns segundos - é automático)...'
    $t0 = Get-Date
    # streaming (não $res = &...) + "-u" (sem buffer): sem isto a tela fica muda até o fim e parece travada
    & cmd /c "$py -u `"$rodar`" --so gui --sem-dev -v 2>&1" | ForEach-Object { L "    t> $_" }
    L ("    (bateria de interface levou {0:N0} s)" -f ((Get-Date) - $t0).TotalSeconds)
}
L '== FIM'
}
catch {
    L "== ERRO FATAL (o script parou antes do fim): $($_.Exception.Message)"
    L "    linha $($_.InvocationInfo.ScriptLineNumber): $($_.InvocationInfo.Line.Trim())"
}
finally {
    # SEMPRE grava o relatório até aqui, mesmo que algo acima tenha travado o script - assim nunca fica sem nada.
    Apagar-ComTentativas $venvT      # apaga o ambiente temporário (com novas tentativas se algo o tiver bloqueado)
    Set-Content -Path $saida -Value $linhas -Encoding UTF8
}
