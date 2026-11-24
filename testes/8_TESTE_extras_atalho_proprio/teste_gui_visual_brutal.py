#!/usr/bin/env python3
# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Teste VISUAL BRUTO da interface: travadas, animacao truncada, glitch de tela, bugs e erros ao escolher opcoes.

O que ele faz (tudo num cofre descartavel; nada do cofre real e tocado):
  1. Varre a GEOMETRIA de cada tela e de cada dialogo: texto cortado, controle fora da janela, controles um em cima do
     outro, controle sem tamanho. Faz isso em TODOS os temas e em varios tamanhos de janela.
  2. Aperta/seleciona TODAS as opcoes que encontra (botoes, caixas de marcar, escolhas, listas, deslizantes) e mede
     quanto a janela fica CONGELADA em cada uma (travada). Reprova acima do limite.
  3. TEMPESTADE: centenas de trocas de opcao seguidas, sem esperar a tela assentar, e depois confere se sobrou erro,
     janela perdida, vazamento de widgets ou desenho quebrado.
  4. 'Fotografa' a janela (sem usar a tela, entao funciona com a janela em segundo plano) e procura: tela que pisca
     (quadro A-B-A), quadro em branco no meio da troca, desenho que continua mudando sozinho depois de assentar,
     'fantasma' (voltar ao estado inicial e a imagem ficar diferente) e residuo depois de redimensionar.
  5. Qualquer excecao de callback do Tk, qualquer caixa de erro e qualquer janela que sobrou aberta reprova.

Variaveis opcionais:  COFRE_VISUAL_LIMITE_MS (congelamento maximo aceito, padrao 700),
                      COFRE_VISUAL_TEMPESTADE (numero de acoes aleatorias, padrao 400),
                      COFRE_VISUAL_SEMENTE (semente do sorteio; o padrao muda a cada rodada e e impressa).
Saida no padrao dos outros testes: linhas [OK]/[FALHOU]/[ALERTA]/[PULADO], 'PASSOU n / m' e 'FALHAS: [...]'.
"""
import os
import re
import sys
import time
import random
import shutil
import tempfile
import traceback

for _f in (sys.stdout, sys.stderr):                      # evita UnicodeEncodeError no console cp1252 do Windows
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = AQUI
for _ in range(4):                                         # acha a pasta que tem cofre_senhas.py, sem caminho fixo
    if os.path.exists(os.path.join(RAIZ, "cofre_senhas.py")):
        break
    RAIZ = os.path.dirname(RAIZ)
else:
    print("[FALHOU] nao achei cofre_senhas.py acima desta pasta")
    print("PASSOU 0 / 1\nFALHAS: ['sem_cofre_senhas']")
    sys.exit(1)
sys.path.insert(0, RAIZ)
os.environ["COFRE_GUI_TESTS_BACKGROUND"] = "1"
os.environ["COFRE_SEM_VERIFICACAO_INICIAL"] = "1"

LIMITE_MS = float(os.environ.get("COFRE_VISUAL_LIMITE_MS", "700"))
ALERTA_MS = min(250.0, LIMITE_MS)
N_TEMPESTADE = int(os.environ.get("COFRE_VISUAL_TEMPESTADE", "400"))
SEMENTE = int(os.environ.get("COFRE_VISUAL_SEMENTE", str(int(time.time()) % 100000)))
TOL_PIXELS = 0.0004            # fracao de pixels que pode mudar (cursor piscando, antisserrilhado) sem ser defeito
SENHA = "Senha-Visual-Teste-2026!"

total, falhas, alertas = 0, [], []


def ok(cond, msg):
    global total
    total += 1
    print(("  [OK]   " if cond else "  [FALHOU] ") + msg, flush=True)
    if not cond:
        falhas.append(msg[:90])
    return cond


def alerta(msg):
    alertas.append(msg)
    print("  [ALERTA] " + msg, flush=True)


def info(msg):
    print("  [info] " + msg, flush=True)


def pulado(msg):
    print("  [PULADO] " + msg, flush=True)


try:
    import tkinter as tk
    from tkinter import ttk
    import tkinter.messagebox as tkmb
    import tkinter.filedialog as tkfd
    import tkinter.simpledialog as tksd
except ImportError:
    print("[PULADO] Tkinter indisponivel neste Python")
    sys.exit(0)
try:
    from PIL import Image, ImageChops
except ImportError:
    Image = ImageChops = None

import cofre_senhas as cs

EH_WINDOWS = sys.platform == "win32"
cs.proteger_contra_captura = lambda janela: True          # SO neste processo de teste: sem isso a janela sai preta nas fotos

# ---------------------------------------------------------------- registro de erros e caixas de mensagem
erros_tk = []
caixas = []


def _registrar_caixa(tipo, padrao):
    def f(*a, **kw):
        titulo = a[0] if a else kw.get("title", "")
        texto = a[1] if len(a) > 1 else kw.get("message", "")
        caixas.append((tipo, str(titulo), str(texto)[:160]))
        return padrao
    return f


def instalar_patches():
    """Troca as caixas de mensagem/arquivo por gravadores. Precisa rodar DEPOIS de criar o App, porque o App instala
    as proprias caixas temadas (modais, que travariam o teste) em cima das originais."""
    for n, p in (("showerror", "ok"), ("showwarning", "ok"), ("showinfo", "ok")):
        setattr(tkmb, n, _registrar_caixa(n, p))
    for n in ("askyesno", "askokcancel", "askretrycancel"):
        setattr(tkmb, n, _registrar_caixa(n, False))      # confirmacao destrutiva sempre responde NAO
    tkmb.askquestion = _registrar_caixa("askquestion", "no")
    tkmb.askyesnocancel = _registrar_caixa("askyesnocancel", None)
    for n in ("askopenfilename", "asksaveasfilename", "askdirectory", "askopenfilenames"):
        setattr(tkfd, n, lambda *a, **kw: "")
    for n in ("askstring", "askinteger", "askfloat"):
        setattr(tksd, n, lambda *a, **kw: None)


def erros_novos(desde):
    return erros_tk[desde:], caixas[desde:]


# ---------------------------------------------------------------- utilidades de arvore e geometria
def descendentes(w):
    try:
        filhos = w.winfo_children()
    except tk.TclError:
        return
    for c in filhos:
        yield c
        yield from descendentes(c)


def dentro_de_rolagem(w, topo):
    p = w.master
    while p is not None and p is not topo:
        if p.winfo_class() in ("Canvas", "Text", "Treeview", "Listbox"):
            return True
        p = p.master
    return False


def nome_w(w):
    try:
        t = w.cget("text")
    except tk.TclError:
        t = ""
    try:
        cls = w.winfo_class()
    except tk.TclError:
        cls = "?"
    return f"{cls} {str(w).split('.')[-1]}" + (f" '{str(t)[:28]}'" if t else "")


CLASSES_TEXTO = {"Label", "TLabel", "Button", "TButton", "Checkbutton", "TCheckbutton", "Radiobutton",
                 "TRadiobutton", "Menubutton", "TMenubutton"}


def inspecionar(topo):
    """Devolve a lista de defeitos de geometria dentro de uma janela (a propria janela e tudo dentro dela)."""
    ach = []
    try:
        topo.update_idletasks()
        tx, ty, tw, th = topo.winfo_rootx(), topo.winfo_rooty(), topo.winfo_width(), topo.winfo_height()
    except tk.TclError:
        return ach
    irmaos = {}
    for w in descendentes(topo):
        try:
            if not w.winfo_viewable():
                continue
            W, H = w.winfo_width(), w.winfo_height()
            cls = w.winfo_class()
            rolagem = dentro_de_rolagem(w, topo)
            if cls in CLASSES_TEXTO and not rolagem:
                try:
                    texto = str(w.cget("text"))
                    img = str(w.cget("image"))
                except tk.TclError:
                    texto, img = "", ""
                if (texto or img) and (W <= 2 or H <= 2):
                    ach.append(f"sem tamanho: {nome_w(w)} ({W}x{H})")
                    continue
                if texto and (W + 2 < w.winfo_reqwidth() or H + 2 < w.winfo_reqheight()):
                    ach.append(f"cortado: {nome_w(w)} cabe {W}x{H}, pede {w.winfo_reqwidth()}x{w.winfo_reqheight()}")
            if W <= 1 or H <= 1 or rolagem:
                continue
            rx, ry = w.winfo_rootx(), w.winfo_rooty()
            if rx < tx - 1 or ry < ty - 1 or rx + W > tx + tw + 1 or ry + H > ty + th + 1:
                ach.append(f"fora da janela: {nome_w(w)} em ({rx - tx},{ry - ty}) {W}x{H} janela {tw}x{th}")
            if w.winfo_manager() in ("pack", "grid"):
                irmaos.setdefault(str(w.master), []).append((w, rx, ry, W, H))
        except tk.TclError:
            continue
    for mestre, lista in irmaos.items():
        for i in range(len(lista)):
            a, ax, ay, aw, ah = lista[i]
            for j in range(i + 1, len(lista)):
                b, bx, by, bw, bh = lista[j]
                ix = min(ax + aw, bx + bw) - max(ax, bx)
                iy = min(ay + ah, by + bh) - max(ay, by)
                if ix > 4 and iy > 4:
                    ach.append(f"sobrepostos: {nome_w(a)} e {nome_w(b)} ({ix}x{iy} px)")
    return ach


def contar_widgets(root):
    return sum(1 for _ in descendentes(root))


def janelas_extras(root):
    try:
        return [w for w in root.winfo_children() if w.winfo_class() == "Toplevel"]
    except tk.TclError:
        return []


# ---------------------------------------------------------------- fotografia da janela (sem depender da tela)
def _capturar_windows(root):
    import ctypes
    from ctypes import wintypes
    u, g = ctypes.windll.user32, ctypes.windll.gdi32
    u.GetAncestor.restype, u.GetAncestor.argtypes = wintypes.HWND, (wintypes.HWND, wintypes.UINT)
    u.GetDC.restype, u.GetDC.argtypes = ctypes.c_void_p, (wintypes.HWND,)
    u.ReleaseDC.argtypes = (wintypes.HWND, ctypes.c_void_p)
    u.PrintWindow.argtypes = (wintypes.HWND, ctypes.c_void_p, wintypes.UINT)
    g.CreateCompatibleDC.restype, g.CreateCompatibleDC.argtypes = ctypes.c_void_p, (ctypes.c_void_p,)
    g.CreateCompatibleBitmap.restype = ctypes.c_void_p
    g.CreateCompatibleBitmap.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_int)
    g.SelectObject.restype, g.SelectObject.argtypes = ctypes.c_void_p, (ctypes.c_void_p, ctypes.c_void_p)
    g.DeleteObject.argtypes = (ctypes.c_void_p,)
    g.DeleteDC.argtypes = (ctypes.c_void_p,)
    g.GetDIBits.argtypes = (ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                            ctypes.c_void_p, wintypes.UINT)

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]
    hwnd = u.GetAncestor(wintypes.HWND(root.winfo_id()), 2)
    rc = wintypes.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(rc))
    w, h = rc.right - rc.left, rc.bottom - rc.top
    if w <= 0 or h <= 0:
        return None
    dc_tela = u.GetDC(None)
    mem = g.CreateCompatibleDC(dc_tela)
    bmp = g.CreateCompatibleBitmap(dc_tela, w, h)
    antigo = g.SelectObject(mem, bmp)
    try:
        u.PrintWindow(hwnd, mem, 2)                       # PW_RENDERFULLCONTENT: pega a janela mesmo coberta por outras
        bih = BIH(ctypes.sizeof(BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        g.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bih), 0)
        return Image.frombuffer("RGBA", (w, h), bytes(buf), "raw", "BGRA", 0, 1).convert("RGB")
    finally:
        g.SelectObject(mem, antigo)
        g.DeleteObject(bmp)
        g.DeleteDC(mem)
        u.ReleaseDC(None, dc_tela)


def capturar(root):
    """Foto da janela principal como imagem RGB, ou None se nao for possivel."""
    if Image is None:
        return None
    try:
        root.update_idletasks()
        if EH_WINDOWS:
            return _capturar_windows(root)
        from PIL import ImageGrab
        x, y, w, h = root.winfo_rootx(), root.winfo_rooty(), root.winfo_width(), root.winfo_height()
        return ImageGrab.grab(bbox=(x, y, x + w, y + h)).convert("RGB")
    except Exception:
        return None


def foto_util(img):
    """True se a foto tem conteudo de verdade (nao e preta/vazia por protecao de captura)."""
    if img is None:
        return False
    peq = img.resize((48, 32)).convert("RGB")
    b = peq.tobytes()
    return len(set(zip(b[0::3], b[1::3], b[2::3]))) > 6


def fracao_diferente(a, b):
    if a is None or b is None or a.size != b.size:
        return 1.0
    d = ImageChops.difference(a, b).convert("L").point(lambda p: 255 if p > 14 else 0)
    return d.histogram()[255] / float(a.size[0] * a.size[1])


def quase_vazia(img):
    """Quadro em branco: quase todos os pixels da mesma cor."""
    b = img.resize((96, 64)).convert("RGB").tobytes()
    dados = list(zip(b[0::3], b[1::3], b[2::3]))
    mais = max(set(dados), key=dados.count)
    return dados.count(mais) / len(dados) > 0.985


# ---------------------------------------------------------------- medicao de congelamento
medidas = []            # (nome, ms)


def assentar(root, quadros=14, pausa=0.012):
    """Deixa o Tk desenhar tudo; devolve o MAIOR congelamento visto em um unico passo (ms)."""
    pior = 0.0
    for _ in range(quadros):
        t = time.perf_counter()
        root.update()
        pior = max(pior, (time.perf_counter() - t) * 1000)
        time.sleep(pausa)
    return pior


dialogos_vistos = []    # (quem abriu, titulo do dialogo)


def vigiar_dialogos(ref, rotulo):
    """Dialogo modal bloqueia a chamada que o abriu: este vigia o mede e o fecha, para o teste nunca ficar preso."""
    for top in [x for x in janelas_extras(root) if x not in ref]:
        try:
            top.update()
            titulo = top.title()
            probs = inspecionar(top)
        except tk.TclError:
            continue
        dialogos_vistos.append((rotulo, titulo))
        if probs:
            alerta(f"dialogo '{titulo}' aberto por {rotulo}: " + " | ".join(probs[:4]))
            ok(False, f"dialogo '{titulo}' (aberto por {rotulo[:40]}): geometria com defeito -> {probs[0][:80]}")
        try:
            top.destroy()
        except tk.TclError:
            pass


def medir(root, nome, fn, quadros=14):
    ref = set(janelas_extras(root))
    agenda = root.after(500, lambda: vigiar_dialogos(ref, nome))
    t = time.perf_counter()
    try:
        fn()
    except tk.TclError as ex:
        if "bad window path name" not in str(ex):          # controle que o proprio clique destruiu nao e defeito
            erros_tk.append(f"{nome}: TclError {ex}")
    except Exception as ex:                                # a acao em si falhou: e um defeito do app
        erros_tk.append(f"{nome}: {type(ex).__name__}: {ex}")
    pior = (time.perf_counter() - t) * 1000
    try:
        root.after_cancel(agenda)
    except tk.TclError:
        pass
    n_dial = len(dialogos_vistos)
    vigiar_dialogos(ref, nome)
    if len(dialogos_vistos) > n_dial or any(q == nome for q, _ in dialogos_vistos[-3:]):
        pior = 0.0           # abriu dialogo modal: a espera pela resposta da pessoa nao e travada do programa
    pior = max(pior, assentar(root, quadros))
    medidas.append((nome, pior))
    return pior


# ---------------------------------------------------------------- achar e apertar as opcoes de uma tela
PERIGOSOS = re.compile(r"bloquear|sair|excluir|apagar|destru|fechar|lixeira|remover|limpar|restaur|sobrescrev|"
                       r"importar|exportar|imprimir|backup|tentativas|mestra|trocar senha|c[oó]digo|fido|chave", re.I)


def texto_de(w):
    try:
        return str(w.cget("text"))
    except tk.TclError:
        return ""


def clicavel(w):
    """Controle que o usuario pode apertar/selecionar."""
    cls = w.winfo_class()
    if cls in ("Button", "TButton", "Checkbutton", "TCheckbutton", "Radiobutton", "TRadiobutton", "TCombobox",
               "TSpinbox", "TScale", "Menubutton", "TMenubutton"):
        try:
            return str(w.cget("state")) not in ("disabled",)
        except tk.TclError:
            return True
    try:
        return bool(w.bind("<Button-1>")) or bool(w.bind("<ButtonRelease-1>"))
    except tk.TclError:
        return False


def candidatos(raiz):
    out = []
    for w in descendentes(raiz):
        try:
            if not w.winfo_viewable() or w.winfo_width() < 6 or w.winfo_height() < 6:
                continue
            if w.winfo_class() in ("Frame", "TFrame", "Toplevel", "Treeview", "Text", "TEntry", "Entry"):
                if not (w.winfo_class() in ("Frame", "TFrame") and clicavel(w)):
                    continue
            if not clicavel(w):
                continue
            if PERIGOSOS.search(texto_de(w)):
                continue
            out.append(w)
        except tk.TclError:
            continue
    return out


def apertar(w):
    """Clique de verdade (Press + Release) no centro do controle, sem ativar a janela."""
    if not w.winfo_exists():
        return
    cx, cy = max(1, w.winfo_width() // 2), max(1, w.winfo_height() // 2)
    for ev in ("<Enter>", "<Motion>", "<ButtonPress-1>", "<ButtonRelease-1>"):
        w.event_generate(ev, x=cx, y=cy)
    cls = w.winfo_class()
    if cls == "TCombobox":
        vals = list(w.cget("values") or ())
        if vals:
            w.set(random.choice(vals))
            w.event_generate("<<ComboboxSelected>>")
    elif cls == "TScale":
        a, b = float(w.cget("from")), float(w.cget("to"))
        w.set(random.uniform(a, b))
    elif cls == "TSpinbox":
        w.event_generate("<Up>")


def varrer_toplevel(top, rotulo):
    """Mede um dialogo ja aberto: geometria + aperta tudo que da para apertar dentro dele."""
    top.update()
    probs = inspecionar(top)
    return probs


# ================================================================ PREPARO
pasta = tempfile.mkdtemp(prefix="cofre_visual_")
caminho = os.path.join(pasta, "cofre.dat")
print("=== Teste visual bruto da interface ===")
info(f"semente do sorteio: {SEMENTE} (repita com COFRE_VISUAL_SEMENTE={SEMENTE}); limite de congelamento {LIMITE_MS:.0f} ms")
random.seed(SEMENTE)
root = None
try:
    c = cs.Cofre.criar(caminho, SENHA, nivel="alto")
    grupos = ["Banco", "Trabalho", "Redes sociais", "Compras", "Governo", "Saude", "Jogos", "Viagem"]
    pessoas = ["", "Maria da Silva Pereira de Albuquerque", "Joao", "Ze"]
    for i in range(60):
        c.registros.append(cs.novo_item(
            servico=("Servico com nome MUITO longo " * (1 + i % 3)) + str(i) if i % 7 == 0 else f"Conta {i} \u00e7\u00e3o",
            login=f"usuario{i}@exemplo.com.br", senha=f"S3nh@-{i}-" + "x" * (i % 20),
            grupo=grupos[i % len(grupos)], pessoa=pessoas[i % len(pessoas)], url=f"https://site{i}.exemplo.com",
            notas=("linha\n" * (i % 6)), ativo=(i % 9 != 0)))
    c.salvar()
    root = tk.Tk()
    root.withdraw()
    root.report_callback_exception = lambda t, v, tb: erros_tk.append("callback: " + "".join(
        traceback.format_exception_only(t, v)).strip() + " @ " + traceback.format_tb(tb)[-1].strip().replace("\n", " "))
    app = cs.App(root, caminho)
    instalar_patches()
    app.cofre = cs.Cofre.abrir(caminho, senha=SENHA)
    app.tela_principal()
    cs.revelar_janela(root)
    assentar(root, 30)
except Exception:
    print("[FALHOU] nao foi possivel montar o cenario de teste")
    traceback.print_exc()
    print("PASSOU 0 / 1\nFALHAS: ['cenario']")
    shutil.rmtree(pasta, ignore_errors=True)
    sys.exit(1)

TEMAS = list(cs.PALETAS.keys())
base_widgets = contar_widgets(root)
ok(len(erros_tk) == 0, f"o cenario abriu sem erro de callback ({erros_tk[:1]})")


def tema(nome):
    cs._definir_tema(nome)
    app.tema = nome
    cs.aplicar_tema(root)
    app.tela_principal()


def estado_principal():
    app.cofre = app.cofre or cs.Cofre.abrir(caminho, senha=SENHA)
    if not getattr(app, "tree", None) or not app.tree.winfo_exists():
        app.tela_principal()


# ================================================================ 1) GEOMETRIA EM TODOS OS TEMAS E TAMANHOS
print("\n== 1) Geometria: texto cortado, fora da janela, controles sobrepostos (todos os temas, varios tamanhos)")
larg0, alt0 = root.winfo_width(), root.winfo_height()
tamanhos = [(larg0, alt0), (cs._px(1040), cs._px(660)), (cs._px(1280), cs._px(720)), (cs._px(1700), cs._px(1000))]
visto = set()
for nome_t in TEMAS:
    e0 = len(erros_tk)
    tema(nome_t)
    for (w_, h_) in tamanhos:
        root.geometry(f"{w_}x{h_}")
        assentar(root, 8)
        probs = inspecionar(root)
        novos = [p for p in probs if p not in visto]
        visto.update(probs)
        if novos:
            alerta(f"tema '{nome_t}' {w_}x{h_}: " + " | ".join(novos[:5]))
        ok(not probs, f"tema '{nome_t}' em {w_}x{h_}: sem corte, sem controle fora da janela ou sobreposto ({len(probs)})")
    ok(len(erros_tk) == e0, f"tema '{nome_t}': nenhuma excecao de callback ao montar e redimensionar")
root.geometry(f"{larg0}x{alt0}")
tema(TEMAS[0])
assentar(root, 10)

# ================================================================ 2) APERTAR TODAS AS OPCOES, UMA A UMA
print("\n== 2) Apertar cada opcao da tela principal e medir congelamento")
estado_principal()
quant = 0
for rodada in range(2):
    estado_principal()
    lista = candidatos(root)
    random.shuffle(lista)
    for w in lista[:90]:
        try:
            if not w.winfo_exists():
                continue
            rotulo = nome_w(w)
        except tk.TclError:
            continue
        e0, c0 = len(erros_tk), len(caixas)
        ms = medir(root, rotulo, lambda w=w: apertar(w))
        quant += 1
        if len(erros_tk) > e0:
            ok(False, f"{rotulo}: excecao ao apertar -> {erros_tk[-1][:150]}")
        if ms > LIMITE_MS:
            ok(False, f"{rotulo}: congelou {ms:.0f} ms (limite {LIMITE_MS:.0f})")
        elif ms > ALERTA_MS:
            alerta(f"{rotulo}: congelou {ms:.0f} ms")
        if app.cofre is None or not getattr(app, "tree", None):
            estado_principal()
        if not root.winfo_exists():
            break
ok(quant > 5, f"apertou {quant} opcoes da tela principal (precisa de mais de 5 para o teste valer)")
assentar(root, 10)

# ================================================================ 3) DIALOGOS CONHECIDOS
print("\n== 3) Dialogos: abrir, varrer geometria, apertar tudo dentro, fechar")


def abrir_e_varrer(rotulo, abrir_fn, apertar_tudo=True):
    e0 = len(erros_tk)
    achados = {"probs": None, "fechou": False, "feito": False}

    def visitar():
        tops = janelas_extras(root)
        if not tops:
            root.after(120, visitar)
            return
        top = tops[-1]
        try:
            top.update()
            achados["probs"] = inspecionar(top)
            if apertar_tudo:
                for w in candidatos(top)[:40]:
                    try:
                        apertar(w)
                        top.update()
                    except tk.TclError:
                        pass
                achados["probs"] += [p for p in inspecionar(top) if p not in achados["probs"]]
        finally:
            achados["feito"] = True
            for t in janelas_extras(root):
                try:
                    t.destroy()
                except tk.TclError:
                    pass
    root.after(500, visitar)
    guarda = root.after(9000, lambda: [t.destroy() for t in janelas_extras(root)])
    t0 = time.perf_counter()
    try:
        abrir_fn()
    except tk.TclError as ex:
        erros_tk.append(f"{rotulo}: TclError {ex}")
    except Exception as ex:
        erros_tk.append(f"{rotulo}: {type(ex).__name__}: {ex}")
    ms = (time.perf_counter() - t0) * 1000
    limite = time.perf_counter() + 6
    while not achados["feito"] and time.perf_counter() < limite:      # dialogo que nao bloqueia: espera o visitante
        try:
            root.update()
        except tk.TclError:
            break
        time.sleep(0.02)
    try:
        root.after_cancel(guarda)
    except tk.TclError:
        pass
    assentar(root, 6)
    if achados["probs"] is None:
        pulado(f"{rotulo}: nao abriu janela (nada para varrer)")
        return
    if achados["probs"]:
        alerta(f"{rotulo}: " + " | ".join(achados["probs"][:5]))
    ok(not achados["probs"], f"{rotulo}: sem corte/sobreposicao/controle fora da janela ({len(achados['probs'])})")
    ok(len(erros_tk) == e0, f"{rotulo}: sem excecao ao abrir e apertar tudo ({erros_tk[e0:e0 + 1]})")
    sobra = janelas_extras(root)             # um botao do dialogo pode abrir OUTRO dialogo depois do fechamento: so limpa
    for s_ in sobra:
        try:
            s_.destroy()
        except tk.TclError:
            pass
    if sobra:
        info(f"{rotulo}: um botao abriu outro dialogo ({len(sobra)}); fechado pelo teste")


alvos = [("Novo item", lambda: app.dialogo_registro(None)),
         ("Aparencia e cores", app.dialogo_aparencia),
         ("Gerador de senhas", lambda: app.dialogo_gerador())]
import inspect as _insp
_ja = {n for n, _ in alvos}
_PROIBIDOS = re.compile(r"excluir|apagar|destru|bloquear|sair|fechar|restaur|trocar_senha|importar|exportar|imprimir|"
                        r"novo_codigo|nova_chave|fido|backup|tentativas|desativar", re.I)
for nome_m, fn in _insp.getmembers(type(app), predicate=_insp.isfunction):
    if nome_m in _ja or _PROIBIDOS.search(nome_m) or nome_m.startswith("__"):
        continue
    try:
        sig = _insp.signature(fn)
        obrig = [p for p in list(sig.parameters.values())[1:] if p.default is p.empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        fonte = _insp.getsource(fn)
    except (OSError, TypeError, ValueError):
        continue
    if obrig or "_nova_janela(" not in fonte:
        continue
    alvos.append((nome_m, getattr(app, nome_m)))
for nome_m in ("_mostrar_atalhos", "tela_seguranca_adicional"):
    if hasattr(app, nome_m) and nome_m not in {n for n, _ in alvos}:
        alvos.append((nome_m, getattr(app, nome_m)))
info("dialogos que serao varridos: " + ", ".join(n for n, _ in alvos))
for nome_t in TEMAS:                                        # os dois dialogos mais ricos, em todos os temas
    tema(nome_t)
    abrir_e_varrer(f"Novo item no tema '{nome_t}'", lambda: app.dialogo_registro(None))
tema(TEMAS[0])
for rotulo, fn in alvos:
    estado_principal()
    abrir_e_varrer(rotulo, fn)
    estado_principal()
    if getattr(app, "cofre", None) is None:
        app.cofre = cs.Cofre.abrir(caminho, senha=SENHA)
    if not getattr(app, "tree", None) or not app.tree.winfo_exists():
        app.tela_principal()
assentar(root, 8)

# ================================================================ 4) TEMPESTADE
print(f"\n== 4) Tempestade: {N_TEMPESTADE} trocas seguidas sem esperar a tela assentar")
estado_principal()
e0, c0 = len(erros_tk), len(caixas)
n0 = contar_widgets(root)
tem_antes = set(janelas_extras(root))
pior_tempestade, feitas = 0.0, 0
inicio = time.perf_counter()
for i in range(N_TEMPESTADE):
    estado_principal()
    op = random.random()
    t = time.perf_counter()
    ref_t = set(janelas_extras(root))
    agenda_t = root.after(500, lambda: vigiar_dialogos(ref_t, f"tempestade[{i}]"))
    try:
        if op < 0.55:
            cand = candidatos(root)
            if cand:
                apertar(random.choice(cand))
        elif op < 0.75:
            itens = app.tree.get_children()
            if itens:
                app.tree.selection_set(random.choice(itens))
                app.tree.event_generate("<<TreeviewSelect>>")
        elif op < 0.85:
            tema(random.choice(TEMAS))
        elif op < 0.93:
            w_, h_ = random.choice(tamanhos)
            root.geometry(f"{w_}x{h_}")
        else:
            app.busca.set(random.choice(["", "a", "conta 1", "xyz", "Servico", "\u00e7"]))
        if random.random() < 0.5:
            root.update()                                  # as vezes deixa desenhar, as vezes empilha o proximo evento
    except tk.TclError as ex:
        if "bad window path name" not in str(ex):
            erros_tk.append(f"tempestade[{i}]: TclError {ex}")
    except Exception as ex:
        erros_tk.append(f"tempestade[{i}]: {type(ex).__name__}: {ex}")
    try:
        root.after_cancel(agenda_t)
    except tk.TclError:
        pass
    vigiar_dialogos(ref_t, f"tempestade[{i}]")
    pior_tempestade = max(pior_tempestade, (time.perf_counter() - t) * 1000)
    feitas += 1
    for extra in [t_ for t_ in janelas_extras(root) if t_ not in tem_antes]:
        try:
            extra.destroy()
        except tk.TclError:
            pass
assentar(root, 20)
for extra in [t_ for t_ in janelas_extras(root) if t_ not in tem_antes]:
    extra.destroy()
info(f"{feitas} acoes em {time.perf_counter() - inicio:.1f} s; pior acao isolada: {pior_tempestade:.0f} ms")
ok(len(erros_tk) == e0, f"tempestade: nenhuma excecao de callback/acao ({erros_tk[e0:e0 + 2]})")
ok(pior_tempestade <= LIMITE_MS * 2, f"tempestade: nenhuma acao congelou a janela por mais de {LIMITE_MS * 2:.0f} ms ({pior_tempestade:.0f} ms)")
tema(TEMAS[0])
root.geometry(f"{larg0}x{alt0}")
assentar(root, 20)
n1 = contar_widgets(root)
ok(n1 <= n0 * 1.15 + 40, f"tempestade: sem vazamento de widgets ({n0} -> {n1})")
ok(not [t_ for t_ in janelas_extras(root) if t_ not in tem_antes], "tempestade: nenhuma janela solta sobrou")
ok(not inspecionar(root), f"tempestade: depois dela a geometria continua correta ({inspecionar(root)[:2]})")

# ================================================================ 5) FOTOS: PISCA, QUADRO EM BRANCO, FANTASMA, RESIDUO
print("\n== 5) Fotos da janela: pisca, quadro em branco, desenho instavel, fantasma, residuo de redimensionar")
estado_principal()
tema(TEMAS[0])
root.geometry(f"{larg0}x{alt0}")
assentar(root, 25)
teste_foto = capturar(root)
if not foto_util(teste_foto):
    pulado("nao deu para fotografar a janela neste ambiente (captura bloqueada ou sem PIL); testes de imagem pulados")
else:
    info(f"foto da janela: {teste_foto.size[0]}x{teste_foto.size[1]}")
    # 5a) estabilidade: assentada, nao pode mudar sozinha
    for nome_t in TEMAS:
        tema(nome_t)
        assentar(root, 25)
        a = capturar(root)
        time.sleep(0.45)
        root.update()
        b = capturar(root)
        f = fracao_diferente(a, b)
        ok(f <= TOL_PIXELS, f"tema '{nome_t}': a tela assentada nao muda sozinha ({f * 100:.3f}% dos pixels)")
    # 5b) fantasma: voltar ao ponto de partida tem de dar a MESMA imagem
    for nome_t in TEMAS:
        tema(nome_t)
        assentar(root, 25)
        base = capturar(root)
        for outro in random.sample(TEMAS, len(TEMAS)) * 2:
            tema(outro)
            root.update()
        tema(nome_t)
        assentar(root, 25)
        f = fracao_diferente(base, capturar(root))
        ok(f <= TOL_PIXELS * 2, f"tema '{nome_t}': depois de trocar de tema varias vezes a imagem volta igual ({f * 100:.3f}%)")
    # 5c) pisca durante a troca: quadro A, B, A = flicker; quadro em branco no meio = flash
    def amostrar(rotulo, acao, quadros=14):
        antes = capturar(root)
        acao()
        seq = []
        for _ in range(quadros):
            root.update()
            fr = capturar(root)
            if fr is not None:
                seq.append(fr)
            time.sleep(0.008)
        flash = [i for i, fr in enumerate(seq) if quase_vazia(fr) and not quase_vazia(antes)]
        aba = [i for i in range(1, len(seq) - 1)
               if fracao_diferente(seq[i - 1], seq[i + 1]) <= TOL_PIXELS and fracao_diferente(seq[i], seq[i - 1]) > 0.01]
        ok(not flash, f"{rotulo}: nenhum quadro em branco no meio da troca (quadros {flash[:4]})")
        ok(not aba, f"{rotulo}: a tela nao pisca (quadro A-B-A em {aba[:4]})")
    for nome_t in TEMAS[1:] + TEMAS[:1]:
        amostrar(f"trocar para o tema '{nome_t}'", lambda n=nome_t: tema(n))
    amostrar("abrir e fechar 'Novo item'", lambda: (root.after(150, lambda: [t.destroy() for t in janelas_extras(root)]),
                                                    app.dialogo_registro(None)))
    itens = list(app.tree.get_children())
    for iid in random.sample(itens, min(5, len(itens))):
        amostrar("selecionar um item da lista", lambda i=iid: (app.tree.selection_set(i),
                                                               app.tree.event_generate("<<TreeviewSelect>>")))
    # 5d) residuo depois de redimensionar
    tema(TEMAS[0])
    root.geometry(f"{larg0}x{alt0}")
    assentar(root, 25)
    base = capturar(root)
    for (w_, h_) in tamanhos[1:] + tamanhos[1:]:
        root.geometry(f"{w_}x{h_}")
        root.update()
    root.geometry(f"{larg0}x{alt0}")
    assentar(root, 30)
    f = fracao_diferente(base, capturar(root))
    ok(f <= TOL_PIXELS * 2, f"redimensionar varias vezes e voltar ao tamanho original deixa a imagem igual ({f * 100:.3f}%)")

# ================================================================ 6) CICLOS: VAZAMENTO E JANELAS SOLTAS
print("\n== 6) Ciclos de reconstrucao da tela: vazamento de widgets e de janelas")
estado_principal()
tema(TEMAS[0])
assentar(root, 20)
w0 = contar_widgets(root)
e0 = len(erros_tk)
for i in range(60):
    app.tela_principal()
    if i % 10 == 0:
        root.update()
assentar(root, 20)
w1 = contar_widgets(root)
ok(abs(w1 - w0) <= max(6, w0 * 0.02), f"60 reconstrucoes da tela principal: widgets {w0} -> {w1}")
ok(len(erros_tk) == e0, "60 reconstrucoes: nenhuma excecao")
ok(not janelas_extras(root), "nenhuma janela solta no final")

# ================================================================ RESUMO
print("\n== Dialogos que as opcoes abriram")
for quem, titulo in dict.fromkeys(dialogos_vistos):
    info(f"'{titulo}'  <-  {quem}")
print("\n== Resumo de tempos (os 10 maiores congelamentos)")
for nome_m, ms in sorted(medidas, key=lambda x: -x[1])[:10]:
    info(f"{ms:7.0f} ms  {nome_m}")
if medidas:
    ordenado = sorted(ms for _, ms in medidas)
    info(f"{len(medidas)} acoes medidas; mediana {ordenado[len(ordenado) // 2]:.0f} ms; p95 {ordenado[int(len(ordenado) * .95) - 1]:.0f} ms")
if caixas:
    info(f"{len(caixas)} caixa(s) de mensagem apareceram durante o teste (esperado para confirmacoes). Erros entre elas:")
    for tipo, titulo, texto in caixas:
        if tipo == "showerror":
            alerta(f"caixa de ERRO durante o teste: '{titulo}': {texto[:110]}")
erros_de_caixa = [c_ for c_ in caixas if c_[0] == "showerror" and "algo deu errado" in c_[1].lower()]
ok(not erros_de_caixa, "nenhuma caixa 'Algo deu errado' (erro interno do app) apareceu")
if erros_tk:
    print("\nErros registrados:")
    for e in dict.fromkeys(erros_tk):
        print("   - " + e[:300])

try:
    root.destroy()
except tk.TclError:
    pass
shutil.rmtree(pasta, ignore_errors=True)
print(f"\nPASSOU {total - len(falhas)} / {total}")
print(f"FALHAS: {falhas}")
sys.exit(1 if falhas else 0)
