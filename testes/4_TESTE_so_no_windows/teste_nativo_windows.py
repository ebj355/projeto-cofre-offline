# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Teste NATIVO no Windows real: confirma o que os testes em Linux só puderam simular.
Cobre: atributos de arquivo (oculto/sistema/somente leitura), ACL NTFS (icacls do instalador), leitura do SMBIOS
(comparada com o PowerShell), DPAPI (criar/ler/adulterar o segredo local), fator "computador autorizado" de ponta a
ponta com as identidades reais, blindagens do processo, pré-carga de DLLs da System32 e disponibilidade do WebAuthn.
Nada daqui altera o seu cofre real: tudo acontece numa pasta de teste DENTRO desta mesma pasta (nada em %TEMP% nem
solto no C:, e o segredo DPAPI de teste fica nela), apagada sozinha no fim.
Uso:  python teste_nativo_windows.py [LETRA_DO_PENDRIVE]   (a letra é opcional: testa também os atributos no pendrive)"""
import os, sys, subprocess, shutil, hashlib, ctypes, platform, re, traceback, time
RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, RAIZ)
res = []
def ver(nome, cond, detalhe=""):
    """Registra e mostra uma verificação (PASSOU / FALHOU)."""
    res.append((nome, bool(cond)))
    print(("  [PASSOU] " if cond else "  [FALHOU] ") + nome + (f"  -> {detalhe}" if detalhe else ""), flush=True)
def info(t): print("  [info]   " + t, flush=True)
def seguro(nome, fn):
    """Roda um bloco; qualquer erro vira FALHOU com o motivo (o teste continua)."""
    try: fn()
    except Exception as ex:
        ver(nome + " (erro inesperado)", False, f"{type(ex).__name__}: {str(ex)[:120]}")
        traceback.print_exc(limit=2, file=sys.stdout)
def sh(cmd, **k):
    """Executa um comando e devolve (código, saída)."""
    p = subprocess.run(cmd, capture_output=True, text=True, errors="replace", **k)
    return p.returncode, (p.stdout or "") + (p.stderr or "")

print("=== TESTE NATIVO NO WINDOWS: Cofre de Senhas ===")
print(f"Data: {time.strftime('%Y-%m-%d %H:%M:%S')} | Windows {platform.version()} | {platform.machine()} | Python {sys.version.split()[0]}")
if os.name != "nt":
    print("Este teste só faz sentido no Windows. Nada foi feito."); sys.exit(2)
import cofre_senhas as c
ver("programa carregou no Windows (EH_WINDOWS)", c.EH_WINDOWS is True)
W = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_nativo_windows")   # dentro da pasta, nada no C:\ ou %TEMP%
shutil.rmtree(W, ignore_errors=True)
os.makedirs(W, exist_ok=True)
os.environ["LOCALAPPDATA"] = os.path.join(W, "LocalAppData")          # DPAPI de teste NÃO mexe no seu segredo real
os.makedirs(os.environ["LOCALAPPDATA"], exist_ok=True)
info(f"pasta do teste (dentro de testes\\windows, apagada no fim): {W}")
cp = lambda t: "".join(list(t))
SEN = "cavalo azul come pizza na chuva"

# ---------------- 1) atributos de arquivo ----------------
def atributos(base, rotulo):
    """Cria arquivos de apoio falsos, esconde, confere com o attrib do Windows e revela."""
    pasta = os.path.join(base, "attr_teste"); os.makedirs(pasta, exist_ok=True)
    cofre = os.path.join(pasta, "cofre.dat")
    for n in ("cofre.dat", "cofre.dat.bak1", "cofre.dat.lock", "CofreSenhas.sha256"):
        open(os.path.join(pasta, n), "wb").write(b"x")
    open(os.path.join(pasta, "CofreSenhas.exe"), "wb").write(b"MZ")      # o programa: tem de continuar SEMPRE visivel
    open(os.path.join(pasta, "outro.bat"), "w").write("@echo off\n")      # nenhum .bat e escondido
    os.makedirs(os.path.join(pasta, "logs"), exist_ok=True)
    n = c.ocultar_apoio(cofre, executavel=os.path.join(pasta, "CofreSenhas.exe"))
    ver(f"[{rotulo}] ocultar_apoio marcou os arquivos de apoio", n >= 4, f"{n} itens")
    a = c._ler_atributos(os.path.join(pasta, "cofre.dat"))
    ver(f"[{rotulo}] cofre.dat ficou Oculto+Sistema+SomenteLeitura", a is not None and (a & 0x7) == 0x7, hex(a or 0))
    cod, saida = sh(["attrib", os.path.join(pasta, "cofre.dat")])
    linha = saida.strip().split("\\")[0].replace(" ", "")
    ver(f"[{rotulo}] o comando attrib do Windows confirma (S, H, R)", all(x in linha for x in "SHR"), linha)
    b = c._ler_atributos(os.path.join(pasta, "CofreSenhas.exe"))
    ver(f"[{rotulo}] CofreSenhas.exe continua visível (sem Oculto/Sistema)", b is not None and (b & 0x6) == 0, hex(b or 0))
    b = c._ler_atributos(os.path.join(pasta, "outro.bat"))
    ver(f"[{rotulo}] um .bat solto na pasta continua visível", b is not None and (b & 0x6) == 0, hex(b or 0))
    try:
        open(os.path.join(pasta, "cofre.dat"), "ab").write(b"y"); gravou = True
    except OSError: gravou = False
    ver(f"[{rotulo}] com o atributo, gravar no cofre é recusado (somente leitura)", not gravou)
    r = c.revelar_apoio(cofre, executavel=os.path.join(pasta, "CofreSenhas.exe"))
    a2 = c._ler_atributos(os.path.join(pasta, "cofre.dat"))
    ver(f"[{rotulo}] revelar_apoio devolve os arquivos ao normal", a2 is not None and (a2 & 0x7) == 0, hex(a2 or 0))
    try:
        open(os.path.join(pasta, "cofre.dat"), "ab").write(b"y"); gravou = True
    except OSError: gravou = False
    ver(f"[{rotulo}] depois de revelar, gravar funciona", gravou)
    c.revelar_apoio(cofre, executavel=os.path.join(pasta, "CofreSenhas.exe"))
    shutil.rmtree(pasta, ignore_errors=True)
print("\n[1] Atributos de arquivo")
seguro("atributos no disco do sistema", lambda: atributos(W, "disco"))
if len(sys.argv) > 1 and re.fullmatch(r"[A-Za-z]:?\\?", sys.argv[1]):
    letra = sys.argv[1][0].upper() + ":\\"
    if os.path.isdir(letra):
        seguro("atributos no pendrive", lambda: atributos(os.path.join(letra, "_teste_cofre_tmp"), "pendrive " + letra[0]))
        shutil.rmtree(os.path.join(letra, "_teste_cofre_tmp"), ignore_errors=True)
    else: info(f"unidade {letra} não encontrada: teste do pendrive pulado")
else: info("para testar também o pendrive, rode com a letra: B - testar atributos e permissoes do Windows.bat H")

# ---------------- 2) ACL NTFS (mesmo comando do instalador) ----------------
def acl():
    """Aplica a ACL do instalador numa pasta e confere quem tem acesso."""
    pasta = os.path.join(W, "acl_teste"); os.makedirs(pasta)
    cod, saida = sh(["whoami", "/user", "/fo", "csv", "/nh"])
    sid = re.findall(r'S-1-[0-9-]+', saida)[-1] if "S-1-" in saida else ""
    ver("SID do usuário obtido (whoami)", sid.startswith("S-1-5-21") or sid.startswith("S-1-12-1") or sid.startswith("S-1-5-"), sid[:12] + "...")
    cod, saida = sh(["icacls", pasta, "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"])
    if cod == 0:
        cod, saida_remocao = sh(["icacls", pasta, "/remove:g", "*S-1-1-0", "*S-1-5-11", "*S-1-5-32-545"])
        if cod != 0:
            saida += "\n" + saida_remocao
    ver("icacls aplicou a ACL sem grupos amplos", cod == 0, saida.strip().splitlines()[-1][:80] if saida.strip() else "")
    cod, lista = sh(["icacls", pasta])
    ent = [l.strip() for l in lista.splitlines() if ":(" in l or "):" in l.replace("OI", "")]
    info("ACL resultante:\n             " + "\n             ".join(l.strip() for l in lista.splitlines() if l.strip() and "processados" not in l.lower() and "processed" not in l.lower()))
    baixa = lista.lower()
    # grupos amplos que NÃO deveriam ter acesso (em inglês e em português, já que o Windows do usuário pode estar
    # em qualquer idioma): "builtin\" distingue o grupo do Windows da própria conta do usuário, que por coincidência
    # pode se chamar "Usuário" em português (ex.: "JR\Usuário" é o dono legítimo, não o grupo "BUILTIN\Usuários").
    ver("nenhum 'Everyone'/'Todos', 'Users'/'Usuários' ou 'Authenticated Users'/'Usuários autenticados' na ACL",
        not any(x in baixa for x in ("everyone", "todos:", "builtin\\users", "builtin\\usuários", "authenticated users",
                                      "usuários autenticados")),
        "")
    # BUILTIN\Administrators/Administradores pode aparecer (o Windows cria pastas novas já com essa entrada): é uma
    # exceção aceita e já documentada no README/MODELO_DE_AMEACAS — um administrador da máquina sempre consegue tomar
    # posse de qualquer arquivo, com ou sem essa entrada, então negá-la não aumentaria a segurança de verdade.
    info("BUILTIN\\Administrators/Administradores na ACL: " +
         ("sim (esperado; documentado como limite no README/MODELO_DE_AMEACAS)"
          if ("builtin\\administrators" in baixa or "builtin\\administradores" in baixa) else "não"))
    ver("SISTEMA presente (necessário para o Windows)", "system" in baixa or "sistema" in baixa)
    try:
        open(os.path.join(pasta, "t.txt"), "w").write("ok"); os.remove(os.path.join(pasta, "t.txt")); pode = True
    except OSError: pode = False
    ver("o próprio usuário continua gravando na pasta", pode)
    cod, saida = sh(["icacls", pasta, "/reset", "/T", "/C", "/Q"])
    shutil.rmtree(pasta, ignore_errors=True)
print("\n[2] Permissões NTFS (ACL)")
seguro("ACL", acl)

# ---------------- 3) SMBIOS e MachineGuid ----------------
def smbios():
    """Lê o UUID da placa-mãe pela API nativa e compara com o PowerShell."""
    u = c._smbios_uuid(); g = c._machine_guid()
    ver("MachineGuid lido do registro (HKLM, somente leitura)", len(g) in (36,) and g.count(b"-") == 4, f"{g[:4].decode()}…")
    ver("UUID SMBIOS lido pela API GetSystemFirmwareTable", u is not None and len(u) == 16, (u.hex()[:4] + "…") if u else "NÃO leu (placa sem UUID válido?)")
    ver("leituras estáveis (duas leituras iguais)", c._smbios_uuid() == u and c._machine_guid() == g)
    cod, ps = sh(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_ComputerSystemProduct).UUID"])
    ps = ps.strip().lower()
    if u and re.fullmatch(r"[0-9a-f-]{36}", ps):
        a = u.hex(); b = bytes([u[3], u[2], u[1], u[0], u[5], u[4], u[7], u[6]]).hex() + u[8:].hex()   # ordem do SMBIOS 2.6+
        ok_ = ps.replace("-", "") in (a, b)
        ver("o UUID lido pelo programa bate com o do PowerShell (Win32_ComputerSystemProduct)", ok_, "iguais" if ok_ else "DIFERENTES: o parser do SMBIOS precisa de ajuste")
    else: info(f"PowerShell não devolveu um UUID comparável ({ps[:12]})")
    ids = c.identidades_do_pc()
    ver("identidades do computador geradas (2 candidatos com SMBIOS, 1 sem)", len(ids) in (1, 2) and all(len(x) == 32 for x in ids), f"{len(ids)} identidade(s)")
    ver("identidade estável entre chamadas", ids == c.identidades_do_pc())
print("\n[3] SMBIOS e MachineGuid")
seguro("SMBIOS", smbios)

# ---------------- 4) DPAPI ----------------
def dpapi():
    """Cria, lê e adultera o segredo local protegido pela DPAPI."""
    arq = c._arquivo_segredo_local()
    ver("segredo local ainda não existe (pasta de teste limpa)", c.segredo_local() is None)
    s1 = c.segredo_local(criar=True)
    ver("segredo criado (32 bytes) e protegido pela DPAPI", s1 is not None and len(s1) == 32)
    bruto = open(arq, "rb").read()
    ver("o arquivo em disco NÃO contém o segredo em claro", s1 not in bruto)
    ver("o arquivo é um blob DPAPI (começa com 01 00 00 00 D0 8C 9D DF)", bruto[:8] == bytes.fromhex("01000000d08c9ddf"), bruto[:8].hex())
    ver("segundo acesso devolve o MESMO segredo", c.segredo_local() == s1)
    b = bytearray(bruto); b[len(b) // 2] ^= 0x01; open(arq, "wb").write(bytes(b))
    ver("blob adulterado (1 bit): o Windows recusa e o cofre trata como 'sem segredo'", c.segredo_local() is None)
    open(arq, "wb").write(bruto)
    ver("blob original restaurado volta a abrir", c.segredo_local() == s1)
    cod, saida = sh(["icacls", os.path.dirname(arq)])
    info("o segredo fica em %LOCALAPPDATA% (herda a ACL do seu perfil: só você, SISTEMA e administradores).")
print("\n[4] DPAPI (segredo local)")
seguro("DPAPI", dpapi)

# ---------------- 5) fator "computador autorizado" ponta a ponta ----------------
def pc():
    """Cria um cofre de teste, autoriza ESTE computador (com reforço DPAPI) e abre de novo."""
    p = os.path.join(W, "pc.dat")
    v = c.Cofre.criar(p, cp(SEN), 5, c.MODO_S, "alto")
    cod = v.pc_adicionar("Este PC (teste)", local=True); v.salvar(); v.fechar()
    ver("computador autorizado com reforço DPAPI", bool(cod))
    ver("info_pc: exige computador e este está autorizado", c.info_pc(p) == (True, True), str(c.info_pc(p)))
    v = c.Cofre.abrir(p, senha=cp(SEN)); nivel = v.pc_nivel_deste(); v.fechar()
    ver("abre com a senha neste computador", True, f"nível: {nivel}")
    seg = c._arquivo_segredo_local(); guarda = open(seg, "rb").read(); os.remove(seg)
    try: c.Cofre.abrir(p, senha=cp(SEN)); r = "abriu"
    except c.PcNaoAutorizado: r = "barrado"
    except Exception as ex: r = type(ex).__name__
    ver("sem o segredo DPAPI (outra conta/cópia do arquivo): barrado antes de gastar tentativa", r == "barrado", r)
    try: v = c.Cofre.abrir(p, senha=cp(SEN), recuperacao=cp(cod)); v.fechar(); r = "abriu"
    except Exception as ex: r = type(ex).__name__
    ver("com o código de recuperação o cofre abre mesmo sem o segredo", r == "abriu", r)
    open(seg, "wb").write(guarda)
print("\n[5] Computador autorizado (de ponta a ponta)")
seguro("PC autorizado", pc)

# ---------------- 6) blindagens do processo e DLLs ----------------
def blindagem():
    """Aplica as defesas do Windows e confere as DLLs da System32."""
    b = list(c.blindar_processo())
    info("blindagens aplicadas: " + ", ".join(b))
    ver("pelo menos 4 blindagens do processo ativas", len(b) >= 4, f"{len(b)}")
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.GetModuleHandleW.restype = ctypes.c_void_p; k.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    k.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
    sysdir = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32").lower()
    for dll in ("wer", "wtsapi32", "dwmapi", "webauthn"):
        h = k.GetModuleHandleW(dll + ".dll")
        if h:
            buf = ctypes.create_unicode_buffer(520); k.GetModuleFileNameW(h, buf, 520)
            ver(f"{dll}.dll carregada da System32", buf.value.lower().startswith(sysdir), buf.value)
        else: info(f"{dll}.dll ainda não carregada (normal se o recurso não foi usado)")
    ver("nenhum depurador anexado (IsDebuggerPresent)", not ctypes.windll.kernel32.IsDebuggerPresent())
print("\n[6] Blindagens do processo e DLLs")
seguro("blindagem", blindagem)

# ---------------- 7) WebAuthn / FIDO2 (só disponibilidade) e registro ----------------
def fido():
    """Confere se o Windows oferece WebAuthn (não toca em nenhuma chave)."""
    try:
        from fido2.client.windows import WindowsClient
        from fido2.client.win_api import WEBAUTHN_API_VERSION
        ver("Windows oferece WebAuthn (chave FIDO2)", WindowsClient.is_available(), f"API v{WEBAUTHN_API_VERSION} (>= 4 recomendado para PRF)")
    except Exception as ex:
        ver("biblioteca fido2 carrega", False, f"{type(ex).__name__}: {str(ex)[:80]}")
    hib = c.hibernacao_ligada()
    if isinstance(hib, bool):
        ver("hibernação lida do registro (somente leitura)", True, str(hib))
    else:
        # None = o valor não existe/não respondeu. Em VM (ex.: runner do GitHub Actions) o Windows não tem hibernação e a
        # chave HibernateEnabled nem existe: isso não é erro do programa. Confirma com o próprio Windows antes de aceitar.
        cod, saida = sh(["reg", "query", r"HKLM\SYSTEM\CurrentControlSet\Control\Power", "/v", "HibernateEnabled"])
        if cod != 0:
            info("este Windows não tem o valor HibernateEnabled (típico de VM/CI): a hibernação não se aplica; o programa trata como 'não sei'")
        else:
            ver("hibernação lida do registro (somente leitura)", False, "o valor existe, mas o programa não conseguiu lê-lo")
print("\n[7] FIDO2 e registro")
seguro("FIDO", fido)

shutil.rmtree(W, ignore_errors=True)
f = sum(1 for _, o in res if not o)
print(f"\n=== RESULTADO: {len(res) - f} passaram, {f} falharam ===")
if f:
    print("Verificações que falharam:"); [print("  - " + n) for n, o in res if not o]
sys.exit(1 if f else 0)
