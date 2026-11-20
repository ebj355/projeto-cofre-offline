# Testes unitários (Pester) das funções auxiliares do instalar_cofre.ps1: hash, arquitetura, sistema de arquivos,
# espaço em disco, certificado, limpeza de caminhos e log. Roda com Pester 3, 4 ou 5 (só usa Describe/It/BeforeAll e 'throw').
# Como rodar:  powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-Pester -Path .\instalador.Tests.ps1"
# (o A - testar o instalador.bat já roda isto sozinho se o Pester existir no Windows)

Describe 'instalar_cofre.ps1: funções auxiliares' {
    BeforeAll {
        $aqui = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
        $script:instalador = Join-Path (Split-Path (Split-Path $aqui -Parent) -Parent) 'instalar_cofre.ps1'
        . $script:instalador      # só define as funções: o arquivo não instala nada quando é carregado assim
    }

    It 'Confirmar-PalavraApagar aceita maiúsculas e minúsculas, mas exige a palavra exata' {
        foreach ($valor in 'APAGAR', 'apagar', 'ApAgAr') {
            if (-not (Confirmar-PalavraApagar $valor)) { throw "devia aceitar: '$valor'" }
        }
        foreach ($valor in '', 'APAGA', 'APAGAR ') {
            if (Confirmar-PalavraApagar $valor) { throw "devia recusar: '$valor'" }
        }
    }

    It 'Test-PrefixoSha256 aceita 16+ caracteres iguais ao início do hash (sem diferenciar maiúsculas)' {
        $h = 'A1B2C3D4E5F60718293A4B5C6D7E8F90A1B2C3D4E5F60718293A4B5C6D7E8F90' # pragma: allowlist secret
        if (-not (Test-PrefixoSha256 $h 'a1b2c3d4e5f60718')) { throw 'devia aceitar' } # pragma: allowlist secret
        if (-not (Test-PrefixoSha256 $h '  A1B2C3D4E5F60718293A  ')) { throw 'devia aceitar com espaços' }
    }
    It 'Test-PrefixoSha256 recusa curto, errado, vazio e não-hexadecimal' {
        $h = 'A1B2C3D4E5F60718293A4B5C6D7E8F90A1B2C3D4E5F60718293A4B5C6D7E8F90' # pragma: allowlist secret
        foreach ($ruim in 'a1b2c3d4e5f6071', 'a1b2c3d4e5f60719', '', 'n', 'a1b2c3d4e5f6071g', '................') { # pragma: allowlist secret
            if (Test-PrefixoSha256 $h $ruim) { throw "devia recusar: '$ruim'" }
        }
        if (Test-PrefixoSha256 '' 'a1b2c3d4e5f60718') { throw 'hash vazio não pode aceitar nada' } # pragma: allowlist secret
    }
    It 'Test-ArquiteturaArm reconhece ARM64 e não confunde com x64' {
        if (-not (Test-ArquiteturaArm 'Arm64')) { throw 'Arm64' }
        if (-not (Test-ArquiteturaArm 'ARM64')) { throw 'ARM64' }
        foreach ($x in 'X64', 'AMD64', 'x86', '') { if (Test-ArquiteturaArm $x) { throw "não é ARM: '$x'" } }
    }
    It 'Get-AvisoSistemaArquivos: NTFS/ReFS sem aviso; FAT32/exFAT/desconhecido com aviso' {
        foreach ($ok in 'NTFS', 'ntfs', 'ReFS') { if (Get-AvisoSistemaArquivos $ok) { throw "sem aviso para $ok" } }
        foreach ($fs in 'FAT32', 'exFAT', 'FAT') {
            $a = Get-AvisoSistemaArquivos $fs
            if (-not $a -or $a -notmatch $fs.ToUpper()) { throw "aviso esperado para $fs" }
        }
        if (-not (Get-AvisoSistemaArquivos '')) { throw 'aviso esperado quando o sistema de arquivos não é conhecido' }
    }
    It 'Test-EspacoSuficiente: ok, pouco e desconhecido' {
        if ((Test-EspacoSuficiente 5GB 3GB) -ne 'ok') { throw '5 GB de 3 GB' }
        if ((Test-EspacoSuficiente 3GB 3GB) -ne 'ok') { throw 'exatamente 3 GB' }
        if ((Test-EspacoSuficiente 2.9GB 3GB) -ne 'pouco') { throw '2,9 GB' }
        if ((Test-EspacoSuficiente 0 3GB) -ne 'pouco') { throw 'zero' }
        if ((Test-EspacoSuficiente $null 3GB) -ne 'desconhecido') { throw 'nulo' }
    }
    It 'Get-EspacoLivreBytes usa o valor do WMI e, sem ele, tenta a unidade' {
        $v = New-Object psobject -Property @{ FreeSpace = 123456789 }
        if ((Get-EspacoLivreBytes 'Z' $v) -ne 123456789) { throw 'devia usar o WMI' }
        $r = Get-EspacoLivreBytes '?' $null          # unidade inexistente: não pode lançar erro
        if ($null -ne $r) { throw 'unidade inexistente devia dar nulo' }
    }
    It 'Test-Thumbprint exige exatamente 40 hexadecimais' {
        if (-not (Test-Thumbprint ('AB' * 20))) { throw '40 hex' }
        if (-not (Test-Thumbprint (('ab' * 20) + ' '))) { throw 'com espaço no fim' }
        foreach ($ruim in '', 'abc', ('AB' * 19), ('AB' * 21), ('GH' * 20)) { if (Test-Thumbprint $ruim) { throw "devia recusar '$ruim'" } }
    }
    It 'Remove-Caminhos tira caminhos de disco, de rede e o nome do usuário' {
        $t = Remove-Caminhos 'Erro em H:\_cb\src\cofre_senhas.py e \\servidor\pasta\arq.txt'
        if ($t -match 'H:\\' -or $t -match 'servidor' -or $t -notmatch '<caminho>') { throw "restou caminho: $t" }
        $antes = $env:USERNAME; $env:USERNAME = 'fulano_teste'
        try { $u = Remove-Caminhos 'usuário fulano_teste falhou' } finally { $env:USERNAME = $antes }
        if ($u -match 'fulano_teste') { throw "restou o usuário: $u" }
    }
    It 'Add-LogDetalhado grava linhas com data e Limitar-Arquivo mantém só o final' {
        $arq = Join-Path ([IO.Path]::GetTempPath()) ("cofre_log_teste_" + [guid]::NewGuid().ToString('N') + '.log')
        try {
            Add-LogDetalhado $arq @('INSTALACAO resultado=ok', '  etapa="x" tempo=1 s')
            $l = @(Get-Content -LiteralPath $arq -Encoding UTF8)
            if ($l.Count -ne 2 -or $l[0] -notmatch '^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d INSTALACAO resultado=ok$') { throw "formato: $($l -join '|')" }
            1..400 | ForEach-Object { Add-LogDetalhado $arq @("linha de enchimento numero $_ " + ('x' * 100)) }
            Limitar-Arquivo $arq 20000
            $depois = Get-Item -LiteralPath $arq
            if ($depois.Length -ge 60000) { throw "não encolheu: $($depois.Length)" }
            $ult = @(Get-Content -LiteralPath $arq -Encoding UTF8)[-1]
            if ($ult -notmatch 'numero 400') { throw 'o final (mais recente) devia ser mantido' }
        } finally { Remove-Item -LiteralPath $arq -Force -ErrorAction SilentlyContinue }
    }
    It 'Get-InstalacaoLegada encontra o diretório antigo e classifica dados sem revelá-los' {
        $raiz = Join-Path ([IO.Path]::GetTempPath()) ("cofre_legado_teste_" + [guid]::NewGuid().ToString('N'))
        $pasta = Join-Path $raiz 'CofreSenhas'
        try {
            New-Item -ItemType Directory -Path $pasta -Force | Out-Null
            if (Get-InstalacaoLegada $raiz) { throw 'uma pasta vazia não deve ser identificada como instalação antiga' }
            Set-Content -LiteralPath (Join-Path $pasta 'CofreSenhas.exe') -Value 'programa'
            Set-Content -LiteralPath (Join-Path $pasta 'cofre.dat') -Value 'dados cifrados'
            Set-Content -LiteralPath (Join-Path $pasta 'acesso.key') -Value 'chave'
            $legada = Get-InstalacaoLegada $raiz
            if (-not $legada -or $legada.Path -ne $pasta) { throw 'a pasta antiga não foi encontrada' }
            if ($legada.Programas -notcontains 'CofreSenhas.exe') { throw 'o executável antigo não foi classificado' }
            if ($legada.Cofres -notcontains 'cofre.dat' -or $legada.Chaves -notcontains 'acesso.key') { throw 'os dados ou a chave não foram identificados' }
        } finally { Remove-Item -LiteralPath $raiz -Recurse -Force -ErrorAction SilentlyContinue }
    }
    It 'Remove-ProgramaLegado apaga só o programa antigo e preserva cofre, backup e chave' {
        $pasta = Join-Path ([IO.Path]::GetTempPath()) ("cofre_remocao_teste_" + [guid]::NewGuid().ToString('N'))
        try {
            New-Item -ItemType Directory -Path $pasta -Force | Out-Null
            foreach ($nome in 'CofreSenhas.exe', 'Abrir_Cofre.bat', 'cofre.dat', 'cofre.dat.bak1', 'acesso.key') {
                Set-Content -LiteralPath (Join-Path $pasta $nome) -Value 'teste'
            }
            $resultado = Remove-ProgramaLegado $pasta
            if ($resultado.Falhas.Count -gt 0) { throw "falha ao remover programa: $($resultado.Falhas -join ', ')" }
            if (Test-Path -LiteralPath (Join-Path $pasta 'CofreSenhas.exe')) { throw 'o executável antigo permaneceu' }
            foreach ($nome in 'cofre.dat', 'cofre.dat.bak1', 'acesso.key') {
                if (-not (Test-Path -LiteralPath (Join-Path $pasta $nome))) { throw "$nome não deveria ser apagado" }
            }
        } finally { Remove-Item -LiteralPath $pasta -Recurse -Force -ErrorAction SilentlyContinue }
    }
    It 'carregar o instalador com ponto não instala nada (guarda de execução)' {
        if (-not (Get-Command Instalar-Cofre -ErrorAction SilentlyContinue)) { throw 'Instalar-Cofre devia estar definida' }
    }
}
