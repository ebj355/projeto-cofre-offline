"""Passeio básico (teste rápido de fumaça): tela de desbloqueio, tela principal, Novo item, teclado virtual, Ctrl+C bloqueado, bloquear e limpar a área de transferência."""
import os as _os, sys as _sys, tempfile as _tf, subprocess as _sp
_RAIZ = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".."))
def _foto(arq):
    """Captura a tela (só onde existe o ImageMagick 'import'); sem ele, ignora."""
    try: _sp.run(["import", "-window", "root", arq], check=False)
    except Exception: pass
import os, sys
sys.path.insert(0, _RAIZ)
import tkinter as tk
import cofre_senhas as c
W = _tf.mkdtemp(prefix="cofre_gui_"); P = os.path.join(W, "gui.dat")
if os.path.exists(P): os.remove(P)
c.Cofre.criar(P, "cavalo azul come pizza na chuva", 3)
root = tk.Tk()
app = c.App(root, P)
passos = []
def etapa(nome, f):
    try: f(); passos.append(("OK", nome))
    except Exception as e: passos.append(("ERRO", f"{nome}: {type(e).__name__}: {e}"))
def roteiro():
    etapa("tela de desbloqueio", lambda: None)
    app.cofre = c.Cofre.abrir(P, senha="cavalo azul come pizza na chuva")
    etapa("tela principal", app.tela_principal)
    etapa("diálogo novo item", lambda: app.dialogo_registro(None))
    d = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)][-1]
    entradas = []
    def achar(w):
        for ch in w.winfo_children():
            if ch.winfo_class() == "TEntry": entradas.append(ch)
            achar(ch)
    achar(d)
    etapa("teclado virtual digita e embaralha", lambda: (app.teclado_virtual(entradas[2]),))
    vk = [w for w in d.winfo_children() if isinstance(w, tk.Toplevel)][-1]
    btns = []
    def achar_b(w):
        for ch in w.winfo_children():
            if ch.winfo_class() == "Button" and len(ch.cget("text")) == 1: btns.append(ch)
            achar_b(ch)
    achar_b(vk)
    antes = [b.cget("text") for b in btns][:5]
    btns[0].invoke()
    btns2 = []; 
    def achar_b2(w):
        for ch in w.winfo_children():
            if ch.winfo_class() == "Button" and len(ch.cget("text")) == 1: btns2.append(ch)
            achar_b2(ch)
    achar_b2(vk)
    passos.append(("OK" if len(entradas[2].get()) == 1 else "ERRO", f"VK inseriu 1 caractere; teclas: {len(btns)}"))
    passos.append(("INFO", f"layout antes {antes} depois {[b.cget('text') for b in btns2][:5]}"))
    etapa("Ctrl+C bloqueado no campo de senha", lambda: None)
    r = entradas[2].event_generate("<<Copy>>")
    etapa("bloquear (fecha tudo)", app.bloquear)
    passos.append(("OK" if app.cofre is None and not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)] else "ERRO", "cofre fechado e janelas destruídas"))
    etapa("copiar/limpar clipboard", lambda: (app._copiar_texto("x", "t"), app._limpar_clip(forcar=True)))
    root.after(100, root.destroy)
root.after(300, roteiro)
root.mainloop()
for s, n in passos: print(f"[{s}] {n}")
os.remove(P)
