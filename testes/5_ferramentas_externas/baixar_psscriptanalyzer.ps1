# Baixa o modulo PSScriptAnalyzer para pacotes\powershell-modules (precisa de internet so aqui).
# Depois de baixar, ANOTE o SHA-512 impresso e fixe-o neste script (o pacote Pester do projeto ja e conferido assim).
$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$versao = '1.24.0'
$destino = Join-Path $raiz "pacotes\powershell-modules\PSScriptAnalyzer\$versao"
$nupkg = Join-Path $raiz "pacotes\PSScriptAnalyzer-$versao.nupkg"
Invoke-WebRequest -Uri "https://www.powershellgallery.com/api/v2/package/PSScriptAnalyzer/$versao" -OutFile $nupkg -UseBasicParsing -TimeoutSec 300
$sha = (Get-FileHash -LiteralPath $nupkg -Algorithm SHA512).Hash
Write-Host "SHA-512 de $versao (confira no PowerShell Gallery e fixe aqui): $sha"
New-Item -ItemType Directory -Path $destino -Force | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory($nupkg, $destino)
Write-Host "Pronto: $destino"
