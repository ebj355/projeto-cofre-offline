# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
# Baixa o modulo PSScriptAnalyzer para pacotes\powershell-modules com o SHA-512 publicado pela Gallery.
$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$versao = '1.24.0'
$destino = Join-Path $raiz "pacotes\powershell-modules\PSScriptAnalyzer\$versao"
$nupkg = Join-Path $raiz "pacotes\PSScriptAnalyzer-$versao.nupkg"
$esperado = [BitConverter]::ToString([Convert]::FromBase64String('B8yVwiGkpN9LU8q7cBZHgBtBIAKgW+FbpVA/ZtSHD65K1FWFTT7nSVfehKL2OuoyufPf8VNcaRfHUTB3Rb3RZQ==')).Replace('-', '')

if ((Test-Path -LiteralPath $nupkg) -and (Get-FileHash -LiteralPath $nupkg -Algorithm SHA512).Hash -ne $esperado) {
    Remove-Item -LiteralPath $nupkg -Force
}
if (-not (Test-Path -LiteralPath $nupkg)) {
    Invoke-WebRequest -Uri "https://www.powershellgallery.com/api/v2/package/PSScriptAnalyzer/$versao" -OutFile $nupkg -UseBasicParsing -TimeoutSec 300
}
if ((Get-FileHash -LiteralPath $nupkg -Algorithm SHA512).Hash -ne $esperado) {
    Remove-Item -LiteralPath $nupkg -Force -ErrorAction SilentlyContinue
    throw "SHA-512 do pacote PSScriptAnalyzer $versao nao confere com o publicado pela PowerShell Gallery."
}
if (-not (Test-Path -LiteralPath (Join-Path $destino 'PSScriptAnalyzer.psd1'))) {
    if (Test-Path -LiteralPath $destino) { Remove-Item -LiteralPath $destino -Recurse -Force }
    New-Item -ItemType Directory -Path $destino -Force | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($nupkg, $destino)
}
Write-Host "PSScriptAnalyzer $versao verificado e pronto: $destino"
