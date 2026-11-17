"""COBERTURA DE CÓDIGO (coverage.py): quais linhas e ramificações de cofre_senhas.py os testes realmente executam.

Para quê: achar blocos de tratamento de erro importantes (falha de descriptografia, timeout de E/S em pendrive, queda no meio
da gravação...) que NENHUM teste automatizado exercita. Linha coberta não prova que está certa, mas linha NÃO coberta é um
ponto cego garantido.
Como: roda cada teste do núcleo e do pentest como processo separado sob `coverage run --parallel-mode` (com ramificações),
junta os dados e grava em testes/resultados/: cobertura_codigo.txt (resumo + as faixas de linhas sem cobertura, com o texto
da linha), cobertura_codigo.json e a pasta cobertura_html/ (relatório navegável). Os testes de interface ficam de fora
por padrão (são lentos); inclua com --gui. Se o `coverage` não estiver instalado, tenta instalar; se não der, avisa e sai
com código 0 (cobertura é uma ferramenta de análise, nunca uma falha de teste).
Uso: python testes/ferramentas_dos_testes/cobertura_codigo.py [--gui] [--filtro texto] [--minimo 0]   (--minimo N: sai com 1 se cobrir menos de N%)"""
import argparse, glob, json, os, subprocess, sys, time

AQUI = os.path.dirname(os.path.abspath(__file__))
TESTES = os.path.dirname(AQUI)
RAIZ = os.path.dirname(TESTES)
RES = os.path.join(TESTES, "resultados")
PROG = os.path.join(RAIZ, "cofre_senhas.py")


def tem_coverage():
    return subprocess.run([sys.executable, "-c", "import coverage"], capture_output=True).returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gui", action="store_true", help="inclui os testes de interface (lentos)")
    ap.add_argument("--filtro", default="")
    ap.add_argument("--minimo", type=float, default=0.0)
    a = ap.parse_args()
    if not tem_coverage():
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "coverage"],
                       capture_output=True)
        if not tem_coverage():
            print("coverage não está instalado e não deu para instalar (sem internet?): cobertura pulada.")
            return 0
    os.makedirs(RES, exist_ok=True)
    dados = os.path.join(RES, ".coverage")
    for velho in glob.glob(dados + "*"):
        os.remove(velho)
    rc = os.path.join(RES, ".coveragerc")
    with open(rc, "w", encoding="utf-8") as f:
        f.write("[run]\nbranch = True\nparallel = True\ndata_file = %s\nsource_pkgs =\ninclude = %s\n[report]\nshow_missing = True\n"
                % (dados, PROG))
    testes = sorted(glob.glob(os.path.join(TESTES, "1_motor_do_cofre", "teste_*.py")) + glob.glob(os.path.join(TESTES, "3_ataques_simulados", "teste_pentest_*.py")))
    if a.gui:
        testes += sorted(glob.glob(os.path.join(TESTES, "2_telas_e_botoes", "teste_gui_*.py")))
    testes = [t for t in testes if a.filtro in os.path.basename(t)]
    amb = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", COFRE_SOAK_CICLOS="30")
    ruins = []
    t0 = time.time()
    for t in testes:
        nome = os.path.basename(t)
        if "soak" in nome or nome in ("teste_pentest_dependencias.py", "teste_pentest_sast.py", "teste_desempenho_forca_bruta.py"):
            continue                                              # lentos, ou dependem de rede/ferramentas e não exercitam o programa
        print("[cobertura] %s" % nome, flush=True)
        try:
            subprocess.run([sys.executable, "-m", "coverage", "run", "--rcfile", rc, t], cwd=os.path.dirname(t),
                           capture_output=True, timeout=600, env=amb)
        except subprocess.TimeoutExpired:
            ruins.append(nome + " (tempo)")
    subprocess.run([sys.executable, "-m", "coverage", "combine", "--rcfile", rc, "--quiet"], capture_output=True, cwd=RES)
    rel = subprocess.run([sys.executable, "-m", "coverage", "report", "--rcfile", rc, "--show-missing"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    subprocess.run([sys.executable, "-m", "coverage", "html", "--rcfile", rc, "-d", os.path.join(RES, "cobertura_html")],
                   capture_output=True)
    subprocess.run([sys.executable, "-m", "coverage", "json", "--rcfile", rc, "-o", os.path.join(RES, "cobertura_codigo.json")],
                   capture_output=True)
    pct, faltam = 0.0, []
    try:
        with open(os.path.join(RES, "cobertura_codigo.json"), encoding="utf-8") as f:
            j = json.load(f)
        arq = next(iter(j["files"].values()))
        pct = j["totals"]["percent_covered"]
        faltam = arq["missing_lines"]
        fonte = open(PROG, encoding="utf-8", errors="replace").read().splitlines()
    except (OSError, ValueError, StopIteration, KeyError):
        fonte = []
    # junta linhas sem cobertura vizinhas em faixas e mostra o começo de cada uma
    faixas = []
    for n in faltam:
        if faixas and n - faixas[-1][1] <= 2:
            faixas[-1][1] = n
        else:
            faixas.append([n, n])
    linhas = ["COBERTURA DE CÓDIGO de cofre_senhas.py (linhas + ramificações)",
              "Testes executados sob coverage: %d em %.0fs%s" % (len(testes), time.time() - t0,
                                                                 " | com tempo esgotado: %s" % ruins if ruins else ""),
              "Cobertura total: %.1f%%  |  linhas sem cobertura: %d em %d faixas" % (pct, len(faltam), len(faixas)), "",
              "Faixas SEM cobertura (linha inicial - final: texto da primeira linha). Foque nos blocos 'except' e de erro:"]
    for ini, fim in faixas:
        txt = fonte[ini - 1].strip()[:90] if 0 < ini <= len(fonte) else ""
        marca = "  <== tratamento de erro" if txt.startswith(("except", "raise", "return None")) else ""
        linhas.append("  %5d-%-5d %s%s" % (ini, fim, txt, marca))
    linhas += ["", "Relatório navegável: testes/resultados/cobertura_html/index.html"]
    saida = "\n".join(linhas)
    print(saida[:3000])
    with open(os.path.join(RES, "cobertura_codigo.txt"), "w", encoding="utf-8") as f:
        f.write(saida + "\n")
    return 1 if (a.minimo and pct < a.minimo) else 0


if __name__ == "__main__":
    sys.exit(main())
