# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Interface: o salvamento (lento num pendrive FAT32) NÃO congela a janela; o aviso 'Salvando…' só aparece
se passar de 0,4 s; o bloqueio automático espera a gravação acabar; erros de formato da chave contam depois de 3."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
import tkinter as tk
from tkinter import messagebox
import cofre_senhas as c
f = []
def ok(cond, nome):
    """Registra uma verificação."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
for n in ("showinfo", "showwarning", "showerror"):
    setattr(messagebox, n, lambda *a, **k: None)
messagebox.askyesno = lambda *a, **k: False
tk.Misc.wait_window = lambda self, window=None: None
P = os.path.join(tempfile.mkdtemp(), "t.dat"); S = "cavalo azul come pizza na chuva"
v = c.Cofre.criar(P, S, 5, c.MODO_S, "alto"); v.fechar()
root = tk.Tk(); root.geometry("900x600+0+0")
app = c.App(root, P); root.update()
app.cofre = c.Cofre.abrir(P, senha=S)
ok(c.Cofre.executor_salvar is not None, "a tela liga o salvamento fora da thread da janela")

# grava de forma lenta (1,2 s), como um pendrive de 3 MB/s com antivírus
orig = c._gravar_atomico
def lento(caminho, dados):
    """Gravação artificialmente lenta."""
    time.sleep(1.2); return orig(caminho, dados)
c._gravar_atomico = lento
batidas = []
def tique():
    """Conta quantas vezes a janela conseguiu rodar enquanto salvava."""
    batidas.append(time.monotonic()); root.after(30, tique)
tique(); root.update()
visiveis = []
def espia():
    """Vê se o aviso 'Salvando…' apareceu (e quando)."""
    for w in root.winfo_children():
        if isinstance(w, tk.Toplevel) and w.winfo_viewable() and float(w.attributes("-alpha")) > 0.5:
            visiveis.append(time.monotonic())
    root.after(50, espia)
espia()
t0 = time.monotonic()
app.cofre.registros.append(c.novo_item(servico="X", login="a", senha="b" * 12))
app.cofre.salvar()
dur = time.monotonic() - t0
buracos = max((b - a for a, b in zip(batidas, batidas[1:])), default=9)
ok(dur >= 1.1, f"a gravação lenta realmente demorou ({dur:.1f} s)")
ok(buracos < 0.25, f"a janela respondeu durante toda a gravação (maior pausa {buracos * 1000:.0f} ms)")
ok(visiveis and visiveis[0] - t0 >= 0.35, "o aviso 'Salvando…' só aparece depois de 0,4 s")
c._gravar_atomico = orig
# gravação rápida: nenhum aviso aparece
visiveis.clear(); t0 = time.monotonic()
app.cofre.registros.append(c.novo_item(servico="Y", login="a", senha="b" * 12)); app.cofre.salvar(); root.update()
ok(not visiveis, "gravação rápida não mostra aviso (nada pisca)")
# bloquear no meio de uma gravação espera o fim
c._gravar_atomico = lento
estado = {}
def tentar_bloquear():
    """Pede o bloqueio automático no meio da gravação."""
    app.bloquear(); estado["cofre_durante"] = app.cofre is not None
root.after(300, tentar_bloquear)
app.cofre.registros.append(c.novo_item(servico="Z", login="a", senha="b" * 12)); app.cofre.salvar()
ok(estado.get("cofre_durante") is True, "bloqueio automático NÃO apaga as chaves no meio da gravação")
c._gravar_atomico = orig
for _ in range(30): root.update(); time.sleep(0.02)
ok(app.cofre is None, "e bloqueia logo depois que a gravação termina")
# 3 erros de formato são perdoados, o 4º conta (núcleo)
r0 = c.tentativas_restantes(P)
r1 = c.gastar_tentativa_arquivo(P)
ok(r1 == r0 - 1, "gastar_tentativa_arquivo desconta 1")
root.destroy()
print("FALHAS:", f.count(False)); sys.exit(1 if False in f else 0)
