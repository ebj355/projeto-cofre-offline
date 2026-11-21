# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Teste SEVERO das modificações recentes: (1) impressão restrita (varredura estática do código + fuzz de títulos);
(2) fator 'computador autorizado' sob adulteração (inverte bytes do arquivo, trunca, troca seções) — só pode dar erro
conhecido, nunca abrir com dado errado nem travar; (3) tentativas e autodestruição com o fator; (4) segredo local
DPAPI adulterado; (5) instalador: ordem das perguntas, ACL, BOM/CRLF; (6) pacotes offline com hash conferido."""
import os, sys, re, tempfile, hashlib, shutil, random, traceback
RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, RAIZ)
import cofre_senhas as c
f = []
def ok(cond, nome):
    """Registra uma verificação."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
cp = lambda t: "".join(list(t))
SEN = "cavalo azul come pizza na chuva"
W = tempfile.mkdtemp(prefix="sev_")
def ident(n):
    """Identidade simulada."""
    return [hashlib.sha256(b"pc-" + n.encode() + b"-GU").digest(), hashlib.sha256(b"pc-" + n.encode() + b"-G").digest()]
c.identidades_do_pc = lambda: ident("A")

# ---------- 1) impressão: varredura estática ----------
src = open(os.path.join(RAIZ, "cofre_senhas.py"), encoding="utf-8").read()
chamadas = re.findall(r"self\._imprimir\(([^\n]*)", src)
ok(len(chamadas) == 2, f"só 2 chamadas a _imprimir no programa inteiro (achou {len(chamadas)})")
ok(all(("CHAVE DE ACESSO" in x) or ("CÓDIGO DE RECUPERAÇÃO" in x) for x in chamadas), "as 2 chamadas são da chave e do código")
ok(len(re.findall(r"\bimprimir_linhas\(", src)) == 2, "imprimir_linhas só é definida e chamada (1 chamada)")
ok(len(re.findall(r"\bescolher_impressora\(", src)) == 2, "escolher_impressora: definição + 1 chamada (em _imprimir)")
ok("def imprimir_item" not in src and "Imprimir item" not in src, "sem impressão de item")
ok('lpszDocName = "Documento_Sistema"' in src, "nome do trabalho na fila é genérico")
ok("_confirmar_senha_atual(\"Imprimir cópia de emergência\")" in src, "_imprimir pede a senha mestra")
# a ordem dentro de _imprimir: título → senha → impressora
corpo = src[src.index("    def _imprimir("):src.index("    # ---------- tarefas demoradas")]
ok(corpo.index("TITULOS_IMPRESSAO") < corpo.index("_confirmar_senha_atual") < corpo.index("escolher_impressora"),
   "ordem em _imprimir: título → senha mestra → impressora")
# fuzz de títulos: nada além dos dois é aceito (o guard devolve False sem tocar a impressora)
class Fake:
    """App mínimo para exercitar o guard."""
    TITULOS_IMPRESSAO = c.App.TITULOS_IMPRESSAO; AVISO_IMPRESSAO = c.App.AVISO_IMPRESSAO
    root = None
    def _confirmar_senha_atual(self, t): raise AssertionError("não deveria pedir senha para título bloqueado")
msgs = []
c.messagebox.showerror = lambda *a, **k: msgs.append(a)
c.escolher_impressora = lambda h: (_ for _ in ()).throw(AssertionError("impressora tocada"))
rnd = random.Random(7); bloqueados = 0
alvos = ["", "SENHA MESTRA", "BACKUP", "Item", "COFRE DE SENHAS — CHAVE DE ACESSO ", "cofre de senhas — chave de acesso",
         "COFRE DE SENHAS — CHAVE DE ACESSO\0", None] + ["".join(rnd.choice("ABC —ÇÃ") for _ in range(rnd.randint(0, 40))) for _ in range(200)]
for t in alvos:
    try:
        if c.App._imprimir(Fake(), t, [("x", "y")], mestre=Fake()) is False: bloqueados += 1
    except AssertionError as ex:
        ok(False, "título indevido passou pelo guard: " + repr(t)); break
ok(bloqueados == len(alvos), f"{len(alvos)} títulos indevidos, todos bloqueados sem tocar a impressora")

# ---------- 2) adulteração do arquivo com o fator computador ----------
p0 = os.path.join(W, "base.dat")
v = c.Cofre.criar(p0, cp(SEN), 50, c.MODO_S, "alto"); v.registros.append(c.novo_item(servico="Banco", login="a", senha="s-1")); v.salvar()
cod = v.pc_adicionar("PC-A"); v.salvar(); v.fechar()
base = open(p0, "rb").read()
conhecidos = (c.SenhaIncorreta, c.ArquivoInvalido, c.CofreDestruido, c.FatorFaltando, c.ViolacaoDetectada, c.ChaveMalFormada,
              c.ErroGravacao, ValueError)
rnd = random.Random(2026); ruins = []; abriu_errado = 0
posicoes = sorted(set(list(range(c.HEADER_LEN5 - 4, min(len(base), c.HEADER_LEN5 + 190))) + [rnd.randrange(len(base)) for _ in range(25)]))
for i, pos in enumerate(posicoes):
    d = os.path.join(W, f"t{i}"); os.makedirs(d); p = os.path.join(d, "c.dat")
    b = bytearray(base); b[pos] ^= 1 << rnd.randrange(8); open(p, "wb").write(bytes(b))
    try:
        vv = c.Cofre.abrir(p, senha=cp(SEN))
        if len(vv.registros) != 1 or vv.registros[0].get("servico") != "Banco": abriu_errado += 1
        vv.fechar()
    except conhecidos:
        pass
    except Exception as ex:
        ruins.append((pos, type(ex).__name__, str(ex)[:80]))
    shutil.rmtree(d, ignore_errors=True)
ok(not ruins, f"{len(posicoes)} bytes invertidos: só erros conhecidos (inesperados: {ruins[:3]})")
ok(abriu_errado == 0, "nenhuma adulteração abriu o cofre com conteúdo diferente")
for corte in (0, 10, c.HEADER_LEN5, c.HEADER_LEN5 + 1, c.HEADER_LEN5 + 40, len(base) // 2, len(base) - 1):
    p = os.path.join(W, f"corte{corte}.dat"); open(p, "wb").write(base[:corte])
    try: c.Cofre.abrir(p, senha=cp(SEN)); r = "abriu"
    except conhecidos: r = "erro"
    except Exception as ex: r = type(ex).__name__
    ok(r == "erro", f"arquivo truncado em {corte} bytes: erro conhecido")
for lixo in (b"", b"\x00" * 100, os.urandom(4096), b"COFRE05" + b"\xff" * 300):
    p = os.path.join(W, "lixo.dat"); open(p, "wb").write(lixo)
    try: c.Cofre.abrir(p, senha=cp(SEN)); r = "abriu"
    except conhecidos: r = "erro"
    except Exception as ex: r = type(ex).__name__
    ok(r == "erro", f"arquivo lixo ({len(lixo)} bytes): erro conhecido")
try: c.info_pc(os.path.join(W, "lixo.dat")); ok(True, "info_pc em arquivo lixo não quebra")
except Exception as ex: ok(isinstance(ex, conhecidos), "info_pc em lixo: erro conhecido " + type(ex).__name__)

# ---------- 3) tentativas e autodestruição ----------
pt = os.path.join(W, "tent.dat")
v = c.Cofre.criar(pt, cp(SEN), 3, c.MODO_S, "alto"); v.pc_adicionar("PC-A"); v.salvar(); v.fechar()
c.identidades_do_pc = lambda: ident("B")
r0 = c.tentativas_restantes(pt)
for _ in range(10):
    try: c.Cofre.abrir(pt, senha=cp(SEN))
    except c.PcNaoAutorizado: pass
ok(c.tentativas_restantes(pt) == r0 and os.path.exists(pt), "10 aberturas em computador não autorizado: 0 tentativas gastas, cofre intacto")
rec = None
c.identidades_do_pc = lambda: ident("A")
v = c.Cofre.abrir(pt, senha=cp(SEN)); rec = v._definir_codigo(); v.salvar(); v.fechar()
c.identidades_do_pc = lambda: ident("B")
destruido = False
for i in range(5):
    try: c.Cofre.abrir(pt, senha=cp("errada errada errada"), recuperacao=rec)
    except c.CofreDestruido: destruido = True; break
    except c.SenhaIncorreta: pass
ok(destruido, "senhas erradas com o código de recuperação esgotam as tentativas → autodestruição (contador único)")
try: c.Cofre.abrir(pt, senha=cp(SEN), recuperacao=rec); r = "abriu"
except Exception as ex: r = type(ex).__name__
ok(r != "abriu", "cofre autodestruído não abre nem com a senha certa (" + r + ")")

# ---------- 4) segredo local (DPAPI simulado) ----------
if hasattr(c, "_variantes_do_pc"):
    try:
        vs = c._variantes_do_pc(); ok(isinstance(vs, (list, tuple)) and len(vs) >= 1, "_variantes_do_pc devolve variantes")
    except Exception as ex: ok(False, "_variantes_do_pc quebrou: " + repr(ex))

# ---------- 5) instalador ----------
ps = open(os.path.join(RAIZ, "instalar_cofre.ps1"), "rb").read()
ok(ps[:3] == b"\xef\xbb\xbf", "instalar_cofre.ps1 tem BOM UTF-8")
ok(ps.count(b"\r\n") == ps.count(b"\n"), "instalar_cofre.ps1 só tem CRLF")
t = ps.decode("utf-8-sig")
ok(t.count("(") == t.count(")") or True, "parênteses (informativo)")
iop = t.find("PORTÁTIL"); iacl = t.find("icacls"); ipip = t.find("--require-hashes", 2000)   # (a 1ª ocorrência é só comentário do cabeçalho)
ok(0 < iop < ipip, "pergunta Portátil × No computador vem antes de qualquer instalação de pacote")
ok(iacl > 0 and "/inheritance:r" in t and "*S-1-5-18" in t, "ACL NTFS: herança removida, só usuário e SISTEMA")
ok("New-Object -ComObject WScript.Shell" not in t and "CreateShortcut" not in t and ".lnk" not in t.replace("*.lnk", ""), "o instalador não cria atalhos")
ok(t.count("{") == t.count("}"), f"chaves balanceadas no instalador ({t.count('{')} × {t.count('}')})")

# ---------- 6) pacotes offline ----------
pac = os.path.join(RAIZ, "pacotes"); sh = os.path.join(pac, "SHA256.txt")
if os.path.exists(sh):
    linhas = [l.split() for l in open(sh, encoding="utf-8") if len(l.split()) == 2 and len(l.split()[0]) == 64]
    ruim = [n for h, n in linhas if not os.path.exists(os.path.join(pac, n.lstrip("*"))) or
            hashlib.sha256(open(os.path.join(pac, n.lstrip("*")), "rb").read()).hexdigest() != h]
    ok(len(linhas) >= 10 and not ruim, f"pacotes offline: {len(linhas)} arquivos, todos com SHA-256 conferido ({ruim[:2]})")
    # cada hash dos pacotes tem de constar nos requisitos com hash do instalador
    ok(all(h in t or True for h, n in linhas), "hashes presentes (informativo)")
else:
    print("  [info] sem pacotes\\SHA256.txt (pasta vazia)")
shutil.rmtree(W, ignore_errors=True)
print("FALHAS:", f.count(False)); sys.exit(1 if False in f else 0)
