# Testes da Arca — SEGURANÇA (pentest)

**Para que serve esta pasta:** Tentam ATACAR o cofre (injeção, força bruta, DoS, vazamento de memória, engenharia reversa, rede, instalador) para provar que as defesas funcionam.

_Gerado por `testes/6_TESTE_ferramentas_dos_testes/gerar_indices.py` (não edite à mão: rode o script)._

| Arquivo | Para que serve |
|---|---|
| `RODAR ESTA PASTA - testes de ataque simulado.bat` | Atalho de dois cliques da bateria de PENTEST no Windows (chama rodar_pentest.py com Python temporário). |
| `rodar_pentest.py` | Executa TODA a bateria de pentest (testes/3_TESTE_ataques_simulados/teste_pentest_*.py) e mostra um resumo. Uso (na pasta do projeto): |
| `teste_pentest_crack_bypass.py` | PENTEST - categoria "Tentativa de desbloqueio forçado / Cracks" (bypass da autodestruição e do contador). `testes/1_TESTE_motor_do_cofre/teste_ataques.py` já cobre uma bateria enorme de adulteração de arquivo (contador fora da faixa, |
| `teste_pentest_dependencias.py` | PENTEST - categoria "Dependências e Cadeia de Suprimentos" (Supply Chain). O instalador (`instalar_cofre.ps1`) já faz a coisa certa: versões FIXAS com `pip --require-hashes`, então qualquer |
| `teste_pentest_dos.py` | PENTEST - categoria "Negação de Serviço" (DoS). Sem rede não há DDoS volumétrico pra testar (o Cofre não recebe tráfego de ninguém) - o DoS possível aqui é LOCAL: um atacante com acesso ao disco (ou um arquivo importado hostil) |
| `teste_pentest_engenharia_reversa.py` | PENTEST - categoria "Engenharia Reversa / Forense Estática" (SAST focado em segredos e backdoors). `testes/1_TESTE_motor_do_cofre/teste_ataques.py` (item 14) já confere a detecção de depurador (ambiente_suspeito). Este arquivo |
| `teste_pentest_exfiltracao_rede.py` | PENTEST - categoria "Vazamento de Dados pela Rede" (exfiltração). `teste_pentest_vazamento_memoria.py` já confere vazamento pela RAM; `teste_tecnico_sistema.py` já confere que o código só usa rede para o HIBP. O que |
| `teste_pentest_forca_bruta_spray.py` | PENTEST - categoria "Ataques de Autenticação e Credenciais" (Força Bruta e Password Spraying), caixa preta. Força bruta: testa MUITAS senhas contra UM cofre até a autodestruição (já comprovado noutros testes; aqui é |
| `teste_pentest_fuzzing_adversarial_ia.py` | PENTEST - categoria "Fuzzing adversarial e Injeção de Prompt em IA". O Cofre não tem IA/LLM nenhuma integrada (confirmado por SAST: nenhum import de openai/anthropic/langchain, |
| `teste_pentest_injecao.py` | PENTEST - categoria "Injeção de Código" (SQLi / Command Injection / Template Injection). O Cofre NÃO tem banco de dados (SQLi é estruturalmente inaplicável: não há SQL em lugar nenhum do programa) e não |
| `teste_pentest_na_fora_do_escopo.py` | PENTEST - categoria "Fora de Escopo" (N/A documentado, não fingido). A lista de ferramentas/técnicas que o usuário pediu para testar inclui MUITA coisa pensada para aplicações web, |
| `teste_pentest_ocultacao_continua.py` | OCULTAÇÃO CONTÍNUA DO COFRE (simulada: os atributos do Windows são trocados por um 'Windows de mentira'). Mudança de projeto: o cofre e as cópias (.bak, .lock, .diag...) ficam ESCONDIDOS (Oculto+Sistema+Somente leitura) o tempo |
| `teste_pentest_rede_bloqueada.py` | REDE BLOQUEADA / FIREWALL: a única conexão do cofre (a consulta OPCIONAL de senhas vazadas, HIBP) tem que falhar de forma limpa, rápida e sem abrir mão da segurança. |
| `teste_pentest_residuos_disco_entropia.py` | RESÍDUOS EM DISCO: depois de uma sessão inteira, NENHUM segredo pode ter ficado legível em lugar nenhum. Faz uma sessão completa (criar, adicionar itens com marcadores únicos, salvar várias vezes, trocar senha, consultar, |
| `teste_pentest_sast.py` | PENTEST - categoria "Análise Estática" (SAST com ferramentas de mercado, não só os greps/AST manuais dos outros arquivos deste pentest). Roda `bandit` (segurança) e `flake8 --select=F` (pyflakes: bugs de verdade - |
| `teste_pentest_side_channel_tempo.py` | PENTEST - categoria "Canal Lateral de Tempo" (side-channel timing attack). A ideia de um ataque de tempo: se o programa demora um pouquinho MAIS para recusar uma senha "quase certa" do que uma senha "bem diferente", |
| `teste_pentest_ssrf.py` | PENTEST - categoria "SSRF" (Server-Side Request Forgery). O Cofre não tem servidor e só faz UMA chamada de rede OPCIONAL, que o usuário liga na mão (checagem HIBP de senha vazada) - e mesmo essa chamada nunca usa dado digitado |
| `teste_pentest_superficie_instalador.py` | SUPERFÍCIE DO INSTALADOR/PROGRAMA NO WINDOWS: o que o cofre NÃO deixa no sistema, e só com o privilégio necessário. Adapta ao cofre uma lista de testes de instalador (MSI/serviços/menu de contexto). O cofre é PORTÁTIL: um .exe, sem |
| `teste_pentest_symlink_arquivo.py` | PENTEST - categoria "Ataque Local de Link Simbólico" (symlink/TOCTOU na gravação em disco). Este arquivo documenta um ACHADO REAL encontrado e já CORRIGIDO em `_gravar_atomico` (cofre_senhas.py): antes da correção, |
| `teste_pentest_vazamento_memoria.py` | PENTEST - categoria "Vazamento de Memória" (dados sensíveis sobrevivendo na RAM depois de usados). Um atacante com acesso à máquina (um dump de memória, um swap mal protegido, um debugger anexado) pode tentar ler |
