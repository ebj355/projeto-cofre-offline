# Ferramentas EXTERNAS de análise

**Para que serve esta pasta:** Programas instalados no Windows (Bandit, pip-audit, Nmap, pytest) que analisam o cofre de fora; o pytest é opcional porque repete testes já incluídos.

_Gerado por `testes/6_ferramentas_dos_testes/gerar_indices.py` (não edite à mão: rode o script)._

| Arquivo | Para que serve |
|---|---|
| `00_MENU_TESTES_FERRAMENTAS.bat` | Menu para rodar separadamente Bandit, pip-audit, pytest ou Nmap. |
| `01_BANDIT_CODIGO.bat` | Analisa estaticamente cofre_senhas.py com Bandit. |
| `02_PIP_AUDIT_DEPENDENCIAS.bat` | Verifica vulnerabilidades conhecidas nas dependências declaradas. |
| `03_PYTEST_PROJETO.bat` | Ponte opcional para executar os testes via pytest; repete baterias já existentes. |
| `04_NMAP_PORTAS_LOCAIS.bat` | Verifica portas TCP somente em 127.0.0.1 (este computador). |
| `LEIA-ME.txt` | Instruções e limites das ferramentas externas. |
| `RODAR ESTA PASTA - ferramentas externas.bat` | Executa Bandit, pip-audit e Nmap e salva todos os relatórios diretamente em testes/resultados/. |
| `gerar_indices.py` | Gera o INDICE.md de cada pasta de testes (e atualiza o MAPA dos testes): uma linha por arquivo dizendo PARA QUE SERVE (primeira linha do texto de abertura de cada .py; descrição escrita à mão para .bat/.ps1/.md) e POR QUE está naquela pasta. |
