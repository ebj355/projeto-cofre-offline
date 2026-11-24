# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Trocar cores e aparencia do cofre: depois de CADA troca, tudo precisa continuar respondendo.

Defeito relatado: ao trocar as cores/aparencia, funcoes do cofre param de funcionar.

O que este teste faz (tudo pela tela de verdade: menu, "Aparencia e cores", botao "Aplicar"):
  A) paletas: todas tem as mesmas chaves; toda chave de cor usada no codigo existe em TODA paleta (uma chave que
     falta num tema e um KeyError no meio de uma tela); contraste minimo de leitura;
  B) abertura: com cada tema ja salvo, o programa abre, a tela de desbloqueio esta no tema certo, a senha digitada
     na tela destrava e a tela principal funciona;
  C) transicoes: de CADA tema para CADA outro (30 pares com 6 temas). Apos cada troca: nenhuma excecao do Tk,
     nenhuma cor/icone do tema anterior sobrando, preferencia gravada, filtros/busca/selecao preservados e as
     funcoes da tela principal respondem (lista, busca, grupo, ordem, selecionar, Novo item, Editar);
  D) por tema: TODOS os itens do menu "..." e todos os botoes do cabecalho abrem e fecham sem erro e sem cor
     de outro tema; bloquear e desbloquear de novo;
  E) rajada: 5 trocas seguidas sem esperar a tela terminar (duplo clique em "Aplicar");
  F) preferencia corrompida/desconhecida: o programa abre no tema padrao em vez de cair.

COFRE_TEMAS_RAPIDO=1 troca o item C por um ciclo simples (cada tema -> proximo) para diagnostico rapido.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _apoio_gui_novos as A          # noqa: E402

TMP = A.preparar("cofre_gui_temas_", limite_segundos=1500)
cs = A.importar_cofre()
import tkinter as tk                  # noqa: E402
import tkinter.ttk as ttk             # noqa: E402,F401

rel = A.Relatorio("Temas: trocar cores/aparencia e conferir que todas as funcoes continuam respondendo")
RAPIDO = os.environ.get("COFRE_TEMAS_RAPIDO") == "1"
TEMAS = list(cs.PALETAS)
NEUTRAS = {(255, 255, 255), (0, 0, 0), (17, 24, 39)}      # branco, preto e o texto escuro de _texto_contraste

ITENS = [
    dict(servico="Banco Azul", login="ana@exemplo.com", senha="Abc-123-xyz-987-Q", grupo="Bancos", pessoa=""),
    dict(servico="Instagram", login="ana", senha="fraca", grupo="Redes sociais", pessoa=""),
    dict(servico="Netflix", login="pai@exemplo.com", senha="Netflix-Senha-Longa-2026!", grupo="Streaming", pessoa="Pai"),
    dict(servico="Cartao Loja", login="mae", senha="Cartao-Mae-9988-xx", grupo="Compras", pessoa="Mae",
         pin="1234", numero_conta="12345-6", agencia="0001"),
]


# ----------------------------------------------------------------------------------------------------------------
# A) paletas
# ----------------------------------------------------------------------------------------------------------------
def teste_paletas():
    rel.secao("A) paletas: chaves, uso no codigo e contraste")
    rel.info(f"{len(TEMAS)} temas: {', '.join(TEMAS)}")
    chaves = [set(cs._cores_da_paleta(t)) for t in TEMAS]
    comuns = set.intersection(*chaves)
    todas = set.union(*chaves)
    rel.verifica(todas == comuns, "todas as paletas tem exatamente as mesmas chaves",
                 f"faltam em algum tema: {sorted(todas - comuns)}")
    fonte = open(os.path.join(A.RAIZ, "cofre_senhas.py"), encoding="utf-8").read()
    usadas = set(re.findall(r'\bCORES\[\s*"(\w+)"\s*\]', fonte)) | set(re.findall(r'\bC\[\s*"(\w+)"\s*\]', fonte))
    sem_chave = sorted(k for k in usadas if k not in comuns)
    rel.verifica(not sem_chave, f"toda chave de cor usada no codigo ({len(usadas)}) existe em todos os temas",
                 f"nao existem nas paletas: {sem_chave}")
    for t in TEMAS:
        c = cs._cores_da_paleta(t)
        for chave in ("fundo", "sup", "campo", "prim", "texto", "prim_fg", "perigo", "ok", "alerta"):
            rel.verifica(bool(A.hex_para_rgb(c[chave])), f"{t}: cor '{chave}' e um #rrggbb valido ({c[chave]})")
        # leitura essencial: reprova. Cores de apoio: so avisa (decisao de design, nao quebra o cofre).
        obrigatorias = (("texto", "fundo", 4.5), ("texto", "sup", 4.5), ("prim_fg", "prim", 3.0))
        desejaveis = (("suave", "fundo", 4.5), ("fraco", "fundo", 3.0), ("ok", "ok_fundo", 3.0),
                      ("alerta", "alerta_fundo", 3.0), ("perigo", "perigo_fundo", 3.0), ("prim_txt", "sup", 3.0))
        for fg, bg, minimo in obrigatorias:
            r = cs._contraste_wcag(c[fg], c[bg])
            rel.verifica(r >= minimo, f"{t}: contraste {fg} sobre {bg} >= {minimo}", f"{r:.2f}")
        for fg, bg, minimo in desejaveis:
            r = cs._contraste_wcag(c[fg], c[bg])
            if r < minimo:
                rel.aviso(f"{t}: contraste {fg} sobre {bg} = {r:.2f} (desejavel >= {minimo})")
    # cores distintas o bastante entre fundo e superficie, senao os cartoes somem
    for t in TEMAS:
        c = cs._cores_da_paleta(t)
        rel.verifica(c["fundo"] != c["sup"] and c["sup"] != c["sup3"], f"{t}: fundo, superficie e realce sao distintos")


# ----------------------------------------------------------------------------------------------------------------
# utilidades de tela
# ----------------------------------------------------------------------------------------------------------------
# cores FIXAS do medidor de forca da senha: nao pertencem a nenhum tema, entao nao sao "sobra" de tema antigo
FIXAS = {A.hex_para_rgb(c) for c in getattr(cs.App, "_CORES_FORCA", ())}


def velhas_para(atual, outros):
    return A.cores_so_do_outro(cs, atual, outros) - NEUTRAS - FIXAS


def aplicar_pela_tela(app, nome, esperar=True):
    """Abre 'Aparencia e cores', escolhe o tema e aperta Aplicar, como o usuario."""
    root = app.root
    antes = set(A.toplevels(root))
    app.dialogo_aparencia()
    import time
    fim = time.time() + 4.0                  # a janela abre com atraso em maquina ocupada: espera em vez de 0,25 s fixos
    novos = []
    while not novos and time.time() < fim:
        A.bombear(root, 0.1)
        novos = [t for t in A.toplevels(root) if t not in antes]
    if not novos:
        return False, "o dialogo 'Aparencia e cores' nao abriu"
    d = novos[0]
    rb = next((w for w in A.todos(d) if w.winfo_class() == "TRadiobutton" and A.texto_de(w) == nome), None)
    if rb is None:
        return False, f"o dialogo nao tem a opcao '{nome}'"
    root.setvar(str(rb.cget("variable")), nome)
    ap = A.achar_botao(d, "Aplicar")
    if ap is None:
        return False, "o dialogo nao tem o botao 'Aplicar'"
    ap.invoke()
    if esperar:
        A.bombear(root, 0.35)
    return True, ""


def conferir_estado(app, erros, nome, rotulo, outros, onde=None):
    """Itens que valem para QUALQUER tela logo depois de uma troca/abertura."""
    root = app.root
    rel.verifica(cs.TEMA_ATUAL == nome and app.tema == nome, f"{rotulo}: tema ativo = {nome}",
                 f"global={cs.TEMA_ATUAL} app={app.tema}")
    rel.verifica(dict(cs.CORES) == cs._cores_da_paleta(nome), f"{rotulo}: CORES = paleta de '{nome}'")
    rel.verifica(cs._carregar_preferencia_tema() == nome, f"{rotulo}: preferencia salva em disco = {nome}")
    achados = A.varrer_cores_antigas(cs, onde or root, velhas_para(nome, outros))
    rel.verifica(not achados, f"{rotulo}: nenhuma cor/icone de OUTRO tema sobrando na tela", "; ".join(achados))
    sobras = erros.pegar()
    rel.verifica(not sobras, f"{rotulo}: nenhuma excecao do Tk", sobras[0] if sobras else "")


def itens_visiveis(app):
    return set(app.tree.get_children())


def sondar_leve(app, erros, msgs, rotulo, outros, nome):
    """Funcoes da tela principal, uma a uma. Cada verificacao diz qual funcao parou."""
    root = app.root
    cof = app.cofre
    todos_ids = {r["id"] for r in cof.registros}
    A.bombear(root, 0.15)
    rel.verifica(itens_visiveis(app) == todos_ids, f"{rotulo}: a lista mostra os {len(todos_ids)} itens",
                 f"mostra {len(itens_visiveis(app))}")
    # selecionar um item -> painel de detalhes
    alvo = next(r for r in cof.registros if r["servico"] == "Netflix")
    app.tree.selection_set(alvo["id"])
    A.bombear(root, 0.4)
    textos = " | ".join(A.todos_os_textos(app.detalhe)).lower()
    rel.verifica("netflix" in textos, f"{rotulo}: selecionar um item mostra o detalhe dele")
    # busca
    app.busca.set("insta")
    A.bombear(root, 0.7)
    achados = itens_visiveis(app)
    esperado = {r["id"] for r in cof.registros if r["servico"] == "Instagram"}
    rel.verifica(achados == esperado, f"{rotulo}: a busca filtra a lista", f"{len(achados)} itens")
    app.busca.set("")
    A.bombear(root, 0.7)
    rel.verifica(itens_visiveis(app) == todos_ids, f"{rotulo}: limpar a busca devolve todos os itens")
    # grupo na barra lateral
    grupos = [i for i in app.lateral.get_children() if i not in ("__todos__", "__sem__", "__atencao__")]
    rel.verifica(bool(grupos), f"{rotulo}: a barra lateral lista os grupos", str(app.lateral.get_children()))
    if grupos:
        g = next((i for i in grupos if i[2:] == "Bancos"), grupos[0])
        app.lateral.selection_set(g)
        A.bombear(root, 0.4)
        so_grupo = {r["id"] for r in cof.registros if r.get("grupo") == g[2:]}
        rel.verifica(itens_visiveis(app) == so_grupo, f"{rotulo}: escolher o grupo '{g[2:]}' filtra a lista",
                     f"{len(itens_visiveis(app))} de {len(so_grupo)}")
        app.lateral.selection_set("__todos__")
        A.bombear(root, 0.4)
        rel.verifica(itens_visiveis(app) == todos_ids, f"{rotulo}: voltar para 'Todos' mostra tudo")
    # ordem A->Z / Z->A
    antes_txt = A.texto_de(app._btn_ordem)
    app._btn_ordem.invoke()
    A.bombear(root, 0.2)
    rel.verifica(A.texto_de(app._btn_ordem) != antes_txt, f"{rotulo}: botao de ordem alterna A->Z / Z->A")
    app._btn_ordem.invoke()
    A.bombear(root, 0.2)
    # Novo item e Editar: abrem, estao no tema, e fecham
    app.tree.selection_set(alvo["id"])
    A.bombear(root, 0.3)
    for nome_acao, funcao, titulo in (("Novo item", app._btn_novo.invoke, "Novo item"),
                                      ("Editar", app.editar, "Editar item")):
        achados_cor = []

        def inspecionar(janelas, acumulador=achados_cor):
            for j in janelas:
                acumulador.extend(A.varrer_cores_antigas(cs, j, velhas_para(nome, outros)))
        titulos, erro = A.chamar_e_fechar(app, funcao, 0.7, durante=inspecionar)
        rel.verifica(erro is None and titulo in titulos, f"{rotulo}: '{nome_acao}' abre o formulario '{titulo}'",
                     f"titulos={titulos} erro={erro!r}")
        rel.verifica(not achados_cor, f"{rotulo}: formulario '{titulo}' sem cores de outro tema", "; ".join(achados_cor))
        A.bombear(root, 0.1)
    rel.verifica(not [t for t in A.toplevels(root)], f"{rotulo}: nenhum dialogo ficou aberto para tras")
    sobras = erros.pegar()
    rel.verifica(not sobras, f"{rotulo}: nenhuma excecao do Tk nas funcoes", sobras[0] if sobras else "")


def sondar_completo(app, erros, msgs, rotulo, outros, nome):
    """Todos os botoes do cabecalho e TODOS os itens do menu '...'."""
    root = app.root
    # as perguntas de senha/arquivo viram cancelamento: nada e alterado no cofre de teste
    app._pedir_senha = lambda *a, **k: None
    app._pedir_texto = lambda *a, **k: None
    for nome_btn in ("_btn_novo", "_btn_mais", "_btn_bloquear", "_btn_ajuda", "_btn_ordem"):
        b = getattr(app, nome_btn, None)
        ok = b is not None and b.winfo_exists() and str(b.cget("state")) != "disabled"
        rel.verifica(ok, f"{rotulo}: botao {nome_btn[5:]} existe e esta habilitado")
        if ok:
            rel.verifica(b.winfo_ismapped() and b.winfo_width() > 8 and b.winfo_height() > 8,
                         f"{rotulo}: botao {nome_btn[5:]} esta visivel e com tamanho")
    # menu "..." aberto: mostra todos os itens e esta no tema
    m = app._menu_mais.abrir(app._btn_mais)
    A.bombear(root, 0.3)
    rotulos_menu = [it for it in app._menu_mais.itens if isinstance(it, tuple)]
    achados = A.varrer_cores_antigas(cs, m, velhas_para(nome, outros))
    texto_menu = " | ".join(A.todos_os_textos(m))
    faltam = [r for r, _, _ in rotulos_menu if r not in texto_menu]
    rel.verifica(not faltam, f"{rotulo}: o menu '...' mostra os {len(rotulos_menu)} itens", str(faltam))
    rel.verifica(not achados, f"{rotulo}: menu '...' sem cores de outro tema", "; ".join(achados))
    try:
        m.destroy()
    except tk.TclError:
        pass
    A.bombear(root, 0.1)
    # cada item do menu
    for rot, _icone, func in rotulos_menu:
        achados_d = []

        def inspecionar(janelas, acumulador=achados_d):
            for j in janelas:
                acumulador.extend(A.varrer_cores_antigas(cs, j, velhas_para(nome, outros)))
        titulos, erro = A.chamar_e_fechar(app, func, 0.8, durante=inspecionar)
        rel.verifica(erro is None, f"{rotulo}: menu '{rot}' executa sem excecao", repr(erro))
        rel.verifica(not achados_d, f"{rotulo}: dialogo de '{rot}' sem cores de outro tema", "; ".join(achados_d))
        sobras = erros.pegar()
        rel.verifica(not sobras, f"{rotulo}: menu '{rot}' sem excecao no Tk", sobras[0] if sobras else "")
    rel.verifica(app.cofre is not None, f"{rotulo}: o cofre continua aberto depois de usar todo o menu")
    senha_ok = app.cofre.confere_senha(A.SENHA) if app.cofre is not None else False
    rel.verifica(senha_ok, f"{rotulo}: a senha mestra do cofre NAO foi alterada pelos testes do menu")


def bloquear_e_desbloquear(app, erros, nome, rotulo, outros):
    """Bloquear -> tela de desbloqueio no tema -> digitar a senha NA TELA -> tela principal de volta."""
    root = app.root
    app.bloquear()
    A.bombear(root, 0.6)
    rel.verifica(app.cofre is None, f"{rotulo}: 'Bloquear' fecha o cofre")
    achados = A.varrer_cores_antigas(cs, app.frame, velhas_para(nome, outros))
    rel.verifica(not achados, f"{rotulo}: tela de desbloqueio sem cores de outro tema", "; ".join(achados))
    campo = next((w for w in A.todos(app.frame) if w.winfo_class() == "TEntry" and str(w.cget("show"))), None)
    botao = A.achar_botao(app.frame, "Desbloquear")
    rel.verifica(campo is not None and botao is not None, f"{rotulo}: tela de desbloqueio tem campo de senha e botao")
    if campo is None or botao is None:
        return False
    campo.insert(0, A.SENHA)
    botao.invoke()
    import time
    fim = time.time() + 40
    while app.cofre is None and time.time() < fim:
        A.bombear(root, 0.1)
    rel.verifica(app.cofre is not None, f"{rotulo}: a senha digitada na tela destrava o cofre")
    A.bombear(root, 0.6)
    ok = app.cofre is not None and hasattr(app, "tree") and itens_visiveis(app) == {r["id"] for r in app.cofre.registros}
    rel.verifica(ok, f"{rotulo}: apos desbloquear, a lista mostra os itens no tema {nome}")
    sobras = erros.pegar()
    rel.verifica(not sobras, f"{rotulo}: bloquear/desbloquear sem excecao", sobras[0] if sobras else "")
    return app.cofre is not None


# ----------------------------------------------------------------------------------------------------------------
# B) abertura com cada tema salvo
# ----------------------------------------------------------------------------------------------------------------
def teste_abertura():
    rel.secao("B) abrir o programa com cada tema ja salvo (da abertura ate os botoes)")
    for nome in TEMAS:
        outros = [t for t in TEMAS if t != nome]
        cs._salvar_preferencia_tema(nome)
        caminho, cof = A.criar_cofre_de_teste(cs, TMP, ITENS)
        cof.fechar()
        root = tk.Tk()
        root.withdraw()
        erros = A.RecolhedorDeErros(root)
        app = cs.App(root, caminho)
        msgs = A.Mensagens(cs)
        root.report_callback_exception = erros._registrar
        try:
            cs.revelar_janela(root)
        except Exception:
            root.deiconify()
        A.bombear(root, 0.5)
        rot = f"[abre em {nome}]"
        conferir_estado(app, erros, nome, rot, outros)
        # destrava pela tela
        campo = next((w for w in A.todos(app.frame) if w.winfo_class() == "TEntry" and str(w.cget("show"))), None)
        botao = A.achar_botao(app.frame, "Desbloquear")
        rel.verifica(campo is not None and botao is not None, f"{rot}: tela de desbloqueio completa")
        if campo is not None and botao is not None:
            campo.insert(0, A.SENHA)
            botao.invoke()
            import time
            fim = time.time() + 40
            while app.cofre is None and time.time() < fim:
                A.bombear(root, 0.1)
        rel.verifica(app.cofre is not None, f"{rot}: a senha digitada destrava o cofre")
        if app.cofre is not None:
            A.bombear(root, 0.7)
            conferir_estado(app, erros, nome, rot + " principal", outros)
            sondar_leve(app, erros, msgs, rot, outros, nome)
            sondar_completo(app, erros, msgs, rot, outros, nome)
        A.fechar_app(cs, app)


# ----------------------------------------------------------------------------------------------------------------
# C, D, E) trocas na mesma sessao
# ----------------------------------------------------------------------------------------------------------------
def teste_trocas():
    rel.secao("C) trocar de CADA tema para CADA outro, pela tela 'Aparencia e cores'")
    cs._salvar_preferencia_tema(TEMAS[0])
    app, root, erros, msgs = A.abrir_app(cs, TMP, ITENS)
    msgs.resposta = True
    try:
        if RAPIDO:
            pares = [(TEMAS[i], TEMAS[(i + 1) % len(TEMAS)]) for i in range(len(TEMAS))]
        else:
            pares = [(a, b) for a in TEMAS for b in TEMAS if a != b]
        ja_completo = set()
        # estado que precisa sobreviver a trocas: item selecionado, busca vazia e grupo
        for a, b in pares:
            ok, porque = aplicar_pela_tela(app, a)
            rel.verifica(ok, f"preparo: ir para '{a}'", porque)
            if not ok:
                continue
            erros.pegar()
            alvo = next(r for r in app.cofre.registros if r["servico"] == "Banco Azul")
            app.tree.selection_set(alvo["id"])
            A.bombear(root, 0.3)
            grupo_antes = app.filtro_grupo.get()
            rot = f"[{a} -> {b}]"
            ok, porque = aplicar_pela_tela(app, b)
            rel.verifica(ok, f"{rot}: Aplicar funciona", porque)
            if not ok:
                continue
            outros = [t for t in TEMAS if t != b]
            conferir_estado(app, erros, b, rot, [a])
            sel = app.tree.selection()
            rel.verifica(sel == (alvo["id"],), f"{rot}: o item selecionado continua selecionado", str(sel))
            rel.verifica(app.filtro_grupo.get() == grupo_antes, f"{rot}: o filtro de grupo foi preservado")
            sondar_leve(app, erros, msgs, rot, [a], b)
            if b not in ja_completo:
                ja_completo.add(b)
                sondar_completo(app, erros, msgs, rot, [a], b)
        rel.secao("D) bloquear e desbloquear depois das trocas")
        final = TEMAS[-1]
        aplicar_pela_tela(app, final)
        erros.pegar()
        if bloquear_e_desbloquear(app, erros, final, f"[apos trocas em {final}]", [t for t in TEMAS if t != final]):
            sondar_leve(app, erros, msgs, f"[desbloqueado em {final}]", [t for t in TEMAS if t != final], final)
        rel.secao("E) rajada: 5 trocas seguidas sem esperar a tela terminar")
        sequencia = [TEMAS[i % len(TEMAS)] for i in (1, 3, 0, 2, 4)]
        for nome in sequencia:
            ok, porque = aplicar_pela_tela(app, nome, esperar=False)
            rel.verifica(ok, f"rajada: aplicar '{nome}'", porque)
        A.bombear(root, 1.2)
        ultimo = sequencia[-1]
        conferir_estado(app, erros, ultimo, "[rajada]", [t for t in TEMAS if t != ultimo])
        sondar_leve(app, erros, msgs, "[rajada]", [t for t in TEMAS if t != ultimo], ultimo)
        sondar_completo(app, erros, msgs, "[rajada]", [t for t in TEMAS if t != ultimo], ultimo)
        # nenhuma imagem do Tk pode ter sumido: se sumiu, o desenho de botao/icone falha com "image doesn't exist"
        try:
            imagens = root.tk.call("image", "names")
            rel.verifica(len(imagens) > 20, f"rajada: imagens do tema continuam existindo ({len(imagens)})")
        except tk.TclError as ex:
            rel.verifica(False, "rajada: consultar imagens do Tk", str(ex))
        # a troca nao pode vazar widgets: depois de tudo, so a janela principal
        rel.verifica(not A.toplevels(root), "rajada: nenhum dialogo sobrando")
    finally:
        A.fechar_app(cs, app)


# ----------------------------------------------------------------------------------------------------------------
# F) preferencia corrompida
# ----------------------------------------------------------------------------------------------------------------
def teste_preferencia_ruim():
    rel.secao("F) preferencia de aparencia corrompida ou desconhecida")
    caminho_pref = cs._caminho_preferencias()
    os.makedirs(os.path.dirname(caminho_pref), exist_ok=True)
    casos = {
        "JSON quebrado": "{nao e json",
        "lista no lugar de objeto": "[1, 2, 3]",
        "tema que nao existe": json.dumps({"tema": "Verde-Neon-Inexistente"}),
        "tema com tipo errado": json.dumps({"tema": 123}),
        "vazio": "",
        "binario": "\x00\x01\x02\xff",
    }
    for descricao, conteudo in casos.items():
        with open(caminho_pref, "w", encoding="utf-8", errors="ignore") as f:
            f.write(conteudo)
        try:
            tema = cs._carregar_preferencia_tema()
            rel.verifica(tema == cs.TEMA_PADRAO, f"preferencia '{descricao}': volta ao tema padrao", tema)
        except Exception as ex:                # noqa: BLE001
            rel.verifica(False, f"preferencia '{descricao}': nao pode levantar excecao", repr(ex))
    for nome in ("", None, 5, "Inexistente"):
        try:
            cs._salvar_preferencia_tema(nome)
            rel.verifica(False, f"salvar tema invalido {nome!r} deveria ser recusado")
        except ValueError:
            rel.verifica(True, f"salvar tema invalido {nome!r} e recusado")
    with open(caminho_pref, "w", encoding="utf-8") as f:
        f.write("{lixo")
    caminho, cof = A.criar_cofre_de_teste(cs, TMP, ITENS)
    cof.fechar()
    root = tk.Tk()
    root.withdraw()
    erros = A.RecolhedorDeErros(root)
    try:
        app = cs.App(root, caminho)
        A.bombear(root, 0.4)
        rel.verifica(app.tema == cs.TEMA_PADRAO, "abrir o programa com preferencia corrompida usa o tema padrao")
        rel.verifica(not erros.pegar(), "abrir com preferencia corrompida: nenhuma excecao")
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass
        cs.Cofre.executor_salvar = None
    cs._salvar_preferencia_tema(cs.TEMA_PADRAO)
    # a gravacao e atomica: nenhum .tmp sobrando ao lado da preferencia
    sobras = [n for n in os.listdir(os.path.dirname(caminho_pref)) if n.endswith(".tmp")]
    rel.verifica(not sobras, "gravar a preferencia nao deixa arquivo temporario", str(sobras))


if __name__ == "__main__":
    teste_paletas()
    teste_preferencia_ruim()
    teste_abertura()
    teste_trocas()
    sys.exit(rel.fim())
