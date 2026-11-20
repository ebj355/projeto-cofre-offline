"""Teste de interface: ordem A→Z/Z→A, mover contas entre perfis (arrastar/menu), avaliação em tempo real,
tela montada de uma vez e ausência do botão Gerador ao lado de 'Novo item'. Roda no Linux com xvfb-run."""
import os, sys, tempfile
_RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, _RAIZ)
import tkinter as tk, cofre_senhas as c
from tkinter import messagebox
f = []
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
W = tempfile.mkdtemp(prefix="cofre_gui_"); P = os.path.join(W, "p.dat")
SENHA = "cavalo azul come pizza na chuva"
v = c.Cofre.criar(P, SENHA, 5, c.MODO_OU, "alto")
for s in ("Zeta", "álamo", "Banco", "alfa", "Nubank"):
    v.registros.append(c.novo_item(servico=s, login="x@y.com", senha="Senha-Forte-123!"))
v.salvar()
messagebox.askyesno = lambda *a, **k: True
root = tk.Tk(); root.geometry("1366x768"); app = c.App(root, P)
app.cofre = c.Cofre.abrir(P, senha=SENHA); app.tela_principal(); root.update()
def nomes(): return [app.cofre.registros[[r["id"] for r in app.cofre.registros].index(i)]["servico"] for i in app.tree.get_children()]
ok(c.chave_ordem_alfabetica("Álamo") == c.chave_ordem_alfabetica("alamo"), "ordenação ignora acento e maiúscula")
ok(nomes() == ["álamo", "alfa", "Banco", "Nubank", "Zeta"], f"padrão A→Z: {nomes()}")
app._alternar_ordem(); root.update()
ok(nomes() == ["Zeta", "Nubank", "Banco", "alfa", "álamo"] and app._btn_ordem.cget("text") == "Z → A", f"Z→A: {nomes()}")
app._alternar_ordem(); root.update()
ok(nomes()[0] == "álamo", "volta para A→Z")
# mover conta para perfil novo e entre perfis
zeta = next(r for r in app.cofre.registros if r["servico"] == "Zeta")
c.App._pedir_nome = lambda self, *a, **k: "Pai"
ok(app._mover_para_nova_pessoa(zeta["id"]) and zeta["pessoa"] == "Pai", "criar perfil novo com a conta já move a conta")
ok("p:Pai" in app.lateral_pessoas.get_children(), "perfil novo aparece na barra")
ok(app._mover_conta(zeta["id"], pessoa="") and zeta["pessoa"] == "", "mover de volta para 'Eu'")
# soltar sobre alvo (simula posição do mouse sobre a linha 'Adicionar pessoa'/'Pai')
root.update(); alvo = app.lateral_pessoas._itens["p:Pai"]["linha"]
x, y = alvo.winfo_rootx() + 5, alvo.winfo_rooty() + 5
ok(app._alvo_em(x, y) == ("pessoa", "p:Pai"), "alvo sob o mouse identificado")
app._soltar_conta(zeta["id"], x, y); root.update()
ok(zeta["pessoa"] == "Pai", "soltar a conta sobre o perfil move a conta")
app.filtro_pessoa.set("*"); app.atualizar_lista(); root.update()
# arrastar de verdade pela lista (eventos)
app.tree.selection_set(app.tree.get_children()[0]); root.update()
cv = app.tree.canvas
class E: pass
e = E(); e.x, e.y = 30, 30
app.tree._clique(e)
e2 = E(); e2.x, e2.y, e2.x_root, e2.y_root = 80, 90, x, y
app.tree._arrastando(e2)
ok(app.tree._arraste is not None, "arraste começou depois de mover o mouse")
app.tree._soltou(e2); root.update()
ok(app.tree._arraste is None, "arraste terminou")
# grupos livres
c.App._pedir_nome = lambda self, *a, **k: "Redes sociais"
ok(app._novo_grupo() and "Redes sociais" in app._grupos(), "criar grupo vazio")
root.update()
ok("g:Redes sociais" in app.lateral.get_children(), "grupo vazio aparece na barra")
ok("Banco" in app._grupos_sugeridos() and "Compras" in app._grupos_sugeridos(), "sugestões de grupo (Banco, Compras...)")
nub = next(r for r in app.cofre.registros if r["servico"] == "Nubank")
ok(app._mover_conta(nub["id"], grupo="Redes sociais") and nub["grupo"] == "Redes sociais", "mover conta para o grupo")
app._remover_grupo("Redes sociais"); root.update()
ok(nub["grupo"] == "" and "Redes sociais" not in app._grupos(), "remover grupo solta as contas e não apaga")
# vários códigos de recuperação, grandes
cods = [("ABCD-%04d-" % i) + "x9Zq" * 12 for i in range(12)]
nub["codigos"] = "\n".join(cods)
ok(app._salvar(), "salva item com 12 códigos grandes")
app.atualizar_lista(); app.tree.selection_set(nub["id"]); root.update()
app._revelados.add((nub["id"], "codigos")); app._montar_detalhe(); root.update()
copiados = []
app._copiar_texto = lambda v, d: (copiados.append(v), (True, "ok"))[1]
def bots(w):
    r = []
    for ch in w.winfo_children():
        r += bots(ch)
        if ch.winfo_class() == "TButton" and str(ch.cget("text")).strip() == "Copiar": r.append(ch)
    return r
bb = bots(app.detalhe)
ok(len(bb) >= 13, f"detalhe: um Copiar por código + o geral ({len(bb)})")
bb[-1].invoke(); root.update()
ok(copiados and copiados[-1] in cods, "copiar um código copia só aquele código")
# botão Gerador não fica mais ao lado de Novo item
def textos(w):
    r = []
    for ch in w.winfo_children():
        try: r.append(str(ch.cget("text")).strip())
        except tk.TclError: pass
        r += textos(ch)
    return r
t = textos(app.frame)
ok("Novo item" in t and "Gerador" not in t, "barra de cima: tem 'Novo item' e não tem 'Gerador'")
# avaliação em tempo real: texto colocado SEM evento de teclado (como colar com o mouse)
app.bloquear(); root.update()
app.tela_criar(); root.update()
ent = [w for w in root.winfo_children()]  # só garante que a tela montou
ok(root.winfo_exists(), "tela de criar montada")
d = tk.Toplevel(root)
e_ = tk.Entry(d); e_.pack()
painel = c.PainelForca(d, app); painel.pack()
app._medidor(d, e_, dicas_lbl=painel).pack()
e_.insert(0, "Zq9!vT#2mLp@8xRw"); root.update()
import time
for _ in range(30):
    root.update(); time.sleep(0.02)
ok(painel.cget("text") != "", "painel avalia a senha colada sem evento de tecla (vigia em tempo real)")
e_.delete(0, "end")
for _ in range(30):
    root.update(); time.sleep(0.02)
ok(painel.cget("text") == "", "painel limpa quando o campo esvazia")
print("PASSOU" if all(f) else "FALHOU", sum(f), "/", len(f))
root.destroy()
sys.exit(0 if all(f) else 1)
