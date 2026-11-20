"""Executa TODOS os testes do cofre e mostra um resumo.

Uso (na pasta do projeto):
    python testes/6_TESTE_ferramentas_dos_testes/rodar_todos.py              # tudo (núcleo + interface)
    python testes/6_TESTE_ferramentas_dos_testes/rodar_todos.py --rapido     # só o núcleo (sem janelas)
    python testes/6_TESTE_ferramentas_dos_testes/rodar_todos.py --so gui     # só a interface   (ou: --so nucleo)
    python testes/6_TESTE_ferramentas_dos_testes/rodar_todos.py --filtro fido

No Linux sem tela, a interface roda dentro do `xvfb-run` (precisa estar instalado).
No Windows, as janelas dos testes de interface são não ativáveis e ficam atrás do aplicativo em uso.
Sai com código 0 só se tudo passou. Um teste conta como FALHA se imprimir "[FALHOU]", "FALHAS: [...]" com
conteúdo, "FAIL" ou "[X]", se terminar com código diferente de 0 ou se passar do tempo limite."""
import argparse
import datetime
import glob
import os
import re
import shutil
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))        # testes/6_TESTE_ferramentas_dos_testes
RAIZ_TESTES = os.path.dirname(AQUI)                       # testes/ (onde ficam nucleo/ e gui/)
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _resultado  # log de depuração (testes/resultados/log_depuracao.txt)
from _cache_testes import preparar_cache_temporario

for fluxo in (sys.stdout, sys.stderr):
    if hasattr(fluxo, "reconfigure"):
        fluxo.reconfigure(errors="replace")

ruim = re.compile(r"\[FALHOU\]|\[X\]|\bFAIL\b|FALHAS( v\d+)?: \[[^\]]|\bKeyboardInterrupt\b")
bom = re.compile(r"TODOS( OS TESTES)? (PASSARAM|OK)|FALHAS( v\d+)?: \[\]|\[OK\]|FIM-OK")


def python_da_interface():
    """Python que tem o tkinter (no Linux o python3.12 do sistema costuma ter; senão usa o atual)."""
    if os.name == "nt":
        return sys.executable
    for c in ("/usr/bin/python3.12", "/usr/bin/python3"):
        if os.path.exists(c) and subprocess.run([c, "-c", "import tkinter"], capture_output=True).returncode == 0:
            return c
    return sys.executable


def roda(nome, cmd, cwd, limite):
    t0 = time.time()
    try:
        # UTF-8 nos filhos e na leitura: o console do Windows usa cp850/cp1252 e quebraria os acentos e símbolos
        amb = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
        if (os.name == "nt" and nome.startswith("gui/")
                and os.environ.get("COFRE_GUI_TESTS_FOREGROUND") != "1"):
            pasta_gui = os.path.join(RAIZ_TESTES, "2_TESTE_telas_e_botoes")
            caminhos = [pasta_gui, amb.get("PYTHONPATH", "")]
            amb["PYTHONPATH"] = os.pathsep.join(p for p in caminhos if p)
            amb["COFRE_GUI_TESTS_BACKGROUND"] = "1"
        _resultado.esperar_memoria(1000, 180)           # não começa nada pesado com o PC sem RAM livre
        extra = {"creationflags": 0x00004000} if os.name == "nt" else {"preexec_fn": lambda: os.nice(10)}   # prioridade baixa
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                errors="replace", env=amb, **extra)
        try:
            while True:                                  # sinal de vida a cada 30 s: um teste longo não parece travado
                try:
                    out, _ = proc.communicate(timeout=30)
                    break
                except subprocess.TimeoutExpired:
                    dec = time.time() - t0
                    if dec > limite:
                        proc.kill()
                        out, _ = proc.communicate()
                        raise subprocess.TimeoutExpired(cmd, limite, output=out)
                    print("          ... %s continua rodando (%d s)" % (nome, dec), flush=True)
        except subprocess.TimeoutExpired:
            raise
        r = subprocess.CompletedProcess(cmd, proc.returncode, out, "")
        time.sleep(0.5)                                  # respiro entre testes: o Windows devolve memória/janelas
        saida, codigo = (r.stdout or "") + (r.stderr or ""), r.returncode
    except subprocess.TimeoutExpired as e:
        saida, codigo = ((e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")), -999
    linhas = saida.splitlines()
    ruins = [l.strip() for l in linhas if ruim.search(l)]
    bons = any(bom.search(l) for l in linhas)
    tracebacks = sum(1 for l in linhas if l.startswith("Traceback"))
    if codigo == -999:
        estado = "FALHOU (tempo esgotado)"
    elif ruins:
        estado = "FALHOU"
    elif codigo == 9 and any(l.strip().casefold().startswith("pulado: hypothesis indisponivel") for l in linhas):
        estado = "PULADO (Hypothesis indisponível)"
    elif codigo != 0:
        estado = "FALHOU (código %s)" % codigo
    elif bons or not linhas:
        estado = "ok"
    else:
        estado = "ok (sem marcador de sucesso)"
    return estado, ruins, tracebacks, time.time() - t0, saida


def main():
    preparar_cache_temporario("bateria")
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapido", action="store_true", help="só o núcleo, sem janelas")
    ap.add_argument("--so", choices=("nucleo", "gui"))
    ap.add_argument("--filtro", default="")
    ap.add_argument("--limpar", action="store_true", help="apaga os resultados da bateria anterior antes de começar")
    ap.add_argument("--sem-dev", action="store_true", help="sem -X dev/-W error (para Pythons em que o modo dev trava no Windows)")
    ap.add_argument("-v", action="store_true", help="mostra a saída dos que falharam")
    a = ap.parse_args()
    if a.limpar:
        _resultado.limpar_resultados_antigos()
    py = sys.executable
    tarefas = []
    if a.so != "gui":
        for f in sorted(glob.glob(os.path.join(RAIZ_TESTES, "1_TESTE_motor_do_cofre", "teste_*.py"))):
            n = os.path.basename(f)
            if n == "teste_memoria.py" and not sys.platform.startswith("linux"):
                continue                                  # lê /proc/<pid>/mem: só existe no Linux
            # o soak (1.000 ciclos) fica fora do modo dev: ele deixa o teste 50x mais lento (de ~13 s para ~11 min)
            flags = [] if (a.sem_dev or os.name == "nt" or n in ("teste_severo.py", "teste_backup.py", "teste_nucleo_soak_longa_duracao.py")) else ["-X", "dev", "-W", "error"]
            tarefas.append(("nucleo/" + n, [py] + flags + [f], os.path.dirname(f), 1500))
    if a.so != "nucleo" and not a.rapido:
        pg = python_da_interface()
        xv = [] if (os.name == "nt" or os.environ.get("DISPLAY")) else (["xvfb-run", "-a", "-s", "-screen 0 1600x1000x24"] if shutil.which("xvfb-run") else None)
        if xv is None:
            print("AVISO: sem tela e sem xvfb-run: testes de interface pulados.")
        else:
            for f in sorted(glob.glob(os.path.join(RAIZ_TESTES, "2_TESTE_telas_e_botoes", "teste_*.py"))):
                tarefas.append(("gui/" + os.path.basename(f), xv + [pg] + ([] if (a.sem_dev or os.name == "nt" or "soak" in os.path.basename(f)) else ["-X", "dev"]) + [f], os.path.dirname(f), 900 if "soak" in os.path.basename(f) else 400))   # Windows/dev e soak: sem modo dev (lento/incompatível) e com mais tempo
    tarefas = [t for t in tarefas if a.filtro in t[0]]
    falhas = pulados = 0
    for nome, cmd, cwd, lim in tarefas:
        # mostra qual teste está rodando ANTES de começar (alguns, como o de desempenho/força bruta, usam Argon2id
        # no nível alto/máximo de propósito devagar — sem isto a tela ficava muda por minutos nesses e parecia
        # travada, já que só imprimíamos o resumo depois que o teste terminava)
        print("[rodando] %s..." % nome, flush=True)
        inicio = datetime.datetime.now()
        estado, ruins, tb, seg, saida = roda(nome, cmd, cwd, lim)
        _resultado.log_depuracao('geral', nome, cmd, estado, seg, saida, inicio)   # saída COMPLETA vai para o log de depuração
        _resultado.gravar_resultado_executor(nome, estado, seg, saida)
        if estado.startswith("FALHOU"):
            marca, detalhe = "FALHOU", estado
        elif estado.startswith("PULADO"):
            marca, detalhe = "PULADO", estado
            pulados += 1
        else:
            marca, detalhe = "  ok  ", ""
        extra = "  (%d aviso(s) de Traceback, ruído de -W error)" % tb if tb and marca == "  ok  " else ""
        print("[%s] %-38s %5.1fs  %s%s" % (marca, nome, seg, detalhe, extra))
        if marca == "FALHOU":
            falhas += 1
            for l in ruins[:5]:
                print("          >", l[:150])
            if a.v:
                print("\n".join("          | " + l for l in saida.splitlines()[-25:]))
    print("\n%d teste(s), %d falha(s), %d pulado(s)." % (len(tarefas), falhas, pulados))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
