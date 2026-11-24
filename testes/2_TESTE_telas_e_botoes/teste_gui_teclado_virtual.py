# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Teclado virtual: as teclas são criadas UMA vez e só trocam de letra (sem recriar, sem piscar), digitam no campo,
apagam, alternam maiúsculas, mostram a contagem sem revelar a senha, fecham com Esc e respondem rápido.
Roda no Windows ou no Linux (xvfb-run -a)."""
import os, sys, time, tempfile
# Este teste envia TECLAS de verdade (Esc). Elas só chegam ao campo se a janela puder ter o foco do teclado, e o
# modo "segundo plano" dos testes (COFRE_GUI_TESTS_BACKGROUND=1, janelas WS_EX_NOACTIVATE) impede isso. Por isso este
# teste desliga o modo segundo plano: enquanto roda (cerca de 6 s) as janelas dele podem tomar o foco.
os.environ["COFRE_GUI_TESTS_BACKGROUND"] = "0"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
import tkinter as tk
from tkinter import ttk, messagebox
import cofre_senhas as c
f = []
def ok(cond, nome):
    """Registra uma verificação."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
messagebox.showinfo = messagebox.showwarning = messagebox.showerror = lambda *a, **k: None
tk.Misc.wait_window = lambda self, window=None: None
def todos(w):
    """Todos os widgets filhos, recursivamente."""
    for x in w.winfo_children():
        yield x; yield from todos(x)
W = tempfile.mkdtemp(prefix="tv_"); P = os.path.join(W, "t.dat"); SENHA = "cavalo azul come pizza na chuva"
c.Cofre.criar(P, SENHA, 5, c.MODO_OU, "alto").fechar()
root = tk.Tk(); root.geometry("1000x650+0+0")
app = c.App(root, P); root.update()
alvo = ttk.Entry(root, show="•"); alvo.pack(); root.update()
app.teclado_virtual(alvo); root.update(); root.update()
d = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)][-1]
teclas = lambda: [w for w in todos(d) if w.winfo_class() == "Button"]
t0 = teclas()
ok(len(t0) == 80 and all(b.winfo_ismapped() for b in t0), "80 teclas visíveis")
ok(d.winfo_rootx() >= 0 and d.winfo_rooty() >= 0 and d.winfo_rootx() + d.winfo_width() <= root.winfo_screenwidth(), "janela dentro da tela")
ordem0 = [b.cget("text") for b in t0]
t0[5].invoke(); root.update()
t1 = teclas()
ok(t1 == t0, "as MESMAS teclas continuam depois do clique (nada é destruído/recriado: sem piscar)")
ok(len(alvo.get()) == 1 and alvo.get() == ordem0[5], "a tecla clicada foi digitada no campo")
ok([b.cget("text") for b in t1] != ordem0 and sorted(b.cget("text") for b in t1) == sorted(ordem0), "teclas embaralhadas, sem perder nem repetir nenhuma")
conta = [str(w.cget("text")) for w in todos(d) if w.winfo_class() == "TLabel" and "caracteres" in str(w.cget("text"))]
ok(conta == ["1 caracteres digitados"], "mostra só a contagem (nunca o conteúdo)")
# velocidade: 40 cliques
ini = time.perf_counter()
for i in range(40):
    teclas()[i].invoke(); root.update()
dt = (time.perf_counter() - ini) / 40 * 1000
ok(dt < 60, f"cada clique + embaralhar leva {dt:.0f} ms (< 60 ms)")
ok(len(alvo.get()) == 41, "41 caracteres digitados")
# maiúsculas
bm = [w for w in todos(d) if w.winfo_class() == "TButton" and str(w.cget("text")) == "ABC"][0]
bm.invoke(); root.update()
letras = [b.cget("text") for b in teclas() if b.cget("text").isalpha()]
ok(letras and all(x == x.upper() for x in letras), "ABC: letras em maiúsculas")
ok(str(bm.cget("text")) == "abc" and teclas() == t0, "botão vira 'abc' e as teclas continuam as mesmas")
bm.invoke(); root.update()
ok(all(x == x.lower() for x in [b.cget("text") for b in teclas() if b.cget("text").isalpha()]), "abc: volta às minúsculas")
# apagar e espaço
ba = [w for w in todos(d) if w.winfo_class() == "TButton" and "Apagar" in str(w.cget("text"))][0]
n = len(alvo.get()); ba.invoke(); root.update(); ok(len(alvo.get()) == n - 1, "Apagar remove 1 caractere")
be = [w for w in todos(d) if w.winfo_class() == "TButton" and str(w.cget("text")) == "Espaço"][0]
be.invoke(); root.update(); ok(alvo.get().endswith(" "), "Espaço digita um espaço")
# sem embaralhar: posições fixas
ck = [w for w in todos(d) if w.winfo_class() == "TCheckbutton"][0]; ck.invoke(); root.update()
antes = [b.cget("text") for b in teclas()]; teclas()[0].invoke(); root.update()
ok([b.cget("text") for b in teclas()] == antes, "com 'Embaralhar' desligado as teclas ficam paradas")
# Esc fecha
d.focus_force(); d.event_generate("<Escape>"); root.update()
ok(not d.winfo_exists(), "Esc fecha o teclado")
# alvo destruído: não dá erro
app.teclado_virtual(alvo); root.update(); d2 = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)][-1]
alvo.destroy(); [w for w in todos(d2) if w.winfo_class() == "Button"][0].invoke(); root.update()
ok(not d2.winfo_exists(), "se o campo some, o teclado fecha sozinho (sem erro)")
root.destroy()
print("FALHAS:", f.count(False)); sys.exit(1 if False in f else 0)
