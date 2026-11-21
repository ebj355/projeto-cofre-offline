# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Alerta de tentativas erradas e histórico de aberturas: conta as senhas erradas desde a última abertura, guarda o histórico CIFRADO e mostra o aviso na tela."""
import os as _os, sys as _sys, tempfile as _tf, subprocess as _sp
_RAIZ = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".."))
def _foto(arq):
    """Captura a tela (só onde existe o ImageMagick 'import'); sem ele, ignora."""
    try: _sp.run(["import", "-window", "root", arq], check=False)
    except Exception: pass
import os, sys, subprocess, time
sys.path.insert(0, _RAIZ)
import tkinter as tk, cofre_senhas as c
from tkinter import messagebox
f = []
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
W = _tf.mkdtemp(prefix="cofre_gui_"); P = os.path.join(W, "a.dat")
for x in (P, P + ".tmp"):
    if os.path.exists(x): os.remove(x)
SENHA = "cavalo azul come pizza na chuva"
print("Núcleo: histórico cifrado")
v = c.Cofre.criar(P, SENHA, 5, c.MODO_E, "alto"); K = v.chave_gerada
v.registros.append(c.novo_item(servico="Banco", senha="x")); v.salvar()
for _ in range(2):   # "invasor" erra 2 vezes
    try: c.Cofre.abrir(P, senha="chute errado longo", chave=K)
    except c.SenhaIncorreta: pass
w = c.Cofre.abrir(P, senha=SENHA, chave=K)
ok(w.erros_desde_ultima == 2 and w.ultima_abertura, f"detecta 2 tentativas erradas desde a última abertura ({w.ultima_abertura})")
w2 = c.Cofre.abrir(P, senha=SENHA, chave=K)
ok(w2.erros_desde_ultima == 0, "abertura seguinte sem erros -> 0")
ok(len(w2.meta["historico"]) == 3 and w2.meta["historico"][1]["erros_antes"] == 2, "histórico guarda as aberturas e os erros")
ok(b"historico" not in open(P, "rb").read() and b"ultima_abertura" not in open(P, "rb").read(), "histórico fica CIFRADO (invasor não apaga o rastro)")

print("Telas")
log = []
messagebox.showwarning = lambda *a, **k: log.append(("ALERTA", a[0], a[1]))
messagebox.showinfo = lambda *a, **k: log.append(("info", a[0]))
messagebox.askyesno = lambda *a, **k: True
for _ in range(3):
    try: c.Cofre.abrir(P, senha="outro chute errado", chave=K)
    except c.SenhaIncorreta: pass
root = tk.Tk(); app = c.App(root, P)
confirmacoes = []
def conf(t): confirmacoes.append(t); return True
app._confirmar_senha_atual = conf
def achar(w, txt, cls=("TButton",)):
    for ch in w.winfo_children():
        if ch.winfo_class() in cls and str(ch.cget("text")).startswith(txt): return ch
        r = achar(ch, txt, cls)
        if r: return r
def ents():
    out = []
    def t(w):
        for ch in w.winfo_children():
            if ch.winfo_class() == "TEntry": out.append(ch)
            t(ch)
    t(app.frame); return out
def p1():
    e = ents(); e[0].insert(0, "minha senha digitada errada"); e[1].insert(0, K)
    achar(app.frame, "Desbloquear").invoke(); root.after(4000, p2)
def p2():
    e = ents(); e[0].insert(0, SENHA); e[1].insert(0, K)
    achar(app.frame, "Desbloquear").invoke(); root.after(4000, p3)
def p3():
    al = [x for x in log if x[0] == "ALERTA"]
    ok(app.cofre is not None, "abriu pela tela")
    ok(al and "Houve 3 tentativa" in al[0][2], "alerta mostra as 3 tentativas de OUTRA pessoa (o seu erro desta vez não conta)")
    ok("Última abertura" in app.status.cget("text"), "barra mostra a última abertura: " + app.status.cget("text"))
    app._msg_abertura = ""
    # proteção extra (2026-11-13: deixou de ser uma caixinha por item -- reclamação real de que o formulário
    # ficava poluído -- e virou um único ajuste para o cofre todo, em '⋯ → Segurança → Proteção extra')
    r = app.cofre.registros[0]
    ok(not app._protecao_global(), "proteção extra começa desligada (cofre novo, nenhum item tinha 'protegido')")
    app._transacao(lambda: app.cofre.meta.update({"protecao_global": True}))
    app.atualizar_lista()
    ok("🔒" not in str(app.tree.item(r["id"])["values"]), "a lista não mostra mais cadeado por item (não existe mais por item)")
    app.tree.selection_set(r["id"]); app.copiar("senha")
    ok(len(confirmacoes) == 1, "com a proteção extra ligada, copiar QUALQUER item pede a senha mestra")
    app.copiar("senha")
    ok(len(confirmacoes) == 1, "dentro de 30 s não pede de novo")
    app._liberado_em = {}; app.editar(); root.update()
    ok(len(confirmacoes) == 2, "abrir/editar com a proteção ligada também pede a senha mestra")
    d = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)][-1]
    cb = achar(d, "Item protegido", ("TCheckbutton",))
    ok(cb is None, "o formulário do item não tem mais a caixa 'Item protegido' (virou ajuste único do cofre)")
    _foto(os.path.join(W, "item_protegido.png"))
    d.destroy(); root.update()
    # desligar pela tela de ajuste (⋯ → Segurança → Proteção extra), igual o usuário faria
    app.configurar_protecao_extra(); root.update()
    dp = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)][-1]
    chk = achar(dp, "Pedir a senha mestra", ("TCheckbutton",))
    ok(chk is not None and "selected" in chk.state(), "tela de proteção extra mostra a caixa marcada (está ligada)")
    chk.invoke(); achar(dp, "Salvar").invoke(); root.update()
    ok(not app._protecao_global(), "desmarcar e salvar na tela de ajuste desliga a proteção extra")
    app._liberado_em = {}; app.copiar("senha")
    ok(len(confirmacoes) == 2, "com a proteção extra desligada, copiar não pede mais a senha mestra")
    v3 = c.Cofre.abrir(P, senha=SENHA, chave=K)   # este cofre é MODO_E: exige senha E chave juntas
    ok(v3.meta.get("protecao_global") is False, "o ajuste (desligado) fica gravado, cifrado, dentro do cofre")
    # ocultar ao perder o foco
    app._app_sem_foco = lambda: True; app._talvez_ocultar(); root.update()
    _foto(os.path.join(W, "oculto.png"))
    ok(len(app._ocultadores) >= 1, "perdeu o foco -> conteúdo coberto")
    app._mostrar_conteudo(); ok(not app._ocultadores, "voltou o foco -> conteúdo aparece")
    # suspensão / bloqueio do Windows
    app._ultimo_tique = time.time() - 120; app._vigiar_sistema(); root.update()
    ok(app.cofre is None, "PC dormiu (salto de relógio) -> cofre bloqueado")
    app.sair()
root.after(800, p1); root.mainloop()
for x in (P, P + ".tmp"):
    if os.path.exists(x): os.remove(x)

# migração: cofre ANTIGO (de antes de 2026-11-13), com itens marcados "protegido" por fora, mas sem a chave nova
# "protecao_global" -- precisa herdar a proteção (ligada), nunca desligar silenciosamente quem já contava com ela.
# Checagem direta de _protecao_global() (só olha self.cofre): sem abrir uma 2ª janela/App (um 2º tk.Tk() no mesmo
# processo, depois que o primeiro já rodou um mainloop inteiro, é frágil e pode travar o Tcl à toa).
W2 = _tf.mkdtemp(prefix="cofre_gui_"); P2 = os.path.join(W2, "antigo.dat")
v4 = c.Cofre.criar(P2, SENHA, 5, c.MODO_OU, "alto")
v4.registros.append(c.novo_item(servico="Conta antiga"))
v4.registros[0]["protegido"] = True       # como um cofre salvo por uma versão anterior do programa
v4.salvar()
app2 = c.App.__new__(c.App)
app2.cofre = c.Cofre.abrir(P2, senha=SENHA)
ok(app2._protecao_global(), "cofre antigo sem 'protecao_global': herda ligado, porque já tinha item 'protegido'")
for x in (P2, P2 + ".tmp"):
    if os.path.exists(x): os.remove(x)

print("\nTODOS OK" if all(f) else f"\nFALHAS: {f.count(False)}")
