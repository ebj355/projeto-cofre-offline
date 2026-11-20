"""QUEDA DE ENERGIA EM PONTOS EXATOS: em vez de matar o programa em instantes aleatórios, derruba o processo (os._exit, sem
nenhuma limpeza) EXATAMENTE em cada passo da gravação: depois de escrever o .tmp (antes do fsync), depois do fsync, antes e
depois de CADA renomeação (rotação das cópias .bak e troca final). Em todos os pontos o cofre principal e cada cópia que
existir devem abrir com a senha certa, com tudo que já tinha sido confirmado; um .tmp que sobrou não atrapalha, e a gravação
seguinte funciona."""
import os, sys, tempfile, subprocess, importlib.util
AQUI = os.path.dirname(os.path.abspath(__file__))
CAMINHO_PROG = os.path.abspath(os.path.join(AQUI, "..", "..", "cofre_senhas.py"))
spec = importlib.util.spec_from_file_location("c", CAMINHO_PROG)
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
FAL = []


def ok(cond, msg):
    print(("  [OK]   " if cond else "  [FALHOU] ") + msg, flush=True)
    if not cond:
        FAL.append(msg)


FILHO = r'''
import os, sys, importlib.util
spec = importlib.util.spec_from_file_location("c", sys.argv[1])
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
caminho, senha, evento, k, depois = sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]), sys.argv[6] == "depois"
conta = {"n": 0}
real = getattr(os, evento)
def gancho(*a, **kw):
    conta["n"] += 1
    if conta["n"] == k and not depois:
        os._exit(9)                       # queda ANTES deste passo
    r = real(*a, **kw)
    if conta["n"] == k and depois:
        os._exit(9)                       # queda DEPOIS deste passo
    return r
setattr(os, evento, gancho)
v = c.Cofre.abrir(caminho, senha=senha)
v.registros.append({"id": "novo", "servico": "NOVO", "login": "u", "senha": "x", "notas": ""})
v.salvar(forcar_copia=True)
os._exit(0)
'''
S = "cavalo azul come pizza na chuva 2026"
pontos = [(ev, k, dep) for ev in ("fsync", "replace") for k in range(1, 9) for dep in ("antes", "depois")]
total = quedas = 0
for ev, k, dep in pontos:
    d = tempfile.mkdtemp(); P = os.path.join(d, "cofre.dat")
    v = c.Cofre.criar(P, S, 3, 0, "alto")
    for i in range(3):
        v.registros.append({"id": f"i{i}", "servico": f"Serv{i}", "login": "u", "senha": f"s{i}", "notas": ""})
        v.salvar(forcar_copia=True)               # deixa .bak1 .. .bak3 cheias, para a rotação ter o que empurrar
    v.fechar()
    r = subprocess.run([sys.executable, "-c", FILHO, CAMINHO_PROG, P, S, ev, str(k), dep], capture_output=True, text=True)
    total += 1
    if r.returncode == 0:
        continue                                   # o ponto k não existe nessa gravação (nada caiu)
    quedas += 1
    rotulo = f"{ev}#{k} {dep}"
    try:
        a = c.Cofre.abrir(P, senha=S)
        itens = {x["id"].encode().decode() for x in a.registros}      # cópia NOVA (fechar() zera os textos do cofre no lugar)
        a.fechar()
        bom = {"i0", "i1", "i2"} <= itens
        ok(bom, f"queda {rotulo}: o cofre abre e mantém os 3 itens confirmados" + ("" if "novo" not in itens else " (+ o novo)"))
    except Exception as ex:
        ok(False, f"queda {rotulo}: o cofre NÃO abriu ({type(ex).__name__}: {ex})")
        continue
    for b in c._copias(P):
        if os.path.exists(b):
            try:
                with open(b, "rb") as f:
                    c._ler_cabecalho(f.read())
            except Exception as ex:
                ok(False, f"queda {rotulo}: a cópia {os.path.basename(b)} ficou ilegível ({ex})")
    try:                                           # a gravação seguinte funciona mesmo com .tmp sobrando
        a = c.Cofre.abrir(P, senha=S); a.registros.append({"id": "dep", "servico": "D", "login": "u", "senha": "x", "notas": ""})
        a.salvar(forcar_copia=True); a.fechar()
    except Exception as ex:
        ok(False, f"queda {rotulo}: não conseguiu gravar depois ({ex})")
print(f"\n{quedas} quedas simuladas em {total} pontos testados; falhas: {len(FAL)}")
ok(quedas >= 20, f"o teste realmente derrubou o processo em {quedas} pontos distintos (mínimo 20)")
for f in FAL:
    print("  -", f)
sys.exit(1 if FAL else 0)
