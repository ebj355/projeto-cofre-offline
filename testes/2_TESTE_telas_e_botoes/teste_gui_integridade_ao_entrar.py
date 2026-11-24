# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Verificacao de integridade ao entrar: ao desbloquear o cofre pela tela de desbloqueio, a janela
"Verificar integridade do cofre" deve abrir SOZINHA, antes de o uso comecar, e so LER (nunca gravar).

Os outros testes de interface desligam essa janela (COFRE_SEM_VERIFICACAO_INICIAL=1) para nao travar; por isso
este e o unico que cobre a abertura automatica. Aqui a variavel e REMOVIDA de proposito.

Cobre:
  1. desbloqueio normal pela tela -> a janela abre sozinha e mostra o arquivo principal como integro;
  2. a conferencia nao altera o arquivo do cofre (mesmo hash antes e depois);
  3. controle: com COFRE_SEM_VERIFICACAO_INICIAL=1 a janela NAO abre (prova que o teste 1 enxerga a diferenca);
  4. copia automatica danificada -> a janela avisa "DANIFICADA" e "PROBLEMA", sem derrubar o programa.

Fica em testes\\2_TESTE_telas_e_botoes\\, junto do _apoio_gui_novos.py. Roda no Windows ou no Linux (xvfb-run -a).
"""
import hashlib
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _apoio_gui_novos as ap          # noqa: E402

TMP = ap.preparar("cofre_integridade_entrada_", limite_segundos=600)
os.environ.pop("COFRE_SEM_VERIFICACAO_INICIAL", None)     # ESTE teste quer a verificacao ligada
cs = ap.importar_cofre()
import tkinter as tk                     # noqa: E402

# O programa espera a janela fechar (wait_window) quando ela abre sozinha. Aqui ela so precisa continuar aberta
# para ser inspecionada; fechamos nos mesmos pelo teste.
tk.Misc.wait_window = lambda self, window=None: None

R = ap.Relatorio("Verificacao de integridade ao entrar")
TITULO = "Verificar integridade do cofre"
ITENS = [dict(servico="Banco", login="joao", senha="Xk9$mQ2!vL7@pR4#", grupo="Banco")]


def hash_do(caminho):
    with open(caminho, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def esperar(root, condicao, limite=90.0):
    """Deixa o Tk trabalhar ate a condicao ficar verdadeira (a abertura roda em segundo plano, com Argon2)."""
    fim = time.time() + limite
    while time.time() < fim:
        ap.bombear(root, 0.05)
        try:
            if condicao():
                return True
        except tk.TclError:
            return False
    return False


def janela_de_integridade(root):
    for t in ap.toplevels(root):
        try:
            if TITULO in t.title():
                return t
        except tk.TclError:
            continue
    return None


def abrir_pela_tela_de_desbloqueio(caminho):
    """Abre o programa NA tela de desbloqueio, digita a senha e aperta 'Desbloquear'. Devolve (app, root, erros, msgs)."""
    root = tk.Tk()
    root.withdraw()
    erros = ap.RecolhedorDeErros(root)
    with ap.GravadorDeBotoes() as grav:
        app = cs.App(root, caminho)
        app.mostrar_inicio()
    msgs = ap.Mensagens(cs, resposta=False)             # "Passeio guiado?" etc.: responde NAO sozinho
    try:
        cs.revelar_janela(root)
    except Exception:                                    # noqa: BLE001
        root.deiconify()
    ap.bombear(root, 0.4)
    campos = [w for w in ap.todos(root) if w.winfo_class() in ("TEntry", "Entry")]
    comando = grav.comando("Desbloquear")
    R.verifica(bool(campos) and comando is not None, "a tela de desbloqueio tem campo de senha e botao Desbloquear",
               f"campos={len(campos)} botao={'sim' if comando else 'nao'}")
    if campos and comando is not None:
        campos[0].delete(0, "end")
        campos[0].insert(0, ap.SENHA)
        comando()
    return app, root, erros, msgs


# ----------------------------------------------------------------------------------------------------------------
R.secao("1. Desbloqueio normal: a janela de integridade abre sozinha")
caminho, cof = ap.criar_cofre_de_teste(cs, TMP, ITENS)
cof.fechar()
app, root, erros, msgs = abrir_pela_tela_de_desbloqueio(caminho)
entrou = esperar(root, lambda: app.cofre is not None)
R.verifica(entrou, "o desbloqueio com a senha certa entra na tela principal")
achou = esperar(root, lambda: janela_de_integridade(root) is not None, limite=15) if entrou else False
R.verifica(achou, "a janela 'Verificar integridade do cofre' abre sozinha depois de desbloquear")
jan = janela_de_integridade(root)
if jan is not None:
    ap.bombear(root, 0.3)
    textos = " | ".join(ap.todos_os_textos(jan))
    R.verifica("Arquivo principal: íntegro" in textos, "mostra o arquivo principal como integro", textos[:200])
    R.verifica(ap.achar_botao(jan, "Fechar") is not None, "tem o botao Fechar")
    R.verifica(ap.achar_botao(jan, "Verificar o programa", exato=False) is not None,
               "tem o botao para verificar o programa (.exe)")
    R.verifica("DANIFICADA" not in textos and "NÃO confere" not in textos,
               "cofre sem problema nao mostra aviso de dano", textos[:200])

    R.secao("2. A conferencia so le: o arquivo do cofre nao muda")
    antes = hash_do(caminho)
    try:
        app.verificar_integridade_cofre(automatica=False)
        ap.bombear(root, 0.4)
    except Exception as ex:                              # noqa: BLE001
        R.verifica(False, "reabrir a conferencia pelo menu nao da erro", repr(ex)[:150])
    R.verifica(hash_do(caminho) == antes, "o arquivo do cofre ficou identico depois da conferencia")
    try:
        jan.destroy()
    except tk.TclError:
        pass
R.verifica(not msgs.erros(), "nenhuma caixa de erro apareceu", msgs.texto_dos_erros())
pend = erros.pegar()
R.verifica(not pend, "nenhuma excecao escapou dos botoes/timers", " || ".join(pend)[:300])
ap.fechar_app(cs, app)

# ----------------------------------------------------------------------------------------------------------------
R.secao("3. Controle: com a verificacao desligada a janela NAO abre")
os.environ["COFRE_SEM_VERIFICACAO_INICIAL"] = "1"
caminho2, cof2 = ap.criar_cofre_de_teste(cs, TMP, ITENS)
cof2.fechar()
app2, root2, erros2, msgs2 = abrir_pela_tela_de_desbloqueio(caminho2)
entrou2 = esperar(root2, lambda: app2.cofre is not None)
R.verifica(entrou2, "o desbloqueio tambem entra com a verificacao desligada")
ap.bombear(root2, 0.8)
R.verifica(janela_de_integridade(root2) is None,
           "com COFRE_SEM_VERIFICACAO_INICIAL=1 a janela nao abre (o teste 1 enxerga a diferenca)")
ap.fechar_app(cs, app2)
os.environ.pop("COFRE_SEM_VERIFICACAO_INICIAL", None)

# ----------------------------------------------------------------------------------------------------------------
R.secao("4. Copia automatica danificada: a janela avisa e o programa continua")
caminho3, cof3 = ap.criar_cofre_de_teste(cs, TMP, ITENS)
app3, root3, erros3, msgs3 = None, None, None, None
try:
    import tkinter as _tk
    root3 = _tk.Tk()
    root3.withdraw()
    erros3 = ap.RecolhedorDeErros(root3)
    app3 = cs.App(root3, caminho3)
    msgs3 = ap.Mensagens(cs, resposta=False)
    app3.cofre = cof3
    app3.tela_principal()
    ap.bombear(root3, 0.4)
    # Danifica a copia DEPOIS de abrir (abrir pode regravar as copias e esconderia o dano)
    with open(caminho3 + ".bak1", "wb") as f:
        f.write(b"isto nao e um cofre" * 20)
    app3.verificar_integridade_cofre(automatica=False)
    ap.bombear(root3, 0.5)
    j3 = janela_de_integridade(root3)
    R.verifica(j3 is not None, "a conferencia abre a janela com uma copia danificada")
    if j3 is not None:
        t3 = " | ".join(ap.todos_os_textos(j3))
        R.verifica("DANIFICADA" in t3, "avisa que a copia automatica esta DANIFICADA", t3[:250])
        R.verifica("PROBLEMA" in t3, "o resumo diz que ha PROBLEMA", t3[:250])
        R.verifica(ap.achar_botao(j3, "Fechar") is not None, "mesmo com problema, o botao Fechar existe")
    R.verifica(not msgs3.erros(), "nenhuma caixa de erro apareceu", msgs3.texto_dos_erros())
    pend3 = erros3.pegar()
    R.verifica(not pend3, "nenhuma excecao escapou", " || ".join(pend3)[:300])
except Exception as ex:                                  # noqa: BLE001
    R.verifica(False, "o caso da copia danificada roda sem erro", repr(ex)[:200])
finally:
    if app3 is not None:
        ap.fechar_app(cs, app3)

sys.exit(R.fim())
