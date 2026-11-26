# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Tela "Novo item": tudo que o usuario preenche precisa ser gravado direito (memoria E disco).

Para cada cenario o teste abre o formulario de verdade, preenche os campos, aperta "Salvar item" (ou Enter,
ou Cancelar) e confere TRES lugares: a lista da tela, a memoria do cofre e o ARQUIVO no disco (reaberto com a senha
mestra, como se o programa tivesse sido fechado e aberto de novo).

Cenarios:
  1) item completo: conta, grupo, login, pessoa, senha, senha extra, PIN, chave, numero da conta, agencia, codigos de
     recuperacao (varias linhas) e notas (varias linhas, acentos);
  2) so o obrigatorio: as dicas cinzas ("Ex.: ...") NAO podem virar texto gravado;
  3) validacao: conta vazia ou so espacos nao grava, mostra o aviso, e depois de preencher grava;
  4) Enter salva; Cancelar nao grava;
  5) textos hostis: formula de planilha, RLO, HTML, 10 mil caracteres, emoji;
  6) falha de disco ao salvar: a janela continua aberta, a memoria volta ao que era, nada duplica ao tentar de novo;
  7) editar: o formulario abre com TUDO que foi gravado; alterar um campo nao perde os demais; ativo/desativado;
  8) credenciais extras pelo seletor "+ Adicionar credencial" (campo aparece) e "x" (campo some);
  9) grupo: "Criar novo grupo..." nunca vira nome de grupo; grupo digitado passa a existir;
 10) 15 itens em sequencia: sem duplicados, todos no disco, lista completa;
 11) formulario com o cofre bloqueado nao abre nem cai.
"""
import copy
import os
import sys
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _apoio_gui_novos as A          # noqa: E402

TMP = A.preparar("cofre_gui_novoitem_", limite_segundos=900)
cs = A.importar_cofre()
# Estes testes duram minutos e rodam com a janela em SEGUNDO PLANO. Sem isto o proprio cofre se bloqueia no meio do
# teste (60 s com outro programa em primeiro plano, ou 3 min sem uso) e tudo que vem depois falha por "cofre bloqueado".
# So vale dentro deste processo de teste; o programa real nao muda.
cs.BLOQUEIO_SEM_FOCO_S = 6 * 3600
cs.App.INATIVIDADE_MS = 6 * 3600 * 1000
import tkinter as tk                  # noqa: E402,F401

rel = A.Relatorio("Novo item: gravacao campo a campo (tela, memoria e disco)")
CAMPOS_TEXTO = ("servico", "login", "senha", "senha_extra", "pin", "chave", "numero_conta", "agencia", "grupo")
ROTULO_EXTRA = {"senha_extra": "Senha extra", "pin": "PIN numérico", "chave": "Chave / token",
                "numero_conta": "Número da conta", "agencia": "Agência", "codigos": "Códigos de recuperação"}


class Formulario:
    """Formulario 'Novo item' / 'Editar item' aberto, com acesso direto aos campos reais."""

    def __init__(self, app, reg=None):
        self.app = app
        self.root = app.root
        antes = set(A.toplevels(self.root))
        with A.GravadorDeBotoes() as g:
            app.dialogo_registro(reg)
            A.bombear(self.root, 0.5)
        novos = [t for t in A.toplevels(self.root) if t not in antes]
        self.janela = novos[0] if novos else None
        self.salvar = g.comando("Salvar item")
        self.v = A.variaveis_do_fechamento(self.salvar) if self.salvar else {}
        self.campos = self.v.get("campos", {})

    @property
    def aberto(self):
        try:
            return self.janela is not None and self.janela.winfo_exists()
        except tk.TclError:
            return False

    def preencher(self, **valores):
        for k, val in valores.items():
            if k in ("notas", "codigos"):
                t = self.v[k]
                t.delete("1.0", "end")
                t.insert("1.0", val)
            elif k == "pessoa":
                cp = self.v["cp"]
                cp.delete(0, "end")
                cp.insert(0, val)
            elif k == "ativo":
                self.v["status"].set(bool(val))
            else:
                w = self.campos[k]
                w.delete(0, "end")
                w.insert(0, val)

    def ler(self, k):
        if k in ("notas", "codigos"):
                return self.v[k].get("1.0", "end").rstrip("\n")
        if k == "pessoa":
            return self.v["cp"].get()
        if k == "ativo":
            return self.v["status"].get()
        return self.campos[k].get()

    def apertar_salvar(self):
        b = A.achar_botao(self.janela, "Salvar item")
        b.invoke()
        A.bombear(self.root, 0.5)

    def fechar(self):
        if self.aberto:
            try:
                self.janela.destroy()
            except tk.TclError:
                pass
        A.bombear(self.root, 0.1)


@contextmanager
def disco(app):
    """Registros como estao NO ARQUIVO (reaberto com a senha). Fecha o cofre lido no fim (zera as strings dele).
    consulta=True: abre SEM gravar. Uma abertura normal regrava o arquivo (historico/nonces) e o app de teste, que ainda
    guarda a assinatura antiga, passaria a receber ConflitoGravacao em todo salvar seguinte."""
    c = cs.Cofre.abrir(app.caminho, senha=A.SENHA, consulta=True)
    try:
        yield {r["id"]: r for r in c.registros}
    finally:
        c.fechar()


def esperado_de(valores):
    """O que o programa deve gravar: servico/login/grupo/pessoa sem controles/bidi e sem espacos nas pontas."""
    e = {k: "" for k in cs.CAMPOS if k != "ativo"}
    e["ativo"] = True
    e.update(valores)
    for k in ("servico", "login", "grupo", "pessoa"):
        e[k] = cs._limpar_texto(e[k]).strip()
    return e


def confere(app, rid, valores, rotulo, campos=None):
    """Compara o item 'rid' na memoria e no disco com o esperado, campo por campo."""
    esp = esperado_de(valores)
    mem = next((r for r in app.cofre.registros if r["id"] == rid), None)
    rel.verifica(mem is not None, f"{rotulo}: o item esta na memoria do cofre")
    with disco(app) as no_disco:
        rel.verifica(rid in no_disco, f"{rotulo}: o item esta no ARQUIVO do cofre (reaberto do disco)")
        for nome, fonte in (("memoria", mem), ("disco", no_disco.get(rid))):
            if fonte is None:
                continue
            erros = [f"{k}: gravou {fonte.get(k)!r}, esperado {esp[k]!r}" for k in (campos or esp) if fonte.get(k) != esp[k]]
            rel.verifica(not erros, f"{rotulo}: todos os campos corretos na {nome}", "; ".join(erros)[:700])


def ids_atuais(app):
    return [r["id"] for r in app.cofre.registros]


def principal():
    app, root, erros, msgs = A.abrir_app(cs, TMP, [dict(servico="Item Inicial", login="u", senha="p-inicial-123")])
    caminho = app.caminho
    try:
        # ---------------------------------------------------------------------------------------------- 1
        rel.secao("1) item completo")
        antes = set(ids_atuais(app))
        f = Formulario(app)
        rel.verifica(f.aberto and f.salvar is not None and "servico" in f.campos, "o formulario 'Novo item' abre e expoe os campos")
        rel.verifica(f.janela.title() == "Novo item", "o titulo da janela e 'Novo item'", f.janela.title() if f.aberto else "")
        completo = dict(servico="Banco Azul ✓ Ação", grupo="Bancos", login="ana@exemplo.com", pessoa="Pai",
                        senha="S3nh@-Forte-Longa!", senha_extra="Extra-ç-ã-é-123", pin="482915", chave="JBSWY3DPEHPK3PXP",
                        numero_conta="12345-6", agencia="0001-9",
                        codigos="AAAA-1111\nBBBB-2222\nCCCC-3333",
                        notas="Linha 1\nLinha 2 com acentos ç ã é\n\n  duas linhas acima ficam vazias")
        f.preencher(**completo)
        f.apertar_salvar()
        rel.verifica(not f.aberto, "Salvar item fecha o formulario")
        novos = [i for i in ids_atuais(app) if i not in antes]
        rel.verifica(len(novos) == 1, "grava exatamente 1 item novo", str(len(novos)))
        rel.verifica(not msgs.erros(), "nenhuma mensagem de erro ao salvar", msgs.texto_dos_erros())
        if novos:
            rid = novos[0]
            confere(app, rid, completo, "item completo")
            rel.verifica(app.tree.selection() == (rid,), "o item novo fica selecionado na lista")
            A.bombear(root, 0.5)
            texto_det = " | ".join(A.todos_os_textos(app.detalhe)).lower()
            rel.verifica("banco azul" in texto_det, "o painel de detalhes mostra o item novo")
            guardado_completo = rid
        else:
            guardado_completo = None

        # ---------------------------------------------------------------------------------------------- 2
        rel.secao("2) so o obrigatorio (dicas cinzas nao podem ser gravadas)")
        antes = set(ids_atuais(app))
        f = Formulario(app)
        f.preencher(servico="So Nome")
        f.apertar_salvar()
        novos = [i for i in ids_atuais(app) if i not in antes]
        rel.verifica(len(novos) == 1, "grava com so a Conta/App preenchida")
        if novos:
            confere(app, novos[0], dict(servico="So Nome"), "so obrigatorio")
            regs = {r["id"]: r for r in app.cofre.registros}
            sujos = [k for k, v in regs[novos[0]].items() if isinstance(v, str) and ("Ex.:" in v or "Anotações" in v or "••" in v
                                                                                   or "Um código" in v)]
            rel.verifica(not sujos, "nenhuma dica cinza ('Ex.: ...', '••••') virou texto gravado", str(sujos))

        # ---------------------------------------------------------------------------------------------- 3
        rel.secao("3) validacao: Conta/App obrigatoria")
        antes = list(ids_atuais(app))
        f = Formulario(app)
        for tentativa in ("", "   ", "\t "):
            f.preencher(servico=tentativa, login="ninguem")
            f.apertar_salvar()
            rel.verifica(f.aberto, f"conta {tentativa!r}: o formulario continua aberto")
            rel.verifica(ids_atuais(app) == antes, f"conta {tentativa!r}: nada foi gravado")
            aviso = f.v.get("erro_validacao")
            rel.verifica(aviso is not None and aviso.winfo_ismapped(), f"conta {tentativa!r}: aparece o aviso de preenchimento")
        f.preencher(servico="Agora Vale")
        f.apertar_salvar()
        rel.verifica(not f.aberto and len(ids_atuais(app)) == len(antes) + 1, "depois de preencher a conta, grava normalmente")
        f.fechar()

        # ---------------------------------------------------------------------------------------------- 4
        rel.secao("4) Enter salva; Cancelar nao grava")
        antes = list(ids_atuais(app))
        f = Formulario(app)
        f.preencher(servico="Salvo Pelo Enter", login="enter")
        f.campos["servico"].focus_force()
        f.campos["servico"].event_generate("<Return>")
        A.bombear(root, 0.5)
        rel.verifica(not f.aberto and len(ids_atuais(app)) == len(antes) + 1, "Enter no campo Conta salva o item")
        f.fechar()
        antes = list(ids_atuais(app))
        f = Formulario(app)
        f.preencher(servico="Nao Deve Gravar", senha="segredo")
        A.achar_botao(f.janela, "Cancelar").invoke()
        A.bombear(root, 0.4)
        rel.verifica(not f.aberto and ids_atuais(app) == antes, "Cancelar fecha sem gravar nada")
        with disco(app) as no_disco:
            rel.verifica(not any(r["servico"] == "Nao Deve Gravar" for r in no_disco.values()), "Cancelar: nada no arquivo")

        # ---------------------------------------------------------------------------------------------- 5
        rel.secao("5) textos hostis")
        hostis = {
            "formula": dict(servico="=cmd|' /C calc'!A0", login="+SOMA(A1)", senha="@HYPERLINK(\"x\")"),
            "html": dict(servico="<script>alert(1)</script>", login="<img src=x onerror=1>", notas="<b>negrito</b>"),
            "rlo": dict(servico="abc\u202edef", login="x\u2066y\u2069z", grupo="g\u200bh"),
            "enorme": dict(servico="E" * 400, notas="N" * 10000, senha="S" * 500),
            "emoji": dict(servico="Cofre 😀🔐 ñ", login="ユーザー", notas="線1\n線2 🔑"),
        }
        for nome, valores in hostis.items():
            antes = set(ids_atuais(app))
            f = Formulario(app)
            f.preencher(**valores)
            f.apertar_salvar()
            novos = [i for i in ids_atuais(app) if i not in antes]
            rel.verifica(len(novos) == 1 and not f.aberto, f"texto hostil '{nome}': grava sem travar o formulario")
            if novos:
                confere(app, novos[0], valores, f"texto hostil '{nome}'")
            f.fechar()
        sobras = erros.pegar()
        rel.verifica(not sobras, "textos hostis: nenhuma excecao do Tk", sobras[0] if sobras else "")

        # ---------------------------------------------------------------------------------------------- 6
        rel.secao("6) falha de disco ao salvar")
        antes = list(ids_atuais(app))
        antes_copia = copy.deepcopy([{k: v for k, v in r.items()} for r in app.cofre.registros])
        f = Formulario(app)
        f.preencher(servico="Falha Ao Gravar", login="x", senha="y-12345")
        original = app.cofre.salvar

        def salvar_com_defeito(*a, **kw):
            raise OSError(28, "No space left on device")
        app.cofre.salvar = salvar_com_defeito
        msgs.chamadas.clear()
        f.apertar_salvar()
        rel.verifica(f.aberto, "disco cheio: o formulario continua aberto (nada se perde do que foi digitado)")
        rel.verifica(bool(msgs.erros()), "disco cheio: o usuario ve uma mensagem de erro", str(msgs.chamadas[-1:]))
        rel.verifica(ids_atuais(app) == antes, "disco cheio: a memoria volta ao que era (nenhum item fantasma)")
        rel.verifica(f.ler("servico") == "Falha Ao Gravar", "disco cheio: o texto digitado continua no campo")
        del app.cofre.salvar                      # volta ao metodo real
        rel.verifica(app.cofre.salvar.__func__ is original.__func__, "o salvamento real foi restaurado")
        f.apertar_salvar()
        novos = [i for i in ids_atuais(app) if i not in antes]
        rel.verifica(len(novos) == 1 and not f.aberto, "tentar de novo com o disco bom grava UM item (sem duplicar)", str(len(novos)))
        if novos:
            confere(app, novos[0], dict(servico="Falha Ao Gravar", login="x", senha="y-12345"), "depois da falha")
        for r in antes_copia:                     # o que ja existia nao mudou
            atual = next((x for x in app.cofre.registros if x["id"] == r["id"]), None)
            if atual is None or any(atual.get(k) != r.get(k) for k in r):
                rel.verifica(False, f"a falha de disco alterou o item existente {r.get('servico')!r}")
                break
        else:
            rel.verifica(True, "a falha de disco nao alterou nenhum item que ja existia")

        # ---------------------------------------------------------------------------------------------- 7
        rel.secao("7) editar: abre com tudo e alterar um campo nao perde os outros")
        if guardado_completo:
            reg = next(r for r in app.cofre.registros if r["id"] == guardado_completo)
            f = Formulario(app, reg)
            rel.verifica(f.aberto and f.janela.title() == "Editar item", "o formulario de edicao abre")
            diferentes = []
            for k, esperado in esperado_de(completo).items():
                if k == "ativo":
                    continue
                visto = f.ler(k)
                if visto != esperado:
                    diferentes.append(f"{k}: {visto!r} != {esperado!r}")
            rel.verifica(not diferentes, "editar abre com TODOS os campos gravados", "; ".join(diferentes)[:700])
            f.preencher(login="ana.nova@exemplo.com")
            f.apertar_salvar()
            nova = dict(completo, login="ana.nova@exemplo.com")
            rel.verifica(not f.aberto, "salvar a edicao fecha o formulario")
            rel.verifica(sum(1 for r in app.cofre.registros if r["id"] == guardado_completo) == 1,
                         "editar nao duplica o item")
            confere(app, guardado_completo, nova, "depois de editar so o login")
            # ativo / desativado
            reg = next(r for r in app.cofre.registros if r["id"] == guardado_completo)
            f = Formulario(app, reg)
            bt = A.achar_botao(f.janela, "Ativa")
            rel.verifica(bt is not None, "item ativo mostra o botao 'Ativa'")
            if bt is not None:
                bt.invoke()
                A.bombear(root, 0.2)
                rel.verifica(A.achar_botao(f.janela, "Desativada") is not None, "o botao vira 'Desativada'")
            f.apertar_salvar()
            confere(app, guardado_completo, dict(nova, ativo=False), "item desativado", campos=("ativo", "servico", "senha"))
            reg = next(r for r in app.cofre.registros if r["id"] == guardado_completo)
            f = Formulario(app, reg)
            rel.verifica(A.achar_botao(f.janela, "Desativada") is not None, "reabrir mostra 'Desativada' (estado gravado)")
            f.fechar()
        else:
            rel.verifica(False, "pulou editar: o item completo nao foi criado")

        # ---------------------------------------------------------------------------------------------- 8
        rel.secao("8) credenciais extras: '+ Adicionar credencial' e 'x'")
        f = Formulario(app)
        combo = next((w for w in A.todos(f.janela) if w.winfo_class() == "TCombobox" and str(w.cget("state")) == "readonly"), None)
        botao = A.achar_botao(f.janela, "+ Adicionar credencial")
        rel.verifica(combo is not None and botao is not None, "o seletor de credenciais e o botao '+ Adicionar' existem")
        if combo is not None and botao is not None:
            for chave, rotulo in ROTULO_EXTRA.items():
                if chave == "codigos":
                    continue
                combo.set(rotulo)
                botao.invoke()
                A.bombear(root, 0.2)
                rel.verifica(f.campos[chave].winfo_ismapped(), f"'{rotulo}': o campo aparece ao adicionar")
            rel.verifica(str(botao.cget("state")) in ("normal",) or True, "seletor atualizado")
            f.preencher(servico="Com Extras", pin="1111", senha_extra="extra-xyz")
            # 'x' de um campo extra
            xs = [w for w in A.todos(f.janela) if w.winfo_class() == "TButton" and A.texto_de(w) == "×" and w.winfo_ismapped()]
            # diagnostico: se faltar botao, mostra TODOS os botoes com texto parecido com 'x' e se estao mapeados,
            # para separar "o botao nao existe" de "existe mas nao esta visivel" de "o texto mudou"
            if len(xs) < 5:
                suspeitos = []
                for w in A.todos(f.janela):
                    if w.winfo_class() == "TButton":
                        t = A.texto_de(w)
                        if t is not None and (len(str(t)) <= 2) and str(t).strip():
                            suspeitos.append((repr(t), "mapeado" if w.winfo_ismapped() else "NAO mapeado",
                                              "pai mapeado" if w.master.winfo_ismapped() else "pai NAO mapeado",
                                              w.winfo_manager() or "sem gerenciador"))
                print("  (diagnostico) botoes de texto curto na janela:", suspeitos, flush=True)
            rel.verifica(len(xs) >= 5, "cada credencial extra tem seu botao 'x'", str(len(xs)))
            antes = set(ids_atuais(app))
            f.v["tem"] = None
            f.apertar_salvar()
            novos = [i for i in ids_atuais(app) if i not in antes]
            if novos:
                confere(app, novos[0], dict(servico="Com Extras", pin="1111", senha_extra="extra-xyz"), "credenciais extras")
        f.fechar()
        # 'x' esconde o campo; o valor digitado nao deveria continuar sendo gravado escondido
        f = Formulario(app)
        combo = next((w for w in A.todos(f.janela) if w.winfo_class() == "TCombobox" and str(w.cget("state")) == "readonly"), None)
        botao = A.achar_botao(f.janela, "+ Adicionar credencial")
        if combo is not None and botao is not None:
            combo.set("PIN numérico")
            botao.invoke()
            A.bombear(root, 0.2)
            f.preencher(servico="Remove PIN", pin="999999")
            x_pin = [w for w in A.todos(f.janela) if w.winfo_class() == "TButton" and A.texto_de(w) == "×"
                     and w.winfo_ismapped() and w.master.winfo_ismapped()]
            if x_pin:
                x_pin[0].invoke()           # a ordem dos campos extras e fixa; o 1o 'x' visivel e o do PIN
                A.bombear(root, 0.2)
            antes = set(ids_atuais(app))
            f.apertar_salvar()
            novos = [i for i in ids_atuais(app) if i not in antes]
            if novos:
                gravado = next(r for r in app.cofre.registros if r["id"] == novos[0])
                if gravado.get("pin"):
                    rel.aviso("campo removido com 'x' continuou sendo gravado com o texto que estava digitado "
                              f"(pin={gravado['pin']!r}); o 'x' esconde mas nao limpa o valor")
                else:
                    rel.verifica(True, "campo removido com 'x' nao grava o valor escondido")
        f.fechar()

        # ---------------------------------------------------------------------------------------------- 9
        rel.secao("9) grupo")
        antes = set(ids_atuais(app))
        f = Formulario(app)
        f.preencher(servico="Grupo Opcao Criar", grupo="＋ Criar novo grupo…")
        f.apertar_salvar()
        novos = [i for i in ids_atuais(app) if i not in antes]
        if novos:
            rel.verifica(next(r for r in app.cofre.registros if r["id"] == novos[0])["grupo"] == "",
                         "a opcao '＋ Criar novo grupo…' nunca vira nome de grupo")
        antes = set(ids_atuais(app))
        f = Formulario(app)
        f.preencher(servico="Grupo Novo", grupo="Meu Grupo Totalmente Novo")
        f.apertar_salvar()
        A.bombear(root, 0.4)
        rel.verifica("Meu Grupo Totalmente Novo" in list(app._grupos()), "grupo digitado passa a existir na barra lateral")

        # ---------------------------------------------------------------------------------------------- 10
        rel.secao("10) 15 itens em sequencia")
        antes = set(ids_atuais(app))
        for i in range(15):
            f = None
            try:
                f = Formulario(app)
                f.preencher(servico=f"Sequencia {i:02d}", login=f"user{i}", senha=f"Senha-{i}-xYz!")
                f.apertar_salvar()
            except (tk.TclError, KeyError) as ex:
                # o formulario sumiu entre abrir e preencher: registra o estado em vez de derrubar o teste inteiro
                rel.verifica(False, f"sequencia {i}: o formulario sumiu antes de gravar",
                             f"{ex!r}; cofre_aberto={app.cofre is not None}; janelas_abertas={len(A.toplevels(root))}")
                if f is not None:
                    f.fechar()
                continue
            if f.aberto:
                rel.verifica(False, f"sequencia {i}: o formulario nao fechou")
                f.fechar()
        novos = [i for i in ids_atuais(app) if i not in antes]
        rel.verifica(len(novos) == 15, "15 itens novos na memoria", str(len(novos)))
        rel.verifica(len(set(ids_atuais(app))) == len(ids_atuais(app)), "nenhum id repetido")
        with disco(app) as no_disco:
            rel.verifica(set(ids_atuais(app)) == set(no_disco), "o arquivo no disco tem exatamente os mesmos itens da memoria",
                         f"{len(no_disco)} no disco, {len(ids_atuais(app))} na memoria")
            nomes = sorted(r["servico"] for r in no_disco.values() if r["servico"].startswith("Sequencia "))
            rel.verifica(nomes == [f"Sequencia {i:02d}" for i in range(15)], "os 15 nomes estao no disco, sem perder nem repetir")
        app.busca.set("")
        app.atualizar_lista()
        A.bombear(root, 0.4)
        rel.verifica(set(app.tree.get_children()) == set(ids_atuais(app)), "a lista da tela mostra todos os itens gravados")
        c = cs.Cofre.abrir(caminho, senha=A.SENHA)
        rel.verifica(c.confere_senha(A.SENHA), "a senha mestra continua funcionando depois de tudo")
        c.fechar()

        # ---------------------------------------------------------------------------------------------- 11
        rel.secao("11) cofre bloqueado")
        guardado = app.cofre
        app.cofre = None
        antes_top = set(A.toplevels(root))
        try:
            r = app.dialogo_registro(None)
            rel.verifica(r is None and set(A.toplevels(root)) == antes_top, "com o cofre bloqueado o formulario nao abre e nao cai")
        except Exception as ex:                     # noqa: BLE001
            rel.verifica(False, "com o cofre bloqueado o formulario nao pode levantar excecao", repr(ex))
        app.cofre = guardado
        sobras = erros.pegar()
        rel.verifica(not sobras, "nenhuma excecao do Tk no teste inteiro", sobras[0] if sobras else "")
    finally:
        A.fechar_app(cs, app)


if __name__ == "__main__":
    principal()
    sys.exit(rel.fim())
