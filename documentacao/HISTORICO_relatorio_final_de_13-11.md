<!-- ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt -->
# Cofre de Senhas — relatório final (13/11/2026)

> Registro histórico anterior à adoção da marca **Arca**, produto da **Arca Sistemas**. Os resultados e nomes abaixo descrevem o estado do projeto naquela data.

## 1. Resultado em uma linha
Suíte completa: **77 testes, 0 falhas** (Linux/simulado). bandit: 0 achados médios/altos; pip-audit: nenhuma vulnerabilidade conhecida. **Nada disto foi executado em Windows real:** veja a seção 7 (há um teste novo para isso).

## 2. Camadas de segurança
| Camada | O que é |
|---|---|
| 0 | Meio físico: pendrive com BitLocker (portátil) **ou** pasta NTFS só com a sua conta e o SISTEMA (modo no computador) |
| 1 | **Computador autorizado** (até 8; MachineGuid + UUID da placa-mãe) com **reforço DPAPI** (opcional) |
| 2 | **Senha mestra** (mín. 14 caracteres, Argon2id) + **chave de acesso** (modos OU/E/S) |
| 3 | **Chave de segurança FIDO2** (USB/NFC; sem biometria) |
| 4 | **Código de recuperação** (substitui só FIDO/computador; nunca senha nem chave de acesso) |
| Execução | ChaCha20-Poly1305 dentro de AES-256-GCM, cabeçalho como AAD, anti-depuração, bloqueio automático (padrão 3 min), autodestruição, memória zerada, área de transferência fora do Win+V e limpa em 15 s, arquivos de apoio ocultos |
| Impressão | Só chave de acesso e código de recuperação, com a senha mestra antes e nome `Documento_Sistema` |

## 3. O que mudou nesta rodada
1. **Biometria removida** (Windows Hello/digital/rosto): FIDO agora só aceita chave de segurança física (`hints: security-key`, PIN da própria chave). Código, telas, testes e documentação ajustados; pontuação de proteção recalculada.
2. **Falha real corrigida:** o núcleo aceitava senha mestra de 1 caractere (só a tela exigia 14). Agora `Cofre.criar` e `trocar_senha` recusam menos de 14.
3. **Endurecimento de DLLs:** `blindar_processo()` pré-carrega `wer`, `wtsapi32`, `dwmapi` e `webauthn` da System32 por caminho completo (somado a `SetDllDirectoryW("")` e `PreferSystem32Images`). Só atua no Windows.
4. **Teste nativo para Windows** (`testes\4_so_no_windows\B - testar atributos e permissoes do Windows.bat`): atributos de arquivo, ACL, SMBIOS × PowerShell, DPAPI, computador autorizado de ponta a ponta, blindagens/DLLs, WebAuthn. Usa pasta temporária e nunca toca no seu cofre.
5. Documentação: README (testes, instalação), MODELO_DE_AMEACAS (adendos 9 a 13; corrigi a frase que dizia que o `.bat` confere contra o papel: ele confere contra o `.sha256` ao lado; a conferência com o papel é manual).

## 4. Testes técnicos e de invasão (resultado)
- **Auditoria técnica** (`teste_tecnico_sistema.py`): sem segredo fixo, sem `eval/exec/pickle/shell=True`, rede só na consulta opcional HIBP (prefixo de 5 caracteres), registro só leitura, DLLs todas KnownDLLs ou pré-carregadas, 20 000 mutações de cabeçalho só com erros esperados, sem canal de tempo.
- **Red team** (`teste_red_team.py`, 3 execuções limpas): o arquivo mostra só `COFRE05` + ruído (entropia ≈ 7,99); 1 bit alterado em qualquer lugar é recusado; outro computador é barrado **antes** do Argon2 e sem gastar tentativa.
- **Custo de força bruta** (por tentativa ≈ 1,1 s no Alto e ≈ 5,9 s no Máximo por núcleo): senha de 50 bits com 1 PC ≈ 1e7 anos; senha de 40 bits com 10 000 núcleos ≈ 349 dias. **Senha fraca é o ponto frágil.**

## 5. O que um atacante com Ghidra/IDA/x64dbg/Wireshark/ProcMon etc. consegue
- **Com só o arquivo do cofre:** nada além de metadados (modo, parâmetros do Argon2, se há FIDO/computador). Só resta força bruta offline. O contador de tentativas pode ser zerado editando o arquivo (fica fora do AAD de propósito): a autodestruição protege contra quem usa o programa, **não** contra quem copia o arquivo.
- **Com escrita na pasta desbloqueada:** pode trocar `.exe`, `.sha256` e `.bat` juntos por uma versão que captura a senha. Defesa: BitLocker + comparar à mão o SHA-256 anotado em papel.
- **Com depurador/RAM depois de desbloqueado:** vê o que está aberto. Anti-depuração e zeragem reduzem, não eliminam.
- **Com acesso físico ao PC autorizado e sessão aberta:** o fator computador/DPAPI não protege.
- **Chave de acesso guardada na mesma pasta do cofre** anula os modos E/OU.
- **Ferramentas de rede (Burp, Nmap, Metasploit, Nessus):** o programa não abre porta nem serviço; não há superfície de rede a testar além do HIBP.

## 6. Respostas diretas
- **Ofuscação (PyArmor) + auto-checksum:** não adotei. O Nuitka já compila para C; ofuscar não é fronteira de segurança, e quem remenda o binário remenda a checagem. A defesa real é BitLocker + hash em papel.
- **Já implementados:** limpeza da área de transferência (15 s, sem histórico/nuvem), bloqueio automático (1–30 min, ao minimizar/perder foco), FIDO2, zeragem de memória.
- **Segurança não depende só de senha + DPAPI:** o DPAPI é só o reforço opcional do fator computador.

## 7. Testes no Windows real (feitos agora)
Rodei `testes\4_so_no_windows\B - testar atributos e permissoes do Windows.bat` no seu computador, no disco e no pendrive H:: **39 e depois 46 verificações, 0 falhas** (as 7 extras são os mesmos atributos de arquivo repetidos no pendrive). Confirmado de verdade (não simulado):
atributos oculto/sistema/somente-leitura (e o `attrib` do Windows concorda, no disco e no pendrive), ACL por `icacls` (só você + SISTEMA, sem Everyone/Users/Administrators — com Administradores presente, esperado),
UUID do SMBIOS batendo exatamente com o PowerShell, DPAPI (cria/lê/recusa adulteração/restaura), computador autorizado de ponta a ponta (ativa, reconhece,
barra sem o segredo, recupera pelo código), as 6 blindagens do processo incluindo as 4 DLLs pré-carregadas da System32, e WebAuthn disponível (API v9).
Corrigi um detalhe apontado por você: o teste criava seu ambiente em `%TEMP%`; agora fica todo dentro de `testes\4_so_no_windows\` e se apaga sozinho.

Também rodei `testes\4_so_no_windows\A - testar o instalador.bat` (instalador/`Abrir_Cofre.bat`/Pester): **sintaxe do instalador OK, os 7 testes do `.bat` (íntegro/adulterado/ausente, x64/ARM64) OK, Pester OK (10/0)**. Esse script teve um bug de sintaxe meu (um aviso novo quebrava o PowerShell: `$pai:` era lido como um prefixo de unidade) — corrigido para `${pai}:`. Depois da correção, descobri que a bateria do núcleo (77 testes) ainda não rodava porque `testes\rodar_todos.py` e os `testes\teste_*.py` não estavam na pasta consolidada — só `testes\4_so_no_windows\`. Agora toda a pasta `testes\` (84 arquivos: núcleo, GUI, pytest e os dois READMEs) está dentro de `Downloads\CofreSenhas-Instalador`, junto com tudo o mais, para a bateria completa rodar de verdade no seu Windows.

## 8. O que ainda falta testar (opcional)
O instalador PowerShell completo de ponta a ponta (`instalar_cofre.ps1`: compilação com Nuitka, tempo de instalação) e a chave FIDO2/PRF com uma chave física real. Rode `A - testar o instalador.bat` mais uma vez agora que `rodar_todos.py` está na pasta: a bateria do núcleo (77 testes) deve executar e aparecer linha a linha no `resultado_teste_windows.txt`.

## 9. Cuidados
- Anote o código de recuperação ao ativar computador autorizado (aparece uma vez).
- A folha impressa da chave ou do código **é uma credencial**; a fila do Windows guarda cópia temporária em C:.
- Em ARM64 apague `pacotes\` (x64).
- Apague manualmente o `Downloads\instalar_cofre.ps1` solto (versão antiga).

## 10. Arquivos
`cofre_senhas.py`, `instalar_cofre.ps1`, `1 - INSTALAR O COFRE - compila e instala.bat`, `MANUAL_COMPLETO.md`, `MODELO_DE_AMEACAS.md`, `pacotes\`, `testes\…`, `logs\suite_completa.log`, `docs\HISTORICO_sha256_do_programa.txt`.
