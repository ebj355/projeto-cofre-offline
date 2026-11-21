# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Bateria de interface: cada tela é montada, cada botão do cabeçalho e cada item do menu '⋯' é acionado; confere que
nenhum evento levanta exceção, que não sobram janelas, que os textos fixos da tela são CURTOS (o resto vai no '?'),
que os 3 modos de abertura (só senha / senha+chave / senha ou chave) mostram os campos certos e que o
desempenho fica dentro do limite. Roda no Linux com xvfb-run."""
import os, sys, tempfile, time
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
_RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, _RAIZ)
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import cofre_senhas as c
f = []
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
W = tempfile.mkdtemp(prefix="cofre_gui_"); P = os.path.join(W, "t.dat")
SENHA = "cavalo azul come pizza na chuva"
dialogos = []
messagebox.showinfo = lambda *a, **k: dialogos.append(("info", a[0] if a else ""))
messagebox.showwarning = lambda *a, **k: dialogos.append(("aviso", a[0] if a else ""))
messagebox.showerror = lambda *a, **k: dialogos.append(("erro", a[0] if a else ""))
messagebox.askyesno = lambda *a, **k: False
messagebox.askokcancel = lambda *a, **k: False
filedialog.askopenfilename = lambda *a, **k: ""
filedialog.asksaveasfilename = lambda *a, **k: ""
filedialog.askdirectory = lambda *a, **k: ""
excecoes = []
tk.Misc.wait_window = lambda self, window=None: None      # diálogos modais não esperam o usuário no teste
v = c.Cofre.criar(P, SENHA, 5, c.MODO_OU, "alto")
for i in range(3):
    v.registros.append(c.novo_item(servico=f"Servico {i}", login=f"u{i}@x.com", senha="Seg-123!xyz", grupo="Banco" if i else ""))
v.salvar(); v.fechar()
root = tk.Tk(); root.geometry("1366x768+0+0")
root.report_callback_exception = lambda t, v_, tb: excecoes.append(repr(v_))
app = c.App(root, P)
app._pedir_senha = lambda *a, **k: None                # diálogos modais (esperam o usuário) são trocados por "cancelar"
app._confirmar_senha_atual = lambda *a, **k: False
root.update()

def todos(w, out=None):
    out = [] if out is None else out
    for ch in w.winfo_children():
        out.append(ch); todos(ch, out)
    return out
def textos(w, so_visiveis=False):
    r = []
    for ch in todos(w):
        if so_visiveis and not ch.winfo_ismapped(): continue
        if ch.winfo_class() in ("Label", "TLabel", "Message", "TCheckbutton", "TRadiobutton", "TButton"):
            try: r.append(str(ch.cget("text")))
            except tk.TclError: pass
    return r
def tops():
    return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
def limpar():
    for w in tops():
        try: w.destroy()
        except tk.TclError: pass
    root.update()
LIMITE_TEXTO = 110
def curtos(tela, w):
    longos = [t for t in textos(w) if len(t) > LIMITE_TEXTO]
    ok(not longos, f"{tela}: nenhum texto fixo maior que {LIMITE_TEXTO} caracteres" + (f"  → {[t[:60] for t in longos][:3]}" if longos else ""))

# ---------- tela de criação ----------
os.remove(P)
t0 = time.perf_counter(); app.mostrar_inicio(); root.update(); dt = time.perf_counter() - t0
ok(dt < 3.0, f"tela de criação monta em {dt:.2f}s")
curtos("criação", app.frame)
tx = " | ".join(textos(app.frame))
ok("Só senha mestra" in tx and "Senha E chave de acesso" in tx and "Senha OU chave de acesso" in tx, "criação oferece os 3 modos")
ok("1. Defina a senha mestra" in tx and "2. Escolha como abrir" in tx and
   "3. Proteção contra tentativas" in tx, "criação organiza as escolhas em etapas")
ok("Só a senha abre o cofre." in tx and "Exige senha e chave juntas" in tx and
   "Qualquer uma abre; oferece menos proteção." in tx, "cada modo explica claramente o que será exigido")
proximos = [w for w in todos(app.frame) if w.winfo_class() == "TLabel" and str(w.cget("text")).startswith("PRÓXIMO PASSO")]
ok(len(proximos) == 1 and "chave de acesso" in str(proximos[0].cget("text")),
   "o próximo passo avisa que a chave será exibida uma única vez")
radios = {str(w.cget("text")): w for w in todos(app.frame) if w.winfo_class() == "TRadiobutton"}
cartao_recomendado = radios["Senha E chave de acesso  (recomendado)"].master.master
ok(cartao_recomendado.cget("highlightbackground") == c.CORES["prim"],
   "o modo recomendado começa destacado na identidade visual do cofre")
radios["Só senha mestra"].invoke(); root.update()
ok("o cofre abrirá com a senha mestra" in str(proximos[0].cget("text")),
   "o resumo do próximo passo acompanha o modo escolhido")
ok(cartao_recomendado.cget("highlightbackground") != c.CORES["prim"],
   "o destaque acompanha a opção selecionada")
descricao_ou = next(w for w in todos(app.frame) if w.winfo_class() == "TLabel" and
                    str(w.cget("text")).startswith("Qualquer uma abre; oferece menos proteção."))
descricao_ou.event_generate("<Button-1>"); root.update()
ok("ela também poderá abrir o cofre sozinha" in str(proximos[0].cget("text")),
   "clicar na descrição seleciona o modo correspondente")
cartao_ou = radios["Senha OU chave de acesso"].master.master
ok(cartao_ou.cget("highlightbackground") == c.CORES["prim"],
   "o cartão clicado recebe o destaque")
radios["Senha E chave de acesso  (recomendado)"].invoke(); root.update()
fido = next(w for w in todos(app.frame) if w.winfo_class() == "TCheckbutton" and
            str(w.cget("text")) == "Exigir também a chave FIDO")
fido.invoke(); root.update()
ok("cadastro da chave física será solicitado" in str(proximos[0].cget("text")),
   "o resumo inclui o cadastro FIDO quando ativado")
fido.invoke(); root.update()
ok("Exigir também a chave FIDO" in tx, "criação oferece a chave FIDO")
helps = [w for w in todos(app.frame) if w.winfo_class() == "Label" and str(w.cget("text")) == "?"]
ok(len(helps) >= 3, f"criação tem botões '?' ({len(helps)})")
n0 = len(tops()); helps[0].event_generate("<Button-1>"); root.update()
ok(len(tops()) == n0 + 1, "clicar no '?' abre o pop-up com o texto completo")
pop = tops()[-1]; root.update()
ok(pop.winfo_viewable(), "o pop-up fica visível depois de montado")
ok(any(len(t) > 120 for t in textos(pop)), "o pop-up traz o texto longo")
pop.event_generate("<Escape>"); root.update(); limpar()

# ---------- tela de desbloqueio nos 3 modos ----------
for modo, nome in ((c.MODO_S, "só senha"), (c.MODO_E, "senha E chave"), (c.MODO_OU, "senha OU chave")):
    p2 = os.path.join(W, f"m{modo}.dat")
    x = c.Cofre.criar(p2, SENHA, 4, modo, "alto"); x.registros.append(c.novo_item(servico="Z", senha="Seg-123!xyz")); x.salvar(); x.fechar()
    app.caminho = p2; app.mostrar_inicio(); root.update()
    t = " | ".join(textos(app.frame, True)).lower()
    curtos(f"desbloqueio ({nome})", app.frame)
    ok("tentativas restantes: 4" in t, f"desbloqueio ({nome}): mostra tentativas restantes")
    tem_chave = "chave de acesso" in t
    if modo == c.MODO_S:
        ok(not tem_chave and "senha mestra" in t, "só senha: NÃO pede chave de acesso")
    elif modo == c.MODO_E:
        ok(tem_chave and "senha mestra" in t, "senha E chave: pede os dois campos")
    else:
        ok("senha mestra" in t and "chave de acesso" in t, "senha OU chave: oferece escolher")
    ents = [w for w in todos(app.frame) if w.winfo_class() == "TEntry" and w.winfo_ismapped()]
    botao = next(w for w in todos(app.frame) if w.winfo_class() == "TButton" and str(w.cget("text")).startswith("Desbloquear"))
    if modo == c.MODO_S:
        ents[0].insert(0, SENHA); botao.invoke()
        fim = time.time() + 8
        while time.time() < fim and app.cofre is None: root.update(); time.sleep(0.02)
        ok(app.cofre is not None and app.cofre.modo == c.MODO_S, "só senha: abre com a senha")
        root.update()
        menu = [i for i in app._menu_mais.itens if i]
        ok(all("Nova chave" not in i[0] for i in menu), "só senha: menu não oferece 'Nova chave de acesso'")
        app.bloquear(); root.update()
    limpar()

# ---------- tela principal: botões e menu ----------
app.caminho = P
v = c.Cofre.criar(P, SENHA, 5, c.MODO_OU, "alto")
for i in range(3):
    v.registros.append(c.novo_item(servico=f"Servico {i}", login=f"u{i}@x.com", senha="Seg-123!xyz", grupo="Banco" if i else ""))
v.salvar(); v.fechar()
app.cofre = c.Cofre.abrir(P, senha=SENHA); app.tela_principal(); root.update()
curtos("tela principal", app.frame)
root.after(1, lambda: None)
botoes = [w for w in todos(app.frame) if w.winfo_class() in ("TButton",) and w.winfo_ismapped()]
ok(len(botoes) >= 3, f"tela principal tem {len(botoes)} botões")
acionados = 0
for b in botoes:
    rotulo = str(b.cget("text"))
    if rotulo in ("", "Sair") or "Bloquear" in rotulo: continue
    try:
        n = len(excecoes); b.invoke(); root.update()
        ok(len(excecoes) == n, f"botão '{rotulo or '(ícone)'}' aciona sem erro")
        acionados += 1
    except tk.TclError as ex:
        ok(False, f"botão '{rotulo}' falhou: {ex}")
    for w in tops():
        if w.winfo_class() == "Toplevel" and str(w.wm_overrideredirect()) in ("1", "True"): continue
    limpar()
ok(acionados >= 2, f"{acionados} botões acionados")
app._menu_mais.itens  # menu ⋯ -- itens são 3-tuplas; None é separador e uma string solta é título de seção (ambos pulados)
for it in [i for i in app._menu_mais.itens if isinstance(i, tuple)]:
    rot, ic, func = it
    if "Bloqueio automático" in rot or "Backup" in rot or "Importar" in rot or "modelo" in rot.lower() or "Chaves FIDO" in rot or "Gerador" in rot or "Histórico" in rot or "Diagnóstico" in rot or "Verificar" in rot or "Trocar senha" in rot or "Nova chave" in rot:
        n = len(excecoes)
        try:
            func(); root.update()
        except tk.TclError as ex:
            excecoes.append(repr(ex))
        t_ = tops()
        curtos(f"janela '{rot}'", t_[-1]) if t_ else None
        ok(len(excecoes) == n, f"menu '{rot}' abre sem erro")
        if t_:
            ok(all(w.winfo_viewable() for w in t_ if str(w.wm_overrideredirect()) not in ("1", "True")), f"menu '{rot}': janela aparece pronta (visível)")
        limpar()

# ---------- novo item / editar / excluir ----------
n = len(excecoes); app.dialogo_registro(None); root.update()
d = next((w for w in tops() if w.title() == "Novo item"), None)
ok(d is not None and d.winfo_viewable(), "Novo item abre visível")
if d: curtos("Novo item", d)
limpar()
ok(len(excecoes) == n, "Novo item sem erro")

# ---------- estabilidade: redesenho sem mudança não destrói nada ----------
app.atualizar_lista(); root.update()
ids_lateral = [str(w) for w in app.lateral.winfo_children()]
itens_lista = set(app.tree.canvas.find_all())
app.atualizar_lista(manter_lateral=False); root.update()
ok([str(w) for w in app.lateral.winfo_children()] == ids_lateral, "barra lateral idêntica não é recriada (sem piscar)")
ok(set(app.tree.canvas.find_all()) == itens_lista, "lista idêntica não é redesenhada (sem piscar)")
sel_antes = app.tree.selection() if hasattr(app.tree, "selection") else None
app._agendar_ocultar(); t1 = app._timer_ocultar; app._agendar_ocultar()
ok(t1 is not None and app._timer_ocultar == t1, "foco perdido agenda UMA checagem (não empilha timers)")
ok(not app._ocultadores, "cobertura 'conteúdo oculto' não aparece na hora (espera 1,5 s)")

# ---------- desempenho com muitos itens ----------
app.cofre = c.Cofre.abrir(P, senha=SENHA)
for i in range(1500):
    app.cofre.registros.append(c.novo_item(servico=f"Conta {i:04d}", login=f"user{i}@exemplo.com", senha="Seg-123!xyz", grupo=("Banco", "Compras", "Redes")[i % 3]))
t0 = time.perf_counter(); app.tela_principal(); root.update(); dt = time.perf_counter() - t0
ok(dt < 6.0, f"tela principal com 1500 itens monta em {dt:.2f}s")
t0 = time.perf_counter()
for termo in ("c", "co", "con", "conta 01", "conta 012"):
    app.busca.set(termo); app.atualizar_lista(manter_lateral=True); root.update()
dt = (time.perf_counter() - t0) / 5
ok(dt < 0.6, f"busca com 1500 itens: {dt*1000:.0f} ms por tecla")
app.busca.set(""); app.atualizar_lista(); root.update()
t0 = time.perf_counter()
for _ in range(20):
    app.atualizar_lista(); root.update()
dt = (time.perf_counter() - t0) / 20
ok(dt < 0.5, f"atualizar sem mudança: {dt*1000:.0f} ms")
t0 = time.perf_counter()
for g in ("Banco", "Compras", "Redes", "Banco"):
    app.filtro_grupo.set(g); app.atualizar_lista(); root.update()
dt = (time.perf_counter() - t0) / 4
ok(dt < 1.0, f"trocar de grupo com 1500 itens: {dt*1000:.0f} ms")
ok(not excecoes, f"nenhuma exceção durante toda a bateria {excecoes[:3]}")
ok(len(tops()) == 0, f"nenhuma janela sobrando ({len(tops())})")
print("PASSOU" if all(f) else "FALHOU", sum(f), "/", len(f))
root.destroy(); sys.exit(0 if all(f) else 1)
