# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Qualidade estatística da aleatoriedade GERADA PELO PRÓPRIO PROGRAMA (não é uma suíte NIST SP800-22 completa -
isso exigiria megabytes de amostra; aqui o objetivo é ser um "canário": pegar uma regressão catastrófica, como
alguém trocar por engano `secrets.token_bytes`/Argon2id por um gerador fraco (ex.: `random`, ou um sal/nonce fixo),
antes que isso vá para produção. As margens dos testes são de propósito BEM generosas para não serem instáveis
(flaky) - uma falha aqui é sinal de um problema grave, não de ruído estatístico normal.
1) sal de cada cofre criado (Cofre.criar) e nonce de cada gravação (Cofre.salvar) - lidos do ARQUIVO REAL, não
   gerados "soltos": confere a fiação de verdade, não só a biblioteca `secrets`;
2) chave de acesso (nova_chave_acesso) - os 160 bits que protegem o cofre no modo "chave";
3) PIN gerado (gerar_pin) - dígitos 0-9 têm de ser aproximadamente uniformes;
4) senha gerada (gerar_senha) - nenhuma repetição em centenas de gerações e cobertura de letras/números/símbolos."""
import os, sys, tempfile

RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, RAIZ)
import cofre_senhas as c

falhas = []
def ok(cond, nome):
    print(("  [OK] " if cond else "  [FALHOU] ") + nome)
    if not cond:
        falhas.append(nome)

def monobit(dados, nome):
    """Teste de frequência de bits (monobit): a proporção de bits '1' tem de ficar perto de 50%."""
    total_bits = len(dados) * 8
    uns = sum(bin(b).count("1") for b in dados)
    prop = uns / total_bits
    ok(0.46 <= prop <= 0.54, f"{nome}: proporção de bits '1' = {prop:.3f} (esperado ~0.50, margem generosa 0.46-0.54)")

def chi_quadrado_bytes(dados, nome):
    """Qui-quadrado de uniformidade dos 256 valores de byte possíveis (margem bem generosa de propósito)."""
    n = len(dados)
    contagem = [0] * 256
    for b in dados:
        contagem[b] += 1
    esperado = n / 256
    qui2 = sum((o - esperado) ** 2 / esperado for o in contagem)
    # df=255; limite bem generoso (um valor "normal" fica bem abaixo de 400 na prática) - só pega desvio grosseiro
    ok(qui2 < 450, f"{nome}: qui-quadrado dos bytes = {qui2:.1f} com {n} bytes (limite generoso 450, df=255)")

def sem_blocos_repetidos(blocos, nome):
    """Nenhum bloco de 8+ bytes aparece duas vezes (checagem de colisão trivial)."""
    vistos = set(blocos)
    ok(len(vistos) == len(blocos), f"{nome}: {len(blocos)} blocos gerados, {len(vistos)} distintos (sem repetição)")

W = tempfile.mkdtemp(prefix="cofre_aleatoriedade_")

print("1) Sal de cada cofre criado e nonce de cada gravação (lidos do arquivo real)")
sais, nonces = [], []
p = os.path.join(W, "a.dat")
for i in range(40):
    if os.path.exists(p):
        os.remove(p)
    v = c.Cofre.criar(p, f"Senha-Teste-Entropia-{i}-Aa1!", 5, c.MODO_OU, "alto")
    h = c._ler_cabecalho(open(p, "rb").read())
    sais.append(bytes(h["sal_pw"]))
    v.fechar()
v2 = c.Cofre.abrir(p, senha="Senha-Teste-Entropia-39-Aa1!")
for _ in range(400):
    v2.salvar()
    nonces.append(c._ler_cabecalho(open(p, "rb").read())["nonce_a"])
v2.fechar()
sal_bytes = b"".join(sais)
nonce_bytes = b"".join(nonces)
monobit(sal_bytes, "40 sais de Cofre.criar")
# (amostra pequena de propósito - só 40 cofres - para não deixar o teste lento; com 640 bytes o qui-quadrado de
# 256 categorias não é confiável (esperado só 2,5 por categoria), então aqui só o monobit e a checagem de
# repetição - o qui-quadrado completo roda abaixo nos 400 nonces, que têm amostra suficiente)
sem_blocos_repetidos(sais, "40 sais de Cofre.criar")
monobit(nonce_bytes, "400 nonces de gravação")
chi_quadrado_bytes(nonce_bytes, "400 nonces de gravação")
sem_blocos_repetidos(nonces, "400 nonces de gravação")

print("\n2) Chave de acesso (nova_chave_acesso) - 160 bits")
chaves = [c.nova_chave_acesso()[0] for _ in range(300)]
chave_bytes = b"".join(chaves)
monobit(chave_bytes, "300 chaves de acesso")
chi_quadrado_bytes(chave_bytes, "300 chaves de acesso")
sem_blocos_repetidos(chaves, "300 chaves de acesso")
ok(all(len(k) == 20 for k in chaves), "cada chave de acesso tem exatamente 20 bytes (160 bits)")

print("\n3) PIN gerado (gerar_pin) - dígitos 0-9 aproximadamente uniformes")
pins = [c.gerar_pin(6) for _ in range(1500)]
ok(all(len(p_) == 6 and p_.isdigit() for p_ in pins), "todos os PINs têm 6 dígitos numéricos")
digitos = "".join(pins)
contagem_d = [digitos.count(str(d)) for d in range(10)]
esperado_d = len(digitos) / 10
qui2_d = sum((o - esperado_d) ** 2 / esperado_d for o in contagem_d)
# df=9; limite bem generoso (crítico a 0.001 é ~27) - usamos uma margem ainda maior para não ser flaky
ok(qui2_d < 60, f"distribuição dos dígitos do PIN: qui-quadrado = {qui2_d:.1f} em {len(digitos)} dígitos (limite 60, df=9)")
ok(len(set(pins)) >= 1490, f"1500 PINs de 6 dígitos gerados, {len(set(pins))} distintos (praticamente sem repetição)")

print("\n4) Senha gerada (gerar_senha) - sem repetição e com cobertura de classes de caracteres")
senhas = [c.gerar_senha(20, numeros=True, simbolos=True) for _ in range(300)]
ok(len(set(senhas)) == 300, "300 senhas geradas, todas distintas")
tem_letra = all(any(ch.isalpha() for ch in s) for s in senhas)
tem_numero = all(any(ch.isdigit() for ch in s) for s in senhas)
tem_simbolo = all(any(not ch.isalnum() for ch in s) for s in senhas)
ok(tem_letra and tem_numero and tem_simbolo, "todas as 300 senhas têm letra, número E símbolo (cobertura de classes)")

print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
