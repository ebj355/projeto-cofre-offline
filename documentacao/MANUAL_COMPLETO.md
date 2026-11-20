# 🔐 Cofre de Senhas

Gerenciador de senhas **100% local** para Windows. É um único programa, sem nuvem nem conta e sem conexões automáticas. A verificação online de senhas vazadas é opcional e só ocorre quando solicitada. Ele tem:

- criptografia em cascata (**ChaCha20-Poly1305 dentro de AES-256-GCM**);
- senha mestra protegida por **Argon2id com 1 GiB de memória**;
- desbloqueio em **dois fatores** (senha + chave de acesso de 160 bits), com **chave FIDO2** física opcional (YubiKey etc.);
- **autodestruição** quando as tentativas de senha acabam, com cópias de segurança automáticas contra arquivo danificado;
- várias camadas de proteção do Windows contra espionagem;
- interface escura no estilo Windows 11.

> **Princípio do projeto:** a segurança não depende de o código ser secreto. Tudo aqui pode ser lido e auditado. O que protege os seus dados é a matemática: a senha mestra, a chave de acesso e, opcionalmente, a chave física. Sem elas, o arquivo do cofre é só ruído aleatório.

---

## Sumário

1. [O que o cofre faz](#1-o-que-o-cofre-faz)
2. [Como a segurança funciona](#2-como-a-segurança-funciona)
3. [Proteções do Windows](#3-proteções-do-windows)
4. [Limites: o que nenhum cofre consegue impedir](#4-limites-o-que-nenhum-cofre-consegue-impedir)
5. [Instalação](#5-instalação)
6. [Primeiros passos](#6-primeiros-passos)
7. [Atalhos de teclado](#7-atalhos-de-teclado)
8. [Estrutura do projeto](#8-estrutura-do-projeto)
9. [Testes automáticos](#9-testes-automáticos)
10. [Ferramentas extras de segurança do Windows](#10-ferramentas-extras-de-segurança-do-windows)
11. [Cuidados ao publicar no Git](#11-cuidados-ao-publicar-no-git)
12. [Perguntas frequentes](#12-perguntas-frequentes)
13. [Camadas de segurança (visão organizada)](#13-camadas-de-segurança-visão-organizada)
14. [O que mudou neste projeto](#14-o-que-mudou-neste-projeto)

---

## 1. O que o cofre faz

### 1.1 Desbloqueio

| Fator | Como é | Observação |
|---|---|---|
| **Senha mestra** | Mínimo de 14 caracteres. Senhas só com números, sequências (123456, qwerty), senhas de listas vazadas e senhas que o medidor de entropia classifica como Fraca ou Muito fraca (ex.: `Corinthians2024!!`) são recusadas | Passa pelo Argon2id: cada tentativa custa 1 GiB de memória e alguns segundos |
| **Chave de acesso (token)** | 160 bits aleatórios no formato `XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XX` (os 2 últimos caracteres são de verificação: um erro de digitação é percebido **sem gastar tentativa**; chaves antigas de 32 caracteres continuam valendo). Pode ser digitada ou carregada de um arquivo `.key` | Aparece **uma única vez**, ao criar o cofre. Dá para salvar em `.key` ou anotar à mão. **Não é impressa**, para não passar pela fila de impressão do Windows |
| **Chave FIDO2** (opcional) | Chave física USB/NFC (YubiKey 5, Feitian ePass FIDO2…) com PIN e toque | Aceita várias chaves (principal + reserva) e gera um **código de recuperação** em papel |
| **Computador autorizado** (opcional) | O cofre só abre nos computadores da lista (até 8), reconhecidos pelo **MachineGuid do Windows + UUID da placa-mãe** (não pelo disco, placa de rede ou IP, que mudam) | Fator **a mais** (senha + chave FIDO + computador), nunca alternativa à chave FIDO. Em computador fora da lista o cofre recusa **sem gastar tentativa**; só o **código de recuperação** abre. Menu ⋯ › *Computadores autorizados…* |

**Modos de desbloqueio**, escolhidos ao criar o cofre:

- **Só senha mestra:** o jeito mais simples. Não existe chave de acesso; a segurança vem da senha longa + Argon2id. A chave FIDO continua opcional por cima.
- **Senha E chave de acesso (recomendado):** os dois fatores são obrigatórios. Quem descobrir a senha ainda precisa da chave, e vice-versa.
- **Senha OU chave de acesso:** qualquer um dos dois abre o cofre. A chave funciona como recuperação se você esquecer a senha.

**Telas limpas:** a tela de desbloqueio mostra só o título, os campos, o botão e o selo de tentativas restantes; textos longos ficam atrás do botão **?**. Operações pesadas (derivação Argon2id, abrir, criar e salvar) rodam em **threads separadas** e a janela continua respondendo; trocar de tela monta a nova antes de apagar a antiga (sem piscar).

Na tela de criação, as escolhas aparecem em três etapas: senha mestra, modo de abertura e proteção contra tentativas. Cada modo explica o que será exigido e o resumo do próximo passo informa quando a chave de acesso será mostrada uma única vez. Os detalhes técnicos ficam atrás do botão **?**. Na tela de desbloqueio só aparecem a senha e o botão; o botão **Avançado ▾** mostra o estado da proteção.

A **chave FIDO** soma um fator a mais em qualquer um dos modos (pode ser marcada já na criação):

- Pode ser adicionada, trocada ou removida depois, a qualquer momento.
- O cadastro pede **3 toques** e confere se a chave responde sempre igual. Só depois disso ela é ligada ao cofre.
- Se a chave for perdida, o **código de recuperação** substitui a chave física.
- **FIDO só vale depois do primeiro cadastro:** se você marcou a opção ao criar o cofre mas ainda não cadastrou a chave, o cofre abre normalmente só com a senha (e a chave de acesso, se o modo exigir). A partir do primeiro cadastro, a chave passa a ser obrigatória.

**Computadores autorizados (como funciona):** cada computador da lista guarda uma *embalagem* de um segredo aleatório do cofre, cifrada com uma chave derivada da identidade dele (HKDF sobre MachineGuid + UUID SMBIOS + sal do cofre). Esse segredo entra na chave dos dados junto com o da chave FIDO: um arquivo de cofre levado para outro computador **não tem como** ser decifrado (não há lista para editar nem tela para pular). O primeiro computador gera o **código de recuperação único** (vale também para a chave FIDO; gerar outro invalida o anterior). Reinstalar o Windows ou trocar a placa-mãe muda a identidade: abra com o código de recuperação e autorize de novo. **Limites:** o MachineGuid é legível por qualquer programa no computador, então isto protege contra **pendrive roubado**, não contra quem já está no seu computador; backups feitos antes de ativar continuam abrindo em qualquer computador. Sem o código de recuperação, se todos os computadores da lista mudarem, o cofre não abre.

**Reforço com segredo local (Windows, recomendado):** ao autorizar um computador, o programa pergunta se quer o *reforço*. Ele cria um segredo aleatório em `%LOCALAPPDATA%\CofreSenhas\pc_local.bin`, protegido pelo **DPAPI** do Windows (só a sua conta de usuário neste computador o abre) e o mistura na identidade do computador (HMAC-SHA256). Assim, copiar o MachineGuid de um computador já **não basta** para se passar por ele: falta o segredo guardado pela conta. O cofre decide sozinho qual variante vale (nenhuma mudança no formato do arquivo). Se o segredo for apagado ou a conta mudar, o computador deixa de ser reconhecido: abra com o código de recuperação e autorize de novo. **Limite:** malware rodando **como você** neste computador ainda pode pedir ao DPAPI o segredo. A suíte nativa foi executada em Windows real e incluiu criação, adulteração e restauração do segredo DPAPI.

**Nível de proteção (ranking):** o painel do escudo, na barra lateral, mostra uma barra e a nota de **0 a 100** (Básica, Boa, Forte, Máxima). Ao abrir o painel, o cofre lista o que está ativo (senha mestra 30, chave de acesso 25/12, chave FIDO 20, segunda chave 7, computador autorizado 10, proteção Argon2 10/5; soma limitada a 100) e oferece **Ativar** no que falta e pode ser ligado depois (FIDO, reserva, computador).

**Backup:** *Backup do cofre* pede e confere a **chave de acesso** antes de gerar a cópia (cofre "só senha" não tem chave). A cópia é idêntica ao arquivo original e abre com os mesmos fatores dele; torná-la abrível só com a senha enfraqueceria o backup, por isso não é feito.

### 1.2 O que cada item guarda

| Campo | Exemplo |
|---|---|
| Conta / App | Banco, Gmail, Samsung… |
| Login | e-mail, CPF, usuário |
| Senha | senha principal |
| Senha extra | senha de transação, segunda senha |
| PIN | senha numérica |
| Chave | chave de API, chave Pix, token |
| Número da conta | dado bancário (ver nota abaixo) |
| Agência | dado bancário (ver nota abaixo) |
| Códigos de recuperação | uma lista, um por linha |
| Notas | texto livre |
| Grupo | organiza a barra lateral (cada grupo tem sua cor) |
| Pessoa | de quem é a conta: Eu, Pai, Mãe… (vazio = Eu) |

### 1.2.1 Pessoas

Um mesmo cofre guarda as senhas de várias pessoas, como você, seu pai e outros familiares:

- A barra lateral tem a seção **PESSOAS**, com Todas as pessoas, Eu, Pai e **+ Adicionar pessoa**. Os **grupos** mostrados são os da pessoa escolhida (Pai → Bancos).
- Novas contas já vêm com a pessoa que está selecionada.
- Na visão "Todas as pessoas", a lista mostra de quem é cada conta.
- **Botão direito numa pessoa:** Renomear ou Remover. Ao remover, as contas dela não são apagadas: passam para "Eu".
- **Botão direito num grupo:** **Transformar em pessoa**. Serve para quem importou uma aba "pai" da planilha e quer que ela vire a pessoa "Pai".
- Na importação, as colunas **Pessoa**, **Dono** ou **Titular** viram a pessoa. Linhas sem essa coluna vão para a pessoa escolhida na tela de conferência.
- Os nomes das pessoas também ficam **criptografados** dentro do cofre.

Todas as pessoas ficam no **mesmo cofre**, abertas pela sua senha mestra.

A **proteção extra** (pedir a senha mestra de novo para ver ou copiar, com liberação de 30 segundos) é um único ajuste para **todo o cofre** — `⋯ → Segurança → Proteção extra` — em vez de uma caixinha por item (era assim até 2026-11-13; a caixinha "Item protegido" deixava o formulário "Novo item" poluído e confuso, e foi removida de lá).

**Dados bancários (Número da conta / Agência) — camada extra sempre ativa (2026-11-15):** esses dois campos funcionam como qualquer outro segredo (ocultos, cifrados, com botão de copiar), mas têm uma proteção própria, que **não depende** do ajuste "Proteção extra" acima: qualquer item que tenha número da conta e/ou agência preenchidos **sempre** pede a senha mestra de novo para ser visto, copiado ou editado, mesmo com a proteção extra geral desligada. É pensado para quem quer o cofre normal "destravado" no dia a dia, mas quer uma trava a mais especificamente nos dados bancários. A liberação vale por 30 segundos, igual à proteção extra geral (mesmo relógio).

### 1.3 Gerador de senhas

| Tipo | Tamanho | Uso |
|---|---|---|
| **Aleatória** | 8 a 64 caracteres, com números e símbolos opcionais | Contas de sites e apps (você não precisa decorar) |
| **Fácil de lembrar** | 3 a 10 palavras pronunciáveis | Senhas que você precisa digitar de cabeça |
| **PIN** | 4 a 12 dígitos | PINs óbvios (1234, 0000, 1212, anos…) são descartados |

- O sorteio usa o gerador criptográfico do sistema (`secrets`). Nada passa pela internet.
- A força mostrada é **exata**, calculada pelo número de combinações possíveis.
- Na senha gerada, números e símbolos aparecem em cores diferentes, para facilitar a leitura.

### 1.4 Avaliação de força

A avaliação segue o estilo do verificador do 1Password e do Kaspersky. Ela mostra:

- **nota e barra** (Muito fraca → Muito forte) com os bits estimados;
- **composição** em etiquetas (maiúsculas, minúsculas, números, símbolos);
- **tempo médio para descobrir** em dois cenários:
  - alguém **roubou o arquivo do cofre**: cerca de 1 milhão de tentativas por segundo contra o Argon2id de 1 GiB, mesmo com muitas placas de vídeo;
  - a senha **vazou de um site** com proteção fraca: cerca de 100 bilhões de tentativas por segundo;
- **recomendações** do que melhorar.

A estimativa é **realista**, não ingênua. Ela reconhece e penaliza:

- palavras comuns e senhas de listas vazadas;
- trocas óbvias de letras (`P@ssw0rd`, `Tr0mb0ne`, `s3nh@`);
- sequências e repetições;
- anos e datas;
- frases com poucas palavras.

Além disso, **Verificar senhas** (menu ⋯) audita o cofre inteiro e aponta:

- senhas fracas;
- **senhas repetidas** em mais de uma conta;
- PINs fáceis de adivinhar.
- e, **só se você pedir**, o botão **Checar vazamentos (online)** confere se alguma senha já apareceu em vazamentos conhecidos (veja a pergunta "O programa acessa a internet?").

Os itens com problema também aparecem no filtro **⚠ Atenção** da barra lateral.

### 1.5 Importação de planilhas

- Lê arquivos **Excel (.xlsx, .xlsm)** e **CSV**, inclusive as exportações do Chrome e do Samsung Pass.
- Encontra o cabeçalho sozinho, mesmo com título em cima ou linhas vazias.
- Entende nomes de coluna em português e inglês, com ou sem acento (Serviço/Site/URL, Login/Usuário/E-mail, Senha/Password, PIN…).
- Lê **cada aba** como um grupo.
- Reconhece abas de **códigos de recuperação** sem cabeçalho (um nome seguido dos códigos).
- Antes de importar, mostra uma **prévia** separando cada linha em **nova**, **igual (ignorada)** ou **com dados diferentes**. Você decide se quer atualizar as que já existem.
- Avisa quando o Excel comeu o zero à esquerda de um PIN (por exemplo, `0123` que virou `123`).
- Ao final, oferece **apagar a planilha com segurança**: ela é sobrescrita com dados aleatórios antes de ser apagada, porque guarda as senhas sem criptografia.
- Por segurança, usa `defusedxml` contra arquivos maliciosos e limita o tamanho a 50 MB e 20.000 linhas.
- **Quarentena antes do cofre:** o arquivo é conferido pelos *magic bytes* (um .xlsx precisa ser um ZIP de verdade), copiado para uma pasta isolada (`.tmp_cofre/quarentena_*`), varrido (macros, ActiveX, objetos embutidos, vínculos externos, DDE, fórmulas, DOCTYPE/ENTITY, limites de zip-bomb), lido **só como valores** (sem executar nada, sem abrir outro programa) com tempo limite, e cada campo é **sanitizado** (tamanho máximo, caracteres de controle e de inversão de texto removidos). Só depois os dados chegam ao cofre. A cópia da quarentena é sobrescrita e apagada ao fim.
- **Importação SEGURA (padrão):** o cofre só aceita a planilha **gerada por ele mesmo** (menu ⋯ → *Baixar modelo de planilha*). Ele recusa, antes de ler qualquer dado: CSV e outros formatos, planilhas comuns sem o selo, planilhas de **outro** cofre, modelos com a estrutura alterada e qualquer arquivo com partes que não sejam texto XML. Na prévia, uma lista verde **"Verificação de segurança"** mostra o que foi conferido (selo, estrutura, varredura). Para voltar a aceitar planilhas comuns (Chrome, Samsung), mude `IMPORTAR_SOMENTE_COM_SELO = False` no topo do código e recompile.
- **Modelo profissional e selado:** a planilha tem as abas **Leia-me** (passo a passo, regras de segurança e tabela das colunas), **Senhas** (tabela do Excel com colunas *Conta/App, Login, Senha, Senha extra, PIN, Chave, Códigos, Notas, Grupo, Perfil*, listas suspensas de Grupo e Perfil e linhas EXEMPLO que são ignoradas) e **Listas**. Uma aba **muito oculta** (`_selo_cofre`) guarda o selo: um HMAC-SHA256 com chave derivada (HKDF) do cabeçalho do **seu** cofre sobre a estrutura (nomes das abas e títulos das colunas). Você preenche as linhas à vontade; se alguém mexer na estrutura ou forjar o selo, o cofre recusa. As linhas de dados continuam passando pela varredura (macros, vínculos externos, fórmulas, DOCTYPE, zip-bomb).
- O modelo fica ligado ao cofre que o gerou: depois de reinstalar ou "apagar tudo", baixe um modelo novo.

### 1.6 Impressão

O cofre **só imprime duas coisas**: a **chave de acesso** e o **código de recuperação**, as cópias de emergência que aparecem **uma única vez**, na hora em que são geradas. Senhas, itens, backups, planilhas e a senha mestra **nunca** são impressos (não existe botão nem atalho de impressão na lista de senhas, e o código recusa qualquer outro título).

- **Senha mestra antes:** clicar em *Imprimir só a chave…* ou *Imprimir só o código…* pede a **senha mestra** de novo; sem ela nada vai para a impressora.
- **Nome genérico na fila:** o trabalho aparece no Windows como `Documento_Sistema`, sem dizer o que é. (O conteúdo da folha continua sendo o que você imprimiu: o nome genérico só evita pista no histórico.)
- **Aviso na tela:** as duas janelas mostram *"Impressão bloqueada para senhas; liberada só para esta cópia de emergência (pede a senha mestra)."*
- **Fila do Windows:** o Windows guarda o trabalho numa pasta do disco C: até o fim, e impressoras de rede o enviam pela rede. Use uma impressora USB sua e pegue a folha na hora. Anotar à mão continua sendo a forma mais segura.
- O cofre avisa quando a "impressora" escolhida na verdade gera arquivo (Microsoft Print to PDF, XPS, OneNote) e pede confirmação.

### 1.7 Cópia segura

Cada campo tem um botão **Copiar**, que vira **✓ Copiado** só quando a cópia protegida deu certo (se foi recusada, aparece o aviso e o botão não muda). A cópia:

- **fica fora** do histórico do Windows (Win+V) e da nuvem;
- é marcada para ser ignorada por programas que monitoram a área de transferência;
- é **apagada sozinha em 15 segundos**;
- se o Windows não conseguir fazer a cópia protegida (fora do histórico), o programa **recusa copiar** e avisa, em vez de usar a área de transferência comum.

Nos campos de senha, o **Ctrl+C**, o recortar, o arrastar e o menu do botão direito ficam **bloqueados**. A cópia só acontece de propósito, pelo botão.

### 1.8 Histórico e alerta de invasão

- Cada abertura do cofre fica registrada **dentro do próprio cofre, criptografada**, então um invasor não consegue apagar o rastro. O registro guarda a data e quantas tentativas erradas houve antes.
- Se alguém errou a senha desde a última vez que você abriu o cofre, aparece um **⚠ ALERTA DE SEGURANÇA** assim que você entra.
- O histórico completo fica em menu ⋯ → **Histórico de aberturas**.

### 1.8.1 Adicionar um item (modo simples)

A janela **Novo item** é uma tela só, sem botão "Mais opções": nome, grupo, usuário, pessoa e senha (com o **Gerar…** do próprio campo). PIN, senha extra, chave, **número da conta/agência**, códigos e notas só aparecem quando você marca a caixa correspondente em "Este item também tem". O botão **Copiar** só existe ao **editar** um item (em item novo não há o que copiar). **Enter** salva. Marque as caixas "Número da conta" e "Agência" (em "Este item também tem") para guardar dados bancários — eles herdam a camada extra de proteção descrita em 1.2.

### 1.9 Interface

- **Tema escuro** no estilo Windows 11, com acento índigo, barra de título escura e cantos arredondados.
- Todos os ícones são **desenhados pelo próprio programa**: não dependem de fontes nem de arquivos externos.
- **Tela principal:**
  - barra lateral com grupos coloridos e contadores;
  - lista em duas linhas com avatar colorido;
  - painel de detalhes com os botões Mostrar e Copiar;
  - quadro de status da proteção.
- **Busca instantânea** (Ctrl+F, com um pequeno atraso de 150 ms para não refazer a tela a cada tecla) e **atalhos de teclado**.
- **Aviso de Caps Lock** ao lado dos campos de senha quando a tecla está ligada (errar a senha por isso custa uma tentativa).
- Reautenticar um item protegido usa um **verificador rápido** na memória (HMAC com chave aleatória da sessão): instantâneo, sem repetir o Argon2. Criar o cofre, trocar a senha e abrir usam o Argon2 completo, com uma tela de espera ("pode levar alguns segundos") em vez de congelar a janela.
- Cores com contraste mínimo WCAG AA (4,5:1) nos textos secundários e no botão principal.
- Os dados cifrados guardam uma **versão de esquema** (`meta["schema"]`) para migrações futuras. Pessoas e grupos são alterados por uma **transação** (`Cofre.transacao()`): se a gravação falhar, tudo volta ao que era.
- **Olho 👁** nos campos de senha para conferir o que foi digitado. Volta a esconder sozinho em 30 segundos.
- Funciona em telas com **zoom de 125% e 150%**, e as imagens continuam nítidas.
- Em telas baixas, como notebooks de 768 px, as janelas grandes ganham **barra de rolagem** automaticamente.
- Todas as mensagens são em português e explicam o que fazer, não só o que deu errado.
- **Textos curtos, detalhes no "?"**: nada de parágrafos na tela; o resto abre numa janelinha.
- **Sem piscar:** janelas só aparecem depois de prontas; a lista só redesenha quando algo mudou e só desenha as linhas visíveis (6.000 contas rolam sem engasgar); o aviso "Conteúdo oculto" tem 1,5 s de tolerância.
- **Caps Lock:** um ícone discreto (⇪ Caps) aparece **dentro** do campo de senha enquanto a tecla estiver ligada.
- **Chave FIDO:** os erros dizem o próximo passo ("toque na chave quando piscar", "o PIN não confere", "use a chave cadastrada"); o código técnico só aparece entre parênteses no fim.
- **Arquivo de chave protegido:** "Salvar arquivo protegido (.key)" grava a chave de acesso **cifrada** (ChaCha20-Poly1305, selada com os dados do cabeçalho deste cofre). Só o cofre dono a decifra e carrega ("Carregar .key…" na tela de desbloqueio); outro cofre, byte alterado ou arquivo cortado são recusados com mensagem clara e sem gastar tentativa. Arquivos `.key` antigos (texto) ainda carregam. Se a senha mestra do modo "senha OU chave" for trocada, salve um arquivo novo (a chave anotada em papel continua valendo).
- **Gravação sem travar a tela:** salvar no pendrive (lento em FAT32/antivírus) roda fora da thread da janela; o aviso "Salvando…" só aparece se passar de 0,4 s, a leitura da lista de processos também saiu da thread da janela, e o bloqueio automático espera a gravação acabar.
- **Tentativas e erros de digitação da chave:** chave num formato impossível não gasta tentativa nas 3 primeiras vezes da sessão; a partir da 4ª, cada erro **conta**. Em modo consulta/outra janela aberta nada é contado (a tela avisa).
- **Instalador, recomeçar do zero:** se já existe cofre no destino, o instalador pergunta: 1 = manter (padrão) ou 2 = apagar tudo (cofre, cópias, registro) e começar do zero, exigindo digitar APAGAR.
- **Instalador:** mostra uma barra de progresso (`[#####.....] 40%`) e "Etapa N de 5" em cada etapa.
- **Avisos iniciais só uma vez** (`avisos_vistos.json`, só guarda o hash do texto, ao lado do programa).
- **Memória e PCs fracos:** a blindagem sugerida na criação cai de *Máxima* (1 GiB) para *Alta* (256 MiB) se houver pouca RAM livre; antes de qualquer derivação o programa recusa (sem gastar tentativa) se faltar memória física, para o Windows não paginar. O cache de força de senhas tem teto de 1.000 itens (FIFO) e é esvaziado ao bloquear. A área de transferência é limpa em 15 s.
- Derivação Argon2id, gravação e verificações pesadas rodam **fora da thread da janela**, com tela de espera.

---

## 2. Como a segurança funciona

### 2.1 Visão geral das chaves

```
                         ┌──────────────────────────────┐
  senha mestra ──Argon2id──► KEK da senha ─┐            │
                         │                 ├─(modo E)─► KEK combinada ─┐
  chave de acesso ─HKDF──► KEK da chave ───┘            │              │
  (160 bits)             │                              │              ▼
                         │           AES-256-GCM embrulha a ►  DEK (chave interna,
                         │                                    256 bits aleatórios)
                         │                                              │
  chave FIDO2 ──PRF/hmac-secret──► segredo F ──HKDF(DEK‖F)──────────────┤
  (opcional)             │                                              ▼
                         │                               chave dos dados
                         │                                 │         │
                         │                            HKDF │         │ HKDF
                         │                                 ▼         ▼
                         │                         ChaCha20-Poly1305 → AES-256-GCM
                         │                          (camada interna)   (camada externa)
                         └──────────────────────────────────────────────────────────┘
```

| Peça | Algoritmo | Detalhes |
|---|---|---|
| Chave interna (DEK) | Aleatória, 256 bits | Sorteada uma vez. Trocar a senha só **reembrulha** a DEK, sem recriptografar tudo |
| Senha → chave | **Argon2id** | Nível **Máxima**: 1 GiB de memória e 6 iterações. Nível **Alta**: 256 MiB e 4 iterações. Paralelismo 2, sal aleatório de 128 bits |
| Chave de acesso → chave | **HKDF-SHA256** | 160 bits de entropia: não precisa de Argon2 |
| Modo dois fatores | HKDF(KEK da senha ‖ chave de acesso) | Sem as **duas**, a chave que abre a DEK não existe |
| Embrulho da DEK | **AES-256-GCM** | Um embrulho para a senha e outro para a chave (modo OU), ou um combinado (modo E) |
| Dados | **ChaCha20-Poly1305 dentro de AES-256-GCM** | Duas cifras de famílias diferentes, com subchaves independentes (HKDF). Uma falha futura em uma delas não expõe os dados |
| Fator FIDO | Extensão **PRF / hmac-secret** | A chave física devolve um segredo que nunca sai do chip. Esse segredo destrava o fator F, e F entra na derivação da chave dos dados |
| Código de recuperação FIDO | HKDF + AES-256-GCM | Embrulha o mesmo F, para substituir a chave física em emergências |
| Tamanho | Preenchimento em blocos de **4 KiB** | O tamanho do arquivo não revela quantos itens existem |
| Integridade | Cabeçalho e seção FIDO autenticados (AAD), dados com etiqueta GCM/Poly1305 | Qualquer alteração no cabeçalho, na seção FIDO ou nos dados é detectada. O contador de tentativas fica fora da autenticação (ele muda a cada tentativa); se estiver fora do possível, o arquivo é tratado como danificado |

Todo nonce é aleatório e novo a cada gravação. As gravações são **atômicas** (arquivo temporário seguido de troca), então uma queda de energia não corrompe o cofre.

### 2.2 Formato do arquivo (`COFRE05`)

```
┌────────────────────────── cabeçalho fixo (autenticado) ──────────────────────────┐
│ MAGIC "COFRE05" │ t │ m │ p │ max_tentativas │ modo │                            │
│ sal_senha(16) │ nonce(12) │ embrulho_senha(48) │                                 │
│ sal_chave(16) │ nonce(12) │ embrulho_chave(48) │ nonce_chacha(12) │ nonce_aes(12)│
│ checksum(8): SHA-256 truncado de cabeçalho + seção FIDO (só detecta bit-rot)       │
├──────────────────────────────────────────────────────────────────────────────────┤
│ contador de tentativas restantes (1 byte, fora da autenticação, conferido)       │
├──────────────────────── seção FIDO (autenticada) ────────────────────────────────┤
│ ativo │ nº de chaves │ sal │ embrulho do código de recuperação │                 │
│ para cada chave: nome │ ID da credencial │ nonce │ embrulho de F                 │
├──────────────────────── dados ───────────────────────────────────────────────────┤
│ AES-256-GCM( ChaCha20-Poly1305( JSON {itens, histórico} + preenchimento 4 KiB ) ) │
└──────────────────────────────────────────────────────────────────────────────────┘
```

Cofres criados por versões anteriores (`COFRE01` a `COFRE04`) são abertos e **convertidos automaticamente** para o formato atual; a cópia de segurança da migração guarda o arquivo original.

O **checksum** do `COFRE05` não é segurança: serve para distinguir um arquivo **danificado** (setor ruim do pendrive) de uma **senha errada**. Se ele não bater, o cofre recusa abrir, não gasta tentativa e oferece restaurar a cópia de segurança.

**Trocar a senha ou a chave de acesso troca também a chave interna dos dados (DEK) e recifra tudo.** Assim, quem tem a senha antiga e uma cópia velha do arquivo não abre o arquivo novo. (No modo OU, a troca de senha precisa refazer o cadeado da chave de acesso: o cofre usa a chave que você digitar ou gera uma nova.) **Backups seus, feitos antes da troca, continuam abrindo com a senha antiga.**

**Senhas com acento** (`é`, `ç`…) funcionam em qualquer forma de Unicode (NFC/NFD/NFKC), gastando uma só tentativa. **Duas janelas** do mesmo cofre são impedidas, e o programa se recusa a gravar por cima se o arquivo mudou desde que foi aberto.

### 2.3 Autodestruição e arquivo danificado

**Quantas tentativas:** o cofre nasce com **3 tentativas erradas**. A opção **não fica na tela de criar** (é uma medida de segurança): ela é uma configuração **dentro do cofre**, em ⋯ › **Tentativas erradas** (1 a 10, botões − e +). Mudar pede a **senha mestra** e grava o limite no cabeçalho do cofre; backups antigos continuam com o limite antigo. Em cofres com mais de um fator, só gasta tentativa o erro da senha, da chave de acesso (bem formada) ou do código de recuperação: chave FIDO errada, fator faltando ou chave mal formada (as 3 primeiras por sessão) **não gastam**.

O programa **sobrescreve o arquivo 3 vezes com dados aleatórios e o apaga** (junto com as cópias `.bak1` a `.bak5`, `.danificado` e o registro de diagnóstico ao lado dele) quando:

1. **As tentativas de senha acabam.** O número é escolhido ao criar o cofre, de 1 a 10. O contador é **gravado no disco antes de a senha ser testada**, então desligar o PC no meio de uma tentativa não devolve a tentativa.

O que **não** destrói o cofre, porque um byte ruim no pendrive não pode custar o cofre:

- **Arquivo danificado ou alterado** (contador fora do possível, dados que não conferem). O programa recusa abrir, **não gasta tentativa**, não apaga nada e oferece restaurar a cópia de segurança mais recente. O arquivo ruim fica guardado como `cofre.dat.danificado`.
- **Depurador ligado** ao programa compilado (`.exe`): o cofre não abre, ou, se já estiver aberto, fecha e apaga as chaves da memória. O arquivo **não é alterado**, porque antivírus e ferramentas legítimas também se anexam a programas. Ao rodar o `.py`, depuradores de IDEs são ignorados.
- **Cofre já aberto em outra janela (trava `.lock`, vale entre sessões do Windows e entre letras de unidade).** A primeira janela é a "dona" (grava). Se você abrir o mesmo cofre de novo, o programa **avisa na hora** e a segunda janela abre direto em **MODO CONSULTA** (faixa "este cofre está aberto em OUTRA janela"): vê e copia, não grava, não conta tentativa. O sistema operacional solta a trava sozinho quando a janela dona fecha ou o programa cai (`kill -9`): não existe trava "velha". Se o `.lock` não puder ser criado (pendrive protegido), o programa segue sem ele (no Windows ainda vale o mutex da sessão). Resta apenas a conferência da assinatura do arquivo imediatamente antes de gravar, como segunda barreira.
- **Contador anti-reversão.** Cada gravação guarda, **dentro dos dados cifrados**, um contador crescente (`seq`). Ao abrir, o programa compara o contador do `cofre.dat` com o das cópias `.bak1`–`.bak5` (usa a chave já aberta, sem custo de senha). Cópia **mais nova** que o arquivo principal = o principal voltou no tempo: aparece aviso e faixa vermelha ("possível reversão"). Se você restaurou uma cópia mais velha de propósito, é normal; o aviso some na abertura seguinte. **Limite honesto:** se o atacante trocar o `cofre.dat` **e** todas as cópias por um conjunto antigo, nada acusa (não há onde guardar um contador fora do pendrive sem deixar rastro no computador).
- **Pendrive protegido contra gravação (chave física, política de segurança do computador ou somente leitura): MODO CONSULTA.** Ao desbloquear, se o programa vê que não pode gravar, oferece abrir **somente para leitura**: você vê e copia as senhas, aparece a faixa amarela "MODO CONSULTA" e as ações que alteram dados (novo/editar/apagar, trocar senha, importar, pessoas, FIDO, bloqueio) só explicam e voltam. Nada é gravado (nem tentativa, nem log, nem cópia), então a autodestruição não age nesse modo: ele só aparece depois de o programa confirmar que a gravação é impossível. Cofre de formato muito antigo (v1) precisa ser gravado uma vez e não abre assim.
- **Desgaste do pendrive:** a gravação normal escreve só o arquivo temporário e o troca (poucos KB); a cópia de segurança `.bakN` é renovada no máximo **1 vez a cada 10 minutos** (e sempre guarda o estado **anterior** à sessão), e renomear as gerações não grava dados. Nada é reescrito a cada pequeno clique.
- **Erros de gravação, falta de memória e erros de leitura.** Nenhuma tentativa é gasta. Antes de cada derivação o programa confere a **memória física livre** (Argon2 + 25% de folga): se faltar, avisa na hora, sem gastar tentativa e sem deixar o Windows paginar em disco.
- **Um bit danificado no nome do formato** (`COFRE05` virando `COFRE01`): os campos do cofre atual parecem um cofre v1 válido, e um byte qualquer viraria o contador. Por isso o caminho do formato v1 **nunca destrói** o arquivo: devolve a tentativa e orienta a restaurar a cópia. (Defeito encontrado por um teste intermitente; o teste `teste_queda_e_memoria.py` seção 4 o reproduz.)

**Atenção:** a autodestruição também é um risco para você: quem tiver o programa e o arquivo e errar a senha o número de vezes escolhido (ou um erro de digitação seu) apaga o cofre e as cópias. Tenha sempre um backup seu fora do pendrive. O alerta de "tentativas erradas desde a última abertura" é um aviso de melhor esforço (o contador fica em texto claro): ele nunca prova que ninguém tentou.

**Cópias de segurança automáticas:** **5 gerações rotativas** (`cofre.dat.bak1` = a mais nova, até `.bak5` = a mais antiga), ao lado do cofre. Nascem junto com o cofre e uma nova geração é criada, no máximo, a cada 10 minutos de uso (e só se o conteúdo mudou); as anteriores são empurradas por renomeação, que é atômica. Se a mais nova estiver ilegível, a restauração usa a seguinte. Estão criptografadas como o próprio cofre. Trocar a senha ou gerar nova chave de acesso **apaga essas cópias** (elas ainda abririam com a senha antiga). Elas **não substituem** um backup seu em outro lugar. Itens excluídos continuam existindo, criptografados, nas cópias e em backups antigos até serem substituídos; em SSD e pendrive, sobrescrever não garante apagar de verdade.

**Gravação segura no pendrive:** todo arquivo gravado pelo cofre (cofre, cópias, backup) vai primeiro para um `.tmp` na mesma pasta, é forçado ao disco (`fsync`), **relido e conferido por SHA-256** e só então trocado pelo definitivo (`os.replace`, atômico; no Windows tenta de novo por alguns segundos se o antivírus estiver segurando o arquivo). Se o pendrive sair, ficar cheio, protegido ou der erro no meio, o cofre anterior continua intacto, o `.tmp` é apagado e aparece uma mensagem clara (sem caminho de arquivo). Se o arquivo do cofre **sumir** com o cofre aberto (pendrive removido ou trocado), o programa se recusa a gravar, em vez de criar um cofre novo em outro pendrive. Dentro dos dados cifrados há ainda um **manifesto** (quantidade de itens e SHA-256 dos IDs): se não conferir, o cofre recusa abrir em vez de carregar um estado parcial.

**Registro de diagnóstico (cifrado):** falhas do sistema (gravação, leitura, integridade, erro inesperado) viram **registros de 77 bytes com números** (código do evento, `errno`, linha do programa, versão, minuto), sem texto, caminho, hash ou memória, no arquivo `cofre.dat.diag`. Cada registro é selado com a chave pública do cofre (X25519 + ChaCha20-Poly1305), então dá para registrar até com o cofre trancado; a chave privada fica **dentro do cofre** e só ele, aberto, lê (menu ⋯ › **Diagnóstico**). Guarda no máximo 200 registros (mantém os 100 mais recentes ao rodar) e some junto na autodestruição. Registro adulterado é descartado e contado.

Erros que **não** gastam tentativa:

- chave de acesso mal digitada (formato inválido);
- falta de um dos fatores no modo E;
- chave FIDO cancelada ou ausente.

### 2.4 Por que a força bruta não funciona

- **Pelo programa:** o cofre se apaga depois de 1 a 10 tentativas.
- **Com uma cópia do arquivo:**
  - quem protege é o **Argon2id**. Cada tentativa exige 1 GiB de memória, o que inviabiliza testar bilhões de senhas, mesmo com muitas GPUs;
  - no **modo E**, o atacante também precisa adivinhar a chave de acesso de **160 bits**. Isso dá 2¹⁶⁰ ≈ 10⁴⁸ combinações, muito mais que a idade do universo em qualquer computador existente ou previsível;
  - com **FIDO**, ele precisa ainda do chip físico.
- **Ataques com IA:** não existe atalho. Uma IA não "adivinha" AES-256 nem ChaCha20, e só poderia ajudar a chutar senhas fracas. Por isso o cofre recusa senhas fracas e recomenda frases longas.

---

## 3. Proteções do Windows

| Proteção | O que faz |
|---|---|
| **Invisível a prints e gravações** | A janela aparece **preta** em capturas de tela, gravações, Teams, Discord, AnyDesk e programas espiões que filmam a tela (exige Windows 10 versão 2004 ou mais novo) |
| **Teclado virtual embaralhado** | Botão ⌨ ao lado de cada campo de senha. Você digita com o mouse e as teclas **mudam de lugar a cada clique**: keyloggers não capturam e a posição dos cliques não revela nada |
| **Bloqueio de cópia nos campos** | Ctrl+C, recortar, arrastar e o menu do botão direito ficam desligados nos campos de senha |
| **Área de transferência protegida** | Fora do Win+V e da nuvem, ignorada por monitores e limpa em 15 s |
| **Bloqueia ao sair do programa** | Se outro programa ficar em primeiro plano por **60 s** (navegador, por exemplo), o cofre bloqueia e apaga as chaves da memória (`BLOQUEIO_SEM_FOCO_S`). Voltar antes disso zera a contagem. |
| **Bloqueia junto com o Windows** | Win+L, troca de usuário, suspensão e hibernação **fecham o cofre e descartam as chaves** (o programa recebe o aviso do Windows **antes** de dormir). Atenção: o Python **não zera** todas as cópias de textos e chaves na RAM, então bytes podem sobrar e ir para o `hiberfil.sys`/`pagefile.sys` no C:. Para cobrir isso, use BitLocker no C:, `powercfg /h off` (sem hibernação) e limpar o arquivo de paginação ao desligar |
| **Bloqueio por inatividade** | 3 minutos sem uso por padrão; você escolhe de 1 a 30 minutos em ⋯ › **Bloqueio automático** (a escolha fica dentro do cofre, cifrada). Ao perder o foco, o conteúdo é coberto na hora |
| **Bloqueio ao minimizar** | Minimizou, trancou |
| **Esconde ao perder o foco** | Ao trocar de janela, o conteúdo do cofre é coberto ("Conteúdo oculto") até você voltar |
| **Senhas reveladas por pouco tempo** | "Mostrar" no painel esconde de novo em 20 s. O olho nos campos esconde em 30 s |
| **Memória trancada** | As regras de acesso do processo passam a negar a outros programas ler, escrever ou injetar código no cofre (o SYSTEM e administradores com privilégio de depuração ainda conseguem contornar: é uma camada de defesa, não uma barreira absoluta) |
| **Anti-injeção** | Bloqueia DLLs de ganchos globais, AppInit e LSPs (`ExtensionPointDisable`) |
| **DLLs só confiáveis** | Nunca carrega DLL de rede ou de baixa integridade, prefere as do System32 e ignora a pasta atual (contra DLL falsa) |
| **Só fontes do sistema** | Fecha uma porta clássica de ataque, as falhas em arquivos de fonte |
| **Caixas de erro do Windows** | `SetErrorMode` suprime algumas caixas de diálogo do processo, mas não garante que o Windows deixe de gerar relatórios ou dumps de falha; BitLocker e as políticas do Windows continuam importantes |
| **Detector de ferramentas espiãs** | Se um leitor de memória ou depurador conhecido (x64dbg, Cheat Engine, Process Hacker, ProcDump, WinPmem…) estiver aberto, o cofre **não abre**. Se ele aparecer com o cofre aberto, o cofre **bloqueia na hora**. Nada é apagado |
| **Aviso de acesso remoto** | Área de Trabalho Remota, AnyDesk, TeamViewer, RustDesk e similares disparam um aviso antes de abrir |
| **Chave FIDO durante o toque** | A trava de memória é afrouxada só nos segundos do toque (a janela do Windows precisa conversar com o cofre) e volta logo depois |

Cada proteção é independente. Se alguma versão do Windows recusar uma delas, ela é pulada e o cofre continua funcionando. A tela de desbloqueio mostra quais ficaram ativas.

---

## 4. Limites: o que nenhum cofre consegue impedir

Transparência faz parte da segurança. Estes limites valem para **qualquer** gerenciador de senhas, inclusive 1Password, Bitwarden e KeePass:

- **Malware com permissão de administrador ou rootkit de núcleo**, **com o cofre aberto**, tem mais poder que o próprio cofre. Ele pode ler a memória ou capturar o teclado. Com o cofre **fechado**, o arquivo continua ilegível.
  - Defesa: antivírus atualizado, **Integridade da memória** do Windows ligada, **chave FIDO** (uma senha capturada sozinha não abre o cofre) e o **teclado virtual** para digitar a senha mestra.
- **Perder a senha E a chave de acesso** no modo OU, ou **qualquer uma das duas** no modo E, significa **perder o cofre para sempre**. Não existe "esqueci minha senha": é isso que garante que ninguém mais consiga abrir.
- **Quem pegar o pendrive por alguns minutos** pode trocar o `CofreSenhas.exe` (ou soltar uma DLL ao lado dele) por uma versão que registra a senha. A criptografia não protege contra isso. O programa é o ÚNICO arquivo na pasta (nada de `.bat`/`.sha256` ao lado que pudesse ser trocado junto): o que protege é **BitLocker To Go no pendrive inteiro (programa e cofre) — trate como obrigatório** e o SHA-256 do `.exe` anotado em papel e conferido (menu ⋯ → Verificar integridade do programa, dentro do próprio cofre). **O elo mais fraco é o computador onde você pluga o pendrive**: num PC comprometido, nenhuma defesa de software vence. Veja o `MODELO_DE_AMEACAS.md`.
- **Backups antigos** continuam abrindo com a senha e a chave que valiam quando foram feitos.
- **A autodestruição não é garantida em SSD e pendrive**: o nivelamento de desgaste pode manter blocos antigos fora do alcance do programa. Por isso a proteção real é a senha forte com Argon2id e o BitLocker no pendrive.
- **Uma cópia do arquivo** permite tentativas fora do programa, sem a autodestruição, e o mesmo vale para quem restaura o byte do contador. Nesse cenário, quem protege é o Argon2id, uma senha forte e a chave de 160 bits. A autodestruição barra tentativas **pelo programa**; a matemática barra todo o resto.
- **Senha longa demais:** a senha mestra aceita no máximo **1024 caracteres** (`MAX_SENHA`); acima disso o programa recusa com mensagem clara, **sem gastar tentativa**, e a estimativa de força olha só os primeiros 256 caracteres (texto gigante não esgota CPU nem memória).
- **Campos de texto:** todo campo (`Entry`) é **apagado antes de ser destruído**, ao fechar telas e janelas de diálogo (exceto os ligados a uma variável do programa), e o Python faz coleta de lixo a cada 2 minutos com o cofre aberto, junto da varredura de memória livre. O Tcl/Tk ainda pode manter cópias próprias do que foi digitado: é um limite do Tkinter.
- **Hibernação ligada:** na tela de senha aparece um aviso amarelo se o Windows estiver com a hibernação ligada (lê o registro, sem administrador), porque ao hibernar o Windows grava a RAM inteira em `hiberfil.sys`. O programa já bloqueia o cofre ao detectar a hibernação, mas o ideal é `powercfg /h off` (como administrador) e BitLocker no disco C:. O `pagefile.sys` não tem como ser consultado nem controlado sem administrador: continua valendo o BitLocker no C:.
- **Pendrive FAT32/exFAT:** ao abrir o programa, se o volume não guarda permissões de arquivo, aparece um **alerta que para a tela até você confirmar** (e uma linha vermelha na tela de senha) dizendo que o BitLocker To Go é obrigatório. O programa não consegue saber se o BitLocker está ligado sem direitos de administrador, então por padrão não recusa abrir. **Opcional:** para o cofre RECUSAR abrir em FAT/exFAT, crie um arquivo vazio chamado `exigir_ntfs.txt` ao lado do `.exe` (ou defina `COFRE_EXIGIR_NTFS=1`); para desfazer, apague o arquivo.
- **Rastros no computador:** ao abrir, as pastas temporárias do programa (`TEMP`/`TMP`) passam para `.tmp_cofre`, ao lado do `.exe`, e essa pasta é apagada ao sair. O programa **não** varre nem apaga nada no perfil do computador (poderia destruir arquivos de outros programas).
- **Memória (melhor esforço, medido):** o Python não oferece apagar textos, então o cofre faz o que dá: ao bloquear, **sobrescreve com zeros** (via `ctypes`, só CPython) as chaves e os textos ASCII dos itens, a senha digitada e as cópias do JSON em claro, e depois **sobrescreve os blocos de memória livre** do Python com zeros. O teste `teste_memoria.py` procura palavras-isca (senha e PIN de um item) na RAM do processo com o cofre aberto (cerca de 11 cópias) e depois de bloquear (0 além do piso do sistema). **Limites:** textos com acento/não-ASCII não são apagados individualmente (só pela varredura de memória livre); o Tcl/Tk guarda cópias do que é digitado nos campos, fora do alcance do Python; e o Windows ainda pode ter gravado a RAM no `pagefile.sys`/`hiberfil.sys` antes. Continue usando BitLocker no C:, sem hibernação.
- As proteções do Windows (captura de tela, trava de memória, mitigação de processo) foram escritas para o Windows 10/11 de 64 bits. Algumas exigem versões mínimas do Windows.

---

## 5. Instalação

### 5.1 Requisitos

- **Windows 10 (versão 2004 ou mais nova) ou Windows 11 x64.** Em Windows 11 ARM64, o instalador usa Python e executável x64 sob emulação; build nativo ARM64 não é suportado porque não há wheel Windows ARM64 corrigido de `cryptography`.
- **Python 3.11, 3.12 ou 3.13 x64.** O instalador baixa e instala sozinho, se faltar (3.13.17, com SHA-256 e assinatura da Python Software Foundation conferidos).
- Para FIDO: Windows 10 1903+ e uma chave FIDO2 com **hmac-secret/PRF** e **PIN configurado** (ex.: YubiKey 5, Feitian ePass FIDO2).

### 5.2 Instalação automática (recomendada)

Dê dois cliques em **`1 - INSTALAR O COFRE - compila e instala.bat`** (é o único instalador — veja a nota abaixo), ou rode no PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\instalar_cofre.ps1
```

**Se o Windows bloquear scripts** (erro vermelho "a execução de scripts foi desabilitada neste sistema", comum em PCs de empresa): use o `1 - INSTALAR O COFRE - compila e instala.bat`, que já chama o PowerShell com `-ExecutionPolicy Bypass` **só para aquela execução**, sem mudar a política do computador, ou rode o comando acima. Se uma política de grupo (GPO) impedir até isso, o PC não permite scripts: instale em outro computador.

O instalador **pergunta primeiro, antes de fazer qualquer coisa**, qual é o seu uso: **(1) PORTÁTIL** no pendrive ou **(2) NO COMPUTADOR** (SSD/HD, pasta trancada pelas permissões do Windows, veja 5.5). Ele **pergunta onde instalar**: **(1) pendrive** (recomendado, ideal com BitLocker To Go) ou **(2) só neste PC** (pasta que você escolher, nunca dentro de Downloads/C:\CofreBuild). No modo pendrive, a compilação, os temporários, o programa e o cofre ficam no pendrive; no modo PC, ficam na pasta escolhida. **Pensado para poucos cliques:** fora a letra do pendrive (modo 1) e a pasta (modo 2), basta ENTER para aceitar o padrão recomendado em cada pergunta; no modo PC, a pasta e a confirmação de instalar nela foram unidas numa única pergunta (ENTER aceita a pasta padrão e já confirma). A única etapa que **nunca** aceita ENTER nem atalho é a conferência manual dos 16 caracteres do SHA-256 do `cofre_senhas.py` (passo 1 abaixo): é a defesa central contra um arquivo trocado, então continua exigindo que você digite, de propósito. A tela do instalador também foi reorganizada em blocos separados (linhas divisórias, títulos e espaçamento) para ficar mais fácil de acompanhar. Ele faz 5 etapas e explica cada uma na tela:

> **Um único instalador para tudo:** `1 - INSTALAR O COFRE - compila e instala.bat` serve tanto para o modo pendrive quanto para o modo "no computador" (5.5) — é a mesma pergunta 1/2 da etapa 0 acima. Versões antigas deste projeto tinham `instalar_cofre.bat`/`instalar_cofre_H.bat` como atalhos extras; foram removidos por serem redundantes (o próprio instalador já detecta o pendrive sozinho, preferindo o H: quando existe).

0. **Pergunta a letra do pendrive** (sugere o H:). O disco do Windows é recusado, e um pendrive com BitLocker trancado é avisado. Se o pendrive estiver em **FAT32 ou exFAT** (sem permissões de arquivo/ACL), aparece um **alerta vermelho** recomendando NTFS e BitLocker To Go (não bloqueia: o `cofre.dat` continua cifrado). Um SSD portátil (que o Windows trata como disco fixo) só é aceito se você digitar `SIM`.

1. **Confere o `cofre_senhas.py`.** Usa **somente** o arquivo ao lado do instalador (nada de procurar em outras pastas), mostra o **SHA-256** dele e **exige** que você digite os 16 primeiros caracteres (sem isso, cancela). Copia o arquivo para uma pasta de compilação que só contém ele marca a cópia como **somente leitura** e **recalcula o hash** três vezes (logo após a cópia, antes dos testes e imediatamente antes de chamar o compilador): se mudou, aborta.
2. **Verifica o Python** e o instala se faltar, pelo winget ou pelo instalador oficial assinado do python.org. O build usa Python x64 em todas as máquinas. Em Windows 11 ARM64, o x64 roda por emulação; não há build nativo ARM64 porque o wheel ARM64 corrigido de `cryptography` não está disponível. O programa sai sempre com o mesmo nome, **`CofreSenhas.exe`**.
3. **Instala as bibliotecas** em **versões fixas e com hash** (`pip --require-hashes`): `cryptography`, `argon2-cffi`, `openpyxl`, `defusedxml`, `fido2`, o compilador `nuitka` 4.3.5 e o compilador C `ziglang` 0.16.0 (também fixo e com hash; o Nuitka usa o Zig que está no PATH e não baixa outro). Qualquer arquivo diferente do esperado é recusado. O Nuitka só existe como código-fonte no PyPI: o hash do arquivo é conferido. Tudo é instalado num **ambiente virtual novo dentro do pendrive** (`_cb\venv`): o seu Python do sistema não é alterado. As ferramentas de montagem do Nuitka (`setuptools` e `wheel`) também vêm com versão e hash, e o Nuitka é instalado com `--no-build-isolation`. Variáveis `PYTHON*`, `PIP_*`, `NUITKA_*`, `CC` e semelhantes do seu ambiente são limpas antes, o `pip` roda com `--isolated` e o teste e a compilação usam `python -I`. A opção `--assume-yes-for-downloads` **não** é usada: se o Nuitka tentar baixar algo, a compilação falha e mostra o que era.
4. **Testa a criptografia**: cria, abre e destrói um cofre de teste neste computador.
5. **Compila para código nativo** com o Nuitka, gerando um único `CofreSenhas.exe`.
   - A 1ª compilação leva de 5 a 20 minutos; as seguintes são bem mais rápidas e **uma falha não recomeça do zero**. A pasta `_cb` (ambiente virtual, `zig.exe`, módulos, cópia do fonte) é apagada por inteiro e refeita a cada vez, então um `.exe`, `zig.exe` ou módulo Python plantado ali nunca entra na compilação.
   - **Cache que sobrevive (`<pendrive>:\_cb_cache`, oculta):** `pip\` (downloads, sempre re-conferidos por hash com `--require-hashes`), `zig\` e `nk\` (caches do compilador, endereçados pelo conteúdo) e `obra\` (o que o Nuitka já compilou). Se Nuitka, Zig, Python ou as opções mudaram desde a última vez (`obra.chave`), a compilação recomeça limpa. Para liberar espaço, apague a pasta `_cb_cache` quando quiser; ela só custa tempo na próxima instalação.
   - **Retentativas automáticas:** cada `pip install` tenta até 3 vezes (com 5 repetições de rede cada) e o download do Python também; o Nuitka tenta até 3 vezes: a 2ª **continua de onde parou** com metade dos processos (comum quando faltou memória), a 3ª recomeça do zero. O `.exe` de uma compilação anterior é apagado antes de cada tentativa, então um `.exe` velho nunca é entregue como se fosse novo.
   - **Em qualquer saída** (sucesso, erro ou Ctrl+C) um `try/finally` apaga a pasta `_cb` (a `_cb_cache` fica) e **restaura o console** (QuickEdit volta ao que era) e guarda o log em `<destino>\logs\instalacao-AAAAMMDD-HHMMSS.log` (em caso de falha, também a saída do compilador). Além disso, acrescenta um **resumo estruturado** em `<destino>\instalacao_detalhada.log` (resultado, versão e hash curto do cofre, plataforma, versão do Windows e do PowerShell, sistema de arquivos, espaço livre, assinatura, tempo de cada etapa e a última mensagem de erro **sem caminhos nem nome de usuário**; guarda só o final quando passa de ~300 KB).
   - **Antes de compilar** confere espaço livre (mais de 3 GB; senão, para; se o Windows não informar, mede pela própria unidade), memória livre (avisa se < 2 GB) e mede a velocidade de escrita do pendrive (avisa se < 15 MB/s, sinal de USB 2.0 ou pendrive lento).
   - **Contra "travamento"**: o QuickEdit do console é desligado (um clique na janela pausava toda a saída até ENTER); a compilação roda com `Start-Process -PassThru` e, **a cada 15 s**, mostra `[vivo]` com o tempo, o CPU do compilador e dos processos filhos, e as últimas linhas da saída. Se ficar 10 minutos sem nenhuma atividade, avisa em vermelho que travou de verdade (a etapa final "Onefile Payload" costuma ficar muda alguns minutos: o aviso amarelo só diz isso). O `winget` e o instalador do Python têm tempo limite (5 e 10 min), porque um pedido de permissão (UAC) escondido atrás da janela parece trava.
   - **Assinatura digital (opcional, desligada)**: com a variável de ambiente `COFRE_ASSINAR_SHA1` (impressão digital de 40 caracteres de um certificado de assinatura de código do seu repositório) e o `signtool.exe` do Windows SDK instalado, o instalador assina o programa **antes** de calcular o `.sha256`. `COFRE_ASSINAR_TS` (https) liga o carimbo de tempo; sem ele nada é enviado pela internet. O programa sem assinatura fica em `_cb_cache\sem_assinatura` e volta sozinho se a assinatura falhar. Certificado autoassinado **não** remove o alerta do SmartScreen/Defender. O fluxo opcional de assinatura não foi validado em Windows real.
   - **Aviso "Editor desconhecido" (SmartScreen) na primeira vez que você abre o `.exe`:** é esperado. O programa é compilado por **você**, no seu computador, e não tem assinatura digital paga; o Windows só avisa porque nunca viu esse arquivo antes, e **não** porque encontrou algo errado. Clique em **Mais informações → Executar assim mesmo**. Antes, se quiser ter certeza de que o arquivo é o que o instalador gerou, confira o SHA-256 do papel em **⋯ → Verificar integridade do programa**. Se o Windows ou o antivírus **bloquear** de vez (sem a opção "Executar assim mesmo"), não adicione exceção: reinstale e confira o número.
   - **Tempos**: no fim (ou na falha) aparece uma tabela com o tempo de cada etapa, para medir onde o tempo realmente vai.
   - **Velocidade da compilação**: `--onefile-no-compression` (sem a etapa longa de compactação; o `.exe` fica maior mas abre mais rápido, pois não descompacta), `--lto=no`, `--python-flag=no_docstrings` e `--jobs` escolhido pela memória livre. O `.exe` recebe **ícone próprio e dados de arquivo** (nome do produto, versão = `VERSAO_PROGRAMA`), o que também ajuda contra falso positivo de antivírus.
   - **Por que a compilação fica no pendrive e não em `%LOCALAPPDATA%`** (NTFS do C: seria mais rápido e teria permissões de arquivo): a regra deste projeto é que **nada do cofre fica no disco do Windows**, nem restos de compilação. A segurança do pendrive vem do BitLocker e da conferência do SHA-256 (três vezes) e do ambiente isolado. Se você preferir velocidade, essa é uma decisão sua: mude a variável `$base` no instalador e atualize esta seção.
   - O Nuitka instalado recebe um ajuste: a criação do script de depuração (`scons-debug.bat`) é desligada, porque antivírus como o Avast bloqueiam `.bat` e quebram a compilação. A versão e o resultado do ajuste aparecem no log.

No fim, o instalador:

- deixa o programa em **`<destino>\CofreSenhas.exe`** (na raiz do pendrive no modo portátil; no local escolhido no modo computador). Se encontrar uma instalação antiga em `<destino>\CofreSenhas`, oferece atualizar ali mesmo, instalar na raiz mantendo a pasta antiga intacta ou apagar **somente** os arquivos antigos do programa depois de digitar `APAGAR`. O cofre, as cópias e as chaves nunca são removidos por essa opção. Nenhum `.bat` nem `.sha256` fica ao lado da nova versão;
- mostra o **SHA-256** do `.exe` (anote-o em PAPEL — é a única cópia confiável deste número; o programa não grava mais esse valor em nenhum arquivo ao lado dele). Para conferir depois, abra o cofre e use o menu **⋯ → Verificar integridade do programa**, e compare à mão com o que você anotou;
- apaga restos de instalações antigas no disco do Windows (`C:\CofreBuild` e a cópia da Área de Trabalho, se não houver cofre nela).

Ao abrir, o programa se descompacta numa pasta temporária **ao lado dele no pendrive** (`CofreSenhas_em_uso_...`), que é apagada sozinha ao fechar. Nada vai para a pasta temporária do Windows.

> **Antivírus:** programas compilados novos às vezes são confundidos com ameaças. Se o Avast ou outro antivírus bloquear, prefira enviar o arquivo como falso positivo ao fabricante ou liberar **só o `CofreSenhas.exe`**. Evite liberar pastas inteiras: qualquer programa colocado nelas passaria sem verificação.

### 5.3 Rodar direto do código (desenvolvimento)

```powershell
pip install -r requirements.txt
python cofre_senhas.py                      # cofre.dat ao lado do programa
python cofre_senhas.py E:\pasta\cofre.dat   # outro local
```

Para o cofre de verdade (ou para distribuir), use sempre `1 - INSTALAR O COFRE - compila e instala.bat` — ele confere hashes, usa ambiente isolado e testa a criptografia antes de compilar; os comandos acima são só para rodar/depurar o código-fonte direto, sem compilar.

### 5.5 Instalação no computador (modo 2) e pacotes offline

- **Pasta com permissões reais (ACL NTFS):** no modo *No computador* o instalador remove a herança de permissões da pasta e deixa **só a sua conta e o SISTEMA** com acesso (`icacls /inheritance:r`). Outras contas do mesmo Windows não leem nem alteram. Isto é **controle de acesso do sistema operacional**, bem melhor do que esconder arquivos. **Limite:** administradores e programas rodando como você continuam alcançando a pasta; em FAT32/exFAT (pendrive) não existe ACL.
- **Sem atalhos:** o instalador **não cria** ícone, atalho nem item no Menu Iniciar. Dê dois cliques direto no `CofreSenhas.exe` (é o único arquivo do programa na pasta) ou digite o caminho no Win+R/terminal.
- **Arquivo de dados:** continua `cofre.dat` (nome neutro configurável não foi implementado; o conteúdo é só ruído cifrado). Os arquivos de apoio ficam ocultos/protegidos (5.4).
- **Chave de acesso fora do computador:** salve o `.key` num pendrive separado (ou YubiKey/FIDO): a pasta do computador não guarda o segundo fator.
- **Iniciar a compilação:** dê dois cliques em **`1 - INSTALAR O COFRE - compila e instala.bat`** (aceita a letra do pendrive: `1 - INSTALAR O COFRE - compila e instala.bat H`). Ele confere a pasta, avisa *Modo OFFLINE/ONLINE* pelos `pacotes\`, mostra o SHA-256 do `cofre_senhas.py`, grava o registro em `logs_compilacao\compilar-AAAAMMDD-HHMMSS.log` e chama o instalador, que pergunta **portátil × no computador** antes de tudo. Os testes Pester das funções auxiliares passaram 12/12 em Windows real em 2026-11-20; a compilação e instalação completas ainda não foram validadas ponta a ponta.
- **Pacotes offline:** rode `3 - BAIXAR PACOTES - so para instalar sem internet.bat` com internet uma vez. Ele prepara `pacotes\` com as bibliotecas, Nuitka, Zig, instalador do Python 3.13, ferramentas travadas por `requirements-test-direct.in`/`requirements-test-lock.txt`, Pester e instalador do Nmap; atualiza `SHA256.txt` e verifica hashes/assinaturas conhecidos. Copie a pasta inteira do projeto para o computador offline. O instalador usa o Python empacotado se nenhum compatível estiver instalado; para executar testes, instale o Python de `pacotes\` se necessário. Os binários não são versionados pelo Git, então uma clonagem nova precisa receber a pasta `pacotes\` preparada.
- **Por que a compilação demora:** não é o PowerShell. O tempo vai para a compilação em C do Nuitka e para a escrita lenta do pendrive (FAT32). As opções já estão otimizadas (sem compressão, `--lto=no`, `--jobs` pela memória). Um instalador em `.exe` não aceleraria a compilação e esconderia o que roda; por isso o instalador continua legível em PowerShell.

### 5.4 Onde ficam os dados

- O cofre é o arquivo **`cofre.dat`, na mesma pasta do programa** (no pendrive).
- Se o cofre estiver no disco do Windows, a tela de desbloqueio avisa. Salvar backup, modelo de planilha ou a chave de acesso no disco do Windows pede confirmação. Salvar a chave no mesmo pendrive do cofre também.
- Para usar num pendrive, deixe `CofreSenhas.exe` e `cofre.dat` juntos nele.
- **BitLocker To Go no pendrive é obrigatório** (em FAT32/exFAT, sem permissões de arquivo, mais ainda): sem ele quem pegar o pendrive troca o `.exe` direto (ele é o único arquivo do programa na pasta). O instalador mostra alerta vermelho nesse caso.
- O arquivo é **portátil**: copiar para outro PC com o programa funciona normalmente. A segurança vem da senha e da chave, não do computador.
- **Arquivos escondidos e protegidos:** depois da instalação a pasta só mostra o **`CofreSenhas.exe`** (não há mais nenhum `.bat`/`.sha256` ao lado dele — nada "de fora" para mexer ou copiar). O `cofre.dat`, as cópias (`.bak1`–`.bak5`), `.diag`, `.lock`, `logs` e `avisos_vistos.json` ficam com os atributos **Oculto + Sistema + Somente leitura**; o próprio `.exe` nunca recebe esses atributos, para continuar sempre visível e abrível, como qualquer programa instalado. Ao **abrir** o cofre o programa libera esses atributos (precisa gravar); ao **fechar** (e ao fim da instalação) volta a escondê-los. Se o programa cair, os arquivos ficam visíveis (falha segura). Só vale para o programa compilado no Windows; rodando o `.py` solto nada é escondido. **Limite honesto:** é discrição e proteção contra edição *acidental*, não controle de acesso: quem ligar "mostrar arquivos ocultos" ainda os vê (em FAT32/exFAT não existe permissão de arquivo). A proteção real do conteúdo é a cifra do cofre e o BitLocker do pendrive.
- Ao lado do cofre aparece **`cofre.dat.lock`**: um arquivo **vazio** que serve de trava entre janelas (veja 2.3). Pode ficar lá; apagá-lo com o cofre fechado não causa nada.

---

## 6. Primeiros passos

1. **Crie o cofre.**
   - Recomendado: modo **Senha E chave de acesso** e blindagem **Máxima**.
   - Use **Gerar…** para criar uma frase de 5 ou 6 palavras e acompanhe a análise de força ao lado.
2. **Guarde a chave de acesso.**
   - Salve o `.key` em **outro** pendrive, longe do cofre.
   - **Anote à mão** em papel (a chave não é impressa).
   - Ela aparece uma única vez.
3. **(Opcional) Cadastre a chave FIDO** pelo botão **Chave FIDO**: toque 3 vezes e digite o PIN da chave quando o Windows pedir. **Anote à mão o código de recuperação** (ele não é impresso) e cadastre também uma chave reserva.
4. **Importe suas senhas** (menu ⋯ → Importar planilha), confira a prévia e deixe o cofre **apagar a planilha com segurança**.
5. **Rode Verificar senhas** e troque as fracas e as repetidas. Comece pelas de banco e e-mail.
6. **Faça backup** (menu ⋯ → Backup do cofre). O backup continua criptografado. Guarde uma cópia em outro lugar e refaça depois de mudanças importantes.

---

## 7. Atalhos de teclado

| Atalho | Ação |
|---|---|
| `Ctrl+F` | Buscar |
| `Ctrl+N` | Novo item |
| `Ctrl+G` | Gerador de senhas |
| `Ctrl+L` | Bloquear o cofre |
| `Enter` / duplo clique | Editar o item selecionado |
| `Ctrl+C` (na lista) | Copiar a senha do item selecionado |
| `Ctrl+B` (na lista) | Copiar o login do item selecionado |
| `Delete` | Excluir o item (com confirmação) |
| `↑` `↓` `Home` `End` | Navegar pela lista |
| `Esc` (na busca) | Limpar a busca |

---

## 8. Estrutura do projeto

Esta versão usa **uma única pasta** para tudo — o que você instala/usa no dia a dia *e* o repositório
que vai para o GitHub são a mesma pasta (`CofreSenhas-Instalador/`, que no GitHub se chama `cofre-de-senhas/`).
Não existem mais duas pastas separadas.

```
CofreSenhas-Instalador/  (= cofre-de-senhas/ no GitHub)
│
│   --- o que o usuário final realmente precisa (ver 5. e 7.) ---
├── README.md                              # guia único de entrada: uso, dependências, testes e estrutura
├── 1 - INSTALAR O COFRE - compila e instala.bat    # ÚNICO instalador: dois cliques (confere, registra e chama o instalar_cofre.ps1)
├── 2 - TESTAR TUDO - roda todos os testes.bat      # 6 baterias obrigatórias; POS-COMPILACAO inclui a etapa 7 opcional
├── 3 - BAIXAR PACOTES - so para instalar sem internet.bat   # baixa (com hash conferido) as bibliotecas para pacotes\
├── cofre_senhas.py          # o programa inteiro (um arquivo, fácil de auditar e conferir pelo SHA-256)
├── instalar_cofre.ps1       # instalador (pergunta onde instalar, Python, bibliotecas com hash, compilação)
├── requirements.txt         # dependencias de runtime e compilacao
├── requirements-test-direct.in     # dependencias diretas de teste, com versoes exatas
├── requirements-test-lock.txt    # lock gerado, com dependencias transitivas e hashes
├── baixar_pacotes_offline.ps1 # prepara o wheelhouse completo para testes e instalacao
├── .gitignore
├── SECURITY.md              # limites de protecao e relato privado de problemas
├── .github/
│   └── workflows/
│       └── windows-tests.yml  # GitHub Actions (NAO MOVER ESSE ARQUIVO)
│
├── documentacao/            # MANUAL_COMPLETO.md (este), MODELO_DE_AMEACAS.md, HISTORICO_* (relatórios, mudanças e hashes antigos)
├── pacotes/                 # bibliotecas + Nuitka + Zig para instalar sem internet (LEIA-ME.txt + SHA256.txt no git;
│                            #   os arquivos binários em si ficam de fora do repositório, veja .gitignore)
├── logs_de_compilacao/      # um log por compilação feita pelo "1 - INSTALAR O COFRE" (ficam de fora do git)
├── testes/                  # COMO_RODAR_OS_TESTES.md, PLANO_DE_TESTES.md e as pastas:
│                            #   1_TESTE_motor_do_cofre/ (sem tela), 2_TESTE_telas_e_botoes/ (Tk), 3_TESTE_ataques_simulados/ (pentest),
│                            #   4_TESTE_so_no_windows/ (instalador/ACL no Windows real), 5_TESTE_ferramentas_externas/, 6_TESTE_ferramentas_dos_testes/,
│                            #   7_TESTE_de_compilacao/ (opcional, depois de gerar o executável),
│                            #   resultados/ (TUDO que os testes geram: resultado de cada teste, resumo, log de depuração)
└── ferramentas_windows_opcionais/  # scripts OPCIONAIS que cuidam do seu PC (não do cofre): verificar/aplicar/desfazer segurança e procurar rootkit
```

O programa é **um único arquivo** de propósito: é mais fácil de auditar, de compilar e de conferir pelo SHA-256. Ele é organizado em seções:

1. núcleo criptográfico;
2. avaliação de força;
3. impressão;
4. proteções do Windows;
5. classe `Cofre`;
6. importação;
7. FIDO2;
8. tema e desenho de ícones;
9. componentes de interface;
10. classe `App`.

---

## 9. Testes automáticos

```powershell
python testes\6_TESTE_ferramentas_dos_testes\rodar_todos.py            # tudo (núcleo + interface)
python testes\6_TESTE_ferramentas_dos_testes\rodar_todos.py --rapido   # só o núcleo, sem janelas
python testes\6_TESTE_ferramentas_dos_testes\rodar_todos.py --so gui   # só a interface
python testes\6_TESTE_ferramentas_dos_testes\rodar_todos.py --filtro fido
```

**Log de depuração e relatórios (novo):** a cada `2 - TESTAR TUDO - roda todos os testes.bat`, a pasta `testes\resultados\` ganha um `resultado_*.txt` por teste, e ali mesmo ganha o **`log_depuracao.txt`** (ambiente, horário, duração, estado e a **saída completa com tracebacks** de cada teste; recriado do zero a cada rodada). Em `testes\resultados\` ficam também **`resumo_testes.md`** (tabela legível, uma linha por teste), `resumo_testes.json` (para comparar uma rodada com outra) e `resultados.sarif` (só as falhas, formato aceito por ferramentas de revisão). **Cada bateria nova substitui a anterior:** no começo, `limpar_resultados.py` apaga os `resultado_*`, resumos, `.sarif`, logs e cobertura antigos de `testes\resultados\` (e leva documentos que estavam lá para a pasta certa); a pasta só guarda resultados da última rodada. **Respeito ao PC:** os testes rodam em prioridade baixa, esperam haver RAM livre antes de começar algo pesado e fazem uma pausa entre si (a concorrência usa menos processos se a memória estiver curta). No fim, `limpar_artefatos_testes.py` apaga sobras de testes interrompidos em `%TEMP%` (grava `limpeza_artefatos.txt`). Tudo isso é conveniência: se falhar, o resultado das baterias não muda.

No Windows, cada bateria tem sua própria pasta e seu próprio `.bat`, e **todo** resultado (`resultado_*.txt`) vai para a mesma pasta `testes\resultados\`, qualquer que seja a bateria que o gerou:

- Para rodar só a bateria do **núcleo** (os `teste_*.py` de `testes\1_TESTE_motor_do_cofre\`, com o Python do Windows em vez do Linux), dê dois cliques em `testes\1_TESTE_motor_do_cofre\RODAR ESTA PASTA - testes do motor do cofre.bat` e leia `testes\resultados\resultado_nucleo_windows.txt`.
- Para validar o **instalador** e o programa no Windows real (sem a bateria do núcleo, que agora é separada), dê dois cliques em `testes\4_TESTE_so_no_windows\A - testar o instalador.bat` e leia `testes\resultados\resultado_teste_windows.txt`.
- Para confirmar atributos de arquivo, ACL, SMBIOS, DPAPI e as DLLs da System32, dê dois cliques em `testes\4_TESTE_so_no_windows\B - testar atributos e permissoes do Windows.bat` (ou `B - testar atributos e permissoes do Windows.bat H` para testar também o pendrive H:, que grava em `resultado_nativo_windows_H.txt` — cada variante tem seu próprio arquivo, nenhum sobrescreve o outro) e leia `testes\resultados\resultado_nativo_windows.txt`.
- Para rodar a bateria de **interface** (os ~35 `2_TESTE_telas_e_botoes\teste_gui_*.py`), dê dois cliques em `testes\2_TESTE_telas_e_botoes\RODAR ESTA PASTA - testes das telas e botoes.bat` e leia `testes\resultados\resultado_teste_gui_windows.txt` que ele cria (cada janela abre e fecha sozinha por alguns segundos; é automático, não precisa clicar em nada).
- Para rodar a bateria de **pentest** (injeção, força bruta/spraying, DoS, vazamento de memória, engenharia reversa, fuzzing adversarial, SAST, dependências, canal lateral de tempo, exfiltração pela rede, link simbólico — veja `testes\3_TESTE_ataques_simulados\` e o relatório `testes\resultados\relatorio_pentest.md`), dê dois cliques em `testes\3_TESTE_ataques_simulados\RODAR ESTA PASTA - testes de ataque simulado.bat` e leia `testes\resultados\resultado_pentest_windows.txt`.

Para rodar as **seis baterias obrigatórias de uma vez só** (sem precisar abrir cada `.bat` manualmente), dê dois cliques em `testes\6_TESTE_ferramentas_dos_testes\rodar_todos_windows.bat` (ou `rodar_todos_windows.bat H` para incluir o pendrive H: no teste nativo) — ele chama núcleo, instalador, teste nativo, interface, pentest e ferramentas externas, nessa ordem. A pasta opcional `7_TESTE_de_compilacao` verifica as proteções PE do executável, a varredura do Windows Defender e as conexões do processo. **Compile o CofreSenhas.exe primeiro** e passe `POS-COMPILACAO` ao Testar Tudo para incluir essa etapa; sem executável ou sem processo aberto, a verificação correspondente será `[PULADO]`. Os resultados ficam diretamente em `testes\resultados\`, sem subpastas por rodada; o arquivo conjunto é `resultado_rodar_todos_windows.txt` e a pasta 7 também grava `resultado_cofre_compilado_windows.txt`.

Os testes Windows criam ambientes Python **temporários** ao lado dos executores e os instalam somente do wheelhouse local (`--no-index`); a bateria de ferramentas externas mantém um ambiente local dentro de `testes\`. Rode a etapa 3 para preparar os pacotes e instale o Python do projeto se necessário. Os testes rodam em UTF-8 e **sem** o modo `-X dev` (uma sonda separada, dentro de `A - testar o instalador.bat`, mostra se o modo dev do Python do PC trava sozinho, sem o cofre). O `pip-audit` é empacotado, mas sua consulta é pulada offline por depender de dados de vulnerabilidade atuais; Nmap requer instalação manual do pacote local.

Cada teste trabalha numa **pasta temporária** e termina com `TODOS OK`. O código de saída é 0 em caso de sucesso e 1 em caso de falha, o que permite usar os testes em integração contínua.

Os `teste_*.py` do núcleo (sem janela) listados abaixo ficam todos dentro de `testes\1_TESTE_motor_do_cofre\` (junto com `PECA_DE_TESTE_cofre_versao_4_antiga.py`, usado pelo teste de migração); os `2_TESTE_telas_e_botoes/teste_gui_*.py` ficam em `testes\2_TESTE_telas_e_botoes\`.

| Arquivo | O que testa |
|---|---|
| `teste_backup.py` | Cópia de segurança nasce com o cofre e é renovada a cada 10 min; contador zerado ou dados alterados preservam o arquivo, devolvem a tentativa e permitem restaurar; restaurar não gera falso alarme; a autodestruição apaga `.bak1`, `.bak2` e `.danificado`; trocar a senha apaga as cópias; falta de memória do Argon2 devolve a tentativa |
| `teste_severo.py` | Bit-flips em cada byte do cabeçalho e em pontos da seção FIDO e dos dados (nunca destrói nem gasta tentativa), truncamentos, lixo, queda de energia entre `.tmp` e troca, contagem de tentativas, 14 operações aleatórias (incluindo trocar senha e chave) sempre reabrindo igual, senhas com emoji/acento/NUL, 3000 chaves-lixo, planilhas hostis (bidi, zip bomb, colunas gigantes, CSV binário), migração de um `COFRE04` real, NFD→NFC e 40 salvamentos concorrentes |
| `teste_limites.py` | Senha vazia recusada; senhas de 1 caractere a 300 mil, NUL, emoji e NFC/NFD abrem; itens com 3 MB, `None`, fórmulas, RLO e HTML salvam e reabrem; `zerar_objeto` não toca em textos internados, curtos ou não-ASCII nem corrompe objetos vizinhos; 60 ciclos abrir/fechar sem vazamento |
| `teste_memoria.py` | Palavras-isca na RAM com o cofre aberto (~11 cópias) e depois de bloquear (só o piso) |
| `teste_vazamento_memoria.py` | Ciclos abrir/editar/fechar com `tracemalloc` (sem crescimento por volta), teto do cache de força, `_zerar` e Cofre fechado sem referência presa |
| `teste_modo_senha.py`, `teste_quarentena.py` | Modo só-senha; quarentena e saneamento da planilha importada |
| `teste_seguranca_extra.py` | Senha mestra fraca recusada; checagem de vazamentos (só 5 caracteres do SHA-1 saem; contagem; enchimento; cancelar; resposta grande ou status ruim recusados); tempo de bloqueio configurável e seus limites |
| `teste_io_diag.py` | Gravação atômica com releitura SHA-256 (queda no `fsync`, gravação que não confere, pendrive removido/cheio/protegido/em uso com nova tentativa); arquivo do cofre que some; 5 gerações de cópia rotativas; manifesto interno; diagnóstico cifrado (sem texto nem caminho, só legível com a chave do cofre, adulteração e corte detectados, rotação, 8 fios, nunca levanta erro) |
| `teste_queda_e_memoria.py` | `kill -9` no meio de gravações repetidas (o cofre sempre abre e nada confirmado se perde); duas instâncias gravando no mesmo arquivo (conflito detectado e recusado); pouca memória livre recusa sem gastar tentativa; `COFRE01` com contador 1 nunca apaga |
| `teste_fuzz_importacao.py` | CSV/XLSX hostis (bytes nulos, campos de MB, UTF-16 com BOM trocado, UTF-8 inválido, zip bomb, 200 mutações): nunca um erro não tratado |
| `2_TESTE_telas_e_botoes/teste_gui_semfoco.py` | Bloqueio automático após 60 s fora do programa (e a contagem recomeça ao voltar) |
| `4_TESTE_so_no_windows/instalador.Tests.ps1` | Pester: funções auxiliares do instalador (hash digitado, arquitetura, sistema de arquivos, espaço, certificado, log) |
| `teste_checksum_v5.py` | Danos de mídia (setor zerado ou 0xFF, cabeçalho apagado, arquivo cortado, lixo ou zeros no fim, arquivo vazio, setores trocados): o programa recusa abrir, **não gasta tentativa, não apaga nada, deixa o arquivo como estava** e a cópia `.bak1` restaura os itens |
| `teste_modo_consulta.py` | Pendrive protegido (toda escrita bloqueada): a abertura normal falha sem gastar tentativa; o modo consulta abre, lê e não grava nada (arquivo idêntico, nenhum arquivo criado); salvar é recusado e desfeito; senha errada nunca destrói nesse modo |
| `test_pytest.py` | Ponte opcional para o **pytest**: cada `teste_*.py` vira um caso (`pip install pytest`, depois `pytest testes/6_TESTE_ferramentas_dos_testes/test_pytest.py -v`; `-k trava` escolhe um). A interface usa `xvfb-run` no Linux |
| `teste_queda_pontos_exatos.py` | Derruba o processo (`os._exit`) em cada `fsync` e em cada `os.replace` da gravação (antes e depois, rotação das cópias incluída): o cofre e as cópias sempre abrem com tudo que estava confirmado, e a gravação seguinte funciona |
| `teste_fuzz_cabecalho.py` | Troca cada byte do cabeçalho e da seção FIDO (preenchida): sempre `ArquivoCorrompido`/`ArquivoInvalido`, nunca gasta tentativa nem altera o arquivo |
| `teste_host_e_politica.py` | Pasta temporária privada (TEMP/TMP/tempfile apontam para `.tmp_cofre`, some ao sair, resto de queda apagado, atalho e pendrive protegido não mudam nada, nada fora da pasta é tocado) e política opcional "exigir NTFS" (variável de ambiente e arquivo marcador) |
| `teste_senha_longa_e_fs.py` | Senha acima do limite: recusada ao criar/trocar e, ao abrir, sem gastar tentativa (arquivo idêntico); texto de milhões de caracteres avaliado em menos de 2 s; aviso de sistema de arquivos só em FAT/FAT32/exFAT |
| `2_TESTE_telas_e_botoes/teste_gui_fontes.py` | `preparar_fontes` chamada várias vezes (mesma janela e janela nova) sem erro: o primeiro teste no Windows real (Python 3.14) mostrou que a segunda chamada quebrava |
| `2_TESTE_telas_e_botoes/teste_gui_campos.py` | Campos de texto (tk e ttk) são apagados ao fechar a janela; campos com variável ficam intactos |
| `2_TESTE_telas_e_botoes/teste_gui_dados_bancarios.py` | Número da conta / Agência: aparecem ao marcar as caixas, salvam e sobrevivem a fechar/reabrir o cofre (cifrados); item com dado bancário NUNCA libera sem confirmar a senha mestra, mesmo com a proteção extra geral desligada; item comum, sem dado bancário, libera direto nesse caso |
| `teste_trava_instancias.py` | Trava `.lock` entre processos (segundo recebe "em uso"; some com `kill -9`); sem poder criar o `.lock` o programa segue; contador anti-reversão (alerta ao voltar no tempo, nunca em uso normal, some depois); consulta não grava |
| `2_TESTE_telas_e_botoes/teste_gui_em_uso.py` | Segunda janela abre direto em modo consulta com faixa própria, sem perguntar; faixa e aviso de reversão; ações que alteram dados só explicam |
| `2_TESTE_telas_e_botoes/teste_gui_consulta.py` | Tela de senha oferece o modo consulta, faixa de aviso, ações que alteram dados só explicam |
| `teste_estatico.py` | Sintaxe e nomes não definidos (um `NameError` só apareceria na tela, em uso) |
| `2_TESTE_telas_e_botoes/teste_gui_*.py` | Interface: abrir, criar, editar, copiar, pessoas, importação, FIDO, alerta de tentativas, bloqueio, checagem de vazamentos, bloqueio automático, "macaco" (cliques aleatórios) |
| `1_TESTE_motor_do_cofre/RODAR ESTA PASTA - testes do motor do cofre.bat` | No Windows real: só a bateria do núcleo (`rodar_todos.py --so nucleo`), com ambiente Python temporário próprio (mesmas bibliotecas do cofre). Resultado em `resultados\resultado_nucleo_windows.txt` |
| `4_TESTE_so_no_windows/teste_windows.ps1` (+ `.bat`) | No Windows real: arquitetura detectada, sintaxe do instalador, import do programa e Pester do instalador (a bateria do núcleo **não** roda mais aqui: veja `1_TESTE_motor_do_cofre/RODAR ESTA PASTA - testes do motor do cofre.bat`). Resultado em `resultados\resultado_teste_windows.txt` |
| `2_TESTE_telas_e_botoes/teste_gui_windows.ps1` (+ `.bat`) | No Windows real: roda os ~35 testes de interface (`2_TESTE_telas_e_botoes/teste_gui_*.py`) com ambiente Python temporário próprio (mesmas bibliotecas do cofre) e sem `-X dev`; cada janela abre e fecha sozinha. Resultado em `resultados\resultado_teste_gui_windows.txt` |
| `3_TESTE_ataques_simulados/teste_pentest_*.py` (14 arquivos) | Pentest dedicado: injeção de código (SQLi/command/template), SSRF, força bruta e password spraying, DoS/esgotamento de recursos, vazamento de memória (forense de RAM real), bypass de contador/autodestruição, engenharia reversa (segredos no código), fuzzing adversarial e falsificação visual Unicode, SAST com bandit/flake8, dependências com pip-audit, canal lateral de tempo (comparação manual + medida dinâmica), exfiltração de dados pela rede (monitor real de socket), link simbólico na gravação em disco (achado real, corrigido), e documentação explícita do que é fora de escopo (sem rede/AD/mobile). Relatório completo: `testes\resultados\relatorio_pentest.md` |
| `3_TESTE_ataques_simulados/rodar_pentest.py` (+ `RODAR ESTA PASTA - testes de ataque simulado.bat`) | Executa só a bateria de pentest (os 14 `teste_pentest_*.py`). No Windows real, com ambiente Python temporário próprio. Resultado em `resultados\resultado_pentest_windows.txt` |
| `1_TESTE_motor_do_cofre/teste_nucleo_vetores_criptograficos.py` | Vetores e integridade dos primitivos: determinismo/avalanche do Argon2id, separação de domínio das subchaves ChaCha20/AES-256, amarração do AAD no embrulho da chave, adulteração exaustiva (todos os bits de um ciphertext pequeno), nonce participando de fato da cifra |
| `1_TESTE_motor_do_cofre/teste_nucleo_qualidade_aleatoriedade.py` | Qualidade estatística (monobit, qui-quadrado, sem blocos repetidos) do sal/nonce/chave de acesso/PIN/senha gerados pelo próprio programa - canário contra um gerador de números aleatórios fraco por engano |
| `1_TESTE_motor_do_cofre/teste_nucleo_qualidade_codigo.py` | Higiene do código: sem `eval`/`exec`/`pickle`, `subprocess` com `shell=True`, `except:` nu, `print()` de variável sensível ou TODO/FIXME em função crítica; informa (sem falhar) cobertura de docstring e funções mais longas |
| `2_TESTE_telas_e_botoes/teste_gui_acessibilidade_teclado.py` | Operação inteira sem mouse: foco inicial, Tab/Shift+Tab, barra de espaço ativa botão com foco, setas navegam a lista, Esc não derruba o programa |
| `teste_transacao.py` | Falha ao salvar desfaz a operação na memória e no disco |
| `teste_ataques.py` | Nenhum texto (senha, login, PIN, nome da conta, senha mestra, chave) aparece no arquivo; autodestruição na última tentativa, sem resíduos de dados (travas de sincronização podem ficar); a tentativa é gasta **antes** de testar; adulterar dados, nonce, parâmetros do Argon2, máximo de tentativas, modo de desbloqueio ou contador é detectado e o arquivo é **preservado** para restaurar a cópia; trocar a "fechadura" entre cofres falha; arquivos truncados, vazios ou com lixo são recusados; nonces nunca se repetem; senhas fracas recusadas; depurador detectado só no programa compilado; modo dois fatores (só senha, só chave, uma errada); troca de senha e de chave; tamanho fixo por blocos; cascata (tirar a camada AES ainda deixa tudo cifrado); conversão de formato antigo; custo do Argon2id |
| `teste_fido.py` | Primeira chave ativa o FIDO e gera o código de recuperação; sem a chave, pede a chave sem gastar tentativa; chave de outra pessoa recusada; cancelar o toque não gasta tentativa; chave reserva e código de recuperação abrem; código novo invalida o antigo; chave removida deixa de abrir; não deixa remover a **última** chave; trocar a senha mantém o FIDO; **ataques**: apagar a exigência de FIDO do arquivo ou inserir a chave do atacante não abre; desativar FIDO mantém os dados intactos; chave sem hmac-secret recusada |
| `teste_forca.py` | Tamanhos, números e símbolos do gerador, sem senhas repetidas; frases (5 palavras = 100 bits); PINs óbvios (1234, 0000, 1212, 1990, 2580…) reconhecidos; estimativa realista (123456, senha123, Flamengo2024, Tr0mb0ne-Laranja…); auditoria do cofre (repetidas, PIN óbvio); impressão (quebra de linhas, aviso na folha, impressoras que geram arquivo); tamanhos das estruturas do Windows usadas na impressão |
| `teste_falha_de_memoria_e_sorteio.py` | Falta de memória na 2ª derivação do Argon2 (e na renormalização NFC) não troca o sal nem tranca o cofre (modos OU e E); a frase é sorteada de forma uniforme (bits calculados = reais); destruir/apagar planilha não segue link simbólico nem sobrescreve hard link; planilha com milhares de linhas só formatadas importa normalmente |
| `2_TESTE_telas_e_botoes/teste_gui_limpeza_ao_bloquear.py` | Ao bloquear: hash no lugar dos dados do item, lista/painel soltos, timers cancelados e nenhuma referência à senha; clipboard recusado se a cópia protegida falha; aviso "Bloqueando em N s"; Enter escolhe "Não" nas confirmações destrutivas |
| `teste_planilha_selo.py` | Modelo selado: selo confere, preencher não invalida, estrutura adulterada/selo forjado/outro cofre recusados; **modo estrito**: só o modelo do cofre entra (CSV, planilha comum, outro cofre, adulterada, parte binária extra e macro são recusados) |
| `teste_autodestruicao.py` | Apaga cofre, backups e temporários; travas de sincronização podem permanecer sem dados. Verifica ausência de segredos, 3 sobrescritas, links simbólicos, **tentativas em todas as combinações** (senha / chave / FIDO / recuperação nos 3 modos) e varredura da **memória do processo** (Linux) após fechar/destruir |
| `2_TESTE_telas_e_botoes/teste_gui_recorte.py` | Em 3 tamanhos de janela (1366×768, 1024×640, 900×600), nenhuma tela nem janela tem rótulo, botão ou campo **cortado** nem widget fora da borda |
| `2_TESTE_telas_e_botoes/teste_gui_tentativas_config.py` | Setas das caixas numéricas funcionam (clique real), tentativas só dentro do cofre (pede a senha mestra), tela inicial sem textos cinza soltos |
| `teste_pc_autorizado.py` | Computador autorizado: abre só nos autorizados, outro é recusado sem gastar tentativa, código de recuperação, vários computadores, remover/desativar, combinação com FIDO (fator a mais), adulteração, memória zerada, limite de 8, leitor SMBIOS |
| `teste_pc_segredo_local.py` | Reforço DPAPI do computador autorizado: segredo local, variantes, segredo apagado/corrompido, recusa sem segredo |
| `2_TESTE_telas_e_botoes/teste_gui_imprimir_chave.py` | Impressão só da chave de acesso e do código de recuperação: pede a senha mestra, bloqueia qualquer outro título, folha sem dados de item, nome `Documento_Sistema` |
| `teste_tecnico_sistema.py` | Auditoria técnica: segredos fixos, funções perigosas, rede, registro, DLLs, mutações profundas de cabeçalho, canal de tempo |
| `teste_red_team.py` | Atacante com engenharia reversa/depurador/forense: strings, entropia, bits alterados, contador zerado, outro PC, custo de força bruta |
| `4_TESTE_so_no_windows/teste_nativo_windows.py` (+ `.bat`) | **No Windows real:** atributos oculto/sistema/somente leitura, ACL (`icacls`), UUID SMBIOS × PowerShell, DPAPI (criar/adulterar), computador autorizado de ponta a ponta, blindagens e DLLs da System32, WebAuthn. Resultado em `resultados\resultado_nativo_windows.txt` (ou `_H.txt` etc. se testou um pendrive). **Já confirmado em Windows real: 39/39.** Tudo dentro da própria pasta (sem usar `%TEMP%`) |
| `teste_severo_modificacoes.py` | Teste severo das modificações: impressão restrita (varredura do código + 208 títulos indevidos), 219 bytes invertidos/truncamentos/lixo no arquivo com o fator computador, tentativas e autodestruição, instalador (ordem das perguntas, ACL, sem atalhos, BOM/CRLF) e hashes dos pacotes offline |
| `teste_desempenho_forca_bruta.py` | Desempenho e força bruta: custo do Argon2id por nível (≈1 s Alta, ≈6 s Máxima), 5000 itens, salvamentos repetidos sem crescer, 100 senhas erradas → autodestruição, senhas/campos absurdos sem travar, senha mínima também no núcleo |
| `2_TESTE_telas_e_botoes/teste_gui_efeitos.py` | Animação e efeitos: troca de tela única, janela nunca transparente, aviso "Verificando…" só quando demora e sempre some, 60 trocas e 15 ciclos bloquear/desbloquear sem vazamento de janelas/widgets |
| `2_TESTE_telas_e_botoes/teste_gui_computadores.py` | Janela *Computadores autorizados*, ranking +10 e desbloqueio em computador não autorizado (pede o código, sem gastar tentativa) |
| `teste_ocultar_apoio.py` | Arquivos de apoio ocultos/somente leitura: lista exata (cofre, cópias, programa, hash, logs), `.bat` e arquivos do usuário intocados, revelar desfaz só a marca e preserva outros atributos, nada é escondido fora do programa compilado, cofre abre/salva/autodestrói normalmente (Windows simulado) |
| `teste_patch_bypass.py` | Atacante que remenda o programa (todas as comparações forçadas a verdadeiro): senha errada ou chave errada continuam sem abrir (modos S, E e OU) e a tentativa continua contada |
| `2_TESTE_telas_e_botoes/teste_gui_abertura.py` | Tela de desbloqueio pronta em menos de 2 s e bibliotecas de Excel/FIDO carregadas só sob demanda |
| `teste_nivel_protecao.py` | Ranking de proteção: pontos por item ativo, níveis e ação sugerida |
| `teste_backup_chave.py` | `confere_chave_acesso`: só a chave deste cofre vale (modos E e OU); outra chave, erro de digitação, senha mestra e vazio são recusados |
| `2_TESTE_telas_e_botoes/teste_gui_teclado_virtual.py` | Teclado virtual: 80 teclas criadas uma vez (sem piscar), digitam/apagam, maiúsculas, contagem sem revelar, Esc fecha, resposta rápida |
| `2_TESTE_telas_e_botoes/teste_gui_ajustes_ui.py` | Gerador com rodapé fixo e **senha oculta até clicar no olho**, "Usar em um novo item", caixas de extras (sem revelar senhas), grupos por perfil, painel de proteção com nível, guia na 1ª entrada, troca de tela sem piscar |
| `teste_importacao.py` | Cabeçalho fora do lugar, acentos e colunas fora de ordem; várias abas; CSV do Chrome; CSV em cp1252; PIN com zero à esquerda; classificação nova, igual ou conflito; arquivos inválidos; modelo de planilha; apagamento seguro |
| `1_TESTE_motor_do_cofre/teste_nucleo_concorrencia_multiprocessos.py` | **Concorrência real**: 6 processos disputando a trava (exatamente 1 dono, 3 rodadas) e 3 escritores + 1 leitor no mesmo arquivo por 10 s: nenhum salvamento confirmado se perde, sem duplicados, sem `.tmp` sobrando, leitor nunca vê arquivo inválido |
| `1_TESTE_motor_do_cofre/teste_nucleo_gc_objetos_sensiveis.py` | Depois de `fechar()` a instância some do heap (`gc`), chaves e textos secretos estão zerados no lugar e uma varredura por iscas não acha nada; 20 ciclos abrir/fechar sem crescer |
| `1_TESTE_motor_do_cofre/teste_nucleo_esquema_hostil.py` | Arquivo de cofre válido mas com itens de tipo errado (PIN em lista, `id` repetido/ausente, aninhamento de 3000 níveis, inteiro de 5000 dígitos, NaN): abre, é saneado (`_sanear_itens`), audita e regrava sem erro |
| `1_TESTE_motor_do_cofre/teste_nucleo_fido_mensagens.py` | Mensagens da chave FIDO: **chave sem PIN** (manda criar o PIN), **PIN bloqueado** (avisa que redefinir APAGA as credenciais e manda usar a 2ª chave/código de recuperação), PIN errado, cancelou, tempo, chave errada, recurso ausente |
| `1_TESTE_motor_do_cofre/teste_nucleo_caminhos_especiais.py` | Pastas com espaços, símbolos, acentos, japonês/árabe, emoji, ponto no fim, nome de 120 caracteres e caminho de ~280: ciclo completo criar/salvar/.bak/trava/abrir/trocar senha, lista de apoio sem `.exe`/`.bat`/arquivos do usuário |
| `3_TESTE_ataques_simulados/teste_pentest_superficie_instalador.py` | Análise estática do instalador: sem registro, serviço, tarefa agendada, atalho, pasta Inicializar, protocolo de URL nem menu de contexto; sem pedir administrador; ACL só do dono + SISTEMA; atualização preserva o cofre; sem segredo em disco |
| `3_TESTE_ataques_simulados/teste_pentest_rede_bloqueada.py` | Rede indisponível/lenta/hostil (URLError, DNS, certificado, reset, 503, resposta enorme, lixo, porta fechada, servidor mudo): a checagem opcional de senha vazada falha em silêncio, nunca trava nem derruba o cofre |
| `3_TESTE_ataques_simulados/teste_pentest_residuos_disco_entropia.py` | Sessão completa e varredura de **todo** arquivo da pasta e novo no TEMP atrás de qualquer segredo (UTF-8/UTF-16/Latin-1/invertido); entropia ~8 bits/byte nos arquivos do cofre; sem token de chave solto nos arquivos de apoio |
| `3_TESTE_ataques_simulados/teste_pentest_ocultacao_continua.py` | Ocultação contínua (Windows simulado): cofre escondido o tempo todo, liberado só ao gravar, escondido de novo mesmo com erro/threads/aninhamento; `.exe`, `.bat` e arquivos do usuário intocados |
| `2_TESTE_telas_e_botoes/teste_gui_resiliencia_uso.py` | Salvar clicado 15x (1 item só), texto gigante/emoji/RTL/controle, perda de foco (aviso curto não cobre, prolongado cobre, clique restaura, texto digitado fica), 30 ciclos sem vazar widgets/descritores/GDI, janelas de senha fecham, tela de integridade, aviso "não retire o pendrive" |
| `1_TESTE_motor_do_cofre/teste_nucleo_soak_longa_duracao.py` | **Soak (longa duração) do núcleo:** 1.000 ciclos seguidos de abrir → alterar → salvar → fechar (com consulta e troca de senha de vez em quando; Argon2id barato só no teste). Descritores/handles, threads, instâncias de `Cofre` vivas e memória do Python não crescem; sem `.tmp`, no máx. 5 cópias, arquivo do mesmo tamanho; o cofre abre no fim. Padrão 1.000 (`COFRE_SOAK_CICLOS`); ~13 s |
| `2_TESTE_telas_e_botoes/teste_gui_soak_longa_duracao.py` | **Soak da interface:** ciclos seguidos de desbloquear → tela principal → (formulário a cada 20, salvar a cada 50) → bloquear: widgets, descritores, objetos GDI/USER (Windows), threads, `Cofre` vivos e memória. Padrão 60 ciclos (~3 s cada, a interface é desenhada em Python puro); `COFRE_SOAK_CICLOS=1000` para a corrida longa (~50 min). **Observação:** a memória do Python sobe ~12 KiB por ciclo na interface (limitado e pequeno; o teste só falha acima de 2 MiB no total) |
| `6_TESTE_ferramentas_dos_testes/cobertura_codigo.py` (+ `cobertura_codigo_windows.bat`) | **Cobertura de código** (coverage.py, com ramificações): roda núcleo e pentest sob `coverage` e grava `cobertura_codigo.txt`, `cobertura_codigo.json` e `cobertura_html.zip` diretamente em `testes\resultados\`. Fora do Testar_Tudo (lento; é análise, não teste). `--gui` inclui a interface; `--minimo N` falha abaixo de N% |

---

## 10. Ferramentas extras de segurança do Windows

Pasta `ferramentas_windows_opcionais/` (antiga `extras\seguranca-windows\`). São scripts **opcionais**, independentes do cofre, para conferir e reforçar o PC. Cada `.ps1` tem um `.bat` correspondente para rodar com dois cliques.

| Script | O que faz | Altera o PC? |
|---|---|---|
| `verificar_seguranca` | Relatório de antivírus, Windows Update, firewall, SMBv1, Área de Trabalho Remota e programas de acesso remoto, UAC, SmartScreen, contas Convidado e Administrador, TPM, Secure Boot, Integridade da memória (HVCI), Credential Guard, proteção LSA, histórico da área de transferência e teclados conectados. Salva uma cópia na Área de Trabalho | **Não**, só lê |
| `verificar_nucleo` | Procura sinais de rootkit: drivers sem assinatura ou de fabricante desconhecido, inicialização segura e itens de boot | **Não**, só lê |
| `aplicar_seguranca` | Cria um **ponto de restauração** e depois: desliga a reprodução automática de pendrives, desliga o histórico da área de transferência (Win+V), abre a tela da Integridade da memória (você liga com 1 clique) e mostra o modelo da placa-mãe para ativar o Secure Boot. Mantém o antivírus que você já usa | Sim |
| `desfazer_seguranca` | Desfaz os ajustes do `aplicar_seguranca` | Sim |

Leia cada script antes de rodar. Os que alteram o PC precisam ser executados como administrador.

---

## 11. Cuidados ao publicar no Git

O `.gitignore` já impede o envio de:

- `cofre.dat` e qualquer `*.dat`;
- arquivos de chave `*.key`;
- planilhas `*.xlsx`, `*.xlsm` e `*.csv`;
- o `CofreSenhas.exe` e as pastas de compilação;
- logs e caches.

Mesmo assim:

- **Nunca** faça commit do seu `cofre.dat`, da chave de acesso, do código de recuperação FIDO ou de planilhas com senhas. Antes de cada commit, confira com `git status` o que vai subir.
- Prefira um **repositório privado**. Publicar o código não enfraquece o cofre, porque a segurança está nas chaves e não no segredo do código. Mas não há motivo para expor o seu fluxo pessoal.
- Para distribuir o programa compilado, publique também o **SHA-256** do `.exe`, para quem baixar poder conferir.

---

## 12. Perguntas frequentes

**Se roubarem meu pendrive, conseguem abrir?**
Não. Sem a senha e a chave de acesso (e a chave FIDO, se ativada), o `cofre.dat` é ruído aleatório. Com BitLocker no pendrive, o ladrão nem chega a ver o arquivo.

**E se eu esquecer a senha?**
No modo OU, a chave de acesso abre o cofre. No modo E, não há recuperação: é o preço de ninguém mais conseguir abrir. Guarde a chave e um backup em locais diferentes.

**Perdi a chave FIDO. E agora?**
Use o **código de recuperação** (anotado em papel) ou a chave reserva, e depois remova a chave perdida em **Chave FIDO**. Remover **não troca o segredo interno da chave FIDO**: cópias antigas do cofre ainda abrem com a chave removida, então, se ela foi roubada e não só perdida, troque também a senha mestra e gere uma nova chave de acesso (isso troca a chave interna dos dados).

**Posso usar em mais de um computador?**
Sim. O cofre e o programa são portáteis. Leve os dois no pendrive.

**Por que o Ctrl+C não funciona nos campos de senha?**
De propósito: impede que qualquer coisa digitada vá parar na área de transferência sem você querer. Use o botão **Copiar**, que protege a cópia e a apaga em 15 s.

**Por que abrir demora alguns segundos?**
É o Argon2id trabalhando com 1 GiB de memória. Essa demora é o que torna a força bruta inviável.

**O programa acessa a internet?**
Não. O cofre não faz nenhuma conexão sozinho. Há **uma** função opcional que usa a internet, só quando você pede: ⋯ › Verificar senhas › **Checar vazamentos (online)**. Ela usa o Have I Been Pwned com *k-anonymity*: de cada senha sai pela rede apenas os 5 primeiros caracteres do SHA-1 (nunca a senha nem o hash inteiro), por HTTPS; a comparação final é feita no seu computador. O serviço vê o seu endereço de internet e que você fez a consulta. Fora isso, só o **instalador** baixa o Python e as bibliotecas.

## 13. Camadas de segurança (visão organizada)

| Camada | O que é | Quando vale | Protege contra |
|---|---|---|---|
| **0. Meio físico** | **Pendrive com BitLocker To Go** (modo portátil) ou **pasta NTFS com ACL** (modo no computador) | sempre | pendrive roubado/perdido; outras contas do Windows |
| **1. Computador autorizado** *(opcional, fator a mais)* | até 8 computadores (MachineGuid + UUID da placa-mãe), com **reforço DPAPI** | ativado em *Computadores autorizados…* | arquivo do cofre levado para outro computador |
| **2. Senha mestra + chave de acesso** | Argon2id (1 GiB) + chave de 160 bits (`.key`), modos **OU / E / S** | sempre | força bruta; cópia do arquivo |
| **3. Chave FIDO2** *(opcional)* | segredo da chave física (hmac-secret/PRF) entra na chave dos dados | ativado em *Chaves FIDO* | senha vazada; teclado espionado |
| **4. Código de recuperação** | um único código em papel para os fatores extras (FIDO e computadores); gerar outro invalida o anterior | emergência | perda da chave FIDO ou troca de computador |
| **Proteções em execução** | cifra em cascata ChaCha20-Poly1305 + AES-256-GCM; bloqueio de captura de tela; anti-depuração; bloqueio automático; **autodestruição** após N senhas erradas (contador único para senha e código); memória zerada; arquivos de apoio ocultos; importação selada; teclado virtual | enquanto o cofre está aberto | espionagem, adulteração, uso por terceiros |
| **Impressão restrita** | só chave de acesso e código de recuperação, com senha mestra antes | emergência | vazamento de senhas por papel/fila de impressão |

Cada camada é **independente**: perder uma não abre o cofre (exceto o código de recuperação, que só substitui os fatores *extras*, nunca a senha mestra nem a chave de acesso). O ranking de proteção (soma limitada a 100) mostra no cofre quais camadas estão ligadas.

## 14. O que mudou neste projeto

**Segurança do cofre**
- Importação **selada** (só a planilha gerada pelo próprio cofre, com selo HMAC) e quarentena.
- Senhas **só para os olhos** (sem copiar). *(A biometria / Windows Hello, que existia numa versão anterior, foi **removida** nesta rodada: só chave de segurança FIDO2 física.)*
- **Backup exige a chave de acesso**; teclado virtual; contagem de tentativas revisada e **autodestruição auditada**; tentativas **configuradas dentro do cofre**.
- **Computador autorizado** (até 8, fator a mais, sem gastar tentativa em computador não autorizado) e **reforço DPAPI** (segredo local da conta).
- **Código de recuperação único** para FIDO e computadores.
- **Arquivos de apoio ocultos/protegidos** (Oculto+Sistema+Somente leitura). **Atualizado 2026-11-16:** o cofre e as cópias (`.bak`, `.lock`, `.diag`...) ficam escondidos **o tempo todo** com o programa aberto e só são liberados no instante de cada gravação (salvar, abrir/contar tentativa, criar, apagar); `avisos_vistos.json`, logs e a pasta temporária continuam sendo escondidos ao sair. Não depende mais de um fechamento "limpo" para ficar fora de vista. Teste: `3_TESTE_ataques_simulados/teste_pentest_ocultacao_continua.py` (simulado); no Windows real quem confirma os atributos é `4_TESTE_so_no_windows/B - testar atributos e permissoes do Windows.bat`.
- **Impressão restrita** à chave de acesso e ao código de recuperação (senha mestra antes, nome `Documento_Sistema`, aviso na tela); removida a impressão de itens.
- **Dados bancários** (número da conta / agência), com camada extra própria: pedem a senha mestra de novo SEMPRE (ver, copiar, editar), mesmo com a proteção extra geral desligada (2026-11-15).

**Interface:** formulário simples/completo de item, ranking de proteção, animações e desempenho (menos piscadas), textos de ajuda revisados.

**Instalação:** pergunta **Portátil × No computador** antes de tudo; **ACL NTFS** no modo computador; nenhum atalho criado; **pacotes offline** (`pacotes\`) sem download antes de compilar; aviso de FAT32/exFAT e BitLocker; cache de compilação.

**Qualidade:** a senha mínima (14 caracteres) também é exigida no núcleo (`Cofre.criar` e `trocar_senha`); análise estática (Bandit/Flake8) empacotada no wheelhouse. O `pip-audit` só verifica vulnerabilidades ao consultar a base atual pela internet e, por isso, é registrado como `PULADO` no fluxo offline; resultados de rodadas online anteriores não significam que a base esteja atualizada hoje.

**Validação no Windows real (2026-11-20):** a bateria nativa registrou 39/39 verificações aprovadas; a bateria completa registrou 45 testes de interface sem falhas; e uma execução focada posterior do Pester passou 12/12. Isso cobre atributos, ACL (`icacls`), DPAPI, SMBIOS e funções auxiliares do instalador, mas **não** equivale a uma compilação/instalação ponta a ponta.

**Ainda não validado em Windows real:** instalação e compilação completas de ponta a ponta, assinatura digital opcional, chave FIDO2/PRF física e execução no Windows Sandbox. Build nativo ARM64 não é suportado.

**Compatibilidade:** versões antigas do programa **não abrem** cofres com o fator *computador*; backups feitos antes de ativá-lo continuam abrindo em qualquer computador.

---

Estratégia, riscos e critério Go/No-Go: veja `testes/PLANO_DE_TESTES.md`.
