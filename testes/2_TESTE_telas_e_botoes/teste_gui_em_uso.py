# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""COFRE ABERTO EM OUTRA JANELA: a segunda janela (App(..., em_uso=True)) vai direto para o MODO CONSULTA, sem perguntar,
com faixa de aviso própria, ações que alteram dados só explicam e nada é gravado. Também confere a faixa de REVERSÃO."""
import os, sys, tempfile, shutil
RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, RAIZ)
import tkinter as tk, cofre_senhas as c
from tkinter import messagebox
f = []


def ok(cond, nome):
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome, flush=True); f.append(bool(cond))


W = tempfile.mkdtemp(prefix="cofre_gui_"); P = os.path.join(W, "a.dat"); S = "cavalo azul come pizza na chuva"
v = c.Cofre.criar(P, S, 5, 0, "alto"); v.registros.append(c.novo_item(servico="Banco", senha="x")); v.salvar(forcar_copia=True)
v.registros.append(c.novo_item(servico="Outro", senha="y")); v.salvar(forcar_copia=True); v.salvar(forcar_copia=True)
shutil.copy(P + ".bak2", P)                       # arquivo principal "voltou no tempo": cópia mais nova ao lado
with open(P, "rb") as _f:
    original = _f.read()
log, perguntas = [], []
messagebox.showinfo = lambda *a, **k: log.append(("info", a[0]))
messagebox.showerror = lambda *a, **k: log.append(("erro", a[0]))
messagebox.showwarning = lambda *a, **k: log.append(("aviso", a[0]))
messagebox.askyesno = lambda *a, **k: (perguntas.append(a[0]), True)[1]
root = tk.Tk(); app = c.App(root, P, em_uso=True)


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
    ents()[0].insert(0, "errada qualquer")
    achar(app.frame, "Desbloquear").invoke(); root.after(6000, p2)


def p2():
    ok(app.cofre is None and any("não é contada" in t for t in textos(app.frame)), "senha errada: não conta tentativa")
    ents()[0].delete(0, "end"); ents()[0].insert(0, S)
    achar(app.frame, "Desbloquear").invoke(); root.after(9000, p3)


def p3():
    ok(perguntas == [], "não perguntou nada: foi direto para o modo consulta")
    ok(app.cofre is not None and app.cofre.somente_leitura and app.cofre.motivo_consulta == "em_uso", "abriu em modo consulta (motivo: em uso)")
    t = textos(app.frame)
    ok(any("OUTRA janela" in x for x in t), "faixa diz que o cofre está aberto em OUTRA janela")
    ok(any("MAIS ANTIGO" in x for x in t), "faixa vermelha de reversão aparece (arquivo mais velho que a cópia)")
    root.after(1000, p4)


def p4():
    ok(any(x[0] == "aviso" and "reversão" in x[1] for x in log), "aviso de possível reversão mostrado uma vez")
    log.clear()
    app.excluir(); app.dialogo_registro(None); app.trocar_senha(); app.importar()
    ok(len([x for x in log if x[1] == "Modo consulta"]) == 4, "ações que alteram dados só explicam e voltam")
    with open(P, "rb") as _f:
        agora = _f.read()
    ok(agora == original, "arquivo idêntico ao original")
    ok(not os.path.exists(P + ".tmp"), "nenhum arquivo temporário criado")
    root.destroy()


root.after(500, p1)
root.mainloop()
print("FALHOU" if not all(f) else "TUDO OK", len(f), "verificações")
sys.exit(0 if all(f) else 1)
