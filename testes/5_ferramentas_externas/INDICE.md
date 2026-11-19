# Ferramentas EXTERNAS de análise

**Para que serve esta pasta:** Bandit, pip-audit, Nmap, PSScriptAnalyzer, pefile, Defender, verificação de segredos, qualidade, SBOM, rede do processo e Hypothesis. Fazem parte do TESTAR TUDO (etapa 6/6), menos o pytest, que repete as baterias 1 e 2.

_Gerado por `testes/6_ferramentas_dos_testes/gerar_indices.py` (não edite à mão: rode o script)._

| Arquivo | Para que serve |
|---|---|
| `00_MENU_TESTES_FERRAMENTAS.bat` | Menu de dois cliques para rodar cada ferramenta externa separadamente. |
| `01_BANDIT_CODIGO.bat` | Bandit: análise estática do cofre_senhas.py. Código 9 = Bandit não instalado (pulado). |
| `02_PIP_AUDIT_DEPENDENCIAS.bat` | pip-audit: vulnerabilidades conhecidas nas bibliotecas do requirements.txt (precisa de internet). |
| `03_PYTEST_PROJETO.bat` | pytest: roda a ponte test_pytest.py. Só no menu: repete as baterias 1 e 2, por isso não entra no TESTAR TUDO. |
| `04_NMAP_PORTAS_LOCAIS.bat` | Nmap: portas TCP abertas SOMENTE em 127.0.0.1 (este computador). Não analisa o código. |
| `05_PSSCRIPTANALYZER.bat` | PSScriptAnalyzer: lint dos .ps1 do projeto. Código 9 = módulo não baixado (pulado). |
| `06_PEFILE_EXE.bat` | pefile: confere ASLR, DEP, High-Entropy ASLR e CFG do CofreSenhas.exe compilado. |
| `07_DEFENDER_EXE.bat` | Windows Defender (MpCmdRun): varre só o CofreSenhas.exe para detectar falso positivo antes de entregar. |
| `08_SEGREDOS_NO_REPOSITORIO.bat` | Procura cofre.dat, .key, .bak e segredos em texto (detect-secrets) antes de enviar ao GitHub. |
| `09_QUALIDADE_EXTRA.bat` | Ruff, mypy, Radon e Vulture sobre o cofre_senhas.py: lint extra, tipos, complexidade e código morto. |
| `10_PIP_AUDIT_TESTE_E_SBOM.bat` | pip-audit também no requirements-test.txt e geração do SBOM CycloneDX (precisa de internet). |
| `11_REDE_DO_PROCESSO.bat` | Com o cofre aberto, lista conexões TCP/UDP do processo; o esperado é nenhuma. |
| `12_HYPOTHESIS_PROPRIEDADES.bat` | Roda o teste por propriedades (Hypothesis) do motor do cofre. |
| `LEIA-ME.txt` | Como usar esta pasta, o que cada .bat faz e os limites das ferramentas. |
| `RODAR ESTA PASTA - ferramentas externas.bat` | Roda as ferramentas 01, 02 e 04-12 sem menu e grava resultado_ferramentas_externas_windows.txt. Falhas reais do teste Hypothesis reprovam esta etapa; o pytest 03 fica fora por duplicar o núcleo e a interface. |
| `_achar_exe.bat` | Auxiliar dos .bat 06, 07 e 11: localiza o CofreSenhas.exe (COFRE_EXE, argumento ou raiz). |
| `baixar_psscriptanalyzer.ps1` | Baixa o módulo PSScriptAnalyzer para pacotes\powershell-modules (precisa de internet). |
| `preparar_ambiente_offline.bat` | Cria ou atualiza o ambiente virtual local das ferramentas usando somente os wheels de pacotes\ e requirements-test.txt. |
| `verificar_pe.py` | Confere protecoes ASLR, DEP, High-Entropy ASLR e CFG; codigos: 0=ok, 1=protecao ausente, 2=exe nao encontrado, 9=pefile ausente. |
| `verificar_segredos.py` | Procura no projeto o que NUNCA pode ir para o GitHub: arquivos de cofre/chave/copias e segredos em texto (detect-secrets, se instalado). Uso: python verificar_segredos.py [pasta]  /  Saida: 0 = limpo / 1 = achados / 9 = nada a verificar. |
