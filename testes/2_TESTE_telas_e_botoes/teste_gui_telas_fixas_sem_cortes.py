# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Telas estaticas: ao escolher outra opcao, o que e fixo NAO pode mexer, e nada pode ficar cortado.

A) Regioes fixas: tamanho da janela, cabecalho, barra lateral, painel de detalhes, coluna da lista e rodape medidos
   antes e depois de CADA interacao (escolher cada item, grupo e pessoa, buscar, lista vazia, A->Z, texto enorme,
   trocar de tema). Qualquer pixel de diferenca em posicao/tamanho reprova.
B) Cortes: texto de botao/rotulo mais largo que o widget, rotulo com quebra de linha mais alto que o widget e widget
   saindo da janela. Verificado na tela principal em cada estado, no tamanho padrao e no minimo, em todos os temas.
C) Dialogos: cada item do menu "..." abre sem cortes; o formulario Novo item mantem largura e posicao ao adicionar
   credenciais (botoes da faixa) e ao mostrar/ocultar cada segredo (olho proprio); "Aparencia e cores" nao muda de tamanho ao escolher outra opcao.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _apoio_gui_novos as A          # noqa: E402

TMP = A.preparar("cofre_gui_fixas_", limite_segundos=1200)
cs = A.importar_cofre()
# Estes testes duram minutos e rodam com a janela em SEGUNDO PLANO. Sem isto o proprio cofre se bloqueia no meio do
# teste (60 s com outro programa em primeiro plano, ou 3 min sem uso) e tudo que vem depois falha por "cofre bloqueado".
# So vale dentro deste processo de teste; o programa real nao muda.
cs.BLOQUEIO_SEM_FOCO_S = 6 * 3600
cs.App.INATIVIDADE_MS = 6 * 3600 * 1000
import tkinter as tk                  # noqa: E402

rel = A.Relatorio("Telas fixas: nada se mexe, nada fica cortado")
TEMAS = list(cs.PALETAS)
ITENS = [
    dict(servico="Banco Azul", login="ana@exemplo.com", senha="Abc-123-xyz-987-Q", grupo="Bancos"),
    dict(servico="Instagram", login="ana", senha="x", grupo="Redes sociais", pessoa="Pai"),
    dict(servico="Netflix", login="pai@exemplo.com", senha="Netflix-Senha-2026!", grupo="Streaming", pessoa="Mae"),
    dict(servico="Nome de conta absurdamente comprido " * 4, login="login" * 30, senha="s" * 200,
         grupo="Um grupo com nome muito muito comprido para testar o corte", notas="linha\n" * 60),
    dict(servico="Cartao Loja", login="mae", senha="Cartao-9988-xx", grupo="Compras", pin="1234",
         numero_conta="12345-6", agencia="0001", codigos="\n".join(f"COD-{i:04d}" for i in range(30))),
]
FIXOS = ("_btn_novo", "_btn_mais", "_btn_bloquear", "_btn_ajuda", "_btn_ordem")


def medida(w):
    return (w.winfo_rootx(), w.winfo_rooty(), w.winfo_width(), w.winfo_height())


def assinatura(app):
    """Posicao e tamanho (na tela) de tudo que deve ficar parado enquanto o usuario escolhe opcoes."""
    r = app.root
    sig = {"janela": (r.winfo_width(), r.winfo_height()), "detalhe": medida(app.detalhe), "lista": medida(app.tree),
           "lateral": medida(app.lateral), "pessoas": medida(app.lateral_pessoas), "status": medida(app.status),
           "campo_busca": medida(app.campo_busca), "painel_seg": medida(app._painel_seg)}
    for nome in FIXOS:
        sig[nome] = medida(getattr(app, nome))
    return sig


def mesmo_lugar(d, m0, m):
    """m0/m = (largura, x, y) do dialogo antes e depois. O formulario cresce PARA BAIXO e fica onde esta (o programa nao
    recentraliza); a unica exceção legitima e subir o MINIMO quando o fundo passaria da borda da tela (_manter_no_lugar).
    Entao: largura e x iguais sempre; y igual, ou y menor so se o fundo do dialogo esta colado no fim da tela."""
    if m[0] != m0[0] or m[1] != m0[1]:
        return False
    if m[2] == m0[2]:
        return True
    fundo = m[2] + d.winfo_height()
    return m[2] < m0[2] and fundo >= d.winfo_screenheight() - 140


def comparar(app, base, rotulo):
    atual = assinatura(app)
    mudou = [f"{k}: {base[k]} -> {atual[k]}" for k in base if base[k] != atual[k]]
    rel.verifica(not mudou, f"{rotulo}: regioes fixas nao se mexeram", "; ".join(mudou)[:600])


def cortes(raiz, rotulo, limite=8):
    """Texto cortado e widgets fora da janela dentro de 'raiz'."""
    raiz.update_idletasks()
    topo = raiz.winfo_toplevel()
    x0, y0 = topo.winfo_rootx(), topo.winfo_rooty()
    x1, y1 = x0 + topo.winfo_width(), y0 + topo.winfo_height()
    achados = []
    for w in A.todos(raiz):
        try:
            if not w.winfo_ismapped() or w.winfo_width() <= 1:
                continue
            cls = w.winfo_class()
            texto = A.texto_de(w)
            if cls in ("Label", "TLabel", "Button", "TButton") and texto.strip() and "\n" not in texto:
                try:
                    wrap = int(str(w.cget("wraplength")) or 0)
                except (tk.TclError, ValueError):
                    wrap = 0
                if not wrap and w.winfo_width() + 1 < w.winfo_reqwidth():
                    achados.append(f"{cls} {texto[:28]!r} largura {w.winfo_width()} < {w.winfo_reqwidth()} [{str(w)[-70:]}]")
                if wrap and w.winfo_height() + 1 < w.winfo_reqheight():
                    achados.append(f"{cls} {texto[:28]!r} altura {w.winfo_height()} < {w.winfo_reqheight()} (quebra de linha cortada)")
            if cls in ("Button", "TButton", "Label", "TLabel", "TEntry", "TCombobox") and w.winfo_viewable():
                dir_, baixo = w.winfo_rootx() + w.winfo_width(), w.winfo_rooty() + w.winfo_height()
                if dir_ > x1 + 2 or baixo > y1 + 2 or w.winfo_rootx() < x0 - 2:
                    achados.append(f"{cls} {texto[:24]!r} fora da janela")
        except tk.TclError:
            continue
        if len(achados) >= limite:
            break
    rel.verifica(not achados, f"{rotulo}: nada cortado", "; ".join(achados))


def principal():
    app, root, erros, msgs = A.abrir_app(cs, TMP, ITENS)
    msgs.resposta = True
    app._pedir_senha = lambda *a, **k: None
    app._pedir_texto = lambda *a, **k: None
    try:
        A.bombear(root, 0.6)
        base = assinatura(app)
        rel.secao("A) regioes fixas ao escolher cada item")
        for r in list(app.cofre.registros):
            app.tree.selection_set(r["id"])
            A.bombear(root, 0.45)
            comparar(app, base, f"item '{r['servico'][:18]}'")
            cortes(app.frame, f"detalhe de '{r['servico'][:18]}'")
        rel.secao("A) grupos, pessoas, busca, lista vazia, ordem")
        for iid in list(app.lateral.get_children()):
            app.lateral.selection_set(iid)
            A.bombear(root, 0.4)
            comparar(app, base, f"grupo {iid}")
            cortes(app.frame, f"grupo {iid}")
        app.lateral.selection_set("__todos__")
        for iid in list(app.lateral_pessoas.get_children()):
            app.lateral_pessoas.selection_set(iid)
            A.bombear(root, 0.4)
            comparar(app, base, f"pessoa {iid}")
            cortes(app.frame, f"pessoa {iid}")
        for texto in ("zzzz-nao-existe", "a", "", "Banco"):
            app.busca.set(texto)
            A.bombear(root, 0.7)
            comparar(app, base, f"busca {texto!r}")
            cortes(app.frame, f"busca {texto!r}")
        for _ in range(2):
            app._btn_ordem.invoke()
            A.bombear(root, 0.3)
            comparar(app, base, "botao de ordem")
        sobras = erros.pegar()
        rel.verifica(not sobras, "nenhuma excecao do Tk nas interacoes", sobras[0] if sobras else "")

        rel.secao("B) tamanho minimo da janela e todos os temas")
        for tema in TEMAS:
            cs._definir_tema(tema)
            app.tema = tema
            cs.aplicar_tema(root)
            app.tela_principal()
            A.bombear(root, 0.6)
            for r in app.cofre.registros[:3] + app.cofre.registros[3:4]:
                app.tree.selection_set(r["id"])
                A.bombear(root, 0.4)
                cortes(app.frame, f"[{tema}] '{r['servico'][:14]}'")
            b2 = assinatura(app)
            for r in app.cofre.registros:
                app.tree.selection_set(r["id"])
                A.bombear(root, 0.35)
                comparar(app, b2, f"[{tema}] escolher '{r['servico'][:14]}'")
        mw, mh = root.minsize()
        root.geometry(f"{mw}x{mh}")
        A.bombear(root, 0.8)
        for r in app.cofre.registros:
            app.tree.selection_set(r["id"])
            A.bombear(root, 0.4)
            cortes(app.frame, f"janela minima {mw}x{mh}, '{r['servico'][:14]}'")
        root.geometry("1500x940")
        A.bombear(root, 0.6)

        rel.secao("C) dialogos")
        app.tree.selection_set(app.cofre.registros[0]["id"])
        for rot, _i, func in [it for it in app._menu_mais.itens if isinstance(it, tuple)]:
            tam = []

            def medir(janelas, acc=tam):
                for j in janelas:
                    j.update_idletasks()
                    acc.append((j.winfo_width(), j.winfo_height(), j.winfo_rootx(), j.winfo_rooty()))
                    cortes(j, f"dialogo '{rot}'")
            _t, erro = A.chamar_e_fechar(app, func, 0.8, durante=medir)
            rel.verifica(erro is None, f"menu '{rot}' abre sem excecao", repr(erro))
            if tam:
                tam2 = []
                A.chamar_e_fechar(app, func, 0.8, durante=lambda js, acc=tam2: acc.extend(
                    (j.winfo_width(), j.winfo_height(), j.winfo_rootx(), j.winfo_rooty()) for j in js))
                rel.verifica(not tam2 or tam2[0][:2] == tam[0][:2], f"dialogo '{rot}': abre sempre com o mesmo tamanho",
                             f"{tam[0][:2]} e {tam2[0][:2] if tam2 else '-'}")
        # Aparencia: escolher outra opcao nao muda o dialogo
        antes = set(A.toplevels(root))
        app.dialogo_aparencia()
        A.bombear(root, 0.4)
        d = next((t for t in A.toplevels(root) if t not in antes), None)
        if d is not None:
            m0 = (d.winfo_width(), d.winfo_height(), d.winfo_rootx(), d.winfo_rooty())
            for rb in [w for w in A.todos(d) if w.winfo_class() == "TRadiobutton"]:
                rb.invoke()
                A.bombear(root, 0.12)
                m = (d.winfo_width(), d.winfo_height(), d.winfo_rootx(), d.winfo_rooty())
                rel.verifica(m == m0, f"Aparencia: escolher '{A.texto_de(rb)}' nao muda tamanho nem posicao do dialogo", f"{m0} -> {m}")
            d.destroy()
        # Formulario Novo item
        antes = set(A.toplevels(root))
        app.novo()
        A.bombear(root, 0.6)
        d = next((t for t in A.toplevels(root) if t not in antes), None)
        rel.verifica(d is not None, "Novo item abre", f"cofre_aberto={app.cofre is not None}")
        if d is not None:
            m0 = (d.winfo_width(), d.winfo_rootx(), d.winfo_rooty())
            h0 = d.winfo_height()
            cortes(d, "Novo item (inicial)")
            # credenciais extras: um clique em cada botao da faixa "ADICIONAR AO ITEM" (nao ha mais seletor nem "Mostrar" geral)
            etapas = ["＋ Senha extra", "＋ PIN", "＋ Chave / token", "＋ Nº da conta", "＋ Agência", "＋ Códigos de recuperação"]
            for rotulo in etapas:
                botao = A.achar_botao(d, rotulo)
                rel.verifica(botao is not None, f"Novo item: existe o botao '{rotulo}'")
                if botao is None:
                    continue
                botao.invoke()
                A.bombear(root, 0.3)
                m = (d.winfo_width(), d.winfo_rootx(), d.winfo_rooty())
                rel.verifica(mesmo_lugar(d, m0, m), f"Novo item: adicionar '{rotulo}' nao muda largura nem posicao", f"{m0} -> {m}")
                cortes(d, f"Novo item + {rotulo}")
            h1 = d.winfo_height()
            if h1 != h0:
                rel.aviso(f"Novo item: a altura mudou de {h0} para {h1} ao adicionar credenciais (esperado: acompanha o conteudo)")
            rel.verifica(d.winfo_width() <= root.winfo_width() and d.winfo_height() <= root.winfo_height(),
                         "Novo item: com tudo aberto cabe dentro da janela principal",
                         f"{d.winfo_width()}x{d.winfo_height()} / {root.winfo_width()}x{root.winfo_height()}")
            rel.verifica(not any(w.winfo_class() == "TCheckbutton" and A.texto_de(w) == "Mostrar" for w in A.todos(d)),
                         "Novo item: nao existe mais o 'Mostrar' geral (cada campo tem o seu olho)")
            m_final = (d.winfo_width(), d.winfo_rootx(), d.winfo_rooty())   # tamanho/posicao com tudo aberto: o olho nao pode muda-los
            olhos = [w for w in A.todos(d) if w.winfo_class() == "TButton" and A.texto_de(w) == "👁" and w.winfo_ismapped()]
            rel.verifica(len(olhos) >= 5, "Novo item: cada campo secreto tem o seu olho", str(len(olhos)))
            for olho in olhos:
                for _ in range(2):
                    olho.invoke()
                    A.bombear(root, 0.15)
                    m = (d.winfo_width(), d.winfo_rootx(), d.winfo_rooty())
                    rel.verifica(mesmo_lugar(d, m0, m) or m == m_final, "Novo item: mostrar/ocultar um segredo nao mexe na janela", f"{m0} -> {m}")
                    cortes(d, "Novo item com um campo a mostra")
            d.destroy()
        rel.verifica(not erros.pegar(), "nenhuma excecao do Tk no teste inteiro")
    finally:
        A.fechar_app(cs, app)


if __name__ == "__main__":
    principal()
    sys.exit(rel.fim())
