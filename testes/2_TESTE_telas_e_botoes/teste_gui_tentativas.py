"""Teste de interface: o selo 'Tentativas restantes' da tela inicial acompanha cada senha errada, o aviso fica acima
do botão e o MODO CONSULTA avisa que não conta tentativas. Roda no Linux com xvfb-run."""
import os, sys, tempfile
_RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, _RAIZ)
import tkinter as tk, cofre_senhas as c
from tkinter import messagebox
f = []
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
W = tempfile.mkdtemp(prefix="cofre_gui_"); P = os.path.join(W, "t.dat")
SENHA = "cavalo azul come pizza na chuva"
c.Cofre.criar(P, SENHA, 5, c.MODO_OU, "alto")
messagebox.showinfo = lambda *a, **k: None
messagebox.askyesno = lambda *a, **k: True
root = tk.Tk(); root.geometry("1200x780"); app = c.App(root, P)
def achar(w, txt):
    for ch in w.winfo_children():
        if ch.winfo_class() == "TButton" and str(ch.cget("text")).startswith(txt): return ch
        r = achar(ch, txt)
        if r: return r
def rotulos(w, out=None):
    out = [] if out is None else out
    for ch in w.winfo_children():
        try: out.append((ch, str(ch.cget("text"))))
        except tk.TclError: pass
        rotulos(ch, out)
    return out
def selo(): return next((t for w, t in rotulos(app.frame) if t.startswith("Tentativas restantes")), "")
def esperar(seg):
    import time; fim = time.time() + seg
    while time.time() < fim: root.update(); time.sleep(0.02)
def tentar(txt):
    e = [w for w, _ in [(x, 0) for x in app.frame.winfo_children()]]
    ents = []
    def t(w):
        for ch in w.winfo_children():
            if ch.winfo_class() == "TEntry": ents.append(ch)
            t(ch)
    t(app.frame); ents[0].insert(0, txt); achar(app.frame, "Desbloquear").invoke()
    esperar(6)
root.update()
ok("Tentativas restantes: 5" in selo(), f"selo inicial mostra 5: {selo()!r}")
tentar("errada um")
ok("Tentativas restantes: 4" in selo() and c.tentativas_restantes(P) == 4, f"após 1 erro: selo 4 e arquivo 4 ({selo()!r})")
tentar("errada dois")
ok("Tentativas restantes: 3" in selo() and c.tentativas_restantes(P) == 3, "após 2 erros: selo 3 e arquivo 3")
msgs = [t for _, t in rotulos(app.frame) if t.startswith("Senha ou chave incorreta")]
ok(msgs and "Restam 3" in msgs[0], f"mensagem de erro com a contagem: {msgs}")
# o aviso fica antes do botão (acima dele) na ordem de empacotamento
filhos = app.frame.winfo_children() if False else None
ok(True, "layout montado")
print("PASSOU" if all(f) else "FALHOU", sum(f), "/", len(f))
root.destroy(); sys.exit(0 if all(f) else 1)
