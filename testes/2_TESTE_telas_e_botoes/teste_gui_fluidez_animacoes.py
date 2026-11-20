"""Testes de FLUIDEZ e GLITCHES visuais (Linux/xvfb): janelas que deviam fechar antes de mexer no campo por baixo,
textos com destaque/tamanho dinâmico, redimensionamento em rajada de um diálogo rolável, e arraste do cartão do
passeio guiado. Cada teste aqui é a REGRESSÃO de um glitch relatado de verdade pelo usuário (2026-11-13), não um
teste genérico -- segue o princípio "o teste é a prova documentada do defeito", e cada um fica claro e isolado
(uma causa, um teste) para não virar um "pesticida" que para de pegar nada com o tempo. Descoberto por autodiscovery
em testes/ferramentas_dos_testes/rodar_todos.py (padrão teste_*.py), sem precisar mexer no runner."""
import os, sys, tempfile, traceback
_RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, _RAIZ)
import tkinter as tk
from tkinter import messagebox, filedialog
import cofre_senhas as c

f = []
def ok(cond, nome):
    """Registra uma verificação."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))

W = tempfile.mkdtemp(prefix="gui_fluidez_"); P = os.path.join(W, "g.dat")
SENHA = "cavalo azul come pizza na chuva"
messagebox.showinfo = messagebox.showwarning = lambda *a, **k: None
messagebox.showerror = lambda *a, **k: erros.append(a)
messagebox.askyesno = lambda *a, **k: True
filedialog.askopenfilename = filedialog.asksaveasfilename = filedialog.askdirectory = lambda *a, **k: ""
tk.Misc.wait_window = lambda self, window=None: None     # sem isso, qualquer dialogo.wait_window(d) trava o script
erros, excecoes = [], []

def todos(w):
    for ch in w.winfo_children():
        yield ch; yield from todos(ch)
def tops(root): return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
def fechar_janela(d):
    """Destrói a janela (e tudo dentro dela) de uma vez só, SEM cancelar after() antes -- achado real deste
    arquivo: cancelar manualmente um after() de um widget e DEPOIS destruir esse mesmo widget faz o Tcl tentar
    apagar o mesmo "comando" interno duas vezes (after_cancel já apaga o comando do timer; destroy() tenta apagar
    de novo, pela lista própria de comandos do widget) -- o segundo apagão falha com 'can't delete Tcl command',
    e como esse erro vinha DEPOIS do destroy já ter raspado a árvore de widgets filhos, a janela ficava sem ser
    destruída de verdade (zumbi) sempre que algum widget dela tinha um after() pendente (medidor de força, debounce
    do corpo rolável...). destroy() sozinho (sem cancelar nada antes) já limpa os after() de cada widget filho na
    hora certa, sem esse conflito -- confirmado sem nenhuma exceção em root.report_callback_exception mesmo
    esperando vários segundos depois."""
    try: d.destroy()
    except tk.TclError: pass

c.Cofre.criar(P, SENHA, 5, c.MODO_S, "alto").fechar()
root = tk.Tk(); root.geometry("1366x768+0+0")
root.report_callback_exception = lambda t, v, tb: excecoes.append(
    "".join(traceback.format_exception(t, v, tb)))
app = c.App(root, P)
app.cofre = c.Cofre.abrir(P, senha=SENHA)
app.tela_principal(); root.update()

# ---------------------------------------------------------------------------------------------------------------
# 1) Gerador de senhas: o diálogo PRECISA fechar (destroy) ANTES de inserir a senha no campo de destino.
#    Bug relatado: "quando cliquei no gerador de senhas e escolho a senha a tela ficou meio truncada com glitch" --
#    causa real: o <<Atualizar>> disparado ao inserir a senha recentraliza/redesenha o diálogo de baixo enquanto
#    o gerador (modal, por cima) ainda estava na tela.
# ---------------------------------------------------------------------------------------------------------------
app.dialogo_registro(None); root.update()
d_item = tops(root)[-1]
alvo = next(w for w in todos(d_item) if w.winfo_class() == "TEntry" and str(w.cget("show")) == "•")
app.dialogo_gerador(alvo=alvo, mestre=d_item); root.update()
# o gerador abre como Toplevel(d_item) (filho do diálogo "Novo item", não de root) -- é o jeito certo/padrão do
# Tkinter de empilhar modais; por isso quem acha a janela do gerador é tops(d_item), não tops(root) (que só vê
# Toplevels filhos DIRETOS de root e devolveria o próprio d_item sem erro nenhum -- achado real desta bateria:
# a 1ª versão deste teste usava tops(root) aqui e testava o item sem perceber, "passando" por acidente).
d_ger = tops(d_item)[-1]
ok(d_ger is not d_item, "gerador abriu como uma janela própria, por cima do item")
marca = {"destruido_antes_do_insert": None}
alvo_insert_original = alvo.insert
def insert_rastreado(*a, **k):
    if marca["destruido_antes_do_insert"] is None:
        marca["destruido_antes_do_insert"] = not d_ger.winfo_exists()
    return alvo_insert_original(*a, **k)
alvo.insert = insert_rastreado
btn_usar = next(w for w in todos(d_ger) if w.winfo_class() == "TButton" and str(w.cget("text")).startswith("Usar esta senha"))
btn_usar.invoke(); root.update()
ok(marca["destruido_antes_do_insert"] is True, "gerador: destrói a janela ANTES de inserir a senha no campo (não depois)")
ok(not d_ger.winfo_exists(), "gerador: janela realmente fechada depois de 'Usar esta senha'")
ok(len(alvo.get()) == 20, f"campo recebeu a senha gerada (20 caracteres): {len(alvo.get())}")
fechar_janela(d_item); root.update()

# ---------------------------------------------------------------------------------------------------------------
# 2) Código de recuperação: o bloco destacado em vermelho é escolhido ao acaso (não sempre o último) e o rótulo
#    mostra o tamanho REAL do bloco sorteado -- bug relatado: "terminou com apenas 2 dígitos e não 4 e ele me pede
#    o ultimo bloco com 4 e sai errado" (34 caracteres não é múltiplo de 4: o último bloco sempre tem 2).
# ---------------------------------------------------------------------------------------------------------------
_, codigo = c.nova_chave_acesso()
partes = codigo.split("-")
ok(len(partes[-1]) == 2 and all(len(p) == 4 for p in partes[:-1]), "pré-condição: código real tem último bloco com 2 caracteres")
sorteios = set()
for _ in range(25):                           # 25 tentativas: confere que o sorteio varia (não é sempre o mesmo índice)
    app.mostrar_codigo_recuperacao(codigo); root.update()
    d_cod = tops(root)[-1]
    caixa = next(w for w in todos(d_cod) if isinstance(w, tk.Text))
    faixas = caixa.tag_ranges("destaque")
    ok(len(faixas) == 2, "código: exatamente um trecho marcado como destaque (vermelho)")
    texto_destaque = caixa.get(faixas[0], faixas[1])
    idx = partes.index(texto_destaque) if texto_destaque in partes else -1
    ok(idx >= 0, f"trecho destacado ({texto_destaque!r}) é um dos blocos reais do código")
    sorteios.add(idx)
    rotulo = next(w for w in todos(d_cod) if w.winfo_class() == "TLabel" and "caracteres):" in str(w.cget("text")))
    ok(str(len(texto_destaque)) in str(rotulo.cget("text")), f"rótulo mostra o tamanho certo do bloco sorteado ({len(texto_destaque)})")
    conf = next(w for w in todos(d_cod) if w.winfo_class() == "TEntry")
    conf.insert(0, texto_destaque)
    btn_ok = next(w for w in todos(d_cod) if w.winfo_class() == "TButton" and str(w.cget("text")).startswith("Já anotei"))
    btn_ok.invoke(); root.update()
    ok(not d_cod.winfo_exists(), "código: confirmar com o bloco certo fecha o diálogo")
ok(len(sorteios) >= 3, f"em 25 tentativas, o bloco sorteado variou de posição (posições vistas: {sorted(sorteios)})")
# bloco ERRADO não deve confirmar
app.mostrar_codigo_recuperacao(codigo); root.update()
d_cod = tops(root)[-1]
conf = next(w for w in todos(d_cod) if w.winfo_class() == "TEntry")
conf.insert(0, "ZZZZ")
btn_ok = next(w for w in todos(d_cod) if w.winfo_class() == "TButton" and str(w.cget("text")).startswith("Já anotei"))
btn_ok.invoke(); root.update()
ok(d_cod.winfo_exists(), "código: bloco ERRADO não fecha o diálogo (continua pedindo)")
fechar_janela(d_cod); root.update()

# ---------------------------------------------------------------------------------------------------------------
# 3) _corpo_rolavel: uma rajada de <Configure> (como a reconstrução do painel de força a cada tecla do teclado
#    virtual) deve gerar POUCAS reconfigurações reais do Canvas, não uma por evento -- bug relatado: "ao abrir o
#    teclado virtual e clicar nele... o aplicativo ao fundo fica dando erros e problemas gráficos de animação
#    glitch". Espiona Canvas.configure enquanto dispara manualmente vários <Configure> em sequência rápida no
#    frame interno do corpo rolável do diálogo "Novo item" (mesmo mecanismo usado por todo diálogo rolável).
# ---------------------------------------------------------------------------------------------------------------
app.dialogo_registro(None); root.update()
d_item = tops(root)[-1]
telas = [w for w in todos(d_item) if w.winfo_class() == "Canvas"]
ok(len(telas) >= 1, "diálogo 'Novo item' tem o Canvas do corpo rolável")
tela = telas[0]
fr_interno = next(iter(tela.winfo_children()), None)
ok(fr_interno is not None, "Canvas do corpo rolável tem o frame de conteúdo dentro")
contagem = {"n": 0}
configure_original = tk.Canvas.configure
def configure_espiao(self, *a, **k):
    if self is tela and ("width" in k or "height" in k):
        contagem["n"] += 1
    return configure_original(self, *a, **k)
tk.Canvas.configure = configure_espiao
try:
    contagem["n"] = 0
    for _ in range(12):                        # simula 12 "teclas" em rajada (bem mais rápido que o debounce de 30 ms)
        fr_interno.event_generate("<Configure>")
    root.update()
    ok(contagem["n"] <= 2, f"12 eventos <Configure> em rajada viraram só {contagem['n']} reconfiguração(ões) do Canvas (debounce)")
finally:
    tk.Canvas.configure = configure_original
fechar_janela(d_item); root.update()

# ---------------------------------------------------------------------------------------------------------------
# 4) Passeio guiado: o cartão pode ser arrastado pelo título (pedido do usuário: "o guia que da passo a passo não
#    permite ser movido para outro canto da tela").
# ---------------------------------------------------------------------------------------------------------------
app.passeio_principal(); root.update()
tour = app._tour
ok(tour is not None, "passeio guiado iniciou")
cartao = tour.cartao
ok(cartao is not None and cartao.winfo_exists(), "passeio: cartão de texto existe")
x0, y0 = cartao.winfo_x(), cartao.winfo_y()
classe_evento = type("Ev", (), {})
ev1 = classe_evento(); ev1.x_root, ev1.y_root = x0 + 10, y0 + 10
tour._iniciar_arraste(ev1)
ev2 = classe_evento(); ev2.x_root, ev2.y_root = x0 + 160, y0 + 90
tour._arrastar(ev2)
root.update()
x1, y1 = cartao.winfo_x(), cartao.winfo_y()
ok((x1, y1) != (x0, y0), f"passeio: cartão se moveu ao arrastar pelo título ({(x0, y0)} -> {(x1, y1)})")
ok(abs((x1 - x0) - 150) <= 2 and abs((y1 - y0) - 80) <= 2, "passeio: deslocamento do cartão bate com o movimento do mouse")
for _ in range(len(tour.passos) + 2):
    if app._tour is None:
        break
    tour._ir(tour.i + 1)
    root.update()
ok(app._tour is None, "passeio guiado termina percorrendo todos os passos (sem travar depois do arrasto)")

# ---------------------------------------------------------------------------------------------------------------
# 5) Varredura geral: nenhuma Toplevel nem after() sobrando depois de abrir/fechar os diálogos mais usados.
# ---------------------------------------------------------------------------------------------------------------
def contagem_janelas(): return len(list(todos(root))), len(tops(root))
base_w, base_t = contagem_janelas()
for _ in range(5):
    app.dialogo_registro(None); root.update()
    fechar_janela(tops(root)[-1]); root.update()
    app.dialogo_gerador(); root.update()
    fechar_janela(tops(root)[-1]); root.update()
w1, t1 = contagem_janelas()
ok(t1 == base_t, f"sem Toplevel sobrando depois dos ciclos (eram {base_t}, ficaram {t1})")
ok(abs(w1 - base_w) <= 5, f"sem widgets acumulando depois dos ciclos ({base_w} -> {w1})")

ok(not erros, f"nenhum erro exibido ao usuário durante a bateria {erros[:2]}")
ok(not excecoes, f"nenhuma exceção não tratada {excecoes[:2]}")
print("PASSOU" if all(f) else "FALHOU", sum(f), "/", len(f))
fechar_janela(root)
sys.exit(0 if all(f) else 1)
