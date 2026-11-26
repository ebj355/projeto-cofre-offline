<!-- ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt -->
# Guia técnico para ler o código

Este guia ajuda quem vai ler, manter ou testar a implementação da **Arca**, produto da **Arca Sistemas**. O programa foi mantido intencionalmente em um único arquivo, `cofre_senhas.py`; por isso, as partes são organizadas por seções e funções, não por módulos separados.

O objetivo é mostrar por onde começar, qual parte é responsável por cada assunto e como os fluxos principais se conectam. Não é uma lista de cada função auxiliar: detalhes locais continuam documentados nas docstrings e nos comentários junto ao código.

## Por onde começar

Uma leitura útil, sem precisar percorrer o arquivo inteiro em ordem:

1. Leia a docstring no início de `cofre_senhas.py` para conhecer os limites e os principais recursos.
2. Procure `main()` no fim do arquivo e veja a criação de `App` e a preparação do ambiente.
3. Leia a docstring e o `__init__` de `App` para entender o estado da interface.
4. Leia a classe `Cofre`, começando por `criar()`, `abrir()`, `salvar()`, `transacao()` e `fechar()`.
5. Volte às seções auxiliares chamadas por esses métodos, como derivação de chaves, leitura do cabeçalho, serialização, gravação e cópias.
6. Para entender uma ação da interface, procure o método correspondente de `App` e siga as chamadas até `Cofre` ou até o helper de importação.

No VS Code, `Ctrl+Shift+F` localiza um nome de função ou classe; o painel **Estrutura** e o comando **Ir para definição** ajudam a navegar sem depender de números de linha.

## Mapa do arquivo

Os títulos das seções no próprio `cofre_senhas.py` são os pontos de referência. Os nomes abaixo são bons termos para busca:

| Parte | Responsabilidade | Símbolos para localizar |
|---|---|---|
| Inicialização e configuração | Importações, dependências, detecção do Windows e constantes gerais. | `EH_WINDOWS`, `ARQUIVO_PADRAO`, `MIN_SENHA` |
| Formato e criptografia | Versões do arquivo, parâmetros, derivação e combinação de chaves, cifragem e decifragem. | `MAGIC`, `HEADER_FMT5`, `derivar_chave()`, `_embrulhar()`, `_desembrulhar()`, `_subchaves()`, `_decifrar_dados()` |
| Integridade e armazenamento | Leitura do cabeçalho, escrita atômica, travas, cópias de segurança, recuperação e erros de arquivo. | `_ler_cabecalho()`, `_gravar_atomico()`, `_trava_gravacao()`, `_rodar_copias()`, `restaurar_copia()` |
| Proteções e fatores do Windows | Proteção do processo, identidade do computador, segredo local, FIDO2, impressão e área de transferência. | `blindar_processo()`, `identidades_do_pc()`, `segredo_local()`, `fido_obter()`, `copiar_seguro_windows()` |
| Senhas e diagnósticos | Geração e avaliação de senhas, auditoria opcional, erros e diagnóstico cifrado (registros de 157 bytes, selados com a chave pública do cofre). | `gerar_senha()`, `gerar_frase()`, `avaliar_forca()`, `auditar_cofre()`, `diag_registrar()`, `DIAG_REG`, `DIAG_MAX` |
| Modelo dos itens e importação | Campos do registro, validação, leitura e conferência de CSV/Excel. | `CAMPOS`, `CAMPOS_SECRETOS`, `ROTULOS`, `novo_item()`, `ler_planilha()`, `sanear_registros()`, `classificar_importacao()` |
| Objeto do cofre | Estado aberto em memória, fatores de desbloqueio, tentativas, transações e persistência. | `class Cofre`, `Cofre.criar()`, `Cofre.abrir()`, `Cofre.salvar()`, `Cofre.transacao()`, `Cofre.fechar()` |
| Aparência e componentes | Tema, controles, lista de marcas, ícones locais e sugestões offline do campo Serviço. | `aplicar_tema()`, `_Tela`, `BarraLateral`, `ListaContas`, `PainelForca`, `icones_marcas.py` (`MARCAS`, `ALIASES`, `AutocompletarMarcas`) |
| Interface e ações | Telas, diálogos, eventos, ações sobre itens, bloqueio e coordenação com o cofre. | `class App`, `tela_criar()`, `tela_desbloqueio()`, `tela_principal()`, `dialogo_registro()`, `importar()` |
| Inicialização do programa | Modo consulta, preparação das proteções e início do laço da interface. | `_so_com_escrita()`, `main()`, `root.mainloop()` |

Alguns assuntos aparecem em mais de uma seção. Por exemplo, a interface solicita uma operação FIDO2, mas as rotinas de comunicação com a chave física ficam nos helpers FIDO2; a interface não deve implementar a criptografia por conta própria.

## Como as partes se relacionam

- **`App` é a camada de interface.** Recebe ações, apresenta mensagens e telas e chama as operações do objeto `Cofre`. Não é o formato do arquivo nem a autoridade criptográfica.
- **`Cofre` é o objeto de domínio aberto.** Mantém os registros e metadados em memória e controla desbloqueio, fatores, tentativas, transações e salvamento.
- **Os helpers de módulo fazem tarefas específicas.** Exemplos: validar um cabeçalho, derivar uma chave, ler uma planilha ou gravar um arquivo de forma atômica. Eles são usados pelo `Cofre`, pela interface ou por ambos.
- **Os testes exercitam esses caminhos.** Os testes do motor verificam o comportamento sem depender das telas; os testes de interface verificam a integração com Tk e as ações visíveis.

O fluxo normal de dados é: a interface solicita uma ação → o objeto `Cofre` altera ou consulta o estado → os helpers validam, cifram ou persistem quando necessário → a interface apresenta o resultado. Falhas de gravação devem ser tratadas sem deixar uma alteração recusada como se estivesse salva.

## Fluxos principais

### Criar um cofre

`App.tela_criar()` coleta as escolhas na interface e chama `Cofre.criar()`. O objeto cria a chave interna, configura os fatores escolhidos e salva o primeiro arquivo. A persistência passa pelo mesmo caminho de cifragem e gravação usado nas alterações posteriores.

Depois de mostrar a chave de acesso (quando existe) e abrir a tela principal, `App._autorizar_primeiro_pc_na_criacao()` autoriza o computador atual (`Cofre.pc_adicionar()`), pergunta se há mais computadores (`_perguntar_mais_computadores()` e `Cofre.definir_pcs_multiplos()`) e mostra o código de recuperação. Se algo falhar ou o código não for confirmado, a função desfaz a mudança (`restaurar_pc()`) e o cofre continua válido, sem a exigência. A variável de ambiente `COFRE_SEM_VERIFICACAO_INICIAL=1` pula esse passo e a verificação de integridade ao entrar; ela existe para os testes de interface.

### Abrir um cofre

`App.tela_desbloqueio()` coleta os fatores e chama `Cofre.abrir()`. O método valida o formato e os fatores necessários, verifica o cabeçalho, deriva ou combina as chaves, abre a chave interna e decifra os dados. Em seguida, valida e prepara os registros para uso.

Depois que a tela principal abre, `App.verificar_integridade_cofre(automatica=True)` mostra a tela de integridade do arquivo principal e das cópias `.bak` (dados vindos de `Cofre.verificar_estado_arquivos()`). Ela só lê; uma falha na conferência é registrada com `diag_registrar()` e nunca impede o uso. Em seguida roda `_alerta_invasao()`.

Nem todo erro significa senha incorreta. O código distingue, entre outros casos, fator ausente ou malformado, computador não autorizado, memória insuficiente, arquivo danificado e senha incorreta. Ao alterar a lógica de tentativas ou recuperação, preserve essas distinções e confira os testes do motor.

### Salvar alterações

As ações da interface usam `App._salvar()` ou `App._transacao()`. A transação coordena a mudança e o salvamento; se a gravação falhar, `Cofre.transacao()` restaura o estado anterior em memória. `Cofre.salvar()` delega a gravação serializada e cifrada, com verificação de conflito, trava, cópia de segurança e substituição atômica.

### Importar uma planilha

`App.importar()` chama `ler_planilha()` para ler e validar o arquivo. A interface classifica os registros como novos, iguais ou conflitantes, mostra uma prévia e só altera o cofre depois da confirmação. Para entender esse fluxo, siga também `varrer_planilha()`, `sanear_registros()` e `classificar_importacao()`.

## Ao alterar o código

- **Novo campo de item:** confira `CAMPOS`, `CAMPOS_SECRETOS` quando aplicável, `ROTULOS`, `novo_item()`, o formulário/detalhe da interface, o mapeamento de importação e os testes afetados. Não presuma que adicionar o nome a uma constante atualiza todas as telas ou os formatos de entrada.
- **Criptografia ou formato do arquivo:** siga as constantes de versão e os métodos de `Cofre`; mantenha compatibilidade e restauração de cópias testadas. Não altere o formato com base apenas na aparência do cabeçalho.
- **Ação da interface:** mantenha validação e persistência no caminho existente (`Cofre` e helpers), com mensagens claras para falhas; não grave diretamente fora do fluxo de salvamento.
- **Dependências:** confira os arquivos de requisitos e as instruções de instalação/teste antes de adicionar uma biblioteca.
- **Regressão:** use `testes/COMO_RODAR_OS_TESTES.md` para selecionar a bateria apropriada. Comece pelos testes do motor para regras do cofre e pelos testes de telas para comportamento da interface. A pasta `8_TESTE_extras_atalho_proprio` reúne os testes de integridade ao entrar e o visual bruto, que o `2 - TESTAR TUDO` roda por último.

Antes de editar uma função, leia sua docstring, os helpers chamados e os testes que a exercitam. Os nomes com `_` indicam detalhes internos por convenção, não uma API estável.

## Até onde esta documentação vai

Este guia é um mapa de orientação, não uma especificação completa de cada helper, algoritmo ou evento gráfico. As regras detalhadas devem ser confirmadas no código e nos testes correspondentes. A documentação voltada a quem usa o cofre continua no [MANUAL_COMPLETO.md](./MANUAL_COMPLETO.md), e a visão geral está no [README.md](../README.md).
