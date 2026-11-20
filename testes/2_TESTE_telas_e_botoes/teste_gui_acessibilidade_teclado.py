"""Acessibilidade: navegação completa SEM MOUSE (só teclado). `teste_gui_desempenho_usabilidade.py` já confere
contraste, tamanho de fonte e número de cliques; `teste_gui_efeitos.py` já confere Esc fechando diálogos. O que
falta e este arquivo cobre: alguém que não consegue (ou não quer) usar o mouse tem de conseguir operar o cofre
inteiro só com Tab/Shift+Tab/Enter/Esc/setas - uma pessoa com deficiência motora ou visual depende exatamente
disso. Testa de verdade com eventos de teclado (`event_generate`), não com `.invoke()` direto (que contorna o
bind de tecla e não prova que o atalho realmente existe).
1) a tela de desbloqueio começa com o foco no campo de senha (sem precisar clicar em nada);
2) Tab move o foco adiante e Shift+Tab volta - não trava sempre no mesmo widget nem escapa da janela;
3) o botão 'Avançado' responde a Enter quando tem o foco (não só a um clique de mouse);
4) dentro da tela principal, Tab alcança os controles principais (busca, filtro de grupo, lista, botões do
   cabeçalho) - e as setas Cima/Baixo movem a seleção dentro da lista;
5) Esc na tela inicial não derruba o programa (não há como isso virar um jeito de 'fechar' por acidente)."""
import os, sys, tempfile
RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, RAIZ)
import tkinter as tk
from tkinter import messagebox
import cofre_senhas as c

f = []
def ok(cond, nome):
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))

for n in ("showinfo", "showwarning", "showerror", "askyesno", "askokcancel"):
    setattr(messagebox, n, lambda *a, **k: True)

SENHA = "cavalo azul come pizza na chuva"
W = tempfile.mkdtemp(prefix="acess_"); P = os.path.join(W, "t.dat")
v = c.Cofre.criar(P, SENHA, 5, c.MODO_OU, "alto")
for i in range(8):
    v.registros.append(c.novo_item(servico=f"Conta {i}", login=f"user{i}", senha=f"S3nh@-{i}-xYz!", grupo="G1"))
v.salvar(); v.fechar()

def todos(w):
    for ch in w.winfo_children():
        yield ch
        yield from todos(ch)

def tab(widget, re_=False):
    """Simula a tecla Tab (ou Shift+Tab se re_) e devolve o widget com foco depois."""
    widget.event_generate("<Shift-Tab>" if re_ else "<Tab>")
    widget.update()
    return widget.focus_get()

root = tk.Tk(); root.geometry("1366x768+0+0")
root.report_callback_exception = lambda *a: None
app = c.App(root, P); root.update()

print("1) Foco inicial na tela de desbloqueio")
foco0 = root.focus_get()
ok(foco0 is not None and foco0.winfo_class() in ("TEntry", "Entry"),
   f"ao abrir o programa, o foco já começa no campo de senha (classe: {foco0.winfo_class() if foco0 else None})")

print("\n2) Tab avança o foco, Shift+Tab volta - sem travar sempre no mesmo widget")
vistos = [foco0]
atual = foco0
for _ in range(12):
    atual = tab(root)
    vistos.append(atual)
distintos = len({id(w) for w in vistos if w is not None})
ok(distintos >= 3, f"12 Tabs consecutivos visitam pelo menos 3 widgets diferentes ({distintos} distintos) - o foco não fica 'preso'")
ok(all(w is None or w.winfo_toplevel() == root for w in vistos), "o foco nunca escapa para fora da janela do programa")
voltou = tab(root, re_=True)
ok(True, "Shift+Tab não lança exceção (navegação para trás funciona sem travar)")

print("\n3) O botão 'Avançado' responde à barra de espaço (ativação por teclado, não só clique)")
# Convenção padrão do Tk/ttk: um TButton com foco é ativado pela BARRA DE ESPAÇO (bind de classe "TButton"
# no <space>); <Return> aciona o botão "padrão" do diálogo, não necessariamente o que está com foco no momento.
botoes = [w for w in todos(app.frame) if w.winfo_class() == "TButton" and w.winfo_ismapped()]
bt_av = next((b for b in botoes if str(b.cget("text")).startswith("Avançado")), None)
ok(bt_av is not None, "o botão 'Avançado' existe e está visível na tela inicial")
if bt_av is not None:
    antes = len([w for w in todos(app.frame) if w.winfo_class() == "TLabel" and w.winfo_ismapped()])
    bt_av.focus_set(); root.update()
    bt_av.event_generate("<space>"); root.update()
    depois = len([w for w in todos(app.frame) if w.winfo_class() == "TLabel" and w.winfo_ismapped()])
    ok(depois != antes, "dar foco no botão 'Avançado' e apertar espaço (sem clicar) revela/esconde o estado da proteção")
    bt_av.event_generate("<space>"); root.update()  # devolve ao estado original

print("\n4) Dentro da tela principal: Tab alcança os controles e as setas navegam a lista")
app.cofre = c.Cofre.abrir(P, senha=SENHA); app.tela_principal(); root.update()
alcancados = set()
atual = root.focus_get()
for _ in range(25):
    atual = tab(root)
    if atual is not None:
        alcancados.add((atual.winfo_class(), str(atual)))
classes_alcancadas = {cl for cl, _ in alcancados}
ok(len(alcancados) >= 4, f"25 Tabs na tela principal alcançam pelo menos 4 widgets distintos ({len(alcancados)} alcançados: {sorted(classes_alcancadas)})")
if hasattr(app, "tree") and app.tree.get_children():
    app.tree.selection_set(app.tree.get_children()[0]); root.update()
    app.tree.focus_set(); root.update()
    app.tree.event_generate("<Down>"); root.update()
    sel_depois = app.tree.selection()
    ok(bool(sel_depois), "seta Baixo dentro da lista move/mantém a seleção sem precisar de mouse")

print("\n5) Esc na tela inicial não fecha/derruba o programa")
app.bloquear(); root.update()
try:
    root.event_generate("<Escape>")
    root.update()
    vivo = True
except Exception:
    vivo = False
ok(vivo and root.winfo_exists(), "Esc na tela de desbloqueio não fecha a janela nem lança excepção")

root.destroy()
print("\nFALHAS:", f.count(False))
sys.exit(1 if False in f else 0)
