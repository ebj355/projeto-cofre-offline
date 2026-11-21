# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Força das senhas na interface: senha repetida/fraca nos alertas, 'Verificar senhas', troca por senha forte e a impressão da folha de emergência."""
import os as _os, sys as _sys, tempfile as _tf, subprocess as _sp
_RAIZ = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".."))
def _foto(arq):
    """Captura a tela (só onde existe o ImageMagick 'import'); sem ele, ignora."""
    try: _sp.run(["import", "-window", "root", arq], check=False)
    except Exception: pass
import os, sys, subprocess
sys.path.insert(0, _RAIZ)
import tkinter as tk, cofre_senhas as c
from tkinter import messagebox
W = _tf.mkdtemp(prefix="cofre_gui_"); P = os.path.join(W, "g.dat")
for x in (P, P + ".tmp"):
    if os.path.exists(x): os.remove(x)
SENHA = "cavalo azul come pizza na chuva"
v = c.Cofre.criar(P, SENHA, 5, c.MODO_OU, "alto")
v.registros += [c.novo_item(servico="Banco", login="joao", senha="Flamengo2024", pin="1234"),
                c.novo_item(servico="Loja", login="joao", senha="Flamengo2024"),
                c.novo_item(servico="Gmail", login="joao@g", senha=c.gerar_senha(20))]
v.salvar()
impressos = []
c.escolher_impressora = lambda hwnd: (123, "EPSON L3250 Series", "USB001")
c.imprimir_linhas = lambda hdc, linhas: impressos.append(linhas)
log = []
messagebox.showinfo = lambda *a, **k: log.append(a[0])
messagebox.showerror = lambda *a, **k: log.append(("ERRO",) + a)
root = tk.Tk(); app = c.App(root, P)
app.cofre = c.Cofre.abrir(P, senha=SENHA); app.tela_principal()
app._pedir_senha = lambda *a, **k: SENHA
def shot(n): root.update(); _foto(os.path.join(W, n))
def topos(): return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
def achar(w, txt, cls=("TButton",)):
    for ch in w.winfo_children():
        if ch.winfo_class() in cls and str(ch.cget("text")).startswith(txt): return ch
        r = achar(ch, txt, cls)
        if r: return r
def p1():
    app.tree.selection_set(app.cofre.registros[0]["id"]); app.editar(); root.update()
    shot("1_item_medidor.png")
    d = topos()[-1]
    root.after(500, p2); achar(d, "Gerar").invoke()
def p2():
    g = topos()[-1]; root.update(); shot("2_gerador.png")
    achar(g, " Fácil", ("TRadiobutton",)).invoke(); root.update(); shot("3_gerador_frase.png")
    achar(g, " Aleatória", ("TRadiobutton",)).invoke(); root.update()
    achar(g, "Usar", ("TButton",)).invoke()
    root.after(300, p3)
def p3():
    d = topos()[-1]; root.update(); shot("4_item_apos_gerar.png")
    achar(d, "Salvar").invoke(); root.update()
    print("senha trocada e forte:", c.avaliar_forca(app.cofre.registros[0]["senha"])[1])
    app.verificar_senhas(); root.update(); shot("5_verificacao.png")
    a = topos()[-1]; t = [w for w in a.winfo_children()[0].winfo_children() if w.winfo_class() == "Treeview"][0]
    print("alertas na verificação:", [t.item(i)["values"][:3] for i in t.get_children()])
    a.destroy()
    app.tree.selection_set(app.cofre.registros[0]["id"])
    root.after(300, p5)               # (o cofre só imprime a chave de acesso: ver teste_gui_imprimir_chave.py)
def p5():
    print("impressões:", len(impressos), "| linhas:", [l for l in impressos[0] if l[0] in ("titulo", "campo")][:6] if impressos else None)
    print("mensagens:", log)
    root.destroy()
root.after(500, p1); root.mainloop()
