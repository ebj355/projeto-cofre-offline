# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""LIMITE DE TAMANHO DE SENHA (negação de serviço) e ALERTA DE SISTEMA DE ARQUIVOS.
- avaliar_forca/avaliar_senha com texto gigante: rápido e recusado com mensagem clara;
- criar/trocar com senha acima do limite: recusa; abrir com senha acima do limite: ChaveMalFormada, SEM gastar tentativa
  (o arquivo fica idêntico byte a byte);
- sistema_de_arquivos devolve '' fora do Windows; aviso_sistema_de_arquivos só dispara em FAT/FAT32/exFAT."""
import os, sys, time, tempfile, importlib.util
spec = importlib.util.spec_from_file_location("c", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "cofre_senhas.py"))
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
FAL = []


def ok(cond, msg):
    print(("  [OK]   " if cond else "  [FALHOU] ") + msg, flush=True)
    if not cond:
        FAL.append(msg)


print("== 1) texto gigante não custa caro")
t0 = time.time(); r = c.avaliar_forca("aB3$" * 2_000_000); dt = time.time() - t0
ok(dt < 2.0, f"avaliar_forca de 8 milhões de caracteres levou {dt:.2f}s (< 2 s)")
ok(c.avaliar_senha("x" * (c.MAX_SENHA + 1)) is not None and "caracteres" in c.avaliar_senha("x" * (c.MAX_SENHA + 1)),
   "avaliar_senha recusa senha acima do limite com mensagem")
ok(c.avaliar_senha("cavalo azul come pizza na chuva 2026") is None, "senha normal continua aceita")
S = "cavalo azul come pizza na chuva 2026"

print("== 2) criar / abrir / conferir")
d = tempfile.mkdtemp(); P = os.path.join(d, "cofre.dat")
try:
    c.Cofre.criar(P, "a" * (c.MAX_SENHA + 1), 3, 0, "alto")
    ok(False, "criar com senha gigante deveria recusar")
except ValueError:
    ok(not os.path.exists(P), "criar com senha acima do limite: ValueError e nenhum arquivo criado")
v = c.Cofre.criar(P, S, 3, 0, "alto"); v.salvar(); v.fechar()
antes = open(P, "rb").read()
try:
    c.Cofre.abrir(P, senha="z" * (c.MAX_SENHA + 1))
    ok(False, "abrir com senha gigante deveria recusar")
except c.ChaveMalFormada:
    ok(open(P, "rb").read() == antes, "abrir com senha gigante: recusa SEM gastar tentativa (arquivo idêntico)")
a = c.Cofre.abrir(P, senha=S)
ok(a.confere_senha("q" * 5_000_000) is False, "confere_senha com texto gigante: False, imediato")
ok(a.confere_senha(S) is True, "confere_senha com a senha certa: True")
try:
    a._definir_senha("w" * (c.MAX_SENHA + 1))
    ok(False, "trocar para senha gigante deveria recusar")
except ValueError:
    ok(a.confere_senha(S), "trocar para senha acima do limite recusa e mantém a senha atual")
a.fechar()

print("== 3) sistema de arquivos")
ok(c.sistema_de_arquivos(P) == "" or c.EH_WINDOWS, "fora do Windows: '' (não sabe)")
for fs, esperado in (("EXFAT", True), ("FAT32", True), ("FAT", True), ("NTFS", False), ("REFS", False), ("", False)):
    ok(bool(c.aviso_sistema_de_arquivos(fs)) == esperado, f"aviso para '{fs or '(desconhecido)'}': {'sim' if esperado else 'não'}")
ok("OBRIGATÓRIO" in c.aviso_sistema_de_arquivos("EXFAT"), "o aviso diz que o BitLocker To Go é obrigatório")

print("== 4) hibernação")
ok(c.hibernacao_ligada() is None or c.EH_WINDOWS, "fora do Windows: None (não sabe)")
ok("powercfg /h off" in c.AVISO_HIBERNACAO and "BitLocker" in c.AVISO_HIBERNACAO, "o aviso de hibernação diz o que fazer")
import types
fake = types.SimpleNamespace(HKEY_LOCAL_MACHINE=1, OpenKey=lambda *a: __import__("contextlib").nullcontext(0),
                             QueryValueEx=lambda k, n: (1, 4))
sys.modules["winreg"] = fake; c.EH_WINDOWS = True
ok(c.hibernacao_ligada() is True, "registro com HibernateEnabled=1: True")
fake.QueryValueEx = lambda k, n: (0, 4)
ok(c.hibernacao_ligada() is False, "registro com HibernateEnabled=0: False")
fake.QueryValueEx = lambda k, n: (_ for _ in ()).throw(OSError("sem acesso"))
ok(c.hibernacao_ligada() is None, "registro inacessível: None (não quebra)")
c.EH_WINDOWS = False

print("\nFALHAS:", len(FAL))
for f in FAL:
    print("  -", f)
sys.exit(1 if FAL else 0)
