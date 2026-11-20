"""Tela de chaves FIDO2 e filtros da lista: cadastro/remoção de chaves, item antigo ganhando campos novos, filtro por grupo."""
import os as _os, sys as _sys, tempfile as _tf, subprocess as _sp
_RAIZ = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".."))
def _foto(arq):
    """Captura a tela (só onde existe o ImageMagick 'import'); sem ele, ignora."""
    try: _sp.run(["import", "-window", "root", arq], check=False)
    except Exception: pass
import os, sys, subprocess, hmac, hashlib, secrets
sys.path.insert(0, _RAIZ)
import tkinter as tk, cofre_senhas as c
from tkinter import messagebox
W = _tf.mkdtemp(prefix="cofre_gui_"); P = os.path.join(W, "gui.dat")
for x in (P, P + ".tmp"):
    if os.path.exists(x): os.remove(x)
SENHA = "cavalo azul come pizza na chuva"
_cp = lambda t: "".join(list(t))      # cópia nova: o cofre zera na memória a str que recebe

v = c.Cofre.criar(P, _cp(SENHA), 5, c.MODO_E, "alto"); K = v.chave_gerada
for it in [dict(grupo="senhas", servico="Banco X", login="joao", senha="a", senha_extra="b"),
           dict(grupo="Pin chave", servico="Pin chave 1", pin="1234", chave="CH"),
           dict(grupo="codigo de recuperação", servico="SAMSUNG", codigos="1111\n2222"),
           dict(grupo="pai", servico="vivo", senha="x")]:
    v.registros.append(c.novo_item(**it))
v.registros.append({"id": "antigo", "servico": "Item antigo", "login": "l", "senha": "s", "pin": "", "notas": ""})
v.salvar()

segredos = {}
def fake_cadastrar(hwnd, salt, nome="x"):
    cid = secrets.token_bytes(48); segredos[cid] = secrets.token_bytes(32)
    return cid, hmac.new(segredos[cid], salt, hashlib.sha256).digest()
def fake_obter(hwnd, creds, salt):
    for cid in creds:
        if cid in segredos: return cid, hmac.new(segredos[cid], salt, hashlib.sha256).digest()
    raise c.FidoErro("não cadastrada")
c.fido_cadastrar_e_testar = fake_cadastrar; c.fido_obter = fake_obter
log = []
messagebox.showinfo = lambda *a, **k: log.append(("info", a[0]))
messagebox.showerror = lambda *a, **k: log.append(("ERRO", a[0], a[1] if len(a) > 1 else ""))
messagebox.askyesno = lambda *a, **k: True

root = tk.Tk(); app = c.App(root, P)
app.cofre = c.Cofre.abrir(P, senha=_cp(SENHA), chave=_cp(K))
app.tela_principal()
app._pedir_senha = lambda *a, **k: _cp(SENHA)
app._pedir_texto = lambda titulo, texto, inicial="": inicial
codigos = []
def confirma_codigo(cod): codigos.append(cod); return True
app.mostrar_codigo_recuperacao = confirma_codigo
def shot(n): root.update(); _foto(os.path.join(W, n))
def achar(w, txt, cls=("TButton",)):
    for ch in w.winfo_children():
        if ch.winfo_class() in cls and str(ch.cget("text")).startswith(txt): return ch
        r = achar(ch, txt, cls)
        if r: return r
def topo():
    return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)][-1]

def passo1():
    shot("a_principal.png")
    print("linhas na lista:", len(app.tree.get_children()), "| grupos:", [app.lateral.item(i)["text"].strip() for i in app.lateral.get_children()])
    app.lateral.selection_set("g:pai"); root.update(); print("filtro 'pai':", len(app.tree.get_children()), "item")
    app.lateral.selection_set("__todos__"); root.update()
    app.tree.selection_set("antigo"); root.update()
    app.editar(); root.update(); shot("b_editar.png")
    d = topo(); achar(d, "Salvar").invoke(); root.update()
    print("item antigo após salvar tem campos novos:", all(k in [r for r in app.cofre.registros if r["id"] == "antigo"][0] for k in c.CAMPOS))
    app.gerenciar_fido(); root.update(); shot("c_fido_vazio.png")
    achar(topo(), "Adicionar").invoke()
    root.after(1500, passo2)
def passo2():
    root.update(); shot("d_fido_1chave.png")
    print("FIDO ativo:", bool(app.cofre.fido), "| código gerado:", len(codigos) == 1)
    achar(topo(), "Adicionar").invoke()
    root.after(1500, passo3)
def passo3():
    root.update()
    print("chaves:", [ch["nome"] for ch in app.cofre.fido["chaves"]], "| info_cofre:", c.info_cofre(P))
    shot("e_fido_2chaves.png")
    topo().destroy(); app.bloquear(); root.update(); shot("f_desbloqueio_fido.png")
    # desbloquear com senha + chave + FIDO simulado
    f = app.frame
    ents = []
    def todas(w):
        for ch in w.winfo_children():
            if ch.winfo_class() == "TEntry": ents.append(ch)
            todas(ch)
    todas(f)
    ents[0].insert(0, _cp(SENHA)); ents[1].insert(0, _cp(K))
    achar(f, "Desbloquear").invoke()
    root.after(6000, passo4)
def passo4():
    root.update()
    print("abriu com FIDO pela tela:", app.cofre is not None and len(app.cofre.registros) == 5)
    print("mensagens:", log)
    root.destroy()
root.after(600, passo1)
root.after(90000, lambda: (print("  [FALHOU] tempo esgotado (travou)"), root.destroy()))   # vigia: nunca fica preso
root.mainloop()
