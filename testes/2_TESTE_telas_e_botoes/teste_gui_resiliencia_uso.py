# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Interface sob uso real e abuso: cliques freneticos, texto absurdo, perda de foco, ciclos de abrir/fechar,
janelas modais, tela de integridade e aviso do pendrive. Roda no Linux com xvfb-run e no Windows.
 A) Salvar clicado 15x seguidas  -> UM só item (nunca duplicado);
 B) campos com texto gigante/unicode/RTL/controle -> sem erro, salva e reabre;
 C) perda de foco: aviso rápido (<1,5 s) NÃO cobre; prolongado cobre; clicar restaura; o que foi digitado fica;
 D) 30 ciclos de abrir/bloquear -> sem crescer janelas, widgets, descritores de arquivo (nem objetos GDI no Windows);
 E) janelas de senha: Cancelar fecha e some; bloquear derruba qualquer janela aberta;
 F) tela 'Verificar integridade': mostra o SHA-256 (64 hex em 8 grupos) ou o aviso de 'não foi possível';
 G) aviso 'Salvando… não retire o pendrive' só em unidade removível (e nunca derruba a gravação)."""
import os, re, sys, tempfile, time, shutil
_RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, _RAIZ); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "6_TESTE_ferramentas_dos_testes"))
import _resultado; _resultado.registrar(__file__)          # grava resultados/resultado_gui_resiliencia_uso.txt
import tkinter as tk, cofre_senhas as c
from tkinter import messagebox
f = []
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome, flush=True); f.append(bool(cond))
erros = []
messagebox.showinfo = lambda *a, **k: None; messagebox.showerror = lambda *a, **k: erros.append(a)
messagebox.askyesno = lambda *a, **k: False
tk.Misc.wait_window = lambda self, window=None: None      # diálogos modais não travam o teste
W = _resultado.pasta_temporaria("cofre_gui_"); P = os.path.join(W, "r.dat"); S = "cavalo azul come pizza na chuva"
_nivel_alto = c.NIVEIS["alto"]
try:
    c.NIVEIS["alto"] = (1, 8192)  # este teste mede ciclos de UI/recursos, não o custo do Argon2
    c.Cofre.criar(P, S, 50, c.MODO_OU, "alto").fechar()
finally:
    c.NIVEIS["alto"] = _nivel_alto
root = tk.Tk(); root.geometry("1366x768+0+0"); app = c.App(root, P)
app.cofre = c.Cofre.abrir(P, senha=S); app.tela_principal(); root.update()
# O teste NÃO pode depender de quem tem o foco no PC de quem roda (o bloqueio por falta de foco, a capa de "conteúdo
# oculto" e o vigia de "o PC dormiu" são testados à parte): foco fixo e relógio do vigia renovado a cada passo.
sem_foco = [False]; app._app_sem_foco = lambda: sem_foco[0]
def renova():
    app._ultimo_tique = time.time(); app._sem_foco_desde = None
    app._atividade()


def todos(w):
    for ch in w.winfo_children():
        yield ch; yield from todos(ch)
def achar(d, txt, cls="TButton"):
    return next((w for w in todos(d) if w.winfo_class() == cls and str(w.cget("text")).startswith(txt)), None)
def janelas():
    return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
def novo():
    """Abre o formulário 'Novo item'. Se o cofre bloqueou sozinho (PC de teste sem foco / lento) reabre e tenta de novo;
    se mesmo assim não abrir, diz o estado exato (para a causa aparecer no resultado, não só um StopIteration)."""
    for _ in range(5):
        renova()
        if app.cofre is None:
            app.cofre = c.Cofre.abrir(P, senha=S); app.tela_principal(); renova(); root.update()
        app.dialogo_registro(None); root.update(); root.update(); root.update()
        achou = next((w for w in janelas() if w.title() == "Novo item"), None)
        if achou is not None:
            return achou
        time.sleep(0.3)
    raise AssertionError("o formulário 'Novo item' não abriu: cofre=%s, janelas=%r, erros=%r, erro_espias=%r, espias=%r" % (
        "fechado" if app.cofre is None else "aberto", [w.title() for w in janelas()], erros,
        app._espias_erro, app._espias_res))
def ents(d):
    return [w for w in todos(d) if w.winfo_class() == "TEntry" and w.winfo_ismapped()]
def textos(w):
    """Todo texto visível de uma janela (labels, botões e caixas de texto)."""
    out = []
    for x in todos(w):
        try:
            if x.winfo_class() in ("TLabel", "Label", "TButton"):
                out.append(str(x.cget("text")))
            elif x.winfo_class() == "Text":
                out.append(x.get("1.0", "end"))
        except tk.TclError:
            pass
    return "\n".join(out)

print("== A) Salvar clicado 15x seguidas")
d = novo(); e = ents(d); e[0].insert(0, "Banco Frenético"); e[1].insert(0, "u@x.com"); e[2].insert(0, "Senha-Frenetica-1!")
botao = achar(d, "Salvar")
for _ in range(15):
    try:
        botao.invoke()
    except tk.TclError:
        pass                                             # a janela já fechou: o botão não existe mais (esperado)
    root.update()
n = sum(1 for r in app.cofre.registros if r["servico"] == "Banco Frenético")
ok(n == 1, f"15 cliques em Salvar geraram {n} item (esperado 1)")
ok(not erros, "sem mensagem de erro durante os cliques")
ok(not any(w.title() == "Novo item" for w in janelas()), "a janela do formulário fechou")

print("== B) texto gigante, unicode, RTL e caracteres de controle")
class FonteContadora:
    def __init__(self):
        self.chamadas = 0
    def measure(self, texto):
        self.chamadas += 1
        return len(texto)

fonte = FonteContadora()
cortado = c._cortar("x" * 2000, fonte, 80)
ok(cortado == "x" * 79 + "…" and fonte.chamadas <= 14,
   f"texto longo truncado com busca limitada ({fonte.chamadas} medições)")
estranhos = ["x" * 5000, "🔐🗝️" * 500, "שלום עולם مرحبا " * 50, "linha1\nlinha2\ttab", "‮evil‬", "nulo\x00no meio", "ç~´`^ ÀÉÎÕÜ" * 100]
for i, texto in enumerate(estranhos):
    renova()
    if app.cofre is None:
        app.cofre = c.Cofre.abrir(P, senha=S); app.tela_principal(); renova(); root.update()
    try:
        d = novo(); e = ents(d); e[0].insert(0, f"Fuzz {i}"); e[1].insert(0, texto[:2000]); e[2].insert(0, texto)
        achar(d, "Salvar").invoke(); root.update()
    except Exception as ex:
        ok(False, f"texto estranho #{i} derrubou a interface: {type(ex).__name__}: {ex}")
ok(sum(1 for r in app.cofre.registros if r["servico"].startswith("Fuzz ")) == len(estranhos), "todos os itens com texto estranho foram salvos")
ok(not erros, "nenhuma mensagem de erro com texto estranho")
app.cofre.salvar(); app.cofre.fechar()
r = c.Cofre.abrir(P, senha=S); ok(len(r.registros) >= 1 + len(estranhos), f"reabriu com {len(r.registros)} itens"); r.fechar()
app.cofre = c.Cofre.abrir(P, senha=S); app.tela_principal(); root.update()

print("== C) perda de foco")
if app.cofre is None:
    app.cofre = c.Cofre.abrir(P, senha=S); app.tela_principal(); root.update()
app.OCULTAR_APOS_MS = 200
sem_foco[0] = False; renova()
d = novo(); e = ents(d); e[0].insert(0, "Digitado e mantido")
app._mostrar_conteudo()
if app._timer_ocultar is not None:
    root.after_cancel(app._timer_ocultar)
    app._timer_ocultar = None
sem_foco[0] = True
app._agendar_ocultar(); t1 = app._timer_ocultar; app._agendar_ocultar()
ok(app._timer_ocultar == t1, "pedidos repetidos de ocultar não empilham temporizadores")
sem_foco[0] = False
t0 = time.time()
while time.time() - t0 < 0.5: root.update(); time.sleep(0.02)
ok(not app._ocultadores, "foco roubado só por instantes (voltou antes): NÃO cobriu a tela")
if app._timer_ocultar is not None:
    root.after_cancel(app._timer_ocultar)
    app._timer_ocultar = None
sem_foco[0] = True; app._agendar_ocultar()
t0 = time.time()
while time.time() - t0 < 0.6: root.update(); time.sleep(0.02)
ok(len(app._ocultadores) >= 1, "sem foco por mais que o prazo: cobriu o conteúdo")
sem_foco[0] = False
if app._timer_ocultar is not None:
    root.after_cancel(app._timer_ocultar)
    app._timer_ocultar = None
app._mostrar_conteudo(); root.update()
ok(not app._ocultadores, "clicar na capa tira o 'conteúdo oculto'")
ok(ents(d)[0].get() == "Digitado e mantido", "o que o usuário digitou continua lá depois de cobrir e descobrir")
d.destroy(); root.update()

print("== D) 30 ciclos de abrir/bloquear (vazamento de recursos)")
def fds():
    return _resultado.handles_processo()
def gdi():
    return _resultado.objetos_gdi()
def ciclo():
    app.bloquear(); root.update()
    app.cofre = c.Cofre.abrir(P, senha=S); app.tela_principal(); renova(); root.update()
for _ in range(3): ciclo()                               # aquecimento
base = (len(list(todos(root))), fds(), gdi(), len(janelas()))
for i in range(30):
    ciclo()
    if (i + 1) % 5 == 0:
        print(f"  ciclo {i + 1}/30", flush=True)
fim = (len(list(todos(root))), fds(), gdi(), len(janelas()))
ok(fim[0] <= base[0] + 5, f"widgets não crescem: {base[0]} -> {fim[0]}")
ok(base[1] is None or fim[1] <= base[1] + 3, f"descritores de arquivo não crescem: {base[1]} -> {fim[1]}")
ok(base[2] is None or fim[2] <= base[2] + 10, f"objetos GDI/USER não crescem: {base[2]} -> {fim[2]}")
ok(fim[3] <= base[3], f"janelas abertas não crescem: {base[3]} -> {fim[3]}")

print("== E) janelas de senha")
antes = len(janelas())
app._pedir_senha("Digite", "texto", medidor=True); root.update()
dj = [w for w in janelas()][-1]
campo = next((w for w in todos(dj) if w.winfo_class() in ("TEntry", "Entry")), None)
ok(campo is not None, "janela de senha tem campo")
if campo is not None:
    campo.insert(0, "segredo-que-nao-pode-sobrar")
    ok(campo.cget("show") not in ("", None), "o campo esconde o que é digitado")
achar(dj, "Cancelar").invoke(); root.update()
ok(len(janelas()) == antes, "Cancelar fecha e remove a janela de senha")
app._pedir_senha("Outra", "texto"); app._pedir_senha("Mais outra", "texto"); root.update()
ok(len(janelas()) == antes + 2, "duas janelas de senha abertas")
app.bloquear(); root.update()
ok(not janelas(), "bloquear derruba toda janela aberta (nada com segredo fica solto)")
ok(app.cofre is None, "bloquear apagou as chaves da memória")

print("== F) Verificar integridade")
app.cofre = c.Cofre.abrir(P, senha=S); app.tela_principal(); root.update()
H = "0123456789abcdef" * 4
app._hash_proprio_programa = lambda: H
app.verificar_integridade(); root.update()
dj = [w for w in janelas() if w.title() == "Verificar integridade do programa"][-1]
t = textos(dj)
ok(re.search(r"(?:[0-9a-f]{8}\s+){7}[0-9a-f]{8}", t) is not None, "mostra 64 hex em 8 grupos de 8")
ok("MANUAL" in t or "manual" in t, "avisa que a conferência é manual")
dj.destroy(); root.update()
app._hash_proprio_programa = lambda: None
app.verificar_integridade(); root.update()
dj = [w for w in janelas() if w.title() == "Verificar integridade do programa"][-1]
ok("Não foi possível calcular" in textos(dj), "sem hash: mostra aviso claro, sem quebrar")
dj.destroy(); root.update()

print("== G) aviso de salvamento em pendrive")
vistos = []
app._com_espera = lambda fn, texto="", atraso=0.0: (vistos.append(texto), fn())[1]
orig = c.unidade_removivel
c.unidade_removivel = lambda p: True
app._executar_salvamento(lambda: 1)
ok(vistos[-1] == "Salvando… não retire o pendrive", f"unidade removível: '{vistos[-1]}'")
c.unidade_removivel = lambda p: False
app._executar_salvamento(lambda: 1)
ok(vistos[-1] == "Salvando…", f"disco comum: '{vistos[-1]}'")
def quebra(p): raise OSError("api falhou")
c.unidade_removivel = quebra
ok(app._executar_salvamento(lambda: 7) == 7 and vistos[-1] == "Salvando… não retire o pendrive",
   "se a detecção falhar, grava com o aviso preventivo")
c.unidade_removivel = orig
ok(app._salvando is False, "indicador 'salvando' volta a falso")

app._cancelar_todos_after()
root.destroy()
print("\nTODOS OK" if all(f) else f"\nFALHAS: {f.count(False)} de {len(f)}")
sys.exit(0 if all(f) else 1)
