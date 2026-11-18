"""CONCORRÊNCIA ENTRE VÁRIOS PROCESSOS no mesmo cofre (mais pesado que o teste de 2 instâncias).

O que já existia: `teste_trava_instancias.py` (2-3 processos pedem a trava) e `teste_queda_e_memoria.py` (2 instâncias
gravando). Aqui sobem VÁRIOS processos AO MESMO TEMPO, de verdade:
1) CORRIDA PELA TRAVA: 6 processos largam juntos e pedem `instancia_unica()`; exatamente UM pode virar dono, os
   outros 5 recebem "em uso" (vão para o modo consulta). Repetido 3 vezes.
2) ESCRITORES + LEITOR: 3 processos gravando itens no mesmo arquivo sem parar e 1 lendo em modo consulta. Quando a
   gravação é recusada por conflito (outra instância gravou primeiro) o escritor reabre e tenta de novo.
   Conferência final: o arquivo abre, NENHUMA gravação confirmada se perdeu, nenhum item está duplicado, não sobrou
   .tmp, e o leitor nunca viu um arquivo pela metade (ArquivoInvalido).
Roda no Linux e no Windows (Python). Usa o nível 'alto' do Argon2 (256 MiB por abertura): ~1 GB com 4 processos."""
import os, sys, time, subprocess, tempfile, textwrap, importlib.util

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "6_ferramentas_dos_testes"))
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

# ---------------------------------------------------------------- 1) corrida pela trava
CORRIDA = textwrap.dedent('''
    import sys, time, importlib.util
    spec = importlib.util.spec_from_file_location("c", sys.argv[1]); c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
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
    c.Cofre.criar(P, S, 3, 0, "alto").salvar()
    largada = time.time() + 2.5                         # tempo para os 6 interpretadores subirem
    ps = [subprocess.Popen([sys.executable, "-c", CORRIDA, CAMINHO_PROG, P, repr(largada)],
                           stdout=subprocess.PIPE, text=True) for _ in range(6)]
    saidas = [p.communicate(timeout=90)[0].strip() for p in ps]
    donos = saidas.count("DONO")
    ok(donos == 1 and saidas.count("EM_USO") == 5,
       f"rodada {rodada}: exatamente 1 dono e 5 em uso (saídas: {sorted(saidas)})")

# ---------------------------------------------------------------- 2) escritores + leitor
ESCRITOR = textwrap.dedent('''
    import sys, time, importlib.util
    spec = importlib.util.spec_from_file_location("c", sys.argv[1]); c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
    P, S, nome, segundos = sys.argv[2], sys.argv[3], sys.argv[4], float(sys.argv[5])
    fim = time.time() + segundos

    def abrir():
        """Abre; se a gravação de outro processo estiver no meio (Windows) ou houver conflito, tenta de novo."""
        for _ in range(200):
            try:
                return c.Cofre.abrir(P, senha=S)
            except (c.ConflitoGravacao, c.ErroGravacao, OSError):
                time.sleep(0.05)
        raise SystemExit("não conseguiu abrir")

    v = abrir(); n = 0; conflitos = 0
    while time.time() < fim:
        item = c.novo_item(servico="%s-%d" % (nome, n), login="u", senha="s%d" % n)
        v.registros.append(item)
        try:
            v.salvar()
            print("OK", item["id"], flush=True)          # confirmado: TEM que estar no arquivo final
            n += 1
        except c.ConflitoGravacao:
            conflitos += 1
            v = abrir()                                    # o arquivo mudou: relê e tenta o mesmo item de novo
    print("FIM", n, conflitos, flush=True)
''')
LEITOR = textwrap.dedent('''
    import sys, time, importlib.util
    spec = importlib.util.spec_from_file_location("c", sys.argv[1]); c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
    P, S, segundos = sys.argv[2], sys.argv[3], float(sys.argv[4])
    fim = time.time() + segundos; lidos = 0
    while time.time() < fim:
        try:
            v = c.Cofre.abrir(P, senha=S, consulta=True); lidos += 1; v.fechar()
        except c.ArquivoInvalido as e:
            print("PELA_METADE", str(e)[:120], flush=True)    # nunca pode acontecer: a troca do arquivo é atômica
        except (OSError, c.ErroGravacao, c.ConflitoGravacao):
            print("TRANSIENTE", flush=True)                    # Windows: arquivo sendo trocado neste instante (esperado)
    print("FIM", lidos, flush=True)
''')

# Respeita a RAM do PC: cada processo abre o cofre com Argon2 "alto" (256 MiB). Com pouca memória livre, usa menos escritores
# (o que se testa é a disputa pelo mesmo arquivo; 2 escritores + 1 leitor já a provocam) em vez de travar a máquina.
_resultado.esperar_memoria(1400, 120)
_livre = _resultado.memoria_livre_mb()
NESC = 3 if (_livre is None or _livre >= 2600) else 2
print(f"== 2) {NESC} escritores + 1 leitor no mesmo arquivo por ~10 s (memória livre: {_livre} MiB)")
d = tempfile.mkdtemp(prefix="cofre_conc_"); P = os.path.join(d, "cofre.dat")
# 10 tentativas (não 3): cada abertura em modo normal GASTA uma tentativa antes do Argon2 e devolve se a senha está certa.
# Com 3 escritores abrindo juntos e só 3 tentativas o contador chega a 0 por instantes e o leitor vê "contador danificado"
# (o arquivo NÃO é apagado; é só o aviso de arquivo suspeito). Na vida real só o dono da trava abre em modo normal.
base = c.Cofre.criar(P, S, 10, 0, "alto"); base.salvar(); base.fechar()
SEG = 10
procs = [subprocess.Popen([sys.executable, "-c", ESCRITOR, CAMINHO_PROG, P, S, f"w{i}", str(SEG)],
                          stdout=subprocess.PIPE, text=True) for i in range(NESC)]
leitor = subprocess.Popen([sys.executable, "-c", LEITOR, CAMINHO_PROG, P, S, str(SEG)], stdout=subprocess.PIPE, text=True)
confirmados, fins, conflitos_tot = [], 0, 0
for p in procs:
    out = p.communicate(timeout=180)[0].splitlines()
    ok(p.returncode == 0, f"escritor terminou sem erro (código {p.returncode})")
    for l in out:
        if l.startswith("OK "):
            confirmados.append(l.split()[1])
        elif l.startswith("FIM "):
            fins += 1; conflitos_tot += int(l.split()[2])
saida_leitor = leitor.communicate(timeout=180)[0].splitlines()
ok(fins == NESC, f"os {NESC} escritores chegaram ao fim")
ok(len(confirmados) > 0, f"houve gravações confirmadas ({len(confirmados)}; conflitos tratados: {conflitos_tot})")
ok(len(set(confirmados)) == len(confirmados), "nenhum id confirmado em duplicidade entre os processos")

try:
    final = c.Cofre.abrir(P, senha=S)
    ids = [r["id"] for r in final.registros]
    ok(True, f"o arquivo final abre normalmente ({len(ids)} itens)")
    perdidos = [i for i in confirmados if i not in set(ids)]
    ok(not perdidos, f"NENHUMA gravação confirmada se perdeu ({len(perdidos)} perdida(s) de {len(confirmados)})")
    ok(len(ids) == len(set(ids)), "nenhum item duplicado no arquivo final")
    final.fechar()
except Exception as ex:                                  # noqa: BLE001 - qualquer erro aqui é falha do teste
    ok(False, f"o arquivo final NÃO abriu: {type(ex).__name__}: {ex}")
sobras = [f for f in os.listdir(d) if f.endswith(".tmp")]
ok(not sobras, f"nenhum .tmp esquecido na pasta ({sobras})")
metade = [l for l in saida_leitor if l.startswith("PELA_METADE")]
ok(not metade, f"o leitor nunca viu o arquivo pela metade ({len(metade)} vez(es); 1ª: {metade[:1]})")
ok(any(l.startswith("FIM") for l in saida_leitor), f"o leitor terminou ({[l for l in saida_leitor if l.startswith('FIM')]})")

print("\nFALHAS: " + str(FAL) if FAL else "\nTODOS OK")
sys.exit(1 if FAL else 0)
