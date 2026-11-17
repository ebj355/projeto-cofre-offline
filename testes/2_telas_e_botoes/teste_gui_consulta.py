"""Interface do MODO CONSULTA: pendrive protegido contra gravação. Entra pela tela de senha (a escrita é bloqueada), aceita
a oferta do modo consulta, confere o aviso na tela principal e que as ações que alteram dados só explicam e voltam."""
import os, sys, errno, builtins, tempfile
RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, RAIZ)
import tkinter as tk, cofre_senhas as c
from tkinter import messagebox
f = []


def ok(cond, nome):
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome, flush=True); f.append(bool(cond))


W = tempfile.mkdtemp(prefix="cofre_gui_"); P = os.path.join(W, "a.dat"); S = "cavalo azul come pizza na chuva"
v = c.Cofre.criar(P, S, 5, 0, "alto"); v.registros.append(c.novo_item(servico="Banco", senha="x")); v.salvar()
original = open(P, "rb").read()
log = []
messagebox.showinfo = lambda *a, **k: log.append(("info", a[0]))
messagebox.showerror = lambda *a, **k: log.append(("erro", a[0]))
messagebox.showwarning = lambda *a, **k: log.append(("aviso", a[0]))
perguntas = []
messagebox.askyesno = lambda *a, **k: (perguntas.append(a[0]), True)[1]
real_open = builtins.open


def open_bloqueado(arq, modo="r", *a, **k):
    try:
        na_pasta = os.path.abspath(os.fspath(arq)).startswith(os.path.abspath(W))
    except TypeError:
        na_pasta = False
    if na_pasta and isinstance(modo, str) and any(ch in modo for ch in "wax+"):
        raise PermissionError(errno.EACCES, "Acesso negado (simulação de pendrive protegido)")
    return real_open(arq, modo, *a, **k)


builtins.open = open_bloqueado
root = tk.Tk(); app = c.App(root, P)


def achar(w, txt, cls=("TButton",)):
    for ch in w.winfo_children():
        if ch.winfo_class() in cls and str(ch.cget("text")).startswith(txt):
            return ch
        r = achar(ch, txt, cls)
        if r:
            return r


def ents():
    out = []

    def t(w):
        for ch in w.winfo_children():
            if ch.winfo_class() == "TEntry":
                out.append(ch)
            t(ch)
    t(app.frame)
    return out


def textos(w):
    out = []
    for ch in w.winfo_children():
        try:
            out.append(str(ch.cget("text")))
        except tk.TclError:
            pass
        out += textos(ch)
    return out


def p1():
    ents()[0].insert(0, "senha errada qualquer")
    achar(app.frame, "Desbloquear").invoke(); root.after(6000, p2)


def p2():
    ok(app.cofre is None and any("Modo consulta" in t for t in textos(app.frame)),
       "senha errada em modo consulta: mensagem diz que as tentativas não são contadas")
    ents()[0].insert(0, S)
    achar(app.frame, "Desbloquear").invoke(); root.after(9000, p3)


def p3():
    ok(len(perguntas) >= 1 and "protegido contra gravação" in perguntas[0], "a tela ofereceu o MODO CONSULTA ao detectar o pendrive protegido")
    ok(app.cofre is not None and app.cofre.somente_leitura, "entrou na tela principal em modo consulta")
    ok(any("MODO CONSULTA" in t for t in textos(app.frame)), "aviso 'MODO CONSULTA' visível no topo da tela")
    ok(len(app.cofre.registros) == 1, "o item está lá para leitura")
    log.clear()
    antes = list(app.cofre.registros)
    app.excluir()
    app.dialogo_registro(None)
    app.trocar_senha()
    app.importar()
    ok(len([x for x in log if x[1] == "Modo consulta"]) == 4, "excluir, novo/editar, trocar senha e importar só explicam e voltam")
    ok(app.cofre.registros == antes, "nada foi alterado")
    builtins.open = real_open
    ok(real_open(P, "rb").read() == original, "arquivo do cofre idêntico ao original no fim")
    root.destroy()


root.after(500, p1)
root.mainloop()
builtins.open = real_open
print("FALHOU" if not all(f) else "TUDO OK", len(f), "verificações")
sys.exit(0 if all(f) else 1)
