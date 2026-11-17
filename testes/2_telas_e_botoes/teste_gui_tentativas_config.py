"""Tentativas erradas: as setas das caixas numéricas funcionam (clique real sobe/desce), a tela de criar NÃO mostra mais
a opção (ela fica dentro do cofre, ⋯ > Tentativas erradas, e pede a senha mestra), a mudança é gravada no cofre e vale
na autodestruição; a tela inicial não tem mais os textos cinza sem sentido. Roda no Windows ou no Linux (xvfb-run -a)."""
import os, sys, tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
import tkinter as tk
from tkinter import ttk, messagebox
import cofre_senhas as c
f = []
def ok(cond, nome):
    """Registra uma verificação."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
messagebox.showinfo = messagebox.showwarning = messagebox.showerror = lambda *a, **k: None
messagebox.askyesno = lambda *a, **k: True
tk.Misc.wait_window = lambda self, window=None: None
def todos(w):
    """Todos os widgets filhos, recursivamente."""
    for x in w.winfo_children():
        yield x; yield from todos(x)
def tops(root): return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
def textos(d): return [str(w.cget("text")) for w in todos(d) if w.winfo_class() in ("TLabel", "Label") and w.winfo_ismapped()]

W = tempfile.mkdtemp(prefix="tc_"); P = os.path.join(W, "t.dat"); SENHA = "cavalo azul come pizza na chuva"
root = tk.Tk(); root.geometry("1100x760+0+0")
app = c.App(root, P); root.update()
# ---- tela de criar: sem opção de tentativas e sem os textos cinza
app.mostrar_inicio(); root.update(); root.update()
tx = textos(app.frame)
ok(not any("Apagar o cofre" in t or "tentativas erradas" in t for t in tx), "tela de criar: a opção de tentativas NÃO fica do lado de fora")
ok(not any("Só vale depois de cadastrar" in t or "aparece uma só vez no próximo passo" in t for t in tx), "tela de criar: sem os textos cinza soltos")
ok(not [w for w in todos(app.frame) if w.winfo_class() == "TSpinbox"], "tela de criar: sem caixa numérica")
# ---- setas das caixas numéricas funcionam (o Tk precisa reconhecer uparrow/downarrow)
t = tk.Toplevel(root); sp = ttk.Spinbox(t, from_=1, to=10, width=4, style="TSpinbox"); sp.set("3"); sp.pack(padx=20, pady=20); t.update(); t.update()
w, h = sp.winfo_width(), sp.winfo_height()
cima = [x for x in range(w) if sp.identify(x, h // 2).endswith("uparrow")]
baixo = [x for x in range(w) if sp.identify(x, h // 2).endswith("downarrow")]
ok(bool(cima) and bool(baixo), "o Tk reconhece as setas (uparrow / downarrow) do campo numérico")
def clique(x):
    sp.event_generate("<ButtonPress-1>", x=x, y=h // 2); sp.event_generate("<ButtonRelease-1>", x=x, y=h // 2); t.update()
if cima and baixo:
    antes = int(sp.get()); clique(cima[len(cima) // 2]); ok(int(sp.get()) == antes + 1, f"clicar na seta de CIMA aumenta ({antes} -> {sp.get()})")
    antes = int(sp.get()); clique(baixo[len(baixo) // 2]); ok(int(sp.get()) == antes - 1, f"clicar na seta de BAIXO diminui ({antes} -> {sp.get()})")
t.destroy()
# ---- cria o cofre e abre; configuração dentro do cofre
c.Cofre.criar(P, SENHA, c.TENTATIVAS_PADRAO, c.MODO_S, "alto").fechar()
ok(c.tentativas_restantes(P) == 3, "cofre nasce com 3 tentativas (padrão)")
app.mostrar_inicio(); root.update(); root.update()
tx = textos(app.frame)
ok(not any("Desbloqueie seu cofre" in t or t.endswith(".dat") for t in tx), "tela de desbloqueio: sem subtítulo cinza nem nome de arquivo")
ok(any("tentativa" in t.lower() for t in tx), "mostra só o essencial: quantas tentativas restam")
app.cofre = c.Cofre.abrir(P, senha=SENHA); app.tela_principal(); root.update()
app._confirmar_senha_atual = lambda *a, **k: SENHA
app.configurar_tentativas(); root.update(); root.update()
d = tops(root)[-1]
mais = [b for b in todos(d) if b.winfo_class() == "TButton" and str(b.cget("text")) == "+"][0]
menos = [b for b in todos(d) if b.winfo_class() == "TButton" and str(b.cget("text")) == "−"][0]
for _ in range(4): mais.invoke()
for _ in range(20): menos.invoke()
menos_n = [str(l.cget("text")) for l in todos(d) if l.winfo_class() == "TLabel" and str(l.cget("text")).isdigit()]
ok(menos_n == ["1"], f"mínimo 1 (não passa de 1 para baixo): {menos_n}")
for _ in range(7): mais.invoke()
[b for b in todos(d) if b.winfo_class() == "TButton" and str(b.cget("text")) == "+"]
n = [str(l.cget("text")) for l in todos(d) if l.winfo_class() == "TLabel" and str(l.cget("text")).isdigit()]
ok(n == ["8"], f"sobe de 1 em 1: {n}")
for _ in range(10): mais.invoke()
ok([str(l.cget("text")) for l in todos(d) if l.winfo_class() == "TLabel" and str(l.cget("text")).isdigit()] == ["10"], "máximo 10")
for _ in range(5): menos.invoke()                                   # 5
[b for b in todos(d) if b.winfo_class() == "TButton" and str(b.cget("text")) == "Salvar"][0].invoke(); root.update()
ok(app.cofre.max_t == 5 and c.tentativas_restantes(P) == 5, "gravou o novo limite no cofre (5) e o contador voltou ao máximo")
app.cofre.fechar(); app.cofre = None
v = c.Cofre.abrir(P, senha=SENHA); ok(v.max_t == 5, "reabrir: o limite novo continua (5)"); v.fechar()
fim = None
for i in range(8):
    try: c.Cofre.abrir(P, senha="senha errada numero " + str(i) + " bem longa")
    except c.CofreDestruido: fim = i; break
    except c.SenhaIncorreta: pass
ok(fim == 4 and not os.path.exists(P), "a autodestruição agora acontece no 5º erro")
# senha mestra errada na confirmação: nada muda
c.Cofre.criar(P, SENHA, 3, c.MODO_S, "alto").fechar()
app.cofre = c.Cofre.abrir(P, senha=SENHA); app.tela_principal(); root.update()
app._confirmar_senha_atual = lambda *a, **k: False
app.configurar_tentativas(); root.update(); root.update(); d = tops(root)[-1]
[b for b in todos(d) if b.winfo_class() == "TButton" and str(b.cget("text")) == "+"][0].invoke()
[b for b in todos(d) if b.winfo_class() == "TButton" and str(b.cget("text")) == "Salvar"][0].invoke(); root.update()
ok(app.cofre.max_t == 3 and c.tentativas_restantes(P) == 3, "sem confirmar a senha mestra, nada muda")
root.destroy()
print("FALHAS:", f.count(False)); sys.exit(1 if False in f else 0)
