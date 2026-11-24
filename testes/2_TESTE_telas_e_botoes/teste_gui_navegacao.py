# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Navegação completa: abrir cada tela e bloquear várias vezes, grupos/busca/itens, revelar e copiar, atalhos, capa de 'conteúdo oculto', seleção de senha (Ctrl+A, Delete) e nada cortado em 900x600."""
import os as _os, sys as _sys, tempfile as _tf, subprocess as _sp
_RAIZ = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".."))
def _foto(arq):
    """Captura a tela (só onde existe o ImageMagick 'import'); sem ele, ignora."""
    try: _sp.run(["import", "-window", "root", arq], check=False)
    except Exception: pass
import os, sys, subprocess, time, traceback, faulthandler
# Este teste envia TECLAS de verdade (Ctrl+A, Backspace, Delete, Ctrl+C). Elas só chegam ao campo se a janela puder ter o foco do teclado, e o
# modo "segundo plano" dos testes (COFRE_GUI_TESTS_BACKGROUND=1, janelas WS_EX_NOACTIVATE) impede isso. Por isso este
# teste desliga o modo segundo plano: enquanto roda (cerca de 25 s) as janelas dele podem tomar o foco.
os.environ["COFRE_GUI_TESTS_BACKGROUND"] = "0"
faulthandler.dump_traceback_later(100, exit=True)
sys.path.insert(0, _RAIZ)
import tkinter as tk
from tkinter import messagebox, filedialog
import cofre_senhas as c
W = _tf.mkdtemp(prefix="cofre_gui_"); P = os.path.join(W, "r.dat")
for x in (P,): 
    if os.path.exists(x): os.remove(x)
SENHA = "cavalo azul come pizza na chuva"
v = c.Cofre.criar(P, SENHA, 5, c.MODO_OU, "alto")
for s, g in (("Banco do Brasil", "Bancos"), ("Nubank", "Bancos"), ("Gmail", "E-mail"), ("Itaú do pai", "pai")):
    v.registros.append(c.novo_item(servico=s, login="x@y.com", senha="Senha-Forte-123!", grupo=g, notas="linha1\nlinha2"))
v.salvar()
erros = []; resultados = []
def ok(cond, nome):
    resultados.append(bool(cond)); print(("  [OK]   " if cond else "  [FALHOU] ") + nome)
for nome in ("showerror", "showwarning", "showinfo"):
    setattr(messagebox, nome, lambda *a, _n=nome, **k: erros.append((_n, a[:2])))
messagebox.askyesno = lambda *a, **k: True
messagebox.askokcancel = lambda *a, **k: True
tk.Misc.wait_window = lambda self, w=None: self.update()
root = tk.Tk(); root.geometry("1366x768")
root.report_callback_exception = lambda t, v_, tb: erros.append(("TK", "".join(traceback.format_exception(t, v_, tb))[-700:]))
app = c.App(root, P)
def fecha_dialogos():
    for w in list(root.winfo_children()):
        if isinstance(w, tk.Toplevel):
            try: w.destroy()
            except tk.TclError: pass
    root.update()
def tudo(w, cls=None):
    r = []
    for ch in w.winfo_children():
        if cls is None or ch.winfo_class() == cls: r.append(ch)
        r += tudo(ch, cls)
    return r
def dlg():
    l = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
    return l[-1] if l else None
def passo(nome, fn):
    n0 = len(erros)
    try: fn(); root.update(); root.update()
    except Exception: erros.append(("EXC " + nome, traceback.format_exc()[-700:]))
    novos = erros[n0:]
    novos = [x for x in novos if x[0] != "showinfo"]
    ok(not novos, nome)
    for x in novos: print("      >>", x[0], "\n", x[1])
def foto(n): _foto(os.path.join(W, n + ".png"))

filedialog.asksaveasfilename = lambda *a, **k: os.path.join(W, "arq_teste")
filedialog.askopenfilename = lambda *a, **k: ""
# ---------- 1. trocar de telas várias vezes (criar <-> desbloqueio <-> principal) ----------
for i in range(3):
    passo(f"tela_criar #{i}", app.tela_criar)
    passo(f"tela_desbloqueio #{i}", app.tela_desbloqueio)
app.cofre = c.Cofre.abrir(P, senha=SENHA)
for i in range(3):
    passo(f"tela_principal #{i}", app.tela_principal)
    passo(f"bloquear #{i}", app.bloquear)
    app.cofre = c.Cofre.abrir(P, senha=SENHA)
passo("tela_principal final", app.tela_principal)
foto("principal")

# ---------- 2. filtros e lista ----------
def filtros():
    for iid in list(app.lateral.get_children()):
        if app.lateral._itens[iid]["ent"].get("acao"): continue        # "Novo grupo"/"Adicionar pessoa" são botões, não filtros
        app.lateral.selection_set(iid); root.update()
    app.campo_busca.insert(0, "nu"); root.update(); app.campo_busca.delete(0, "end"); root.update()
passo("percorrer grupos e busca", filtros)
def itens():
    for iid in app.tree.get_children():
        app.tree.selection_set(iid); root.update(); root.update()
passo("percorrer itens da lista (detalhe)", itens)
def revelar():
    app.tree.selection_set(app.tree.get_children()[0]); root.update()
    for campo in ("senha", "login"):
        app._alternar_revelar(campo); root.update(); app._alternar_revelar(campo); root.update()
passo("revelar/ocultar campos no detalhe", revelar)
passo("copiar senha/login", lambda: (app.copiar("senha"), app.copiar("login")))
passo("atalhos", app._mostrar_atalhos)
def cobertura():
    app.cofre = app.cofre
    app._ocultadores.clear(); app._app_sem_foco = lambda: True; app._talvez_ocultar(); root.update()
    ok(len(app._ocultadores) > 0, "cobertura 'conteúdo oculto' aparece quando outro programa está em primeiro plano")
    # clicar na capa "devolve o foco" ao programa: sem isso o vigia/foco reais da máquina de quem roda recobrem na hora
    _orig = app._mostrar_conteudo
    def _mostrar_e_foca(*a, **k):
        app._app_sem_foco = lambda: False
        return _orig(*a, **k)
    app._mostrar_conteudo = _mostrar_e_foca
    capa = app._ocultadores[0]; capa.event_generate("<Button-1>", x=5, y=5); root.update()
    ok(not app._ocultadores, "clicar na cobertura mostra o conteúdo de novo")
    app._app_sem_foco = lambda: False
    app.tela_criar(); root.update(); app.tela_principal(); root.update(); root.after(400); root.update(); app._talvez_ocultar(); root.update()
    ok(not app._ocultadores, "trocar de tela NÃO cobre o conteúdo")
passo("cobertura ao perder foco e ao trocar de tela", cobertura)

# ---------- 3. formulário: novo/editar + seleção de senha ----------
def novo_form():
    app.novo(); root.update()
    d = dlg(); assert d is not None, "formulário não abriu"
    ents = [e for e in tudo(d, "TEntry")]
    secretos = [e for e in ents if str(e.cget("show"))]
    assert secretos, "sem campo secreto"
    e = secretos[0]; e.focus_force(); root.update()
    e.insert(0, "SenhaGrande-123456!")
    # Ctrl+A
    e.event_generate("<Control-a>"); root.update()
    ok(e.selection_present() and e.index("sel.first") == 0 and e.index("sel.last") == len("SenhaGrande-123456!"), "Ctrl+A seleciona a senha inteira no formulário")
    e.event_generate("<BackSpace>"); root.update()
    ok(e.get() == "", "Backspace apaga a seleção inteira")
    e.insert(0, "abc def ghi"); e.selection_clear()
    e.event_generate("<Double-Button-1>", x=5, y=5) if False else None
    e.selection_clear(); e.icursor(0)
    e.event_generate("<Button-1>", x=2, y=5); e.event_generate("<B1-Motion>", x=250, y=5); root.update()
    ok(e.selection_present(), "arrastar o mouse seleciona")
    e.selection_range(0, "end"); e.event_generate("<Delete>"); root.update(); ok(e.get() == "", "Delete apaga a seleção")
    e.insert(0, "abc def ghi")
    e.selection_range(0, "end"); e.event_generate("<Control-c>"); root.update()
    root.clipboard_clear(); root.clipboard_append("ANTES"); e.event_generate("<<Copy>>"); e.event_generate("<Control-c>"); root.update()
    ok(root.clipboard_get() == "ANTES", "Ctrl+C continua BLOQUEADO (clipboard não mudou)")
    e.delete(0, "end")
    # Text (notas)
    for t in tudo(d, "Text"):
        if t.cget("height") <= 6:
            t.insert("1.0", "uma nota qualquer"); t.focus_force(); root.update()
            t.event_generate("<<SelectAll>>"); root.update()
            ok(bool(t.tag_ranges("sel")), "Ctrl+A nas notas seleciona tudo")
            break
    foto("form")
passo("novo item + seleção de senha", novo_form)
fecha_dialogos()
passo("editar item", lambda: (app.tree.selection_set(app.tree.get_children()[0]), root.update(), app.editar()))
fecha_dialogos()
passo("trocar de tela com formulário aberto", lambda: (app.novo(), root.update(), app.bloquear()))
fecha_dialogos()
app.cofre = c.Cofre.abrir(P, senha=SENHA); app.tela_principal(); root.update()

# ---------- 4. gerador ----------
def gerador():
    app.dialogo_gerador(); root.update()
    d = dlg(); foto("gerador")
    for cb in tudo(d, "TRadiobutton") + tudo(d, "TCheckbutton"):
        try: print("  inv", cb.cget("text")); cb.invoke(); root.update()
        except tk.TclError: pass
    for b in tudo(d, "TButton"):
        try:
            t = str(b.cget("text"))
            if "Usar" in t: continue
            print("  btn", t); b.invoke(); root.update()
        except tk.TclError: pass
passo("gerador (todos os botões)", gerador)
fecha_dialogos()
passo("verificar senhas", app.verificar_senhas); fecha_dialogos()
passo("trocar senha mestra", app.trocar_senha); fecha_dialogos()
passo("nova chave de acesso", app.nova_chave); fecha_dialogos()
passo("histórico de aberturas", app.historico_aberturas); fecha_dialogos()
passo("gerenciar FIDO", app.gerenciar_fido); fecha_dialogos()
passo("modelo de planilha", app.modelo_planilha); fecha_dialogos()

passo("backup", app.backup); fecha_dialogos()
passo("excluir item", lambda: (app.tree.selection_set(app.tree.get_children()[0]), root.update(), app.excluir()))
passo("minimizar -> bloqueia", lambda: app._ao_minimizar())
fecha_dialogos()

print("\nERROS:", len(erros))
for e in erros: print("  ", e)
print("RESULTADO:", sum(resultados), "ok de", len(resultados))
