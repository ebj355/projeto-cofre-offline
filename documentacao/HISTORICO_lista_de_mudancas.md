<!-- ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt -->
# Lista de mudanças (2026-11-16)

> A **Arca**, produto da **Arca Sistemas**, é a marca atual do cofre. Os registros abaixo preservam os nomes técnicos e o contexto de quando cada mudança foi feita.

## 1. Programa (`cofre_senhas.py`)
**Mudou / melhorou**
- **Ocultação contínua:** cofre e cópias (`.bak`, `.lock`, `.diag`…) ficam escondidos (Oculto+Sistema+Somente leitura) o tempo todo com o programa aberto e só são liberados no instante de cada gravação (salvar, abrir/contar tentativa, criar, apagar, diagnóstico), inclusive se der erro. Antes só escondiam ao sair.
- **Chave FIDO sem PIN:** mensagem nova que manda criar o PIN nas Configurações do Windows.
- **PIN da chave bloqueado:** mensagem nova (redefinir APAGA as credenciais da chave; usar a 2ª chave ou o código de recuperação; não manda "tentar de novo").
- **Contador de tentativas danificado/zerado:** texto único e mais claro (cobre duas janelas abrindo juntas; "nada foi apagado").
- **Aviso do pendrive:** "Salvando… não retire o pendrive" em unidade removível (só texto).
- **Esquema dos itens:** `_sanear_itens` corrige tipo errado, `id` ausente/repetido (achado real: PIN em lista derrubava a auditoria).

## 2. Testes novos (todos gravam `resultado_<nome>.txt`)
- Núcleo: concorrência real entre processos; objetos sensíveis no gc; esquema hostil; mensagens FIDO; caminhos especiais.
- Pentest: superfície do instalador; rede bloqueada; resíduos em disco + entropia; ocultação contínua.
- Interface: resiliência de uso (cliques frenéticos, texto absurdo, perda de foco, 30 ciclos sem vazar, janelas de senha, tela de integridade, aviso do pendrive).

- **Soak (longa duração):** núcleo com 1.000 ciclos (`teste_nucleo_soak_longa_duracao`, ~13 s) e interface com 60 ciclos por padrão (`teste_gui_soak_longa_duracao`; 1.000 via `COFRE_SOAK_CICLOS`, ~50 min). Mede descritores, threads, instâncias de Cofre e memória.
- **Cobertura de código:** `comum/cobertura_codigo.py` e `cobertura_codigo_windows.bat` (fora do Testar_Tudo).

## 3. Testes corrigidos (estavam desatualizados)
- `teste_gui_copiar` (6 botões Copiar), `teste_gui_passeio` (9 passos), `teste_gui_desempenho_usabilidade` (melhor de 3 rodadas, sem ruído de tempo).

## 4. Infraestrutura de testes
- `_resultado.py`: `pasta_temporaria()` (apaga ao terminar) e `log_depuracao()`.
- `rodar_todos.py` e `rodar_pentest.py` gravam a saída COMPLETA de cada teste em `resultados/log_depuracao.txt`.
- `consolidar_resultados.py` → `resumo_testes.md/json` e `resultados.sarif`.
- `limpar_artefatos_testes.py` → remove pastas temporárias órfãs.
- `rodar_todos_windows.bat` (Testar_Tudo): troca o log anterior por `log_depuracao_anterior.txt`, gera resumos e limpeza no fim.

## 5. Documentação
- README: SmartScreen ("Editor desconhecido → Mais informações → Executar assim mesmo"), ocultação contínua, tabela de testes, log de depuração.
- LEIA-ME, PLANO_DE_TESTES, MODELO_DE_AMEACAS (adendos 22 e 23).

## 5b. Achados do soak e da cobertura
Cobertura medida aqui no Linux (núcleo + pentest, sem interface): **32,1%** das linhas/ramificações de `cofre_senhas.py` (a maior parte do arquivo é interface; 74 faixas de `except`/`raise` sem teste listadas em `cobertura_codigo.txt` quando você rodar `cobertura_codigo_windows.bat`; com `--gui` o total sobe).
Memória do Python na interface cresce ~12 KiB por ciclo de desbloquear/bloquear (pequeno; documentado no MODELO_DE_AMEACAS, adendo 24).

## 6. Deliberadamente NÃO adotado
Detecção de sandbox/EDR e evasão; MSI/serviços/menu de contexto/protocolo de URL/Windows Hello (não existem); estresse simultâneo de todas as baterias; códigos de recuperação de uso único; compatibilidade antiga/ARM64 além do informativo.

## 7. Verificação no Linux (antes de você rodar no Windows)
Núcleo, pentest e interface rodados: tudo passou, exceto itens que dependem do ambiente Linux e falham igual com o programa original: `teste_pentest_vazamento_memoria` (alocador), `teste_gui_recorte` (métrica de fonte), `teste_pentest_dependencias` (precisa de requirements.txt/rede).

## 8. Rodada de correções após o teste no Windows
- **Novo item redesenhado:** sem botão "Mais opções" e sem "Criar uma senha forte"; tela única (nome, grupo, usuário, pessoa, senha), extras pelas caixas "Este item também tem"; "Copiar" só ao editar. Testes ajustados: item_simples, dados_bancarios, desempenho_usabilidade.
- **teste_gui_resiliencia_uso:** texto de 100 mil caracteres travava a janela >20 s e o vigia bloqueava o cofre ("PC dormiu"). Agora 5 mil caracteres, foco fixo e relógio do vigia renovado.
- **teste_gui_navegacao:** clicar na capa agora devolve o foco no teste (antes dependia de qual janela estava ativa no seu PC).
- **teste_gui_recorte:** espera o ajuste (debounce) da janela antes de medir.
- **Handles/GDI = 0:** ctypes tipado (`handles_processo`, `objetos_gdi`) em `_resultado.py`.
- **`.bat` com "em"/"echo" comidos:** ASCII + CRLF.
- **Memória/CPU:** prioridade baixa, espera por RAM livre, pausa entre testes, concorrência com 2 ou 3 escritores conforme a RAM.
- **Resultados:** `limpar_resultados.py` no início do Testar_Tudo; `HISTORICO_lista_de_mudancas.md` agora em `testes/ferramentas_dos_testes/`.
- **Novo teste `teste_nucleo_integridade_proprio`:** autochecagem do SHA-256 do programa (hash confere com conta independente, 1 bit muda o hash, arquivo sumido -> None, sem .sha256 solto).
- **`_trocar` (gravação atômica):** 12 tentativas com espera crescente (até 1,5 s) e também para erros de E/S de pendrive lento/antivírus.
- **Novos testes:** `teste_nucleo_corrupcao_forcada` (arquivo truncado/zerado/lixo/byte virado/pasta no lugar), `teste_nucleo_permissoes_gravacao` (pasta/arquivo sem permissão, simulado e real), `teste_gui_bloqueio_inatividade` (trava sozinho, zera as chaves, renovar o relógio).
- **Correção real:** gravar em pasta somente leitura agora marca o erro como "protegido" (antes só o aviso de tentativas fazia isso), para a tela oferecer o MODO CONSULTA.
- **`_trocar`:** 8 tentativas com espera crescente (~4 s no máximo).
- **Logs numa pasta só:** `logs_de_compilacao\` (1 - INSTALAR O COFRE - compila e instala.bat) e `testes\resultados\log_depuracao.txt` (testes). `.gitignore` e README atualizados.

## 9. Organização do projeto (pedido: "deixe fácil saber para que serve cada item")
- **Novo `LEIA PRIMEIRO - mapa do projeto.md`** na raiz e um **`INDICE.md` em cada pasta de testes** (gerado por `testes/ferramentas_dos_testes/gerar_indices.py`): uma linha por arquivo dizendo para que serve e por que está ali; arquivo sem descrição faz o gerador avisar.
- **`extras\seguranca-windows` virou `ferramentas_windows_opcionais\`** (scripts opcionais que cuidam do PC, não do cofre).
- **Renomeados** (nomes que não diziam nada): `teste_revisao6` -> `teste_falha_de_memoria_e_sorteio`; `teste_gui_revisao6` -> `teste_gui_limpeza_ao_bloquear`; `teste_gui_macaco` -> `teste_gui_cliques_aleatorios`.
- **Textos de abertura reescritos** em 18 testes que diziam só "Teste de interface (Tk) do cofre" (ou nada).
- **`docs\`** novo: `HISTORICO_relatorio_final_de_13-11.md` (retrato antigo) e `HISTORICO_lista_de_mudancas.md` saíram da raiz e de `testes\ferramentas_dos_testes`.
- **Removido:** `testes\ferramentas_dos_testes\test_cofre_completo.py` (suíte unittest duplicada e desatualizada; o `rodar_todos.py` já faz tudo). `PECA_DE_TESTE_cofre_versao_4_antiga.py` ficou, mas está marcado como FIXTURE.
- `D - testar no Windows Sandbox limpo.wsb`: caminho corrigido para a sua pasta (Recuperacao).

## 10. Novo teste (rodada seguinte)
- `teste_nucleo_conflito_e_diagnostico`: duas janelas no mesmo cofre (a desatualizada é recusada com ConflitoGravacao e nada é sobrescrito), conflito registrado no diagnóstico cifrado `.diag` (ilegível com outra chave), senha errada gasta 1 tentativa, e planilha sem a aba do selo (ou com coluna alterada) é recusada como a tela chama. Os outros itens do texto já tinham teste (modo consulta, limpeza de objetos sensíveis, selo alterado).

## 11. Reorganização geral para leigos (16/11)
- Raiz com só 3 atalhos numerados (1 INSTALAR, 2 TESTAR TUDO, 3 BAIXAR PACOTES), o mapa `LEIA PRIMEIRO`, o programa, o instalador e `requirements.txt`.
- `README.md` virou `docs/MANUAL_COMPLETO.md`; `THREAT_MODEL.md` virou `docs/MODELO_DE_AMEACAS.md`; `hashes_sha256.txt` virou `docs/HISTORICO_sha256_do_programa.txt`; os dois relatórios antigos viraram `docs/HISTORICO_*`.
- `logs_de_compilacao/` guarda só os registros de instalação (uma pasta só, sem subpastas). O log de depuração dos testes foi para `testes/resultados/`, que agora guarda TUDO que os testes geram.
- Pastas de teste renomeadas: `1_motor_do_cofre`, `2_telas_e_botoes`, `3_ataques_simulados`, `4_so_no_windows`, `ferramentas_dos_testes` (antes: nucleo, gui, pentest, windows, comum).
- `COMO_RODAR_OS_TESTES.md` e `PLANO_DE_TESTES.md` subiram para `testes/`. Atalhos de cada pasta com nome que diz o que fazem (`RODAR ESTA PASTA - ...`, e `A`/`B`/`C`/`D` em 4_so_no_windows).
- `ferramentas_windows_opcionais/`: atalhos numerados 1 a 4 com o efeito no nome; os `.ps1` foram para `_scripts_internos_nao_mexer/`.
- Apagadas: `_to_delete/`, `extras/`, `logs_compilacao/`, `logs/`. Todos os `.bat` agora em CRLF.
- Caminhos corrigidos em scripts, testes, índices, manual e `.gitignore`. Conferido no Linux (testes de conflito/diagnóstico, README, instalador, dependências, navegação e o executor do motor).

## 12. `VirtualLock` (16/11)
- Chegou a ser implementado e foi **cancelado a pedido do usuário** (decisão: não usar). O programa, os testes e os textos voltaram ao que eram: `VirtualLock` segue como "não adotado" no `MODELO_DE_AMEACAS.md`.

## 13. Novos testes e avaliação de engenharia reversa (16/11)
- **3 testes novos** (sem mexer no programa):
  - `2_telas_e_botoes/teste_gui_captura_de_tela.py`: confirma que a janela principal e os diálogos pedem ao Windows para não aparecer em prints/gravação/acesso remoto (`SetWindowDisplayAffinity`); no Windows real lê de volta e confere que valeu.
  - `1_motor_do_cofre/teste_nucleo_ida_e_volta_aleatoria.py`: vários ciclos de criar/editar/apagar itens com texto aleatório (acentos, emoji, chinês, caracteres de controle) e vira bits do arquivo depois: nunca pode voltar dado diferente em silêncio nem estourar erro não tratado.
  - `1_motor_do_cofre/teste_nucleo_muitos_itens.py`: cofre com 5.000 itens — tamanho de arquivo, tempo de salvar/abrir e pico de memória dentro do esperado, tudo íntegro depois de vários salvamentos.
- **Avaliadas e recusadas** (ver `MODELO_DE_AMEACAS.md`, adendo 16): ofuscadores comerciais, separar em módulos/`.pyc`, `--lto=yes`, anti-debug mais agressivo, ofuscar strings, reproducible builds. Nenhuma mexe no código; todas ficaram só registradas como decisão.

## 14. Janelas que apareciam "montando", vazamento de memória gráfica e 3 rodadas (16/11)
- **Janelas aparecem prontas.** Os diálogos (Novo item, Editar item, Gerador de senhas etc.) apareciam pequenos/cortados e cresciam até "firmar". Agora o tamanho final é calculado ANTES de mostrar a janela (`_corpo_rolavel` + `_revelar_dialogo`), e os painéis de força de senha já nascem preenchidos.
- **Teste novo** `2_telas_e_botoes/teste_gui_janelas_aparecem_prontas.py`: mede cada tela e diálogo no 1º quadro e depois de assentar; qualquer mudança de tamanho/posição ou widget tardio é falha. Antes da correção acusava 8 falhas; agora passa (em 2 tamanhos de janela).
- **Vazamento de objetos GDI/USER (soak) corrigido.** Cada bloqueio/desbloqueio deixava na memória a tela anterior inteira (imagens de cartão e sombra), porque o `bind` da roda do mouse na janela principal não apagava o comando antigo. Novo `_ligar_raiz` substitui de verdade. Imagens vivas ficaram estáveis (de +4 por ciclo para 0).
- **Cofre bloqueado no meio de uma ação** (causa da falha do teste de resiliência no Windows): `dialogo_registro` não abre mais com o cofre fechado e `_grupos` não estoura; o teste reabre o cofre se ele bloquear sozinho.
- **Executor de testes:** a cada 30 s imprime "continua rodando" (não parece mais travado na etapa 4/5).
- **TESTAR TUDO agora faz 3 rodadas** seguidas; cada uma é guardada em `testes\resultados\rodada_1`, `rodada_2`, `rodada_3`.
- **Rodada 2 (análise das 3 rodadas do Windows):** gravação por vários processos usava o mesmo `.tmp` e um pisava no outro; agora cada processo grava em `cofre.dat.<PID>.tmp` (limpeza e "apagar tudo" também cobrem esses temporários). O teste de janelas passou a medir o primeiro quadro de verdade. O soak aquece o formulário antes de medir GDI/USER. O teste de resiliência mostra o estado exato se "Novo item" não abrir.

## 15. Instalador, dependências e validação (2026-11-20)
- **Instalação antiga:** o instalador detecta `<destino>\CofreSenhas` e permite atualizar no local, manter intacta ao instalar em outro destino ou remover somente os arquivos do programa após confirmação `APAGAR`; cofre, backups e chaves são preservados. Testes Pester isolados cobrem os auxiliares e a preservação.
- **Nomes mais claros:** `requirements-test-direct.in` identifica as dependências diretas, `requirements-test-lock.txt` o lock instalado, e `testes\ambiente_virtual_ferramentas (NAO MEXER)` o ambiente virtual persistente. A pasta `docs\` foi renomeada para `documentacao\`; os links e testes que consultam os documentos foram atualizados.
- **Dependências de teste:** `requirements-test-direct.in` é a fonte de dependências diretas fixadas; `requirements-test-lock.txt` é o lock transitivo com hashes. O teste de integridade verifica a consistência dos dois.
- **Caches:** caches transitórios de Python, Hypothesis, Ruff, mypy, pytest e arquivos temporários ficam em `testes\CACHE\<execução>` e são removidos ao fim; `CACHE` desaparece quando fica vazia. `testes\ambiente_virtual_ferramentas (NAO MEXER)` é persistente, separado dos caches e ignorado pelo Git.
- **Automação e segurança:** workflow Windows em `.github\workflows\` permanece na raiz, e foi criado `SECURITY.md` com escopo de proteção e canal privado para relatos.
- **Validação registrada:** bateria completa em Windows 11 Pro 10.0.26300 / Python 3.13.9 AMD64: 2.344 verificações OK e 9 relatórios com falha/interrupção, além de PSScriptAnalyzer e qualidade extra com alerta. Quatro sondas `-X dev` também falharam com `-1073741819` mesmo sem abrir o Cofre. Validações focadas posteriores passaram Pester 14/14 e engenharia reversa; a bateria completa não foi repetida após as últimas mudanças e não foi validada com Python 3.13.17.
