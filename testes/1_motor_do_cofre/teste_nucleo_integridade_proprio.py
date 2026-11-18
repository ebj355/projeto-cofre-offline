"""Autochecagem do SHA-256 do programa ("Verificar integridade"): o hash calculado pelo cofre bate com o de uma conta
independente (hashlib), muda se UM byte do arquivo mudar, tem 64 hex, e o programa não deixa arquivo .sha256 ao lado.
Simula o .exe compilado (COMPILADO=True, argv[0]=arquivo) sem precisar do Nuitka. Roda no Linux e no Windows."""
import os, re, sys, hashlib, tempfile, shutil
_RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, _RAIZ); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "6_ferramentas_dos_testes"))
import _resultado; _resultado.registrar(__file__)
import cofre_senhas as c
f = []
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome, flush=True); f.append(bool(cond))
W = _resultado.pasta_temporaria("cofre_integ_")
exe = os.path.join(W, "CofreSenhas.exe")
with open(exe, "wb") as a: a.write(os.urandom(3 * (1 << 20) + 17))            # > 3 blocos de 1 MiB: testa a leitura em partes
def ler(p):
    with open(p, "rb") as a: return a.read()
def gravar(p, d):
    with open(p, "wb") as a: a.write(d)
def hash_independente(p):
    return hashlib.sha256(ler(p)).hexdigest()
fn = c.App._hash_proprio_programa
ant_c, ant_a = c.COMPILADO, sys.argv[0]
try:
    c.COMPILADO = False
    ok(fn() is None, "fora do .exe compilado: devolve None (não finge ter hash)")
    c.COMPILADO = True; sys.argv[0] = exe
    h1 = fn()
    ok(bool(h1) and re.fullmatch(r"[0-9a-f]{64}", h1) is not None, "devolve 64 caracteres hexadecimais")
    ok(h1 == hash_independente(exe), "bate com o SHA-256 calculado por conta independente")
    ok(fn() == h1, "estável: duas leituras seguidas dão o mesmo valor")
    dados = bytearray(ler(exe)); dados[len(dados) // 2] ^= 1       # UM bit adulterado no meio do arquivo
    gravar(exe, dados)
    h2 = fn()
    ok(h2 != h1 and h2 == hash_independente(exe), "um bit alterado muda o hash (e o novo bate com a conta independente)")
    dados = bytearray(ler(exe)); dados[-1] ^= 0x80                  # e no último byte (limite do último bloco)
    gravar(exe, dados)
    ok(fn() not in (h1, h2), "alterar o ÚLTIMO byte também muda o hash")
    sys.argv[0] = os.path.join(W, "nao_existe.exe")
    ok(fn() is None, "arquivo sumiu/ilegível: devolve None, sem erro")
finally:
    c.COMPILADO, sys.argv[0] = ant_c, ant_a
ok(not [x for x in os.listdir(W) if x.lower().endswith((".sha256", ".bat"))], "nada de .sha256/.bat solto ao lado do programa")
print("\nTODOS OK" if all(f) else "\nHOUVE FALHAS")
sys.exit(0 if all(f) else 1)
