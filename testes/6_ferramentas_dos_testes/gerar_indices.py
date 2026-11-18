"""Gera o INDICE.md de cada pasta de testes (e atualiza o MAPA dos testes): uma linha por arquivo dizendo PARA QUE SERVE
(primeira linha do texto de abertura de cada .py; descrição escrita à mão para .bat/.ps1/.md) e POR QUE está naquela pasta.
Arquivo novo SEM descrição aparece como 'FALTA DESCRIÇÃO' e o programa sai com erro: assim nenhum arquivo fica sem explicação.
Uso: python testes/ferramentas_dos_testes/gerar_indices.py"""
import ast, os, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
TESTES = os.path.dirname(AQUI)
PASTAS = {
    "1_motor_do_cofre": ("Testes do NÚCLEO (sem janelas)", "Provam o motor do cofre: criptografia, arquivo, backups, tentativas, importação, falhas de disco. Rodam no Linux e no Windows, rápidos, sem tela. Cada `teste_*.py` é independente."),
    "2_telas_e_botoes": ("Testes da INTERFACE (janelas Tk)", "Abrem as telas de verdade (no Linux com tela virtual `xvfb-run`; no Windows em janelas reais) e clicam/digitam como um usuário. Cada `teste_gui_*.py` é independente."),
    "3_ataques_simulados": ("Testes de SEGURANÇA ofensiva (pentest)", "Tentam ATACAR o cofre (injeção, força bruta, DoS, vazamento de memória, engenharia reversa, rede, instalador) para provar que as defesas funcionam."),
    "4_so_no_windows": ("Testes que SÓ fazem sentido no Windows real", "Conferem o que o Linux só consegue simular: atributos de arquivo, permissões (ACL), DPAPI, SMBIOS, instalador, Windows Sandbox."),
    "ferramentas_dos_testes": ("Ferramentas COMPARTILHADAS pelos testes", "Não são testes do cofre: são os executores (`rodar_*`), os ajudantes (`_resultado`, `_util_mem`), a limpeza, a cobertura e os relatórios. Também os documentos do plano de testes."),
}
MANUAL = {   # arquivos que não são .py (ou que não têm texto de abertura): para que serve + por que está aqui
    "ferramentas_dos_testes/rodar_todos_windows.bat": "Roda as 5 baterias no Windows em sequência e junta os resultados (é o que o 2 - TESTAR TUDO - roda todos os testes.bat da raiz chama). Fica em ferramentas_dos_testes/ porque usa todas as pastas.",
    "ferramentas_dos_testes/cobertura_codigo_windows.bat": "Atalho de dois cliques para medir a cobertura de código no Windows (chama cobertura_codigo.py). Fora do Testar_Tudo de propósito: é lento.",
    "2_telas_e_botoes/RODAR ESTA PASTA - testes das telas e botoes.bat": "Atalho de dois cliques da bateria de INTERFACE no Windows (chama teste_gui_windows.ps1).",
    "2_telas_e_botoes/teste_gui_windows.ps1": "Prepara um ambiente Python temporário e roda a bateria de interface (rodar_todos.py --so gui) no Windows, gravando o resultado.",
    "1_motor_do_cofre/RODAR ESTA PASTA - testes do motor do cofre.bat": "Atalho de dois cliques da bateria do NÚCLEO no Windows (ambiente Python temporário próprio).",
    "1_motor_do_cofre/PECA_DE_TESTE_cofre_versao_4_antiga.py": "FIXTURE (peça de teste, não é teste): cópia do programa na versão 4 antiga. Serve só para o teste_severo provar que cofres do formato antigo ainda abrem. Não apagar.",
    "3_ataques_simulados/RODAR ESTA PASTA - testes de ataque simulado.bat": "Atalho de dois cliques da bateria de PENTEST no Windows (chama rodar_pentest.py com Python temporário).",
    "4_so_no_windows/A - testar o instalador.bat": "Atalho de dois cliques do teste do INSTALADOR no Windows (chama teste_windows.ps1).",
    "4_so_no_windows/teste_windows.ps1": "Valida o instalador e o programa no Windows real (pastas, atributos, compilação, SmartScreen etc.).",
    "4_so_no_windows/instalador.Tests.ps1": "Testes Pester (PowerShell) do instalar_cofre.ps1: funções internas do instalador. Chamado por teste_windows.ps1.",
    "4_so_no_windows/B - testar atributos e permissoes do Windows.bat": "Atalho de dois cliques do teste NATIVO (atributos, ACL, DPAPI, SMBIOS, DLLs). Aceita a letra do pendrive: B - testar atributos e permissoes do Windows.bat H.",
    "4_so_no_windows/C - testar o Windows tambem no pendrive H.bat": "Atalho que já roda o teste nativo também no pendrive H: (troque a letra dentro do arquivo se o seu for outro).",
    "4_so_no_windows/D - testar no Windows Sandbox limpo.wsb": "Configuração do Windows Sandbox: abre um Windows LIMPO e descartável com o projeto copiado, para testar a instalação do zero. Opcional.",
    "ferramentas_dos_testes/test_pytest.py": "Ponte OPCIONAL para o pytest (cada teste vira um caso do pytest). Não é usada pelo Testar_Tudo.",
}
POR_QUE = {"1_motor_do_cofre": "motor do cofre, sem tela", "2_telas_e_botoes": "precisa de janela", "3_ataques_simulados": "ataque/segurança", "4_so_no_windows": "precisa do Windows real", "ferramentas_dos_testes": "serve a todas as baterias"}

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
                  "_Gerado por `testes/ferramentas_dos_testes/gerar_indices.py` (não edite à mão: rode o script)._", "",
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
