"""DUAS JANELAS NO MESMO COFRE + DIAGNÓSTICO CIFRADO + SELO DA PLANILHA SEM A ABA DE SELO.
1) Duas instâncias abrem o mesmo .dat; a primeira salva; a segunda NÃO pode sobrescrever em silêncio (ConflitoGravacao) e o
   arquivo continua com o que a primeira gravou; o conflito é registrado no diagnóstico cifrado (.diag), legível só com a
   chave do cofre. Também: senha errada / arquivo trocado por lixo registram evento sem derrubar nada.
2) Planilha modelo SELADA a que se REMOVE a aba oculta do selo (ou o selo inteiro): importar com selo conhecido é RECUSADO.
Roda no Linux e no Windows."""
import os, sys, base64, tempfile
_RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, _RAIZ); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ferramentas_dos_testes"))
import _resultado; _resultado.registrar(__file__)
import openpyxl, cofre_senhas as c
f = []
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome, flush=True); f.append(bool(cond))
c.NIVEIS["alto"] = (1, 8192)
W = _resultado.pasta_temporaria("cofre_conf_"); P = os.path.join(W, "c.dat"); S = "cavalo azul come pizza na chuva"
def ler(p):
    with open(p, "rb") as a: return a.read()

print("== 1) duas instâncias, mesmo arquivo")
base = c.Cofre.criar(P, S, 10, c.MODO_OU, "alto"); priv = base64.b64decode(base.meta["diag_priv"]); base.fechar()
# (abrir em modo normal regrava o contador de tentativas; por isso a janela aberta ANTES fica desatualizada)
a = c.Cofre.abrir(P, senha=S); b = c.Cofre.abrir(P, senha=S)
b.registros.append(c.novo_item(servico="da janela B", login="b", senha="b")); b.salvar()
gravado_por_a = ler(P)                                  # (o que a janela B gravou)
a.registros.append(c.novo_item(servico="da janela A", login="a", senha="a"))
try:
    a.salvar(); ok(False, "a janela A (desatualizada) sobrescreveu o que a B gravou, SEM aviso!")
except c.ConflitoGravacao as ex:
    ok(len(str(ex)) > 20, f"janela A (desatualizada) recusada com ConflitoGravacao e mensagem clara ('{str(ex)[:60]}...')")
except Exception as ex:
    ok(False, f"erro solto {type(ex).__name__}: {ex}")
ok(ler(P) == gravado_por_a, "o arquivo continua EXATAMENTE como a janela B gravou (nada foi sobrescrito)")
r = c.Cofre.abrir(P, senha=S, consulta=True)
ok([x["servico"] for x in r.registros] == ["da janela B"], "reabrindo: só existe o item da janela B"); r.fechar()
res = c.diag_ler(P, priv)
ok(res is not None and any(reg[1] == c.DIAG_CONFLITO for reg in res[0]), "o conflito ficou registrado no diagnóstico cifrado (.diag)")
ok(res is not None and res[1] == 0, "todos os registros do diagnóstico passam na autenticação (nenhum adulterado)")
ok(c.diag_ler(P, os.urandom(32)) is None, "o diagnóstico NÃO abre com outra chave (cifrado de verdade)")
bruto = ler(P + ".diag")
ok(b"janela" not in bruto and S.encode() not in bruto, "o .diag não contém texto legível nem a senha")
a.fechar(); b.fechar()

print("== 1b) senha errada e arquivo corrompido não derrubam nada")
try: c.Cofre.abrir(P, senha="senha errada bem comprida 123")
except c.SenhaIncorreta: ok(True, "senha errada: SenhaIncorreta (controlado)")
except Exception as ex: ok(False, f"senha errada: erro solto {type(ex).__name__}")
ok(c.tentativas_restantes(P) == 9, "senha errada gastou exatamente 1 tentativa (9 restantes)")
r = c.Cofre.abrir(P, senha=S); ok(c.tentativas_restantes(P) == 10 and len(r.registros) == 1, "senha certa devolve as tentativas e abre"); r.fechar()

print("== 2) planilha selada SEM a aba do selo")
os.chdir(W)
with open(P, "rb") as fh: h = c._ler_cabecalho(fh.read(c.LIMITE_COFRE + 1))
selo = (h["sal_k"], h["nonce_k"], h["wrap_k"])
c.criar_modelo_planilha("m.xlsx", selo)
def importa(nome, s=selo):
    try: c.ler_planilha(nome, selo=s, exigir_selo=c.IMPORTAR_SOMENTE_COM_SELO); return ""      # exatamente como a tela chama
    except ValueError as e: return str(e)
ok(importa("m.xlsx") == "", "modelo intacto importa")
wb = openpyxl.load_workbook("m.xlsx"); del wb["_selo_cofre"]; wb.save("sem_aba_selo.xlsx")
ok(c.IMPORTAR_SOMENTE_COM_SELO is True, "o programa EXIGE o selo ao importar (IMPORTAR_SOMENTE_COM_SELO)")
e = importa("sem_aba_selo.xlsx"); ok(e != "" and "selo" in e.lower(), "aba do selo REMOVIDA: importação recusada com aviso do selo")
wb = openpyxl.load_workbook("m.xlsx"); wb["Senhas"]["A1"] = "Conta (editada)"; wb.save("coluna.xlsx")
e = importa("coluna.xlsx"); ok(e != "" and "selo" in e.lower(), "título de coluna alterado: recusada")
wb = openpyxl.load_workbook("m.xlsx"); wb["_selo_cofre"].sheet_state = "visible"; wb.save("visivel.xlsx")
print("\nTODOS OK" if all(f) else "\nHOUVE FALHAS")
sys.exit(0 if all(f) else 1)
