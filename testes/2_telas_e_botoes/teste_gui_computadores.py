"""Interface (Tk): janela 'Computadores autorizados', ranking com o item do computador e tela de desbloqueio em um
computador NÃO autorizado (pede o código de recuperação, sem gastar tentativa). Computadores simulados."""
import os, sys, tempfile, hashlib
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
import tkinter as tk
import cofre_senhas as c
from tkinter import messagebox
f = []
def ok(cond, nome):
    """Registra uma verificação."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
cp = lambda t: "".join(list(t))
SENHA = "cavalo azul come pizza na chuva"
W = tempfile.mkdtemp(prefix="gui_pc_"); P = os.path.join(W, "g.dat")
def em(n):
    """Passa a ser o computador n."""
    c.identidades_do_pc = lambda: [hashlib.sha256(b"x" + n.encode()).digest(), hashlib.sha256(b"y" + n.encode()).digest()]
em("A")
c.Cofre.criar(P, cp(SENHA), 5, c.MODO_S, "alto").fechar()
log = []
messagebox.showinfo = lambda *a, **k: log.append(("info", a[0], a[1] if len(a) > 1 else ""))
messagebox.showerror = lambda *a, **k: log.append(("ERRO", a[0], a[1] if len(a) > 1 else ""))
messagebox.askyesno = lambda *a, **k: True
root = tk.Tk(); app = c.App(root, P)
app.cofre = c.Cofre.abrir(P, senha=cp(SENHA)); app.tela_principal(); root.update()
app._confirmar_senha_atual = lambda *a, **k: True
app._pedir_texto = lambda titulo, texto, inicial="": inicial
codigos = []
app.mostrar_codigo_recuperacao = lambda cod: (codigos.append(cod), True)[1]
def todos(w):
    for ch in w.winfo_children():
        yield ch; yield from todos(ch)
def achar(w, txt, cls="TButton"):
    return next((x for x in todos(w) if x.winfo_class() == cls and str(x.cget("text")).startswith(txt)), None)
def topo():
    return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)][-1]
def textos(w):
    return [str(x.cget("text")) for x in todos(w) if x.winfo_class() in ("TLabel", "Label", "TButton", "TCheckbutton") and str(x.cget("text"))]

# ranking: sem o fator o item aparece inativo com ação 'pc'
pts0, _, it0 = c.nivel_protecao(app.cofre.modo, app.cofre.m, app.cofre.fido, app.cofre.pc)
ok(any(a == "pc" and not ativo for _, _, ativo, a in it0), "ranking mostra o item 'Computador autorizado' (inativo)")
app.gerenciar_computadores(); root.update(); d = topo()
ok(achar(d, "Autorizar este computador") is not None and achar(d, "Desativar") is not None, "janela tem os botões")
ok(str(achar(d, "Remover selecionado").cget("state")) == "disabled", "remover desligado enquanto nada está ativo")
achar(d, "Autorizar este computador").invoke(); root.update()
ok(app.cofre.pc is not None and len(app.cofre.pc["maquinas"]) == 1, "autorizou este computador")
ok(len(codigos) == 1, "mostrou o código de recuperação uma vez")
ok(str(achar(d, "Autorizar este computador").cget("state")) == "disabled", "botão de autorizar apagado (este computador já está)")
lista = next(x for x in todos(d) if x.winfo_class() == "Treeview")
# usa startswith (não igualdade exata): com reforço DPAPI (pergunta respondida "sim" pelo
# askyesno globalmente mockado acima), o valor vem como "este computador ✓ reforçado" em vez
# de apenas "este computador" -- achado real ao rodar no Windows de verdade (onde EH_WINDOWS
# é True e a pergunta do reforço chega a aparecer; no Linux de desenvolvimento ela nunca é
# feita e por isso esse caso nunca apareceu antes). Marcar com sufixo é o comportamento
# CORRETO do programa (indica reforço ativo); o teste é que estava rígido demais.
valores0 = lista.item(lista.get_children()[0])["values"]
ok(len(lista.get_children()) == 1 and any(str(v).startswith("este computador") for v in valores0),
   "lista marca 'este computador'")
pts1, _, it1 = c.nivel_protecao(app.cofre.modo, app.cofre.m, app.cofre.fido, app.cofre.pc)
ok(pts1 == pts0 + 10 and any(a == "pc" and ativo for _, _, ativo, a in it1), "ranking sobe 10 pontos")
ok(c.info_pc(P) == (True, True), "arquivo gravado: exige e está autorizado")
# segundo computador
em("B"); app.cofre.pc_adicionar("Outro"); root.update()
d.destroy(); root.update()
app.gerenciar_computadores(); root.update(); d = topo()
lista = next(x for x in todos(d) if x.winfo_class() == "Treeview")
ok(len(lista.get_children()) == 2, "lista mostra 2 computadores")
d.destroy(); root.update()
# bloqueia e abre num computador NÃO autorizado
app.salvar() if hasattr(app, "salvar") else app.cofre.salvar()
app.bloquear(); root.update(); em("C"); app.mostrar_inicio(); root.update(); root.update()
tx = " | ".join(textos(app.frame))
ok("não está autorizado" in tx, "desbloqueio mostra que o computador não está autorizado")
ok("CÓDIGO DE RECUPERAÇÃO" in " | ".join(str(x.cget("text")).upper() for x in todos(app.frame) if x.winfo_class() in ("TLabel",)), "campo do código de recuperação já visível")
ents = [x for x in todos(app.frame) if x.winfo_class() == "TEntry"]
r0 = c.tentativas_restantes(P)
ents[0].insert(0, cp(SENHA))
achar(app.frame, "Desbloquear").invoke(); root.update()
t0 = c.tentativas_restantes(P)
ok(t0 == r0, "senha sem o código: recusado e SEM gastar tentativa")
ok(any("não está autorizado" in t and "Nenhuma tentativa" in t for t in textos(app.frame)), "mostra a explicação sem gastar tentativa")
ok(all(e.get() == "" for e in ents), "campos limpos depois da tentativa")
ents = [x for x in todos(app.frame) if x.winfo_class() == "TEntry"]
ents[0].insert(0, cp(SENHA)); ents[-1].insert(0, codigos[0])
achar(app.frame, "Desbloquear").invoke()
import time
t = time.time()
while app.cofre is None and time.time() - t < 60: root.update(); time.sleep(0.05)
ok(app.cofre is not None and len(app.cofre.registros) == 0, "senha + código de recuperação abrem em outro computador")
print("mensagens:", log[-3:])
root.destroy()
print("FALHAS:", f.count(False)); sys.exit(1 if False in f else 0)
