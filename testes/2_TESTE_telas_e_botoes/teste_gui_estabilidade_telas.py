#!/usr/bin/env python3
# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Estabilidade visual das telas: "clicou e a tela se mexeu".

Regra medida (vale para qualquer tela ou dialogo):
  Ao escolher uma opcao (botao de opcao, caixa de marcar, olho, "ver detalhes"...), NADA que ja estava na tela
  ACIMA do controle clicado pode mudar de lugar ou de tamanho, em nenhum instante depois do clique (0 px de
  tolerancia alem de 1 px de arredondamento), e a janela nao pode andar nem mudar de tamanho.
  Mudar o que fica abaixo do controle e normal (campos que aparecem/somem); o que nao pode e o conteudo de cima
  "pular" para se ajustar, nem o cartao crescer para cima, nem o dialogo ser recentralizado.

Como mede: fotografa a posicao e o tamanho de todos os widgets visiveis (sem usar a tela, so a geometria do Tk)
antes do clique e em 5 instantes depois (imediato, 40, 120, 300 e 600 ms), repete duas vezes cada opcao (a 1a
vez costuma revelar o cartao que "cresce na primeira troca") e compara. Um quadro intermediario fora do lugar
(A-B-A) tambem reprova.

Roda no Windows e no Linux (xvfb-run). Nao toca em nenhum cofre real: tudo em pasta temporaria.
Uso:  python teste_gui_estabilidade_telas.py [-v]
Saida: linhas [OK] / [FALHOU] / [PULADO]; codigo de saida 0 sem falhas, 1 com falhas.
"""
import os
import re
import shutil
import sys
import tempfile
import time
import traceback

sys.dont_write_bytecode = True                  # nao deixa __pycache__ na raiz do projeto (nem na pasta do teste)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"     # vale tambem para qualquer subprocesso
os.environ.setdefault("COFRE_GUI_TESTS_BACKGROUND", "1")
os.environ.setdefault("COFRE_SEM_VERIFICACAO_INICIAL", "1")
os.environ.setdefault("COFRE_TESTE_SEM_JANELA_FATAL", "1")

AQUI = os.path.dirname(os.path.abspath(__file__))
for _nivel in (0, 1, 2, 3):                     # acha a raiz do projeto (a pasta que tem cofre_senhas.py)
    _raiz = os.path.abspath(os.path.join(AQUI, *([".."] * _nivel)))
    if os.path.exists(os.path.join(_raiz, "cofre_senhas.py")):
        sys.path.insert(0, _raiz)
        break

import tkinter as tk                            # noqa: E402
from tkinter import ttk                         # noqa: E402

import cofre_senhas as cs                       # noqa: E402

# Este teste roda com a janela em SEGUNDO PLANO. Nessa situacao o proprio cofre cobre a janela com o aviso
# "Conteudo oculto / clique para mostrar" (e depois se bloqueia). A capa e centralizada sobre a janela e "anda"
# quando o dialogo cresce, o que reprovava o Gerador de senhas por um pulo que o usuario nunca ve (a janela dele
# tem o foco). Aqui o foco do sistema nao e medido; so vale dentro deste processo de teste.
cs.App._app_sem_foco = lambda self: False
cs.BLOQUEIO_SEM_FOCO_S = 6 * 3600
cs.App.INATIVIDADE_MS = 6 * 3600 * 1000

VERBOSO = "-v" in sys.argv
TOL = 1                                         # px de arredondamento tolerados
INSTANTES_MS = (0, 40, 120, 300, 600)           # quando fotografar depois do clique
SENHA = "senha-de-teste-bem-longa-123"

OK, FALHAS, PULADOS = [], [], []


def registrar(lista, texto):
    lista.append(texto)
    marca = {id(OK): "[OK]", id(FALHAS): "[FALHOU]", id(PULADOS): "[PULADO]"}[id(lista)]
    print(f"{marca} {texto}", flush=True)


# --------------------------------------------------------------------------- medicao
def _filhos(w):
    try:
        return w.winfo_children()
    except tk.TclError:
        return []


def fotografar(topo):
    """{caminho: (x, y, largura, altura, classe, texto)} de todo widget visivel DENTRO desta janela.
    x e y sao RELATIVOS a janela (se o dialogo andar, isso e avaliado a parte, como movimento da janela)."""
    foto = {}
    ox, oy = topo.winfo_rootx(), topo.winfo_rooty()

    def visitar(w):
        for c in _filhos(w):
            if isinstance(c, tk.Toplevel):
                continue                        # outra janela: fotografada a parte
            try:
                if c.winfo_ismapped() and c.winfo_width() > 1 and c.winfo_height() > 1:
                    try:
                        txt = str(c.cget("text"))[:30]
                    except (tk.TclError, AttributeError):
                        txt = ""
                    foto[str(c)] = (c.winfo_rootx() - ox, c.winfo_rooty() - oy, c.winfo_width(), c.winfo_height(),
                                    c.winfo_class(), txt)
            except tk.TclError:
                continue
            visitar(c)

    visitar(topo)
    return foto


def geometria_janela(topo):
    return (topo.winfo_rootx(), topo.winfo_rooty(), topo.winfo_width(), topo.winfo_height())


def bombear(root, ms):
    """Deixa o Tk processar eventos por 'ms' milissegundos (animacoes, after, Configure)."""
    fim = time.time() + ms / 1000.0
    while True:
        try:
            root.update()
        except tk.TclError:
            return
        if time.time() >= fim:
            return
        time.sleep(0.005)


def _diferente(a, b):
    return any(abs(x - y) > TOL for x, y in zip(a[:4], b[:4]))


def _problemas_janela(topo, jan0, jan, nome, alvo):
    """Regras da JANELA. Principal: nada pode mudar. Dialogo: largura e posicao fixas (so sobe o minimo se o fundo
    passar da borda da tela) e a altura so pode CRESCER (nunca encolher: encolher e piscar)."""
    if not isinstance(topo, tk.Toplevel):
        return [f"{nome}: a JANELA PRINCIPAL mudou {jan0} -> {jan} aos {alvo} ms"] if _diferente(jan0, jan) else []
    achados = []
    if abs(jan[2] - jan0[2]) > TOL:
        achados.append(f"{nome}: o dialogo mudou de LARGURA {jan0[2]} -> {jan[2]} aos {alvo} ms")
    if jan[3] < jan0[3] - TOL:
        achados.append(f"{nome}: o dialogo ENCOLHEU {jan0[3]} -> {jan[3]} aos {alvo} ms")
    if abs(jan[0] - jan0[0]) > TOL:
        achados.append(f"{nome}: o dialogo andou na horizontal {jan0[0]} -> {jan[0]} aos {alvo} ms")
    if abs(jan[1] - jan0[1]) > TOL:
        limite = topo.winfo_screenheight() - cs._px(48) + TOL
        if not (jan[1] < jan0[1] and jan0[1] + jan[3] > limite):          # subir so e valido se faltou espaco
            achados.append(f"{nome}: o dialogo andou na vertical {jan0[1]} -> {jan[1]} aos {alvo} ms")
    return achados


def medir_acao(root, topo, controle, acao, nome, so_fixos=False):
    """Executa 'acao' (o clique) e devolve a lista de problemas de estabilidade."""
    bombear(root, 80)
    antes = fotografar(topo)
    jan0 = geometria_janela(topo)
    try:
        corte = controle.winfo_rooty() - topo.winfo_rooty()     # tudo que termina acima disso nao pode se mexer
        if so_fixos:
            corte = 10 ** 9
    except tk.TclError:
        corte = 10 ** 9
    acao()
    problemas = []
    t0 = time.time()
    for alvo in INSTANTES_MS:
        if alvo == 0:
            try:
                root.update_idletasks()
            except tk.TclError:
                pass
        else:
            bombear(root, max(0, alvo - (time.time() - t0) * 1000))
        depois = fotografar(topo)
        jan = geometria_janela(topo)
        problemas += _problemas_janela(topo, jan0, jan, nome, alvo)
        # Barra de rolagem que aparece pela 1a vez (dialogo que passou da altura da tela): estreita a largura util
        # uma unica vez. Aceito so isso (mudanca de largura, nada mais), porque a barra fica fixa depois.
        barra_nova = (not any(v[4] == "TScrollbar" for v in antes.values())
                      and any(v[4] == "TScrollbar" for v in depois.values()))
        for cam, a in antes.items():
            b = depois.get(cam)
            if b is None or b[4] != a[4] or b[5] != a[5]:
                continue                        # o widget sumiu/foi trocado (outro texto): e conteudo novo, nao "pulo"
            if barra_nova and a[:2] == b[:2] and a[3] == b[3]:
                continue
            if so_fixos and a[4] not in ("Frame", "TFrame", "Canvas", "TButton", "TEntry", "TLabelframe"):
                continue                        # nesta lista so as AREAS FIXAS contam (rotulos se repetem: "1", "2"...)
            if (so_fixos or a[1] + a[3] <= corte + TOL) and _diferente(a, b):
                problemas.append(f"{nome}: '{a[4]} {a[5]}' (acima do clique) foi de {a[:4]} para {b[:4]} "
                                 f"aos {alvo} ms")
    # sem repeticao do mesmo achado
    vistos, unicos = set(), []
    for p in problemas:
        chave = re.sub(r" aos \d+ ms", "", p)
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(p)
    return unicos


def controles(topo):
    """Controles de opcao da janela: botoes de opcao, caixas de marcar, olhos e 'ver detalhes'."""
    achados = []

    def visitar(w):
        for c in _filhos(w):
            if isinstance(c, tk.Toplevel):
                continue
            try:
                cls = c.winfo_class()
                if c.winfo_ismapped() and cls in ("TRadiobutton", "TCheckbutton", "Radiobutton", "Checkbutton",
                                                  "TButton"):
                    txt = ""
                    try:
                        txt = str(c.cget("text"))
                    except tk.TclError:
                        pass
                    if cls == "TButton" and not re.search(r"detalhe|👁|mostrar|ocultar|avan|extra|▸|▾|▶|▼", txt, re.I):
                        pass
                    else:
                        achados.append(c)
            except tk.TclError:
                pass
            visitar(c)

    visitar(topo)
    return achados


def varrer(root, topo, nome_tela):
    """Aperta cada opcao da janela duas vezes (ida e volta) e junta os problemas.
    A lista de controles e lida de novo a cada clique: varias telas refazem as opcoes ao escolher uma."""
    problemas, usados = [], 0
    for rodada in (1, 2):
        indice = 0
        while True:
            lista = controles(topo)
            if indice >= len(lista):
                break
            c = lista[indice]
            indice += 1
            try:
                txt = str(c.cget("text")).strip()[:28]
                rotulo = f"{nome_tela} > {c.winfo_class()} '{txt}' (rodada {rodada})"
                if str(c.cget("state")) == "disabled":
                    continue
            except tk.TclError:
                continue
            usados += 1
            try:
                problemas += medir_acao(root, topo, c, c.invoke, rotulo)
            except tk.TclError as ex:
                problemas.append(f"{rotulo}: erro do Tk ao clicar: {ex}")
    return problemas, usados


# --------------------------------------------------------------------------- cenarios
class Ambiente:
    def __init__(self):
        self.pasta = tempfile.mkdtemp(prefix="cofre_estab_")
        self.root = tk.Tk()
        self.app = None
        self.n = 0

    def novo_caminho(self):
        self.n += 1
        return os.path.join(self.pasta, f"cofre{self.n}.dat")

    def abrir_app(self, caminho):
        self.app = cs.App(self.root, caminho)
        bombear(self.root, 300)
        return self.app

    def reiniciar(self):
        """Fecha o App atual e destroi tudo, para o proximo cenario partir do zero."""
        try:
            if self.app is not None and self.app.cofre is not None:
                self.app.cofre.fechar()
        except Exception:
            pass
        for w in list(self.root.winfo_children()):
            try:
                w.destroy()
            except tk.TclError:
                pass
        self.app = None

    def fim(self):
        self.reiniciar()
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        shutil.rmtree(self.pasta, ignore_errors=True)


def cenario_desbloqueio(amb, modo, nome):
    caminho = amb.novo_caminho()
    cs.Cofre.criar(caminho, SENHA, 5, modo, "alto").fechar()
    amb.abrir_app(caminho)
    problemas, usados = varrer(amb.root, amb.root, nome)
    return problemas, usados


def cenario_criar(amb):
    caminho = amb.novo_caminho()
    amb.abrir_app(caminho)                      # sem arquivo: abre a tela de criacao
    return varrer(amb.root, amb.root, "Criar cofre")


def _principal(amb):
    caminho = amb.novo_caminho()
    c = cs.Cofre.criar(caminho, SENHA, 5, cs.MODO_S, "alto")
    for i in range(12):
        c.registros.append(cs.novo_item(servico=f"Servico {i}", login=f"user{i}", senha=f"Senha-{i}-xyz!",
                                        grupo="Trabalho" if i % 2 else "Pessoal"))
    c.salvar()
    c.fechar()
    amb.abrir_app(caminho)
    amb.app.cofre = cs.Cofre.abrir(caminho, senha=SENHA)
    amb.app.tela_principal()
    bombear(amb.root, 400)


def cenario_principal(amb):
    _principal(amb)
    return varrer(amb.root, amb.root, "Tela principal")


def _toplevels(root):
    return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]


def cenario_dialogo(amb, abrir, nome, pre=None, depois=None):
    """Abre um dialogo (eles BLOQUEIAM em wait_window), aperta as opcoes de dentro do laco de eventos e fecha.
    'depois(topo)' pode devolver problemas extras medidos pelo cenario."""
    if pre:
        pre(amb)
    else:
        _principal(amb)
    resultado = {"res": None, "erro": None, "feito": False}
    antes = set(map(str, _toplevels(amb.root)))

    def conduzir():
        topo = None
        try:
            novos = [t for t in _toplevels(amb.root) if str(t) not in antes]
            if not novos:
                return
            topo = novos[-1]
            bombear(amb.root, 400)
            problemas, usados = varrer(amb.root, topo, nome)
            if depois:
                problemas += depois(topo) or []
            resultado["res"] = (problemas, usados)
        except Exception:
            resultado["erro"] = traceback.format_exc()
        finally:
            resultado["feito"] = True
            for t in _toplevels(amb.root):
                if str(t) not in antes:
                    try:
                        t.destroy()
                    except tk.TclError:
                        pass

    amb.root.after(600, conduzir)
    abrir(amb.app)                              # dialogos bloqueantes so voltam quando conduzir() os fecha
    limite = time.time() + 60
    while not resultado["feito"] and time.time() < limite:      # os nao bloqueantes: espera o teste terminar
        bombear(amb.root, 50)
    if resultado["erro"]:
        raise RuntimeError(resultado["erro"])
    if resultado["res"] is None:
        return None, 0
    return resultado["res"]


def cenario_selecao_principal(amb):
    """Tela principal: escolher itens diferentes na lista (simples, completo, com muita nota) e grupos na barra
    lateral. As areas fixas (barra de ferramentas, lateral, lista, painel de detalhes) nao podem mudar de
    posicao nem de tamanho, nem durante a remontagem do painel."""
    caminho = amb.novo_caminho()
    c = cs.Cofre.criar(caminho, SENHA, 5, cs.MODO_S, "alto")
    dados = [
        dict(servico="Simples", login="a", senha="Senha-simples-1!"),
        dict(servico="Completo", login="usuario@exemplo.com", senha="Senha-completa-2!", pin="1234",
             chave="ABCD-EFGH", numero_conta="12345-6", agencia="0001",
             codigos="\n".join(str(111111 * n) for n in range(1, 9)), notas="Linha de nota\n" * 12,
             grupo="Trabalho", pessoa="Maria"),
        dict(servico="Nota enorme", login="x" * 60, senha="S3nh4-longa-3!" * 3,
             notas="texto longo de nota " * 40, grupo="Pessoal"),
        dict(servico="Nome de conta muito longo para testar a quebra de linha no cabecalho do painel " * 2,
             login="l", senha="Senha-4-xxxxx!!"),
    ]
    for d in dados:
        c.registros.append(cs.novo_item(**d))
    c.salvar()
    c.fechar()
    amb.abrir_app(caminho)
    amb.app.cofre = cs.Cofre.abrir(caminho, senha=SENHA)
    amb.app.tela_principal()
    bombear(amb.root, 500)
    a = amb.app
    ids = [r["id"] for r in a.cofre.registros]
    problemas, cliques = [], 0
    grupos = []
    try:
        grupos = list(getattr(a.lateral, "_itens", {}))[:6]
    except (AttributeError, TypeError):
        pass
    for rodada in (1, 2):
        for iid in grupos:                       # barra lateral: grupos e pessoas filtram a lista
            cliques += 1
            nome = f"Tela principal > barra lateral '{str(iid)[:18]}' (rodada {rodada})"
            problemas += medir_acao(amb.root, amb.root, a.lateral, lambda i=iid: a.lateral.selection_set(i), nome,
                                    so_fixos=True)
        for iid in ids + ids[:1]:
            cliques += 1
            nome = f"Tela principal > escolher item {iid[:4]} (rodada {rodada})"
            problemas += medir_acao(amb.root, amb.root, a.tree.canvas if hasattr(a.tree, "canvas") else a.tree,
                                    lambda i=iid: a.tree.selection_set(i), nome, so_fixos=True)
    return problemas, cliques


CENARIOS = []


def cenario(nome):
    def deco(f):
        CENARIOS.append((nome, f))
        return f
    return deco


@cenario("Desbloqueio (senha OU chave)")
def _(amb):
    return cenario_desbloqueio(amb, cs.MODO_OU, "Desbloqueio OU")


@cenario("Desbloqueio (senha E chave)")
def _(amb):
    return cenario_desbloqueio(amb, cs.MODO_E, "Desbloqueio E")


@cenario("Desbloqueio (so senha)")
def _(amb):
    return cenario_desbloqueio(amb, cs.MODO_S, "Desbloqueio S")


@cenario("Criar cofre")
def _(amb):
    return cenario_criar(amb)


@cenario("Tela principal")
def _(amb):
    return cenario_principal(amb)


@cenario("Tela principal: escolher itens")
def _(amb):
    return cenario_selecao_principal(amb)


@cenario("Gerador de senhas")
def _(amb):
    return cenario_dialogo(amb, lambda a: a.dialogo_gerador(), "Gerador")


@cenario("Novo item")
def _(amb):
    return cenario_dialogo(amb, lambda a: a.dialogo_registro(None), "Novo item")


@cenario("Aparencia e cores")
def _(amb):
    return cenario_dialogo(amb, lambda a: a.dialogo_aparencia(), "Aparencia")


def main():
    amb = Ambiente()
    try:
        for nome, f in CENARIOS:
            try:
                amb.reiniciar()
                problemas, usados = f(amb)
            except Exception:
                registrar(FALHAS, f"{nome}: excecao no teste\n{traceback.format_exc()}")
                continue
            if problemas is None:
                registrar(PULADOS, f"{nome}: o dialogo nao abriu neste ambiente")
            elif problemas:
                registrar(FALHAS, f"{nome}: {len(problemas)} problema(s) em {usados} cliques\n    "
                          + "\n    ".join(problemas[:12]))
            else:
                registrar(OK, f"{nome}: {usados} cliques sem nenhum movimento indevido")
    finally:
        amb.fim()
    print(f"\nResumo: {len(OK)} ok, {len(PULADOS)} pulados, {len(FALHAS)} falhas")
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())
