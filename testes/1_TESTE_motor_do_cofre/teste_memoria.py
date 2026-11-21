# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Varredura de memória com 'palavras-isca': depois de fechar o cofre e varrer a memória livre, as iscas de itens
(senha e PIN) não podem sobrar no processo além do piso do próprio teste (argv do sistema). Linux/CPython."""
import os, re, secrets, subprocess, sys, tempfile
raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ALVO = r'''
import sys, os, gc, tempfile
sys.path.insert(0, sys.argv[1]); import cofre_senhas as c
def passo(n): print(n, flush=True); sys.stdin.readline()
d = tempfile.mkdtemp(); p = os.path.join(d, "c.dat")
S = "".join(list(sys.argv[2]))
c.Cofre.criar(p, S, 3, 0, "alto")
v = c.Cofre.abrir(p, senha="".join(list(S)))
v.registros.append(c.novo_item(servico="x", senha="".join(list(sys.argv[3])), pin="".join(list(sys.argv[4]))))
v.salvar(); v.fechar(); v = None
for i in (2, 3, 4): c.zerar_objeto(sys.argv[i])
v = c.Cofre.abrir(p, senha="".join(list(S)))
passo("ABERTO")
v.fechar(); v = None; c.varrer_memoria_livre()
passo("FECHADO")
'''
S = "Mestra" + secrets.token_hex(8) + "Aa1!"; R = "ISCAREG" + secrets.token_hex(10); P = "PINISCA" + secrets.token_hex(10)
pr = subprocess.Popen([sys.executable, "-c", ALVO, raiz, S, R, P], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
def varrer(pid, ag):
    out = {k: 0 for k in ag}
    with open(f"/proc/{pid}/maps") as m, open(f"/proc/{pid}/mem", "rb", 0) as mem:
        for l in m:
            mt = re.match(r"([0-9a-f]+)-([0-9a-f]+) (\S+)", l)
            if not mt or "r" not in mt.group(3): continue
            a, b = int(mt.group(1), 16), int(mt.group(2), 16)
            if b - a > 1 << 30: continue
            try: mem.seek(a); dat = mem.read(b - a)
            except Exception: continue
            for k, v in ag.items(): out[k] += dat.count(v.encode()) + dat.count(v.encode("utf-16-le"))
    return out
res = {}
while True:
    l = pr.stdout.readline().strip()
    if not l: break
    res[l] = varrer(pr.pid, {"registro": R, "pin": P}); print(l, res[l])
    pr.stdin.write("\n"); pr.stdin.flush()
pr.wait()
f = res.get("FECHADO", {}); a = res.get("ABERTO", {})
ok = all(f.get(k, 99) <= 2 for k in ("registro", "pin"))          # 2 = piso (argv/ambiente do sistema)
print(f"  [{'OK' if ok else 'FALHOU'}] iscas de senha e PIN não sobram na RAM depois de fechar (abertas: {a}, fechadas: {f})")
sys.exit(0 if ok else 1)
