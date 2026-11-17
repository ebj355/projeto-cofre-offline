"""Queda de energia e acesso simultâneo: mata (SIGKILL) o programa no meio de gravações repetidas e confere que o cofre
SEMPRE abre com tudo que já tinha sido confirmado; duas instâncias gravando no mesmo arquivo nunca o corrompem; e a
checagem de memória livre recusa o Argon2 sem gastar tentativa. Roda no Linux (e no Windows, com Python)."""
import sys, os, random, signal, subprocess, tempfile, textwrap, time, importlib.util

AQUI = os.path.dirname(os.path.abspath(__file__))
CAMINHO_PROG = os.path.abspath(os.path.join(AQUI, "..", "..", "cofre_senhas.py"))
spec = importlib.util.spec_from_file_location("c", CAMINHO_PROG)
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
FAL = []


def ok(cond, msg):
    print(("  [OK]   " if cond else "  [FALHOU] ") + msg)
    if not cond:
        FAL.append(msg)


S = "cavalo azul come pizza na chuva"
FILHO = textwrap.dedent('''
    import sys, importlib.util, time
    spec = importlib.util.spec_from_file_location("c", sys.argv[1]); c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
    P, S, modo, segundos = sys.argv[2], sys.argv[3], sys.argv[4], float(sys.argv[5])
    fim = time.time() + segundos
    def abrir():
        while True:
            try:
                return c.Cofre.abrir(P, senha=S)
            except c.ConflitoGravacao:         # outra instância gravou no instante da abertura: abre de novo
                print("CONFLITO_AO_ABRIR", flush=True)
            except (OSError, c.ErroGravacao) as ex:   # Windows: o outro processo está trocando o arquivo neste instante
                print("ERRO_AO_ABRIR", type(ex).__name__, str(ex)[:80], flush=True)
                time.sleep(0.05)
    v = abrir(); n = len(v.registros)
    while time.time() < fim:
        v.registros.append({"id": "r%d_%d" % (id(v) % 9999, n), "servico": "S", "login": "x", "senha": "s", "nota": "n" * 60000})
        try:
            v.salvar(); n += 1
            print("OK", len(v.registros), flush=True)
        except c.ConflitoGravacao:
            print("CONFLITO", flush=True)
            v = abrir(); n = len(v.registros)
        except c.ErroGravacao as ex:               # Windows: arquivo momentaneamente ausente/preso pelo outro processo
            print("ERRO_GRAVACAO", type(ex).__name__, str(ex)[:80], flush=True)
            time.sleep(0.05)
            v = abrir(); n = len(v.registros)
''')


def novo_cofre():
    d = tempfile.mkdtemp(); P = os.path.join(d, "cofre.dat")
    c.Cofre.criar(P, S, 5, 0, "alto").salvar()
    return d, P


print("== 1) kill -9 no meio da gravação (queda de energia simulada)")
random.seed(7)
d, P = novo_cofre()
confirmados = 0; abriu_sempre = True; nunca_perdeu = True; rodadas = 8
for r in range(rodadas):
    p = subprocess.Popen([sys.executable, "-I", "-c", FILHO, CAMINHO_PROG, P, S, "q", "30"], stdout=subprocess.PIPE, text=True)
    vistos = 0
    t0 = time.time()
    while time.time() - t0 < 20:
        linha = p.stdout.readline()
        if not linha:
            break
        if linha.startswith("OK"):
            vistos = int(linha.split()[1]); confirmados = max(confirmados, vistos)
            if random.random() < 0.5:                       # mata em pontos aleatórios, logo após uma confirmação
                time.sleep(random.uniform(0, 0.05))
                break
    p.send_signal(signal.SIGKILL if hasattr(signal, "SIGKILL") else signal.SIGTERM); p.wait()
    try:
        v = c.Cofre.abrir(P, senha=S)
        if len(v.registros) < confirmados:
            nunca_perdeu = False
            print("    rodada", r, "tinha", len(v.registros), "confirmados", confirmados)
    except Exception as ex:
        abriu_sempre = False; print("    rodada", r, "NÃO abriu:", type(ex).__name__, ex)
ok(abriu_sempre, f"o cofre abriu depois de cada uma das {rodadas} mortes abruptas (arquivo principal íntegro)")
ok(nunca_perdeu, f"nada confirmado foi perdido (até {confirmados} registros confirmados)")
ok(c.tentativas_restantes(P) == 5, "as quedas não gastaram tentativas")
sobras = [f for f in os.listdir(d) if f.endswith(".tmp")]
ok(len(sobras) <= 1, f"sobra no máximo um .tmp de gravação interrompida ({len(sobras)})")
v = c.Cofre.abrir(P, senha=S); v.registros.append({"id": "final", "servico": "S", "login": "x", "senha": "s"}); v.salvar()
ok(True, "e o cofre continua aceitando gravação normal depois das mortes")

print("== 2) duas instâncias gravando no MESMO arquivo ao mesmo tempo")
d, P = novo_cofre()
fs = [subprocess.Popen([sys.executable, "-I", "-c", FILHO, CAMINHO_PROG, P, S, "q", "6"], stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace") for _ in range(2)]
saidas = [f.communicate(timeout=90)[0] for f in fs]
oks = sum(s.count("OK ") for s in saidas); conflitos = sum(s.count("CONFLITO") for s in saidas)   # inclui os conflitos ao abrir
print(f"    gravações confirmadas: {oks}; conflitos detectados e recusados: {conflitos}")
# diagnóstico (ajuda a entender o que aconteceu no Windows): mensagens dos filhos e o que sobrou na pasta
_outros = {}
for _s in saidas:
    for _l in _s.splitlines():
        if not _l.startswith(("OK ", "CONFLITO")):
            _outros[_l[:140]] = _outros.get(_l[:140], 0) + 1
for _l, _n in list(_outros.items())[:12]:
    print(f"    filho> {_l}  (x{_n})")
print("    pasta:", sorted((_f, os.path.getsize(os.path.join(d, _f))) for _f in os.listdir(d)))
try:
    v = c.Cofre.abrir(P, senha=S); aberto = True; n = len(v.registros)
except Exception as ex:
    aberto = False; n = -1; print("   ", type(ex).__name__, ex)
ok(aberto, "o cofre abre e o manifesto interno confere depois da disputa")
ok(conflitos > 0, "a gravação concorrente foi DETECTADA e recusada (nada sobrescrito às cegas)")
ok(oks > 0 and n >= 1, f"houve gravações válidas ({n} registros no arquivo)")
ok(c.tentativas_restantes(P) == 5, "a disputa não gastou tentativas")

print("== 3) pouca memória livre: recusa antes do Argon2, sem gastar tentativa")
d, P = novo_cofre()
real = c.memoria_fisica_livre
c.memoria_fisica_livre = lambda: 200 * 1024 * 1024                 # só 200 MiB livres; o nível 'alto' pede 256 MiB (+25%)
try:
    c.Cofre.abrir(P, senha=S); r = "abriu"
except MemoryError:
    r = "memoria"
ok(r == "memoria" and c.tentativas_restantes(P) == 5, "abrir com 200 MiB livres: MemoryError e nenhuma tentativa gasta")
try:
    c.Cofre.criar(os.path.join(d, "outro.dat"), S, 5, 0, "alto"); r = "criou"
except MemoryError:
    r = "memoria"
ok(r == "memoria", "criar com pouca memória livre também recusa")
c.memoria_fisica_livre = lambda: 4 * 1024 ** 3
v = c.Cofre.abrir(P, senha=S)
ok(len(v.registros) == 0, "com memória suficiente abre normalmente")
c.memoria_fisica_livre = lambda: None
v = c.Cofre.abrir(P, senha=S)
ok(len(v.registros) == 0, "se o sistema não informa a memória, segue sem recusar")
c.memoria_fisica_livre = real
liv = c.memoria_fisica_livre()
ok(liv is None or liv > 0, f"leitura real da memória livre funciona ({'?' if liv is None else str(liv // 2**20) + ' MiB'})")

print("== 4) bit danificado no NOME do formato (COFRE05 -> COFRE01) nunca apaga o cofre")
# Defeito encontrado por um teste intermitente: com o nome virando 'COFRE01', os campos t/m/p do cofre atual parecem um
# v1 válido e um byte qualquer vira o 'contador'. Com contador = 1, a senha (certa ou errada) destruiria o cofre.
d, P = novo_cofre()
base = open(P, "rb").read()
ruim = bytearray(base); ruim[:8] = c.MAGIC_V1; ruim[c.HEADER_V1_LEN] = 1; ruim = bytes(ruim)
vivo = True; msg = ""
for senha in (S, "senha errada qualquer"):
    open(P, "wb").write(ruim)
    try:
        c.Cofre.abrir(P, senha=senha)
    except c.CofreDestruido:
        vivo = False
    except Exception as ex:
        msg = type(ex).__name__
    vivo = vivo and os.path.exists(P) and open(P, "rb").read() == ruim
ok(vivo, f"com contador=1 o arquivo não foi destruído nem alterado ({msg})")

print("\nFALHAS:", FAL)
sys.exit(1 if FAL else 0)
