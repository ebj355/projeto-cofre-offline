"""Fator extra 'computador autorizado' (MachineGuid + UUID da placa-mãe): o computador entra na derivação da chave.
Computadores simulados trocando c.identidades_do_pc. Verifica: abre só em computador autorizado, outro computador é
recusado SEM gastar tentativa, o código de recuperação abre em qualquer um, vários computadores, remover/desativar,
combinação com FIDO (A MAIS, nunca alternativa), compatibilidade com cofres sem o fator, corrupção/adulteração,
memória zerada ao fechar e o leitor da tabela SMBIOS."""
import os, sys, tempfile, hmac, hashlib, secrets
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
import cofre_senhas as c
f = []
def ok(cond, nome):
    """Registra uma verificação."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
cp = lambda t: "".join(list(t))                    # cópia nova: o cofre zera na memória a str que recebe
SEN = "cavalo azul come pizza na chuva"
W = tempfile.mkdtemp(prefix="pc_")
def ident(nome):
    """Identidade simulada de um computador."""
    return [hashlib.sha256(b"pc-" + nome.encode() + b"-GU").digest(), hashlib.sha256(b"pc-" + nome.encode() + b"-G").digest()]
def em(nome):
    """Passa a 'ser' o computador `nome`."""
    c.identidades_do_pc = lambda: ident(nome)
def abre(p, **k):
    """Abre o cofre com a senha certa."""
    return c.Cofre.abrir(p, senha=cp(SEN), **k)
def nova(nome):
    """Cria um cofre novo (modo só-senha) com um item."""
    p = os.path.join(W, nome + ".dat")
    v = c.Cofre.criar(p, cp(SEN), 5, c.MODO_S, "alto"); v.registros.append(c.novo_item(servico="Banco", login="a", senha="s-1")); v.salvar(); v.fechar()
    return p

# 1) sem o fator: nada muda (cofre antigo continua abrindo; formato idêntico)
em("A"); p = nova("a")
ok(c.info_pc(p) == (False, True), "cofre sem o fator: info_pc = (False, True)")
v = abre(p); ok(v.pc is None and len(v.registros) == 1, "cofre sem o fator abre normal"); antes = open(p, "rb").read(); v.fechar()
ok(antes[c.HEADER_LEN5 + 1] == 0, "formato antigo preservado (marca de fatores extras = 0)")

# 2) autorizar o computador A
v = abre(p); cod = v.pc_adicionar("Desktop"); ok(bool(cod) and len(v.pc["maquinas"]) == 1, "primeiro computador devolve o código de recuperação")
v.salvar(); v.fechar()
ok(c.info_pc(p) == (True, True), "info_pc no computador A: exige e está autorizado")
v = abre(p); ok(len(v.registros) == 1 and v.pc_id_deste() is not None, "abre no computador A (autorizado)"); v.fechar()
# 3) computador B: recusado SEM gastar tentativa
em("B"); r0 = c.tentativas_restantes(p)
ok(c.info_pc(p) == (True, False), "info_pc no computador B: exige e NÃO está autorizado")
try: abre(p); res = "abriu"
except c.PcNaoAutorizado: res = "recusado"
except Exception as ex: res = type(ex).__name__
ok(res == "recusado", "computador B é recusado (PcNaoAutorizado)")
ok(c.tentativas_restantes(p) == r0, "recusa do computador B NÃO gasta tentativa")
ok(issubclass(c.PcNaoAutorizado, c.FatorFaltando), "a interface trata como 'fator faltando' (sem tentativa)")
# 4) código de recuperação abre no B; senha errada com código certo gasta; código errado gasta
v = abre(p, recuperacao=cod); ok(len(v.registros) == 1, "código de recuperação abre em outro computador"); v.fechar()
r1 = c.tentativas_restantes(p)
try: c.Cofre.abrir(p, senha=cp("senha errada"), recuperacao=cod); res = "abriu"
except c.SenhaIncorreta: res = "errada"
ok(res == "errada" and c.tentativas_restantes(p) == r1 - 1, "senha errada (código certo) gasta 1 tentativa")
v = abre(p, recuperacao=cod); v.fechar()
r2 = c.tentativas_restantes(p)
try: abre(p, recuperacao=c.nova_chave_acesso()[1]); res = "abriu"
except c.SenhaIncorreta: res = "errada"
ok(res == "errada" and c.tentativas_restantes(p) == r2 - 1, "código de recuperação errado gasta 1 tentativa")
# 5) autorizar B estando no B (aberto com o código); A continua abrindo
v = abre(p, recuperacao=cod); ok(v.pc_adicionar("Notebook") is None and len(v.pc["maquinas"]) == 2, "segundo computador autorizado (sem novo código)")
try: v.pc_adicionar("de novo"); res = "ok"
except ValueError: res = "dup"
ok(res == "dup", "o mesmo computador não entra duas vezes"); v.salvar(); v.fechar()
for nome in ("A", "B"):
    em(nome); v = abre(p); ok(len(v.registros) == 1, f"abre nos dois computadores ({nome})"); v.fechar()
# 6) remover A: A deixa de abrir; B continua
em("B"); v = abre(p); ida = c._id_pc(v.pc["salt"], ident("A")[0])
v.pc_remover(ida); v.salvar(); v.fechar()
em("A"); ok(c.info_pc(p) == (True, False), "A removido: não está mais autorizado")
em("B"); v = abre(p); ok(len(v.registros) == 1, "B continua abrindo")
try: v.pc_remover(v.pc_id_deste()); res = "ok"
except ValueError: res = "ultimo"
ok(res == "ultimo", "não remove o único computador"); v.fechar()
# 7) um computador ROUBADO só com a senha e o arquivo não abre; uma cópia de backup idêntica também exige
bk = os.path.join(W, "backup.dat"); open(bk, "wb").write(open(p, "rb").read())
em("C"); 
try: c.Cofre.abrir(bk, senha=cp(SEN)); res = "abriu"
except c.PcNaoAutorizado: res = "recusado"
ok(res == "recusado", "cópia do arquivo em outro computador também é recusada")
# 8) combinação com FIDO: o computador é A MAIS
segredos = {}
def fido_prov(creds, salt):
    """Chave FIDO simulada."""
    for cid in creds:
        if cid in segredos: return cid, hmac.new(segredos[cid], salt, hashlib.sha256).digest()
    raise c.FidoErro("não cadastrada")
em("A"); q = nova("q")
v = abre(q); cid = secrets.token_bytes(48); segredos[cid] = secrets.token_bytes(32)
cf = v.adicionar_fido("Chave", cid, hmac.new(segredos[cid], v.salt_fido(), hashlib.sha256).digest()); v.salvar()
cod2 = v.pc_adicionar("Desktop"); ok(bool(cod2) and cod2 != cf, "com FIDO já ativo, autorizar PC gera um NOVO código único (o antigo deixa de valer)")
v.salvar(); v.fechar()
v = abre(q, fido=fido_prov); ok(len(v.registros) == 1, "senha + FIDO + computador A abre")
v.fechar()
try: abre(q); res = "abriu"
except c.FatorFaltando: res = "faltou"
ok(res == "faltou", "sem a chave FIDO não abre (mesmo no computador autorizado)")
em("B")
try: abre(q, fido=fido_prov); res = "abriu"
except c.PcNaoAutorizado: res = "recusado"
ok(res == "recusado", "com a chave FIDO, mas em computador não autorizado, NÃO abre (PC é fator a mais)")
try: abre(q, recuperacao=cf); res = "abriu"
except c.SenhaIncorreta: res = "antigo"
ok(res == "antigo", "o código ANTIGO (anterior ao PC) não vale mais")
v = abre(q, recuperacao=cod2); ok(len(v.registros) == 1, "código único abre no outro computador sem a chave FIDO"); v.fechar()
em("A"); v = abre(q, fido=fido_prov); v.salvar(); v.fechar()
v = abre(q, fido=fido_prov); v.desativar_pc(); v.salvar(); v.fechar()
ok(c.info_pc(q) == (False, True), "desativar o fator: cofre volta a depender só do FIDO")
em("B"); v = abre(q, fido=fido_prov); ok(len(v.registros) == 1, "sem o fator, B abre com a chave FIDO"); v.fechar()
# 9) adulteração / corrupção
em("A"); r = nova("r"); v = abre(r); v.pc_adicionar("X"); v.salvar(); v.fechar()
raw = bytearray(open(r, "rb").read()); hl = c.HEADER_LEN5
for off, nome in ((hl + 1, "flag"), (hl + 2 + 5, "n/sal"), (hl + 40 + 80, "wrap")):
    t = bytearray(raw); t[off] ^= 0x55; q2 = os.path.join(W, "adult.dat"); open(q2, "wb").write(bytes(t))
    try: abre(q2); res = "abriu"
    except (c.ArquivoCorrompido, c.ArquivoInvalido, c.SenhaIncorreta, c.CofreDestruido, c.FatorFaltando): res = "recusou"
    ok(res == "recusou", f"byte alterado ({nome}) não abre")
# 10) memória: fator zerado ao fechar
v = abre(r); G = v._G; ok(G is not None and any(G), "fator em memória enquanto aberto"); v.fechar()
ok(v._G is None, "fator descartado ao fechar")
# 11) limite
em("A"); s2 = nova("s"); v = abre(s2)
n = 0
for i in range(c.MAX_PC + 2):
    em("PC%d" % i)
    try: v.pc_adicionar("pc%d" % i); n += 1
    except ValueError: break
ok(n == c.MAX_PC, f"limite de {c.MAX_PC} computadores"); v.fechar()
# 12) SMBIOS
def tipo(t, dados): return bytes([t, 4 + len(dados), 0, 0]) + dados + b"\x00\x00"
u = bytes(range(1, 17)); t1 = bytes([1, 0x1b, 1, 0]) + bytes(4) + u + bytes(0x1b - 4 - 4 - 16) + b"\x00\x00"
t0 = bytes([0, 0x08, 0, 0, 1, 2, 3, 4]) + b"\x00\x00"
ok(c._uuid_de_smbios(t0 + t1 + bytes([127, 4, 0, 0, 0, 0])) == u, "SMBIOS: UUID do tipo 1 lido")
zeros = bytes([1, 0x1b, 1, 0]) + bytes(4) + bytes(16) + bytes(0x1b - 24) + b"\x00\x00"
ok(c._uuid_de_smbios(t0 + zeros) is None, "SMBIOS: UUID zerado é ignorado")
ok(c._uuid_de_smbios(b"") is None and c._uuid_de_smbios(b"\x01\x02\x03") is None and c._uuid_de_smbios(bytes([1, 2, 0, 0])) is None, "SMBIOS: lixo/curto não quebra")
ok(c._smbios_uuid() is None or isinstance(c._smbios_uuid(), bytes), "fora do Windows a leitura nativa devolve None")
print("FALHAS:", f.count(False)); sys.exit(1 if False in f else 0)
