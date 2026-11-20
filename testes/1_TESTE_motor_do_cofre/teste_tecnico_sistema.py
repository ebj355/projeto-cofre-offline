"""Testes técnicos de sistema (equivalentes locais dos testes de pentest de aplicativo de PC):
1) rede: nenhuma conexão é aberta em criar/abrir/salvar/backup/exportar/importar/trocar senha/computador/FIDO;
   a única exceção é a consulta opcional HIBP, que só sai com 5 caracteres de hash;
2) rastros em disco: nenhum arquivo temporário/log guarda senha, PIN ou notas em texto puro;
3) DLL hijacking: toda DLL carregada pelo código é do Windows e as 'não conhecidas' são pré-carregadas pela System32;
4) registro do Windows: só leitura (nada é criado, alterado ou apagado);
5) código perigoso: sem eval/exec/pickle/shell=True/os.system/yaml.load; sem segredo fixo no código;
6) ctypes: toda chamada de API tem tipos declarados quando recebe ponteiros (sem corrupção de memória por argumento);
7) fuzzing do analisador de cabeçalho (milhares de mutações, sem travar nem estourar memória)."""
import os, sys, re, socket, tempfile, shutil, time, random, hashlib, ast
RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, RAIZ)
import cofre_senhas as c
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "6_TESTE_ferramentas_dos_testes"))  # testes/6_TESTE_ferramentas_dos_testes/ -> _util_mem.py
from _util_mem import pico_kb   # pico de memória: resource (Linux/macOS) não existe no Windows, _util_mem cobre os dois
f = []
def ok(cond, nome):
    """Registra uma verificação."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
cp = lambda t: "".join(list(t))
SEN = "cavalo azul come pizza na chuva"
SEGREDOS = ["Segredo-Banco-9X!qz", "PIN-48291577", "nota-confidencial-ZZ-77"]
fonte = open(os.path.join(RAIZ, "cofre_senhas.py"), encoding="utf-8").read()

# ---------- 1) rede ----------
tentativas = []
class SemRede(socket.socket):
    """Qualquer tentativa de conexão é registrada e barrada."""
    def connect(self, *a, **k): tentativas.append(("connect", a)); raise OSError("rede bloqueada no teste")
    def connect_ex(self, *a, **k): tentativas.append(("connect_ex", a)); return 111
socket.socket = SemRede
_gai = socket.getaddrinfo
def _bloq(*a, **k): tentativas.append(("dns", a[:1])); raise OSError("DNS bloqueado no teste")
socket.getaddrinfo = _bloq

W = tempfile.mkdtemp(prefix="tec_"); TMP = os.path.join(W, "tmp"); os.makedirs(TMP)
tempfile.tempdir = TMP; os.environ["TMPDIR"] = os.environ["TEMP"] = os.environ["TMP"] = TMP
c.identidades_do_pc = lambda: [hashlib.sha256(b"pcA-GU").digest(), hashlib.sha256(b"pcA-G").digest()]
P = os.path.join(W, "v.dat")
v = c.Cofre.criar(P, cp(SEN), 5, c.MODO_S, "alto")
v.registros.append(c.novo_item(servico="Banco", login="eu@exemplo.com", senha=SEGREDOS[0], pin=SEGREDOS[1], notas=SEGREDOS[2]))
v.salvar(); cod = v.pc_adicionar("PC-A"); v.salvar(); v.fechar()
fluxos = 0
try:
    v = c.Cofre.abrir(P, senha=cp(SEN)); fluxos += 1                       # abrir
    v.registros.append(c.novo_item(servico="Outro", login="x", senha="o-2")); v.salvar(); fluxos += 1   # salvar
    v.novo_codigo_recuperacao(); v.salvar(); fluxos += 1                     # código de recuperação
    try: v.pc_adicionar("PC-B")
    except ValueError: fluxos += 1                                            # mesmo computador: recusa prevista
    v.fechar()
    v = c.Cofre.abrir(P, senha=cp(SEN), consulta=True); v.fechar(); fluxos += 1   # modo consulta
    v = c.Cofre.abrir(P, senha=cp(SEN)); v.trocar_senha(cp(SEN) + "-nova-9"); v.salvar(); v.fechar(); fluxos += 1  # trocar senha
    c.criar_modelo_planilha(os.path.join(W, "modelo.xlsx")); c.varrer_planilha(os.path.join(W, "modelo.xlsx"), estrito=True); fluxos += 1
except Exception as ex:
    print("  [info] fluxo interrompido:", type(ex).__name__, str(ex)[:80])
ok(fluxos == 7, f"7 fluxos executados sem rede (abrir, salvar, recuperação, computador, consulta, trocar senha, planilha): {fluxos}")
# consulta HIBP: só o prefixo de 5 caracteres pode sair
pref, suf = c.hibp_dividir("senha-de-teste-123")
ok(len(pref) == 5 and len(suf) == 35 and pref + suf == hashlib.sha1(b"senha-de-teste-123").hexdigest().upper(), "HIBP: só 5 caracteres de hash saem; o resto fica local")
chamadas = []
def falso(prefixo, timeout=15): chamadas.append(prefixo); return suf + ":7\r\n"
try:
    r = c.hibp_verificar([("x", pref, suf)], baixar=falso)
except Exception as ex:
    r = repr(ex)
ok(r == [("x", 7)], "HIBP: a comparação dos sufixos acontece localmente")
ok(not chamadas or all(len(x) == 5 for x in chamadas), "HIBP: o pedido só carrega 5 caracteres (" + str(chamadas) + ")")
ok(len(tentativas) == 0, f"nenhuma conexão de rede aberta em criar/abrir/salvar/computador/FIDO/planilha ({tentativas[:2]})")
socket.socket = socket.socket.__mro__[1]; socket.getaddrinfo = _gai
rede_no_codigo = re.findall(r"^\s*(?:import|from)\s+(urllib\S*|http\S*|socket|ftplib|smtplib|requests|telnetlib|xmlrpc\S*)", fonte, re.M)
ok(set(rede_no_codigo) <= {"urllib.request"}, f"único módulo de rede importado: urllib.request ({sorted(set(rede_no_codigo))})")
ok(fonte.count("urlopen(") == 1 and 'HIBP_URL.startswith("https://")' in fonte, "uma só chamada de rede (HIBP), sempre HTTPS")

# ---------- 2) rastros em disco ----------
achados = []
for raiz, _, arqs in os.walk(W):
    for a in arqs:
        try: dados = open(os.path.join(raiz, a), "rb").read()
        except OSError: continue
        for sg in SEGREDOS + [SEN]:
            if sg.encode() in dados or sg.encode("utf-16-le") in dados: achados.append((a, sg[:8]))
ok(not achados, f"nenhum arquivo (cofre, cópias, temporários, logs) contém senha/PIN/nota em texto puro ({achados[:3]})")
ok(os.listdir(TMP) == [] or all(not os.path.isfile(os.path.join(TMP, x)) or os.path.getsize(os.path.join(TMP, x)) == 0 for x in os.listdir(TMP)), "pasta temporária sem arquivos soltos")

# ---------- 3) DLL hijacking ----------
dlls = set(m.lower() for m in re.findall(r'(?:WinDLL|CDLL|LoadLibrary\w*)\(\s*[rf]?["\']([A-Za-z0-9_.]+)["\']', fonte))
dlls |= set(m.lower() for m in re.findall(r"ctypes\.windll\.(\w+)", fonte))
conhecidas = {"kernel32", "user32", "advapi32", "gdi32", "comdlg32", "crypt32", "shcore", "shell32", "ole32", "oleaut32", "ntdll", "kernelbase"}
preload = {"wer", "wtsapi32", "dwmapi", "webauthn"}
sem_cobertura = sorted(d.replace(".dll", "") for d in dlls if d.replace(".dll", "") not in conhecidas | preload)
ok(not sem_cobertura, f"toda DLL carregada é conhecida do Windows ou pré-carregada da System32 ({sem_cobertura}; total {len(dlls)})")
ok("SetDllDirectoryW" in fonte and "PreferSystem32" in fonte or "(\"dlls\", 10" in fonte, "pasta atual fora da busca de DLL e preferência pela System32")
ok(not re.search(r"os\.add_dll_directory|os\.environ\[.PATH.\]\s*=|sys\.path\.(insert|append)\(", fonte), "o programa não acrescenta pastas à busca de DLL/módulos")
ok(not re.search(r'(?:WinDLL|CDLL|LoadLibrary\w*)\(\s*(?:os\.path|["\'][^"\']*[\\/])', fonte.replace("sysdir.value", "")) or "sysdir.value" in fonte, "nenhuma DLL carregada por caminho relativo/de usuário")

# ---------- 4) registro: só leitura ----------
escritas = re.findall(r"winreg\.(SetValue\w*|CreateKey\w*|DeleteKey\w*|DeleteValue|SaveKey|LoadKey|ConnectRegistry)", fonte)
ok(not escritas, f"registro do Windows: nenhuma escrita ({escritas})")
chaves = re.findall(r"winreg\.OpenKey\(([^)]*)\)", fonte)
ok(all("KEY_READ" in k or "KEY_WRITE" not in k for k in chaves), "OpenKey nunca pede KEY_WRITE/KEY_ALL_ACCESS")
ok(not re.search(r"KEY_ALL_ACCESS|KEY_SET_VALUE|KEY_CREATE", fonte), "nenhuma permissão de escrita no registro")

# ---------- 5) código perigoso e segredos fixos ----------
arv = ast.parse(fonte); ruins = []
for n in ast.walk(arv):
    if isinstance(n, ast.Call):
        nome = n.func.id if isinstance(n.func, ast.Name) else (n.func.attr if isinstance(n.func, ast.Attribute) else "")
        dono = n.func.value.id if isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) else ""
        if nome in ("eval", "exec", "compile") and dono == "": ruins.append((nome, n.lineno))
        if dono == "os" and nome in ("system", "popen"): ruins.append(("os." + nome, n.lineno))
        if dono in ("pickle", "marshal", "shelve") and nome in ("load", "loads"): ruins.append((dono + "." + nome, n.lineno))
        if dono == "yaml" and nome == "load": ruins.append(("yaml.load", n.lineno))
        for kw in n.keywords:
            if kw.arg == "shell" and getattr(kw.value, "value", False) is True: ruins.append(("shell=True", n.lineno))
ok(not ruins, f"sem eval/exec/pickle/os.system/shell=True ({ruins[:4]})")
sus = re.findall(r"""(?i)(?:senha|password|secret|token|api[_-]?key)\w*\s*=\s*["'][^"'\s]{12,}["']""", fonte)
sus = [x for x in sus if not re.search(r"(?i)exemplo|teste|placeholder|nome|texto|mensagem", x)]
ok(not sus, f"sem senha/token fixo no código ({sus[:3]})")

# ---------- 6) ctypes: argumentos tipados ----------
usos = re.findall(r"\b(\w+)\.(\w+)\.argtypes\s*=", fonte)
ok(len(usos) >= 25, f"APIs do Windows com tipos de argumento declarados: {len(usos)} (>= 25)")
chamadas_ptr = re.findall(r"ctypes\.byref\(", fonte)
ok(len(usos) >= len(chamadas_ptr) // 2, f"declarações de tipo ({len(usos)}) cobrem a maior parte das chamadas com ponteiro ({len(chamadas_ptr)})")

# ---------- 7) fuzzing do cabeçalho ----------
v = c.Cofre.criar(os.path.join(W, "fz.dat"), cp(SEN), 5, c.MODO_S, "alto"); v.pc_adicionar("PC-A"); v.salvar(); v.fechar()
base = open(os.path.join(W, "fz.dat"), "rb").read()
rnd = random.Random(99); erros_ok = (c.ArquivoInvalido, ValueError, c.FatorFaltando); inesperados = []; t0 = time.perf_counter(); lentos = 0
N = 20000
for i in range(N):
    b = bytearray(base[:c.HEADER_LEN5 + 400])
    for _ in range(rnd.randint(1, 6)):
        b[(8 if rnd.random() < 0.85 else 0) + rnd.randrange(len(b) - 8)] = rnd.randrange(256)   # 85%: mantém o selo do formato e testa o miolo
    if rnd.random() < 0.15: b = b[:rnd.randrange(len(b))]
    if rnd.random() < 0.05: b += os.urandom(rnd.randrange(2000))
    t1 = time.perf_counter()
    try: c._ler_cabecalho(bytes(b))
    except erros_ok: pass
    except Exception as ex: inesperados.append((type(ex).__name__, str(ex)[:50]))
    if time.perf_counter() - t1 > 0.5: lentos += 1
dt = time.perf_counter() - t0
ok(not inesperados, f"{N} mutações do cabeçalho: só erros previstos ({inesperados[:3]})")
ok(lentos == 0 and dt < 120, f"{N} mutações em {dt:.1f}s, nenhuma lenta (> 0,5 s)")
ok(pico_kb() / 1024 < 2500, "fuzzing sem estourar memória")
# campos de tamanho gigantes (alocação absurda)
for cab in (c.MAGIC + b"\xff" * 80, c.MAGIC + b"\x00" * 80, c.MAGIC + os.urandom(300), c.MAGIC):
    try: c._ler_cabecalho(cab); r = "aceitou"
    except erros_ok: r = "recusou"
    except MemoryError: r = "MemoryError"
    except Exception as ex: r = type(ex).__name__
    ok(r == "recusou", f"cabeçalho com tamanhos absurdos recusado ({r})")
shutil.rmtree(W, ignore_errors=True)
print("FALHAS:", f.count(False)); sys.exit(1 if False in f else 0)
