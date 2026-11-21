# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Botão do 'olho' (mostrar/ocultar a senha): mostra, esconde sozinho depois de um tempo e continua sem permitir copiar."""
import os as _os, sys as _sys, tempfile as _tf, subprocess as _sp
_RAIZ = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".."))
def _foto(arq):
    """Captura a tela (só onde existe o ImageMagick 'import'); sem ele, ignora."""
    try: _sp.run(["import", "-window", "root", arq], check=False)
    except Exception: pass
import os, sys, subprocess, time
sys.path.insert(0, _RAIZ)
import tkinter as tk, cofre_senhas as c
f = []
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
W = _tf.mkdtemp(prefix="cofre_gui_"); P = os.path.join(W, "o.dat")
if os.path.exists(P): os.remove(P)
c.Cofre.criar(P, "cavalo azul come pizza na chuva", 3, c.MODO_E, "alto")
root = tk.Tk(); app = c.App(root, P); root.update()
def todos(w, cls):
    r = []
    for ch in w.winfo_children():
        if ch.winfo_class() == cls: r.append(ch)
        r += todos(ch, cls)
    return r
ents = todos(root, "TEntry"); olhos = [b for b in todos(root, "TButton") if b.cget("text") == "👁"]
ok(len(olhos) == 2, f"desbloqueio: olho na senha e na chave ({len(olhos)})")
e = ents[0]; e.insert(0, "minha senha secreta"); root.update()
olhos[0].invoke(); root.update()
ok(e.cget("show") == "", "clicar no olho mostra o texto")
_foto(os.path.join(W, "desbloqueio_olho.png"))
ok(e.bind("<Control-c>") != "", "continua sem permitir copiar")
olhos[0].invoke(); root.update()
ok(e.cget("show") == "•", "clicar de novo esconde")
app.MOSTRAR_SENHA_MS = 300
olhos[0].invoke(); root.update(); t0 = time.time()
while time.time() - t0 < 1: root.update(); time.sleep(0.02)
ok(e.cget("show") == "•", "esconde sozinho depois do tempo")
os.remove(P); app.tela_criar(); root.update()
olhos = [b for b in todos(root, "TButton") if b.cget("text") == "👁"]
ok(len(olhos) == 2, f"criação: olho na senha e na confirmação ({len(olhos)})")
print("\nTODOS OK" if all(f) else "\nHOUVE FALHAS")
root.destroy()
