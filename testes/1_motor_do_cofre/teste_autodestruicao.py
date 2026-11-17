"""Autodestruição sem resíduos: depois do limite de tentativas não sobra NADA do cofre em disco (arquivo, cópias .bak1-5,
.tmp, .danificado, .pre-v5, .diag) e nenhum texto conhecido (serviço, login, senha, notas) aparece em arquivo algum da
pasta; o arquivo do cofre nunca guarda texto legível; e, no Linux, a memória do processo (/proc/self/mem) não guarda
os textos secretos depois de fechar/destruir. Contagem de tentativas conferida em todas as combinações de fatores."""
import os, sys, tempfile, subprocess, hmac, hashlib, secrets, textwrap
RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, RAIZ)
import cofre_senhas as c
f = []
def ok(cond, nome):
    """Registra uma verificação."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))

def todos_os_arquivos(pasta):
    """Todos os arquivos (caminho completo) sob a pasta."""
    return [os.path.join(r, n) for r, _, ns in os.walk(pasta) for n in ns]

SEGREDOS = ["Banco-ZetaQuimica-77", "usuario.zeta@exemplo.com", "S3nh@-Ultra-Secreta-9981", "nota-confidencial-xyz-42", "PIN-4815162342"]
def com_segredos(pasta, nome="c.dat", modo=c.MODO_OU, max_t=3):
    """Cria um cofre com os segredos acima, salva várias vezes (gera .bak1..5) e devolve (caminho, senha, chave)."""
    p = os.path.join(pasta, nome); senha = "frase-mestra-longa-do-teste-0001"
    v = c.Cofre.criar(p, senha, max_t, modo, "alto"); chave = (v.chave_gerada or "") + "x"; chave = chave[:-1]
    v.registros.append(c.novo_item(servico=SEGREDOS[0], login=SEGREDOS[1], senha=SEGREDOS[2], notas=SEGREDOS[3], pin=SEGREDOS[4].split("-")[1]))
    for i in range(7):
        v.registros[0]["notas"] = SEGREDOS[3] + str(i); v.salvar()
    v.fechar()
    return p, senha, chave

# ---------- 1) o que fica em disco NUNCA é legível
d = tempfile.mkdtemp(prefix="auto_"); p, senha, chave = com_segredos(d)
arqs = todos_os_arquivos(d)
ok(any(a.endswith(".bak1") for a in arqs), "o salvamento gerou cópias de segurança (.bak1...)")
legivel = [os.path.basename(a) for a in arqs if any(s.encode() in open(a, "rb").read() or s.encode("utf-16-le") in open(a, "rb").read() for s in SEGREDOS)]
ok(not legivel, f"nenhum arquivo do cofre guarda texto legível ({len(arqs)} arquivos conferidos)")

# ---------- 2) autodestruição apaga TUDO e não deixa resíduo
for extra in (".danificado", ".pre-v5", ".tmp", ".diag", ".diag.tmp"):
    with open(p + extra, "wb") as fh: fh.write(("resíduo " + " ".join(SEGREDOS)).encode())
outro = os.path.join(d, "foto_de_ferias.jpg"); open(outro, "wb").write(b"nao mexer")
destruiu = False
for i in range(10):
    try:
        c.Cofre.abrir(p, senha="senha errada numero " + str(i) + " bem longa")
    except c.CofreDestruido: destruiu = True; break
    except c.SenhaIncorreta: pass
ok(destruiu and i == 2, f"cofre destruído na tentativa certa (3ª): i={i}")
sobras = [os.path.basename(a) for a in todos_os_arquivos(d) if os.path.basename(a) != "foto_de_ferias.jpg"]
ok(not sobras, f"nada do cofre sobrou na pasta (sobras: {sobras})")
ok(open(outro, "rb").read() == b"nao mexer", "arquivos que não são do cofre ficam intactos")
ok(not any(any(s.encode() in open(a, "rb").read() for s in SEGREDOS) for a in todos_os_arquivos(d)), "nenhum segredo legível em nenhum arquivo da pasta")
try: c.Cofre.abrir(p, senha=senha); depois = "abriu"
except FileNotFoundError: depois = "sumiu"
except Exception as e: depois = type(e).__name__
ok(depois in ("sumiu", "ArquivoInvalido"), f"depois de destruído, nem a senha certa abre ({depois})")

# ---------- 3) sobrescrita: o conteúdo é trocado ANTES do nome sumir (3 passagens), e links não atingem o alvo
d2 = tempfile.mkdtemp(prefix="auto2_"); alvo = os.path.join(d2, "alvo.txt"); open(alvo, "wb").write(b"importante" * 100)
lnk = os.path.join(d2, "c.dat.bak1")
try: os.symlink(alvo, lnk); tem_link = True
except (OSError, NotImplementedError): tem_link = False
if tem_link:
    c.destruir(os.path.join(d2, "c.dat"))
    ok(os.path.exists(alvo) and open(alvo, "rb").read() == b"importante" * 100 and not os.path.lexists(lnk), "atalho para outro arquivo: só o nome do atalho some, o alvo fica intacto")
vistos = []
orig = c.secrets.token_bytes
arq = os.path.join(d2, "x.bin"); open(arq, "wb").write(b"A" * 5000)
c.secrets.token_bytes = lambda n: (vistos.append(n), orig(n))[1]
try: c._destruir_um(arq)
finally: c.secrets.token_bytes = orig
ok(vistos.count(5000) == 3 and not os.path.exists(arq), "arquivo sobrescrito 3 vezes com aleatórios do tamanho todo e depois apagado")

# ---------- 4) contagem de tentativas em TODAS as combinações de fatores
class Ch:
    """Chave FIDO simulada (o segredo nunca sai dela)."""
    def __init__(s): s.cr = {}
    def reg(s): i = secrets.token_bytes(64); s.cr[i] = secrets.token_bytes(32); return i
    def prov(s, creds, salt):
        for i in creds:
            if i in s.cr: return i, hmac.new(s.cr[i], salt, hashlib.sha256).digest()
        raise c.FidoErro("Esta chave FIDO não está cadastrada neste cofre.")
def tenta(p_, **k):
    """Tenta abrir; devolve o nome do resultado."""
    try: v_ = c.Cofre.abrir(p_, **k); v_.fechar(); return "ABRIU"
    except Exception as e: return type(e).__name__
SEN = "cavalo azul come pizza na chuva"
for modo, nm in ((c.MODO_E, "senha E chave"), (c.MODO_OU, "senha OU chave"), (c.MODO_S, "só senha")):
    for fido in (False, True):
        dd = tempfile.mkdtemp(prefix="cont_"); pp = os.path.join(dd, "c.dat")
        v = c.Cofre.criar(pp, SEN, 5, modo, "alto"); K = ((v.chave_gerada or "") + "x")[:-1]
        ch = Ch(); rec = None
        if fido:
            cred = ch.reg(); s_ = hmac.new(ch.cr[cred], v.salt_fido(), hashlib.sha256).digest()
            rec = ((v.adicionar_fido("k", cred, s_) or "") + "x")[:-1]; v.salvar()
        v.fechar()
        base = dict(senha=SEN, chave=K) if modo == c.MODO_E else dict(senha=SEN)
        if fido: base["fido"] = ch.prov
        t = f"{nm}{' + FIDO' if fido else ''}"
        r = lambda: c.tentativas_restantes(pp)
        e = dict(base, senha="errada errada errada errada 1")
        ok(tenta(pp, **e) == "SenhaIncorreta" and r() == 4, f"{t}: senha errada gasta 1 tentativa")
        if modo == c.MODO_E:
            e = dict(base, chave=c.nova_chave_acesso()[1]); ok(tenta(pp, **e) == "SenhaIncorreta" and r() == 3, f"{t}: chave errada (bem formada) gasta 1")
            e = dict(base, chave="lixo"); ok(tenta(pp, **e) == "ChaveMalFormada" and r() == 3, f"{t}: chave mal formada NÃO gasta")
            e = dict(base); e.pop("chave"); ok(tenta(pp, **e) == "FatorFaltando" and r() == 3, f"{t}: sem a chave NÃO gasta")
        if fido:
            antes = r()
            e = dict(base, fido=Ch().prov); ok(tenta(pp, **e) == "FidoErro" and r() == antes, f"{t}: chave FIDO errada NÃO gasta (o toque vem antes)")
            e = dict(base, fido=None); ok(tenta(pp, **e) == "FatorFaltando" and r() == antes, f"{t}: sem FIDO NÃO gasta")
            e = dict(base, recuperacao=c.nova_chave_acesso()[1]); e.pop("fido")
            ok(tenta(pp, **e) == "SenhaIncorreta" and r() == antes - 1, f"{t}: código de recuperação errado gasta 1")
            e = dict(base, recuperacao=rec); e.pop("fido"); ok(tenta(pp, **e) == "ABRIU" and r() == 5, f"{t}: recuperação certa abre e devolve as tentativas")
        ok(tenta(pp, **base) == "ABRIU" and r() == 5, f"{t}: tudo certo abre e o contador volta ao máximo")
        # esgotar: a última errada destrói
        fim = None
        for i in range(8):
            try: c.Cofre.abrir(pp, **dict(base, senha="errada errada errada errada 1"))
            except c.CofreDestruido: fim = i; break
            except c.SenhaIncorreta: pass
        ok(fim == 4 and not os.path.exists(pp), f"{t}: 5 erros seguidos destroem o cofre (na 5ª)")

# ---------- 5) memória do processo (Linux): segredos não ficam depois de fechar/destruir
if sys.platform.startswith("linux"):
    filho = textwrap.dedent('''
        import sys, os, gc, tempfile
        sys.path.insert(0, %r)
        import cofre_senhas as c
        def mk(*partes): return "".join(partes)
        S = [mk("Banco-Zeta", "Quimica-77"), mk("usuario.zeta", "@exemplo.com"), mk("S3nh@-Ultra-", "Secreta-9981"), mk("nota-confi", "dencial-xyz-42")]
        MESTRA = mk("frase-mestra-", "longa-do-teste-0001")
        ERRADA = mk("errada-mui", "to-errada-9988")
        d = tempfile.mkdtemp(); p = os.path.join(d, "c.dat")
        v = c.Cofre.criar(p, MESTRA, 2, c.MODO_S, "alto")
        v.registros.append(c.novo_item(servico=S[0], login=S[1], senha=S[2], notas=S[3]))
        v.salvar(); v.fechar()
        v = c.Cofre.abrir(p, senha=MESTRA); _ = [r.get("senha") for r in v.registros]
        v.fechar(); v = None
        for i in range(2):
            try: c.Cofre.abrir(p, senha=ERRADA)
            except (c.SenhaIncorreta, c.CofreDestruido): pass
        # o que a interface faz com o que o usuário digitou: apaga o texto da memória
        c.zerar_objeto(ERRADA); c.zerar_objeto(MESTRA)
        for s in S: c.zerar_objeto(s)
        del S, MESTRA, ERRADA, _
        gc.collect()
        alvos = [b"Zeta" + b"Quimica-77", b"usuario.zeta" + b"@exemplo.com", b"S3nh@-Ultra-" + b"Secreta-9981", b"nota-confi" + b"dencial-xyz-42",
                 b"frase-mestra-" + b"longa-do-teste-0001", b"errada-mui" + b"to-errada-9988"]
        alvos = [a.replace(b"ZetaQuimica", b"Banco-ZetaQuimica") if a.startswith(b"ZetaQ") else a for a in alvos]
        alvos.append(b"controle-nun" + b"ca-usado-no-cofre-55")          # CONTROLE: só existe na própria varredura (mede o ruído dela)
        achados = {}
        with open("/proc/self/maps") as mp, open("/proc/self/mem", "rb", 0) as mem:
            for linha in mp:
                ini, fim = [int(x, 16) for x in linha.split()[0].split("-")]
                if "r" not in linha.split()[1] or "[vvar]" in linha or "[vsyscall]" in linha: continue
                try: mem.seek(ini); dados = mem.read(fim - ini)
                except (OSError, OverflowError, ValueError): continue
                for a in alvos:
                    for cod in (a, a.decode().encode("utf-16-le")):
                        n = dados.count(cod)
                        if n: achados[a.decode()] = achados.get(a.decode(), 0) + n
        base = achados.pop("controle-nunca-usado-no-cofre-55", 0)
        extra = {k: v - base for k, v in achados.items() if v > base}
        print("BASE", base, "ACHADOS", extra)
    ''') % RAIZ
    out = subprocess.run([sys.executable, "-c", filho], capture_output=True, text=True, timeout=300)
    linha = [x.split("ACHADOS", 1)[1].strip() and "ACHADOS" + x.split("ACHADOS", 1)[1] for x in out.stdout.splitlines() if "ACHADOS" in x]
    print("   ", linha[0] if linha else out.stderr[-400:])
    ok(bool(linha) and linha[0] == "ACHADOS {}", "memória do processo: nenhum segredo (serviço, login, senha, notas, senha mestra, tentativa errada) sobra depois de fechar/destruir")
print("FALHAS:", f.count(False)); sys.exit(1 if False in f else 0)
