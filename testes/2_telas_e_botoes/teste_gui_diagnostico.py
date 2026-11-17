"""Teste de interface (Tk): menu ⋯ › Diagnóstico mostra os registros cifrados (só com o cofre aberto), pendrive removido
durante uma gravação mostra mensagem clara (sem caminho) e não perde nada na memória. Veja testes/COMO_RODAR_OS_TESTES.md."""
import os as _os, sys as _sys, tempfile as _tf
_RAIZ = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".."))
import os, sys, errno, base64
sys.path.insert(0, _RAIZ)
import tkinter as tk, cofre_senhas as c
from tkinter import messagebox
W = _tf.mkdtemp(prefix="cofre_gui_"); P = os.path.join(W, "g.dat")
SENHA = "cavalo azul come pizza na chuva"
FAL = []
def ok(cond, msg):
    print(("  [OK]   " if cond else "  [FALHOU] ") + msg)
    if not cond: FAL.append(msg)
v = c.Cofre.criar(P, SENHA, 5, c.MODO_OU, "alto"); v.salvar()
log = []
messagebox.showinfo = lambda *a, **k: log.append(("INFO",) + a)
messagebox.showerror = lambda *a, **k: log.append(("ERRO",) + a)
messagebox.askyesno = lambda *a, **k: True
root = tk.Tk(); app = c.App(root, P)
app.cofre = c.Cofre.abrir(P, senha=SENHA); app.tela_principal(); root.update()
def topos(): return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
def achar_tree(w):
    for ch in w.winfo_children():
        if ch.winfo_class() == "Treeview": return ch
        r = achar_tree(ch)
        if r: return r
def achar(w, txt):
    for ch in w.winfo_children():
        if ch.winfo_class() == "TButton" and str(ch.cget("text")).startswith(txt): return ch
        r = achar(ch, txt)
        if r: return r

# 1) vazio
app.ver_diagnostico(); root.update()
d = topos()[-1]; tree = achar_tree(d)
ok(len(tree.get_children()) == 0, "sem falhas anotadas: a lista vem vazia")
d.destroy(); root.update()

# 2) com registros
c.diag_registrar(c.DIAG_GRAVACAO, OSError(errno.ENOSPC, "sem espaço em " + P))
c.diag_registrar(c.DIAG_LEITURA, OSError(errno.EIO, "x"))
app.ver_diagnostico(); root.update()
d = topos()[-1]; tree = achar_tree(d)
linhas = [tree.item(i, "values") for i in tree.get_children()]
ok(len(linhas) == 2 and "Falha ao ler" in linhas[0][1] and "Falha ao gravar" in linhas[1][1], "lista os 2 registros, o mais recente primeiro")
ok("espaço" in linhas[1][1] and W not in " ".join(" ".join(x) for x in linhas), "mostra a causa em português e nenhum caminho")
# 3) limpar
achar(d, "Limpar").invoke(); root.update()
app.ver_diagnostico(); root.update()
d = topos()[-1]; tree = achar_tree(d)
ok(len(tree.get_children()) == 0, "Limpar registro esvazia a lista")
d.destroy(); root.update()

# 4) pendrive removido durante uma gravação: mensagem clara, memória intacta, cofre no disco intacto
antes = open(P, "rb").read()
n0 = len(app.cofre.registros)
real = os.fsync
def fsync_ruim(fd): raise OSError(errno.EIO, "pendrive removido", P)
os.fsync = fsync_ruim
try:
    r = app._transacao(lambda: app.cofre.registros.append(c.novo_item(servico="Novo", login="x", senha="y")))
finally:
    os.fsync = real
ok(r is False, "gravar com o pendrive saindo devolve False")
ok(len(app.cofre.registros) == n0, "a operação foi desfeita na memória (nada de estado pela metade)")
ok(open(P, "rb").read() == antes and not os.path.exists(P + ".tmp"), "o arquivo do cofre no disco ficou intacto e sem .tmp")
erros = [x for x in log if x[0] == "ERRO"]
ok(erros and "pendrive" in erros[-1][2].lower() and W not in erros[-1][2] and "Traceback" not in erros[-1][2],
   "mensagem clara em português, sem caminho")
priv = base64.b64decode(app.cofre.meta["diag_priv"])
res = c.diag_ler(P, priv)
ok(res and res[0][-1][1] == c.DIAG_GRAVACAO and res[0][-1][2] == errno.EIO, "a falha ficou registrada (código + errno) no diagnóstico")
root.destroy()
print("FALHAS:", FAL)
print("TODOS OS TESTES PASSARAM" if not FAL else "HÁ FALHAS")
sys.exit(1 if FAL else 0)
