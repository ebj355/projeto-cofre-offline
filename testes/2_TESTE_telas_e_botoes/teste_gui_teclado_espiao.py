# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Teclado virtual e ferramentas espiãs: a tela mostra a dica do teclado; com depurador/espião aberto o cofre recusa abrir ou se bloqueia (sem destruir o arquivo nem gastar tentativa)."""
import os as _os, sys as _sys, tempfile as _tf, subprocess as _sp
_RAIZ = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".."))
def _foto(arq):
    """Captura a tela (só onde existe o ImageMagick 'import'); sem ele, ignora."""
    try: _sp.run(["import", "-window", "root", arq], check=False)
    except Exception: pass
import faulthandler; faulthandler.dump_traceback_later(45, exit=True)
import os, sys
sys.path.insert(0, _RAIZ)
import tkinter as tk, cofre_senhas as c
from tkinter import messagebox
f = []
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
W = _tf.mkdtemp(prefix="cofre_gui_"); P = os.path.join(W, "b.dat")
for x in (P, P + ".tmp"):
    if os.path.exists(x): os.remove(x)
SENHA = "cavalo azul come pizza na chuva"
v = c.Cofre.criar(P, SENHA, 5, c.MODO_OU, "alto"); v.registros.append(c.novo_item(servico="Banco", senha="x")); v.salvar()
log = []
messagebox.showwarning = lambda *a, **k: log.append(("aviso", a[0]))
messagebox.showerror = lambda *a, **k: log.append(("erro", a[0]))
root = tk.Tk(); app = c.App(root, P)
def labels(w, acc):
    for ch in w.winfo_children():
        try: acc.append(str(ch.cget("text")))
        except Exception: pass
        labels(ch, acc)
    return acc
root.update()
def _todos(w):
    for ch in w.winfo_children():
        yield ch; yield from _todos(ch)
_av = next(w for w in _todos(app.frame) if w.winfo_class() == "TButton" and str(w.cget("text")).startswith("Avançado"))
_av.invoke(); root.update()      # a dica fica no painel "Avançado" (tela de desbloqueio mínima)
txts = labels(root, [])
ok(any("Teclado da tela disponível" in t for t in txts), "tela mostra dica do teclado virtual (painel Avançado)")
# 1) desbloqueio recusado com ferramenta espiã aberta
orig = c.ferramentas_espias
c.ferramentas_espias = lambda nomes=None: ["x64dbg.exe"]
app.tela_desbloqueio(); root.update()
ents = [w for w in root.winfo_children()]
def achar(w, cls):
    r = []
    for ch in w.winfo_children():
        if ch.winfo_class() == cls: r.append(ch)
        r += achar(ch, cls)
    return r
e = achar(root, "TEntry")[0]; e.insert(0, SENHA)
bt = [b for b in achar(root, "TButton") if str(b.cget("text")).startswith("Desbloquear")][0]
bt.invoke(); root.update()
ok(app.cofre is None and any("x64dbg.exe" in t for t in labels(root, [])), "recusa desbloquear com x64dbg aberto, sem gastar tentativa")
ok(c.info_cofre(P)[0] == 5, "nenhuma tentativa gasta")
# 2) abrir normalmente e depois aparece a ferramenta
c.ferramentas_espias = orig
app.cofre = c.Cofre.abrir(P, senha=SENHA); app.tela_principal(); root.update()
c.ferramentas_espias = lambda nomes=None: ["cheatengine-x86_64.exe"]
app._ultimo_tique = __import__("time").time()
for _ in range(8):      # a lista de processos é lida em outra thread: o aviso chega no tique seguinte
    app._vigiar_sistema(); __import__("time").sleep(0.1); app._ultimo_tique = __import__("time").time(); root.update()
    if app.cofre is None: break
ok(app.cofre is None and ("aviso", "Ferramenta espiã detectada") in log, "ferramenta espiã aberta com o cofre aberto -> bloqueia e avisa")
ok(os.path.exists(P), "arquivo NÃO é destruído por ferramenta espiã (só bloqueia)")
c.ferramentas_espias = orig
# 3) depurador ligado com o cofre aberto -> destrói
app.cofre = c.Cofre.abrir(P, senha=SENHA)
c.ambiente_suspeito = lambda: "Um depurador está ligado ao programa."
app._ultimo_tique = __import__("time").time()
app._vigiar_sistema()
ok(os.path.exists(P) and app.cofre is None and ("erro", "Depurador detectado") in log, "depurador ligado com o cofre aberto -> fecha, apaga chaves da memória e PRESERVA o arquivo")
print("\nTODOS OK" if all(f) else "\nHOUVE FALHAS")
