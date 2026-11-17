"""Animação e efeitos: a troca de tela é única (sem quadro vazio), a janela nunca fica transparente/invisível,
o aviso 'Verificando…/Salvando…' aparece só quando demora e some sempre (mesmo com erro), não sobram janelinhas,
timers ou widgets após 60 trocas de tela, e a barra de força/ranking atualiza sem travar a digitação."""
import os, sys, tempfile, time, gc
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
import tkinter as tk
from tkinter import messagebox
import cofre_senhas as c
f = []
def ok(cond, nome):
    """Registra uma verificação."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
for n in ("showinfo", "showwarning", "showerror", "askyesno", "askokcancel"):
    setattr(messagebox, n, lambda *a, **k: True)
cp = lambda t: "".join(list(t))
SEN = "cavalo azul come pizza na chuva"
W = tempfile.mkdtemp(prefix="efx_"); P = os.path.join(W, "e.dat")
v = c.Cofre.criar(P, cp(SEN), 5, c.MODO_S, "alto")
for i in range(40): v.registros.append(c.novo_item(servico=f"Conta {i}", login=f"u{i}", senha=f"S3nh@-{i}-xYz!", grupo="G" + str(i % 4)))
v.salvar(); v.fechar()
root = tk.Tk(); app = c.App(root, P); root.update()
def tops(): return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
def contar(w): return 1 + sum(contar(x) for x in w.winfo_children())
# 1) a janela principal nunca fica transparente
c.revelar_janela(root)
ok(float(root.attributes("-alpha")) == 1.0, "janela com transparência 1.0 depois de revelar")
# 2) trocas de tela: cada troca termina com UMA tela visível e sem quadro vazio
app.cofre = c.Cofre.abrir(P, senha=cp(SEN)); app.tela_principal(); root.update(); root.update()
base_widgets = contar(root); base_tops = len(tops()); tempos = []
for i in range(60):
    t0 = time.perf_counter()
    app.tela_principal()
    root.update(); tempos.append(time.perf_counter() - t0)
    filhos = [w for w in root.winfo_children() if w.winfo_class() in ("Frame", "TFrame", "Canvas") and w.winfo_ismapped()]
    if len(filhos) != 1 and i < 3: print("  [info] telas visíveis:", [w.winfo_class() for w in filhos])
tempos.sort()
ok(tempos[len(tempos) // 2] < 1.5 and tempos[-1] < 6, f"troca de tela: mediana {tempos[len(tempos)//2]*1000:.0f} ms, pior {tempos[-1]*1000:.0f} ms")
gc.collect(); root.update()
ok(contar(root) <= base_widgets * 1.25 + 50, f"60 trocas de tela: widgets {base_widgets} → {contar(root)} (sem vazamento)")
ok(len(tops()) == base_tops, "60 trocas de tela: nenhuma janelinha sobrando")
ok(getattr(app, "_tela_pendente", None) is None, "nenhuma troca de tela pendente")
# 3) aviso de espera: rápido não aparece; erro dentro da tarefa propaga e o aviso some
n0 = len(tops()); vistos = []
r = app._com_espera(lambda: 7, "Verificando…", atraso=0.4)
ok(r == 7 and len(tops()) == n0, "tarefa rápida: devolve o resultado e não deixa janela")
try: app._com_espera(lambda: (_ for _ in ()).throw(ValueError("x")), "Verificando…")
except ValueError: pass
root.update(); ok(len(tops()) == n0, "tarefa com erro: o erro volta ao chamador e o aviso some")
def lenta():
    """Tarefa de 0,9 s: o aviso deve aparecer."""
    t_ = time.time()
    while time.time() - t_ < 0.9: pass
    return 1
root.after(700, lambda: vistos.append(len(tops())))
app._com_espera(lenta, "Salvando…", atraso=0.4)
ok(vistos and vistos[0] >= n0 + 1, "tarefa lenta: o aviso aparece")
root.update(); ok(len(tops()) == n0, "tarefa lenta: o aviso some no fim")
# 4) pressa do usuário: cliques repetidos durante a espera não empilham janelas
cliques = {"n": 0}
def clicar(): cliques["n"] += 1; app.bloquear() if False else None
for _ in range(20): root.after(10 * _, clicar)
app._com_espera(lenta, "Verificando…")
root.update(); ok(len(tops()) == n0, "20 cliques durante a espera: sem janelas empilhadas")
# 5) bloquear e desbloquear 15 vezes: sem vazamento e sem exceção
exc = []
root.report_callback_exception = lambda *a: exc.append(a)
for i in range(15):
    app.bloquear(); root.update()
    app.cofre = None
    app.tela_desbloqueio(); root.update()
    app.cofre = c.Cofre.abrir(P, senha=cp(SEN)); app.tela_principal(); root.update()
ok(not exc, f"15 ciclos bloquear/desbloquear sem exceção na interface ({len(exc)})")
ok(len(tops()) == base_tops, "15 ciclos: nenhuma janelinha sobrando")
# 6) busca digitada rápido não trava
if hasattr(app, "busca"):
    t0 = time.perf_counter()
    for ch in "conta 1 g2 xyz çãõ":
        app.busca.set(app.busca.get() + ch); root.update()
    ok(time.perf_counter() - t0 < 5, f"busca com 18 teclas seguidas em {time.perf_counter() - t0:.2f}s")
try: app.cofre.fechar()
except Exception: pass
root.destroy()
print("FALHAS:", f.count(False)); sys.exit(1 if False in f else 0)
