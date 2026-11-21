# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
$ErrorActionPreference = 'Stop'

$raiz = $PSScriptRoot
$pacotes = Join-Path $raiz 'pacotes'
$requisitos = Join-Path $raiz 'requirements-test-lock.txt'
New-Item -ItemType Directory -Path $pacotes -Force | Out-Null

$pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
if (-not $pyLauncher) {
    Write-Error "O Python 3.13/launcher 'py' nao esta disponivel. Instale o Python e rode novamente."
    exit 1
}
$python = (& $pyLauncher.Source '-3.13-64' -c 'import sys; print(sys.executable)' 2>$null | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or -not $python -or -not (Test-Path -LiteralPath $python)) {
    Write-Error "Python 3.13 x64 nao encontrado. A preparacao offline requer o Python x64 (inclusive em hosts ARM64)."
    exit 1
}
$plataformaPython = (& $python -I -c 'import sysconfig; print(sysconfig.get_platform())' 2>$null | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $plataformaPython -ne 'win-amd64') {
    Write-Error "A preparacao offline requer Python x64 (win-amd64); arquitetura encontrada: $plataformaPython."
    exit 1
}

function Testar-Hash([string]$caminho, [string]$algoritmo, [string]$esperado) {
    if (-not (Test-Path -LiteralPath $caminho)) { return $false }
    return (Get-FileHash -LiteralPath $caminho -Algorithm $algoritmo).Hash -eq $esperado
}

function Baixar-Verificado([string]$url, [string]$caminho, [string]$algoritmo, [string]$esperado) {
    if (Testar-Hash $caminho $algoritmo $esperado) {
        Write-Host "Ja conferido: $(Split-Path $caminho -Leaf)"
        return
    }
    if (Test-Path -LiteralPath $caminho) { Remove-Item -LiteralPath $caminho -Force }
    Write-Host "Baixando $(Split-Path $caminho -Leaf)..."
    Invoke-WebRequest -Uri $url -OutFile $caminho -UseBasicParsing -TimeoutSec 600
    if (-not (Testar-Hash $caminho $algoritmo $esperado)) {
        Remove-Item -LiteralPath $caminho -Force -ErrorAction SilentlyContinue
        throw "Hash $algoritmo nao confere para $(Split-Path $caminho -Leaf)."
    }
}

# Os requisitos estao pinados; o wheelhouse recebe tambem as dependencias transitivas.
Write-Host 'Baixando as bibliotecas e ferramentas Python para testes...'
& $python -I -m pip download --disable-pip-version-check --only-binary=:all: --require-hashes --dest $pacotes --requirement $requisitos
if ($LASTEXITCODE -ne 0) { throw 'Falha ao baixar as dependencias Python de teste.' }

$sufixo = 'amd64'
$shaPython = if ($sufixo -eq 'arm64') {
    '3089A1977C32B26F5078E5A7D0285B7A861B8C96250C5DAC3B6AF59FBE9E9A75' # pragma: allowlist secret
} else {
    '5DA012101BA2E17113A9A1CD901E9CE1441086F2B7ECB5DE06EC94163899A190' # pragma: allowlist secret
}
$pythonInstaller = Join-Path $pacotes "python-3.13.17-$sufixo.exe"
Baixar-Verificado "https://www.python.org/ftp/python/3.13.17/python-3.13.17-$sufixo.exe" $pythonInstaller 'SHA256' $shaPython
$assinaturaPython = Get-AuthenticodeSignature -LiteralPath $pythonInstaller
if ($assinaturaPython.Status -ne 'Valid' -or $assinaturaPython.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
    throw 'A assinatura do instalador Python nao e valida; pacote offline recusado.'
}

$nmapInstaller = Join-Path $pacotes 'nmap-7.993-setup.exe'
Baixar-Verificado 'https://nmap.org/dist/nmap-7.993-setup.exe' $nmapInstaller 'SHA256' '22E5928D1738A1B94FFD3643014F52CB87D467DBEC4CFF9E5F721FE0B3782F1B' # pragma: allowlist secret

$pesterPackage = Join-Path $pacotes 'Pester-5.7.1.nupkg'
$pesterShaBytes = [Convert]::FromBase64String('TZlqSN2UgW0mtOnmk1ro5sy8Gfg5DqOCY0XxIeHOKufM4WNptRfBkM6tBev/AxI/gmarvTVWBK3V8SnCTc8oAg==') # pragma: allowlist secret
$pesterShaHex = [BitConverter]::ToString($pesterShaBytes).Replace('-', '')
if (-not (Testar-Hash $pesterPackage 'SHA512' $pesterShaHex)) {
    if (Test-Path -LiteralPath $pesterPackage) { Remove-Item -LiteralPath $pesterPackage -Force }
    Write-Host 'Baixando Pester 5.7.1...'
    Invoke-WebRequest -Uri 'https://www.powershellgallery.com/api/v2/package/Pester/5.7.1' -OutFile $pesterPackage -UseBasicParsing -TimeoutSec 300
    if (-not (Testar-Hash $pesterPackage 'SHA512' $pesterShaHex)) {
        Remove-Item -LiteralPath $pesterPackage -Force -ErrorAction SilentlyContinue
        throw 'Hash SHA-512 do pacote Pester nao confere.'
    }
}

$modulos = Join-Path $pacotes 'powershell-modules'
$pesterDir = Join-Path $modulos 'Pester\5.7.1'
$pesterManifest = Join-Path $pesterDir 'Pester.psd1'
if (-not (Test-Path -LiteralPath $pesterManifest)) {
    if (Test-Path -LiteralPath $pesterDir) { Remove-Item -LiteralPath $pesterDir -Recurse -Force }
    New-Item -ItemType Directory -Path $pesterDir -Force | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($pesterPackage, $pesterDir)
}
if (-not (Test-Path -LiteralPath $pesterManifest)) { throw 'O modulo Pester nao foi extraido corretamente.' }

$scriptAnalyzer = Join-Path $raiz 'testes\5_TESTE_ferramentas_externas\baixar_psscriptanalyzer.ps1'
if (-not (Test-Path -LiteralPath $scriptAnalyzer)) { throw 'O script para baixar PSScriptAnalyzer nao foi encontrado.' }
& $scriptAnalyzer

# O manifesto permite conferir o conjunto que deve ser copiado para o computador offline.
$manifesto = Join-Path $pacotes 'SHA256.txt'
$linhas = @()
foreach ($arquivo in (Get-ChildItem -LiteralPath $pacotes -File -Recurse | Where-Object { $_.FullName -ne $manifesto } | Sort-Object FullName)) {
    $relativo = $arquivo.FullName.Substring($pacotes.Length + 1).Replace('\', '/')
    $hash = (Get-FileHash -LiteralPath $arquivo.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $linhas += "$hash  $relativo"
}
Set-Content -LiteralPath $manifesto -Value $linhas -Encoding ASCII
Write-Host "Pacotes offline prontos em $pacotes (Python x64, ferramentas Python, Pester, PSScriptAnalyzer e Nmap)."
Write-Host 'O pip-audit esta empacotado, mas precisa de internet ou de uma base local atualizada para consultar vulnerabilidades.'
