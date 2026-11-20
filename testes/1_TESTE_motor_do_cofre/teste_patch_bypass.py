"""Simula um ATACANTE que remendou o programa (patch de saltos/comparações): mesmo com todas as comparações do
Python forçadas a 'verdadeiro' e a conferência de senha da sessão sempre aprovando, uma senha ERRADA continua sem
abrir o cofre, porque quem decide é a etiqueta de autenticação do AEAD (AES-GCM / ChaCha20-Poly1305): a chave dos dados
só existe se a senha (e a chave de acesso / FIDO) derivarem a chave certa. Não há 'if senha == ...' para pular."""
import os, sys, tempfile, hmac, secrets
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
import cofre_senhas as c
f = []
def ok(cond, nome):
    """Registra uma verificação."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
W = tempfile.mkdtemp(prefix="patch_"); SEN = "cavalo azul come pizza na chuva"
caminhos = {}
for modo, nm in ((c.MODO_S, "S"), (c.MODO_E, "E"), (c.MODO_OU, "OU")):
    p = os.path.join(W, nm + ".dat"); v = c.Cofre.criar(p, SEN, 5, modo, "alto")
    v.registros.append(c.novo_item(servico="Banco", login="a", senha="segredo-123")); v.salvar()
    caminhos[nm] = (p, (v.chave_gerada or "") + "x"); v.fechar()
# o atacante troca TODAS as comparações em tempo constante e a conferência da sessão por "sempre verdadeiro"
orig = (secrets.compare_digest, hmac.compare_digest, c.Cofre.confere_senha, c.Cofre.confere_chave_acesso)
secrets.compare_digest = lambda *a, **k: True
hmac.compare_digest = lambda *a, **k: True
c.Cofre.confere_senha = lambda self, s: True
c.Cofre.confere_chave_acesso = lambda self, t: True
try:
    for nm, (p, K) in caminhos.items():
        K = K[:-1]
        antes = c.tentativas_restantes(p)
        try:
            v = c.Cofre.abrir(p, senha="senha errada completamente diferente 9", chave=(K if nm == "E" else None)); abriu = True; v.fechar()
        except (c.SenhaIncorreta, c.CofreDestruido, c.ChaveMalFormada, c.FatorFaltando): abriu = False
        ok(not abriu, f"modo {nm}: com as comparações remendadas, senha errada AINDA não abre")
        if nm == "E":
            try:
                v = c.Cofre.abrir(p, senha=SEN, chave=c.nova_chave_acesso()[1]); abriu = True; v.fechar()
            except (c.SenhaIncorreta, c.CofreDestruido): abriu = False
            ok(not abriu, "modo E: senha certa + chave errada AINDA não abre (remendado)")
        ok(c.tentativas_restantes(p) < antes or not os.path.exists(p), f"modo {nm}: a tentativa errada continua sendo contada")
finally:
    secrets.compare_digest, hmac.compare_digest, c.Cofre.confere_senha, c.Cofre.confere_chave_acesso = orig
print("FALHAS:", f.count(False)); sys.exit(1 if False in f else 0)
