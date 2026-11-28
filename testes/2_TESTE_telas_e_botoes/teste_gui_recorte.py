# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Recorte de texto e de botões: em vários tamanhos de janela, nenhuma tela nem janela pode ter rótulo/botão/campo
CORTADO (largura/altura real menor que a pedida) nem widget fora da área visível da janela. Roda no Windows ou no
Linux (xvfb-run -a)."""
import time, os, sys, tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
import tkinter as tk
from tkinter import messagebox
import cofre_senhas as c
f = []
def ok(cond, nome, detalhe=""):
    """Registra uma verificação."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome + ((" -> " + detalhe) if (detalhe and not cond) else "")); f.append(bool(cond))
messagebox.showinfo = messagebox.showwarning = messagebox.showerror = lambda *a, **k: None
messagebox.askyesno = lambda *a, **k: False
tk.Misc.wait_window = lambda self, window=None: None
def todos(w):
    """Todos os widgets filhos, recursivamente."""
    for x in w.winfo_children():
        if isinstance(x, tk.Toplevel):
            continue
        try: yield x; yield from todos(x)
        except tk.TclError: pass
CLASSES = ("TLabel", "Label", "TButton", "Button", "TCheckbutton", "TRadiobutton", "TEntry", "Entry", "TCombobox")
def em_area_rolavel(w):
    """True se o widget está dentro de um Canvas que tem uma barra de rolagem VISÍVEL ao lado (ex.: o diálogo 'Novo item'
    quando a janela é pequena): o que está fora da vista não é texto cortado, é conteúdo que se alcança rolando."""
    p = w.master
    while p is not None:
        if isinstance(p, tk.Canvas):
            try:
                return any(x.winfo_class() == "TScrollbar" and x.winfo_ismapped() for x in p.master.winfo_children())
            except tk.TclError:
                return False
        p = getattr(p, "master", None)
    return False
def cortados(topo, tol=3):
    """Widgets visíveis cujo tamanho real é menor que o pedido (texto cortado) ou que passam da borda da janela."""
    ruins = []
    try: topo.update_idletasks()
    except tk.TclError: return ruins
    tx0, ty0 = topo.winfo_rootx(), topo.winfo_rooty()
    tx1, ty1 = tx0 + topo.winfo_width(), ty0 + topo.winfo_height()
    for w in todos(topo):
        try:
            if w.winfo_class() not in CLASSES or not w.winfo_ismapped(): continue
            if w.winfo_width() <= 1 or w.winfo_height() <= 1: continue
            nome = f"{w.winfo_class()}[{str(w.cget('text'))[:30]!r}]" if "text" in w.keys() else w.winfo_class()
            texto = str(w.cget("text")) if "text" in w.keys() else ""
            imagem = str(w.cget("image")) if "image" in w.keys() else ""
            sem_conteudo = w.winfo_class() in ("TLabel", "Label") and not texto and not imagem
            if (w.winfo_width() + tol < w.winfo_reqwidth()
                    and w.winfo_class() not in ("TEntry", "Entry", "TCombobox") and not sem_conteudo):
                ruins.append(f"{nome} largura {w.winfo_width()} < {w.winfo_reqwidth()}")
            if w.winfo_height() + tol < w.winfo_reqheight():
                ruins.append(f"{nome} altura {w.winfo_height()} < {w.winfo_reqheight()}")
            if (w.winfo_rootx() + w.winfo_width() > tx1 + tol or w.winfo_rooty() + w.winfo_height() > ty1 + tol) \
                    and not em_area_rolavel(w):
                ruins.append(f"{nome} passa da borda da janela")
        except tk.TclError:
            continue
    return ruins

W = tempfile.mkdtemp(prefix="rc_"); P = os.path.join(W, "t.dat"); SENHA = "cavalo azul come pizza na chuva"
for geo in ("1366x768", "1024x640", "900x600"):
    root = tk.Tk()
    gw, gh = (int(x) for x in geo.split("x"))
    if gw > root.winfo_screenwidth() or gh > root.winfo_screenheight():
        print(f"  [PULADO] {geo}: maior que a tela ({root.winfo_screenwidth()}x{root.winfo_screenheight()})", flush=True)
        root.destroy()
        continue
    root.geometry(geo + "+0+0")
    app = c.App(root, P); root.update()
    for p in (P, P + ".bak1"):
        if os.path.exists(p): os.remove(p)
    def fotos(titulo):
        """Confere a janela principal e todas as janelas abertas."""
        t0 = time.time()
        while time.time() - t0 < 0.25: root.update(); time.sleep(0.01)    # o diálogo se ajusta com debounce de 30 ms
        r = cortados(root)
        for t in [x for x in root.winfo_children() if isinstance(x, tk.Toplevel)]:
            r += ["(janela " + t.title() + ") " + x for x in cortados(t)]
        ok(not r, f"{geo}: {titulo}: nada cortado", "; ".join(r[:4]))
    app.mostrar_inicio(); fotos("tela de criar")
    v = c.Cofre.criar(P, SENHA, 3, c.MODO_S, "alto")
    v.registros += [c.novo_item(servico="Banco com um nome bem comprido para testar o corte do texto na lista", login="joao.silva.pereira@exemplo.com.br", senha="Xk9$mQ2!vL7@pR4#", grupo="Banco"),
                    c.novo_item(servico="Google", login="joao", senha="Yz8#nB3@wM6$tQ1!", grupo="Google", pessoa="Pai")]
    v.salvar(); v.fechar()
    app.mostrar_inicio(); fotos("tela de desbloqueio")
    app.cofre = c.Cofre.abrir(P, senha=SENHA); app.tela_principal(); fotos("tela principal")
    for nome, chama in (("Novo item", lambda: app.novo()), ("Gerador", lambda: app.dialogo_gerador()),
                        ("Bloqueio automático", lambda: app.configurar_bloqueio()), ("Tentativas erradas", lambda: app.configurar_tentativas()),
                        ("Chaves FIDO", lambda: app.gerenciar_fido()), ("Guia (?)", lambda: app._mostrar_atalhos()),
                        ("Verificar senhas", lambda: app.verificar_senhas()), ("Histórico", lambda: app.historico_aberturas())):
        try: chama(); root.update(); fotos(nome)
        except Exception as ex: ok(False, f"{geo}: {nome} abre sem erro", repr(ex)[:120])
        for t in [x for x in root.winfo_children() if isinstance(x, tk.Toplevel)]: t.destroy()
        root.update()
    app.cofre.fechar(); app.cofre = None
    app._cancelar_todos_after()
    root.destroy()
print("FALHAS:", f.count(False)); sys.exit(1 if False in f else 0)
