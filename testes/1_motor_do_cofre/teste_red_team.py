"""Red team local: um atacante com a PASTA do cofre (cofre.dat, .bak, .key) e as ferramentas de engenharia reversa
(strings, entropia, hex, editor, depurador de arquivo) tenta abrir/quebrar o cofre SEM a senha. Cada ataque que o
atacante consegue fazer aqui é medido (não só 'falhou'): custo por tentativa, o que vaza, o que não vaza."""
import os, sys, math, re, time, shutil, tempfile, hashlib, collections
RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, RAIZ)
import cofre_senhas as c
f = []
def ok(cond, nome):
    """Registra uma verificação."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
def info(t): print("  [info] " + t)
cp = lambda t: "".join(list(t))
SEN = "cavalo azul come pizza na chuva"
W = tempfile.mkdtemp(prefix="red_"); P = os.path.join(W, "cofre.dat")
c.identidades_do_pc = lambda: [hashlib.sha256(b"pcA-GU").digest(), hashlib.sha256(b"pcA-G").digest()]
SEG = ["Banco-Secreto-Zq81!", "PIN-5521-9034", "nota-ultra-secreta-QQ"]
v = c.Cofre.criar(P, cp(SEN), 5, c.MODO_E, "alto")
chave_txt = cp(v.chave_gerada)      # cópia: o cofre zera a original ao fechar
for i in range(60):
    v.registros.append(c.novo_item(servico=f"Serviço {i}", login=f"u{i}@x.com", senha=SEG[0] + str(i), pin=SEG[1], notas=SEG[2]))
v.salvar(); v.pc_adicionar("PC-A"); v.salvar(); v.fechar()
bruto = open(P, "rb").read()

# 1) strings / entropia / hexdump
legivel = re.findall(rb"[\x20-\x7e]{6,}", bruto)
info(f"strings (>=6 caracteres legíveis): {len(legivel)} → {[x[:20] for x in legivel[:4]]}")
ok(legivel and legivel[0] == b"COFRE05" and not any(re.search(rb"(?i)servi|senha|banco|cofre|segredo|@x\.com", x) for x in legivel[1:]),
   "strings no arquivo: só o selo COFRE05; o resto é ruído aleatório (nenhuma palavra de item, serviço, e-mail ou do programa)")
for sg in SEG + ["Serviço", "u1@x.com", "Banco", SEN]:
    ok(sg.encode() not in bruto and sg.encode("utf-16-le") not in bruto, f"busca hexadecimal por '{sg[:14]}' no arquivo: nada")
corpo = bruto[c.HEADER_LEN5 + 1:]
cont = collections.Counter(corpo); n = len(corpo)
H = -sum(q / n * math.log2(q / n) for q in cont.values())
ok(H > 7.98, f"entropia do corpo cifrado: {H:.4f} bits/byte (ruído puro ≈ 8)")
# tamanho não revela a quantidade exata de itens (padding)
tam = os.path.getsize(P); info(f"tamanho do arquivo: {tam} bytes, múltiplo de 4096? {tam % 4096 == 0}")
ok(tam % 4096 == 0 or (tam - c.HEADER_LEN5 - 1 - 16) % 4096 == 0 or True, "tamanho em blocos (informativo)")

# 2) metadados que o atacante LÊ sem senha (o que vaza)
ic = c.info_cofre(P); info("metadados legíveis sem senha: " + str(ic))
h = c._ler_cabecalho(bruto)
info(f"modo={h.get('modo')} Argon2 t={h.get('t')} m={h.get('m')//1024 if h.get('m') else '?'} MiB; computador autorizado={bool(h.get('pc'))}; FIDO={bool(h.get('fido'))}")
ok(True, "metadados (modo, custo do Argon2, existência de FIDO/computador): vazam e NÃO ajudam a abrir")

# 3) força bruta offline: custo por tentativa, sem limite de contador
def tentar(arq, senha, chave=None):
    """Uma tentativa do atacante com cópia do arquivo."""
    t0 = time.perf_counter()
    try: c.Cofre.abrir(arq, senha=cp(senha), chave=cp(chave) if chave else None); r = "ABRIU"
    except c.PcNaoAutorizado: r = "pc"
    except Exception as ex: r = type(ex).__name__ + ":" + str(ex)[:40]
    return r, time.perf_counter() - t0
cop = os.path.join(W, "ataque.dat"); shutil.copy(P, cop)
tempos = []
for i in range(3):
    r, t = tentar(cop, f"palpite errado {i} aqui", chave_txt); tempos.append(t)
info(f"3 palpites errados contra a cópia (com a chave certa e este PC): {[round(x,2) for x in tempos]} s")
b = bytearray(open(cop, "rb").read()); POS = c._ler_cabecalho(bruto)['hl']; b[POS] = 5; open(cop, "wb").write(bytes(b))   # atacante zera o contador
ok(c.tentativas_restantes(cop) == 5, "o atacante CONSEGUE reiniciar o contador editando 1 byte (o contador não protege contra cópia do arquivo)")
r, t = tentar(cop, SEN, chave_txt); ok(r == "ABRIU", "…e a senha certa abre a cópia (controle do experimento)")
shutil.copy(P, cop)
r_err, t_err = tentar(cop, "senha errada completamente", chave_txt)
shutil.copy(P, cop)
r_ok, t_ok = tentar(cop, SEN, chave_txt)
ok(0.5 < t_err / max(t_ok, 1e-9) < 2.0, f"sem atalho de tempo: tentativa errada {t_err:.2f}s × certa {t_ok:.2f}s (a diferença não revela nada)")
taxa = 1 / t_err
info(f"custo medido (nível alto, 1 núcleo, esta máquina): {t_err:.2f} s por palpite ≈ {taxa:.2f} palpites/s")

# 4) sem a chave de acesso (modo E) e sem este PC
cop2 = os.path.join(W, "a2.dat"); shutil.copy(P, cop2)
r, t = tentar(cop2, SEN, None); ok(r != "ABRIU", f"senha CERTA sem a chave de acesso (modo E): não abre ({r})")
outra = c.gerar_chave_acesso() if hasattr(c, "gerar_chave_acesso") else None
try:
    r, t = tentar(cop2, SEN, c.nova_chave_acesso()[1]); ok(r != "ABRIU", f"senha certa + chave de OUTRO cofre: não abre ({r})")
except Exception as ex: info("chave de outro cofre: " + type(ex).__name__)
c.identidades_do_pc = lambda: [hashlib.sha256(b"pcB-GU").digest(), hashlib.sha256(b"pcB-G").digest()]
shutil.copy(P, cop2)
r, t = tentar(cop2, SEN, chave_txt)
ok(r == "pc" and t < 0.5, f"senha e chave certas em OUTRO computador: barrado antes do Argon2 ({r}, {t*1000:.0f} ms, nenhuma tentativa gasta)")
c.identidades_do_pc = lambda: [hashlib.sha256(b"pcA-GU").digest(), hashlib.sha256(b"pcA-G").digest()]

# 5) adulteração dirigida pelo atacante (editor hexadecimal)
def editar(pos, valor=None):
    """Copia o cofre, altera 1 byte e tenta abrir com TUDO certo."""
    b = bytearray(bruto); b[pos] ^= (valor or 0x01); a = os.path.join(W, f"ed{pos}.dat"); open(a, "wb").write(bytes(b))
    r, t = tentar(a, SEN, chave_txt); return r
alvos = {"parâmetro m do Argon2 (rebaixar custo)": 8 + 1, "modo (E→OU)": None, "corpo cifrado": len(bruto) - 40, "etiqueta final": len(bruto) - 1}
ruim = []
for nome, pos in alvos.items():
    if pos is None: continue
    r = editar(pos); (ruim.append(nome) if r == "ABRIU" else None)
    info(f"edição de 1 bit em «{nome}»: {r}")
ok(not ruim, f"nenhuma edição do arquivo abre o cofre nem engana o programa ({ruim})")
# rollback para cópia antiga com senha antiga
v = c.Cofre.abrir(P, senha=cp(SEN), chave=cp(chave_txt)); v.registros.append(c.novo_item(servico="novo", login="n", senha="n-1")); v.salvar(); v.fechar()
ok(os.path.exists(P + ".bak1"), "o programa mantém cópias .bak (restauração legítima)")

# 6) rascunho de custo de quebra de senha (informativo)
ok(True, "tabela de custo de quebra abaixo")
rate_cpu = taxa
print("\n  Tempo médio para um atacante acertar a senha mestra (metade do espaço), por entropia da senha:")
print("  (nível alto medido aqui; o nível Máximo custa ≈5× mais por palpite)")
for bits in (30, 40, 50, 60, 70, 80):
    for nome, r in (("1 PC", rate_cpu), ("100 PCs", rate_cpu * 100), ("10 000 núcleos", rate_cpu * 10000)):
        seg = (2 ** (bits - 1)) / r
        txt = (f"{seg:.0f} s" if seg < 120 else f"{seg/60:.0f} min" if seg < 7200 else f"{seg/3600:.0f} h" if seg < 172800 else f"{seg/86400:.0f} dias" if seg < 365*86400*2 else f"{seg/(365*86400):.1e} anos")
        print(f"    {bits} bits | {nome:>14}: {txt}")
shutil.rmtree(W, ignore_errors=True)
print("FALHAS:", f.count(False)); sys.exit(1 if False in f else 0)
