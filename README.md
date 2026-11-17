# 🔐 Cofre de Senhas (offline)

**Gerenciador de senhas 100% local para Windows.** Um único programa, sem nuvem, sem conta e sem internet, que guarda as suas senhas num arquivo criptografado (`cofre.dat`) e roda direto de um pendrive ou de uma pasta protegida do computador.

![Windows 10/11](https://img.shields.io/badge/Windows-10%20%2F%2011%20(64%20bits)-0078D6?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11%20%E2%80%93%203.13-3776AB?logo=python&logoColor=white)
![Offline](https://img.shields.io/badge/rede-nenhuma%20(salvo%20consulta%20opcional)-2ea44f)
![Criptografia](https://img.shields.io/badge/cripto-ChaCha20--Poly1305%20%2B%20AES--256--GCM-5a4fcf)
![Senha mestra](https://img.shields.io/badge/senha%20mestra-Argon2id%201%20GiB-5a4fcf)

> **Princípio do projeto:** a segurança não depende de o código ser secreto. Tudo aqui pode ser lido e auditado. O que protege os seus dados é a matemática: a senha mestra, a chave de acesso e, opcionalmente, uma chave física FIDO2. Sem elas, o arquivo do cofre é só ruído aleatório.

---

## Índice

1. [Visão geral](#1-visão-geral)
2. [Para quem é (e para quem não é)](#2-para-quem-é-e-para-quem-não-é)
3. [O que ele faz](#3-o-que-ele-faz)
4. [Como a segurança funciona](#4-como-a-segurança-funciona)
5. [Proteções do Windows](#5-proteções-do-windows)
6. [Limites: o que nenhum cofre consegue impedir](#6-limites-o-que-nenhum-cofre-consegue-impedir)
7. [Requisitos](#7-requisitos)
8. [Instalação passo a passo](#8-instalação-passo-a-passo)
9. [Primeiros passos](#9-primeiros-passos)
10. [Uso no dia a dia e atalhos](#10-uso-no-dia-a-dia-e-atalhos)
11. [Rodando direto do código-fonte](#11-rodando-direto-do-código-fonte)
12. [Testes automáticos](#12-testes-automáticos)
13. [Estrutura do repositório](#13-estrutura-do-repositório)
14. [Documentação detalhada](#14-documentação-detalhada)
15. [Cuidados ao publicar no Git](#15-cuidados-ao-publicar-no-git)
16. [Perguntas frequentes](#16-perguntas-frequentes)
17. [Glossário](#17-glossário)
18. [Status e honestidade do projeto](#18-status-e-honestidade-do-projeto)
19. [Licença e aviso legal](#19-licença-e-aviso-legal)

---

## 1. Visão geral

O **Cofre de Senhas** foi feito para quem quer guardar logins, senhas, PINs, chaves de API, códigos de recuperação e dados bancários **sem entregar nada para um serviço na nuvem**. Ele é:

| Característica | Como é |
|---|---|
| **Local** | Tudo fica num arquivo `cofre.dat`, ao lado do programa. Não há servidor, conta nem sincronização. |
| **Portátil** | Funciona num pendrive (recomendado, com BitLocker To Go) ou numa pasta do computador protegida por permissões do Windows. |
| **Um arquivo só** | O programa inteiro é o `cofre_senhas.py`, de propósito: fica mais fácil de auditar e de conferir pelo SHA-256. |
| **Compilado por você** | O instalador compila o `CofreSenhas.exe` no seu próprio computador, a partir de bibliotecas com versão e hash fixos. Você não baixa um `.exe` pronto de ninguém. |
| **Em português** | Interface escura no estilo Windows 11, com mensagens que explicam o que fazer, não só o que deu errado. |

Em uma frase: **é um cofre que só abre com o que você sabe (senha), o que você tem (chave de acesso e, opcionalmente, uma chave FIDO2) e, opcionalmente, o computador onde você autorizou.**

---

## 2. Para quem é (e para quem não é)

**É para você se:**

- quer um cofre de senhas **offline**, sob seu controle total, sem depender de empresa nenhuma;
- usa um pendrive e aceita ativar o **BitLocker To Go** nele;
- está disposto a guardar uma chave de acesso e um backup em locais separados;
- gosta de poder **ler e conferir** o que o programa faz.

**Não é para você se:**

- precisa de **sincronização automática** entre celular e computador (não existe versão mobile nem nuvem);
- precisa **preencher senhas automaticamente** no navegador (não há extensão de navegador);
- quer um programa **auditado por terceiros** ou com suporte comercial (veja [Status e honestidade](#18-status-e-honestidade-do-projeto));
- usa **macOS ou Linux** como sistema principal (o cofre é feito para Windows; os testes do motor também rodam em Linux, mas o programa e as proteções são para Windows).

---

## 3. O que ele faz

### 3.1 Formas de desbloquear

| Fator | O que é | Observações |
|---|---|---|
| **Senha mestra** | Mínimo de **14 caracteres**. Passa pelo Argon2id: cada tentativa custa 1 GiB de memória e alguns segundos. | Senhas só com números, sequências (`123456`, `qwerty`), senhas de listas vazadas e as que o medidor classifica como fracas são **recusadas**. |
| **Chave de acesso** | 160 bits aleatórios no formato `XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XX`. Os 2 últimos caracteres são de verificação: um erro de digitação é percebido **sem gastar tentativa**. | Aparece **uma única vez**, ao criar o cofre. Pode ser salva num arquivo `.key` (cifrado) ou anotada à mão. **Não é impressa.** |
| **Chave FIDO2** *(opcional)* | Chave física USB/NFC (YubiKey 5, Feitian ePass FIDO2…), com PIN e toque. | Aceita várias chaves (principal + reserva). Gera um **código de recuperação** em papel. Só chave física: **sem biometria**. |
| **Computador autorizado** *(opcional)* | O cofre só abre nos computadores da lista (até 8), reconhecidos pelo MachineGuid do Windows + UUID da placa-mãe. | Fator **a mais**. Em computador fora da lista, o cofre recusa **sem gastar tentativa**. Pode ter reforço com segredo local protegido pelo DPAPI. |

**Modos de desbloqueio**, escolhidos ao criar o cofre:

| Modo | Como funciona | Quando escolher |
|---|---|---|
| **Senha E chave de acesso** *(recomendado)* | Os dois fatores são obrigatórios. Quem descobrir só a senha, ou só a chave, não abre. | Uso normal, com mais segurança. |
| **Senha OU chave de acesso** | Qualquer um dos dois abre. A chave funciona como recuperação se você esquecer a senha. | Quando o medo de esquecer a senha é maior que o de vazá-la. |
| **Só senha mestra** | Não existe chave de acesso. | O jeito mais simples; a segurança vem só da senha longa + Argon2id. |

### 3.2 O que cada item guarda

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

**Pessoas:** um mesmo cofre guarda as senhas de várias pessoas (você, familiares), todas abertas pela mesma senha mestra. Os nomes das pessoas também ficam criptografados.

**Dados bancários:** qualquer item com número da conta e/ou agência **sempre** pede a senha mestra de novo para ser visto, copiado ou editado, mesmo com a "Proteção extra" geral desligada. A liberação dura 30 segundos.

**Proteção extra:** um ajuste único para o cofre inteiro (`⋯ → Segurança → Proteção extra`) que exige a senha mestra de novo para ver ou copiar qualquer senha.

### 3.3 Gerador de senhas

| Tipo | Tamanho | Uso |
|---|---|---|
| **Aleatória** | 8 a 64 caracteres, com números e símbolos opcionais | Contas de sites e apps |
| **Fácil de lembrar** | 3 a 10 palavras pronunciáveis | Senhas que você precisa digitar de cabeça |
| **PIN** | 4 a 12 dígitos | PINs óbvios (1234, 0000, 1212, anos…) são descartados |

O sorteio usa o gerador criptográfico do sistema (`secrets`). A força mostrada é **exata**, calculada pelo número de combinações possíveis.

### 3.4 Avaliação de força e auditoria

- **Nota e barra** (Muito fraca → Muito forte), com bits estimados e composição da senha.
- **Tempo médio para descobrir** em dois cenários: arquivo do cofre roubado (cerca de 1 milhão de tentativas por segundo contra o Argon2id) e senha vazada de um site com proteção fraca (cerca de 100 bilhões por segundo).
- A estimativa é **realista**: penaliza palavras comuns, senhas de listas vazadas, trocas óbvias (`P@ssw0rd`), sequências, repetições, anos e datas.
- **Verificar senhas** (menu `⋯`) audita o cofre todo e aponta senhas fracas, **repetidas** e PINs fáceis. Os itens com problema aparecem no filtro **⚠ Atenção**.
- **Checar vazamentos (online)** é a **única** função que usa a internet, e só quando você clica. Usa o Have I Been Pwned com *k-anonymity*: de cada senha saem pela rede apenas os 5 primeiros caracteres do SHA-1, nunca a senha nem o hash inteiro.

### 3.5 Importação de planilhas

- Lê Excel (`.xlsx`, `.xlsm`) e CSV, encontra o cabeçalho sozinho e entende nomes de colunas em português e inglês.
- Mostra uma **prévia** separando cada linha em *nova*, *igual (ignorada)* ou *com dados diferentes*.
- Avisa quando o Excel "comeu" o zero à esquerda de um PIN.
- Oferece **apagar a planilha com segurança** ao final (sobrescrita com dados aleatórios), porque ela guarda as senhas sem criptografia.
- **Quarentena antes do cofre:** confere os *magic bytes*, copia para uma pasta isolada, varre (macros, ActiveX, objetos embutidos, vínculos externos, DDE, fórmulas, zip-bomb), lê **só como valores** e sanitiza cada campo.
- **Importação segura (padrão):** o cofre só aceita a planilha **gerada por ele mesmo** (`⋯ → Baixar modelo de planilha`), que leva um selo HMAC ligado ao *seu* cofre. Planilhas comuns, CSV, modelos adulterados ou de outro cofre são recusados antes de ler qualquer dado. Para aceitar planilhas comuns, mude `IMPORTAR_SOMENTE_COM_SELO = False` no topo do código e recompile.

### 3.6 Cópia segura e impressão

- **Copiar** envia o texto para a área de transferência **fora** do histórico do Windows (Win+V) e da nuvem, marcado para ser ignorado por monitores, e **apaga sozinho em 15 segundos**. Se o Windows não conseguir a cópia protegida, o programa **recusa copiar** em vez de usar a área comum.
- Nos campos de senha, `Ctrl+C`, recortar, arrastar e o menu do botão direito ficam **bloqueados**; a cópia só acontece de propósito, pelo botão.
- O cofre **só imprime duas coisas**: a chave de acesso e o código de recuperação (as cópias de emergência), com a senha mestra pedida antes e nome genérico na fila (`Documento_Sistema`). Senhas e itens **nunca** são impressos.

### 3.7 Histórico e alerta de invasão

Cada abertura é registrada **dentro do próprio cofre, criptografada**, então um invasor não consegue apagar o rastro. Se alguém errou a senha desde a última vez que você abriu, aparece um **⚠ ALERTA DE SEGURANÇA** ao entrar. O histórico completo fica em `⋯ → Histórico de aberturas`.

### 3.8 Backup e cópias automáticas

- **Backup do cofre** (`⋯ → Backup do cofre`) pede e confere a chave de acesso antes de gerar a cópia, que continua criptografada.
- **5 cópias automáticas rotativas** (`cofre.dat.bak1` = mais nova … `.bak5` = mais antiga), no máximo uma nova a cada 10 minutos de uso. Se o arquivo principal ficar danificado, o programa oferece restaurar a cópia mais recente.
- Isso **não substitui** um backup seu em outro lugar.

### 3.9 Interface

- Tema escuro no estilo Windows 11, com todos os ícones desenhados pelo próprio programa (sem depender de fontes ou arquivos externos).
- Busca instantânea (`Ctrl+F`), lista que desenha só as linhas visíveis (6.000 contas rolam sem engasgar), painel de detalhes e quadro de status da proteção.
- **Ranking de proteção** (escudo na barra lateral): nota de 0 a 100 (Básica, Boa, Forte, Máxima) com botão **Ativar** no que falta.
- Teclado virtual embaralhado, olho 👁 para conferir a digitação (volta a esconder em 30 s) e aviso de Caps Lock.
- Funciona com zoom de 125% e 150% e em telas baixas (notebooks de 768 px), com barra de rolagem automática.
- Operações pesadas (Argon2id, abrir, criar, salvar) rodam fora da thread da janela: a tela continua respondendo.
- **Modo consulta:** se o pendrive estiver protegido contra gravação, ou se o cofre já estiver aberto em outra janela, o programa abre só para leitura (vê e copia, não altera nada).

---

## 4. Como a segurança funciona

### 4.1 Visão geral das chaves

```
  senha mestra ──Argon2id──► chave da senha ──┐
                                              ├─(modo E)─► chave combinada ──┐
  chave de acesso ──HKDF──► chave da chave ───┘                              │
  (160 bits)                                                                 ▼
                                        AES-256-GCM "embrulha" ──►  DEK (chave interna,
                                                                    256 bits aleatórios)
  chave FIDO2 ──hmac-secret/PRF──► segredo F ──HKDF(DEK ‖ F)──────────────────┤
  (opcional)                                                                 ▼
                                                                    chave dos dados
                                                                    │              │
                                                               HKDF │              │ HKDF
                                                                    ▼              ▼
                                              ChaCha20-Poly1305 ──► AES-256-GCM
                                               (camada interna)    (camada externa)
```

| Peça | Algoritmo | Detalhes |
|---|---|---|
| Chave interna (DEK) | Aleatória, 256 bits | Sorteada uma vez. Trocar a senha **reembrulha** e recifra tudo. |
| Senha → chave | **Argon2id** | Nível **Máxima**: 1 GiB de memória, 6 iterações. Nível **Alta**: 256 MiB, 4 iterações. Paralelismo 2, sal de 128 bits. |
| Chave de acesso → chave | **HKDF-SHA256** | 160 bits de entropia: não precisa de Argon2. |
| Dados | **ChaCha20-Poly1305 dentro de AES-256-GCM** | Duas cifras de famílias diferentes, com subchaves independentes. Uma falha futura em uma delas não expõe os dados. |
| Fator FIDO2 | Extensão **hmac-secret / PRF** | A chave física devolve um segredo que nunca sai do chip. |
| Tamanho do arquivo | Preenchimento em blocos de **4 KiB** | O tamanho não revela quantos itens existem. |
| Integridade | Cabeçalho e seção FIDO autenticados (AAD) | Qualquer alteração é detectada. |

Todo nonce é aleatório e novo a cada gravação. As gravações são **atômicas** (arquivo temporário, releitura conferida por SHA-256 e só então a troca), então queda de energia ou pendrive arrancado não corrompe o cofre.

### 4.2 Camadas de segurança (visão organizada)

| Camada | O que é | Protege contra |
|---|---|---|
| **0. Meio físico** | Pendrive com **BitLocker To Go** (portátil) ou pasta **NTFS com ACL** (modo no computador) | Pendrive roubado ou perdido; outras contas do Windows |
| **1. Computador autorizado** *(opcional)* | Até 8 computadores, com reforço DPAPI | Arquivo do cofre levado para outro computador |
| **2. Senha mestra + chave de acesso** | Argon2id (1 GiB) + chave de 160 bits, modos E / OU / S | Força bruta; cópia do arquivo |
| **3. Chave FIDO2** *(opcional)* | Segredo da chave física entra na chave dos dados | Senha vazada; teclado espionado |
| **4. Código de recuperação** | Um código em papel que substitui só os fatores *extras* (FIDO e computador) | Perda da chave FIDO; troca de computador |
| **Execução** | Cifra em cascata, anti-depuração, bloqueio automático, autodestruição, memória zerada, arquivos de apoio ocultos, importação selada, teclado virtual | Espionagem, adulteração, uso por terceiros |

O código de recuperação **nunca** substitui a senha mestra nem a chave de acesso.

### 4.3 Autodestruição, e o que **não** a dispara

O cofre nasce com **3 tentativas erradas** (ajustável de 1 a 10 dentro do cofre, em `⋯ → Tentativas erradas`, exigindo a senha mestra). O contador é gravado **antes** de a senha ser testada, então desligar o PC no meio de uma tentativa não devolve a tentativa.

Ao esgotar as tentativas, o programa **sobrescreve o arquivo 3 vezes com dados aleatórios e o apaga**, junto com as cópias (`.bak1`–`.bak5`), o `.danificado` e o registro de diagnóstico.

**Isto não destrói o cofre**, porque um byte ruim no pendrive não pode custar tudo que você guardou:

- arquivo **danificado** ou alterado: recusa abrir, **não gasta tentativa**, não apaga nada e oferece restaurar a cópia;
- **depurador** ligado ao programa compilado: o cofre não abre (ou fecha e apaga as chaves da memória), sem alterar o arquivo;
- cofre aberto em **outra janela** ou pendrive protegido: abre em modo consulta;
- erros de gravação, falta de memória e erros de leitura.

Erros que também **não** gastam tentativa: chave de acesso mal digitada (formato inválido), fator faltando no modo E, chave FIDO cancelada ou ausente.

> ⚠️ **A autodestruição também é um risco para você.** Quem tiver o programa e o arquivo e errar a senha o número de vezes escolhido apaga o cofre e as cópias. Mantenha **sempre um backup seu fora do pendrive**.

### 4.4 Por que a força bruta não funciona

- **Pelo programa:** o cofre se apaga depois de 1 a 10 tentativas.
- **Com uma cópia do arquivo** (ataque offline, sem contador): quem protege é o **Argon2id**, que exige 1 GiB de memória por tentativa (≈ 1,1 s no nível Alto e ≈ 5,9 s no Máximo, por núcleo). No modo E, o atacante também precisa adivinhar a chave de acesso de **160 bits** (2¹⁶⁰ ≈ 10⁴⁸ combinações). Com FIDO, precisa ainda do chip físico.
- **Senha fraca continua sendo o ponto frágil.** Por isso o cofre recusa senhas fracas e recomenda frases longas.
- **Ataques com IA:** não existe atalho; uma IA não "adivinha" AES-256 nem ChaCha20, só ajudaria a chutar senhas fracas.

---

## 5. Proteções do Windows

| Proteção | O que faz |
|---|---|
| **Invisível a prints e gravações** | A janela aparece **preta** em capturas de tela, gravações, Teams, Discord, AnyDesk etc. (Windows 10 versão 2004 ou mais novo). |
| **Teclado virtual embaralhado** | As teclas **mudam de lugar a cada clique**: keyloggers não capturam e a posição dos cliques não revela nada. |
| **Bloqueio de cópia nos campos** | `Ctrl+C`, recortar, arrastar e botão direito desligados nos campos de senha. |
| **Área de transferência protegida** | Fora do Win+V e da nuvem, ignorada por monitores e limpa em 15 s. |
| **Bloqueio por inatividade** | 3 minutos por padrão (1 a 30 em `⋯ → Bloqueio automático`). |
| **Bloqueio ao sair do programa** | Se outro programa ficar em primeiro plano por 60 s, o cofre bloqueia e apaga as chaves da memória. Ao perder o foco, o conteúdo é coberto na hora. |
| **Bloqueio ao minimizar / Win+L / suspensão** | Minimizou, trancou. Win+L, troca de usuário, suspensão e hibernação fecham o cofre e descartam as chaves. |
| **Senhas reveladas por pouco tempo** | "Mostrar" esconde de novo em 20 s; o olho 👁 em 30 s. |
| **Memória trancada e anti-injeção** | Regras de acesso do processo negam leitura/escrita/injeção por outros programas; bloqueia DLLs de ganchos globais, AppInit e LSPs. |
| **DLLs só confiáveis** | Nunca carrega DLL de rede ou de baixa integridade; prefere a System32 e ignora a pasta atual. |
| **Só fontes do sistema** | Fecha uma porta clássica de ataque (falhas em arquivos de fonte). |
| **Sem cópia da memória em travamento** | O Windows não grava a memória do cofre em disco se ele travar. |
| **Detector de ferramentas espiãs** | Se um leitor de memória ou depurador conhecido (x64dbg, Cheat Engine, Process Hacker, ProcDump…) estiver aberto, o cofre **não abre**; se aparecer com o cofre aberto, **bloqueia na hora**. Nada é apagado. |
| **Aviso de acesso remoto** | Área de Trabalho Remota, AnyDesk, TeamViewer, RustDesk etc. disparam um aviso antes de abrir. |
| **Arquivos de apoio ocultos** | O cofre e as cópias ficam com os atributos Oculto + Sistema + Somente leitura o tempo todo, liberados só no instante de cada gravação. |

Cada proteção é independente: se alguma versão do Windows recusar uma delas, ela é pulada e o cofre continua funcionando. A tela de desbloqueio mostra quais ficaram ativas.

---

## 6. Limites: o que nenhum cofre consegue impedir

Transparência faz parte da segurança. Estes limites valem para **qualquer** gerenciador de senhas:

- **Malware com administrador ou rootkit de núcleo, com o cofre aberto,** tem mais poder que o cofre: pode ler a memória ou capturar o teclado. Com o cofre **fechado**, o arquivo continua ilegível. Defesas: antivírus atualizado, Integridade da memória do Windows, chave FIDO e teclado virtual.
- **O elo mais fraco é o computador onde você pluga o pendrive.** Num PC comprometido, nenhuma defesa de software vence.
- **Quem pegar o pendrive por alguns minutos** pode trocar o `CofreSenhas.exe` por uma versão que registra a senha. A criptografia não protege contra isso. A defesa é **BitLocker To Go no pendrive inteiro (trate como obrigatório)** e anotar o **SHA-256 do `.exe` em papel**, conferindo à mão no menu `⋯ → Verificar integridade do programa`.
- **Perder a senha E a chave de acesso** (modo OU), ou **qualquer uma das duas** (modo E), significa **perder o cofre para sempre**. Não existe "esqueci minha senha": é isso que garante que ninguém mais abra.
- **Autodestruição não protege contra cópia do arquivo.** O contador fica fora da parte autenticada; quem copia o arquivo ataca offline, sem contador. Ali só o Argon2id + senha forte + chave de 160 bits protegem.
- **A autodestruição não é garantida em SSD e pendrive** (o nivelamento de desgaste pode manter blocos antigos fora do alcance do programa). Use BitLocker.
- **Backups antigos** continuam abrindo com a senha e a chave que valiam quando foram feitos.
- **Remover uma chave FIDO não troca o segredo interno dela.** Se a chave foi roubada (e não só perdida), troque também a senha mestra e gere nova chave de acesso.
- **Memória (melhor esforço, medido):** o Python não oferece apagar textos; ao bloquear, o cofre sobrescreve com zeros as chaves, os textos ASCII dos itens e a memória livre do Python. Sobram textos não-ASCII, cópias internas do Tcl/Tk e o que o Windows já gravou em `pagefile.sys`/`hiberfil.sys`. Use BitLocker no C: e desligue a hibernação (`powercfg /h off`, como administrador).
- **Pendrive FAT32/exFAT** não guarda permissões de arquivo: o programa e o instalador alertam e exigem confirmação.
- **Coação física** (obrigar você a entregar senha e chave) não é defendida: não há "senha de coação".

A análise completa, atacante por atacante, está em [`docs/MODELO_DE_AMEACAS.md`](docs/MODELO_DE_AMEACAS.md).

---

## 7. Requisitos

- **Windows 10 (versão 2004 ou mais nova) ou Windows 11, 64 bits**, x64 ou ARM64 (o instalador detecta a arquitetura).
- **Python 3.11, 3.12 ou 3.13.** Se faltar, o instalador baixa e instala o 3.13 com SHA-256 e assinatura da Python Software Foundation conferidos.
- **Espaço livre:** mais de 3 GB no destino durante a compilação (o instalador confere), e de preferência 2 GB ou mais de memória livre.
- **Para FIDO2:** Windows 10 1903+ e uma chave FIDO2 com **hmac-secret/PRF** e **PIN configurado** (ex.: YubiKey 5, Feitian ePass FIDO2).
- **Recomendado:** pendrive NTFS com **BitLocker To Go**.

---

## 8. Instalação passo a passo

### 8.1 Baixar o projeto

```powershell
git clone https://github.com/ebj355/projeto-cofre-offline.git
cd projeto-cofre-offline
```

Ou use **Code → Download ZIP** no GitHub e extraia numa pasta.

### 8.2 Rodar o instalador

Dê dois cliques em **`1 - INSTALAR O COFRE - compila e instala.bat`**. Ele confere os arquivos, informa se vai trabalhar em modo ONLINE ou OFFLINE, mostra o SHA-256 do `cofre_senhas.py`, grava um log da execução em `logs_de_compilacao\` e chama o `instalar_cofre.ps1`.

Se o Windows bloquear scripts, o `.bat` já usa `-ExecutionPolicy Bypass` **só para aquela execução**, sem mudar a política do computador. Também dá para rodar direto:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\instalar_cofre.ps1
```

### 8.3 O que o instalador pergunta e faz

O instalador **pergunta primeiro** qual é o seu uso:

| Modo | Onde fica | Observações |
|---|---|---|
| **1. Portátil** (recomendado) | Num pendrive. Compilação, temporários, programa e cofre ficam **todos no pendrive**; nada vai para o disco do Windows. | Ideal com BitLocker To Go. Alerta vermelho se o pendrive for FAT32/exFAT. |
| **2. No computador** | Numa pasta que você escolher (nunca dentro de Downloads). | Remove a herança de permissões e deixa **só a sua conta e o SISTEMA** com acesso (`icacls`). Não cria atalho nem item no Menu Iniciar. |

Depois, são 5 etapas explicadas na tela:

0. **Destino:** pergunta a letra do pendrive (sugere H:) e recusa o disco do Windows.
1. **Conferência do programa:** usa **somente** o `cofre_senhas.py` ao lado do instalador, mostra o SHA-256 e **exige que você digite os 16 primeiros caracteres**. Essa é a única etapa que nunca aceita ENTER: é a defesa central contra um arquivo trocado. O hash é recalculado três vezes (após a cópia, antes dos testes e imediatamente antes de compilar).
2. **Python:** verifica e instala se faltar.
3. **Bibliotecas:** instala em **versões fixas e com hash** (`pip --require-hashes`), num ambiente virtual novo e isolado. Qualquer arquivo diferente do esperado é recusado.
4. **Teste de criptografia:** cria, abre e destrói um cofre de teste.
5. **Compilação:** gera um único `CofreSenhas.exe` nativo com o Nuitka e o compilador Zig. A primeira compilação leva de 5 a 20 minutos; as seguintes são bem mais rápidas, e uma falha **não recomeça do zero**. Durante a compilação, o instalador mostra `[vivo]` a cada 15 s para você saber que não travou.

No fim, o instalador mostra o **SHA-256 do `.exe`**. **Anote esse número em papel**: é a única cópia confiável dele.

### 8.4 Instalar sem internet (pacotes offline)

Dê dois cliques em **`3 - BAIXAR PACOTES - so para instalar sem internet.bat`** (precisa de internet só nessa hora). Ele baixa, com hash conferido, tudo o que a instalação usa para a pasta `pacotes\`. Com a pasta cheia, o instalador avisa *Modo OFFLINE* e não baixa nada. A pasta `pacotes\` **não é versionada no Git**; cada máquina gera a sua. Em ARM64, apague a pasta para o instalador baixar o pacote certo.

### 8.5 Aviso "Editor desconhecido" do Windows (SmartScreen)

Na primeira vez que abrir o `.exe`, o Windows pode avisar "Editor desconhecido". É esperado: o programa é compilado por **você** e não tem assinatura digital paga; o Windows só avisa porque nunca viu esse arquivo antes. Clique em **Mais informações → Executar assim mesmo**. Se quiser certeza, confira o SHA-256 anotado em `⋯ → Verificar integridade do programa`.

> **Antivírus:** programas compilados novos às vezes são confundidos com ameaças. Se o seu antivírus bloquear, libere **só o `CofreSenhas.exe`**, nunca pastas inteiras.

### 8.6 Onde ficam os dados

- O cofre é o arquivo **`cofre.dat`, na mesma pasta do programa**. Para usar num pendrive, deixe `CofreSenhas.exe` e `cofre.dat` juntos nele.
- Depois da instalação, a pasta só mostra o `CofreSenhas.exe`; o `cofre.dat`, as cópias, o `.diag`, o `.lock` e os logs ficam ocultos e protegidos.
- Ao abrir, o programa se descompacta numa pasta temporária **ao lado dele** (`CofreSenhas_em_uso_...`), apagada ao fechar. Nada vai para a pasta temporária do Windows.
- O cofre é portátil: copiar para outro PC com o programa funciona. A segurança vem da senha e da chave, não do computador (a menos que você ative *Computadores autorizados*).

---

## 9. Primeiros passos

1. **Crie o cofre.** Recomendado: modo **Senha E chave de acesso** e blindagem **Máxima**. Use **Gerar…** para criar uma frase de 5 ou 6 palavras e acompanhe a análise de força.
2. **Guarde a chave de acesso.** Ela aparece **uma única vez**. Salve o `.key` em **outro** pendrive, longe do cofre, e **anote à mão** em papel.
3. *(Opcional)* **Cadastre a chave FIDO** pelo botão **Chave FIDO**: toque 3 vezes e digite o PIN da chave quando o Windows pedir. **Anote o código de recuperação** e cadastre também uma chave reserva.
4. **Importe suas senhas** (`⋯ → Importar planilha`), confira a prévia e deixe o cofre **apagar a planilha com segurança**.
5. **Rode Verificar senhas** e troque as fracas e as repetidas. Comece pelas de banco e e-mail.
6. **Faça backup** (`⋯ → Backup do cofre`) e guarde em outro lugar. Refaça depois de mudanças importantes.
7. **Anote o SHA-256 do `.exe`** (mostrado no fim da instalação) e guarde junto com o código de recuperação, em local seguro.

---

## 10. Uso no dia a dia e atalhos

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

O menu `⋯` concentra: Verificar senhas, Importar planilha, Baixar modelo de planilha, Backup do cofre, Tentativas erradas, Bloqueio automático, Proteção extra, Computadores autorizados, Histórico de aberturas, Diagnóstico e Verificar integridade do programa.

---

## 11. Rodando direto do código-fonte

Só para desenvolvimento ou depuração. Para o cofre de verdade, use sempre o instalador (ele confere hashes, isola o ambiente e testa a criptografia antes de compilar).

```powershell
pip install -r requirements.txt
python cofre_senhas.py                      # cofre.dat ao lado do programa
python cofre_senhas.py E:\pasta\cofre.dat   # outro local
```

Bibliotecas usadas (versões exatas em `requirements.txt`): `cryptography`, `argon2-cffi`, `openpyxl`, `defusedxml`, `fido2`; e, só para compilar, `nuitka`, `ziglang`, `setuptools` e `wheel`. O programa rodando em `.py` solto não esconde arquivos nem detecta depurador do mesmo modo que o `.exe` compilado.

---

## 12. Testes automáticos

O projeto tem uma bateria grande de testes, organizada por assunto. Cada teste trabalha numa pasta temporária, termina com `TODOS OK` e devolve código de saída 0 (sucesso) ou 1 (falha), o que permite usar em integração contínua.

| Pasta | O que testa |
|---|---|
| `testes/1_motor_do_cofre/` | O **motor** (criptografia, arquivo, backup, falhas de disco, queda de energia, concorrência entre processos, vazamento de memória, soak de 1.000 ciclos), sem abrir janelas. |
| `testes/2_telas_e_botoes/` | A **interface**: abre janelas e clica de verdade (criar, editar, copiar, bloqueio, teclado virtual, cortes de texto em vários tamanhos de janela, janelas que aparecem prontas…). |
| `testes/3_ataques_simulados/` | **Ataques simulados** (pentest): injeção, força bruta, DoS, forense de memória, engenharia reversa, fuzzing, SAST (bandit), dependências (pip-audit), canal lateral de tempo, exfiltração pela rede, link simbólico. |
| `testes/4_so_no_windows/` | O que só vale no **Windows real**: instalador (Pester), atributos de arquivo, ACL, SMBIOS, DPAPI, WebAuthn, Windows Sandbox limpo. |
| `testes/ferramentas_dos_testes/` | **Não são testes:** são os programas que executam, juntam resultados, limpam e medem cobertura. |
| `testes/resultados/` | Tudo que os testes geram (resultado de cada teste, `resumo_testes.md/json`, `resultados.sarif`, `log_depuracao.txt`). Guarda só a **última** rodada. |

### Como rodar

**No Windows (mais fácil):** dê dois cliques em **`2 - TESTAR TUDO - roda todos os testes.bat`**. Ele roda as cinco baterias em sequência (leva de 20 a 30 minutos) e junta os resultados em `testes\resultados\`. Cada pasta de testes também tem o seu `.bat` ("RODAR ESTA PASTA - …") para rodar só aquela bateria.

**Pela linha de comando:**

```powershell
python testes\ferramentas_dos_testes\rodar_todos.py            # tudo (núcleo + interface)
python testes\ferramentas_dos_testes\rodar_todos.py --rapido   # só o núcleo, sem janelas
python testes\ferramentas_dos_testes\rodar_todos.py --so gui   # só a interface
python testes\ferramentas_dos_testes\rodar_todos.py --filtro fido
```

Com `pytest`: `pytest testes/ferramentas_dos_testes/test_pytest.py -v` (cada `teste_*.py` vira um caso).

Os testes rodam em prioridade baixa e esperam haver RAM livre, para não travar o seu PC. Leia [`testes/COMO_RODAR_OS_TESTES.md`](testes/COMO_RODAR_OS_TESTES.md) para o passo a passo e [`testes/PLANO_DE_TESTES.md`](testes/PLANO_DE_TESTES.md) para saber quais riscos são cobertos e quais ficaram de fora (e por quê).

---

## 13. Estrutura do repositório

```
projeto-cofre-offline/
│
├── LEIA PRIMEIRO - mapa do projeto.md            # para que serve cada pasta e arquivo (para não programadores)
├── 1 - INSTALAR O COFRE - compila e instala.bat  # instalador: dois cliques
├── 2 - TESTAR TUDO - roda todos os testes.bat    # roda as 5 baterias de teste no Windows
├── 3 - BAIXAR PACOTES - so para instalar sem internet.bat
│
├── cofre_senhas.py        # o programa inteiro (um arquivo só, fácil de auditar)
├── instalar_cofre.ps1     # o instalador que o "1 - INSTALAR..." chama por trás
├── requirements.txt       # bibliotecas e compilador, com versão exata
├── .gitignore
│
├── docs/
│   ├── MANUAL_COMPLETO.md           # manual técnico completo
│   ├── MODELO_DE_AMEACAS.md         # quem pode atacar, o que consegue, o que NÃO é defendido
│   └── HISTORICO_*                  # relatório de 13/11, lista de mudanças, SHA-256 do programa
│
├── testes/                # COMO_RODAR_OS_TESTES.md, PLANO_DE_TESTES.md e as 5 pastas de testes
│
├── ferramentas_windows_opcionais/   # extras que cuidam do seu PC (não do cofre)
│
├── pacotes/               # (não versionada) bibliotecas para instalar sem internet
└── logs_de_compilacao/    # (não versionada) um log por instalação
```

O programa é **um único arquivo** de propósito. Internamente ele é organizado em seções: núcleo criptográfico, avaliação de força, impressão, proteções do Windows, classe `Cofre`, importação, FIDO2, tema e ícones, componentes de interface e classe `App`.

### Ferramentas opcionais do Windows

A pasta `ferramentas_windows_opcionais/` traz scripts **independentes do cofre** para conferir e reforçar o PC. Leia cada um antes de rodar; os que alteram o PC precisam de administrador.

| Atalho | O que faz | Altera o PC? |
|---|---|---|
| `1 - VERIFICAR a seguranca do Windows` | Relatório de antivírus, atualizações, firewall, SMBv1, acesso remoto, UAC, SmartScreen, TPM, Secure Boot, Integridade da memória, histórico da área de transferência e teclados conectados. | **Não**, só lê |
| `2 - APLICAR ajustes de seguranca do Windows` | Cria um ponto de restauração; desliga a reprodução automática de pendrives e o histórico da área de transferência; abre a tela da Integridade da memória. | **Sim** |
| `3 - DESFAZER os ajustes de seguranca` | Desfaz os ajustes do item 2. | **Sim** |
| `4 - PROCURAR rootkit no nucleo do Windows` | Procura drivers sem assinatura ou de fabricante desconhecido e confere a inicialização segura. | **Não**, só lê |

---

## 14. Documentação detalhada

| Documento | Para que serve |
|---|---|
| [`LEIA PRIMEIRO - mapa do projeto.md`](LEIA%20PRIMEIRO%20-%20mapa%20do%20projeto.md) | Mapa simples, escrito para quem não é programador. Comece por aqui. |
| [`docs/MANUAL_COMPLETO.md`](docs/MANUAL_COMPLETO.md) | Manual técnico completo: formato do arquivo (`COFRE05`), detalhes de cada proteção, instalador, tabela de todos os testes e perguntas frequentes. |
| [`docs/MODELO_DE_AMEACAS.md`](docs/MODELO_DE_AMEACAS.md) | Quem pode atacar, o que cada atacante consegue, onde cada recurso realmente ajuda e o que **não** é defendido. |
| [`docs/HISTORICO_lista_de_mudancas.md`](docs/HISTORICO_lista_de_mudancas.md) | O que mudou em cada rodada de desenvolvimento. |
| [`docs/HISTORICO_relatorio_final_de_13-11.md`](docs/HISTORICO_relatorio_final_de_13-11.md) | Retrato de 13/11/2026: resultados, red team e o que um atacante com ferramentas de engenharia reversa consegue. |
| [`testes/COMO_RODAR_OS_TESTES.md`](testes/COMO_RODAR_OS_TESTES.md) e [`testes/PLANO_DE_TESTES.md`](testes/PLANO_DE_TESTES.md) | Como rodar e o que os testes cobrem. |

---

## 15. Cuidados ao publicar no Git

O `.gitignore` já impede o envio de `cofre.dat` e qualquer `*.dat`, arquivos de chave `*.key`, planilhas `*.xlsx`/`*.xlsm`/`*.csv`, o `CofreSenhas.exe`, pastas de compilação, a pasta `pacotes/`, logs e caches.

Mesmo assim:

- **Nunca** faça commit do seu `cofre.dat`, da chave de acesso, do código de recuperação ou de planilhas com senhas. Antes de cada commit, confira com `git status` o que vai subir.
- Prefira um **repositório privado** para o seu fluxo pessoal. Publicar o código não enfraquece o cofre, porque a segurança está nas chaves e não no segredo do código.
- Para distribuir um programa compilado, publique também o **SHA-256** do `.exe`, para quem baixar poder conferir.
- O GitHub bloqueia o push se o e-mail do commit for privado (erro `GH007`). Use o e-mail `ID+usuario@users.noreply.github.com` mostrado em *Settings → Emails*.

---

## 16. Perguntas frequentes

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
É o Argon2id trabalhando com 1 GiB de memória. Essa demora é o que torna a força bruta inviável.

**O programa acessa a internet?**
Não, por conta própria. Há **uma** função opcional, só quando você pede: `⋯ → Verificar senhas → Checar vazamentos (online)` (veja [3.4](#34-avaliação-de-força-e-auditoria)). Fora isso, só o **instalador** baixa o Python e as bibliotecas (e nem isso, no modo offline).

**Apaguei sem querer o cofre depois de errar a senha. Dá para recuperar?**
Não pelo programa: a autodestruição sobrescreve o arquivo e as cópias. Só um backup seu, feito em outro lugar, resolve.

**Posso aceitar planilhas do Chrome ou do Samsung Pass?**
Por padrão não (só o modelo gerado pelo próprio cofre). Para aceitar, mude `IMPORTAR_SOMENTE_COM_SELO = False` no topo do `cofre_senhas.py` e recompile, sabendo que isso reduz a proteção da importação.

**Funciona em macOS, Linux ou celular?**
O programa e as proteções são para Windows. Os testes do motor também rodam em Linux, mas isso é para desenvolvimento, não para uso.

---

## 17. Glossário

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
| **Nuitka / Zig** | Ferramentas que compilam o programa Python em um `.exe` nativo. |
| **Pentest / red team** | Testes em que o cofre é atacado de propósito para provar que as defesas funcionam. |

---

## 18. Status e honestidade do projeto

- Este é um **projeto pessoal**. Não passou por auditoria de segurança independente. A suíte de testes (motor, interface, ataques simulados e Windows real), a análise estática (`bandit`, sem achados médios/altos) e a verificação de dependências (`pip-audit`) ajudam, mas **não substituem** uma revisão externa.
- Nas rodadas de teste no Windows real foram confirmados atributos de arquivo, ACL por `icacls`, UUID do SMBIOS, DPAPI, computador autorizado de ponta a ponta, blindagens do processo e WebAuthn (0 falhas).
- **Ainda não verificado em Windows real** (ou só parcialmente): o instalador de ponta a ponta em todos os cenários (modo no computador, ARM64), a assinatura digital opcional do `.exe` e o uso com uma **chave FIDO2/PRF física real**.
- Versões antigas do programa **não abrem** cofres com o fator *computador*; backups feitos antes de ativá-lo continuam abrindo em qualquer computador. Cofres de formatos anteriores (`COFRE01`–`COFRE04`) são convertidos automaticamente para o atual (`COFRE05`), e a cópia de segurança guarda o original.
- O que o projeto decidiu **não** fazer (ofuscadores comerciais, detecção de sandbox/EDR, MSI/serviços, "senha de coação"…) e por quê está registrado em `docs/MODELO_DE_AMEACAS.md` e em `docs/HISTORICO_lista_de_mudancas.md`.

**Use por sua conta e risco. Mantenha sempre um backup do cofre, da chave de acesso e do código de recuperação em locais diferentes.**

---

## 19. Licença e aviso legal

**Licença:** ainda não definida. Enquanto nenhum arquivo `LICENSE` for adicionado ao repositório, vale o padrão legal: todos os direitos reservados ao autor. Se você quiser permitir que outras pessoas usem, estudem e modifiquem o código, adicione uma licença (por exemplo MIT ou GPL-3.0) pelo botão *Add file → Create new file → LICENSE* no GitHub.

**Aviso:** o software é fornecido "como está", sem garantias de qualquer tipo. O autor não se responsabiliza por perda de dados, perda de acesso ao cofre ou qualquer dano decorrente do uso.

**Autor e manutenção:** [@ebj355](https://github.com/ebj355)

**Reportar um problema de segurança:** prefira avisar o autor em particular (pelo perfil do GitHub) antes de abrir uma issue pública com detalhes de uma vulnerabilidade.
