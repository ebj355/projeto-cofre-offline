> **Para a visão geral do projeto, consulte o `README.md` na raiz. Para saber o que cada arquivo de teste faz, abra o `INDICE.md` da pasta numerada (1 a 6).**

# Testes do Cofre de Senhas

Tudo que é teste está nesta pasta. Os testes trabalham em pastas temporárias: **nunca tocam no seu `cofre.dat`**.

## Preparar para rodar sem internet

1. Em um computador com internet, execute na raiz `3 - BAIXAR PACOTES - so para instalar sem internet.bat`.
2. Copie o projeto inteiro, inclusive `pacotes\`, para o computador sem internet. Os binários de `pacotes\` são ignorados pelo Git e não vêm em uma clonagem nova.
3. Se o computador não tiver Python 3.13, execute `pacotes\python-3.13.17-*.exe`. As baterias instalam dependências com `--no-index` e não tentam baixar nada. Depois de alterar `requirements-test.txt`, rode novamente o item 3 para atualizar o wheelhouse; os wheels das ferramentas 05–12 ainda precisam ser incluídos e suas versões `>=` fixadas em `==` antes de distribuir o pacote offline.
4. Pester é carregado do pacote local. Nmap está em `pacotes\nmap-7.993-setup.exe`, mas requer instalação manual e pode precisar de privilégios/Npcap.
5. O `pip-audit` não inclui uma base de vulnerabilidades local. A bateria completa do Windows consulta a base atual online por padrão; use `rodar_todos_windows.bat OFFLINE` para pular a consulta quando estiver sem rede. A auditoria usa as dependências fixadas (`==`) sem resolver ou instalar pacotes; ferramentas ainda declaradas com faixas (`>=`) são listadas como puladas até terem versões exatas. Para executar os BATs de auditoria separadamente, defina `COFRE_ONLINE_AUDIT=1`.

Para rodar as seis baterias no Windows, execute `testes\6_ferramentas_dos_testes\rodar_todos_windows.bat`. A etapa 6 audita online as dependências do programa e de testes, além de gerar o SBOM. Para testar um pendrive, passe a letra como primeiro argumento; acrescente `OFFLINE` como último argumento para não consultar a internet (por exemplo, `rodar_todos_windows.bat H OFFLINE`).

## Rodar tudo

```
python testes/6_ferramentas_dos_testes/rodar_todos.py              # núcleo + interface
python testes/6_ferramentas_dos_testes/rodar_todos.py --rapido     # só o núcleo (sem janelas)
python testes/6_ferramentas_dos_testes/rodar_todos.py --so gui     # só a interface
python testes/6_ferramentas_dos_testes/rodar_todos.py --filtro fido -v
python testes/6_ferramentas_dos_testes/rodar_todos.py --so nucleo --filtro propriedades_hypothesis -v
```

No Linux sem tela, a interface roda dentro do `xvfb-run`. No Windows, durante os testes de interface aparecem janelas
por alguns segundos. O resumo mostra `ok`, `PULADO` ou `FALHOU` por teste; opcional ausente (como Hypothesis, código 9) é `PULADO`, nunca aprovado. O código de saída é 0 se não houver falhas.
Linhas `Traceback` em testes marcados `ok` são ruído do modo `-W error` (avisos de recurso), não falha.

## Pastas

| Pasta / arquivo | O que é |
|---|---|
| `1_motor_do_cofre/` | `teste_*.py` (sem janelas): inclui testes por propriedades Hypothesis de ida e volta e CSV hostil, além de ataques, fido, importação, backup, concorrência, corrupção, fuzzing, memória e soak. Se Hypothesis não estiver no wheelhouse, o executor registra `[PULADO]` (código 9); com o wheel, o BAT do núcleo o instala no ambiente temporário. |
| `2_telas_e_botoes/` | Interface (Tk): abrir/criar, editar, copiar, pessoas, importação, FIDO, alerta de tentativas, bloqueio, olho, navegação, energia, "macaco", segurança extra, acessibilidade por teclado, fluidez/glitches visuais. `RODAR ESTA PASTA - testes das telas e botoes.bat` roda só esta bateria no **Windows real** |
| `4_so_no_windows/` | `A - testar o instalador.bat`: roda no **Windows real** só os testes do instalador/SO (sintaxe do `instalar_cofre.ps1`, import do programa, Pester) - a bateria do núcleo **não** roda mais aqui, veja `1_motor_do_cofre/`. `B - testar atributos e permissoes do Windows.bat`: atributos, ACL, SMBIOS, DPAPI, PC autorizado, DLLs |
| `3_ataques_simulados/` | Pentest dedicado (`teste_pentest_*.py`): injeção de código, SSRF, força bruta/spraying, DoS, vazamento de memória (forense de RAM), bypass de contador/autodestruição, engenharia reversa, fuzzing adversarial/Unicode, SAST (bandit/flake8), dependências (pip-audit), canal lateral de tempo, exfiltração pela rede e link simbólico (achado real, corrigido), além da documentação explícita do que é fora de escopo. O BAT instala somente as bibliotecas essenciais do programa a partir de `pacotes\`; ferramentas opcionais ausentes são puladas, sem bloquear o pentest. `rodar_pentest.py` roda só esta bateria; `RODAR ESTA PASTA - testes de ataque simulado.bat` roda no **Windows real**. Relatório: `resultados/relatorio_pentest.md` |
| `resultados/` | Onde **todo** `resultado_*.txt` é gravado (de qualquer um dos `.bat` acima ou do `rodar_todos_windows.bat`) - uma pasta só para ver tudo, nunca sobrescrevendo (cada bateria tem seu próprio nome de arquivo). Não cria subpastas por rodada. |
| `5_ferramentas_externas/` | Ferramentas 01–12: Bandit, pip-audit, Nmap, PSScriptAnalyzer, pefile, Defender, busca de segredos, qualidade extra, SBOM, conexões do processo e Hypothesis. O `03_PYTEST_PROJETO.bat` é opcional e fica fora da bateria geral por repetir núcleo e interface. |
| `6_ferramentas_dos_testes/` | O que **organiza** os testes, sem ser um teste em si: `rodar_todos.py` e `rodar_todos_windows.bat` (executores que chamam as 6 baterias), `test_pytest.py` (ponte opcional para o pytest), `_util_mem.py`, limpeza e relatórios. |
| `PECA_DE_TESTE_cofre_versao_4_antiga.py` | Versão antiga do formato, usada pelo teste de migração (fica em `1_motor_do_cofre/`, junto do teste que a usa) |

## Antes de entregar uma versão

1. `python testes/6_ferramentas_dos_testes/rodar_todos.py` sem nenhum `FALHOU`.
2. `testes\6_ferramentas_dos_testes\rodar_todos_windows.bat` no Windows (ou os `.bat` de `1_motor_do_cofre\`, `4_so_no_windows\` e `2_telas_e_botoes\` em separado), sem `[FALHOU]`.
3. Instalar e abrir dando dois cliques no `CofreSenhas.exe` (é o único arquivo do programa na pasta), criar um item, fechar e reabrir.


## Testes do instalador (Windows)
`testes\4_so_no_windows\instalador.Tests.ps1` é uma suíte **Pester** das funções auxiliares do `instalar_cofre.ps1` (conferência do hash digitado, arquitetura, sistema de arquivos, espaço em disco, certificado, limpeza de caminhos e log). O `A - testar o instalador.bat` carrega o Pester 5.7.1 empacotado em `pacotes\powershell-modules`. Carregar o instalador com `. .\instalar_cofre.ps1` só define as funções, não instala nada. **Ainda não foi executada em Windows real.**

## Queda de energia, concorrência, memória e fuzzing
- `teste_queda_e_memoria.py`: mata (SIGKILL) o programa no meio de gravações repetidas e confere que o cofre abre sempre e nada confirmado se perde; duas instâncias gravando no mesmo arquivo (a gravação concorrente é detectada e recusada); e a checagem de **memória livre antes do Argon2** (recusa sem gastar tentativa).
- `teste_fuzz_importacao.py`: CSV/XLSX hostis (bytes nulos, campos de MB, UTF-16 com BOM trocado, UTF-8 inválido, zip bomb, 200 mutações aleatórias): nunca pode estourar erro não tratado. Este teste encontrou e corrigiu um defeito real (campo CSV maior que 128 mil caracteres dava `csv.Error` sem tratamento).
- `teste_checksum_v5.py`: setor zerado/0xFF, cabeçalho apagado, corte, lixo no fim, arquivo vazio e setores trocados: nunca gasta tentativa nem apaga, e a cópia restaura.
- Análise estática: Bandit e Flake8 são instalados do `pacotes\` preparado por `3 - BAIXAR PACOTES`; o BAT de Bandit cria `testes\_venv_ferramentas` sem rede.
- **pytest:** o BAT correspondente usa o mesmo ambiente offline (`testes\_venv_ferramentas`): `03_PYTEST_PROJETO.bat` roda `test_pytest.py`, cada `teste_*.py` como um caso. A ponte repete as baterias 1 e 2.
- `teste_queda_pontos_exatos.py` (queda de energia em cada `fsync`/`os.replace`) e `teste_fuzz_cabecalho.py` (cada byte do cabeçalho v5 e da seção FIDO): nada gasta tentativa, nada se perde.
- `2_telas_e_botoes/teste_gui_fontes.py`: fontes nomeadas podem ser preparadas mais de uma vez.
- `teste_host_e_politica.py`: pasta temporária privada no pendrive (rastros no host) e política opcional de exigir NTFS.
- `teste_senha_longa_e_fs.py` e `2_telas_e_botoes/teste_gui_campos.py`: limite de tamanho de senha (sem gastar tentativa), aviso de sistema de arquivos sem permissões e limpeza dos campos de texto ao fechar janelas.
- `teste_trava_instancias.py` e `2_telas_e_botoes/teste_gui_em_uso.py`: trava `.lock` entre processos (segundo processo = "em uso" → modo consulta; some com `kill -9`), contador anti-reversão (alerta ao voltar no tempo, nunca em uso normal) e a segunda janela em modo consulta.
- `teste_modo_consulta.py` e `2_telas_e_botoes/teste_gui_consulta.py`: pendrive protegido contra gravação (escrita bloqueada por simulação): modo consulta, mensagens e ações bloqueadas.

- `teste_vazamento_memoria.py` e `teste_payloads.py`: resíduos de senha/chave na RAM após `fechar()` e payloads hostis (10 mil caracteres, `\n`, `\x00`, HTML/SQL) em título/usuário/URL: nada trava, nada se perde, importação gigante é recusada inteira.
- `teste_chave_selada.py`: arquivo `.key` selado (só o cofre de origem abre; qualquer byte adulterado, arquivo de outro cofre ou texto puro antigo é tratado sem estourar erro).
- `2_telas_e_botoes/teste_gui_salvar_fluido.py`: salvar sem congelar a janela (o disco lento roda fora da thread da interface; a janela continua respondendo e o bloqueio automático espera o salvamento).
- `2_telas_e_botoes/teste_gui_caps_fido.py`: ícone de Caps Lock dentro do campo e mensagens FIDO didáticas (próximo passo + código entre parênteses).
- `2_telas_e_botoes/teste_gui_desempenho_usabilidade.py`: a medida de "abrir+fechar Novo item" usa a MENOR média de 4 rodadas (ruído de CPU só aumenta o tempo), para o teste medir o código e não a carga da máquina.
- `2_telas_e_botoes/teste_gui_fluidez_animacoes.py`: regressão de glitches relatados de verdade: gerador de senhas fecha ANTES de preencher o campo (sem recentralizar o diálogo de baixo com o gerador ainda em cima); bloco destacado do código de recuperação sorteado e do tamanho certo; rajada de `<Configure>` (teclado virtual) vira poucas reconfigurações do Canvas (debounce); cartão do passeio guiado arrasta pelo título; varredura geral sem Toplevel/widget sobrando.

## Ferramentas novas (05–12)
O Testar Tudo chama as ferramentas automáticas 01, 02 e 04–12. O pytest (03) fica somente no menu por repetir as baterias 1 e 2. As novas ferramentas usam dependências em `requirements-test.txt`; rode `3 - BAIXAR PACOTES` com internet antes de usar em modo offline. Até os wheels estarem no pacote, ausência de ferramenta é `[PULADO]`; o Hypothesis é descoberto pelo executor do núcleo e código 9 é skip, enquanto falha real retorna código de falha. O atalho 12 é também uma forma de rodar esse teste isoladamente.

- `teste_planilha_selo.py`: modelo selado e **importação estrita** (só o que o cofre gerou); `teste_nivel_protecao.py`: ranking de proteção; `teste_backup_chave.py`: backup exige a chave de acesso.
- `2_telas_e_botoes/teste_gui_teclado_virtual.py`: teclado virtual sem recriar teclas (sem piscar), com contagem e Esc; `2_telas_e_botoes/teste_gui_ajustes_ui.py`: senhas sempre ocultas até o olho e painel de nível de proteção.
- `teste_autodestruicao.py`: autodestruição sem resíduos em disco/memória e contagem de tentativas em todas as combinações de fatores; `2_telas_e_botoes/teste_gui_tentativas_config.py`: setas numéricas, tentativas dentro do cofre e tela inicial limpa.
- `teste_patch_bypass.py`: remendo do programa não abre o cofre; `2_telas_e_botoes/teste_gui_abertura.py`: abertura rápida e carga sob demanda; `2_telas_e_botoes/teste_gui_recorte.py`: nada cortado em 3 tamanhos de janela.
- `teste_ocultar_apoio.py`: arquivos de apoio ocultos/somente leitura (Windows simulado): lista exata, .bat e arquivos do usuário intocados, revelar/ocultar idempotentes.

- `teste_pc_segredo_local.py` — reforço DPAPI do computador autorizado (simulado).
- `2_telas_e_botoes/teste_gui_imprimir_chave.py` — impressão só da chave de acesso e do código de recuperação, com senha mestra e nome genérico.
- `teste_tecnico_sistema.py` — auditoria técnica (segredos, funções perigosas, rede, DLLs, mutações, tempo).
- `teste_red_team.py` — ataque simulado (engenharia reversa, forense, bits alterados, custo de força bruta).
- `4_so_no_windows/B - testar atributos e permissoes do Windows.bat` — **só no Windows real**: atributos, ACL, SMBIOS, DPAPI, PC autorizado, DLLs. Saída em `resultados/resultado_nativo_windows.txt` (`_H.txt` etc. para cada pendrive testado — cada teste grava o seu próprio arquivo, sem sobrescrever os outros).


## Log de depuração, resumos e limpeza (2026-11-16)
Além de um `resultado_<teste>.txt` por teste, a pasta `testes/resultados/` guarda:
- `testes/resultados/log_depuracao.txt` — saída COMPLETA (com tracebacks), horário, duração e comando de cada teste; recriado do zero a cada rodada. É o arquivo para abrir quando algo falha.
- `resumo_testes.md` / `resumo_testes.json` / `resultados.sarif` — gerados por `testes/6_ferramentas_dos_testes/consolidar_resultados.py` (tabela legível, JSON comparável e SARIF só com falhas).
- `limpeza_artefatos.txt` — relatório de `testes/6_ferramentas_dos_testes/limpar_artefatos_testes.py`, que apaga pastas temporárias órfãs (prefixos dos nossos testes, mais velhas que 5 min).
Os testes novos criam pastas temporárias por `_resultado.pasta_temporaria()`, que as apaga ao terminar mesmo se o teste falhar.
Observação do Linux: `teste_pentest_vazamento_memoria.py` (conta cópias de um texto na memória do processo) oscila conforme o alocador do Python; no Windows o resultado é o que vale.

## Soak e cobertura (2026-11-16)
- `1_motor_do_cofre/teste_nucleo_soak_longa_duracao.py`: 1.000 ciclos seguidos (descritores, threads, memória, instâncias de Cofre). Roda sem `-X dev` (o modo dev o deixaria 50x mais lento).
- `2_telas_e_botoes/teste_gui_soak_longa_duracao.py`: 60 ciclos por padrão (cada um custa ~3 s); `COFRE_SOAK_CICLOS=1000` para a corrida longa.
- `6_ferramentas_dos_testes/cobertura_codigo.py` / `cobertura_codigo_windows.bat`: cobertura de código com ramificações (`resultados/cobertura_codigo.txt`, `cobertura_codigo.json` e `cobertura_html.zip`, todos diretamente em `resultados/`, sem subpastas persistentes). Não faz parte do Testar_Tudo.
