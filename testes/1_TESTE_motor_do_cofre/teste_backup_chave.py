# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""O backup exige a chave de acesso: Cofre.confere_chave_acesso aceita só a chave certa deste cofre."""
import os, sys, tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
import cofre_senhas as c
f = []
def ok(cond, nome):
    """Registra uma verificação."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
W = tempfile.mkdtemp(prefix="bk_"); os.chdir(W)
for modo, nome in ((c.MODO_E, "senha E chave"), (c.MODO_OU, "senha OU chave")):
    v = c.Cofre.criar(os.path.join(W, f"{modo}.dat"), "cavalo azul come pizza na chuva", 5, modo, "alto")
    K = v.chave_gerada
    ok(v.confere_chave_acesso(K), f"{nome}: chave certa é aceita")
    ok(v.confere_chave_acesso(K.lower().replace("-", " ")), f"{nome}: aceita minúsculas e espaços")
    outra = c.Cofre.criar(os.path.join(W, f"o{modo}.dat"), "outra senha bem diferente 12345", 5, modo, "alto")
    ok(not v.confere_chave_acesso(outra.chave_gerada), f"{nome}: chave de OUTRO cofre é recusada")
    ok(not v.confere_chave_acesso("") and not v.confere_chave_acesso("abc") and not v.confere_chave_acesso(None), f"{nome}: vazio/curto/None recusados")
    errada = K[:-2] + ("AA" if not K.endswith("AA") else "BB")
    ok(not v.confere_chave_acesso(errada), f"{nome}: chave com erro de digitação recusada")
    ok(not v.confere_chave_acesso("senha: cavalo azul come pizza na chuva"), f"{nome}: a senha mestra NÃO vale como chave")
    v.fechar(); outra.fechar()
s = c.Cofre.criar(os.path.join(W, "s.dat"), "cavalo azul come pizza na chuva", 5, c.MODO_S, "alto")
ok(s.confere_chave_acesso("qualquer"), "cofre só senha: não há chave a conferir")
s.fechar()
print("FALHAS:", f.count(False)); sys.exit(1 if False in f else 0)
