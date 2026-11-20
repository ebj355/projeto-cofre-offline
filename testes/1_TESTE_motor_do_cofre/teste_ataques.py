"""Bateria de ataques contra o cofre. Uso: python3.12 ataques.py /caminho/para/pasta_do_cofre"""
import os, sys, time, shutil, struct, secrets, math
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import cofre_senhas as c

import tempfile
W = tempfile.mkdtemp(prefix="cofre_ataques_")
P = os.path.join(W, "alvo.dat")
SENHA = "cavalo azul come pizza na chuva"
falhas = []


def ok(cond, nome):
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome)
    if not cond:
        falhas.append(nome)


def novo(max_t=5, modo=0, nivel="alto"):
    for x in (P, P + ".tmp"):
        if os.path.exists(x):
            os.remove(x)
    v = c.Cofre.criar(P, SENHA, max_t, modo, nivel)
    v.registros.append({"id": "1", "servico": "Banco", "login": "joao.silva",
                        "senha": "SegredoMuitoSecreto!9", "pin": "4821", "notas": "conta salário"})
    v.salvar()
    return v.chave_gerada


def corromper(pos, delta=1):
    b = bytearray(open(P, "rb").read())
    b[pos] = (b[pos] + delta) % 256
    open(P, "wb").write(bytes(b))


print("\n1) Dados em claro no arquivo")
chave = novo()
bruto = open(P, "rb").read()
for s in (b"SegredoMuitoSecreto", b"4821", b"joao.silva", b"Banco", b"cavalo", "salário".encode()):
    ok(s not in bruto, f"'{s.decode()}' não aparece no arquivo")
ok(chave.replace("-", "").encode() not in bruto, "chave de acesso não aparece no arquivo")

print("\n2) Abertura legítima")
ok(c.Cofre.abrir(P, senha=SENHA).registros[0]["pin"] == "4821", "abre com a senha")
ok(c.Cofre.abrir(P, chave=chave).registros[0]["pin"] == "4821", "abre com a chave de acesso")

print("\n3) Força bruta / dicionário pelo programa (as 5 senhas mais comuns + variações)")
novo(5)
lista = ["123456", "senha123", "cavalo azul", "Cavalo azul come pizza na chuva", "password", "qwerty"]
destruido_em = None
for i, tentativa in enumerate(lista, 1):
    try:
        c.Cofre.abrir(P, senha=tentativa)
    except c.SenhaIncorreta:
        pass
    except c.CofreDestruido:
        destruido_em = i
        break
ok(destruido_em == 5, f"autodestruiu na 5ª tentativa (destruído em {destruido_em})")
ok(not os.path.exists(P), "arquivo apagado do disco")
base = os.path.basename(P)
travas = {base + ".lock", base + ".gravar.lock"}
sobras = [f for f in os.listdir(W) if f.startswith(base) and f not in travas]
ok(not sobras, f"sem sobras do cofre ou temporários na pasta (trava persistente permitida): {sobras}")

print("\n4) Força bruta na chave de acesso (chaves aleatórias)")
novo(3)
r = []
for _ in range(3):
    try:
        c.Cofre.abrir(P, chave=c.nova_chave_acesso()[1])
    except c.SenhaIncorreta as e:
        r.append(e.restantes)
    except c.CofreDestruido:
        r.append("destruído")
ok(r == [2, 1, "destruído"], f"chaves erradas consomem tentativas e destroem: {r}")

print("\n5) Interromper o programa no meio da tentativa (para não gastar tentativa)")
novo(5)
original = c.derivar_chave
c.derivar_chave = lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt())
try:
    c.Cofre.abrir(P, senha="chute")
except KeyboardInterrupt:
    pass
c.derivar_chave = original
ok(c.tentativas_restantes(P) == 4, "a tentativa foi gasta ANTES de testar a senha")

print("\n6) Restaurar o contador para o máximo editando o arquivo")
novo(5)
b = bytearray(open(P, "rb").read()); b[c.POS_CONTADOR] = 200; open(P, "wb").write(bytes(b))
try:
    c.Cofre.abrir(P, senha="chute"); res = "abriu"
except c.ArquivoCorrompido:
    res = "violação"
except Exception as e:
    res = type(e).__name__
ok(res == "violação" and os.path.exists(P), "contador acima do máximo = violação + autodestruição")

print("\n7) Adulterar o conteúdo cifrado (ataque de reversão/edição de bytes)")
for nome, pos in [("último byte dos dados", -1), ("meio dos dados", None), ("nonce dos dados", c.HEADER_LEN - 1)]:
    novo(5)
    tam = os.path.getsize(P)
    p = tam - 1 if pos == -1 else (c.POS_DADOS + (tam - c.POS_DADOS) // 2 if pos is None else pos)
    corromper(p)
    try:
        c.Cofre.abrir(P, senha=SENHA); res = "abriu"
    except c.ArquivoCorrompido:
        res = "violação"
    except Exception as e:
        res = type(e).__name__
    ok(res == "violação" and os.path.exists(P), f"{nome} alterado -> detectado e PRESERVADO (nada apagado)")

print("\n8) Adulterar parâmetros do cabeçalho (enfraquecer o Argon2 / aumentar tentativas)")
novo(5)
b = bytearray(open(P, "rb").read()); struct.pack_into(">I", b, 12, 8192); open(P, "wb").write(bytes(b))
try:
    c.Cofre.abrir(P, senha=SENHA); res = "abriu"
except c.SenhaIncorreta:
    res = "senha incorreta"
except c.ArquivoCorrompido:
    res = "violação"
ok(res != "abriu", f"memória do Argon2 reduzida -> não abre ({res})")
novo(5)
b = bytearray(open(P, "rb").read()); b[17] = 50; open(P, "wb").write(bytes(b))   # max_t
try:
    c.Cofre.abrir(P, senha=SENHA); res = "abriu"
except c.ArquivoCorrompido:
    res = "violação"
except Exception as e:
    res = type(e).__name__
ok(res == "violação", f"máximo de tentativas alterado -> {res}")

print("\n9) Trocar a 'fechadura': colar a chave embrulhada de outro cofre que eu controlo")
novo(5)
alvo = bytearray(open(P, "rb").read())
shutil.move(P, P + ".orig")
c.Cofre.criar(P, "senha do atacante 98765 xyz", 5, 0, "alto")
atk = open(P, "rb").read()
a, z = 19, 19 + 16 + 12 + 48                      # sal_pw + nonce_pw + wrap_pw
alvo[a:z] = atk[a:z]
open(P, "wb").write(bytes(alvo)); os.remove(P + ".orig")
try:
    c.Cofre.abrir(P, senha="senha do atacante 98765 xyz"); res = "abriu"
except c.SenhaIncorreta:
    res = "senha incorreta"
except c.ArquivoCorrompido:
    res = "violação"
ok(res != "abriu", f"fechadura trocada não abre os dados ({res})")

print("\n10) Arquivo truncado / lixo / outro arquivo qualquer")
for nome, dados in [("truncado", None), ("lixo aleatório", secrets.token_bytes(500)), ("vazio", b"")]:
    novo(5)
    if dados is None:
        dados = open(P, "rb").read()[:60]
    open(P, "wb").write(dados)
    try:
        c.Cofre.abrir(P, senha=SENHA); res = "abriu"
    except c.ArquivoInvalido:
        res = "inválido"
    ok(res == "inválido", f"{nome} -> recusado")

print("\n11) Chave digitada errada (formato) não gasta tentativa")
chave = novo(5)
try:
    c.Cofre.abrir(P, chave="ABCD-1234")
except c.ChaveMalFormada:
    pass
ok(c.tentativas_restantes(P) == 5, "contador intacto")

print("\n12) Cada gravação usa nonce novo (sem reutilização)")
novo(5)
v = c.Cofre.abrir(P, senha=SENHA)
nonces = set()
for _ in range(50):
    v.salvar(); nonces.add(open(P, "rb").read()[c.HEADER_LEN - 12:c.HEADER_LEN])
ok(len(nonces) == 50, "50 gravações = 50 nonces diferentes")

print("\n13) Política de senha mestra")
for s, deve in [("123456789012345", False), ("senhasenhasenha", False), ("aaaaaaaaaaaaaaaa", False),
                ("qwerty123meunome", False), ("curto", False), (SENHA, True),
                ("Tr0mb0ne-Laranja-Voa", True)]:
    ok((c.avaliar_senha(s) is None) == deve, f"'{s}' {'aceita' if deve else 'recusada'}")

print("\n14) Detecção de depurador (engenharia reversa)")
sys.settrace(lambda *a: None)
c.COMPILADO = False
det0 = c.ambiente_suspeito()
c.COMPILADO = True
det = c.ambiente_suspeito()
c.COMPILADO = False
sys.settrace(None)
ok(det0 is None, "rodando como .py (IDE/depurador legítimo): NÃO acusa invasão")
ok(det is not None, f"no programa compilado, depurador detectado: {det}")
ok(c.ambiente_suspeito() is None, "sem depurador -> normal")

print("\n16) MODO DOIS FATORES (senha E chave)")
chave = novo(5, modo=1)
for nome, kw in [("só a senha", {"senha": SENHA}), ("só a chave", {"chave": chave})]:
    try:
        c.Cofre.abrir(P, **kw); res = "abriu"
    except c.FatorFaltando:
        res = "recusado"
    ok(res == "recusado" and c.tentativas_restantes(P) == 5, f"{nome} -> recusado sem gastar tentativa")
for nome, kw in [("senha certa + chave errada", {"senha": SENHA, "chave": c.nova_chave_acesso()[1]}),
                 ("senha errada + chave certa", {"senha": "chute qualquer longo", "chave": chave})]:
    try:
        c.Cofre.abrir(P, **kw); res = "abriu"
    except c.SenhaIncorreta:
        res = "negado"
    ok(res == "negado", f"{nome} -> negado")
v = c.Cofre.abrir(P, senha=SENHA, chave=chave)
ok(v.registros[0]["pin"] == "4821", "senha + chave certas -> abre")
b = open(P, "rb").read()
h = c._ler_cabecalho(b)
try:
    c._desembrulhar(c.kek_da_chave(c.ler_chave_acesso(chave), h["sal_k"]), h["nonce_k"], h["wrap_k"]); res = "abriu"
except Exception:
    res = "negado"
ok(res == "negado", "ataque direto: só a chave contra o arquivo -> inútil")
b2 = bytearray(b); b2[18] = 0; open(P, "wb").write(bytes(b2))
try:
    c.Cofre.abrir(P, senha=SENHA); res = "abriu"
except (c.SenhaIncorreta, c.ArquivoCorrompido) as e:
    res = type(e).__name__
ok(res != "abriu", f"mudar o modo para 'só senha' editando o arquivo -> {res}")
chave = novo(5, modo=1)
v = c.Cofre.abrir(P, senha=SENHA, chave=chave)
v.trocar_senha("nova frase secreta bem longa")
ok(bool(c.Cofre.abrir(P, senha="nova frase secreta bem longa", chave=chave)), "trocar senha mantém a chave")
v = c.Cofre.abrir(P, senha="nova frase secreta bem longa", chave=chave)
k2 = v.gerar_nova_chave_acesso()
try:
    c.Cofre.abrir(P, senha="nova frase secreta bem longa", chave=chave); res = "abriu"
except c.SenhaIncorreta:
    res = "negado"
ok(res == "negado", "chave antiga revogada")
ok(bool(c.Cofre.abrir(P, senha="nova frase secreta bem longa", chave=k2)), "chave nova funciona")
ok(v.confere_senha("nova frase secreta bem longa") and not v.confere_senha("errada errada errada"),
   "confirmação de senha no modo dois fatores")

print("\n17) Cascata ChaCha20 + AES-256 e tamanho escondido")
novo(5)
v = c.Cofre.abrir(P, senha=SENHA)
t1 = os.path.getsize(P)
for i in range(15):
    v.registros.append({"id": str(i), "servico": f"s{i}", "login": "l", "senha": "x", "pin": "", "notas": ""})
v.salvar()
ok(os.path.getsize(P) == t1, f"1 item e 16 itens geram arquivos do mesmo tamanho ({t1} bytes)")
b = open(P, "rb").read(); h = c._ler_cabecalho(b)
k_cha, k_aes = c._subchaves(v.dek)
interno = c.AESGCM(k_aes).decrypt(h["nonce_a"], b[h["ini_dados"]:], h["aad"])
ok(b"Banco" not in interno, "removendo a camada AES, o conteúdo continua cifrado (ChaCha20)")
try:
    c.AESGCM(v.dek).decrypt(h["nonce_a"], b[h["ini_dados"]:], h["aad"]); res = "abriu"
except Exception:
    res = "negado"
ok(res == "negado", "chave interna sozinha não abre: as camadas usam chaves derivadas diferentes")

print("\n18) Atualização automática de cofre da versão anterior (v2)")
dek = secrets.token_bytes(32); sal = secrets.token_bytes(16); t, m = 4, 262144
n_pw, w_pw = c._embrulhar(c.derivar_chave(SENHA, sal, t, m, 2), dek)
kb, ktxt = c.nova_chave_acesso(); sk = secrets.token_bytes(16)
n_k, w_k = c._embrulhar(c.kek_da_chave(kb, sk), dek)
nn = secrets.token_bytes(12)
cab = struct.pack(c.HEADER_V2_FMT, c.MAGIC_V2, t, m, 2, 5, sal, n_pw, w_pw, sk, n_k, w_k, nn)
dados = c.json.dumps([{"id": "1", "servico": "Antigo", "login": "a", "senha": "b", "pin": "", "notas": ""}]).encode()
open(P, "wb").write(cab + bytes([5]) + c.AESGCM(dek).encrypt(nn, dados, cab))
v = c.Cofre.abrir(P, chave=ktxt)
ok(v.registros[0]["servico"] == "Antigo" and open(P, "rb").read()[:8] == c.MAGIC, "cofre v2 abre e é convertido")
ok(c.Cofre.abrir(P, senha=SENHA).registros[0]["servico"] == "Antigo", "depois da conversão, senha e chave seguem valendo")

print("\n15) Custo da força bruta FORA do programa (copiando o arquivo)")
nivel_ataque = c.nivel_recomendado()
novo(5, nivel=nivel_ataque)
h = c._ler_cabecalho(open(P, "rb").read())
n = 3
t0 = time.time()
for i in range(n):
    c.derivar_chave(f"chute{i}", h["sal_pw"], h["t"], h["m"], h["p"])
dt = (time.time() - t0) / n
memoria_mb = h["m"] // 1024
print(f"     1 chute = {dt:.2f} s e {memoria_mb} MiB de RAM neste computador (blindagem {nivel_ataque})")
# Atacante com 10.000 GPUs muito potentes, cada uma 100x mais rápida que este PC
taxa = 10_000 * 100 / dt
ano = 3600 * 24 * 365
for nome, bits in [("senha fraca de 8 letras minúsculas", 8 * math.log2(26)),
                   ("frase de 5 palavras (de 7.776)", 5 * math.log2(7776)),
                   ("frase de 6 palavras", 6 * math.log2(7776)),
                   ("chave de acesso (160 bits)", 160)]:
    anos = (2 ** bits / 2) / taxa / ano
    txt = f"{anos:.1e} anos" if anos >= 1 else f"{anos * 365 * 24:.1f} horas"
    print(f"     {nome:38s} -> {txt}")
if nivel_ataque == "maximo":
    ok(dt > 1, "cada chute é caro (Argon2id 1 GiB)")
else:
    ok(h["m"] == c.NIVEIS["alto"][1],
       "a estimativa usa a blindagem Alta recomendada para a memória livre deste computador")
print("     No modo DOIS FATORES o atacante ainda precisaria acertar a chave de 160 bits junto: impraticável.")

for x in (P, P + ".tmp"):
    if os.path.exists(x):
        os.remove(x)
print("\n" + ("TODOS OS TESTES PASSARAM" if not falhas else f"FALHAS: {falhas}"))
sys.exit(1 if falhas else 0)
