# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Impressão: o cofre só imprime a cópia de emergência da chave de acesso e do código de recuperação, e só depois de
pedir a senha mestra. Itens não têm 'Imprimir'; qualquer outro título é bloqueado; a senha mestra nunca é impressa;
o trabalho na fila do Windows tem nome genérico."""
import os, sys, tempfile
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
W = tempfile.mkdtemp(prefix="gui_imp_"); P = os.path.join(W, "g.dat")
v = c.Cofre.criar(P, cp(SENHA), 5, c.MODO_OU, "alto")
v.registros.append(c.novo_item(servico="Banco Azul", login="maria", senha="SegredoNaoImprimir-77")); v.salvar()
impressos = []
c.escolher_impressora = lambda hwnd: (123, "EPSON L3250 Series", "USB001")
c.impressora_gera_arquivo = lambda n, p: False
c.imprimir_linhas = lambda hdc, linhas: impressos.append(linhas)
log = []
messagebox.showinfo = lambda *a, **k: log.append(("info", a[0]))
messagebox.showerror = lambda *a, **k: log.append(("ERRO", a[0], a[1] if len(a) > 1 else ""))
messagebox.askyesno = lambda *a, **k: True
senha_ok = {"v": True}; pedidos = []
root = tk.Tk(); app = c.App(root, P)
def _conf(titulo):
    """Simula a confirmação da senha mestra."""
    pedidos.append(titulo); return bool(senha_ok["v"])
app._confirmar_senha_atual = _conf
app.cofre = c.Cofre.abrir(P, senha=cp(SENHA)); app.tela_principal(); root.update()
def todos(w):
    for ch in w.winfo_children():
        yield ch; yield from todos(ch)
ok(not hasattr(c.App, "imprimir_item"), "não existe mais impressão de item")
app.tree.selection_set(app.cofre.registros[0]["id"]); root.update(); root.update()
rot = [str(w.cget("text")) for w in todos(app.frame) if w.winfo_class() in ("TButton", "Button", "TMenubutton")]
ok("Imprimir" not in rot, "painel do item não tem botão Imprimir")
chave = c.nova_chave_acesso()[1]
def clicar():
    """Com a janela da chave aberta: imprime e fecha."""
    d = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)][-1]
    b = next((w for w in todos(d) if w.winfo_class() == "TButton" and str(w.cget("text")).startswith("Imprimir só a chave")), None)
    ok(b is not None, "janela da chave de acesso tem 'Imprimir só a chave…'")
    if b is not None: b.invoke()
    root.update()
    d.destroy()
root.after(400, clicar)
app.mostrar_chave_acesso(chave, c.MODO_OU); root.update()
ok(len(impressos) == 1, "imprimiu uma folha")
texto = " ".join(str(x) for l in impressos[0] for x in (l[1] if isinstance(l[1], tuple) else (l[1],))) if impressos else ""
ok(chave in texto, "a folha tem a chave de acesso")
ok("Banco Azul" not in texto and "SegredoNaoImprimir" not in texto and "maria" not in texto, "a folha NÃO tem dado de item nem senha")
ok(not any(l[0] == "campo" and l[1][0] not in ("Chave de acesso", "") for l in impressos[0]), "um único campo: 'Chave de acesso'")
root.destroy()
print("FALHAS:", f.count(False)); sys.exit(1 if False in f else 0)
