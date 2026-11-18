# LEIA PRIMEIRO — mapa do projeto (para que serve cada coisa)

Escrito para quem **não é programador**. Cada item abaixo diz o que é e se você precisa mexer nele.
Dentro de cada pasta de testes existe também um `INDICE.md` que explica **cada arquivo** da pasta.

## 1. O que você usa (clique duas vezes)
| Arquivo na pasta principal | O que faz | Quando usar |
|---|---|---|
| `1 - INSTALAR O COFRE - compila e instala.bat` | Instala o cofre (no pendrive ou no computador). | Para instalar ou atualizar o cofre. |
| `2 - TESTAR TUDO - roda todos os testes.bat` | Roda **todos** os testes no Windows e junta os resultados em `testes\resultados\`. Apaga os resultados da rodada anterior antes. | Depois de mudar qualquer coisa, ou para conferir que está tudo certo. |
| `3 - BAIXAR PACOTES - so para instalar sem internet.bat` | Baixa as dependências do cofre e das ferramentas de teste para `pacotes\`. | Rode com internet antes de copiar o projeto para um computador offline. |

## 2. O programa em si (não mexer)
| Arquivo | O que é |
|---|---|
| `cofre_senhas.py` | **O cofre inteiro** (um arquivo só, de propósito: fica mais fácil de conferir). |
| `instalar_cofre.ps1` | O instalador que o `1 - INSTALAR...` chama por trás. |
| `requirements.txt` | Lista das bibliotecas usadas, com a versão exata. |
| `requirements-test.txt` | Lista das bibliotecas e ferramentas usadas pelas baterias, com versões fixas. |
| `.gitignore` | Lista de coisas que não vão para o GitHub (arquivo técnico, pode ignorar). |

## 3. Pastas
| Pasta | O que tem dentro |
|---|---|
| `docs/` | Os textos: `MANUAL_COMPLETO.md` (manual), `MODELO_DE_AMEACAS.md` (o que o cofre protege e o que **não** protege), e três `HISTORICO_*` (relatório antigo de 13/11, lista do que mudou em cada rodada e os SHA-256 do programa). |
| `testes/` | Tudo sobre testes (veja a seção 4). |
| `logs_de_compilacao/` | Um arquivo de registro **por instalação/compilação** (o que deu certo ou errado). Gerado sozinho. |
| `pacotes/` | Wheelhouse do cofre e dos testes, instaladores locais de Python/Nmap e módulo Pester para uso sem internet. Copie a pasta inteira para o computador offline. |
| `ferramentas_windows_opcionais/` | Extras **opcionais** que cuidam do seu Windows (não do cofre). Cada `.bat` numerado diz o que faz no próprio nome; os `.ps1` ficam na subpasta `_scripts_internos_nao_mexer`. |

## 4. Dentro de `testes/`
| Pasta / arquivo | Em uma frase |
|---|---|
| `COMO_RODAR_OS_TESTES.md` | Passo a passo de como rodar os testes. |
| `PLANO_DE_TESTES.md` | Quais riscos os testes cobrem e quais ideias ficaram de fora (e por quê). |
| `1_motor_do_cofre/` | Testa o **motor** (criptografia, arquivo, backup, falhas de disco), sem abrir janelas. |
| `2_telas_e_botoes/` | Testa as **telas**: abre janelas e clica de verdade. |
| `3_ataques_simulados/` | **Ataca** o cofre de propósito para provar que as defesas funcionam (pentest). |
| `4_so_no_windows/` | Testes que só valem no **Windows de verdade** (instalador, permissões, atributos). Os `.bat` com letra (A, B, C, D) dizem no nome o que fazem. |
| `6_ferramentas_dos_testes/` | **Não são testes**: são os programas que rodam os testes, juntam resultados, limpam e medem cobertura. |
| `resultados/` | **TUDO que os testes geram**: um resultado por teste, o resumo, o relatório de cobertura e o `log_depuracao.txt` (a saída completa, para abrir quando algo falha). Só guarda a **última** rodada; a anterior é apagada ao começar. |

## 5. Regras para manter limpo
1. Tudo que um teste gerar vai para `testes/resultados/`; logs de instalação vão para `logs_de_compilacao/`; textos vão para `docs/`.
2. Teste novo: o nome diz o assunto e a 1ª frase do arquivo explica para que serve (aparece no `INDICE.md`).
3. Depois de criar, renomear ou apagar algo em `testes/`, rode `python testes/6_ferramentas_dos_testes/gerar_indices.py` (avisa se algum arquivo ficou sem explicação).
