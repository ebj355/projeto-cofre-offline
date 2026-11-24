# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Apoio dos testes de interface novos (temas, Novo item, computadores autorizados, telas fixas).

NAO e um teste (o nome comeca com "_", entao o executor nao o roda sozinho). Fica junto dos testes que o usam.

O que faz:
  * acha a raiz do projeto (onde esta o cofre_senhas.py) e isola TUDO do usuario: preferencias de aparencia,
    segredo local do computador e cofres de teste vao para uma pasta temporaria que e apagada ao terminar;
  * da o mesmo formato de saida dos outros testes ("  [OK]   ...", "PASSOU n / m", "FALHAS: k");
  * troca as caixas de mensagem por espioes (nada abre janela de verdade nem trava esperando clique);
  * oferece funcoes para achar botoes/campos, varrer cores de todos os widgets e abrir/fechar dialogos sem travar.
"""
import atexit
import faulthandler
import os
import shutil
import sys
import tempfile
import time

CODIGO_PULADO = 9               # mesmo codigo que o executor entende como [PULADO]
SENHA = "Senha-Mestra-De-Teste-14+"          # >= 14 caracteres (MIN_SENHA)


def _achar_raiz():
    """Sobe pelas pastas ate achar o cofre_senhas.py."""
    p = os.path.abspath(os.path.dirname(__file__))
    for _ in range(8):
        if os.path.exists(os.path.join(p, "cofre_senhas.py")):
            return p
        p = os.path.dirname(p)
    print("[PULADO] nao encontrei cofre_senhas.py acima desta pasta")
    sys.exit(CODIGO_PULADO)


RAIZ = _achar_raiz()
_TMP = []


def preparar(prefixo="cofre_gui_novo_", limite_segundos=900):
    """Cria a pasta temporaria, isola preferencias/segredos do usuario e arma um vigia contra travamento."""
    tmp = tempfile.mkdtemp(prefix=prefixo)
    _TMP.append(tmp)
    atexit.register(shutil.rmtree, tmp, True)
    for var in ("LOCALAPPDATA", "XDG_CONFIG_HOME", "APPDATA"):
        os.environ[var] = os.path.join(tmp, "dados_" + var.lower())
    os.environ["HOME"] = os.environ["USERPROFILE"] = os.path.join(tmp, "casa")
    os.makedirs(os.environ["HOME"], exist_ok=True)
    os.environ.setdefault("COFRE_SEM_VERIFICACAO_INICIAL", "1")
    if os.environ.get("COFRE_GUI_TESTS_FOREGROUND") != "1":
        os.environ.setdefault("COFRE_GUI_TESTS_BACKGROUND", "1")
    if RAIZ not in sys.path:
        sys.path.insert(0, RAIZ)
    # Se algo travar (por exemplo um dialogo modal que ninguem fecha), morre COM traceback em vez de ficar parado.
    faulthandler.dump_traceback_later(limite_segundos, exit=True)
    return tmp


def importar_cofre():
    """Importa o programa. Sem Tkinter ou sem tela, termina com [PULADO] (codigo 9), nunca como aprovado."""
    try:
        import tkinter as tk
        import cofre_senhas as cs
    except ImportError as ex:
        print(f"[PULADO] dependencia ausente: {ex}")
        sys.exit(CODIGO_PULADO)
    if getattr(cs, "tk", None) is None:
        print("[PULADO] Tkinter indisponivel")
        sys.exit(CODIGO_PULADO)
    try:
        t = tk.Tk()
        t.destroy()
    except tk.TclError as ex:
        print(f"[PULADO] sem tela para abrir janelas: {ex}")
        sys.exit(CODIGO_PULADO)
    return cs


class Relatorio:
    """Conta verificacoes e imprime no formato dos demais testes."""

    def __init__(self, titulo):
        self.titulo = titulo
        self.total = 0
        self.falhas = []
        print(f"=== {titulo} ===")

    def secao(self, texto):
        print(f"\n== {texto}")

    def info(self, texto):
        print(f"  [INFO] {texto}")

    def aviso(self, texto):
        print(f"  [AVISO] {texto}")

    def verifica(self, condicao, mensagem, detalhe=""):
        self.total += 1
        if condicao:
            print(f"  [OK]   {mensagem}")
        else:
            linha = mensagem + (f"  ->  {detalhe}" if detalhe else "")
            print(f"  [FALHOU] {linha}")
            self.falhas.append(linha)
        return bool(condicao)

    def fim(self):
        print(f"PASSOU {self.total - len(self.falhas)} / {self.total}")
        print(f"FALHAS: {len(self.falhas)}")
        for f in self.falhas[:40]:
            print(f"   - {f}")
        return 1 if self.falhas else 0


# ----------------------------------------------------------------------------------------------------------------
# Caixas de mensagem e dialogos que bloqueariam o teste
# ----------------------------------------------------------------------------------------------------------------
class Mensagens:
    """Espiao das caixas de mensagem: registra e responde sozinho. Instale DEPOIS de criar o App
    (o App reinstala as caixas proprias do programa no __init__)."""

    def __init__(self, cs, resposta=True):
        import tkinter.filedialog as fd
        self.chamadas = []
        self.resposta = resposta
        mb = cs.messagebox
        for nome in ("showinfo", "showwarning", "showerror"):
            setattr(mb, nome, self._fazer(nome, "ok"))
        for nome in ("askyesno", "askokcancel", "askretrycancel", "askquestion"):
            setattr(mb, nome, self._fazer(nome, None))
        for nome in ("askopenfilename", "asksaveasfilename", "askdirectory", "askopenfilenames"):
            setattr(fd, nome, self._fazer(nome, ""))

    def _fazer(self, nome, fixo):
        def espiao(*a, **kw):
            self.chamadas.append((nome, a, kw))
            return fixo if fixo is not None else self.resposta
        return espiao

    def erros(self):
        return [c for c in self.chamadas if c[0] == "showerror"]

    def texto_dos_erros(self):
        return " | ".join(str(c[1][1]) if len(c[1]) > 1 else str(c[1]) for c in self.erros())


class RecolhedorDeErros:
    """Guarda excecoes que o Tk teria impresso/mostrado (callbacks de botoes, after, bind...)."""

    def __init__(self, root):
        self.itens = []
        root.report_callback_exception = self._registrar

    def _registrar(self, tipo, valor, tb):
        import traceback
        self.itens.append("".join(traceback.format_exception(tipo, valor, tb))[-900:])

    def pegar(self):
        saida, self.itens = self.itens, []
        return saida


# ----------------------------------------------------------------------------------------------------------------
# Abrir o programa como os testes de tela fazem
# ----------------------------------------------------------------------------------------------------------------
_CONTADOR = [0]


def bombear(root, segundos=0.05):
    """Deixa o Tk trabalhar (after, <Configure>, janelas que aparecem) por um tempo."""
    import tkinter as tk
    fim = time.time() + segundos
    while True:
        try:
            root.update()
        except tk.TclError:
            return
        if time.time() >= fim:
            return
        time.sleep(0.004)


def criar_cofre_de_teste(cs, tmp, itens=(), modo=None, senha=SENHA):
    """Cria um cofre de verdade (Argon2 'alto') com os itens dados e devolve (caminho, Cofre aberto)."""
    _CONTADOR[0] += 1
    caminho = os.path.join(tmp, f"cofre_{_CONTADOR[0]}.dat")
    modo = cs.MODO_S if modo is None else modo
    cof = cs.Cofre.criar(caminho, senha, max_tentativas=5, modo=modo, nivel="alto")
    for dados in itens:
        cof.registros.append(cs.novo_item(**dados))
    if itens:
        cof.salvar()
    return caminho, cof


def abrir_app(cs, tmp, itens=(), mostrar=True, senha=SENHA):
    """Abre a janela principal com um cofre ja destravado (tela principal pronta).
    Devolve (app, root, recolhedor_de_erros, mensagens)."""
    import tkinter as tk
    caminho, cof = criar_cofre_de_teste(cs, tmp, itens, senha=senha)
    root = tk.Tk()
    root.withdraw()
    erros = RecolhedorDeErros(root)
    app = cs.App(root, caminho)
    msgs = Mensagens(cs)
    erros.root = root
    root.report_callback_exception = erros._registrar
    if mostrar:
        try:
            cs.revelar_janela(root)
        except Exception:                      # o teste nao deve cair por causa do "revelar"
            root.deiconify()
    app.cofre = cof
    app.tela_principal()
    bombear(root, 0.4)
    return app, root, erros, msgs


def fechar_app(cs, app):
    """Fecha tudo sem deixar a janela nem o executor de salvamento do teste para tras."""
    try:
        if app.cofre is not None:
            app.cofre.fechar()
    except Exception:
        pass
    try:
        app.root.destroy()
    except Exception:
        pass
    cs.Cofre.executor_salvar = None


# ----------------------------------------------------------------------------------------------------------------
# Percorrer widgets
# ----------------------------------------------------------------------------------------------------------------
def todos(w):
    """w e todos os seus descendentes."""
    yield w
    try:
        filhos = w.winfo_children()
    except Exception:
        return
    for f in filhos:
        yield from todos(f)


def toplevels(root):
    return [w for w in root.winfo_children() if w.winfo_class() == "Toplevel"]


def texto_de(w):
    try:
        return str(w.cget("text"))
    except Exception:
        return ""


def achar_botao(raiz, texto, exato=True):
    """Primeiro botao (ttk ou tk) visivel cujo texto bate."""
    for w in todos(raiz):
        if w.winfo_class() in ("TButton", "Button"):
            t = texto_de(w)
            if (t == texto) if exato else (texto.lower() in t.lower()):
                return w
    return None


def todos_os_textos(raiz):
    saida = []
    for w in todos(raiz):
        t = texto_de(w)
        if t:
            saida.append(t)
    return saida


def fechar_toplevels_novos(root, antes):
    for t in toplevels(root):
        if t not in antes:
            try:
                t.destroy()
            except Exception:
                pass


def chamar_e_fechar(app, funcao, esperar=0.6, durante=None):
    """Chama 'funcao' (que costuma abrir um dialogo) e fecha o que ela abrir, MESMO que ela fique esperando
    (wait_window): timers agendados antes destroem a janela nova e liberam a espera. 'durante(janelas_novas)'
    roda com os dialogos ainda abertos (para conferir cores, tamanhos...). Devolve (titulos, excecao)."""
    root = app.root
    antes = set(toplevels(root))
    # Os fechamentos agendados so podem disparar DEPOIS da inspecao (esperar): com 350 ms fixos o formulario
    # (que leva ~0,5 s para aparecer) era destruido antes de ser visto e a lista de titulos vinha vazia.
    # Se a funcao ficar esperando (wait_window), estes mesmos timers a liberam, so um pouco mais tarde.
    base = int(esperar * 1000) + 250
    for ms in (base, base + 600, base + 1500, base + 2700):
        root.after(ms, lambda: fechar_toplevels_novos(root, antes))
    titulos, erro = [], None
    try:
        funcao()
        bombear(root, esperar)
        novas = [t for t in toplevels(root) if t not in antes]
        titulos = [t.title() for t in novas]
        if durante is not None and novas:
            durante(novas)
    except Exception as ex:                    # noqa: BLE001 - o teste quer ver QUALQUER falha
        erro = ex
    fechar_toplevels_novos(root, antes)
    bombear(root, 0.1)
    return titulos, erro


def variaveis_do_fechamento(funcao):
    """Variaveis que uma funcao interna (closure) captura, por nome. Usado para chegar nos campos do formulario
    'Novo item' sem depender da posicao dos widgets."""
    nomes = funcao.__code__.co_freevars
    cel = funcao.__closure__ or ()
    saida = {}
    for n, c in zip(nomes, cel):
        try:
            saida[n] = c.cell_contents
        except ValueError:
            pass
    return saida


class GravadorDeBotoes:
    """Enquanto ativo, guarda (texto, comando) de todo ttk.Button criado: da acesso ao 'salvar' do formulario."""

    def __init__(self):
        import tkinter.ttk as ttk
        self._ttk = ttk
        self._orig = ttk.Button
        self.botoes = []
        gravador = self

        class BotaoGravado(self._orig):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                gravador.botoes.append((str(kw.get("text", "")), kw.get("command"), self))
        self._novo = BotaoGravado

    def __enter__(self):
        self._ttk.Button = self._novo
        return self

    def __exit__(self, *a):
        self._ttk.Button = self._orig

    def comando(self, texto):
        for t, c, w in reversed(self.botoes):
            if t == texto and c is not None:
                return c
        return None


# ----------------------------------------------------------------------------------------------------------------
# Cores
# ----------------------------------------------------------------------------------------------------------------
def hex_para_rgb(h):
    h = (h or "").strip()
    if len(h) == 7 and h.startswith("#"):
        try:
            return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
        except ValueError:
            return None
    return None


def cores_da_paleta(cs, nome):
    """Conjunto de cores (r,g,b) de uma paleta, ja com os apelidos que a interface usa."""
    return {hex_para_rgb(v) for v in cs._cores_da_paleta(nome).values() if hex_para_rgb(v)}


def cores_so_do_outro(cs, atual, outros):
    """Cores que existem em alguma das paletas 'outros' e NAO existem na paleta atual: se aparecerem na tela,
    sao sobras de outro tema."""
    mantidas = cores_da_paleta(cs, atual)
    velhas = set()
    for o in outros:
        velhas |= cores_da_paleta(cs, o)
    return velhas - mantidas


_OPCOES_COR = ("bg", "background", "fg", "foreground", "highlightbackground", "highlightcolor", "activebackground",
               "activeforeground", "insertbackground", "selectbackground", "selectforeground", "troughcolor",
               "disabledforeground")


def _rgb_do_widget(w, valor):
    valor = str(valor)
    if not valor:
        return None
    rgb = hex_para_rgb(valor)
    if rgb:
        return rgb
    try:
        r, g, b = w.winfo_rgb(valor)
        return (r >> 8, g >> 8, b >> 8)
    except Exception:
        return None


def varrer_cores_antigas(cs, raiz, velhas, limite=12):
    """Lista de achados 'caminho opcao=#cor' de widgets que ainda usam uma cor de OUTRO tema.
    Olha as opcoes de cor dos widgets tk, os estilos dos widgets ttk, os itens de Canvas e os icones em cache."""
    import tkinter.ttk as ttk
    achados = []
    estilo = ttk.Style(raiz)
    chaves_de_imagem = {}
    for cache in (getattr(cs, "_CACHE_ICONES", {}),):
        for chave, img in cache.items():
            chaves_de_imagem[str(img)] = chave
    for w in todos(raiz):
        try:
            if not w.winfo_exists():
                continue
        except Exception:
            continue
        cls = w.winfo_class()
        nome = f"{cls}:{str(w)[-28:]}"
        for op in _OPCOES_COR:
            try:
                v = w.cget(op)
            except Exception:
                continue
            rgb = _rgb_do_widget(w, v)
            if rgb in velhas:
                achados.append(f"{nome} {op}={v}")
        if cls.startswith("T"):                     # widget ttk: confere o estilo
            try:
                est = str(w.cget("style")) or cls
            except Exception:
                est = cls
            for op in ("background", "foreground", "fieldbackground"):
                try:
                    v = estilo.lookup(est, op)
                except Exception:
                    continue
                rgb = _rgb_do_widget(w, v)
                if rgb in velhas:
                    achados.append(f"{nome} estilo {est}.{op}={v}")
        if cls == "Canvas":
            try:
                for item in w.find_all()[:300]:
                    for op in ("fill", "outline"):
                        try:
                            v = w.itemcget(item, op)
                        except Exception:
                            continue
                        rgb = _rgb_do_widget(w, v)
                        if rgb in velhas:
                            achados.append(f"{nome} item{item} {op}={v}")
            except Exception:
                pass
        try:
            img = str(w.cget("image"))
        except Exception:
            img = ""
        if img and img in chaves_de_imagem:
            cor = chaves_de_imagem[img][1]
            if _rgb_do_widget(w, cor) in velhas:
                achados.append(f"{nome} icone '{chaves_de_imagem[img][0]}' pintado com {cor}")
        if len(achados) >= limite:
            break
    return achados[:limite]
