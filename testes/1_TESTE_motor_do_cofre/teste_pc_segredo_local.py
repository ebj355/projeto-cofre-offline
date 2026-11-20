"""Reforço do computador autorizado com o segredo local (DPAPI no Windows; arquivo comum só em desenvolvimento).
Prova: PC reforçado NÃO abre só com a identidade (MachineGuid/UUID) — precisa do segredo; sem o segredo (outro usuário,
Windows reinstalado) cai no código de recuperação; PC não reforçado continua abrindo; misturar os dois níveis."""
import os, sys, tempfile, hashlib
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
import cofre_senhas as c
f = []
def ok(cond, nome):
    """Registra uma verificação."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
cp = lambda t: "".join(list(t))
SEN = "cavalo azul come pizza na chuva"
W = tempfile.mkdtemp(prefix="seg_")
def ident(n): return [hashlib.sha256(b"id" + n.encode()).digest()]
def em(n, usuario):
    """Computador n, usuário do Windows `usuario` (cada usuário tem a sua pasta do segredo local)."""
    c.identidades_do_pc = lambda: ident(n)
    os.environ["LOCALAPPDATA"] = os.path.join(W, "usuarios", usuario)
def abre(p, **k): return c.Cofre.abrir(p, senha=cp(SEN), **k)
p = os.path.join(W, "a.dat"); em("A", "eu")
v = c.Cofre.criar(p, cp(SEN), 5, c.MODO_S, "alto"); v.registros.append(c.novo_item(servico="B", login="a", senha="s")); v.salvar(); v.fechar()
ok(c.segredo_local() is None, "sem segredo local ainda")
v = abre(p); cod = v.pc_adicionar("Casa", local=True); v.salvar()
ok(v.pc_nivel_deste() == "local" and c.segredo_local() is not None and len(c.segredo_local()) == 32, "autorizado COM reforço; segredo criado (32 bytes)")
v.fechar()
v = abre(p); ok(len(v.registros) == 1, "abre no mesmo computador e usuário"); v.fechar()
ok(c.info_pc(p) == (True, True), "info_pc: autorizado")
# mesmo computador, outro usuário do Windows (sem o segredo): NÃO abre
em("A", "outro")
ok(c.info_pc(p) == (True, False), "mesmo computador, outro usuário do Windows: NÃO autorizado")
try: abre(p); res = "abriu"
except c.PcNaoAutorizado: res = "recusado"
ok(res == "recusado", "recusado sem gastar tentativa")
# atacante com o pendrive + senha + identidade correta do computador, mas SEM o segredo: não abre
os.environ["LOCALAPPDATA"] = os.path.join(W, "vazio")
ok(c.info_pc(p) == (True, False), "identidade certa sem o segredo local: NÃO abre")
v = abre(p, recuperacao=cod); ok(len(v.registros) == 1, "o código de recuperação abre mesmo assim"); v.fechar()
# autorizar o computador sem reforço (básico) no outro usuário
em("A", "outro"); v = abre(p, recuperacao=cod); v.pc_adicionar("Casa (outro usuário)", local=False); v.salvar()
ok(v.pc_nivel_deste() == "basico", "autorizado SEM reforço: nível básico"); v.fechar()
em("A", "outro"); v = abre(p); ok(len(v.registros) == 1, "abre no básico"); v.fechar()
em("A", "eu"); v = abre(p); ok(v.pc_nivel_deste() == "local", "o usuário reforçado continua abrindo"); v.fechar()
# criar o segredo não enfraquece: segredo corrompido = não abre (cai na recuperação)
arq = c._arquivo_segredo_local(); open(arq, "wb").write(b"lixo")
ok(c.segredo_local() is None, "segredo corrompido é ignorado")
ok(c.info_pc(p) == (True, True), "com segredo corrompido cai na embalagem BÁSICA já cadastrada (se não existisse, não abriria)")
v = abre(p, recuperacao=cod); ok(len(v.registros) == 1, "recuperação resolve"); v.fechar()
# mistura determinística
ok(c._com_segredo_local(b"x", b"s" * 32) != c._com_segredo_local(b"x", b"t" * 32) and len(c._com_segredo_local(b"x", b"s" * 32)) == 32, "mistura HMAC depende do segredo")
# local=True sem conseguir criar o segredo: recusa (não enfraquece em silêncio)
c.segredo_local = lambda criar=False: None
v = abre(p, recuperacao=cod)
try: v.pc_adicionar("Z", local=True); res = "criou"
except ValueError: res = "recusou"
ok(res == "recusou", "reforço pedido e impossível: recusa em vez de enfraquecer"); v.fechar()
print("FALHAS:", f.count(False)); sys.exit(1 if False in f else 0)
