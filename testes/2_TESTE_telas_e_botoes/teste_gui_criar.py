# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Tela de CRIAR o cofre (primeiro uso): campos da senha mestra, validações e criação do arquivo."""
import os as _os, sys as _sys, tempfile as _tf, subprocess as _sp
_RAIZ = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".."))
def _foto(arq):
    """Captura a tela (só onde existe o ImageMagick 'import'); sem ele, ignora."""
    try: _sp.run(["import", "-window", "root", arq], check=False)
    except Exception: pass
import os, sys, subprocess
sys.path.insert(0, _RAIZ)
import tkinter as tk, cofre_senhas as c
W = _tf.mkdtemp(prefix="cofre_gui_"); P = os.path.join(W, "novo.dat")
if os.path.exists(P): os.remove(P)
root = tk.Tk(); app = c.App(root, P)
def p():
    ents = []
    def t(w):
        for ch in w.winfo_children():
            if ch.winfo_class() == "TEntry": ents.append(ch)
            t(ch)
    t(app.frame)
    for ch in "senha123":
        ents[0].insert("end", ch); ents[0].event_generate("<KeyRelease>")
    root.update(); _foto(os.path.join(W, "criar.png"))
    root.destroy()
root.after(700, p); root.mainloop()
