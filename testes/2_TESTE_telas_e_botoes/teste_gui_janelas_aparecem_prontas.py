# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Janelas e telas aparecem PRONTAS: mede cada janela no instante em que ela é mostrada e de novo depois que "assenta"
(0,8 s). Se o tamanho da janela ou a posição/tamanho de QUALQUER botão, texto ou campo mudar depois de aparecer, é o
defeito visual de "janela que aparece cortada/montando e depois se ajeita" (o teste de recorte espera a janela firmar e por
isso não via isso). Cobre a tela de criar, desbloqueio, tela principal e todos os diálogos. Linux (xvfb-run) ou Windows."""
import os, sys, time, tempfile
_RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, _RAIZ); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "6_TESTE_ferramentas_dos_testes"))
import _resultado; _resultado.registrar(__file__)
import tkinter as tk
from tkinter import messagebox, filedialog
import cofre_senhas as c

f = []
def ok(cond, nome, detalhe=""):
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome + ((" -> " + detalhe) if (detalhe and not cond) else ""), flush=True); f.append(bool(cond))
messagebox.showinfo = messagebox.showwarning = messagebox.showerror = lambda *a, **k: None
messagebox.askyesno = lambda *a, **k: False
filedialog.askopenfilename = filedialog.asksaveasfilename = filedialog.askdirectory = lambda *a, **k: ""
tk.Misc.wait_window = lambda self, window=None: None

ESPERA = 0.8        # quanto esperar a janela "assentar"; qualquer mudança depois de aparecer conta como defeito
TOL = 1             # px de tolerância (arredondamento)

def todos(w):
    """Todos os widgets filhos, recursivamente."""
    for x in w.winfo_children():
        try: yield x; yield from todos(x)
        except tk.TclError: pass

def retrato(topo):
    """{caminho: (x, y, largura, altura)} dos widgets de uma janela (posições relativas ao pai de cada um)."""
    r = {}
    for w in todos(topo):
        try: r[str(w)] = (w.winfo_x(), w.winfo_y(), w.winfo_width(), w.winfo_height(), w.winfo_class())
        except tk.TclError: pass
    return r

def mudancas(antes, depois):
    """Lista legível do que mudou entre dois retratos: widgets que andaram/cresceram/encolheram, ou surgiram depois."""
    r = []
    for p, a in antes.items():
        b = depois.get(p)
        if b is None: continue
        if any(abs(a[i] - b[i]) > TOL for i in range(4)):
            r.append("%s %s: %dx%d@%d,%d -> %dx%d@%d,%d" % (a[4], p.split(".")[-1], a[2], a[3], a[0], a[1], b[2], b[3], b[0], b[1]))
    novos = [p for p in depois if p not in antes and depois[p][2] > 1 and depois[p][3] > 1]
    if novos: r.append("%d widget(s) novo(s) só depois de aparecer (ex.: %s)" % (len(novos), novos[0].split(".")[-1]))
    return r

REVELADAS = []                       # uma entrada por janela (Toplevel) no instante em que foi mostrada
_orig = tk.Wm.wm_deiconify
def deiconify_medindo(self, *a):
    """Mostra a janela e processa o mapeamento e o layout inicial antes do retrato.
    No Windows, update_idletasks sozinho não processa as mensagens de geometria do sistema."""
    r = _orig(self, *a)
    if isinstance(self, tk.Toplevel) and not getattr(self, "_rev_ok", False):
        try:
            self.update()
            self._rev_ok = True
            REVELADAS.append({"j": self, "titulo": self.title(), "req": (self.winfo_width(), self.winfo_height()), "foto": retrato(self), "t": time.perf_counter()})
        except tk.TclError:
            pass
    return r
tk.Wm.wm_deiconify = tk.Wm.deiconify = deiconify_medindo

def esperar(seg):
    """Roda o laço do Tk por `seg` segundos (timers e idle disparam como no uso real)."""
    t0 = time.time()
    while time.time() - t0 < seg:
        if "app" in globals() and app.cofre is not None:
            app._ultimo_tique = time.time()
        root.update(); time.sleep(0.005)

def conferir_janelas(rotulo):
    """Para cada janela revelada desde a última conferência: tamanho no 1º quadro x tamanho final, e retrato dos widgets."""
    novas = [r for r in REVELADAS if not r.get("visto")]
    ok(bool(novas), "%s: abriu uma janela" % rotulo)
    for r in novas:
        r["visto"] = True
        j = r["j"]
        try:
            j.update_idletasks()
            final = (j.winfo_width(), j.winfo_height())
            dif = mudancas(r["foto"], retrato(j))
        except tk.TclError:
            continue
        if abs(final[0] - r["req"][0]) > TOL or abs(final[1] - r["req"][1]) > TOL:
            dif.insert(0, "a JANELA apareceu com %dx%d e ficou %dx%d" % (r["req"][0], r["req"][1], final[0], final[1]))
        ok(not dif, "%s: janela '%s' aparece pronta (nada muda depois de aparecer)" % (rotulo, r["titulo"]), "; ".join(dif[:4]))

W = tempfile.mkdtemp(prefix="jp_"); P = os.path.join(W, "t.dat"); SENHA = "cavalo azul come pizza na chuva"
v = c.Cofre.criar(P, SENHA, 3, c.MODO_S, "alto")
v.registros += [c.novo_item(servico="Banco com um nome bem comprido para testar o corte", login="joao.silva@exemplo.com.br", senha="Xk9$mQ2!vL7@pR4#", grupo="Banco"),
                c.novo_item(servico="Google", login="joao", senha="Yz8#nB3@wM6$tQ1!", grupo="Google", pessoa="Pai")]
v.salvar(); v.fechar()
os.remove(P + ".bak1") if os.path.exists(P + ".bak1") else None

for geo in ("1366x768", "900x600"):
    print("== tamanho da janela principal %s" % geo, flush=True)
    root = tk.Tk(); root.withdraw(); root.geometry(geo + "+0+0")
    app = c.App(root, P)
    app._app_sem_foco = lambda: False                 # o PC de teste pode estar com outro programa na frente: isso não é o que se mede aqui
    # --- a janela principal, pelo caminho REAL de abertura (escondida -> montada -> revelada de uma vez) ---
    os.rename(P, P + ".guardado")
    app.mostrar_inicio()
    root.update_idletasks()
    c.revelar_janela(root)
    antes = retrato(root)
    esperar(ESPERA)
    dif = mudancas(antes, retrato(root))
    ok(not dif, "%s: tela de criar aparece pronta (nada muda depois de aparecer)" % geo, "; ".join(dif[:4]))
    os.rename(P + ".guardado", P)
    app.mostrar_inicio(); root.update_idletasks(); antes = retrato(root); esperar(ESPERA); dif = mudancas(antes, retrato(root))
    ok(not dif, "%s: tela de desbloqueio aparece pronta" % geo, "; ".join(dif[:4]))
    app.cofre = c.Cofre.abrir(P, senha=SENHA)
    app.tela_principal(); root.update_idletasks(); antes = retrato(root); esperar(ESPERA); dif = mudancas(antes, retrato(root))
    ok(not dif, "%s: tela principal aparece pronta" % geo, "; ".join(dif[:4]))
    reg = app.cofre.registros[0]
    for nome, chama in (("Novo item", lambda: app.novo()), ("Editar item", lambda: app.dialogo_registro(reg)),
                        ("Gerador de senhas", lambda: app.dialogo_gerador()), ("Bloqueio automático", lambda: app.configurar_bloqueio()),
                        ("Tentativas erradas", lambda: app.configurar_tentativas()), ("Chaves FIDO", lambda: app.gerenciar_fido()),
                        ("Verificar senhas", lambda: app.verificar_senhas()),
                        ("Histórico de aberturas", lambda: app.historico_aberturas()), ("Diagnóstico", lambda: app.ver_diagnostico()),
                        ("Verificar integridade", lambda: app.verificar_integridade()), ("Trocar senha mestra", lambda: app.trocar_senha()),
                        ("Proteção extra", lambda: app.configurar_protecao_extra()), ("Computadores autorizados", lambda: app.gerenciar_computadores()),
                        ("Segurança adicional", lambda: app.tela_seguranca_adicional())):
        try:
            chama(); root.update_idletasks()
        except Exception as ex:
            ok(False, "%s: %s abre sem erro" % (geo, nome), repr(ex)[:120]); continue
        esperar(ESPERA)
        conferir_janelas("%s: %s" % (geo, nome))
        for t in [x for x in root.winfo_children() if isinstance(x, tk.Toplevel)]:
            try: t.destroy()
            except tk.TclError: pass
        root.update()
    app.cofre.fechar(); app.cofre = None
    app._cancelar_todos_after()
    root.destroy()
tk.Wm.wm_deiconify = tk.Wm.deiconify = _orig
print("\nTODOS OK" if all(f) else "\nHOUVE FALHAS (%d)" % f.count(False))
sys.exit(0 if all(f) else 1)
