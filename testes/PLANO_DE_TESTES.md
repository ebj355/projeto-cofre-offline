# Plano de testes — Cofre de Senhas (por risco, ISO 25010 / ISTQB)

## QA1 — Revisão do recurso (testes estáticos)
**Recurso:** cofre local de senhas em um arquivo (`cofre.dat`), aberto por senha mestra e/ou chave de acesso e/ou chave FIDO2,
distribuído como `CofreSenhas.exe` compilado num pendrive com BitLocker.
**Lacunas conhecidas (aceitas, ver MODELO_DE_AMEACAS.md):** malware/keylogger no PC; FAT/exFAT sem ACL; sem Authenticode;
janela TOCTOU entre conferir e abrir o .exe; texto não-ASCII e cópias do Tcl/Tk/pagefile na memória; smoke test automático
do executável, máquina limpa, pendrive físico, memória baixa, mutação, Atheris e SmartScreen ainda não foram validados.
A bateria completa registrada em 2026-11-20 teve 2.321 verificações OK, zero falhas e três pulos condicionais (pefile e
Defender sem `.exe` compilado; conexões do processo sem o executável aberto); PSScriptAnalyzer e qualidade extra geraram
alertas que impedem declarar Go até serem revisados. Houve validações focadas posteriores, mas
a bateria completa não foi repetida depois delas. Não há evidência registrada de execução no Windows Sandbox.
O ambiente e o status de validação do Windows devem seguir a matriz única em `COMO_RODAR_OS_TESTES.md` (seção
"Status do Windows e versões"), sem inferir aprovação da bateria completa apenas pela disponibilidade do host.
**Riscos de produto:** (R1) perder o acesso aos dados; (R2) corrupção ao salvar; (R3) vazar segredo (arquivo, memória,
área de transferência, tela); (R4) programa trocado no pendrive; (R5) força bruta/ataque offline; (R6) importação de
planilha maliciosa; (R7) falha só no Windows.

## QA2 — Plano
**Em escopo (diferente do modelo-base):** Adequação funcional, Confiabilidade, Eficiência, Compatibilidade **e Segurança**
(para um cofre, segurança é o objetivo principal; por isso entra). **Fora:** Portabilidade (só Windows 10/11 x64).
**Ambiente:** Linux x64 (Python 3.12/3.13, Xvfb) para lógica e interface; Windows 10/11 x64 para o instalador e APIs do
Windows. Windows 11 ARM64 pode usar o executável x64 sob emulação; build nativo ARM64 não é suportado. **Entrada:**
`python -m py_compile` sem erro. **Saída (Go):** testes obrigatórios sem falhas nem pulos sem justificativa.

| Risco | Impacto | Prob. | Mitigação no produto | Tipo de teste |
|---|---|---|---|---|
| R1 perder acesso | Crítico | Média | 2 cópias .bak, chave de acesso, códigos de recuperação, rollback | backup, severo, transacao |
| R2 corrupção ao salvar | Crítico | Média | gravação atômica, checksum, `transacao` com rollback | transacao, severo, limites |
| R3 vazamento | Alto | Média | AES+ChaCha, zerar memória, clipboard com sequência, DACL | ataques, memoria, limites |
| R4 exe trocado | Alto | Baixa | BitLocker e SHA-256 anotado fora do pendrive; conferência manual no programa | verificação manual + teste do executável pendente |
| R5 força bruta | Alto | Média | Argon2id, autodestruição, contador | ataques, forca |
| R6 planilha maliciosa | Médio | Média | limites de tamanho/linhas, defusedxml, limpeza de texto | importacao, fuzzing, Hypothesis |
| R7 só no Windows | Alto | Alta | workflow `windows-latest` + testes nativos | CI Windows, teste_windows |

## QA3 — Catálogo (resumo; cada linha é executada por `testes/`)
| ID | Condição | Pri. | Passos → esperado | Automação |
|---|---|---|---|---|
| TC01 | Criar/abrir com senha normal | Alta | criar, fechar, abrir → abre | todas |
| TC02 | Senha vazia | Alta | criar("") → recusa (ValueError) | teste_limites |
| TC03 | Senha extrema (1 char, NUL, 300 mil, emoji, NFC/NFD) | Média | criar+abrir → abre | teste_limites |
| TC04 | Itens extremos (None, 3 MB, `=cmd`, RLO, `<script>`) | Média | salvar+reabrir → íntegro | teste_limites |
| TC05 | Senha errada N vezes | Alta | N erros → autodestruição | teste_ataques |
| TC06 | Arquivo adulterado (1 byte, cabeçalho, truncado) | Alta | abrir → erro claro, nunca trava | teste_ataques, severo |
| TC07 | Falha de disco ao salvar | Alta | exceção → memória e disco voltam ao estado anterior | teste_transacao |
| TC08 | Restos de segredo na memória após fechar | Alta | scan externo de /proc/pid/mem → só o piso | teste_memoria |
| TC09 | `zerar_objeto` não corrompe vizinhos/internados | Alta | memset em objetos vizinhos → intactos | teste_limites |
| TC10 | 60 ciclos abrir/fechar | Média | RSS < +4 MB, objetos estáveis | teste_limites |
| TC11 | Importar planilha/CSV ruim | Média | recusa/ignora linha, sem travar | teste_importacao |
| TC12 | Chave FIDO ausente/errada | Média | mensagem clara, sem perder o cofre | teste_fido |
| TC13 | Fluxos de tela (abrir, editar, excluir, bloquear) | Média | sem exceção, estado coerente | gui_teste, gui_forca, teste_alerta |
| TC14 | Conferir o executável instalado | Alta | Abrir `CofreSenhas.exe`; comparar o SHA-256 mostrado ao valor anotado em papel | manual; smoke automatizado pendente |
| TC15 | README cita constantes reais | Baixa | valores do texto = do código | teste_readme_constantes |
| TC16 | Desempenho | Média | abrir 3000 itens ≈ 0,5 s; salvar ≈ 0,02 s; Argon2 "alto" ≈ 0,5 s | medido (não-gate) |
| TC17 | Ida e volta e entrada CSV arbitrária | Média | Hypothesis gera textos/itens para criar, salvar e reabrir; bytes hostis no CSV não podem gerar exceção não tratada | `teste_propriedades_hypothesis.py` (opcional; `[PULADO]` se Hypothesis indisponível) |
| TC18 | Backup externo e restauração | Alta | criar um cofre descartável, salvar backup cifrado em outro dispositivo, simular perda do original e restaurar/abrir o backup | ensaio manual pendente |
| TC19 | Instalação legada | Alta | detectar `<destino>\CofreSenhas`; oferecer atualização no local ou manter a pasta antiga; remoção exige `APAGAR` e preserva cofre, backups e chaves | Pester (`instalador.Tests.ps1`, auxiliares; 12/12 em execução focada) |

## Rastreabilidade e lacunas
Todo risco R1–R7 tem mitigação ou teste, mas nem todos têm automação. **Lacunas abertas:** smoke do `.exe`, instalação em
máquina limpa, pendrive removido durante gravação, FAT32/exFAT/NTFS, memória de 4 GB, vetores publicados AES/ChaCha/Argon2,
teste de mutação, Atheris, SmartScreen, leitor de tela e DPI alto; FIDO2 real só com chave física. A rodada Windows de
2026-11-20 registra edição/build e versão do Python; futuras execuções devem manter essa identificação.

## Go / No-Go
No-Go se: qualquer `FALHAS` não vazio; qualquer teste obrigatório estiver `[PULADO]`; qualquer `Traceback` que não seja
`ResourceWarning` dos testes; `teste_windows` registrar [FALHOU]; ou uma ferramenta obrigatória terminar em `[ALERTA]`
ou código diferente de zero sem justificativa aprovada. `[OK]` agregado da bateria não apaga alertas individuais.

**Testes obrigatórios:** baterias de núcleo e interface; teste Windows e Pester do instalador em Windows x64; ferramentas
01 (Bandit), 05 (PSScriptAnalyzer), 08 (segredos e arquivos rastreados), 09 (qualidade extra), 12 (Hypothesis) e 13
(integridade do repositório, manifests e arquivos ignorados). Para release, também são obrigatórios 02/10 (`pip-audit`)
com consulta online atualizada. Ausência de ferramenta ou erro nesses testes é No-Go.
O workflow Windows deve ficar verde em cada pull request; sua configuração, por si só, não conta como resultado aprovado.

**Condicionais, com justificativa registrada:** 04 (Nmap, se instalado); as verificações de PE, Defender e rede do
processo ficam separadas em `7_TESTE_de_compilacao/` e só rodam no Testar Tudo quando solicitado por
`POS-COMPILACAO`. Compile o `.exe` primeiro; pefile/Defender exigem o executável compilado e a rede exige que ele esteja
aberto. Verificações físicas de FIDO2, pendrive e Windows Sandbox também dependem dos respectivos dispositivos/ambientes.
`OFFLINE` pula a consulta do `pip-audit` e não equivale a uma aprovação de segurança. TC14 é manual: abrir diretamente
`CofreSenhas.exe`, comparar o SHA-256 mostrado ao anotado fora do pendrive, criar um item, fechar e reabrir. Não há
`Abrir_Cofre.bat`, arquivo `.sha256` lateral nem executável ARM64 nesta versão.

**Ensaio de restauração (TC18):** use um cofre descartável, crie um backup criptografado em outro dispositivo, feche o
programa, renomeie o arquivo de teste original e restaure a cópia pelo fluxo documentado. Confirme que abre e que os
registros estão íntegros. Nunca faça o ensaio com o cofre real nem provoque erros de senha no cofre de produção.

**TC19 é um teste auxiliar, não um ensaio destrutivo:** o Pester chama funções isoladas e usa caminhos temporários; a
execução focada de 2026-11-20 passou 12/12. A escolha interativa entre atualizar, manter ou remover a instalação antiga
e uma compilação/instalação ponta a ponta ainda precisam de validação separada.

## Acréscimos de 2026-11-16
Novos testes: concorrência real entre processos, objetos sensíveis no coletor de lixo, esquema hostil de itens, mensagens da chave FIDO (sem PIN / PIN bloqueado), caminhos especiais, superfície do instalador, rede bloqueada, resíduos em disco com entropia, ocultação contínua e resiliência da interface (cliques frenéticos, texto absurdo, perda de foco, ciclos sem vazamento, janelas modais, tela de integridade, aviso do pendrive). Detalhes e justificativas em README (seção 9) e MODELO_DE_AMEACAS (adendos 22 e 23). Saídas de depuração: `log_depuracao.txt`, `RESULTADO COMPLETO.txt` (conteúdo de todos os relatórios individuais), `resumo_testes.md/json` e `resultados.sarif`.

## Acréscimos de 2026-11-19
`teste_propriedades_hypothesis.py` gera casos para ida e volta dos registros e CSVs hostis; é descoberto automaticamente
por `rodar_todos.py`. A pasta 5 concentra as ferramentas externas independentes do executável; a pasta opcional
`7_TESTE_de_compilacao/` reúne proteções PE, Defender e conexões do processo, executadas depois de compilar o `.exe`.
O pytest (03) continua fora do Testar Tudo por repetir núcleo e interface. As ferramentas de teste têm versões exatas
em `requirements-test-lock.txt`; o wheelhouse offline contém os pacotes e seu manifesto SHA-256.

## Acréscimos de 2026-11-20
A bateria completa registrada no Windows 11 Pro 10.0.26300 / Python 3.13.9 AMD64 teve 2.321 verificações OK, zero
falhas e três pulos condicionais (pefile e Defender sem `.exe` compilado; conexões do processo sem o executável aberto). PSScriptAnalyzer
e qualidade extra terminaram com `[ALERTA]`, então o resultado não libera Go até a revisão desses achados. Depois dessa
rodada foram validados focadamente o Pester do instalador (12/12), o teste Hypothesis e a limpeza dos caches; a bateria
completa ainda não foi repetida após essas mudanças. TC19 registra a cobertura adicionada para detectar instalação
legada e preservar os dados do cofre.

ProcDump e compilação reproduzível não fazem parte do plano atual: o primeiro precisa de um binário externo com hash
verificado; a segunda é demorada e ainda não foi implementada.
