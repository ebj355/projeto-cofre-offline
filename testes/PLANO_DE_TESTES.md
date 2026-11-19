# Plano de testes — Cofre de Senhas (por risco, ISO 25010 / ISTQB)

## QA1 — Revisão do recurso (testes estáticos)
**Recurso:** cofre local de senhas em um arquivo (`cofre.dat`), aberto por senha mestra e/ou chave de acesso e/ou chave FIDO2,
distribuído como `CofreSenhas.exe` compilado num pendrive com BitLocker.
**Lacunas conhecidas (aceitas, ver MODELO_DE_AMEACAS.md):** malware/keylogger no PC; Windows não testado por mim (só pelo
`A - testar o instalador.bat`); FAT/exFAT sem ACL; sem Authenticode; janela TOCTOU entre conferir e abrir o .exe; texto não-ASCII
e cópias do Tcl/Tk/pagefile na memória.
**Riscos de produto:** (R1) perder o acesso aos dados; (R2) corrupção ao salvar; (R3) vazar segredo (arquivo, memória,
área de transferência, tela); (R4) programa trocado no pendrive; (R5) força bruta/ataque offline; (R6) importação de
planilha maliciosa; (R7) falha só no Windows.

## QA2 — Plano
**Em escopo (diferente do modelo-base):** Adequação funcional, Confiabilidade, Eficiência, Compatibilidade **e Segurança**
(para um cofre, segurança é o objetivo principal; por isso entra). **Fora:** Portabilidade (só Windows 10/11 x64).
**Ambiente:** Linux (Python 3.12/3.13, Xvfb) para lógica e interface; Windows 10/11 real para o instalador, .bat e API do
Windows (`A - testar o instalador.bat`). **Entrada:** `python -m py_compile` sem erro. **Saída (Go):** todas as seções da bateria
com `FALHAS: []`, `teste_windows` sem [FALHOU], instalador concluído com o auto-teste do .bat OK.

| Risco | Impacto | Prob. | Mitigação no produto | Tipo de teste |
|---|---|---|---|---|
| R1 perder acesso | Crítico | Média | 2 cópias .bak, chave de acesso, códigos de recuperação, rollback | backup, severo, transacao |
| R2 corrupção ao salvar | Crítico | Média | gravação atômica, checksum, `transacao` com rollback | transacao, severo, limites |
| R3 vazamento | Alto | Média | AES+ChaCha, zerar memória, clipboard com sequência, DACL | ataques, memoria, limites |
| R4 exe trocado | Alto | Baixa | SHA-256 conferido pelo .bat | teste_windows (bat 0/3) |
| R5 força bruta | Alto | Média | Argon2id, autodestruição, contador | ataques, forca |
| R6 planilha maliciosa | Médio | Média | limites de tamanho/linhas, defusedxml, limpeza de texto | importacao, fuzzing, Hypothesis |
| R7 só no Windows | Alto | Alta | script de teste no Windows real | teste_windows |

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
| TC14 | .bat: exe íntegro / 1 byte trocado / sem .sha256 | Alta | exit 0 / 3 / 2 | instalador (auto-teste) + teste_windows |
| TC15 | README cita constantes reais | Baixa | valores do texto = do código | teste_readme_constantes |
| TC16 | Desempenho | Média | abrir 3000 itens ≈ 0,5 s; salvar ≈ 0,02 s; Argon2 "alto" ≈ 0,5 s | medido (não-gate) |
| TC17 | Ida e volta e entrada CSV arbitrária | Média | Hypothesis gera textos/itens para criar, salvar e reabrir; bytes hostis no CSV não podem gerar exceção não tratada | `teste_propriedades_hypothesis.py` (opcional; `[PULADO]` se Hypothesis indisponível) |

## Rastreabilidade e lacunas
Todo risco R1–R7 tem teste. **Lacunas abertas:** R7/TC14 só passam de verdade no Windows do usuário; não há teste de
acessibilidade (leitor de tela) nem de DPI alto; FIDO2 real só com a chave física.

## Go / No-Go
No-Go se: qualquer `FALHAS` não vazio; qualquer teste obrigatório estiver `[PULADO]`; qualquer `Traceback` que não seja `ResourceWarning` do `-W error` dos testes;
hash do .exe diferente do `.sha256`; `teste_windows` com [FALHOU]. Pós-instalação: abrir pelo `Abrir_Cofre.bat`, criar
item, fechar, reabrir, conferir que sobraram só `.dat`, `.bak1` a `.bak5` e `.diag`. Se o computador for ARM64, o
instalador deve gerar `CofreSenhas-arm64.exe` + `CofreSenhas-arm64.sha256` e o `Abrir_Cofre.bat` deve abri-lo.

## Acréscimos de 2026-11-19
`teste_propriedades_hypothesis.py` adiciona geração de casos para ida e volta dos registros e CSVs hostis; é descoberto automaticamente por `rodar_todos.py`. Se o pacote opcional não estiver disponível, o código 9 vira `[PULADO]`, não uma falsa aprovação nem uma falha. A bateria externa inclui 05–12: PSScriptAnalyzer, proteções PE, Defender, segredos no repositório, qualidade extra, auditoria/SBOM, conexões do processo e o atalho Hypothesis. O teste pytest (03) continua fora do Testar Tudo por repetir núcleo e interface.

ProcDump e compilação reproduzível não fazem parte do plano atual: o primeiro precisa de um binário externo com hash verificado; a segunda é demorada e ainda não foi implementada. As versões mínimas (`>=`) das ferramentas novas em `requirements-test.txt` devem ser fixadas em `==` depois que `3 - BAIXAR PACOTES` gerar os wheels correspondentes.


## Acréscimos de 2026-11-16
Novos testes: concorrência real entre processos, objetos sensíveis no coletor de lixo, esquema hostil de itens, mensagens da chave FIDO (sem PIN / PIN bloqueado), caminhos especiais, superfície do instalador, rede bloqueada, resíduos em disco com entropia, ocultação contínua e resiliência da interface (cliques frenéticos, texto absurdo, perda de foco, ciclos sem vazamento, janelas modais, tela de integridade, aviso do pendrive). Detalhes e justificativas em README (seção 9) e MODELO_DE_AMEACAS (adendos 22 e 23). Saídas de depuração: `log_depuracao.txt`, `resumo_testes.md/json`, `resultados.sarif`.
