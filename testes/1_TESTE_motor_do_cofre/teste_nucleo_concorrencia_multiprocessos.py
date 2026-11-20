"""CONCORRÊNCIA ENTRE VÁRIOS PROCESSOS no mesmo cofre (mais pesado que o teste de 2 instâncias).

O que já existia: `teste_trava_instancias.py` (2-3 processos pedem a trava) e `teste_queda_e_memoria.py` (2 instâncias
gravando). Aqui sobem VÁRIOS processos AO MESMO TEMPO, de verdade:
1) CORRIDA PELA TRAVA: 6 processos largam juntos e pedem `instancia_unica()`; exatamente UM pode virar dono, os
   outros 5 recebem "em uso" (vão para o modo consulta). Repetido 3 vezes.
2) ESCRITORES + LEITOR: 2 processos gravando itens no mesmo arquivo e 1 lendo em modo consulta. Quando a
   gravação é recusada por conflito (outra instância gravou primeiro) o escritor reabre e tenta de novo.
   Conferência final: o arquivo abre, NENHUMA gravação confirmada se perdeu, nenhum item está duplicado, não sobrou
   .tmp, e o leitor nunca viu um arquivo pela metade (ArquivoInvalido).
Roda no Linux e no Windows (Python). Usa parâmetros mínimos válidos do Argon2 para focar na concorrência de arquivo,
sem transformar o teste em uma medição de desempenho da derivação de senha."""
import os, sys, time, subprocess, tempfile, textwrap, importlib.util, shutil

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "6_TESTE_ferramentas_dos_testes"))
import _resultado; _resultado.registrar(__file__)          # grava resultados/resultado_nucleo_concorrencia_multiprocessos.txt

CAMINHO_PROG = os.path.abspath(os.path.join(AQUI, "..", "..", "cofre_senhas.py"))
spec = importlib.util.spec_from_file_location("c", CAMINHO_PROG)
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
FAL = []


def ok(cond, msg):
    """Imprime [OK]/[FALHOU] (o executor procura estes marcadores) e guarda as falhas."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + msg, flush=True)
    if not cond:
        FAL.append(msg)


S = "cavalo azul come pizza na chuva 2026"
PARAMETROS_TESTE = (1, 8192)


def criar_cofre_teste(caminho, max_tentativas):
    """Cria um arquivo válido com KDF leve: este teste mede concorrência, não força da senha."""
    anteriores = c.NIVEIS["alto"]
    c.NIVEIS["alto"] = PARAMETROS_TESTE
    try:
        c.Cofre.criar(caminho, S, max_tentativas, 0, "alto").fechar()
    finally:
        c.NIVEIS["alto"] = anteriores


def encerrar_processos(processos):
    """Encerra filhos restantes quando há timeout ou interrupção do teste."""
    processos = [p for p in processos if p is not None]
    for p in processos:
        if p.poll() is None:
            try:
                p.terminate()
            except OSError:
                pass
    for p in processos:
        if p.poll() is None:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()


def ler_saida(caminho):
    with open(caminho, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()

# ---------------------------------------------------------------- 1) corrida pela trava
CORRIDA = textwrap.dedent('''
    import sys, time, importlib.util
    spec = importlib.util.spec_from_file_location("c", sys.argv[1]); c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
    c.NIVEIS["alto"] = (1, 8192)
    P, largada = sys.argv[2], float(sys.argv[3])
    while time.time() < largada:            # todos esperam o MESMO instante para largar juntos
        time.sleep(0.001)
    r = c.instancia_unica(P)
    print("DONO" if r else "EM_USO", flush=True)
    time.sleep(2.5)                          # o dono segura a trava enquanto os outros tentam
''')

print("== 1) corrida pela trava: 6 processos largam juntos, só 1 pode ser o dono")
for rodada in range(1, 4):
    d = tempfile.mkdtemp(prefix="cofre_conc_"); P = os.path.join(d, "cofre.dat")
    ps = []
    try:
        criar_cofre_teste(P, 3)
        largada = time.time() + 2.5                     # tempo para os 6 interpretadores subirem
        ps = [subprocess.Popen([sys.executable, "-c", CORRIDA, CAMINHO_PROG, P, repr(largada)],
                               stdout=subprocess.PIPE, text=True) for _ in range(6)]
        saidas = [p.communicate(timeout=90)[0].strip() for p in ps]
        donos = saidas.count("DONO")
        ok(donos == 1 and saidas.count("EM_USO") == 5,
           f"rodada {rodada}: exatamente 1 dono e 5 em uso (saídas: {sorted(saidas)})")
    finally:
        encerrar_processos(ps)
        shutil.rmtree(d, ignore_errors=True)

# ---------------------------------------------------------------- 2) escritores + leitor
ESCRITOR = textwrap.dedent('''
    import os, sys, time, importlib.util
    spec = importlib.util.spec_from_file_location("c", sys.argv[1]); c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
    c.NIVEIS["alto"] = (1, 8192)
    P, S, nome, pronto, iniciar = sys.argv[2:7]
    v = c.Cofre.abrir(P, senha=S)
    try:
        with open(pronto, "w", encoding="ascii") as f:
            f.write("pronto")
        limite = time.time() + 30
        while not os.path.exists(iniciar):
            if time.time() >= limite:
                raise SystemExit("barreira de início expirou")
            time.sleep(0.005)
        item = c.novo_item(servico=nome, login="u", senha="s")
        v.registros.append(item)
        try:
            v.salvar()
            print("OK", item["id"], flush=True)
        except c.ConflitoGravacao:
            print("CONFLITO", item["id"], flush=True)
    finally:
        v.fechar()
''')
LEITOR = textwrap.dedent('''
    import os, sys, time, importlib.util
    spec = importlib.util.spec_from_file_location("c", sys.argv[1]); c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
    c.NIVEIS["alto"] = (1, 8192)
    P, S, iniciar = sys.argv[2:5]
    limite = time.time() + 30
    while not os.path.exists(iniciar):
        if time.time() >= limite:
            raise SystemExit("barreira de início expirou")
        time.sleep(0.005)
    lidos = 0
    for _ in range(8):
        try:
            v = c.Cofre.abrir(P, senha=S, consulta=True); lidos += 1; v.fechar()
        except c.ArquivoInvalido as e:
            print("PELA_METADE", str(e)[:120], flush=True)
        except (OSError, c.ErroGravacao, c.ConflitoGravacao):
            print("TRANSIENTE", flush=True)
        time.sleep(0.05)
    print("FIM", lidos, flush=True)
''')

# Respeita a RAM do PC. O teste usa 8 MiB por derivação e dois escritores para limitar o tamanho do arquivo temporário.
_resultado.esperar_memoria(400, 60)
_livre = _resultado.memoria_livre_mb()
NESC = 2
print(f"== 2) {NESC} escritores + 1 leitor no mesmo arquivo (memória livre: {_livre} MiB)")
d = tempfile.mkdtemp(prefix="cofre_conc_"); P = os.path.join(d, "cofre.dat")
procs, logs, leitor, log_leitor = [], [], None, os.path.join(d, "leitor.log")
iniciar = os.path.join(d, "iniciar")
try:
    criar_cofre_teste(P, 10)
    for i in range(2):
        pronto = os.path.join(d, f"escritor_{i}.pronto")
        log = os.path.join(d, f"escritor_{i}.log")
        with open(log, "w", encoding="utf-8") as saida:
            p = subprocess.Popen([sys.executable, "-c", ESCRITOR, CAMINHO_PROG, P, S, f"w{i}", pronto, iniciar],
                                stdout=saida, stderr=subprocess.STDOUT, text=True)
        procs.append(p); logs.append(log)
        limite = time.time() + 15
        while not os.path.exists(pronto):
            if p.poll() is not None:
                raise subprocess.SubprocessError(f"escritor {i} terminou antes da barreira")
            if time.time() >= limite:
                raise subprocess.TimeoutExpired(p.args, 15)
            time.sleep(0.01)
    with open(log_leitor, "w", encoding="utf-8") as saida:
        leitor = subprocess.Popen([sys.executable, "-c", LEITOR, CAMINHO_PROG, P, S, iniciar],
                                  stdout=saida, stderr=subprocess.STDOUT, text=True)
    with open(iniciar, "w", encoding="ascii") as f:
        f.write("iniciar")
    resultados = []
    for p, log in zip(procs, logs):
        p.wait(timeout=20)
        out = ler_saida(log)
        ok(p.returncode == 0, f"escritor terminou sem erro (código {p.returncode})")
        resultados.extend(l.split() for l in out if l.startswith(("OK ", "CONFLITO ")))
    leitor.wait(timeout=12)
    saida_leitor = ler_saida(log_leitor)
    confirmados = [linha[1] for linha in resultados if linha[0] == "OK"]
    conflitos = [linha[1] for linha in resultados if linha[0] == "CONFLITO"]
    ok(len(confirmados) == 1 and len(conflitos) == 1,
       f"gravação concorrente: uma confirmada e uma recusada por conflito ({resultados})")
    final = c.Cofre.abrir(P, senha=S)
    ids = [r["id"] for r in final.registros]
    ok(len(ids) == 1, f"o arquivo final abre com uma gravação ({len(ids)} item(ns))")
    ok(all(i in ids for i in confirmados) and not any(i in ids for i in conflitos),
       "a gravação confirmada persistiu e a recusada não sobrescreveu o arquivo")
    ok(len(ids) == len(set(ids)), "nenhum item duplicado no arquivo final")
    final.fechar()
    sobras = [f for f in os.listdir(d) if f.endswith(".tmp")]
    ok(not sobras, f"nenhum .tmp esquecido na pasta ({sobras})")
    metade = [l for l in saida_leitor if l.startswith("PELA_METADE")]
    ok(not metade, f"o leitor nunca viu o arquivo pela metade ({len(metade)} vez(es); 1ª: {metade[:1]})")
    ok(any(l.startswith("FIM") for l in saida_leitor), f"o leitor terminou ({[l for l in saida_leitor if l.startswith('FIM')]})")
except (OSError, subprocess.SubprocessError, c.ArquivoInvalido, c.ErroGravacao) as ex:
    for log in logs + [log_leitor]:
        if os.path.exists(log):
            print(f"  saída de {os.path.basename(log)}:")
            for linha in ler_saida(log)[-10:]:
                print("    " + linha)
    ok(False, f"execução concorrente incompleta: {type(ex).__name__}: {ex}")
except KeyboardInterrupt:
    for log in logs + [log_leitor]:
        if os.path.exists(log):
            print(f"  saída de {os.path.basename(log)}:")
            for linha in ler_saida(log)[-10:]:
                print("    " + linha)
    ok(False, "execução interrompida pelo usuário")
    raise
finally:
    encerrar_processos(procs + ([leitor] if leitor is not None else []))
    shutil.rmtree(d, ignore_errors=True)

print("\nFALHAS: " + str(FAL) if FAL else "\nTODOS OK")
sys.exit(1 if FAL else 0)
