# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Gera o INDICE.md de cada pasta de testes: uma linha por arquivo dizendo PARA QUE SERVE
(primeira linha do texto de abertura de cada .py; descrição escrita à mão para .bat/.ps1/.md) e POR QUE está naquela pasta.
Arquivo novo SEM descrição aparece como 'FALTA DESCRIÇÃO' e o programa sai com erro: assim nenhum arquivo fica sem explicação.
Uso: python testes/6_TESTE_ferramentas_dos_testes/gerar_indices.py"""
import ast, os, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
TESTES = os.path.dirname(AQUI)
PASTAS = {
    "1_TESTE_motor_do_cofre": ("Testes da Arca — NÚCLEO (sem janelas)", "Provam o motor do cofre: criptografia, arquivo, backups, tentativas, importação, falhas de disco. Rodam no Linux e no Windows, rápidos, sem tela. Cada `teste_*.py` é independente."),
    "2_TESTE_telas_e_botoes": ("Testes da Arca — INTERFACE (janelas Tk)", "Abrem as telas de verdade (no Linux com tela virtual `xvfb-run`; no Windows em janelas reais) e clicam/digitam como um usuário. Cada `teste_gui_*.py` é independente."),
    "3_TESTE_ataques_simulados": ("Testes da Arca — SEGURANÇA (pentest)", "Tentam ATACAR o cofre (injeção, força bruta, DoS, vazamento de memória, engenharia reversa, rede, instalador) para provar que as defesas funcionam."),
    "4_TESTE_so_no_windows": ("Testes da Arca — Windows real", "Conferem o que o Linux só consegue simular: atributos de arquivo, permissões (ACL), DPAPI, SMBIOS, instalador, Windows Sandbox."),
    "5_TESTE_ferramentas_externas": ("Análise externa da Arca", "Bandit, pip-audit, Nmap, PSScriptAnalyzer, verificação de segredos, qualidade, SBOM, Hypothesis e integridade do repositório. São independentes do executável compilado e fazem parte do TESTAR TUDO (etapa 6/7), menos o pytest, que repete as baterias 1 e 2."),
    "6_TESTE_ferramentas_dos_testes": ("Ferramentas de teste da Arca", "Não são testes do cofre: são os executores (`rodar_*`), os ajudantes (`_resultado`, `_util_mem`), a limpeza, a cobertura e os relatórios. Também os documentos do plano de testes."),
    "7_TESTE_de_compilacao": ("Testes da Arca — executável compilado", "Verificam o executável gerado: proteções PE, varredura do Defender e conexões de rede do processo. Compile o programa antes; esta pasta é incluída automaticamente no Testar Tudo."),
}
MANUAL = {   # arquivos que não são .py (ou que não têm texto de abertura): para que serve + por que está aqui
    "6_TESTE_ferramentas_dos_testes/rodar_todos_windows.bat": "Roda as 7 baterias no Windows, incluindo a verificação pós-compilação. Pode incluir a letra do pendrive. Limpa resultados antigos e gera resultado completo/RESULTADO COMPLETO.txt.",
    "6_TESTE_ferramentas_dos_testes/consolidar_resultados.py": "Gera resumo_testes.md, resumo_testes.json e resultados.sarif em resultados/, além de resultado completo/RESULTADO COMPLETO.txt com todos os resultados individuais.",
    "6_TESTE_ferramentas_dos_testes/reunir_erros_compilacao.py": "Limpa e reúne os arquivos de erro da bateria em logs_de_compilacao/erros de compilação/TODOS_OS_ERROS.txt.",
    "6_TESTE_ferramentas_dos_testes/cobertura_codigo_windows.bat": "Atalho de dois cliques para medir a cobertura de código no Windows (chama cobertura_codigo.py). Fora do Testar_Tudo de propósito: é lento.",
    "2_TESTE_telas_e_botoes/RODAR ESTA PASTA - testes das telas e botoes.bat": "Atalho de dois cliques da bateria de INTERFACE no Windows (chama teste_gui_windows.ps1).",
    "2_TESTE_telas_e_botoes/teste_gui_windows.ps1": "Prepara um ambiente Python temporário e roda a bateria de interface (rodar_todos.py --so gui) no Windows, gravando o resultado.",
    "1_TESTE_motor_do_cofre/RODAR ESTA PASTA - testes do motor do cofre.bat": "Atalho de dois cliques da bateria do NÚCLEO no Windows (ambiente Python temporário próprio).",
    "1_TESTE_motor_do_cofre/PECA_DE_TESTE_cofre_versao_4_antiga.py": "FIXTURE (peça de teste, não é teste): cópia do programa na versão 4 antiga. Serve só para o teste_severo provar que cofres do formato antigo ainda abrem. Não apagar.",
    "3_TESTE_ataques_simulados/RODAR ESTA PASTA - testes de ataque simulado.bat": "Atalho de dois cliques da bateria de PENTEST no Windows (chama rodar_pentest.py com Python temporário).",
    "4_TESTE_so_no_windows/A - testar o instalador.bat": "Atalho de dois cliques do teste do INSTALADOR no Windows (chama teste_windows.ps1).",
    "4_TESTE_so_no_windows/teste_windows.ps1": "Valida o instalador e o programa no Windows real (pastas, atributos, compilação, SmartScreen etc.).",
    "4_TESTE_so_no_windows/instalador.Tests.ps1": "Testes Pester (PowerShell) do instalar_cofre.ps1: funções internas do instalador. Chamado por teste_windows.ps1.",
    "4_TESTE_so_no_windows/B - testar atributos e permissoes do Windows.bat": "Atalho de dois cliques do teste NATIVO (atributos, ACL, DPAPI, SMBIOS, DLLs). Aceita a letra do pendrive: B - testar atributos e permissoes do Windows.bat H.",
    "4_TESTE_so_no_windows/C - testar o Windows tambem no pendrive H.bat": "Atalho que já roda o teste nativo também no pendrive H: (troque a letra dentro do arquivo se o seu for outro).",
    "4_TESTE_so_no_windows/D - testar no Windows Sandbox limpo.wsb": "Configuração do Windows Sandbox: abre um Windows LIMPO e descartável com o projeto copiado, para testar a instalação do zero. Opcional.",
    "6_TESTE_ferramentas_dos_testes/test_pytest.py": "Ponte OPCIONAL para o pytest (cada teste vira um caso do pytest). Não é usada pelo Testar_Tudo.",
    "5_TESTE_ferramentas_externas/00_MENU_TESTES_FERRAMENTAS.bat": "Menu de dois cliques para rodar as ferramentas externas; inclui um atalho para a pasta 7 de testes de compilação.",
    "5_TESTE_ferramentas_externas/01_BANDIT_CODIGO.bat": "Bandit: análise estática do cofre_senhas.py. Código 9 = Bandit não instalado (pulado).",
    "5_TESTE_ferramentas_externas/02_PIP_AUDIT_DEPENDENCIAS.bat": "pip-audit: vulnerabilidades conhecidas nas bibliotecas do requirements.txt (precisa de internet).",
    "5_TESTE_ferramentas_externas/03_PYTEST_PROJETO.bat": "pytest: roda a ponte test_pytest.py. Só no menu: repete as baterias 1 e 2, por isso não entra no TESTAR TUDO.",
    "5_TESTE_ferramentas_externas/04_NMAP_PORTAS_LOCAIS.bat": "Nmap: portas TCP abertas SOMENTE em 127.0.0.1 (este computador). Não analisa o código.",
    "5_TESTE_ferramentas_externas/RODAR ESTA PASTA - ferramentas externas.bat": "Roda as ferramentas 01, 02, 04, 05 e 08-10, 12 e 13 sem menu e grava resultado_ferramentas_externas_windows.txt. Os testes do executável compilado estão separados na pasta 7; o pytest 03 fica fora por duplicar o núcleo e a interface.",
    "5_TESTE_ferramentas_externas/05_PSSCRIPTANALYZER.bat": "PSScriptAnalyzer: lint dos .ps1 do projeto. Código 9 = módulo não baixado (pulado).",
    "5_TESTE_ferramentas_externas/08_SEGREDOS_NO_REPOSITORIO.bat": "Procura cofre.dat, .key, .bak e segredos em texto (detect-secrets) antes de enviar ao GitHub.",
    "5_TESTE_ferramentas_externas/09_QUALIDADE_EXTRA.bat": "Ruff, mypy, Radon e Vulture sobre o cofre_senhas.py: lint extra, tipos, complexidade e código morto.",
    "5_TESTE_ferramentas_externas/10_PIP_AUDIT_TESTE_E_SBOM.bat": "pip-audit também no requirements-test-lock.txt e geração do SBOM CycloneDX (precisa de internet).",
    "5_TESTE_ferramentas_externas/12_HYPOTHESIS_PROPRIEDADES.bat": "Roda o teste por propriedades (Hypothesis) do motor do cofre.",
    "5_TESTE_ferramentas_externas/13_INTEGRIDADE_REPOSITORIO.bat": "Confere o .gitignore com resíduos reais de cofre e valida pins e hashes das dependências.",
    "5_TESTE_ferramentas_externas/baixar_psscriptanalyzer.ps1": "Baixa o módulo PSScriptAnalyzer para pacotes\\powershell-modules (precisa de internet).",
    "5_TESTE_ferramentas_externas/LEIA-ME.txt": "Como usar esta pasta, o que cada .bat faz e os limites das ferramentas.",
    "5_TESTE_ferramentas_externas/preparar_ambiente_offline.bat": "Cria ou atualiza o ambiente virtual local das ferramentas usando somente os wheels de pacotes\\ e requirements-test-lock.txt.",
    "7_TESTE_de_compilacao/RODAR ESTA PASTA - testes de compilacao.bat": "Roda as verificações pós-compilação: pefile, Defender e rede do processo. Grava o resumo e os relatórios individuais em testes/resultados/. Compile primeiro; se o executável, processo, Defender ou a política de segurança impedirem a verificação, registra PULADO sem contornar o bloqueio.",
    "7_TESTE_de_compilacao/06_PEFILE_EXE.bat": "Confere as proteções ASLR, DEP, High-Entropy ASLR e CFG do CofreSenhas.exe compilado.",
    "7_TESTE_de_compilacao/07_DEFENDER_EXE.bat": "Varre apenas o executável compilado com o Windows Defender, sem enviar dados do cofre a scanners externos; registra PULADO se o Defender estiver desativado ou uma política de segurança impedir a verificacao.",
    "7_TESTE_de_compilacao/11_REDE_DO_PROCESSO.bat": "Com o CofreSenhas.exe aberto, lista as conexões TCP/UDP do processo; o esperado é nenhuma.",
    "7_TESTE_de_compilacao/testar_rede_processo.ps1": "Abre uma instância temporária do executável, confere conexões TCP/UDP e encerra apenas os processos dessa instância.",
    "7_TESTE_de_compilacao/_achar_exe.bat": "Localiza CofreSenhas.exe por COFRE_EXE, argumento, raiz do drive do pendrive ou caminhos padrão do projeto.",
    "7_TESTE_de_compilacao/verificar_pe.py": "Verifica as flags de segurança PE do executável compilado com pefile.",
}
POR_QUE = {"1_TESTE_motor_do_cofre": "motor do cofre, sem tela", "2_TESTE_telas_e_botoes": "precisa de janela", "3_TESTE_ataques_simulados": "ataque/segurança", "4_TESTE_so_no_windows": "precisa do Windows real", "5_TESTE_ferramentas_externas": "usa programas instalados no Windows", "6_TESTE_ferramentas_dos_testes": "serve a todas as baterias", "7_TESTE_de_compilacao": "precisa do executável compilado"}

def primeira_linha(caminho):
    try:
        doc = ast.get_docstring(ast.parse(open(caminho, encoding="utf-8").read())) or ""
    except SyntaxError:
        return ""
    linhas = [l.strip() for l in doc.strip().splitlines() if l.strip()]
    return " ".join(linhas[:2])[:260]

def main():
    faltando = []
    for pasta, (titulo, intro) in PASTAS.items():
        d = os.path.join(TESTES, pasta)
        if not os.path.isdir(d): continue
        linhas = [f"# {titulo}", "", f"**Para que serve esta pasta:** {intro}", "",
                  "_Gerado por `testes/6_TESTE_ferramentas_dos_testes/gerar_indices.py` (não edite à mão: rode o script)._", "",
                  "| Arquivo | Para que serve |", "|---|---|"]
        for nome in sorted(os.listdir(d)):
            if nome in ("__pycache__", "INDICE.md") or nome.startswith("venv") or nome.startswith("_venv") or os.path.isdir(os.path.join(d, nome)): continue
            rel = f"{pasta}/{nome}"
            desc = MANUAL.get(rel) or (primeira_linha(os.path.join(d, nome)) if nome.endswith(".py") else "")
            if not desc:
                desc = "**FALTA DESCRIÇÃO**"; faltando.append(rel)
            linhas.append(f"| `{nome}` | {desc.replace('|', '/')} |")
        open(os.path.join(d, "INDICE.md"), "w", encoding="utf-8", newline="\n").write("\n".join(linhas) + "\n")
    print("Índices gerados." + (" FALTA DESCRIÇÃO em: " + ", ".join(faltando) if faltando else " Todos os arquivos têm descrição."))
    return 1 if faltando else 0

if __name__ == "__main__":
    sys.exit(main())
