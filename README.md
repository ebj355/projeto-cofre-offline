<!-- ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt -->
# 🔐 Arca — Cofre de Segurança (offline)

![Arca — Cofre de Segurança, produto da Arca Sistemas](<imagens visuais para campanha/arca_capa_1600x300.png>)

<p align="center">
  <img src="imagens%20visuais%20para%20campanha/arca_perfil_230x320.png" alt="Arca — cofre offline" width="160">
</p>

**Produto da Arca Sistemas.** A Arca é um cofre de segurança e gerenciador de senhas **100% local para Windows**. Um único programa, sem nuvem, sem conta e sem conexões automáticas, guarda as senhas num arquivo criptografado (`cofre.dat`) e roda direto de um pendrive ou de uma pasta protegida do computador. A verificação online de senhas vazadas é opcional e só acontece quando solicitada.

![Windows 10/11](https://img.shields.io/badge/Windows-10%20%2F%2011%20(64%20bits)-0078D6?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11%20%E2%80%93%203.13-3776AB?logo=python&logoColor=white)
![Offline](https://img.shields.io/badge/rede-nenhuma%20(salvo%20consulta%20opcional)-2ea44f)
![Criptografia](https://img.shields.io/badge/cripto-ChaCha20--Poly1305%20%2B%20AES--256--GCM-5a4fcf)
![Senha mestra](https://img.shields.io/badge/senha%20mestra-Argon2id%201%20GiB-5a4fcf)
![FIDO2](https://img.shields.io/badge/fator%20extra-FIDO2%20(opcional)-5a4fcf)
![Testes](https://img.shields.io/badge/testes-motor%20%7C%20telas%20%7C%20pentest%20%7C%20Windows%20real-2ea44f)

> **Princípio do projeto:** a segurança não depende de o código ser secreto. Tudo aqui pode ser lido e auditado. O que protege os seus dados é a matemática: a senha mestra, a chave de acesso e, opcionalmente, uma chave física FIDO2. Sem elas, o arquivo do cofre é só ruído aleatório.

---

## Índice

1. [Resumo em um minuto](#1-resumo-em-um-minuto)
2. [Visão geral e o que o projeto contempla](#2-visão-geral-e-o-que-o-projeto-contempla)
3. [Para quem é (e para quem não é)](#3-para-quem-é-e-para-quem-não-é)
4. [O que o programa faz](#4-o-que-o-programa-faz)
5. [Como a segurança funciona](#5-como-a-segurança-funciona)
6. [Integridade e resiliência dos dados](#6-integridade-e-resiliência-dos-dados)
7. [Proteções do Windows](#7-proteções-do-windows)
8. [Modelo de ameaças e limites](#8-modelo-de-ameaças-e-limites)
9. [Requisitos](#9-requisitos)
10. [Instalação](#10-instalação)
11. [Primeiros passos](#11-primeiros-passos)
12. [Uso no dia a dia e atalhos](#12-uso-no-dia-a-dia-e-atalhos)
13. [Rodando direto do código-fonte e dependências](#13-rodando-direto-do-código-fonte-e-dependências)
14. [Testes automáticos](#14-testes-automáticos)
15. [Ferramentas opcionais do Windows](#15-ferramentas-opcionais-do-windows)
16. [Estrutura do repositório](#16-estrutura-do-repositório)
17. [Documentação detalhada](#17-documentação-detalhada)
18. [Cuidados ao publicar no Git](#18-cuidados-ao-publicar-no-git)
19. [Solução de problemas](#19-solução-de-problemas)
20. [Perguntas frequentes](#20-perguntas-frequentes)
21. [Glossário](#21-glossário)
22. [Decisões de projeto (o que foi adotado e o que não)](#22-decisões-de-projeto-o-que-foi-adotado-e-o-que-não)
23. [Status e honestidade do projeto](#23-status-e-honestidade-do-projeto)
24. [Licença e aviso legal](#24-licença-e-aviso-legal)

---

## 1. Resumo em um minuto

**O que é:** um cofre de senhas que fica num arquivo seu (`cofre.dat`), ao lado de um programa (`CofreSenhas.exe`) que **você mesmo compila** no seu computador. Não existe servidor, conta, sincronização nem telemetria.

**O que protege:**

| Camada | Resumo |
|---|---|
| **Dados** | Cifra em cascata: ChaCha20-Poly1305 dentro de AES-256-GCM, com chave interna aleatória de 256 bits. |
| **Senha mestra** | Mínimo de 14 caracteres, passa pelo Argon2id (até 1 GiB de memória por tentativa). Senhas fracas são recusadas. |
| **Fatores extras** | Chave de acesso de 160 bits (modo E/OU/S), chave física FIDO2 e lista de computadores autorizados (todos opcionais). |
| **Tentativas** | Autodestruição após 1 a 10 erros de senha (padrão 3), com contador gravado **antes** de testar a senha. |
| **Tela e teclado** | Janela invisível a prints e gravações, teclado virtual embaralhado, cópia protegida que se apaga em 15 s. |
| **Arquivo** | Gravação atômica conferida por SHA-256, 5 cópias automáticas, checksum, manifesto interno e modo consulta. |
| **Build** | Bibliotecas, Nuitka e Zig com versão e hash fixos; você digita 16 caracteres do SHA-256 do código antes de compilar. |

**Para começar:**

1. Baixe o projeto e dê dois cliques em **`1 - INSTALAR O COFRE - compila e instala.bat`** (confira o SHA-256 quando o instalador pedir).
2. Na tela de criação, siga as etapas da senha mestra, modo de abertura e proteção contra tentativas. Recomendado: **Senha E chave de acesso**; guarde a chave exibida uma única vez.
3. Anote o SHA-256 do `.exe` em papel e faça um backup do cofre em **outro lugar**.

**O que ele não é:** não sincroniza com o celular, não preenche senhas no navegador e não passou por auditoria independente (veja [Status e honestidade](#23-status-e-honestidade-do-projeto)).

---

## 2. Visão geral e o que o projeto contempla

A **Arca**, produto da **Arca Sistemas**, foi feita para quem quer guardar logins, senhas, PINs, chaves de API, códigos de recuperação e dados bancários **sem entregar nada para um serviço na nuvem**.

| Característica | Como é |
|---|---|
| **Local** | Tudo fica num arquivo `cofre.dat`, ao lado do programa. Não há servidor, conta nem sincronização. |
| **Portátil** | Funciona num pendrive (recomendado, com BitLocker To Go) ou numa pasta do computador protegida por permissões do Windows. |
| **Fontes conferíveis** | O motor fica em `cofre_senhas.py` e os dados de marcas/autocompletar em `icones_marcas.py`; o instalador confere os dois arquivos e seu hash combinado. |
| **Compilado por você** | O instalador compila o `CofreSenhas.exe` no seu próprio computador, a partir de bibliotecas com versão e hash fixos. Você não baixa um `.exe` pronto de ninguém. |
| **Em português** | Interface escura no estilo Windows 11, com mensagens que explicam o que fazer, não só o que deu errado. |
| **Sem rastros no sistema** | Sem registro, serviço, tarefa agendada, atalho, menu de contexto ou pedido de administrador. "Desinstalar" é apagar a pasta. |

Em uma frase: **é um cofre que só abre com o que você sabe (senha), o que você tem (chave de acesso e, opcionalmente, uma chave FIDO2) e, opcionalmente, o computador onde você autorizou.**

### Os cinco componentes do projeto

| Componente | O que contém | Onde |
|---|---|---|
| **1. O programa** | O cofre inteiro: criptografia, arquivo, interface, importação, FIDO2, proteções do Windows | `cofre_senhas.py` |
| **2. O instalador** | Confere o código por hash, prepara ambiente isolado, compila o `.exe` nativo, testa a criptografia | `1 - INSTALAR O COFRE...bat` + `instalar_cofre.ps1` |
| **3. Testes e executor** | Seis etapas obrigatórias; a pasta 6 contém o executor, não uma bateria. A etapa 7 é opcional e pós-compilação. | `testes/` + `2 - TESTAR TUDO...bat` |
| **4. Ferramentas opcionais do Windows** | Scripts independentes que verificam e reforçam o seu PC (não o cofre) | `ferramentas_windows_opcionais/` |
| **5. A documentação** | Este README é o guia único de entrada; manuais técnicos e plano de testes detalham assuntos específicos | `README.md`, `documentacao/`, `testes/*.md` |

### Fluxo de compilação e testes

```text
FONTE DO PROGRAMA
cofre_senhas.py + requirements.txt
          │
          ▼
1 - INSTALAR O COFRE - compila e instala.bat ──► instalar_cofre.ps1
                               │
                               ├─ confere o hash do código com você
                               ├─ prepara Python e dependências fixadas
                               ├─ executa o teste de criptografia
                               └─ compila com Nuitka + Zig
                                          │
                                          ▼
                                  CofreSenhas.exe

2 - TESTAR TUDO - roda todos os testes.bat
          │
          ▼
rodar_todos_windows.bat
  ├─ 1 núcleo
  ├─ 2 instalador
  ├─ 3 Windows nativo
  ├─ 4 interface
  ├─ 5 pentest
  ├─ 6 ferramentas externas
  ├─ resultados em testes\resultados\
  └─ 7 testes de compilação (depois de compilar)
```

O executor `rodar_todos_windows.bat` fica em `testes\6_TESTE_ferramentas_dos_testes\`; os números acima indicam a ordem das etapas. O fluxo não compila o aplicativo: a etapa 7 verifica um executável já compilado e roda automaticamente, registrando `[PULADO]` quando não houver pré-requisitos.

---

## 3. Para quem é (e para quem não é)

**É para você se:**

- quer um cofre de senhas **offline**, sob seu controle total, sem depender de serviços na nuvem;
- usa um pendrive e aceita ativar o **BitLocker To Go** nele;
- está disposto a guardar uma chave de acesso e um backup em locais separados;
- gosta de poder **ler e conferir** o que o programa faz.

**Não é para você se:**

- precisa de **sincronização automática** entre celular e computador (não existe versão mobile nem nuvem);
- precisa **preencher senhas automaticamente** no navegador (não há extensão de navegador);
- quer um programa **auditado por terceiros** ou com suporte comercial;
- usa **macOS ou Linux** como sistema principal (o programa e as proteções são para Windows; os testes do motor também rodam em Linux, mas só para desenvolvimento).

---

## 4. O que o programa faz

### 4.1 Formas de desbloquear

| Fator | O que é | Observações |
|---|---|---|
| **Senha mestra** | Mínimo de **14 caracteres** (máximo 1.024). Passa pelo Argon2id: cada tentativa custa até 1 GiB de memória e alguns segundos. | Senhas só com números, sequências (`123456`, `qwerty`), senhas de listas vazadas e as que o medidor classifica como fracas são **recusadas**. O núcleo também recusa menos de 14 caracteres, não só a tela. |
| **Chave de acesso** | 160 bits aleatórios no formato `XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XX`. Os 2 últimos caracteres são de verificação: um erro de digitação é percebido **sem gastar tentativa**. | Aparece **uma única vez**, ao criar o cofre. Pode ser salva num arquivo `.key` **cifrado e selado** ao cofre de origem, ou anotada à mão. **Não é impressa automaticamente.** |
| **Chave FIDO2** *(opcional)* | Chave física USB/NFC (YubiKey 5, Feitian ePass FIDO2…), com PIN e toque. | Aceita até 8 chaves (principal + reserva). Gera um **código de recuperação** em papel. Só chave física: **sem biometria**. |
| **Computador autorizado** *(opcional)* | O cofre só abre nos computadores da lista (até 8), reconhecidos pelo MachineGuid do Windows + UUID da placa-mãe (SMBIOS). | Fator **a mais**. Em computador fora da lista, o cofre recusa **antes do Argon2 e sem gastar tentativa**. Pode ter reforço com segredo local protegido pelo DPAPI. |

**Modos de desbloqueio**, escolhidos ao criar o cofre:

| Modo | Como funciona | Quando escolher |
|---|---|---|
| **Senha E chave de acesso** *(recomendado)* | Os dois fatores são obrigatórios. Quem descobrir só a senha, ou só a chave, não abre. | Uso normal, com mais segurança. |
| **Senha OU chave de acesso** | Qualquer um dos dois abre. A chave funciona como recuperação se você esquecer a senha. | Quando o medo de esquecer a senha é maior que o de vazá-la. |
| **Só senha mestra** | Não existe chave de acesso. | O jeito mais simples; a segurança vem só da senha longa + Argon2id. |

**Níveis de blindagem do Argon2id:**

| Nível | Memória por tentativa | Iterações | Custo aproximado por tentativa |
|---|---|---|---|
| **Máxima** | 1 GiB | 6 | ≈ 5,9 s por núcleo |
| **Alta** | 256 MiB | 4 | ≈ 1,1 s por núcleo |

Em PCs com pouca RAM livre, o programa sugere *Alta* na criação e, antes de qualquer derivação, **recusa sem gastar tentativa** se faltar memória física (para o Windows não paginar o Argon2 em disco).

### 4.2 O que cada item guarda

| Campo | Exemplo |
|---|---|
| Conta / App | Banco, Gmail, Samsung… |
| Login | e-mail, CPF, usuário |
| Senha / Senha extra / PIN | senha principal, senha de transação, senha numérica |
| Chave | chave de API, chave Pix, token |
| Número da conta e Agência | dados bancários (com camada extra de proteção, veja abaixo) |
| Códigos de recuperação | uma lista, um por linha |
| Notas | texto livre |
| Grupo | organiza a barra lateral (cada grupo tem sua cor) |
| Pessoa | de quem é a conta: Eu, Pai, Mãe… |

- **Novo item em tela única:** campos organizados em cartões, senha com **Gerar…**, notas sempre visíveis e códigos/PIN/senha extra/chave/conta/agência opcionais. As dicas cinzas nos campos vazios são apenas visuais: nunca entram no valor salvo. O botão **Copiar** só existe ao editar um item existente. `Enter` salva.
- **Aparência:** seis temas prontos — Roxo (padrão), Obsidiana, Claro, Terminal, Azul e Rosa — disponíveis em `⋯ → Aparência e cores`. A escolha vale para todos os cofres daquele usuário neste computador. Só o nome do tema é salvo separadamente em `%LOCALAPPDATA%\CofreSenhas\preferencias.json`; esse arquivo não contém senhas nem dados do cofre. Não há personalização livre de cores.
- **Identificação de serviços:** nomes e URLs conhecidos recebem monogramas locais discretos (por exemplo, NU, IG, GD e GH), sem baixar ou copiar logos oficiais e sem conexão de rede. Quando o serviço não é reconhecido, o grupo selecionado pode indicar a categoria; sem correspondência, é usado o avatar genérico.
- **Avisos e exposição:** alertas mantêm ícone e texto além da cor. O cofre mostra sua tela de desbloqueio ao bloquear e limpa a área de transferência após 15 segundos, ao bloquear ou ao sair.
- **Pessoas:** um mesmo cofre guarda as senhas de várias pessoas (você, familiares), todas abertas pela mesma senha mestra. Os nomes das pessoas também ficam criptografados. Pessoas e grupos mudam por **transação**: se a gravação falhar, tudo volta ao que era.
- **Dados bancários:** qualquer item com número da conta e/ou agência **sempre** pede a senha mestra de novo para ser visto, copiado ou editado, mesmo com a "Proteção extra" geral desligada. A liberação dura 30 segundos. A proteção é por **item inteiro**, não por campo.
- **Proteção extra:** um ajuste único para o cofre inteiro (`⋯ → Proteção extra`) que exige a senha mestra de novo para ver ou copiar qualquer senha. A reconfirmação usa um verificador rápido em memória (HMAC com chave aleatória da sessão), sem repetir o Argon2.
- **Saneamento dos itens:** ao abrir, o cofre corrige itens com campo de tipo errado, `id` ausente ou repetido, sem perder campos desconhecidos nem alterar itens válidos.

### 4.3 Gerador de senhas

| Tipo | Tamanho | Uso |
|---|---|---|
| **Aleatória** | 8 a 64 caracteres, com números e símbolos opcionais | Contas de sites e apps |
| **Fácil de lembrar** | 3 a 10 palavras pronunciáveis (75 sílabas possíveis) | Senhas que você precisa digitar de cabeça |
| **PIN** | 4 a 12 dígitos | PINs óbvios (1234, 0000, 1212, anos…) são descartados |

O sorteio usa o gerador criptográfico do sistema (`secrets`). A força mostrada é **exata**, calculada pelo número de combinações possíveis. O gerador abre com `Ctrl+G` e também serve para **testar** uma senha que você já tem.

### 4.4 Avaliação de força e auditoria

- **Nota e barra** (Muito fraca → Muito forte), com bits estimados e composição da senha.
- **Tempo médio para descobrir** em dois cenários: no arquivo roubado, usa o custo medido do Argon2id (cerca de 1,1 s no nível Alto ou 5,9 s no Máximo por tentativa e núcleo); para hashes fracos de sites, usa uma hipótese separada de até 100 bilhões de tentativas por segundo.
- A estimativa é **realista**: penaliza palavras comuns, senhas de listas vazadas, trocas óbvias (`P@ssw0rd`), sequências, repetições, anos e datas.
- **Verificar senhas** (menu `⋯`) audita o cofre todo e aponta senhas fracas, **repetidas** e PINs fáceis. Os itens com problema aparecem no filtro **⚠ Atenção**.
- **Checar vazamentos (online)** é a **única** função que usa a internet, e só quando você clica. Usa o Have I Been Pwned com *k-anonymity*: de cada senha saem pela rede apenas os 5 primeiros caracteres do SHA-1, nunca a senha nem o hash inteiro.

### 4.5 Importação de planilhas

- Lê Excel (`.xlsx`, `.xlsm`) e CSV, encontra o cabeçalho sozinho e entende nomes de colunas em português e inglês.
- Mostra uma **prévia** separando cada linha em *nova*, *igual (ignorada)* ou *com dados diferentes*.
- Avisa quando o Excel "comeu" o zero à esquerda de um PIN.
- Oferece **apagar a planilha com segurança** ao final (sobrescrita com dados aleatórios), porque ela guarda as senhas sem criptografia.
- **Limites:** até 20.000 linhas, 50 MB por arquivo e 90 s de leitura; cada campo tem tamanho máximo. Passou disso, a importação é recusada inteira.
- **Quarentena antes do cofre:** confere os *magic bytes* (recusa `.exe`, ELF e outros), copia para uma pasta isolada, varre (macros, ActiveX, objetos embutidos, vínculos externos, DDE, fórmulas perigosas, endereços `file:`/`javascript:`/UNC, *zip-bomb*), lê **só como valores** e sanitiza cada campo (caracteres de controle e de direção de texto removidos). XML lido com `defusedxml`.
- **Importação segura (padrão):** o cofre só aceita a planilha **gerada por ele mesmo** (`⋯ → Baixar modelo de planilha`), que leva um selo HMAC (aba oculta `_selo_cofre`) ligado ao *seu* cofre. Planilhas comuns, CSV, modelos adulterados ou de outro cofre são recusados antes de ler qualquer dado. Para aceitar planilhas comuns (Chrome, Samsung Pass), mude `IMPORTAR_SOMENTE_COM_SELO = False` no topo do código e recompile, sabendo que isso reduz a proteção.
- Os campos de dados bancários não existem na planilha de propósito (o selo depende do cabeçalho fixo): só o formulário manual os preenche.

```text
arquivo escolhido
      │
      ▼
validar tipo, limites e política de selo ──► varrer e ler isolado
      │                                             │
      └──────── arquivo recusado ◄─────────────────┘
                                                    ▼
                                  converter colunas e sanear registros
                                                    │
                                                    ▼
                           comparar com o cofre: novos / iguais / conflitos
                                                    │
                                                    ▼
                                           prévia para o usuário
                                                    │ confirmar
                                                    ▼
                          incluir/atualizar → salvar cifrado
                               │                       │
                   falha: restaura a lista       sucesso: atualiza a tela
                                                       │
                                      oferece apagar a planilha em claro
```

### 4.6 Cópia segura e impressão

- **Copiar** envia o texto para a área de transferência **fora** do histórico do Windows (Win+V) e da nuvem, marcado para ser ignorado por monitores, e **apaga sozinho em 15 segundos**. Se o Windows não conseguir a cópia protegida, o programa **recusa copiar** em vez de usar a área comum.
- Nos campos de senha, `Ctrl+C`, recortar, arrastar e o menu do botão direito ficam **bloqueados**; a cópia só acontece de propósito, pelo botão.
- O cofre **só imprime duas coisas**: a chave de acesso e o código de recuperação (as cópias de emergência), com a senha mestra pedida antes e nome genérico na fila (`Documento_Sistema`). Senhas e itens **nunca** são impressos. A folha impressa **é uma credencial**: guarde-a como tal (a fila do Windows guarda uma cópia temporária em C:).

### 4.7 Histórico e alerta de invasão

Cada abertura é registrada **dentro do próprio cofre, criptografada**, então um invasor não consegue apagar o rastro. Se alguém errou a senha desde a última vez que você abriu, aparece um **⚠ ALERTA DE SEGURANÇA** ao entrar. O histórico completo fica em `⋯ → Histórico de aberturas`. O alerta é de melhor esforço (o contador fica em texto claro): nunca prova que ninguém tentou.

### 4.8 Backup e cópias automáticas

- **Backup do cofre** (`⋯ → Backup do cofre`) pede e confere a chave de acesso antes de gerar a cópia, que continua criptografada. Salvar no disco do Windows ou no mesmo pendrive do cofre pede confirmação.
- **5 cópias automáticas rotativas** (`cofre.dat.bak1` = mais nova … `.bak5` = mais antiga), no máximo uma nova a cada 10 minutos de uso (e só se o conteúdo mudou). Se o arquivo principal ficar danificado, o programa oferece restaurar a cópia mais recente legível.
- Essas cópias ficam **ao lado do cofre**: não protegem contra perda/remoção do dispositivo nem contra autodestruição após erros de senha. Faça um backup cifrado em outro dispositivo/local e ensaie a restauração com um cofre de teste.
- Trocar a senha ou gerar nova chave de acesso **apaga essas cópias** (elas ainda abririam com a senha antiga).
- Isso **não substitui** um backup seu em outro lugar.

### 4.9 Interface

- Tema escuro no estilo Windows 11, com todos os ícones desenhados pelo próprio programa (sem depender de fontes ou arquivos externos) e contraste mínimo WCAG AA nos textos secundários.
- Campo Serviço com ícones locais de marcas e sugestões offline; aceita nomes livres e não faz consultas de rede.
- **Passeio guiado** na primeira entrada (escurece a janela e destaca cada área) e **Guia de uso e atalhos** no botão `?`.
- Busca instantânea (`Ctrl+F`), lista que desenha só as linhas visíveis (6.000 contas rolam sem engasgar), painel de detalhes e quadro de status da proteção.
- **Ranking de proteção** (escudo na barra lateral): nota de 0 a 100 (Básica, Boa, Forte, Máxima) com botão **Ativar** no que falta, e tela **Segurança adicional** com a visão geral.
- Teclado virtual embaralhado (sem recriar as teclas, então não pisca), olho 👁 para conferir a digitação (volta a esconder em 30 s) e aviso de Caps Lock **dentro** do campo.
- **Janelas aparecem prontas:** o tamanho final é calculado antes de mostrar, sem diálogos "montando" na tela.
- Funciona com zoom de 125% e 150%, em telas baixas (notebooks de 768 px, com barra de rolagem automática) e com navegação por teclado.
- Operações pesadas (Argon2id, abrir, criar, salvar) rodam fora da thread da janela: a tela continua respondendo e o bloqueio automático espera a gravação terminar. No pendrive, aparece "Salvando… não retire o pendrive".
- **Mensagens didáticas:** cada erro diz o próximo passo; o código técnico fica entre parênteses no fim. Avisos informativos aparecem só uma vez (`avisos_vistos.json`, que guarda apenas o hash do texto).

### 4.10 Modo consulta e uso simultâneo

O cofre abre **somente para leitura** (vê e copia, não altera nada, não conta tentativa) quando:

- o pendrive está **protegido contra gravação** (chave física, política do computador ou somente leitura): o programa confirma que a gravação é impossível e oferece o modo;
- o mesmo cofre já está aberto em **outra janela** (trava `cofre.dat.lock`): a primeira janela é a dona e grava; as demais abrem em consulta. O sistema operacional solta a trava sozinho quando a janela dona fecha ou o programa cai, então não existe trava "velha".

Uma faixa amarela avisa que é **MODO CONSULTA**; as ações que alteram dados explicam e voltam.

### 4.11 O menu `⋯` e o botão `?`

| Grupo | Itens |
|---|---|
| **Uso geral** | Importar planilha (Excel / CSV) · Baixar modelo de planilha · Gerador e teste de senhas (`Ctrl+G`) · Verificar senhas (força e repetidas) · Histórico de aberturas · Diagnóstico · Backup do cofre |
| **Segurança** | Verificar integridade do programa · Segurança adicional (visão geral) · Chaves FIDO · Computadores autorizados · Trocar senha mestra · Nova chave de acesso (não existe no modo "só senha") · Bloqueio automático · Proteção extra · Tentativas erradas |
| **Botão `?`** | Passeio guiado desta tela · Guia de uso e atalhos |
| **Barra superior** | Bloquear (`Ctrl+L`) · Chave FIDO · Novo item (`Ctrl+N`) |

### Fluxo de uma sessão do aplicativo

```text
main()
  │ verificações do ambiente + trava de instância
  ▼
App.mostrar_inicio()
  ├─ cofre.dat não existe ─► tela_criar() ─► Cofre.criar()
  │                                               └─► exibe a chave uma vez (quando existe) ─► tela principal
  │
  └─ cofre.dat existe ────► tela_desbloqueio() ─► Cofre.abrir()
                                                  ├─ fatores incorretos ─► mensagem; continua bloqueado
                                                  ├─ modo consulta ──────► pode ver/copiar, não grava
                                                  └─ abertura válida ────► tela principal
                                                                              │
                                               novo/editar/excluir ──────────┤
                                                                              ▼
                                                            salvar alterações de forma cifrada
                                                                              │
                                               bloquear/sair ─► limpar segredos da memória
```

O modo consulta aparece quando o cofre já está aberto em outra instância ou quando o dispositivo não permite gravação. Ele não deve ser confundido com uma sessão normal: alterações não são persistidas e tentativas não são contadas. O bloqueio retorna à tela de desbloqueio; sair encerra a sessão.

---

## 5. Como a segurança funciona

### 5.1 Visão geral das chaves

```
senha mestra ─Argon2id─► K_senha ────────────┐
chave de acesso ─HKDF──► K_chave ───────────┤
                                             ├─ modo S: K_senha (fator principal)
                                             ├─ modo OU: K_senha OU K_chave
                                             └─ modo E: HKDF(K_senha ‖ K_chave)
                                                       │
                                                       ▼
                                      AES-GCM abre o embrulho da DEK
                                                       │
                                                       ▼
                                      DEK (chave interna aleatória)
                                                       │
                  ┌────────────────────────────────────┴────────────────────┐
                  │                                                         │
        FIDO2 (se ativado)                                      PC autorizado (se ativado)
        chave física ou recuperação                            identidade local ou recuperação
                  └──────────────────────────┬──────────────────────────────┘
                                             ▼
                          DEK + fator(es) extras ─HKDF*─► K_dados
                                             │
                              HKDF gera K_cha e K_aes independentes
                                             │
JSON + preenchimento ─ChaCha20-Poly1305(K_cha)─► AES-256-GCM(K_aes) ─► arquivo
```

`*` Com FIDO ou computador autorizado, HKDF combina os fatores extras com a DEK; sem eles, `K_dados = DEK`. Nos modos **E** e **OU**, a chave de acesso não tem o mesmo papel: no modo E, as duas entradas são combinadas para abrir um único embrulho; no modo OU, cada entrada pode abrir seu próprio embrulho da mesma DEK. No modo S, só a senha é usada como fator principal. FIDO2 e computador autorizado são fatores adicionais: não substituem a senha nem a chave de acesso. O código de recuperação substitui esses fatores extras, não os fatores principais.

| Peça | Algoritmo | Detalhes |
|---|---|---|
| Chave interna (DEK) | Aleatória, 256 bits | Sorteada uma vez. Trocar a senha ou a chave de acesso troca **também a DEK** e recifra tudo. |
| Senha → chave | **Argon2id** | Nível **Máxima**: 1 GiB, 6 iterações. Nível **Alta**: 256 MiB, 4 iterações. Paralelismo 2, sal de 128 bits. |
| Chave de acesso → chave | **HKDF-SHA256** | 160 bits de entropia: não precisa de Argon2. |
| Dados | **ChaCha20-Poly1305 dentro de AES-256-GCM** | Duas cifras de famílias diferentes, com subchaves independentes. Uma falha futura em uma delas não expõe os dados. |
| Fator FIDO2 | Extensão **hmac-secret / PRF** | A chave física devolve um segredo que nunca sai do chip. |
| Tamanho do arquivo | Preenchimento em blocos de **4 KiB** | O tamanho não revela quantos itens existem. |
| Integridade | Cabeçalho e seção de fatores autenticados como AAD; checksum simples para dano acidental | AEAD detecta alteração dos dados associados; o checksum não é um MAC. |
| Arquivo de chave `.key` | ChaCha20-Poly1305 selado com dados do cabeçalho | Só o cofre dono decifra; outro cofre ou byte alterado é recusado sem gastar tentativa. |
| Diagnóstico `.diag` | X25519 + ChaCha20-Poly1305 | Registros só com números; só o cofre aberto lê. |

Todo nonce é aleatório e novo a cada gravação. Senhas com acento funcionam em qualquer forma de Unicode (NFC/NFD/NFKC), gastando uma só tentativa.

### 5.2 Formato do arquivo (`COFRE05`)

```
┌──────────────── cabeçalho fixo (HEADER_FMT5) ────────────────────────────────────┐
│ MAGIC "COFRE05\0"(8) │ t │ m │ p │ max_tentativas │ modo │                       │
│ sal_senha(16) │ nonce_senha(12) │ embrulho_senha(48) │                            │
│ sal_chave(16) │ nonce_chave(12) │ embrulho_chave(48) │                           │
│ nonce_chacha(12) │ nonce_aes(12) │ checksum(8) │                                  │
├──────────────── contador (1 byte; fora do AAD) ──────────────────────────────────┤
│ tentativas restantes; conferido e decrementado antes de testar a senha            │
├──────────────── seção de fatores extras (incluída no AAD) ───────────────────────┤
│ flags: 0=nenhum │ 1=FIDO │ 2=computadores │ 3=FIDO + computadores                 │
│ FIDO: nº de chaves + sal + recuperação + [nome, credencial, nonce, embrulho]      │
│ PC: nº de PCs + sal + recuperação + [nome, ID, nonce, embrulho]                   │
├────────────────────── payload cifrado (AEAD) ─────────────────────────────────────┤
│ AES-256-GCM(ChaCha20-Poly1305(JSON {itens, meta, n, h} + padding em 4 KiB))        │
└───────────────────────────────────────────────────────────────────────────────────┘
```

`AAD` (dados associados autenticados) = cabeçalho completo + seção de fatores extras; o byte do contador fica de fora. O checksum é SHA-256 truncado dos bytes do cabeçalho sem o próprio checksum mais a seção de fatores. Esse checksum rápido detecta danos acidentais, mas **não é um MAC** e não substitui a autenticação AEAD. A seção sempre existe: a flag indica se há FIDO, computadores autorizados, ambos ou nenhum. O modo S mantém os campos de chave de acesso preenchidos com ruído.

O cabeçalho identifica o formato, o modo e o limite de tentativas; FIDO e computadores são descritos na seção de fatores, não em um indicador do cabeçalho. O manifesto cifrado valida contagem e IDs dos registros; `meta` guarda dados internos, incluindo o histórico. O tamanho máximo aceito para um cofre é 200 MiB. Cofres de formatos anteriores (`COFRE01` a `COFRE04`) são abertos e **convertidos automaticamente** para o atual; a cópia de segurança da migração guarda o original.

### Fluxo de desbloqueio e tentativas

```text
ler cabeçalho + checksum
        │
        ├─ arquivo inválido/danificado ─► preservar arquivo; não contar tentativa
        ▼
validar fatores exigidos + computador autorizado + memória disponível
        │
        ├─ falta/erro de fator, PC não autorizado ou memória insuficiente
        │       └─► recusar antes da tentativa
        ▼
FIDO: pedir toque (se exigido) ──► cancelar/credencial não cadastrada: recusar sem contar
        │
        ▼
gravar contador decrementado (exceto modo consulta)
        │
        ├─ senha/chave errada ─► informar tentativas restantes
        │                         └─ chegou a zero ─► autodestruição (melhor esforço)
        ▼
abrir DEK ─► obter fator(es) extras ─► autenticar e decifrar os dados
        │
        ├─ dados não conferem ─► devolver tentativa; preservar e oferecer cópia
        └─ dados válidos ──────► carregar cofre; registrar abertura se gravável
```

No modo consulta não há gravação do contador nem salvamento. Cancelar o toque FIDO, faltar memória ou falhar a autorização do computador também não gasta tentativa. Erros de formato da chave de acesso têm a tolerância da interface descrita em [4.1](#41-formas-de-desbloquear); a verificação do conteúdo do código de recuperação e dos segredos FIDO/PC ocorre depois que a tentativa é gravada, então um código incorreto conta como tentativa errada. Corrupção do payload após os fatores corretos é tratada de forma diferente: devolve a tentativa e preserva o arquivo.

### 5.3 Camadas de segurança (visão organizada)

| Camada | O que é | Protege contra |
|---|---|---|
| **0. Meio físico** | Pendrive com **BitLocker To Go** (portátil) ou pasta **NTFS com ACL** (modo no computador) | Pendrive roubado ou perdido; outras contas do Windows |
| **1. Computador autorizado** *(opcional)* | Até 8 computadores, com reforço DPAPI | Arquivo do cofre levado para outro computador |
| **2. Senha mestra + chave de acesso** | Argon2id (1 GiB) + chave de 160 bits, modos E / OU / S | Força bruta; cópia do arquivo |
| **3. Chave FIDO2** *(opcional)* | Segredo da chave física entra na chave dos dados | Senha vazada; teclado espionado |
| **4. Código de recuperação** | Um código em papel que substitui só os fatores *extras* (FIDO e computador) | Perda da chave FIDO; troca de computador |
| **Execução** | Cifra em cascata, anti-depuração, bloqueio automático, autodestruição, memória zerada, arquivos de apoio ocultos, importação selada, teclado virtual | Espionagem, adulteração, uso por terceiros |

O código de recuperação **nunca** substitui a senha mestra nem a chave de acesso.

### 5.4 Autodestruição, e o que **não** a dispara

O cofre nasce com **3 tentativas erradas** (ajustável de 1 a 10 dentro do cofre, em `⋯ → Tentativas erradas`, exigindo a senha mestra). O contador é gravado **antes** de a senha ser testada, então desligar o PC no meio de uma tentativa não devolve a tentativa.

Ao esgotar as tentativas, o programa tenta **sobrescrever o arquivo 3 vezes com dados aleatórios (melhor esforço) e apagá-lo**, junto com as cópias (`.bak1`–`.bak5`), o `.danificado` e o registro de diagnóstico. Isso não garante a remoção física de blocos em SSDs ou pendrives com nivelamento de desgaste; a proteção contra leitura da cópia é o Argon2id, e a proteção do dispositivo é o BitLocker.

**Isto não destrói o cofre**, porque um byte ruim no pendrive não pode custar tudo que você guardou:

- arquivo **danificado** ou alterado: recusa abrir, **não gasta tentativa**, não apaga nada e oferece restaurar a cópia (o arquivo ruim fica como `cofre.dat.danificado`);
- **depurador** ligado ao programa compilado: o cofre não abre (ou fecha e apaga as chaves da memória), sem alterar o arquivo;
- cofre aberto em **outra janela** ou pendrive protegido: abre em modo consulta;
- erros de gravação, falta de memória e erros de leitura;
- um bit danificado no próprio nome do formato (`COFRE05` virando `COFRE01`): o caminho do formato antigo **nunca destrói** o arquivo.

Erros que também **não** gastam tentativa: chave de acesso mal digitada (formato inválido, nas 3 primeiras vezes da sessão; depois cada erro conta), fator faltando no modo E, chave FIDO cancelada ou ausente, computador fora da lista.

> ⚠️ **A autodestruição também é um risco para você.** Quem tiver o programa e o arquivo e errar a senha o número de vezes escolhido apaga o cofre e as cópias. Mantenha **sempre um backup seu fora do pendrive**.

### 5.5 Por que a força bruta não funciona

- **Pelo programa:** o cofre se apaga depois de 1 a 10 tentativas.
- **Com uma cópia do arquivo** (ataque offline, sem contador): quem protege é o **Argon2id**, que exige até 1 GiB de memória por tentativa. No modo E, o atacante também precisa adivinhar a chave de acesso de **160 bits** (2¹⁶⁰ ≈ 10⁴⁸ combinações). Com FIDO, precisa ainda do chip físico.
- **Custos medidos** (por tentativa ≈ 1,1 s no Alto e ≈ 5,9 s no Máximo, por núcleo): o tempo de busca depende do custo medido e do paralelismo real. Cada tentativa simultânea exige pelo menos 256 MiB (Alto) ou 1 GiB (Máximo), portanto não existe uma taxa fixa de tentativas por segundo para o Argon2id. **Senha fraca continua sendo o ponto frágil.**
- **Ataques com IA:** não existe atalho; uma IA não "adivinha" AES-256 nem ChaCha20, só ajudaria a chutar senhas fracas. Por isso o cofre recusa senhas fracas e recomenda frases longas.

---

## 6. Integridade e resiliência dos dados

O cofre foi desenhado para **não perder o que você guardou**, mesmo com pendrive barato, antivírus xereta ou queda de energia.

```text
alteração na memória
        │
        ▼
operações transacionais guardam o estado anterior (quando aplicável)
        │
        ▼
JSON + manifesto + preenchimento 4 KiB
        │
        ▼
ChaCha20-Poly1305 ─► AES-256-GCM (cabeçalho e fatores como AAD)
        │
        ▼
trava + conferir se o arquivo não mudou + renovar cópia quando necessário
        │
        ▼
.tmp → fsync → reler/conferir SHA-256 → os.replace
        ├─ sucesso ─► confirmar a gravação
        └─ falha ───► arquivo anterior continua intacto; transação desfaz a memória quando aplicável
```

| Mecanismo | O que faz |
|---|---|
| **Gravação atômica** | Todo arquivo gravado (cofre, cópias, backup) vai para um `.tmp` na mesma pasta (`cofre.dat.<PID>.tmp`, um por processo), é forçado ao disco (`fsync`), **relido e conferido por SHA-256** e só então trocado pelo definitivo (`os.replace`). No Windows tenta de novo por alguns segundos se o antivírus estiver segurando o arquivo. |
| **Falha no meio** | Pendrive arrancado, cheio ou protegido: o cofre anterior continua intacto, o `.tmp` é apagado e aparece uma mensagem clara (sem caminho de arquivo). |
| **Arquivo sumiu** | Se o `cofre.dat` desaparecer com o cofre aberto (pendrive removido ou trocado), o programa **recusa gravar**, em vez de criar um cofre novo em outro pendrive. |
| **Checksum do cabeçalho** | Distingue **arquivo danificado** (setor ruim) de **senha errada**. Danificado: não gasta tentativa e oferece restaurar a cópia. |
| **Manifesto interno** | Dentro dos dados cifrados vão a quantidade de itens e o SHA-256 dos IDs: se não conferir, o cofre recusa abrir em vez de carregar um estado parcial. |
| **5 cópias rotativas** | `.bak1` a `.bak5`, criptografadas como o cofre, renovadas por renomeação atômica. Se a mais nova estiver ilegível, a restauração usa a seguinte. |
| **Contador anti-reversão** | Cada gravação guarda, dentro dos dados cifrados, um contador crescente (`seq`). Cópia **mais nova** que o arquivo principal = o principal "voltou no tempo": aparece aviso e faixa vermelha. |
| **Trava entre janelas e gravações** | `cofre.dat.lock` (vale entre sessões do Windows e letras de unidade) impede duas janelas gravando; `cofre.dat.gravar.lock` serializa a conferência e a troca atômica entre processos. O programa recusa gravar por cima se o arquivo mudou desde que foi aberto (`ConflitoGravacao`). |
| **Transações** | Pessoas, grupos e operações compostas voltam ao estado anterior, na memória e no disco, se a gravação falhar. |
| **Diagnóstico cifrado** | Falhas do sistema viram registros de 77 bytes com números (código, `errno`, linha, versão, minuto), sem texto, caminho ou hash, em `cofre.dat.diag`. Cada registro é selado com a chave pública do cofre (dá para registrar com o cofre trancado); só o cofre aberto lê (`⋯ → Diagnóstico`). Máximo de 200 registros. |
| **Desgaste do pendrive** | Nada é reescrito a cada clique: a cópia `.bakN` é renovada no máximo 1 vez a cada 10 minutos e renomear gerações não grava dados. |
| **Política NTFS opcional** | Se existir um arquivo `exigir_ntfs.txt` ao lado do `.exe`, o cofre só abre em NTFS/ReFS. |

**Limite honesto do anti-reversão:** se o atacante trocar o `cofre.dat` **e** todas as cópias por um conjunto antigo, nada acusa (não há onde guardar um contador fora do pendrive sem deixar rastro no computador).

---

## 7. Proteções do Windows

| Proteção | O que faz |
|---|---|
| **Invisível a prints e gravações** | A janela aparece **preta** em capturas de tela, gravações, Teams, Discord, AnyDesk etc. (`SetWindowDisplayAffinity`, Windows 10 versão 2004 ou mais novo). |
| **Teclado virtual embaralhado** | As teclas **mudam de lugar a cada clique**: keyloggers não capturam e a posição dos cliques não revela nada. |
| **Bloqueio de cópia nos campos** | `Ctrl+C`, recortar, arrastar e botão direito desligados nos campos de senha. |
| **Área de transferência protegida** | Fora do Win+V e da nuvem, ignorada por monitores e limpa em 15 s. |
| **Bloqueio por inatividade** | 3 minutos por padrão (1 a 30 em `⋯ → Bloqueio automático`); ao bloquear, as chaves são apagadas da memória. |
| **Bloqueio ao sair do programa** | Se outro programa ficar em primeiro plano por 60 s, o cofre bloqueia e apaga as chaves da memória. Ao perder o foco, o conteúdo é coberto na hora. |
| **Bloqueio ao minimizar / Win+L / suspensão** | Minimizou, trancou. Win+L, troca de usuário, suspensão e hibernação fecham o cofre e descartam as chaves. |
| **Senhas reveladas por pouco tempo** | "Mostrar" esconde de novo em 20 s; o olho 👁 em 30 s. |
| **Memória trancada e anti-injeção** | Regras de acesso do processo (DACL) negam leitura/escrita/injeção por outros programas; bloqueia DLLs de ganchos globais, AppInit e LSPs. |
| **DLLs só confiáveis** | Nunca carrega DLL de rede ou de baixa integridade; prefere a System32, pré-carrega `wer`, `wtsapi32`, `dwmapi` e `webauthn` por caminho completo e ignora a pasta atual. |
| **Só fontes do sistema** | Fecha uma porta clássica de ataque (falhas em arquivos de fonte). |
| **Caixas de erro do Windows** | `SetErrorMode` suprime algumas caixas de diálogo do processo. Isso **não garante** que o Windows deixe de gerar relatórios ou dumps de falha; BitLocker e as políticas do Windows continuam importantes. |
| **Detector de ferramentas espiãs** | Se um leitor de memória ou depurador conhecido (x64dbg, Cheat Engine, Process Hacker, ProcDump…) estiver aberto, o cofre **não abre**; se aparecer com o cofre aberto, **bloqueia na hora**. Nada é apagado. |
| **Aviso de acesso remoto** | Área de Trabalho Remota, AnyDesk, TeamViewer, RustDesk etc. disparam um aviso antes de abrir. |
| **Aviso de hibernação** | Se a hibernação estiver ligada, o programa avisa (o Windows grava a RAM em `hiberfil.sys`). |
| **Arquivos de apoio ocultos** | O cofre e as cópias ficam com os atributos Oculto + Sistema + Somente leitura o tempo todo, liberados só no instante de cada gravação, inclusive se der erro. |
| **Pasta temporária privada** | O programa se descompacta ao lado dele (`CofreSenhas_em_uso_...`, `.tmp_cofre`), apagada ao fechar: nada vai para o `%TEMP%` do Windows. |

Cada proteção é independente: se alguma versão do Windows recusar uma delas, ela é pulada e o cofre continua funcionando. A tela de desbloqueio mostra quais ficaram ativas. Rodando o `.py` solto (sem compilar), o programa não esconde arquivos nem detecta depurador do mesmo modo que o `.exe`.

---

## 8. Modelo de ameaças e limites

Transparência faz parte da segurança. O quadro abaixo resume o [`documentacao/MODELO_DE_AMEACAS.md`](documentacao/MODELO_DE_AMEACAS.md) (que traz a análise completa, adendo por adendo).

### 8.1 Quem pode atacar e o que acontece

| Atacante | Situação |
|---|---|
| **Ladrão do pendrive** (sem a senha) | **Defendido:** senha forte + chave de 160 bits + Argon2id; o BitLocker esconde até o arquivo. |
| **Quem tem acesso rápido ao pendrive** (minutos) | **Não defendido sem BitLocker:** pode trocar o `.exe` por uma versão que registra a senha. Defesa: BitLocker + SHA-256 em papel. |
| **Malware no seu usuário, cofre aberto** | **Parcial:** DACL, mitigações do Windows, cópia protegida. Não impede um malware determinado. |
| **Keylogger** | **Mitigado:** teclado virtual embaralhado e chave FIDO. Não vale contra captura de tela/mouse por malware com a janela aberta. |
| **Malware com administrador ou kernel** | **Não defendido.** |
| **Câmera / olhar por cima do ombro** | **Mitigado:** campos ocultos, revelação temporária, janela fora de capturas. Câmera filmando: não defendido. |
| **Coação física** | **Não defendido** (sem "senha de coação"). |
| **Cadeia de suprimentos do build** | **Mitigado:** versões e hashes fixos, pasta de compilação refeita a cada vez, hash do `.py` digitado por você e conferido 3 vezes. |
| **Recuperação forense em SSD/pendrive** | **Não defendido por software:** use BitLocker. |
| **Sabotagem** (errar a senha de propósito) | **Aceito:** é o que a autodestruição faz. Só um backup externo resolve. |

### 8.2 Limites que valem para qualquer gerenciador de senhas

- **O elo mais fraco é o computador onde você pluga o pendrive.** Num PC comprometido, nenhuma defesa de software vence. Com o cofre **fechado**, o arquivo continua ilegível.
- **Quem pegar o pendrive por alguns minutos** pode trocar o `CofreSenhas.exe`. A criptografia não protege contra isso. A defesa é **BitLocker To Go no pendrive inteiro (trate como obrigatório)** e anotar o **SHA-256 do `.exe` em papel**, conferindo à mão no menu `⋯ → Verificar integridade do programa`. Um `.exe` já trocado poderia mentir sobre o próprio hash, por isso a conferência é uma prova humana, não automática.
- **Perder a senha E a chave de acesso** (modo OU), ou **qualquer uma das duas** (modo E), significa **perder o cofre para sempre**. Não existe "esqueci minha senha": é isso que garante que ninguém mais abra.
- **Autodestruição não protege contra cópia do arquivo.** O contador fica fora da parte autenticada; quem copia o arquivo ataca offline, sem contador. Ali só o Argon2id + senha forte + chave de 160 bits protegem.
- **A autodestruição não é garantida em SSD e pendrive** (o nivelamento de desgaste pode manter blocos antigos fora do alcance do programa).
- **Backups e Cópias de Sombra do Volume (VSS) antigos** continuam abrindo com a senha e a chave que valiam quando foram feitos; contra eles não há contador, e só a senha forte protege.
- **Remover uma chave FIDO não troca o segredo interno dela.** Se a chave foi roubada (e não só perdida), troque também a senha mestra e gere nova chave de acesso.
- **Memória (melhor esforço, medido):** ao bloquear, o cofre sobrescreve com zeros as chaves, os textos ASCII dos itens e a memória livre do Python. Sobram textos não-ASCII, cópias internas do Tcl/Tk e o que o Windows já gravou em `pagefile.sys`/`hiberfil.sys`. Use BitLocker no C: e desligue a hibernação (`powercfg /h off`, como administrador).
- **Pendrive FAT32/exFAT** não guarda permissões de arquivo: o programa e o instalador alertam e exigem confirmação.
- **Arquivos ocultos** são discrição, não controle de acesso: quem ligar "mostrar arquivos ocultos" os vê.

---

## 9. Requisitos

- **Windows 10 (versão 2004 ou mais nova) ou Windows 11 x64.** Em Windows 11 ARM64, o instalador usa Python e executável x64 sob emulação; build nativo ARM64 não é suportado porque não há wheel Windows ARM64 corrigido de `cryptography`.
- **Python 3.11, 3.12 ou 3.13 x64.** Se faltar, o instalador baixa e instala o 3.13 com SHA-256 e assinatura da Python Software Foundation conferidos.
- **Espaço livre:** mais de 3 GB no destino durante a compilação (o instalador confere), e de preferência 2 GB ou mais de memória livre.
- **Para FIDO2:** Windows 10 1903+ e uma chave FIDO2 com **hmac-secret/PRF** e **PIN configurado** (ex.: YubiKey 5, Feitian ePass FIDO2).
- **Recomendado:** pendrive NTFS com **BitLocker To Go**.
- **Criptografia:** `cryptography==50.0.2` é a versão fixa em `requirements.txt`, na entrada `requirements-test-direct.in`, no lock `requirements-test-lock.txt` e no instalador.
- **Internet:** use-a uma vez para preparar `pacotes\`; depois, instalação e dependências de teste usam o conteúdo local. A bateria completa do Windows consulta a base atual do `pip-audit` online por padrão (use `rodar_todos_windows.bat OFFLINE` para pular essa consulta); a checagem opcional de vazamentos também exige rede.

---

## 10. Instalação

### 10.1 Baixar o projeto

```powershell
git clone <URL_DO_REPOSITORIO>
cd projeto-cofre-offline
```

Ou use **Code → Download ZIP** no GitHub e extraia numa pasta.

### 10.2 Rodar o instalador

Dê dois cliques em **`1 - INSTALAR O COFRE - compila e instala.bat`**. Ele confere os arquivos, informa se vai trabalhar em modo ONLINE ou OFFLINE, mostra os SHA-256 de `cofre_senhas.py` e `icones_marcas.py` e o hash combinado, grava um log da execução em `logs_de_compilacao\` e chama o `instalar_cofre.ps1`. Aceita a letra do pendrive como argumento (`... H`).

Se o Windows bloquear scripts, o `.bat` já usa `-ExecutionPolicy Bypass` **só para aquela execução**, sem mudar a política do computador. Também dá para rodar direto:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\instalar_cofre.ps1
```

### 10.3 O que o instalador pergunta e faz

O instalador **pergunta primeiro** qual é o seu uso:

| Modo | Onde fica | Observações |
|---|---|---|
| **1. Portátil** (recomendado) | Num pendrive. Compilação, temporários, programa e cofre ficam **todos no pendrive**; nada vai para o disco do Windows. | Ideal com BitLocker To Go. Alerta vermelho se o pendrive for FAT32/exFAT; pendrive trancado (BitLocker) é avisado; SSD portátil só é aceito digitando `SIM`. |
| **2. No computador** | Numa pasta que você escolher (nunca dentro de Downloads). | Remove a herança de permissões e deixa **só a sua conta e o SISTEMA** com acesso (`icacls`). Não cria atalho nem item no Menu Iniciar. |

Depois, são 5 etapas explicadas na tela, com barra de progresso e "Etapa N de 5":

0. **Destino:** pergunta a letra do pendrive (sugere H:) e recusa o disco do Windows. Se já existe cofre no destino, pergunta se mantém (padrão) ou apaga tudo (exige digitar `APAGAR`; só alcança `cofre.dat*` e o registro, nunca o `.exe`).
1. **Conferência do programa:** usa `cofre_senhas.py` e `icones_marcas.py` ao lado do instalador, mostra os SHA-256 individuais e um hash combinado, e **exige que você digite os 16 primeiros caracteres do combinado**. É a única etapa que nunca aceita ENTER: é a defesa central contra arquivos trocados. Os dois hashes são recalculados após a cópia, antes dos testes e imediatamente antes de compilar; as cópias ficam somente leitura.
2. **Python:** verifica e instala se faltar (winget ou instalador oficial assinado), sempre x64; em Windows 11 ARM64 roda por emulação.
3. **Bibliotecas:** instala em **versões fixas e com hash** (`pip --require-hashes`), num ambiente virtual novo e isolado (`_cb\venv`). Variáveis `PYTHON*`, `PIP_*`, `NUITKA_*` e `CC` do seu ambiente são limpas, o `pip` roda com `--isolated` e a compilação usa `python -I`. Qualquer arquivo diferente do esperado é recusado.
4. **Teste de criptografia:** cria, abre e destrói um cofre de teste.
5. **Compilação:** gera um único `CofreSenhas.exe` nativo com o Nuitka e o compilador Zig. O Nuitka usa seu analisador PE embutido para mapear DLLs, sem baixar o Dependency Walker nem aguardar confirmação interativa. A primeira compilação leva de 5 a 20 minutos; as seguintes são bem mais rápidas, e uma falha **não recomeça do zero**.

No fim, o instalador mostra o **SHA-256 do `.exe`** e uma tabela de tempo por etapa. **Anote o hash em papel**: é a única cópia confiável dele (o programa não grava mais esse valor em nenhum arquivo ao lado do `.exe`, porque um arquivo solto poderia ser trocado junto com ele).

### 10.4 Robustez do instalador

| Recurso | O que faz |
|---|---|
| **Cache que sobrevive** | `_cb_cache\` (oculta, no pendrive) guarda downloads (sempre re-conferidos por hash), caches do Zig e do Nuitka e o que já foi compilado. Se Nuitka, Zig, Python ou as opções mudaram, recomeça limpo. Apague a pasta para liberar espaço. |
| **Pasta de build descartável** | `_cb\` é apagada e refeita a cada vez: nenhum `.exe`, `zig.exe` ou módulo plantado ali entra na compilação. |
| **Retentativas** | Cada `pip install` tenta até 3 vezes; o Nuitka também (a 2ª continua com metade dos processos, a 3ª recomeça). O `.exe` de uma tentativa anterior é apagado antes de cada nova. |
| **Sinal de vida** | A cada 15 s mostra `[vivo]` com tempo, uso do processador e últimas linhas. Se ficar 10 minutos parado, avisa em vermelho. O QuickEdit do console é desligado (um clique na janela pausava a saída). |
| **Conferências prévias** | Espaço livre (>3 GB), memória livre (avisa se <2 GB) e velocidade de escrita do pendrive (avisa se <15 MB/s). |
| **Logs** | `logs_de_compilacao\compilar-*.log` (na raiz do projeto) e, no destino, `logs\instalacao-*.log` e `instalacao_detalhada.log` (resumo estruturado, sem caminhos nem nome de usuário). |
| **Limpeza em qualquer saída** | `try/finally` apaga `_cb`, restaura o console e grava o log, mesmo com erro ou `Ctrl+C`. |
| **Ajuste anti-antivírus** | O Nuitka instalado recebe um ajuste que desliga a criação de `scons-debug.bat` (antivírus como o Avast bloqueiam `.bat` e quebravam a compilação). |
| **Identidade do `.exe`** | Ícone próprio e dados de arquivo (produto, versão), o que também ajuda contra falso positivo. |
| **Assinatura digital (opcional, desligada)** | Com `COFRE_ASSINAR_SHA1` (impressão digital do certificado) e o `signtool.exe` do Windows SDK, assina o programa antes de calcular o hash; `COFRE_ASSINAR_TS` liga o carimbo de tempo. Certificado autoassinado **não** remove o alerta do SmartScreen. Não testado em Windows real. |

### 10.5 Instalar sem internet (pacotes offline)

Dê dois cliques em **`3 - BAIXAR PACOTES - so para instalar sem internet.bat`** enquanto houver internet. Além das bibliotecas, Nuitka e Zig do instalador, ele prepara em `pacotes\` o instalador oficial do Python 3.13, as ferramentas Python de teste, o módulo Pester e o instalador do Nmap. As dependências diretas estão em `requirements-test-direct.in`; os pacotes Python baixados seguem o lock com hashes `requirements-test-lock.txt`. Os arquivos baixados são listados em `pacotes\SHA256.txt`, e Python/Nmap/Pester também têm verificações de hash (Python ainda tem assinatura digital). Em um computador offline, copie o projeto **incluindo a pasta `pacotes\`**. O instalador usa o Python local empacotado se nenhum compatível estiver instalado; para rodar testes, instale o Python de `pacotes\` primeiro se necessário. Os binários de `pacotes\` são ignorados pelo Git por tamanho: uma clonagem sozinha não contém o wheelhouse.

### 10.6 Aviso "Editor desconhecido" do Windows (SmartScreen)

Na primeira vez que abrir o `.exe`, o Windows pode avisar "Editor desconhecido". É esperado: o programa é compilado por **você** e não tem assinatura digital paga; o Windows só avisa porque nunca viu esse arquivo antes. Clique em **Mais informações → Executar assim mesmo**. Se quiser certeza, confira o SHA-256 anotado em `⋯ → Verificar integridade do programa`. Se o Windows ou o antivírus bloquear de vez (sem a opção "Executar assim mesmo"), **não adicione exceção**: reinstale e confira o número.

> **Antivírus:** programas compilados novos às vezes são confundidos com ameaças. Se o seu antivírus bloquear, envie o arquivo como falso positivo ao fabricante ou libere **só o `CofreSenhas.exe`**, nunca pastas inteiras.

### 10.7 Onde ficam os dados e quais arquivos aparecem

Numa instalação portátil, o **`CofreSenhas.exe`** fica na raiz do pendrive. Se o instalador encontrar uma versão antiga em `H:\CofreSenhas`, o padrão (ENTER) instala o programa na raiz e mantém a pasta antiga intacta; os dados antigos não são movidos. Digite **1** para atualizar dentro da pasta antiga e continuar usando aquele cofre. O restante fica oculto e protegido:

| Arquivo / pasta | Para que serve |
|---|---|
| `cofre.dat` | **O cofre** (criptografado). Fica ao lado do `.exe` (na raiz em uma instalação nova no modo portátil). |
| `cofre.dat.bak1` … `.bak5` | Cópias automáticas rotativas (1 = mais nova). |
| `cofre.dat.lock` | Trava vazia entre janelas. Pode ficar lá; apagá-lo com o cofre fechado não causa nada. |
| `cofre.dat.gravar.lock` | Arquivo auxiliar de 1 byte; o sistema operacional mantém a trava só durante a confirmação da gravação. Pode permanecer ao lado do cofre, sem dados secretos. |
| `cofre.dat.diag` | Registro de diagnóstico cifrado (só números). |
| `cofre.dat.danificado` | O arquivo ruim, guardado quando o cofre recusou abrir por dano. |
| `cofre.dat.<PID>.tmp` | Temporário durante uma gravação (some sozinho). |
| `avisos_vistos.json` | Avisos informativos que você já viu (só o hash do texto). |
| `logs\`, `instalacao_detalhada.log` | Registros da instalação (na raiz do pendrive no modo portátil). |
| `CofreSenhas_em_uso_...`, `.tmp_cofre` | Pasta temporária privada, apagada ao fechar. |
| `exigir_ntfs.txt` | *(opcional, você cria)* Faz o cofre abrir só em NTFS/ReFS. |
| `_cb_cache\` | *(só no pendrive de instalação)* Cache do instalador. |

- O cofre é **portátil**: copiar o programa e o `cofre.dat` para outro PC funciona. A segurança vem da senha e da chave, não do computador (a menos que você ative *Computadores autorizados*).
- Se o cofre estiver no disco do Windows, a tela de desbloqueio avisa. Salvar backup, modelo de planilha ou a chave de acesso no disco do Windows pede confirmação.
- **Atualizar:** rode o instalador de novo; se encontrar uma instalação antiga em `H:\CofreSenhas`, o padrão (ENTER) instala o programa na raiz e mantém a pasta antiga intacta. Os cofres, backups e chaves antigos não são movidos; digite **1** para atualizar naquela pasta e continuar usando os dados existentes. A opção **3** apaga somente os arquivos antigos do programa após digitar `APAGAR`. Se já houver um executável no destino, também confirma antes de substituí-lo. **Desinstalar:** no modo portátil, apague os arquivos do cofre na raiz do pendrive; no modo computador, apague a pasta escolhida (não há registro, serviço nem atalho).

---

## 11. Primeiros passos

1. **Crie o cofre.** Recomendado: modo **Senha E chave de acesso** e blindagem **Máxima**. Use **Gerar…** para criar uma frase de 5 ou 6 palavras e acompanhe a análise de força.
2. **Guarde a chave de acesso.** Ela aparece **uma única vez**. Salve o `.key` em **outro** pendrive, longe do cofre, e **anote à mão** em papel.
3. *(Opcional)* **Cadastre a chave FIDO** pelo botão **Chave FIDO**: toque 3 vezes e digite o PIN da chave quando o Windows pedir. **Anote o código de recuperação** e cadastre também uma chave reserva.
4. *(Opcional)* **Autorize computadores** em `⋯ → Computadores autorizados` e anote o código de recuperação (aparece uma vez).
5. **Importe suas senhas** (`⋯ → Baixar modelo de planilha`, preencha, depois `⋯ → Importar planilha`), confira a prévia e deixe o cofre **apagar a planilha com segurança**.
6. **Rode Verificar senhas** e troque as fracas e as repetidas. Comece pelas de banco e e-mail.
7. **Faça backup** (`⋯ → Backup do cofre`) e guarde em outro lugar. Refaça depois de mudanças importantes.
8. **Anote o SHA-256 do `.exe`** (mostrado no fim da instalação) e guarde junto com o código de recuperação, em local seguro.
9. *(Se for usar em PC próprio)* Ative o BitLocker no C: e desligue a hibernação (`powercfg /h off`, como administrador).

---

## 12. Uso no dia a dia e atalhos

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

Clique com o botão direito em uma conta, pessoa ou grupo para o menu de contexto. O menu `⋯` está descrito na [seção 4.11](#411-o-menu--e-o-botão-).

---

## 13. Rodando direto do código-fonte e dependências

Só para desenvolvimento ou depuração. Para o cofre de verdade, use sempre o instalador (ele confere hashes, isola o ambiente e testa a criptografia antes de compilar).

```powershell
pip install -r requirements.txt
python cofre_senhas.py                      # cofre.dat ao lado do programa
python cofre_senhas.py E:\pasta\cofre.dat   # outro local
```

Versões exatas (todas fixas, com hash na instalação):

| Biblioteca | Versão | Para quê |
|---|---|---|
| `cryptography` | 50.0.2 | AES-GCM, ChaCha20-Poly1305, HKDF, X25519 |
| `argon2-cffi` / `argon2-cffi-bindings` | 25.1.0 / 26.1.0 | Argon2id |
| `fido2` | 2.2.1 | Chave de segurança FIDO2 (hmac-secret/PRF) |
| `openpyxl` / `et-xmlfile` | 3.1.5 / 2.0.0 | Leitura e geração de planilhas |
| `defusedxml` | 0.7.1 | XML seguro na importação |
| `cffi` / `pycparser` | 2.1.1 / 3.12 | Dependências indiretas |
| `nuitka` | 4.3.5 | *(só para compilar)* Python → C → `.exe` |
| `ziglang` | 0.16.0 | *(só para compilar)* compilador C |
| `ordered-set`, `zstandard`, `setuptools`, `wheel` | 4.1.0, 0.25.0, 84.2.1, 0.48.0 | *(só para compilar)* apoio do Nuitka |

O programa **não usa** `eval`, `exec`, `pickle` nem `shell=True`, não guarda segredo fixo no código e só abre conexão de rede na checagem opcional de vazamentos.

---

## 14. Testes automáticos

O projeto tem uma bateria grande de testes, organizada por assunto. Cada teste trabalha numa pasta temporária (**nunca toca no seu `cofre.dat`**), termina com `TODOS OK` e devolve código de saída 0 (sucesso) ou 1 (falha), o que permite usar em integração contínua.

### 14.1 As sete etapas

Os números **1 a 6** abaixo são a ordem de execução do BAT, não o prefixo das pastas. Por exemplo, a etapa 2 (instalador) e a etapa 3 (Windows nativo) usam arquivos da pasta `4_TESTE_so_no_windows/`; a pasta `6_TESTE_ferramentas_dos_testes/` guarda o executor e scripts auxiliares/de relatório, não uma bateria. Os resultados gerados ficam em `testes/resultados/`.

| Pasta | O que testa |
|---|---|
| `testes/1_TESTE_motor_do_cofre/` | O **motor**, sem janelas: criptografia e vetores de teste, formato, backup, migração de versões antigas, corrupção forçada, falha e queda de energia em cada `fsync`/`os.replace`, concorrência entre processos, permissões de gravação, esquema hostil de itens, importação e fuzzing de planilhas, qualidade da aleatoriedade, vazamento de memória, soak de 1.000 ciclos, cofre com 5.000 itens, ida e volta com texto aleatório e bits virados. Inclui `teste_propriedades_hypothesis.py` quando Hypothesis está disponível. |
| `testes/2_TESTE_telas_e_botoes/` | A **interface**: abre janelas e clica de verdade. Criar, editar, copiar, pessoas, dados bancários, importação, FIDO, alerta de tentativas, bloqueio por inatividade, teclado virtual, captura de tela, acessibilidade por teclado, janelas que aparecem prontas, nada cortado em 3 tamanhos, fluidez, cliques aleatórios ("macaco"), resiliência e soak. |
| `testes/3_TESTE_ataques_simulados/` | **Ataques simulados** (pentest): injeção, SSRF, força bruta/spraying, DoS, forense de memória, bypass de contador/autodestruição, engenharia reversa, fuzzing adversarial/Unicode, SAST (`bandit`), dependências (`pip-audit`), canal lateral de tempo, exfiltração pela rede, link simbólico, superfície do instalador e resíduos em disco. Relatório em `testes/3_TESTE_ataques_simulados/relatorio_pentest.md`. |
| `testes/4_TESTE_so_no_windows/` | O que só vale no **Windows real**: sintaxe e funções do instalador (Pester), atributos de arquivo, ACL, SMBIOS × PowerShell, DPAPI, computador autorizado de ponta a ponta, blindagens/DLLs, WebAuthn e Windows Sandbox limpo. |
| `testes/5_TESTE_ferramentas_externas/` | Ferramentas independentes do executável compilado: Bandit, pip-audit, Nmap local, PSScriptAnalyzer, busca de segredos, qualidade extra, SBOM, Hypothesis e verificação de integridade do repositório. O pytest é opcional no menu e repete as baterias 1 e 2. |
| `testes/6_TESTE_ferramentas_dos_testes/` | **Não são testes:** executores, ajudantes, limpeza, geradores de relatórios, cobertura e ponte para o `pytest`. |
| `testes/7_TESTE_de_compilacao/` | **Depois de compilar:** confere proteções PE com pefile, varre o executável com o Windows Defender e verifica as conexões do processo aberto. Sem executável, registra `[PULADO]`. |
| `testes/resultados/` | Relatórios individuais, resumos, SARIF e log. Os consolidados ficam separados em `testes/resultados/resultados completos/` (`RESULTADO COMPLETO.txt` e `resultado_rodar_todos_windows.txt`). A bateria nova limpa a anterior; não vai para o Git. |

### 14.2 Riscos cobertos

O [`PLANO_DE_TESTES.md`](testes/PLANO_DE_TESTES.md) organiza os testes por risco (ISO 25010 / ISTQB):

| Risco | Exemplo de teste |
|---|---|
| Perder o acesso aos dados | backup, transação, corrupção forçada |
| Corrupção ao salvar | queda de energia, gravação atômica, limites |
| Vazar segredo (arquivo, memória, área de transferência, tela) | vazamento de memória, objetos sensíveis no GC, captura de tela |
| Programa trocado no pendrive | integridade do próprio programa, teste do instalador |
| Força bruta / ataque offline | força bruta, autodestruição, spraying |
| Planilha maliciosa | importação, fuzzing, payloads hostis |
| Falha só no Windows | bateria `4_TESTE_so_no_windows` |

### 14.3 Como rodar

**No Windows (mais fácil):** primeiro rode **`3 - BAIXAR PACOTES - so para instalar sem internet.bat`** com internet para preparar os wheels das ferramentas; depois dê dois cliques em **`2 - TESTAR TUDO - roda todos os testes.bat`**. Ele executa as etapas 1 a 7: núcleo (incluindo Hypothesis), instalador, Windows nativo, interface, pentest, ferramentas externas e verificações pós-compilação. O pytest 03 fica fora porque repete as baterias 1 e 2. Compile o `CofreSenhas.exe` antes da etapa 7; sem executável ou processo aberto, o relatório registra `[PULADO]`. Para executar somente essa pasta, rode `testes\7_TESTE_de_compilacao\RODAR ESTA PASTA - testes de compilacao.bat`. Exemplo combinado: `2 - TESTAR TUDO - roda todos os testes.bat H OFFLINE POS-COMPILACAO` (o argumento POS-COMPILACAO é compatível, mas não é necessário). A etapa 6 consulta a base atual do `pip-audit` pela internet; `OFFLINE` pula essa consulta. Os resultados individuais ficam em `testes\resultados\`; os dois relatórios consolidados ficam em `testes\resultados\resultados completos\`: `RESULTADO COMPLETO.txt` reúne todos os arquivos individuais e `resultado_rodar_todos_windows.txt` reúne as etapas por bateria.

**Pela linha de comando:**

```powershell
python testes\6_TESTE_ferramentas_dos_testes\rodar_todos.py            # tudo (núcleo + interface)
python testes\6_TESTE_ferramentas_dos_testes\rodar_todos.py --rapido   # só o núcleo, sem janelas
python testes\6_TESTE_ferramentas_dos_testes\rodar_todos.py --so gui   # só a interface
python testes\6_TESTE_ferramentas_dos_testes\rodar_todos.py --filtro fido -v
python testes\6_TESTE_ferramentas_dos_testes\rodar_todos.py --so nucleo --filtro propriedades_hypothesis -v
```

Para a ponte opcional do pytest, use `testes\5_TESTE_ferramentas_externas\03_PYTEST_PROJETO.bat`; ela mantém os caches em `testes\CACHE\` e os limpa ao terminar. Cada `teste_*.py` vira um caso; ausência de Hypothesis aparece como `SKIPPED`. No Linux sem tela, a interface roda dentro do `xvfb-run`.

### 14.4 Relatórios, depuração e boas maneiras

- **`log_depuracao.txt`**: saída **completa** (com tracebacks), horário, duração e comando de cada teste. É o arquivo para abrir quando algo falha.
- **`testes\resultados\resultados completos\RESULTADO COMPLETO.txt`**: conteúdo de todos os arquivos individuais `resultado_*.txt` da rodada, cada um com o nome do arquivo e separadores. Os arquivos individuais continuam disponíveis; a bateria completa do Windows gera novamente o TXT a cada execução.
- **`resumo_testes.md` / `.json` / `resultados.sarif`**: tabela legível, JSON comparável entre rodadas e SARIF só com as falhas.
- **Bateria nova substitui a antiga:** `limpar_resultados.py` apaga os resultados anteriores antes de começar, para nunca misturar "ontem" com "hoje". No fim, `limpar_artefatos_testes.py` apaga pastas temporárias órfãs.
- **Respeito ao seu PC:** por padrão, os testes rodam em prioridade baixa, esperam haver RAM livre e fazem pausa entre si. Para uma rodada autorizada em prioridade alta, defina `COFRE_TEST_HIGH_PRIORITY=1`; as janelas GUI continuam no segundo plano.
- **Manifestos de teste:** `requirements-test-direct.in` guarda as dependências diretas com versões exatas (`==`); `requirements-test-lock.txt` é o lock gerado, com dependências transitivas e hashes, usado por `pip --require-hashes`. São duas etapas intencionais do mesmo fluxo, não cópias redundantes. Depois de alterar o arquivo de dependências diretas, regenere o lock com o comando em `testes\5_TESTE_ferramentas_externas\LEIA-ME.txt` e atualize `pacotes\` com `3 - BAIXAR PACOTES`.
- **Ambiente e caches:** `testes\ambiente_virtual_ferramentas (NAO MEXER)` é um ambiente virtual persistente, ignorado pelo Git; não renomeie, mova ou apague: os atalhos dependem desse caminho. As baterias usam caches temporários em `testes\CACHE\<execução>` e os removem ao terminar; execuções diretas do programa ou Ruff também direcionam seus caches para subpastas de `testes\CACHE\`. Assim, não são criados `.hypothesis` nem `.ruff_cache` na raiz. Relatórios em `testes\resultados\` são mantidos.
- **Ferramentas de teste:** o lock fixa versões exatas. Dependências de runtime e ferramentas são instaladas em ambiente virtual local a partir de `pacotes\`, sem acesso à rede. O pentest instala somente as bibliotecas essenciais do programa; ferramentas opcionais ausentes são puladas, sem impedir os demais testes. Pester também é carregado do pacote local. O Nmap vem como instalador local, mas requer instalação manual e pode solicitar privilégios/Npcap; sem ele, o teste registra `PULADO`. Relatórios ficam diretamente em `testes\resultados\`. Nmap verifica apenas `127.0.0.1`.
- **Testes do executável:** pefile e Defender só podem analisar um `CofreSenhas.exe` compilado; o teste de rede exige que esse executável esteja aberto. Baixar dependências não cria nem abre o programa; cada relatório individual explica o pré-requisito ausente.
- **Hypothesis:** `teste_propriedades_hypothesis.py` verifica ida e volta de cofres com dados gerados e entradas CSV hostis. O executor tenta instalá-lo do wheelhouse do núcleo quando disponível; se faltar, mostra `PULADO` com código 9, sem contar como aprovado nem como falha. Uma falha real do teste retorna código diferente e reprova a bateria. O atalho 12 permite rodá-lo isoladamente.
- **Auditoria de dependências:** a bateria completa `rodar_todos_windows.bat` define `COFRE_ONLINE_AUDIT=1` na etapa 6 e consulta a base atual do `pip-audit`. `requirements.txt` e o lock `requirements-test-lock.txt` são auditados sem resolução/instalação de pacotes. O SBOM CycloneDX usa `requirements.txt`. Sem internet, a consulta registra erro/alerta, não aprovação. Use `rodar_todos_windows.bat OFFLINE` para pular a consulta; ao executar os BATs de auditoria separadamente, defina `COFRE_ONLINE_AUDIT=1` para habilitá-la.
- **Windows:** o executor não ativa `-X dev`, pois essa opção pode travar alguns builds do Python no Windows; os testes continuam verificando seus resultados e códigos de saída.
- **Cobertura de código:** `cobertura_codigo_windows.bat` mede quais linhas e ramificações de `cofre_senhas.py` os testes executam e lista as faixas de `except`/`raise` sem teste. Gera `cobertura_codigo.txt`, `cobertura_codigo.json` e `cobertura_html.zip` diretamente em `testes\resultados\` (sem subpastas persistentes). Fica fora do "Testar Tudo" porque é lenta. A medição de 16/11, no Linux e sem interface, foi de **32,1%** (a maior parte do arquivo é interface; o total sobe com `--gui`).
- **Soak:** o do núcleo faz 1.000 ciclos (~13 s) e o da interface 60 por padrão (`COFRE_SOAK_CICLOS=1000` para a corrida longa). Achado registrado: a memória do Python na interface cresce cerca de 12 KiB por ciclo de desbloquear/bloquear, sem sobrar chaves nem instâncias do cofre.
- **Antes de entregar uma versão:** rode tudo sem nenhum `FALHOU`, rode o `TESTAR TUDO` no Windows e instale e abra o `.exe` de verdade (criar item, fechar, reabrir).

Leia [`testes/COMO_RODAR_OS_TESTES.md`](testes/COMO_RODAR_OS_TESTES.md) para o passo a passo completo.

---

## 15. Ferramentas opcionais do Windows

A pasta `ferramentas_windows_opcionais/` traz scripts **independentes do cofre** para conferir e reforçar o PC. Cada atalho numerado diz o efeito no nome, e os `.ps1` ficam na subpasta `_scripts_internos_nao_mexer`. Leia cada um antes de rodar; todos pedem administrador.

| Atalho | O que faz | Altera o PC? |
|---|---|---|
| `1 - VERIFICAR a seguranca do Windows - so le, nao altera` | Relatório de antivírus, atualizações, firewall, SMBv1, acesso remoto, UAC, SmartScreen, contas Convidado/Administrador, TPM, Secure Boot, Integridade da memória (HVCI), Credential Guard, proteção LSA, histórico da área de transferência e teclados conectados. Salva `relatorio_seguranca.txt` na Área de Trabalho. | **Não**, só lê |
| `2 - APLICAR ajustes de seguranca do Windows - altera o Windows` | Cria um **ponto de restauração**; desliga a reprodução automática de pendrives e o histórico da área de transferência; abre a tela da Integridade da memória; mostra o modelo da placa-mãe para o Secure Boot. Mantém o antivírus que você já usa. | **Sim** |
| `3 - DESFAZER os ajustes de seguranca` | Desfaz os ajustes do item 2. | **Sim** |
| `4 - PROCURAR rootkit no nucleo do Windows - so le` | Procura drivers sem assinatura ou de fabricante desconhecido, em pastas estranhas, e confere a inicialização (`testsigning`, `nointegritychecks`, depurador de kernel). Salva `relatorio_nucleo.txt`. | **Não**, só lê |

---

## 16. Estrutura do repositório

```
projeto-cofre-offline/
│
├── README.md                                     # guia principal: uso, dependências, testes e mapa do projeto
├── 1 - INSTALAR O COFRE - compila e instala.bat  # instalador: dois cliques
├── 2 - TESTAR TUDO - roda todos os testes.bat    # roda as etapas 1 a 7
├── 3 - BAIXAR PACOTES - so para instalar sem internet.bat # wheelhouse do cofre e das ferramentas de teste
├── baixar_pacotes_offline.ps1 # prepara Python, dependencias de teste, Pester e Nmap
├── ENVIAR PRO GITHUB.bat  # atalho de conveniência: git add + commit + push
│
├── cofre_senhas.py        # núcleo criptográfico e interface principal
├── icones_marcas.py       # marcas, ícones locais e autocompletar offline
├── instalar_cofre.ps1     # o instalador que o "1 - INSTALAR..." chama por trás
├── requirements.txt         # runtime + compilação
├── requirements-test-direct.in    # entradas diretas fixadas; fonte para gerar o lock de testes
├── requirements-test-lock.txt  # lock de teste completo, com dependências transitivas e hashes
├── ruff.toml              # mantém o cache Ruff em testes/CACHE
├── .gitignore
├── LICENSE                # licença de uso pessoal e estudo
├── SECURITY.md            # escopo de proteção e contato para relatos privados
├── .github/
│   └── workflows/
│       └── windows-tests.yml  # GitHub Actions (NÃO MOVER ESSE ARQUIVO)
│
├── documentacao/
│   ├── GUIA_TECNICO_DO_CODIGO.md     # mapa técnico para ler e manter a implementação
│   ├── MANUAL_COMPLETO.md           # manual técnico completo
│   ├── MODELO_DE_AMEACAS.md         # quem pode atacar, o que consegue, o que NÃO é defendido
│   └── HISTORICO_*                  # relatório de 13/11, lista de mudanças, SHA-256 do programa
│
├── testes/
│   ├── COMO_RODAR_OS_TESTES.md, PLANO_DE_TESTES.md
│   ├── ambiente_virtual_ferramentas (NAO MEXER)/ # ambiente persistente: não renomear, mover ou apagar
│   ├── 1_TESTE_motor_do_cofre/            # núcleo, sem janelas
│   ├── 2_TESTE_telas_e_botoes/            # interface (Tk)
│   ├── 3_TESTE_ataques_simulados/         # pentest
│   ├── 4_TESTE_so_no_windows/             # só no Windows real (A, B, C, D)
│   ├── 5_TESTE_ferramentas_externas/      # ferramentas gerais (sem depender do exe compilado)
│   ├── 6_TESTE_ferramentas_dos_testes/    # executores, relatórios, cobertura (não são testes)
│   ├── 7_TESTE_de_compilacao/             # verificações opcionais do executável compilado
│   ├── CACHE/                             # caches temporários durante os testes; removida ao terminar
│   └── resultados/                  # (não versionada) tudo que os testes geram
│
├── ferramentas_windows_opcionais/   # extras que cuidam do seu PC (não do cofre)
│
├── pacotes/               # wheelhouse local; binários ignorados pelo Git
└── logs_de_compilacao/    # (não versionada) um log por instalação
```

Este README é o único guia de entrada na raiz e explica os atalhos, arquivos e pastas para quem não é programador. Os manuais especializados em `documentacao/` e os guias em `testes/` continuam disponíveis para consulta detalhada. Cada pasta de testes tem um `INDICE.md` que explica **cada arquivo**; depois de criar, renomear ou apagar algo em `testes/`, atualize os índices com `python testes\6_TESTE_ferramentas_dos_testes\gerar_indices.py`.

O núcleo criptográfico e a interface principal ficam em `cofre_senhas.py`, organizado em seções. `icones_marcas.py` concentra as marcas, os ícones gerados localmente e as sugestões offline do campo Serviço; não baixa logos nem consulta a rede.

```text
cofre_senhas.py
├── início e proteções do processo
├── criptografia, formato, armazenamento e fatores do Windows
├── class Cofre                 ← estado, desbloqueio e persistência
├── campos e importação         ← validação e conversão de CSV/Excel
├── FIDO2
└── interface
    ├── tema e componentes
    └── class App               ← telas e ações; coordena a interface com Cofre
icones_marcas.py                ← MARCAS, ALIASES, ícones Pillow e autocompletar offline
```

As pastas numeradas de teste descrevem **assuntos**; a numeração do executor descreve **ordem de execução**. Por isso, a etapa 6 é a bateria de ferramentas externas, mas o executor fica na pasta `6_TESTE_ferramentas_dos_testes/`. A etapa 7 fica separada porque exige um executável já compilado.

Quem vai ler ou manter a implementação pode começar pelo [guia técnico do código](documentacao/GUIA_TECNICO_DO_CODIGO.md), que mapeia as responsabilidades e os fluxos principais sem exigir a leitura linear do arquivo inteiro.

---

## 17. Documentação detalhada

| Documento | Para que serve |
|---|---|
| `README.md` (este arquivo) | Guia único de entrada: instalação, uso, dependências, testes, estrutura do projeto e orientação para iniciantes. |
| [`documentacao/GUIA_TECNICO_DO_CODIGO.md`](documentacao/GUIA_TECNICO_DO_CODIGO.md) | Ponto de partida para quem vai ler ou manter o Python: mapa do arquivo, responsabilidades e fluxos de criação, abertura, gravação e importação. |
| [`documentacao/MANUAL_COMPLETO.md`](documentacao/MANUAL_COMPLETO.md) | Manual técnico completo: formato do arquivo, detalhes de cada proteção, instalador, tabela de todos os testes e perguntas frequentes. |
| [`documentacao/MODELO_DE_AMEACAS.md`](documentacao/MODELO_DE_AMEACAS.md) | Quem pode atacar, o que cada atacante consegue, onde cada recurso realmente ajuda, o que **não** é defendido e as sugestões avaliadas e recusadas (adendo por adendo). |
| [`documentacao/HISTORICO_lista_de_mudancas.md`](documentacao/HISTORICO_lista_de_mudancas.md) | O que mudou em cada rodada de desenvolvimento. |
| [`documentacao/HISTORICO_relatorio_final_de_13-11.md`](documentacao/HISTORICO_relatorio_final_de_13-11.md) | Retrato de 13/11/2026: resultados, red team e o que um atacante com ferramentas de engenharia reversa consegue. |
| [`documentacao/HISTORICO_sha256_do_programa.txt`](documentacao/HISTORICO_sha256_do_programa.txt) | Hashes SHA-256 de uma versão anterior dos arquivos (registro histórico). |
| [`testes/COMO_RODAR_OS_TESTES.md`](testes/COMO_RODAR_OS_TESTES.md) e [`testes/PLANO_DE_TESTES.md`](testes/PLANO_DE_TESTES.md) | Como rodar, status do Windows e o que os testes cobrem. |
| [`SECURITY.md`](SECURITY.md) | Limites de segurança e como relatar um problema sem expor dados reais. |
| [`.github/workflows/windows-tests.yml`](.github/workflows/windows-tests.yml) | Bateria automatizada em `windows-latest` a cada push e pull request. |
| `ferramentas_windows_opcionais/` e `pacotes/LEIA-ME.txt` | Instruções de cada extra e dos pacotes offline. |

---

## 18. Cuidados ao publicar no Git

O `.gitignore` já impede o envio de `cofre.dat` e qualquer `*.dat`, `*.danificado`, `*.pre-v5`, `*.tmp`, cópias `*.bak1`–`*.bak5`, `*.lock`, `*.diag`, `.tmp_cofre/`, arquivos de chave `*.key`, planilhas `*.xlsx`/`*.xlsm`/`*.csv`, o `CofreSenhas.exe`, as pastas de compilação (`_cb/`, `_cb_cache/`), os binários de `pacotes/`, logs, `testes/resultados/` e os relatórios salvos pelos scripts do Windows. `pacotes/LEIA-ME.txt` e `pacotes/SHA256.txt` ficam versionáveis.

Mesmo assim:

- **Nunca** faça commit do seu `cofre.dat`, da chave de acesso, do código de recuperação ou de planilhas com senhas. Antes de cada commit, confira com `git status` o que vai subir.
- O atalho `ENVIAR PRO GITHUB.bat` faz `git add .`, `commit` e `push` de uma vez: ele **só é seguro porque o `.gitignore` está correto**. Confira o `git status` antes de usá-lo com arquivos novos.
- Prefira um **repositório privado** para o seu fluxo pessoal. Publicar o código não enfraquece o cofre, porque a segurança está nas chaves e não no segredo do código.
- Para distribuir um programa compilado, publique também o **SHA-256** do `.exe`, para quem baixar poder conferir.
- O GitHub bloqueia o push se o e-mail do commit for privado (erro `GH007`). Use o e-mail `ID+usuario@users.noreply.github.com` mostrado em *Settings → Emails*.

---

## 19. Solução de problemas

| Sintoma | O que significa e o que fazer |
|---|---|
| *"A execução de scripts foi desabilitada neste sistema"* | Use o `1 - INSTALAR O COFRE...bat` (ele já usa `-ExecutionPolicy Bypass` só naquela execução). Se uma política de grupo (GPO) impedir até isso, instale em outro computador. |
| O instalador recusa o hash dos 16 caracteres | Nunca avance. Confira se `cofre_senhas.py` e `icones_marcas.py` são os que você baixou e se digitou o hash combinado informado por quem forneceu o projeto. Arquivos diferentes = abortar. |
| A compilação falhou ou foi interrompida | É só **rodar de novo**: o que já foi baixado e compilado fica no cache e é aproveitado. Veja `logs_de_compilacao\` e o `instalacao_detalhada.log` do destino. |
| A tela parece parada na compilação | A etapa "Onefile Payload" costuma ficar muda alguns minutos. O instalador mostra `[vivo]` a cada 15 s; só considere travado se avisar em vermelho (10 min sem atividade). |
| "Pouco espaço" na instalação | São necessários mais de 3 GB livres no destino. Apague a pasta `_cb_cache` se precisar liberar espaço. |
| O antivírus bloqueou o `.exe` ou o instalador | Libere só o `CofreSenhas.exe` (nunca pastas inteiras) ou envie como falso positivo. Se o bloqueio for total, reinstale e confira o SHA-256. |
| "Editor desconhecido" ao abrir | Esperado (programa sem assinatura paga). Veja a [seção 10.6](#106-aviso-editor-desconhecido-do-windows-smartscreen). |
| "O contador de tentativas está danificado ou zerado" | Pode ser duas janelas abrindo juntas. Feche a outra, aguarde e tente de novo. **Nada foi apagado.** Se persistir, o programa oferece restaurar a cópia. |
| O cofre abriu em **MODO CONSULTA** | Ou o pendrive está protegido contra gravação, ou o cofre já está aberto em outra janela. Feche a outra janela ou remova a proteção de gravação; no modo consulta você vê e copia, mas não altera. |
| "Arquivo danificado" ou oferta de restaurar cópia | O checksum não bateu (setor ruim). Nenhuma tentativa foi gasta. Aceite restaurar a cópia mais recente legível. |
| Faixa vermelha "possível reversão" | O `cofre.dat` está mais velho que uma cópia `.bak`. Se você restaurou uma cópia antiga de propósito, é normal e some na abertura seguinte. |
| Aviso de memória insuficiente ao abrir | O Argon2id precisa de memória física livre; o programa recusa sem gastar tentativa. Feche outros programas ou use a blindagem *Alta*. |
| Chave FIDO: "sem PIN" | Crie o PIN da chave nas Configurações do Windows. |
| Chave FIDO: "PIN bloqueado" | Só desbloqueia redefinindo a chave (o que **apaga** as credenciais dela). Use a segunda chave ou o **código de recuperação**; não insista no PIN. |
| A importação recusou a planilha | Por padrão só vale o modelo gerado pelo próprio cofre (`⋯ → Baixar modelo de planilha`), preenchido e salvo como `.xlsx`. Planilha de outro cofre, CSV ou modelo alterado são recusados. |
| O cofre bloqueou sozinho | Inatividade (padrão 3 min), minimizar, Win+L, suspensão, 60 s com outro programa em primeiro plano ou uma ferramenta espiã detectada. Nada é apagado; é só desbloquear de novo. |
| A cópia (Ctrl+C) não funciona nos campos de senha | De propósito. Use o botão **Copiar**. Se o Windows não conseguir a cópia protegida, o programa recusa copiar. |
| Um teste falhou | Abra `testes\resultados\log_depuracao.txt` (saída completa com tracebacks) e `resumo_testes.md`. Linhas `Traceback` em testes marcados `ok` são ruído do modo `-W error`, não falha. |

---

## 20. Perguntas frequentes

**Se roubarem meu pendrive, conseguem abrir?**
Não. Sem a senha e a chave de acesso (e a chave FIDO, se ativada), o `cofre.dat` é ruído aleatório. Com BitLocker no pendrive, o ladrão nem chega a ver o arquivo.

**E se eu esquecer a senha?**
No modo OU, a chave de acesso abre o cofre. No modo E, não há recuperação: é o preço de ninguém mais conseguir abrir. Guarde a chave e um backup em locais diferentes.

**Perdi a chave FIDO. E agora?**
Use o **código de recuperação** (anotado em papel) ou a chave reserva, e depois remova a chave perdida em **Chave FIDO**. Se ela foi roubada, troque também a senha mestra e gere nova chave de acesso.

**Posso usar em mais de um computador?**
Sim. Leve o programa e o `cofre.dat` juntos no pendrive. Se você ativou *Computadores autorizados*, só abre nos que estão na lista.

**Por que o `Ctrl+C` não funciona nos campos de senha?**
De propósito: impede que algo digitado vá parar na área de transferência sem você querer. Use o botão **Copiar**, que protege a cópia e a apaga em 15 s.

**Por que abrir demora alguns segundos?**
É o Argon2id trabalhando com até 1 GiB de memória. Essa demora é o que torna a força bruta inviável.

**O programa acessa a internet?**
Não, por conta própria. Há **uma** função opcional, só quando você pede: `⋯ → Verificar senhas → Checar vazamentos (online)` (veja [4.4](#44-avaliação-de-força-e-auditoria)). Fora isso, só o **instalador** baixa o Python e as bibliotecas (e nem isso, no modo offline).

**Apaguei sem querer o cofre depois de errar a senha. Dá para recuperar?**
Não pelo programa: a autodestruição sobrescreve o arquivo e as cópias. Só um backup seu, feito em outro lugar, resolve.

**Posso aceitar planilhas do Chrome ou do Samsung Pass?**
Por padrão não (só o modelo gerado pelo próprio cofre). Para aceitar, mude `IMPORTAR_SOMENTE_COM_SELO = False` no topo do `cofre_senhas.py` e recompile, sabendo que isso reduz a proteção da importação.

**Mais de uma pessoa pode usar o mesmo cofre?**
Pode guardar as senhas de várias pessoas (campo *Pessoa*), mas todas abrem com a mesma senha mestra. Duas janelas ao mesmo tempo: a segunda abre em modo consulta.

**Funciona em macOS, Linux ou celular?**
O programa e as proteções são para Windows. Os testes do motor também rodam em Linux, mas isso é para desenvolvimento, não para uso.

**Preciso confiar no `.exe` de alguém?**
Não: você compila o seu, a partir dos fontes `cofre_senhas.py` e `icones_marcas.py`, que pode ler, com bibliotecas de versão e hash fixos.

---

## 21. Glossário

| Termo | Em português simples |
|---|---|
| **Argon2id** | Método que transforma a senha mestra numa chave de forma propositalmente lenta e gulosa em memória, para tornar inviável testar bilhões de senhas. |
| **AES-256-GCM / ChaCha20-Poly1305** | As duas cifras que embaralham os dados. O cofre usa uma dentro da outra. |
| **DEK** | Chave interna aleatória que de fato cifra os dados; a senha só "embrulha" essa chave. |
| **HKDF** | Método de derivar várias chaves independentes a partir de um segredo. |
| **FIDO2 / hmac-secret (PRF)** | Padrão de chaves físicas (YubiKey etc.). O cofre usa o segredo que a chave devolve como mais um fator. |
| **BitLocker To Go** | Criptografia do Windows para o pendrive inteiro. Protege programa e cofre contra quem pegar o pendrive. |
| **ACL / icacls** | Permissões de arquivo do Windows (quem pode ler/alterar uma pasta). |
| **DPAPI** | Cofre interno do Windows que prende um segredo à sua conta de usuário. |
| **SHA-256** | "Impressão digital" de um arquivo: se mudar um bit, o número muda por completo. |
| **AAD** | Dados que não são secretos mas são autenticados: se forem alterados, a abertura falha. |
| **k-anonymity** | Técnica da checagem de vazamentos: só os 5 primeiros caracteres do hash saem do computador. |
| **Nuitka / Zig** | Ferramentas que compilam o programa Python em um `.exe` nativo. |
| **SmartScreen** | Filtro do Windows que avisa sobre programas que ele ainda não conhece. |
| **VSS (Cópias de Sombra)** | Recurso do Windows que guarda versões antigas de arquivos num volume NTFS. |
| **Modo consulta** | Abertura somente leitura: vê e copia, não grava nada. |
| **Soak** | Teste de longa duração: repete o mesmo ciclo centenas de vezes para achar vazamentos. |
| **Pentest / red team** | Testes em que o cofre é atacado de propósito para provar que as defesas funcionam. |
| **SARIF** | Formato padrão de relatório de falhas, aceito por ferramentas de revisão de código. |

---

## 22. Decisões de projeto (o que foi adotado e o que não)

**Adotado de propósito:**

- **Um executável só para uso**; os fontes auditáveis são `cofre_senhas.py` e `icones_marcas.py`, conferidos individualmente e por hash combinado.
- **Compilar na sua máquina**, com versões e hashes fixos, em vez de distribuir um `.exe`.
- **Compilação e temporários no pendrive**, nunca no disco do Windows (preferência por segurança em vez de velocidade).
- **Nada fora do `.exe`:** sem `.bat` nem `.sha256` ao lado dele, porque um arquivo solto poderia ser trocado junto.
- **Sem registro, serviço, tarefa, atalho, menu de contexto, protocolo de URL ou pedido de administrador** (um teste garante que continue assim).
- **Só chave FIDO física**, sem biometria (Windows Hello removido).
- **Autodestruição só por tentativas de senha**, nunca por arquivo danificado ou depurador (um byte ruim não pode custar o cofre).
- **Importação selada por padrão**, para não ler planilhas hostis.
- **Código de recuperação persistente** (vale até ser renovado), e só para os fatores extras.

**Avaliado e não adotado** (detalhes em `documentacao/MODELO_DE_AMEACAS.md`):

- Ofuscadores comerciais (PyArmor, VMProtect, Themida), `.pyc` separados, `--lto=yes`, anti-debug mais agressivo, ofuscação extra de strings e *reproducible builds*: não aumentam a segurança real e complicam a compilação.
- Detecção de sandbox/EDR e técnicas de evasão: fora do escopo de um cofre (cheiram a malware).
- `VirtualLock` (chegou a ser implementado e foi cancelado por decisão do usuário).
- MSI, serviços, extensão de navegador, versão mobile, "senha de coação".
- Códigos de recuperação de uso único.
- Teste de estresse simultâneo de todas as baterias (mascara a causa das falhas).

---

## 23. Status e honestidade do projeto

- A **Arca é um produto da Arca Sistemas**. Não passou por auditoria de segurança independente.
- A bateria completa mais recente foi em 2026-11-21, no mesmo Windows 11 Pro 10.0.26300 / Python 3.13.9 AMD64: 2.541 verificações `[OK]`, 6 `[PULADO]` (as verificações do `.exe` — pefile, Defender, conexões de rede e smoke visual — porque os scripts não localizaram o executável, que estava dentro de `testes/7_TESTE_de_compilacao`; o `_achar_exe.bat` agora procura nessa pasta e pergunta o caminho quando não acha) e 2 relatórios com falha/interrupção. Núcleo 60/60, pentest 18/18, teste nativo do Windows 39/39 e Pester do instalador 17/17; PSScriptAnalyzer terminou sem alertas. Pendências: a medida de desempenho de abrir/fechar "Novo item" (541 ms contra o limite antigo de 500 ms; o limite passou a 650 ms, com a justificativa no teste), a "qualidade extra" (Ruff, mypy, Radon, Vulture), que acusou 71 achados do Ruff e foi tratada depois: as 14 ocorrências de `raise` dentro de `except` sem `from` (B904) receberam `from None`, como o resto do código já faz, as duas chamadas de `urlopen` ganharam `noqa: S310` (o endereço HTTPS já é conferido antes) e as regras só de estilo (ponto e vírgula, nomes de uma letra, `lambda` atribuída, `%`, `zip` sem `strict`) foram ignoradas no `ruff.toml`, com o motivo comentado; mypy, Radon e Vulture continuam apenas informativos; falta repetir a bateria para confirmar, e as quatro sondas `python -X dev`, que continuam com `-1073741819`. Resultado: No-Go. A bateria anterior, de 2026-11-20, no mesmo ambiente, o consolidado registrou 2.344 verificações `[OK]`, 9 relatórios com falha/interrupção e zero testes marcados como `[PULADO]`. As quatro sondas `python -X dev` terminaram com violação de acesso `-1073741819` mesmo em comandos mínimos, sem carregar o Cofre; o defeito não foi localizado no programa, mas a causa exata entre o interpretador e o Windows não foi comprovada. PSScriptAnalyzer e qualidade extra também tiveram alertas. Esse resultado é No-Go. Alterações posteriores tiveram validações focadas (Pester 14/14, engenharia reversa e integridade dos pacotes), mas a bateria completa não foi repetida depois delas e a versão final ainda precisa ser validada com Python 3.13.17. A matriz detalhada está em [`testes/COMO_RODAR_OS_TESTES.md`](testes/COMO_RODAR_OS_TESTES.md#status-do-windows-e-versões).
- Não há evidência de execução no Windows Sandbox. Também seguem sem validação: instalação/compilação ponta a ponta no Windows 11 x64, build nativo ARM64 (não suportado), assinatura digital opcional do `.exe` e uso com uma **chave FIDO2/PRF física real**.
- A cobertura de código medida no Linux (motor + pentest, sem interface) foi de 32,1%; as faixas sem teste estão listadas por `cobertura_codigo_windows.bat`.
- Versões antigas do programa **não abrem** cofres com o fator *computador*; backups feitos antes de ativá-lo continuam abrindo em qualquer computador. Cofres de formatos anteriores (`COFRE01`–`COFRE04`) são convertidos automaticamente para o atual (`COFRE05`).
- Os achados reais encontrados pelos próprios testes (por exemplo: senha mestra curta aceita pelo núcleo, campo CSV gigante sem tratamento, item com PIN em lista derrubando a auditoria, link simbólico, vazamento de objetos gráficos no bloqueio/desbloqueio) foram corrigidos e registrados em `documentacao/HISTORICO_lista_de_mudancas.md` e `documentacao/MODELO_DE_AMEACAS.md`.

**Use por sua conta e risco. Mantenha sempre um backup do cofre, da chave de acesso e do código de recuperação em locais diferentes.**

---

## 24. Licença e aviso legal

### 24.1 Licença do código

**Licença: Uso Pessoal e Estudo** (texto completo no arquivo [`LICENSE`](LICENSE)). O código é **visível**, mas **não é software livre nem open source**.

| Você pode | Você NÃO pode sem autorização por escrito da Arca Sistemas |
|---|---|
| Ler, estudar e auditar o código | Vender, alugar ou cobrar pelo software ou por versões dele |
| Compilar e usar para uso **pessoal e não comercial** | Usar em empresa, órgão ou atividade que gere receita |
| Fazer backup e modificar **para você mesmo** | Redistribuir ou publicar o código, o `.exe` ou versões modificadas |
| Ver e fazer fork dentro do GitHub (termos da plataforma) | Remover a autoria ou dizer que a obra é sua |

Para **uso comercial, revenda ou redistribuição**, peça autorização à **Arca Sistemas** pelo canal oficial informado pela empresa. A autorização pode ser condicionada a pagamento.

### 24.2 Sem garantia

O software é fornecido **"como está"**, sem garantias de qualquer tipo, expressas ou implícitas, incluindo adequação a uma finalidade específica. O autor não se responsabiliza por perda de dados, perda de acesso ao cofre, acesso indevido por terceiros ou qualquer outro dano decorrente do uso.

### 24.3 Responsabilidade de quem usa

- A **autodestruição apaga o cofre e as cópias de forma irreversível**. Mantenha sempre um backup em outro lugar.
- **Perder a senha mestra ou a chave de acesso significa perder o cofre.** Não existe recuperação feita pelo autor.
- O projeto **não passou por auditoria independente** (veja a [seção 23](#23-status-e-honestidade-do-projeto)). Para dados cuja perda ou vazamento cause dano grave, não use este cofre como única proteção.
- Você é responsável por compilar, conferir o SHA-256 e guardar o programa e as chaves com cuidado.

### 24.4 Bibliotecas de terceiros

O cofre usa bibliotecas de terceiros (lista exata em `requirements.txt`: `cryptography`, `argon2-cffi`, `openpyxl`, `defusedxml`, `fido2`, `nuitka`, `ziglang` e outras). Para testes, `requirements-test-direct.in` lista as dependências diretas e `requirements-test-lock.txt` é o lock completo, com dependências transitivas e hashes, usado com `pip --require-hashes`. Cada biblioteca continua sob a **sua própria licença**, e a licença deste projeto não se aplica a elas. O preparador baixa pacotes Python dos repositórios oficiais; o instalador do cofre também confere hashes fixos. Consulte as licenças antes de redistribuir qualquer pacote compilado ou ferramenta.

### 24.5 Marcas e leis locais

- Windows, BitLocker, SmartScreen, YubiKey, Feitian, GitHub e outros nomes citados são marcas dos seus donos. Este projeto **não tem vínculo nem aprovação** de nenhum deles.
- O uso e a distribuição de software de criptografia podem ter regras em alguns países. Conferir a legislação local é responsabilidade de quem usa.

### 24.6 Autor e contato

**Titular e manutenção:** **Arca Sistemas**

**Reportar um problema de segurança:** prefira avisar a Arca Sistemas em particular pelo canal oficial antes de abrir uma issue pública com detalhes de uma vulnerabilidade.
