"""CORRUPÇÃO FORÇADA do arquivo do cofre: truncado em vários pontos, zerado, cheio de lixo, cabeçalho estragado, 1 byte
virado em posições espalhadas, arquivo vazio, lixo no fim e uma PASTA no lugar do arquivo. Em TODOS os casos o programa
tem de (1) nunca abrir como se estivesse bom, (2) nunca dar erro técnico solto (TypeError/IndexError/struct.error...):
só os erros do próprio cofre, com mensagem em português; (3) nunca destruir nem alterar o arquivo ao apenas olhar.
Abre em MODO CONSULTA (não gasta tentativa, não grava). Roda no Linux e no Windows."""
import os, sys, secrets, shutil
_RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, _RAIZ); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "6_TESTE_ferramentas_dos_testes"))
import _resultado; _resultado.registrar(__file__)
import cofre_senhas as c
f = []
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome, flush=True); f.append(bool(cond))
c.NIVEIS["alto"] = (1, 8192)                      # Argon2 leve: aqui se testa o formato do arquivo, não a força da senha
def ler(p):
    with open(p, "rb") as a: return a.read()
W = _resultado.pasta_temporaria("cofre_corr_"); S = "cavalo azul come pizza na chuva"
BOM = os.path.join(W, "bom.dat")
v = c.Cofre.criar(BOM, S, 5, c.MODO_OU, "alto")
v.registros.append(c.novo_item(servico="Banco", login="a@b.c", senha="Segredo-123!")); v.salvar(); v.fechar()
orig = ler(BOM); T = len(orig)
ok(T > 100, f"cofre de teste criado ({T} bytes)")
PERMITIDOS = (c.ArquivoInvalido, c.SenhaIncorreta, c.ViolacaoDetectada, c.CofreDestruido, c.ChaveMalFormada, OSError)

def tenta(nome, dados=None, pasta=False):
    p = os.path.join(W, "caso.dat")
    for x in (p, p + ".bak1", p + ".bak2", p + ".tmp"):
        if os.path.isdir(x): shutil.rmtree(x)
        elif os.path.exists(x): os.remove(x)
    if pasta: os.mkdir(p)
    else:
        with open(p, "wb") as a: a.write(dados)
    antes = None if pasta else dados
    try:
        r = c.Cofre.abrir(p, senha=S, consulta=True)
        r.fechar(); ok(False, f"{nome}: abriu como se estivesse bom!"); return
    except PERMITIDOS as ex:
        msg = str(ex)
        ok(True, f"{nome}: erro controlado ({type(ex).__name__})")
        if not isinstance(ex, OSError):
            ok(len(msg.strip()) > 5 and "Traceback" not in msg, f"{nome}: mensagem legível ('{msg[:50]}...')")
    except Exception as ex:
        ok(False, f"{nome}: erro TÉCNICO solto {type(ex).__name__}: {ex}"); return
    if antes is not None:
        ok(os.path.exists(p) and ler(p) == antes, f"{nome}: o arquivo ficou exatamente como estava (nada destruído)")

print("== truncado")
for corte in sorted({0, 1, 7, 8, 9, 15, 16, 31, 64, 100, T // 4, T // 2, T - 17, T - 1}):
    if 0 <= corte < T: tenta(f"truncado em {corte}/{T}", orig[:corte])
print("== zerado / lixo / vazio / cabeçalho")
tenta("tudo zeros (mesmo tamanho)", bytes(T))
tenta("tudo 0xFF", b"\xff" * T)
tenta("lixo aleatório (mesmo tamanho)", secrets.token_bytes(T))
tenta("lixo aleatório pequeno", secrets.token_bytes(5))
tenta("cabeçalho (16 bytes) trocado por lixo", secrets.token_bytes(16) + orig[16:])
tenta("magic trocado por texto", b"NAO-COFRE" + orig[9:])
tenta("lixo anexado no fim", orig + secrets.token_bytes(64))
tenta("corpo todo zerado, só o cabeçalho certo", orig[:40] + bytes(T - 40))
print("== um byte virado em posições espalhadas")
for pos in sorted({0, 4, 8, 12, 20, 40, T // 3, T // 2, T - 20, T - 1}):
    if 0 <= pos < T:
        b = bytearray(orig); b[pos] ^= 0x01; tenta(f"byte {pos} virado", bytes(b))
print("== pasta no lugar do arquivo")
tenta("pasta no lugar do cofre", pasta=True)
print("== o cofre original continua abrindo")
r = c.Cofre.abrir(BOM, senha=S, consulta=True); ok(len(r.registros) == 1, "cofre bom abre e tem 1 item"); r.fechar()
print("\nTODOS OK" if all(f) else "\nHOUVE FALHAS")
sys.exit(0 if all(f) else 1)
