# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""FUZZING DO CABEÇALHO v5 E DA SEÇÃO FIDO: troca CADA byte do cabeçalho e da seção FIDO (vários valores) e confere que
o programa NUNCA gasta tentativa, NUNCA destrói e NUNCA abre com dados errados: o resultado é sempre ArquivoCorrompido ou
ArquivoInvalido, e o arquivo no disco fica idêntico byte a byte. (Só o byte do contador fica de fora: ele não é autenticado.)"""
import os, sys, random, tempfile, importlib.util
spec = importlib.util.spec_from_file_location("c", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "cofre_senhas.py"))
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
FAL = []


def ok(cond, msg):
    print(("  [OK]   " if cond else "  [FALHOU] ") + msg, flush=True)
    if not cond:
        FAL.append(msg)


S = "cavalo azul come pizza na chuva 2026"
SEG = None
d = tempfile.mkdtemp(); P = os.path.join(d, "cofre.dat")
v = c.Cofre.criar(P, S, 3, 0, "alto"); v.registros.append({"id": "a", "servico": "A", "login": "u", "senha": "s", "notas": ""})
v.salvar()
import hmac, hashlib, secrets                       # chave FIDO simulada: a seção FIDO do arquivo fica PREENCHIDA
segredo = secrets.token_bytes(32); cred = secrets.token_bytes(64)
v.adicionar_fido("Principal", cred, hmac.new(segredo, v.salt_fido(), hashlib.sha256).digest()); v.salvar(); v.fechar()
bom = open(P, "rb").read()


def prov(creds, salt):
    """Chave FIDO simulada."""
    return cred, hmac.new(segredo, salt, hashlib.sha256).digest()


h = c._ler_cabecalho(bom)
ok(h["ini_dados"] - h["hl"] - 1 > 100, "a seção FIDO está preenchida (tem credencial e código de recuperação)")
regioes = [("cabeçalho", 0, h["hl"]), ("seção FIDO", h["hl"] + 1, h["ini_dados"])]
print(f"cabeçalho: {h['hl']} bytes; seção FIDO: {h['ini_dados'] - h['hl'] - 1} bytes")
rnd = random.Random(20261111)
estat = {"corr": 0, "inv": 0, "outro": {}}
for nome, ini, fim in regioes:
    for pos in range(ini, fim):
        for _ in range(3):
            novo = bytearray(bom)
            novo[pos] ^= rnd.choice([1, 2, 4, 8, 16, 32, 64, 128, rnd.randrange(1, 256)])
            if novo[pos] == bom[pos]:
                continue
            open(P, "wb").write(bytes(novo))
            try:
                c.Cofre.abrir(P, senha=S, fido=prov).fechar()
                r = "ABRIU"
            except c.ArquivoCorrompido:
                r = "corr"
            except c.ArquivoInvalido:
                r = "inv"
            except Exception as ex:
                r = type(ex).__name__
            if r in ("corr", "inv"):
                estat[r] += 1
            else:
                estat["outro"][(nome, pos, r)] = estat["outro"].get((nome, pos, r), 0) + 1
            if open(P, "rb").read() != bytes(novo):
                estat["outro"][(nome, pos, "ARQUIVO ALTERADO")] = 1
print("resultado:", estat["corr"], "ArquivoCorrompido,", estat["inv"], "ArquivoInvalido,", len(estat["outro"]), "outros")
for k, n in list(estat["outro"].items())[:15]:
    print("   fora do esperado:", k, n)
ok(not estat["outro"], "nenhum byte trocado gastou tentativa, destruiu, alterou o arquivo ou abriu com dados errados")
ok(estat["corr"] > 0, "o checksum v5 acusou corrupção (ArquivoCorrompido)")
open(P, "wb").write(bom)
ok(c.Cofre.abrir(P, senha=S, fido=prov).registros[0]["servico"] == "A", "o arquivo original continua abrindo com a senha certa")
print("\nFALHAS:", len(FAL))
sys.exit(1 if FAL else 0)
