# Ferramentas EXTERNAS de análise

**Para que serve esta pasta:** Bandit, pip-audit, Nmap, PSScriptAnalyzer, verificação de segredos, qualidade, SBOM, Hypothesis e integridade do repositório. São independentes do executável compilado e fazem parte do TESTAR TUDO (etapa 6/6), menos o pytest, que repete as baterias 1 e 2.

_Gerado por `testes/6_TESTE_ferramentas_dos_testes/gerar_indices.py` (não edite à mão: rode o script)._

| Arquivo | Para que serve |
|---|---|
| `00_MENU_TESTES_FERRAMENTAS.bat` | Menu de dois cliques para rodar as ferramentas externas; inclui um atalho para a pasta 7 de testes de compilação. |
| `01_BANDIT_CODIGO.bat` | Bandit: análise estática do cofre_senhas.py. Código 9 = Bandit não instalado (pulado). |
| `02_PIP_AUDIT_DEPENDENCIAS.bat` | pip-audit: vulnerabilidades conhecidas nas bibliotecas do requirements.txt (precisa de internet). |
| `03_PYTEST_PROJETO.bat` | pytest: roda a ponte test_pytest.py. Só no menu: repete as baterias 1 e 2, por isso não entra no TESTAR TUDO. |
| `04_NMAP_PORTAS_LOCAIS.bat` | Nmap: portas TCP abertas SOMENTE em 127.0.0.1 (este computador). Não analisa o código. |
| `05_PSSCRIPTANALYZER.bat` | PSScriptAnalyzer: lint dos .ps1 do projeto. Código 9 = módulo não baixado (pulado). |
| `08_SEGREDOS_NO_REPOSITORIO.bat` | Procura cofre.dat, .key, .bak e segredos em texto (detect-secrets) antes de enviar ao GitHub. |
| `09_QUALIDADE_EXTRA.bat` | Ruff, mypy, Radon e Vulture sobre o cofre_senhas.py: lint extra, tipos, complexidade e código morto. |
| `10_PIP_AUDIT_TESTE_E_SBOM.bat` | pip-audit também no requirements-test-lock.txt e geração do SBOM CycloneDX (precisa de internet). |
| `12_HYPOTHESIS_PROPRIEDADES.bat` | Roda o teste por propriedades (Hypothesis) do motor do cofre. |
| `13_INTEGRIDADE_REPOSITORIO.bat` | Confere o .gitignore com resíduos reais de cofre e valida pins e hashes das dependências. |
| `LEIA-ME.txt` | Como usar esta pasta, o que cada .bat faz e os limites das ferramentas. |
| `RODAR ESTA PASTA - ferramentas externas.bat` | Roda as ferramentas 01, 02, 04, 05 e 08-10, 12 e 13 sem menu e grava resultado_ferramentas_externas_windows.txt. Os testes do executável compilado estão separados na pasta 7; o pytest 03 fica fora por duplicar o núcleo e a interface. |
| `baixar_psscriptanalyzer.ps1` | Baixa o módulo PSScriptAnalyzer para pacotes\powershell-modules (precisa de internet). |
| `preparar_ambiente_offline.bat` | Cria ou atualiza o ambiente virtual local das ferramentas usando somente os wheels de pacotes\ e requirements-test-lock.txt. |
| `verificar_integridade_repositorio.py` | Confere o .gitignore com residuos reais de cofre e valida os pins usados pelo build. |
| `verificar_segredos.py` | Procura arquivos de cofre/chave/copias e segredos em texto antes de enviar o projeto ao GitHub. Uso: python verificar_segredos.py [pasta]  /  Saida: 0 = limpo / 1 = achados ou falha da auditoria. |
