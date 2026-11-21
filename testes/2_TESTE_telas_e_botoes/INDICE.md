# Testes da Arca — INTERFACE (janelas Tk)

**Para que serve esta pasta:** Abrem as telas de verdade (no Linux com tela virtual `xvfb-run`; no Windows em janelas reais) e clicam/digitam como um usuário. Cada `teste_gui_*.py` é independente.

_Gerado por `testes/6_TESTE_ferramentas_dos_testes/gerar_indices.py` (não edite à mão: rode o script)._

| Arquivo | Para que serve |
|---|---|
| `RODAR ESTA PASTA - testes das telas e botoes.bat` | Atalho de dois cliques da bateria de INTERFACE no Windows (chama teste_gui_windows.ps1). |
| `sitecustomize.py` | Keeps automated Tk windows behind the user's active app on Windows. |
| `teste_autocompletar.py` | Verifica o autocomplete de marcas sem rede; use --visual para abrir a janela manual. |
| `teste_gui_abertura.py` | Velocidade de abertura: importação + tela de desbloqueio em menos de 2,5 s (sem contar o Argon2 de criar o cofre), e as bibliotecas pesadas (Excel/openpyxl, FIDO) só carregam quando são usadas (lazy). |
| `teste_gui_acessibilidade_teclado.py` | Acessibilidade: navegação completa SEM MOUSE (só teclado). `teste_gui_desempenho_usabilidade.py` já confere contraste, tamanho de fonte e número de cliques; `teste_gui_efeitos.py` já confere Esc fechando diálogos. O que |
| `teste_gui_ajustes_ui.py` | Interface (Tk): gerador com rodapé fixo e detalhes escondidos, 'Usar em um novo item', caixas de extras no Novo item, grupos DENTRO de cada perfil, painel de proteção recolhido, convite do guia na 1ª entrada e troca de tela sem apagar a |
| `teste_gui_alerta.py` | Alerta de tentativas erradas e histórico de aberturas: conta as senhas erradas desde a última abertura, guarda o histórico CIFRADO e mostra o aviso na tela. |
| `teste_gui_basico.py` | Passeio básico (teste rápido de fumaça): tela de desbloqueio, tela principal, Novo item, teclado virtual, Ctrl+C bloqueado, bloquear e limpar a área de transferência. |
| `teste_gui_bloqueio_inatividade.py` | BLOQUEIO POR INATIVIDADE: com o relógio curto, o cofre se tranca sozinho, apaga as chaves da memória (o objeto Cofre fica zerado), derruba as janelas abertas e volta para a tela de desbloqueio; mexer no programa RENOVA o relógio (não bloqueia |
| `teste_gui_botoes.py` | Bateria de interface: cada tela é montada, cada botão do cabeçalho e cada item do menu '⋯' é acionado; confere que nenhum evento levanta exceção, que não sobram janelas, que os textos fixos da tela são CURTOS (o resto vai no '?'), |
| `teste_gui_campos.py` | CAMPOS DE TEXTO: ao destruir uma tela ou janela de diálogo, o texto digitado nos campos (senhas, chaves) é apagado antes; campos ligados a uma variável (textvariable) ficam como estão. |
| `teste_gui_caps_fido.py` | Interface (Tk): ícone de Caps Lock dentro do campo de senha e mensagens do FIDO com o próximo passo. Roda no Windows ou no Linux (xvfb-run -a). |
| `teste_gui_captura_de_tela.py` | Anti-captura de tela: a janela principal e os diálogos pedem ao Windows para aparecer PRETOS em prints, gravações e acesso remoto (SetWindowDisplayAffinity). No Windows lê de volta com GetWindowDisplayAffinity e confere que valeu; no Linux só confere o que dá  |
| `teste_gui_cliques_aleatorios.py` | 'Teste do macaco': 700 ações ALEATÓRIAS (cliques, teclas, abas, busca, bloquear, redimensionar) para achar travadas; confere erros, memória, widgets e que o cofre continua íntegro. |
| `teste_gui_computadores.py` | Interface (Tk): janela 'Computadores autorizados', ranking com o item do computador e tela de desbloqueio em um computador NÃO autorizado (pede o código de recuperação, sem gastar tentativa). Computadores simulados. |
| `teste_gui_consulta.py` | Interface do MODO CONSULTA: pendrive protegido contra gravação. Entra pela tela de senha (a escrita é bloqueada), aceita a oferta do modo consulta, confere o aviso na tela principal e que as ações que alteram dados só explicam e voltam. |
| `teste_gui_copiar.py` | Botões 'Copiar' do painel do item e do formulário de edição: copiam o valor certo, mostram 'Copiado', limpam a área de transferência e voltam ao normal. |
| `teste_gui_criar.py` | Tela de CRIAR o cofre (primeiro uso): campos da senha mestra, validações e criação do arquivo. |
| `teste_gui_dados_bancarios.py` | Interface: dados bancários (número da conta / agência) no formulário de item. Verifica que os campos aparecem ao marcar as caixas, salvam e sobrevivem a fechar/reabrir o cofre (cifrados), |
| `teste_gui_desempenho_usabilidade.py` | Desempenho e usabilidade da interface (Linux/xvfb). Mede tempos, vazamento de janelas/widgets/timers e memória em ciclos repetidos, paginação/busca/ordenação com milhares de contas, e confere critérios de usabilidade: foco inicial, |
| `teste_gui_diagnostico.py` | Teste de interface (Tk): menu ⋯ › Diagnóstico mostra os registros cifrados (só com o cofre aberto), pendrive removido durante uma gravação mostra mensagem clara (sem caminho) e não perde nada na memória. Veja testes/COMO_RODAR_OS_TESTES.md. |
| `teste_gui_efeitos.py` | Animação e efeitos: a troca de tela é única (sem quadro vazio), a janela nunca fica transparente/invisível, o aviso 'Verificando…/Salvando…' aparece só quando demora e some sempre (mesmo com erro), não sobram janelinhas, |
| `teste_gui_em_uso.py` | COFRE ABERTO EM OUTRA JANELA: a segunda janela (App(..., em_uso=True)) vai direto para o MODO CONSULTA, sem perguntar, com faixa de aviso própria, ações que alteram dados só explicam e nada é gravado. Também confere a faixa de REVERSÃO. |
| `teste_gui_energia.py` | Suspender o PC / bloquear a sessão (Win+L): apaga as chaves da memória e bloqueia; trocar a senha mestra pela tela e a chave de acesso nova. |
| `teste_gui_fido.py` | Tela de chaves FIDO2 e filtros da lista: cadastro/remoção de chaves, item antigo ganhando campos novos, filtro por grupo. |
| `teste_gui_fluidez_animacoes.py` | Testes de FLUIDEZ e GLITCHES visuais (Linux/xvfb): janelas que deviam fechar antes de mexer no campo por baixo, textos com destaque/tamanho dinâmico, ajuste do diálogo sem rolagem, e arraste do cartão do |
| `teste_gui_fontes.py` | FONTES NOMEADAS: preparar_fontes pode ser chamada de novo (mesma janela ou outra janela) sem erro. Antes, a segunda chamada falhava com "named font ... does not exist" no Python 3.14 do Windows (descartar o objeto Font antigo apagava a |
| `teste_gui_forca.py` | Força das senhas na interface: senha repetida/fraca nos alertas, 'Verificar senhas', troca por senha forte e a impressão da folha de emergência. |
| `teste_gui_importacao.py` | Importar planilha pela interface: itens entram no cofre, a planilha é apagada depois, o aviso de itens que precisam de atenção. |
| `teste_gui_imprimir_chave.py` | Impressão: o cofre só imprime a cópia de emergência da chave de acesso e do código de recuperação, e só depois de pedir a senha mestra. Itens não têm 'Imprimir'; qualquer outro título é bloqueado; a senha mestra nunca é impressa; |
| `teste_gui_item_simples.py` | Interface: formulário SIMPLES de novo item (nome, grupo, pessoa, usuário, senha), sem botão 'Mais opções'. Para leigos e idosos: poucos campos, poucos cliques. Roda no Linux com xvfb-run. |
| `teste_gui_janelas_aparecem_prontas.py` | Janelas e telas aparecem PRONTAS: mede cada janela no instante em que ela é mostrada e de novo depois que "assenta" (0,8 s). Se o tamanho da janela ou a posição/tamanho de QUALQUER botão, texto ou campo mudar depois de aparecer, é o |
| `teste_gui_limpeza_ao_bloquear.py` | Limpeza ao bloquear: depois de bloquear não sobra lista, barra lateral, hash do detalhe com segredo nem campos revelados na memória. |
| `teste_gui_navegacao.py` | Navegação completa: abrir cada tela e bloquear várias vezes, grupos/busca/itens, revelar e copiar, atalhos, capa de 'conteúdo oculto', seleção de senha (Ctrl+A, Delete) e nada cortado em 900x600. |
| `teste_gui_olho.py` | Botão do 'olho' (mostrar/ocultar a senha): mostra, esconde sozinho depois de um tempo e continua sem permitir copiar. |
| `teste_gui_passeio.py` | Teste de interface: passeio guiado (retângulo amarelo + escurecimento + Próximo), oferta na 1ª abertura, passeio do formulário de item e limpeza das janelas auxiliares. Roda no Linux com xvfb-run. |
| `teste_gui_perfis.py` | Teste de interface: ordem A→Z/Z→A, mover contas entre perfis (arrastar/menu), avaliação em tempo real, tela montada de uma vez e ausência do botão Gerador ao lado de 'Novo item'. Roda no Linux com xvfb-run. |
| `teste_gui_pessoas.py` | Perfis (pessoas): lista lateral 'Eu' + 'Adicionar', grupo antigo virando pessoa, cabeçalhos de planilha 'Dono/Titular'. |
| `teste_gui_recorte.py` | Recorte de texto e de botões: em vários tamanhos de janela, nenhuma tela nem janela pode ter rótulo/botão/campo CORTADO (largura/altura real menor que a pedida) nem widget fora da área visível da janela. Roda no Windows ou no |
| `teste_gui_resiliencia_uso.py` | Interface sob uso real e abuso: cliques freneticos, texto absurdo, perda de foco, ciclos de abrir/fechar, janelas modais, tela de integridade e aviso do pendrive. Roda no Linux com xvfb-run e no Windows. |
| `teste_gui_salvar_fluido.py` | Interface: o salvamento (lento num pendrive FAT32) NÃO congela a janela; o aviso 'Salvando…' só aparece se passar de 0,4 s; o bloqueio automático espera a gravação acabar; erros de formato da chave contam depois de 3. |
| `teste_gui_seguranca.py` | Interface: checagem de vazamentos (rede simulada) e janela do bloqueio automático configurável. |
| `teste_gui_semfoco.py` | Teste de interface: fora do programa por 60 s bloqueia e apaga as chaves; voltar antes disso não bloqueia. |
| `teste_gui_soak_longa_duracao.py` | SOAK TEST DA INTERFACE: ciclos seguidos (padrão 60; 1.000 = cerca de 50 min, use COFRE_SOAK_CICLOS=1000) de desbloquear -> usar -> bloquear com o Tkinter de verdade. Complementa o teste de 30 ciclos (teste_gui_resiliencia_uso): aqui o uso é MUITO prolongado, p |
| `teste_gui_teclado_espiao.py` | Teclado virtual e ferramentas espiãs: a tela mostra a dica do teclado; com depurador/espião aberto o cofre recusa abrir ou se bloqueia (sem destruir o arquivo nem gastar tentativa). |
| `teste_gui_teclado_virtual.py` | Teclado virtual: as teclas são criadas UMA vez e só trocam de letra (sem recriar, sem piscar), digitam no campo, apagam, alternam maiúsculas, mostram a contagem sem revelar a senha, fecham com Esc e respondem rápido. |
| `teste_gui_tentativas.py` | Teste de interface: o selo 'Tentativas restantes' da tela inicial acompanha cada senha errada, o aviso fica acima do botão e o MODO CONSULTA avisa que não conta tentativas. Roda no Linux com xvfb-run. |
| `teste_gui_tentativas_config.py` | Tentativas erradas: as setas das caixas numéricas funcionam (clique real sobe/desce), a tela de criar NÃO mostra mais a opção (ela fica dentro do cofre, ⋯ > Tentativas erradas, e pede a senha mestra), a mudança é gravada no cofre e vale |
| `teste_gui_visual_varredura.py` | Varredura VISUAL da interface da Arca (Tk real), em varias escalas do Windows e varios tamanhos de janela. O que procura, em cada tela (criar, desbloqueio, principal e a janela "Novo item"): |
| `teste_gui_windows.ps1` | Prepara um ambiente Python temporário e roda a bateria de interface (rodar_todos.py --so gui) no Windows, gravando o resultado. |
| `teste_icones.py` | Verifica ícones de marcas; use --visual para abrir uma grade demonstrativa de 40 marcas. |
