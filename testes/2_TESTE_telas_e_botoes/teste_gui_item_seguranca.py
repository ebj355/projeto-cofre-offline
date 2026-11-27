# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Interface: tela "Novo item / Editar item" - nada se perde nem se grava por acidente.

Prova, no formulario de verdade:
  * Enter NAO salva (so passa ao proximo campo); Ctrl+S salva;
  * Cancelar, Esc e o X da janela pedem confirmacao SO quando ha dados digitados;
  * "Remover" uma credencial preenchida pede confirmacao (e, confirmado, apaga de verdade);
  * validacao do nome da conta com texto junto do campo; avisos antes de salvar (sem senha, fraca, duplicado, repetida);
  * grupo automatico pelo nome da conta (e respeito a escolha do usuario);
  * credenciais com UM clique, na ordem de chegada; nao existe "Mostrar" geral; olho por campo que nao some
    enquanto se digita; "Salvar e criar outro"; o formulario nunca passa do tamanho da janela principal.
Fica em testes\\2_TESTE_telas_e_botoes\\ (usa o _apoio_gui_novos.py). Roda no Linux com xvfb-run."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _apoio_gui_novos as ap          # noqa: E402

TMP = ap.preparar("cofre_gui_item_seg_")
cs = ap.importar_cofre()
import tkinter as tk                    # noqa: E402

rel = ap.Relatorio("Novo item: seguranca dos dados, fluxo e tamanho")
FORTE_A = cs.gerar_senha(20, True, True)
FORTE_B = cs.gerar_senha(20, True, True)
FORTE_C = cs.gerar_senha(20, True, True)
app, root, erros, msgs = ap.abrir_app(
    cs, TMP, itens=[{"servico": "Banco Azul", "login": "a@b.com", "senha": FORTE_A}])
app.MOSTRAR_SENHA_MS = 500             # so no teste: o olho volta a esconder em 0,5 s sem mexer


def abrir_form(reg=None):
    """Abre o formulario e devolve a janela dele."""
    app.dialogo_registro(reg)
    ap.bombear(root, 0.5)
    titulo = "Editar item" if reg else "Novo item"
    return next(t for t in ap.toplevels(root) if t.title() == titulo)


def entradas(d):
    """Campos de uma linha visiveis, na ordem: Conta/App, Login, Senha, depois os extras."""
    return [w for w in ap.todos(d) if w.winfo_class() == "TEntry" and w.winfo_ismapped()]


def botao(d, texto, visivel=True):
    """Botao ttk pelo texto exato (por padrao, so os visiveis)."""
    for w in ap.todos(d):
        if w.winfo_class() == "TButton" and ap.texto_de(w) == texto and (w.winfo_ismapped() or not visivel):
            return w
    return None


def rotulo(d, texto):
    """Rotulo visivel pelo texto exato."""
    return next((w for w in ap.todos(d) if w.winfo_class() == "TLabel" and ap.texto_de(w) == texto
                 and w.winfo_ismapped()), None)


def disparar(w, sequencia, keysym="Return", keycode="13"):
    """Executa o bind (do campo, ou da janela) para 'sequencia' sem depender de a tecla chegar pelo sistema de
    janelas: a janela de teste fica sem o foco do teclado e o Tk descarta teclas sinteticas."""
    script = w.bind(sequencia) or w.winfo_toplevel().bind(sequencia)
    if not script:
        return False
    valores = {"#": "0", "b": "0", "f": "0", "h": "0", "k": keycode, "s": "0", "t": "0", "w": "0", "x": "0",
               "y": "0", "A": "{}", "E": "0", "K": keysym, "N": "65293", "W": str(w), "T": "2", "X": "0",
               "Y": "0", "D": "0"}
    try:
        w.tk.eval(re.sub(r"%([#bfhkstwxyAEKNWTXYD])", lambda m: valores[m.group(1)], script))
    except tk.TclError:                  # um bind que devolve "break" faz o eval avisar: o efeito ja aconteceu
        pass
    ap.bombear(root, 0.05)
    return True


def fechar(d):
    """Fecha o formulario do teste sem perguntar nada."""
    try:
        if d.winfo_exists():
            d.destroy()
    except tk.TclError:
        pass
    ap.bombear(root, 0.1)


def existe(d):
    try:
        return bool(d.winfo_exists())
    except tk.TclError:
        return False


def perguntas(titulo):
    """Chamadas de askyesno com este titulo."""
    return [c for c in msgs.chamadas if c[0] == "askyesno" and c[1] and c[1][0] == titulo]


def qtd(nome):
    return sum(1 for r in app.cofre.registros if r["servico"] == nome)


# ---------------------------------------------------------------- Enter, Ctrl+S
rel.secao("Enter nao salva; Ctrl+S salva")
d = abrir_form()
e = entradas(d)
e[0].insert(0, "Loja Enter"); e[1].insert(0, "l@x.com"); e[2].insert(0, FORTE_B)
disparar(e[0], "<Return>")
rel.verifica(qtd("Loja Enter") == 0, "Enter no campo Conta/App NAO salva o item")
rel.verifica(existe(d), "Enter nao fecha o formulario")
disparar(e[2], "<Return>")
rel.verifica(qtd("Loja Enter") == 0, "Enter no campo Senha tambem nao salva")
disparar(e[0], "<Control-s>", "s", "83")
rel.verifica(qtd("Loja Enter") == 1, "Ctrl+S salva o item")
rel.verifica(not existe(d), "depois de salvar o formulario fecha")

# ---------------------------------------------------------------- descartar alteracoes
rel.secao("Cancelar, Esc e X pedem confirmacao so com dados digitados")
d = abrir_form()
msgs.chamadas.clear()
botao(d, "Cancelar").invoke(); ap.bombear(root, 0.1)
rel.verifica(not existe(d) and not perguntas("Descartar alterações?"),
             "Cancelar SEM dados fecha sem perguntar")

d = abrir_form()
entradas(d)[0].insert(0, "Rascunho")
msgs.chamadas.clear(); msgs.resposta = False
botao(d, "Cancelar").invoke(); ap.bombear(root, 0.1)
rel.verifica(existe(d) and len(perguntas("Descartar alterações?")) == 1,
             "Cancelar COM dados pergunta e, respondendo Nao, o formulario continua aberto")
rel.verifica(entradas(d)[0].get() == "Rascunho", "o texto digitado continua la depois de responder Nao")
disparar(d, "<Escape>", "Escape", "27")
rel.verifica(existe(d) and len(perguntas("Descartar alterações?")) == 2, "Esc COM dados pergunta (e Nao mantem aberto)")
protocolo = d.protocol("WM_DELETE_WINDOW")
try:
    d.tk.call(protocolo)
except tk.TclError:
    pass
ap.bombear(root, 0.1)
rel.verifica(existe(d) and len(perguntas("Descartar alterações?")) == 3, "o X da janela COM dados pergunta (e Nao mantem aberto)")
msgs.resposta = True
botao(d, "Cancelar").invoke(); ap.bombear(root, 0.1)
rel.verifica(not existe(d), "respondendo Sim, descarta e fecha")
rel.verifica(qtd("Rascunho") == 0, "nada foi gravado ao descartar")

# ---------------------------------------------------------------- validacao do nome
rel.secao("Validacao com texto junto do campo")
d = abrir_form()
msgs.chamadas.clear()
total_antes = len(app.cofre.registros)
botao(d, "Salvar item").invoke(); ap.bombear(root, 0.1)
erro = next((ap.texto_de(w) for w in ap.todos(d) if w.winfo_class() == "TLabel" and ap.texto_de(w).startswith("⚠")
             and w.winfo_ismapped()), "")
rel.verifica(existe(d) and len(app.cofre.registros) == total_antes, "Salvar sem nome nao grava nem fecha")
rel.verifica("Obrigatório" in erro, "o erro aparece como TEXTO com ícone junto ao campo", erro)
rel.verifica(entradas(d)[0].instate(["invalid"]), "o campo fica marcado como inválido")
entradas(d)[0].insert(0, "Algo")
disparar(entradas(d)[0], "<KeyRelease>", "o", "79")
rel.verifica(not any(ap.texto_de(w).startswith("⚠") and w.winfo_ismapped()
                     for w in ap.todos(d) if w.winfo_class() == "TLabel"), "o erro some ao preencher o nome")
fechar(d)

# ---------------------------------------------------------------- avisos antes de salvar
rel.secao("Avisos antes de salvar (sem senha, fraca, duplicado, repetida)")
rel.verifica(cs.relatorio_forca("abc123")[0] <= 1, "pre-condicao: 'abc123' conta como senha fraca")


def tentar_salvar(servico, login, senha, resposta):
    """Preenche e clica Salvar item com a resposta dada ao aviso; devolve (janela, texto do aviso ou '')."""
    d_ = abrir_form()
    e_ = entradas(d_)
    e_[0].insert(0, servico); e_[1].insert(0, login); e_[2].insert(0, senha)
    msgs.chamadas.clear(); msgs.resposta = resposta
    botao(d_, "Salvar item").invoke(); ap.bombear(root, 0.2)
    avisos = perguntas("Conferir antes de salvar")
    return d_, (str(avisos[-1][1][1]) if avisos else "")


d, txt = tentar_salvar("Sem Senha Co", "", "", False)
rel.verifica(existe(d) and qtd("Sem Senha Co") == 0 and "sem senha" in txt, "sem senha: avisa e, respondendo Nao, nao grava", txt)
fechar(d)
d, txt = tentar_salvar("Sem Senha Co", "", "", True)
rel.verifica(qtd("Sem Senha Co") == 1 and not existe(d), "sem senha: respondendo Sim, grava")
d, txt = tentar_salvar("Fraca Co", "", "abc123", False)
rel.verifica(existe(d) and qtd("Fraca Co") == 0 and "fraca" in txt, "senha fraca: avisa e nao grava", txt)
fechar(d)
d, txt = tentar_salvar("Banco Azul", "a@b.com", FORTE_C, False)
rel.verifica(existe(d) and qtd("Banco Azul") == 1 and "mesmo login" in txt, "duplicado (mesma conta e login): avisa", txt)
fechar(d)
d, txt = tentar_salvar("Outro Site", "", FORTE_A, False)
rel.verifica(existe(d) and qtd("Outro Site") == 0 and "Banco Azul" in txt, "senha repetida: avisa e diz em qual item", txt)
fechar(d)
d, txt = tentar_salvar("Tudo Certo", "t@x.com", FORTE_C, False)
rel.verifica(not txt and qtd("Tudo Certo") == 1, "tudo em ordem: salva SEM nenhuma pergunta", txt)

# ---------------------------------------------------------------- grupo automatico
rel.secao("Grupo automatico pelo nome da conta")
d = abrir_form()
e = entradas(d)
cg = next(w for w in ap.todos(d) if w.winfo_class() == "TCombobox")
esperado = app._nome_grupo_recomendado("Instagram")
rel.verifica(bool(esperado), "pre-condicao: 'Instagram' tem grupo recomendado", str(esperado))
e[0].insert(0, "Instagram"); disparar(e[0], "<KeyRelease>", "m", "58")
rel.verifica(cg.get() == esperado, "digitar 'Instagram' preenche o Grupo sozinho", cg.get())
cg.delete(0, "end"); cg.insert(0, "Meu grupo"); disparar(cg, "<KeyRelease>", "p", "33")
e[0].delete(0, "end"); e[0].insert(0, "Instagram 2"); disparar(e[0], "<KeyRelease>", "2", "11")
rel.verifica(cg.get() == "Meu grupo", "o grupo que o usuario escolheu nao e sobrescrito", cg.get())
fechar(d)
d = abrir_form()
e = entradas(d)
cg = next(w for w in ap.todos(d) if w.winfo_class() == "TCombobox")
e[0].insert(0, "Instagram"); disparar(e[0], "<KeyRelease>", "m", "58")
e[0].delete(0, "end"); e[0].insert(0, "zzqqxx"); disparar(e[0], "<KeyRelease>", "x", "53")
rel.verifica(cg.get() == "", "se o nome deixa de ser reconhecido, o grupo automatico e desfeito", cg.get())
fechar(d)

# ---------------------------------------------------------------- credenciais
rel.secao("Credenciais: um clique, ordem de chegada, remover com confirmacao")
d = abrir_form()
rel.verifica(not any(w.winfo_class() == "TCheckbutton" and "Mostrar" in ap.texto_de(w) for w in ap.todos(d)),
             "nao existe botao 'Mostrar' geral")
olhos = lambda: [w for w in ap.todos(d) if w.winfo_class() == "TButton" and ap.texto_de(w) == "👁" and w.winfo_ismapped()]
rel.verifica(len(olhos()) == 1, "a Senha tem o seu proprio olho", str(len(olhos())))
botao(d, "＋ Chave / token").invoke(); ap.bombear(root, 0.2)
botao(d, "＋ PIN").invoke(); ap.bombear(root, 0.2)
rot_chave, rot_pin = rotulo(d, "CHAVE / TOKEN"), rotulo(d, "PIN NUMÉRICO")
rel.verifica(rot_chave is not None and rot_pin is not None and rot_chave.winfo_rooty() < rot_pin.winfo_rooty(),
             "os campos aparecem na ORDEM em que foram adicionados (Chave, depois PIN)")
rel.verifica(len(olhos()) == 3, "cada campo secreto novo traz o seu olho", str(len(olhos())))
rel.verifica(botao(d, "＋ PIN", visivel=True) is None and botao(d, "＋ Chave / token", visivel=True) is None,
             "os botoes ja usados saem da faixa")
bloco_pin = rot_pin.master.master            # bloco do PIN: cabecalho (rotulo + Remover) e linha do campo
campo_pin = next(w for w in ap.todos(bloco_pin) if w.winfo_class() == "TEntry")
campo_pin.insert(0, "4821")
msgs.chamadas.clear(); msgs.resposta = False
rems = [w for w in ap.todos(d) if w.winfo_class() == "TButton" and ap.texto_de(w) == "✕ Remover" and w.winfo_ismapped()]
rel.verifica(len(rems) == 2, "cada credencial extra tem o seu 'Remover'", str(len(rems)))
rem_pin = next(w for w in ap.todos(bloco_pin) if w.winfo_class() == "TButton" and ap.texto_de(w) == "✕ Remover")
rem_pin.invoke(); ap.bombear(root, 0.2)      # o do PIN, nao "o segundo da lista" (a lista segue a ordem de criacao, nao a de chegada)
rel.verifica(len(perguntas("Remover campo")) == 1 and campo_pin.winfo_ismapped() and campo_pin.get() == "4821",
             "Remover com dado digitado pergunta e, respondendo Nao, mantem o campo e o texto")
msgs.resposta = True
rem_pin.invoke(); ap.bombear(root, 0.2)
rel.verifica(not campo_pin.winfo_ismapped() and campo_pin.get() == "",
             "respondendo Sim, o campo some e o texto digitado e apagado")
rel.verifica(botao(d, "＋ PIN") is not None, "o botao '＋ PIN' volta para a faixa")
msgs.chamadas.clear()
rems = [w for w in ap.todos(d) if w.winfo_class() == "TButton" and ap.texto_de(w) == "✕ Remover" and w.winfo_ismapped()]
rems[0].invoke(); ap.bombear(root, 0.2)
rel.verifica(not perguntas("Remover campo"), "Remover campo VAZIO nao pergunta nada")
botao(d, "＋ Códigos de recuperação").invoke(); ap.bombear(root, 0.2)
caixa = [w for w in ap.todos(d) if w.winfo_class() == "Text" and w.winfo_ismapped()]
rel.verifica(len(caixa) >= 2, "a caixa dos codigos de recuperacao aparece logo, pronta para digitar (alem das notas)")
rel.verifica(not any(w.winfo_class() == "TCheckbutton" and "Mostrar" in ap.texto_de(w) for w in ap.todos(d)),
             "os codigos de recuperacao nao dependem de nenhum 'Mostrar' geral")
fechar(d)

# ---------------------------------------------------------------- olho
rel.secao("Olho por campo: nao some enquanto se digita")
d = abrir_form()
senha = entradas(d)[2]
olho = next(w for w in ap.todos(d) if w.winfo_class() == "TButton" and ap.texto_de(w) == "👁")
olho.invoke(); ap.bombear(root, 0.05)
rel.verifica(str(senha.cget("show")) == "", "clicar no olho mostra a senha")
ap.bombear(root, 0.3)
disparar(senha, "<KeyPress>", "a", "38")
ap.bombear(root, 0.3)
rel.verifica(str(senha.cget("show")) == "", "digitar reinicia a contagem: continua a mostra depois do tempo original")
ap.bombear(root, 0.9)
rel.verifica(str(senha.cget("show")) != "", "sem mexer, volta a ocultar sozinho")
fechar(d)

# ---------------------------------------------------------------- tamanho
rel.secao("Tamanho acompanha o conteudo e nunca passa da tela principal")
d = abrir_form()
for chave in ("＋ Senha extra", "＋ PIN", "＋ Chave / token", "＋ Nº da conta", "＋ Agência", "＋ Códigos de recuperação"):
    b = botao(d, chave)
    if b is not None:
        b.invoke(); ap.bombear(root, 0.15)
ap.bombear(root, 0.3)
rel.verifica(d.winfo_width() <= root.winfo_width() and d.winfo_height() <= root.winfo_height(),
             "com todas as credenciais abertas o formulario cabe dentro da janela principal",
             f"form {d.winfo_width()}x{d.winfo_height()} / principal {root.winfo_width()}x{root.winfo_height()}")
fechar(d)
d = abrir_form()
rel.verifica(d.winfo_height() <= root.winfo_height() and d.winfo_width() <= root.winfo_width(),
             "o formulario simples tambem cabe dentro da janela principal", str(d.winfo_height()))
fechar(d)

# ---------------------------------------------------------------- salvar e criar outro
rel.secao("Salvar e criar outro")
d = abrir_form()
e = entradas(d)
e[0].insert(0, "Primeiro Lote"); e[1].insert(0, "p@x.com"); e[2].insert(0, FORTE_B)
msgs.chamadas.clear(); msgs.resposta = True
botao(d, "Salvar e criar outro").invoke(); ap.bombear(root, 0.8)
novos = [t for t in ap.toplevels(root) if t.title() == "Novo item"]
rel.verifica(qtd("Primeiro Lote") == 1 and len(novos) == 1, "grava o item e abre um formulario novo")
rel.verifica(novos and entradas(novos[0])[0].get() == "", "o formulario novo vem em branco")
for t in novos:
    fechar(t)

# ---------------------------------------------------------------- editar: Status e itens existentes
rel.secao("Editar")
reg = next(r for r in app.cofre.registros if r["servico"] == "Banco Azul")
d = abrir_form(reg)
rel.verifica(botao(d, "Status: Ativa") is not None, "editar mostra 'Status: Ativa'")
botao(d, "Status: Ativa").invoke(); ap.bombear(root, 0.1)
rel.verifica(botao(d, "Status: Desativada") is not None, "o botão de status troca o texto")
msgs.chamadas.clear(); msgs.resposta = False
botao(d, "Cancelar").invoke(); ap.bombear(root, 0.1)
rel.verifica(existe(d) and len(perguntas("Descartar alterações?")) == 1,
             "mudar so o status tambem conta como alteracao nao salva")
fechar(d)
d = abrir_form(reg)
msgs.chamadas.clear()
botao(d, "Cancelar").invoke(); ap.bombear(root, 0.1)
rel.verifica(not existe(d) and not perguntas("Descartar alterações?"),
             "editar SEM mexer em nada fecha sem perguntar")

rel.verifica(not erros.pegar(), "nenhuma excecao escondida em callbacks do Tk")
ap.fechar_app(cs, app)
sys.exit(rel.fim())
