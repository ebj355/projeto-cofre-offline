# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Cobertura local: quanto do cofre_senhas.py os testes do NUCLEO realmente executam.

Roda cada teste de testes\\1_TESTE_motor_do_cofre\\teste_*.py sob o `coverage` (que ja esta no
requirements-test-lock.txt, nenhum pacote novo), junta os resultados e grava o relatorio em
testes\\resultados\\cobertura_codigo.txt. E INFORMATIVO: nao reprova nada. Serve para achar trechos do cofre que
nenhum teste exercita. Os dados de trabalho ficam em CACHE_PROJETO_NAO_MEXER, nada solto na raiz do projeto.
Quando um teste termina com codigo diferente de zero (ou estoura o tempo), o texto que ele escreveu na tela e
gravado em testes\\resultados\\cobertura_saida_testes.txt, para voce poder me mandar.

Uso (na raiz do projeto):  python <esta pasta>\\14_COBERTURA_DO_CODIGO.py [--filtro texto]
Demora (cada teste roda por inteiro, Argon2 incluido); rode quando nao precisar do computador."""
import glob
import os
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))


def _achar_raiz(inicio):
    """Sobe pastas ate achar a raiz do projeto (a que tem o cofre_senhas.py): a pasta pode ficar em qualquer lugar."""
    d = inicio
    while not os.path.exists(os.path.join(d, "cofre_senhas.py")):
        pai = os.path.dirname(d)
        if pai == d:
            raise SystemExit("ERRO: nao achei o cofre_senhas.py acima de " + inicio)
        d = pai
    return d


RAIZ = _achar_raiz(AQUI)
ALVO = os.path.join(RAIZ, "cofre_senhas.py")
TRABALHO = os.path.join(RAIZ, "CACHE_PROJETO_NAO_MEXER", "testes", "coverage")
SAIDA = os.path.join(RAIZ, "testes", "resultados", "cobertura_codigo.txt")
SAIDA_ERROS = os.path.join(RAIZ, "testes", "resultados", "cobertura_saida_testes.txt")
LIMITE_POR_TESTE = 900      # segundos
MAX_CHARS_ERRO = 6000       # guarda so o final da saida de cada teste que falhou
# Testes que dependem de recursos que o Windows nao tem (teste_memoria le /proc/<pid>/mem, que so existe no Linux).
# Aqui eles sao apenas registrados como "nao se aplica", sem contar como erro.
SO_LINUX = {"teste_memoria.py"}


def rodar(args, **k):
    return subprocess.run([sys.executable, "-m", "coverage"] + args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=RAIZ, **k)


def _texto(valor):
    if valor is None:
        return ""
    if isinstance(valor, bytes):
        return valor.decode("utf-8", "replace")
    return valor


def main():
    filtro = sys.argv[sys.argv.index("--filtro") + 1].lower() if "--filtro" in sys.argv else ""
    if rodar(["--version"]).returncode != 0:
        print("[PULADO] o pacote 'coverage' nao esta instalado neste Python (ele esta no requirements-test-lock.txt).")
        return 2
    testes = sorted(glob.glob(os.path.join(RAIZ, "testes", "1_TESTE_motor_do_cofre", "teste_*.py")))
    testes = [t for t in testes if filtro in os.path.basename(t).lower()]
    if not testes:
        print("[PULADO] nenhum teste do nucleo encontrado em testes\\1_TESTE_motor_do_cofre.")
        return 2
    os.makedirs(TRABALHO, exist_ok=True)
    os.makedirs(os.path.dirname(SAIDA), exist_ok=True)
    for velho in glob.glob(os.path.join(TRABALHO, ".coverage*")):
        os.remove(velho)
    if os.path.exists(SAIDA_ERROS):
        os.remove(SAIDA_ERROS)
    env = dict(os.environ, COVERAGE_FILE=os.path.join(TRABALHO, ".coverage"),
               COFRE_TESTE_SEM_JANELA_FATAL="1",                    # um aviso fatal nao pode prender a rodada esperando OK
               PYTHONUTF8="1", PYTHONIOENCODING="utf-8",            # sem isso o Windows usa cp1252 e os testes quebram em setas, emoji e CJK
               PYTHONPATH=RAIZ + os.pathsep + os.environ.get("PYTHONPATH", ""))   # subprocessos dos testes acham os modulos
    linhas = [f"Cobertura de {os.path.basename(ALVO)} pelos testes do nucleo", time.strftime("%Y-%m-%d %H:%M:%S"), ""]
    falhos = 0
    for i, t in enumerate(testes, 1):
        nome = os.path.basename(t)
        if os.name == "nt" and nome in SO_LINUX:
            print(f"  [{i}/{len(testes)}] {nome}: nao se aplica no Windows (pulado)", flush=True)
            linhas.append(f"{nome}: nao se aplica no Windows (pulado)")
            continue
        ini = time.time()
        saida_texto = ""
        try:
            p = rodar(["run", "--parallel-mode", f"--include={ALVO}", t], env=env, timeout=LIMITE_POR_TESTE)
            ok = p.returncode == 0
            estado = "ok" if ok else f"codigo {p.returncode} (a cobertura dele conta mesmo assim)"
            saida_texto = _texto(p.stdout) + _texto(p.stderr)
        except subprocess.TimeoutExpired as ex:
            ok = False
            estado = f"INTERROMPIDO apos {LIMITE_POR_TESTE} s"
            saida_texto = _texto(ex.stdout) + _texto(ex.stderr)
        if not ok:
            falhos += 1
            with open(SAIDA_ERROS, "a", encoding="utf-8") as f:
                f.write(f"===== {nome}: {estado} =====\n")
                f.write((saida_texto.strip()[-MAX_CHARS_ERRO:] or "(o teste nao escreveu nada na tela)") + "\n\n")
        print(f"  [{i}/{len(testes)}] {nome}: {estado} ({time.time() - ini:.0f} s)", flush=True)
        linhas.append(f"{nome}: {estado}")
    rodar(["combine", "--quiet"], env=env)
    rel = rodar(["report", f"--include={ALVO}", "--show-missing"], env=env)
    linhas += ["", rel.stdout.strip() or rel.stderr.strip() or "(sem dados de cobertura)"]
    with open(SAIDA, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")
    ultima = [x for x in rel.stdout.splitlines() if x.strip()]
    print("\n" + (ultima[-1] if ultima else "sem dados") + f"\nRelatorio completo: {SAIDA}")
    if falhos:
        print(f"{falhos} teste(s) terminaram com erro; o texto deles esta em: {SAIDA_ERROS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
