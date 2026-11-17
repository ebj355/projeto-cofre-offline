"""Falha de memória no meio do Argon2 não tranca nem estraga o cofre (todos os modos) e o sorteio de palavras da frase-senha é uniforme."""
import os, sys, tempfile, math, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import cofre_senhas as c
FAL = []
def ok(cond, msg):
    print(("  [OK]   " if cond else "  [FALHOU] ") + msg)
    if not cond: FAL.append(msg)
S = "cavalo azul come pizza na chuva"
d = tempfile.mkdtemp(); P = os.path.join(d, "cofre.dat")

print("== 1.3 falha de memória na 2ª derivação não tranca o cofre")
for modo in (c.MODO_OU, c.MODO_E):
    v = c.Cofre.criar(P, S, 3, modo, "alto")
    chave = v.chave_gerada
    v.registros.append({"id": "1", "servico": "A", "login": "x", "senha": "segredo1"}); v.salvar()
    sal0, wrap0 = v.sal_pw, v.wrap_pw
    orig = c.derivar_chave
    def falha(*a, **k): raise MemoryError("sem memória")
    c.derivar_chave = falha
    try:
        try: v._definir_senha("outra senha bem comprida 2026 xyz"); r = "passou"
        except MemoryError: r = "mem"
    finally:
        c.derivar_chave = orig
    ok(r == "mem" and v.sal_pw == sal0 and v.wrap_pw == wrap0, f"modo {modo}: sal e embrulho intactos após falha")
    v.salvar()
    w = c.Cofre.abrir(P, senha=S, chave=chave if modo == c.MODO_E else None)
    ok(len(w.registros) == 1, f"modo {modo}: cofre salvo depois da falha ainda abre com a senha antiga")
    # falha na SEGUNDA derivação durante a renormalização NFC (cofre gravado em NFD)
    import unicodedata
    senha_acento = "Pão de açúcar com café 2026!"
    c.destruir(P)
    nfd = unicodedata.normalize("NFD", senha_acento)
    v = c.Cofre.criar(P, nfd, 3, modo, "alto")
    chave = v.chave_gerada
    v._definir_senha(nfd, normalizar=False); v.salvar()
    n = {"i": 0}
    def segunda_falha(*a, **k):
        n["i"] += 1
        if n["i"] >= 2: raise MemoryError("sem memória")
        return orig(*a, **k)
    c.derivar_chave = segunda_falha
    try:
        try: w = c.Cofre.abrir(P, senha=senha_acento, chave=chave if modo == c.MODO_E else None); r = "abriu"
        except Exception as e: r = type(e).__name__
    finally:
        c.derivar_chave = orig
    ok(r in ("abriu", "MemoryError"), f"modo {modo}: abrir com 2ª derivação falhando não quebra ({r})")
    try:
        w2 = c.Cofre.abrir(P, senha=senha_acento, chave=chave if modo == c.MODO_E else None)
        w2.salvar()
        w3 = c.Cofre.abrir(P, senha=senha_acento, chave=chave if modo == c.MODO_E else None)
        ok(True, f"modo {modo}: abre e regrava normalmente depois")
    except Exception as e:
        ok(False, f"modo {modo}: depois da falha o cofre não abre mais: {e!r}")
    c.destruir(P)

print("== 1.4 entropia da frase")
cont = collections.Counter()
N = 20000
for _ in range(N):
    f = c.gerar_frase(3, maiuscula=False, numero=False, separador="-")
    for w in f.split("-"):
        cont[len(w) // 2] += 1
tot = sum(cont.values()); p3 = cont[3] / tot
esperado = 75 ** 3 / (75 ** 2 + 75 ** 3)
ok(abs(p3 - esperado) < 0.01, f"palavras de 3 sílabas ocorrem {p3:.3f} (esperado uniforme {esperado:.3f})")
b5 = c.bits_frase(5, numero=False)
ok(abs(b5 - 5 * math.log2(75 ** 2 + 75 ** 3)) < 1e-9, f"bits_frase(5) = {b5:.1f}")
vistas = {c.gerar_frase(4, True, True) for _ in range(300)}
ok(len(vistas) == 300, "frases distintas")
ok(all(all(ch.isalnum() or ch == "-" for ch in x) for x in vistas), "alfabeto esperado")

print("== links e hard links na destruição")
alvo = os.path.join(d, "importante.txt"); open(alvo, "w").write("NAO PODE MUDAR")
ln = os.path.join(d, "atalho.xlsx")
try:
    os.symlink(alvo, ln); tem = True
except OSError:
    tem = False
if tem:
    c.destruir_arquivo(ln)
    ok(not os.path.lexists(ln) and open(alvo).read() == "NAO PODE MUDAR", "link simbólico: remove o link, alvo intacto")
hl = os.path.join(d, "outro_nome.xlsx"); os.link(alvo, hl)
c.destruir_arquivo(hl)
ok(not os.path.exists(hl) and open(alvo).read() == "NAO PODE MUDAR", "hard link: remove só o nome, conteúdo intacto")
p2 = os.path.join(d, "normal.xlsx"); open(p2, "wb").write(b"x" * 100)
c.destruir_arquivo(p2); ok(not os.path.exists(p2), "arquivo normal é sobrescrito e apagado")

print("== importação: linhas vazias formatadas não contam")
try:
    import openpyxl
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["Serviço", "Login", "Senha"])
    for i in range(30): ws.append([f"Conta {i}", f"u{i}", f"Sx#{i}aaaa"])
    for i in range(30050, 30060): ws.cell(row=i, column=1, value=None)
    ws.cell(row=c.LIMITE_LINHAS + 500, column=60).number_format = "0.00"
    px = os.path.join(d, "g.xlsx"); wb.save(px)
    regs, av = c.ler_planilha(px) if hasattr(c, "ler_planilha") else (None, None)
    ok(regs is not None and len(regs) == 30, f"planilha com cauda formatada vazia importa {len(regs) if regs else 0} contas")
except Exception as e:
    ok(False, f"importação: {e!r}")

print("== backup: dois cofres idênticos")
v = c.Cofre.criar(P, S, 3, c.MODO_OU, "alto")
ok(True, "criar ok")
print("\nFALHAS:", FAL)
sys.exit(1 if FAL else 0)
