"""Teste de interface: passeio guiado (retângulo amarelo + escurecimento + Próximo), oferta na 1ª abertura,
passeio do formulário de item e limpeza das janelas auxiliares. Roda no Linux com xvfb-run."""
import os, sys, tempfile
_RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, _RAIZ)
import tkinter as tk, cofre_senhas as c
from tkinter import messagebox
f = []
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
W = tempfile.mkdtemp(prefix="cofre_gui_"); P = os.path.join(W, "t.dat")
SENHA = "cavalo azul come pizza na chuva"
v = c.Cofre.criar(P, SENHA, 5, c.MODO_OU, "alto")
v.registros.append(c.novo_item(servico="Banco", login="a@b.com", senha="Senha-Forte-123!", codigos="AAAA-1111\nBBBB-2222"))
v.salvar()
perguntas = []
messagebox.askyesno = lambda *a, **k: (perguntas.append(a[0]), False)[1]
root = tk.Tk(); root.geometry("1366x768+0+0"); app = c.App(root, P)
app.cofre = c.Cofre.abrir(P, senha=SENHA); app.tela_principal(); root.update()
app._oferecer_passeio(); root.update()
ok(perguntas == ["Passeio guiado"] and app.cofre.meta.get("tour_visto") is True, "1ª abertura oferece o passeio e guarda que já ofereceu")
app._oferecer_passeio(); root.update()
ok(len(perguntas) == 1, "não oferece de novo")
n_top = lambda: len([w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
base_top = n_top()
app.passeio_principal(); root.update()
t = app._tour
ok(t is not None and t.i == 0 and t.cartao is not None, "passeio começa no passo 1 (cartão central)")
vistos = []
for _ in range(len(t.passos) + 2):
    if app._tour is None: break
    vistos.append(t.i)
    if t.passos[t.i][0] is not None:
        ok(len(t.pecas) >= 8, f"passo {t.i + 1}: escurecimento (4) + borda amarela (4): {len(t.pecas)} peças")
        amarelas = [p for p in t.pecas if p.cget("bg") == c.TourGuiado.COR_DESTAQUE]
        ok(len(amarelas) == 4, f"passo {t.i + 1}: 4 lados do retângulo amarelo")
    t._ir(t.i + 1); root.update()
ok(app._tour is None, "ao passar do último passo o passeio termina")
ok(n_top() == base_top, f"nenhuma janela auxiliar sobrou ({n_top()} vs {base_top})")
ok(len(vistos) >= 10, f"passou por {len(vistos)} passos")
# anterior / pular
app.passeio_principal(); root.update(); t = app._tour
t._ir(3); root.update(); t._ir(2, -1); root.update()
ok(t.i == 2, "Anterior volta um passo")
t.encerrar(); root.update()
ok(app._tour is None and n_top() == base_top, "Pular encerra e limpa")
# trocar de tela encerra o passeio
app.passeio_principal(); root.update()
app.bloquear(); root.update()
ok(app._tour is None, "bloquear o cofre encerra o passeio")
# formulário de item
app.cofre = c.Cofre.abrir(P, senha=SENHA); app.tela_principal(); root.update()
roda = {}
app.dialogo_registro(None); root.update()
d = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w.title() == "Novo item"][0]
def achar(w, txt):
    for ch in w.winfo_children():
        if ch.winfo_class() == "TButton" and str(ch.cget("text")).startswith(txt): return ch
        r = achar(ch, txt)
        if r: return r
b = achar(d, "?")
ok(b is not None, "formulário tem o botão '?' (passeio de como preencher)")
b.invoke(); root.update()
t = app._tour
ok(t is not None and len(t.passos) == 9, "passeio do formulário com 9 passos (inclui dados bancários)")
for _ in range(9):
    if app._tour is None: break
    t._ir(t.i + 1); root.update()
ok(app._tour is None, "passeio do formulário termina")
d.destroy(); root.update()
print("PASSOU" if all(f) else "FALHOU", sum(f), "/", len(f))
root.destroy(); sys.exit(0 if all(f) else 1)
