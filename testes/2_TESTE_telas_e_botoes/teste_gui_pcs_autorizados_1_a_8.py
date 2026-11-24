# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Tela "Computadores autorizados": autorizar 1, 2, 3 ... ate 8 computadores pelos botoes de verdade.

O teste do motor (1_TESTE_motor_do_cofre/teste_nucleo_pcs_autorizados_1_a_8.py) cobre as regras e o arquivo.
Este cobre a TELA: botoes certos habilitados/desabilitados, lista, contador "Ativo: N", marca "este computador",
mensagens de recusa (9o computador, repeticao, remover o ultimo, limitar a 1 com varios), codigo de recuperacao,
desativar, e que nada fica cortado dentro do dialogo.

"Computador diferente" = identidades_do_pc() simulada por numero (o resto e o codigo real). Perguntas de senha,
de nome e a janela do codigo de recuperacao sao respondidas pelo teste (sem digitar nada).
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _apoio_gui_novos as A          # noqa: E402

TMP = A.preparar("cofre_gui_pcs_", limite_segundos=900)
cs = A.importar_cofre()
import tkinter as tk                  # noqa: E402,F401

rel = A.Relatorio("Computadores autorizados (tela): de 1 ate 8")
PC = [1]
cs.identidades_do_pc = lambda: [hashlib.sha256(b"cofre-teste-pc-simulado|%d" % PC[0]).digest()]
CODIGOS = []


def dialogo(app, funcao):
    root = app.root
    antes = set(A.toplevels(root))
    funcao()
    A.bombear(root, 0.35)
    novos = [t for t in A.toplevels(root) if t not in antes]
    return novos[0] if novos else None


def lista_do(d):
    return next((w for w in A.todos(d) if w.winfo_class() == "Treeview"), None)


def estado_do(d):
    return next((t for t in A.todos_os_textos(d) if t.startswith(("Ativo:", "Desativado:"))), "")


def linhas(d):
    tv = lista_do(d)
    return [tv.item(i, "values") for i in tv.get_children()] if tv else []


def nao_cortado(d, rotulo):
    """Botoes com o texto inteiro e nada saindo da janela do dialogo."""
    d.update_idletasks()
    cortados, fora = [], []
    dx0, dx1 = d.winfo_rootx(), d.winfo_rootx() + d.winfo_width()
    for w in A.todos(d):
        if w.winfo_class() in ("TButton", "Button") and w.winfo_ismapped():
            if w.winfo_width() + 1 < w.winfo_reqwidth():
                cortados.append(f"{A.texto_de(w)!r} {w.winfo_width()}<{w.winfo_reqwidth()}")
        if w.winfo_ismapped() and w.winfo_width() > 1:
            if w.winfo_rootx() + w.winfo_width() > dx1 + 2 or w.winfo_rootx() < dx0 - 2:
                fora.append(f"{w.winfo_class()}:{A.texto_de(w)[:20]!r}")
    rel.verifica(not cortados, f"{rotulo}: texto dos botoes nao esta cortado", "; ".join(cortados))
    rel.verifica(not fora, f"{rotulo}: nenhum widget sai dos limites do dialogo", "; ".join(fora[:5]))


def principal():
    app, root, erros, msgs = A.abrir_app(cs, TMP, [
        dict(servico="Banco Azul", login="ana", senha="s1-Banco-Azul!"),
        dict(servico="Netflix", login="pai", senha="s3-Netflix-2026!")])
    itens_de = lambda regs: sorted((x["servico"].encode(), x["login"].encode(), x["senha"].encode()) for x in regs)
    esperado = itens_de(app.cofre.registros)      # bytes: Cofre.fechar() zera as strings dos itens no lugar

    # respostas automaticas (sem digitar nada)
    app._confirmar_senha_atual = lambda titulo: A.SENHA
    app._pedir_texto = lambda titulo, texto, inicial="": f"PC {PC[0]}"
    app.mostrar_codigo_recuperacao = lambda codigo: (CODIGOS.append(codigo) or True)
    perguntas = []

    def pergunta(titulo=None, mensagem=None, *a, **kw):
        perguntas.append(str(titulo))
        return not str(titulo).startswith("Refor")      # "Reforco (DPAPI)": nao, para o teste ser igual em todo SO
    cs.messagebox.askyesno = pergunta

    def abrir_do_disco(n):
        PC[0] = n
        try:
            # consulta=True: abre SEM gravar. Uma abertura normal regrava o arquivo e o app em teste (assinatura
            # antiga) passaria a receber ConflitoGravacao em todo salvar seguinte.
            return cs.Cofre.abrir(app.caminho, senha=A.SENHA, consulta=True)
        except Exception as ex:                # noqa: BLE001
            return ex

    try:
        rel.secao("1 computador")
        PC[0] = 1
        d = dialogo(app, app.gerenciar_computadores)
        rel.verifica(d is not None, "a tela 'Computadores autorizados' abre")
        rel.verifica(estado_do(d).startswith("Desativado"), "comeca 'Desativado: abre em qualquer computador'", estado_do(d))
        bt_aut = A.achar_botao(d, "Autorizar este computador")
        for rot_b in ("Remover selecionado", "Novo código de recuperação", "Desativar"):
            b = A.achar_botao(d, rot_b)
            rel.verifica(b is not None and str(b.cget("state")) == "disabled", f"sem computador, '{rot_b}' esta desabilitado")
        rel.verifica(bt_aut is not None and str(bt_aut.cget("state")) != "disabled", "'Autorizar este computador' esta habilitado")
        nao_cortado(d, "tela vazia")
        bt_aut.invoke()
        A.bombear(root, 0.6)
        rel.verifica(estado_do(d).startswith("Ativo: 1"), "autorizar o PC 1: 'Ativo: 1 computador(es)'", estado_do(d))
        rel.verifica(len(CODIGOS) == 1, "o codigo de recuperacao foi mostrado UMA vez", str(CODIGOS))
        rel.verifica(len(linhas(d)) == 1 and "este computador" in linhas(d)[0][1], "a lista mostra o PC 1 marcado 'este computador'",
                     str(linhas(d)))
        rel.verifica(str(A.achar_botao(d, "Autorizar este computador").cget("state")) == "disabled",
                     "com este PC ja autorizado, 'Autorizar este computador' fica desabilitado")
        for rot_b in ("Remover selecionado", "Novo código de recuperação", "Desativar"):
            rel.verifica(str(A.achar_botao(d, rot_b).cget("state")) != "disabled", f"com 1 PC, '{rot_b}' fica habilitado")
        nao_cortado(d, "1 computador")
        r = abrir_do_disco(1)
        rel.verifica(not isinstance(r, Exception) and itens_de(r.registros) == esperado,
                     "o arquivo no disco abre como PC 1 com os itens intactos", repr(r))
        if not isinstance(r, Exception):
            r.fechar()
        A.achar_botao(d, "Fechar").invoke()
        A.bombear(root, 0.2)

        rel.secao("do 2o ao 8o computador (a tela pergunta 'liberar mais' no 2o)")
        for n in range(2, cs.MAX_PC + 1):
            PC[0] = n
            perguntas.clear()
            d = dialogo(app, app.gerenciar_computadores)
            rel.verifica(d is not None and estado_do(d).startswith(f"Ativo: {n - 1}"),
                         f"PC {n}: a tela abre mostrando {n - 1} autorizados", estado_do(d) if d else "sem dialogo")
            rel.verifica(not any("este computador" in v[1] for v in linhas(d)),
                         f"PC {n}: nenhuma linha marcada como 'este computador' antes de autorizar")
            b = A.achar_botao(d, "Autorizar este computador")
            rel.verifica(str(b.cget("state")) != "disabled", f"PC {n}: 'Autorizar este computador' habilitado")
            b.invoke()
            A.bombear(root, 0.7)
            if n == 2:
                rel.verifica(any("Limitado a 1" in p for p in perguntas), "2o PC: a tela pergunta se quer liberar mais computadores",
                             str(perguntas))
            rel.verifica(estado_do(d).startswith(f"Ativo: {n}"), f"PC {n}: 'Ativo: {n} computador(es)'", estado_do(d))
            rel.verifica(len(linhas(d)) == n, f"PC {n}: a lista tem {n} linhas", str(len(linhas(d))))
            marcadas = [v for v in linhas(d) if "este computador" in v[1]]
            rel.verifica(len(marcadas) == 1 and marcadas[0][0] == f"PC {n}", f"PC {n}: so a linha 'PC {n}' esta marcada",
                         str(marcadas))
            rel.verifica(len(CODIGOS) == 1, f"PC {n}: nao mostra outro codigo de recuperacao", str(len(CODIGOS)))
            r = abrir_do_disco(n)
            rel.verifica(not isinstance(r, Exception) and len(r.pc["maquinas"]) == n and
                         itens_de(r.registros) == esperado,
                         f"PC {n}: o disco tem {n} computadores e o PC {n} abre com itens intactos", repr(r))
            if not isinstance(r, Exception):
                r.fechar()
            nao_cortado(d, f"{n} computadores")
            sobras = erros.pegar()
            rel.verifica(not sobras, f"PC {n}: nenhuma excecao do Tk", sobras[0] if sobras else "")
            A.achar_botao(d, "Fechar").invoke()
            A.bombear(root, 0.15)

        rel.secao("limites na tela")
        PC[0] = 9
        msgs.chamadas.clear()
        d = dialogo(app, app.gerenciar_computadores)
        A.achar_botao(d, "Autorizar este computador").invoke()
        A.bombear(root, 0.5)
        rel.verifica("Limite de 8" in msgs.texto_dos_erros(), "o 9o computador mostra o erro 'Limite de 8 computadores'",
                     msgs.texto_dos_erros())
        rel.verifica(estado_do(d).startswith("Ativo: 8") and len(linhas(d)) == 8, "depois da recusa continuam 8 computadores")
        PC[0] = 1
        msgs.chamadas.clear()
        b_lim = A.achar_botao(d, "Limitar a 1 computador")
        rel.verifica(b_lim is not None, "com o limite 8 ativo, o botao diz 'Limitar a 1 computador'")
        if b_lim is not None:
            b_lim.invoke()
            A.bombear(root, 0.4)
            rel.verifica("Remova" in msgs.texto_dos_erros(), "limitar a 1 com 8 autorizados e recusado com explicacao",
                         msgs.texto_dos_erros())
            rel.verifica(app.cofre.pcs_multiplos(), "o limite 8 continua ativo")

        rel.secao("remover pela tela, de 8 ate 1")
        for n in range(8, 1, -1):
            tv = lista_do(d)
            iid = next(i for i in tv.get_children() if tv.item(i, "values")[0] == f"PC {n}")
            tv.selection_set(iid)
            A.achar_botao(d, "Remover selecionado").invoke()
            A.bombear(root, 0.6)
            rel.verifica(estado_do(d).startswith(f"Ativo: {n - 1}") and len(linhas(d)) == n - 1,
                         f"remover 'PC {n}': restam {n - 1} na tela", estado_do(d))
            r = abrir_do_disco(n)
            rel.verifica(isinstance(r, cs.PcNaoAutorizado), f"o PC {n} removido nao abre mais", repr(r))
        PC[0] = 1
        tv = lista_do(d)
        tv.selection_set(tv.get_children()[0])
        msgs.chamadas.clear()
        A.achar_botao(d, "Remover selecionado").invoke()
        A.bombear(root, 0.4)
        rel.verifica(len(linhas(d)) == 1 and ("único" in msgs.texto_dos_erros() or "unico" in msgs.texto_dos_erros().lower()),
                     "remover o ultimo computador e recusado ('use Desativar')", msgs.texto_dos_erros())
        rel.verifica(str(A.achar_botao(d, "Remover selecionado").cget("state")) != "disabled",
                     "o botao 'Remover selecionado' segue funcional depois da recusa")

        rel.secao("novo codigo de recuperacao e desativar")
        antes = len(CODIGOS)
        A.achar_botao(d, "Novo código de recuperação").invoke()
        A.bombear(root, 0.6)
        rel.verifica(len(CODIGOS) == antes + 1 and CODIGOS[-1] != CODIGOS[0], "'Novo codigo de recuperacao' mostra um codigo diferente")
        A.achar_botao(d, "Desativar").invoke()
        A.bombear(root, 0.7)
        rel.verifica(estado_do(d).startswith("Desativado") and not linhas(d), "'Desativar' limpa a lista e mostra 'Desativado'",
                     estado_do(d))
        r = abrir_do_disco(77)
        rel.verifica(not isinstance(r, Exception) and itens_de(r.registros) == esperado,
                     "desativado: um computador qualquer abre, itens intactos", repr(r))
        if not isinstance(r, Exception):
            r.fechar()
        A.achar_botao(d, "Fechar").invoke()
        A.bombear(root, 0.2)
        rel.verifica(not A.toplevels(root), "nenhum dialogo ficou aberto")
        sobras = erros.pegar()
        rel.verifica(not sobras, "nenhuma excecao do Tk no teste inteiro", sobras[0] if sobras else "")
    finally:
        A.fechar_app(cs, app)


if __name__ == "__main__":
    principal()
    sys.exit(rel.fim())
