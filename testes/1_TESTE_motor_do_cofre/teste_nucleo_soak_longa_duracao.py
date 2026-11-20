"""SOAK TEST (longa duração) DO NÚCLEO: 1.000 ciclos seguidos de abrir -> alterar -> salvar -> fechar.

Os outros testes repetem 20-30 ciclos; aqui o objetivo é achar o que só aparece com uso MUITO prolongado:
 - vazamento de descritores de arquivo / handles do Windows (um por ciclo vira milhares);
 - threads que sobram (cada gravação roda numa thread; se alguma ficar presa, acumulam);
 - instâncias de Cofre que o coletor de lixo não consegue soltar (chaves vivas na memória);
 - memória do Python crescendo sem parar (tracemalloc, comparando o começo com o fim);
 - arquivos sobrando na pasta (.tmp, cópias .bak acima do limite) e o cofre crescendo sem motivo;
 - e, no fim, o cofre ainda abre, com o conteúdo certo.
Para ficar rápido, os níveis de proteção (Argon2id) são trocados por valores BARATOS só dentro deste teste (os parâmetros
vão no cabeçalho do arquivo, então o abrir usa os mesmos): o que se mede aqui é o gerenciamento de recursos, não a força
da senha (essa é medida em outros testes). Quantidade de ciclos: variável COFRE_SOAK_CICLOS (padrão 1000)."""
import gc, importlib.util, os, sys, threading, time, tracemalloc

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "6_TESTE_ferramentas_dos_testes"))
import _resultado; _resultado.registrar(__file__)          # grava resultados/resultado_nucleo_soak_longa_duracao.txt

spec = importlib.util.spec_from_file_location("c", os.path.abspath(os.path.join(AQUI, "..", "..", "cofre_senhas.py")))
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
FAL = []
CICLOS = int(os.environ.get("COFRE_SOAK_CICLOS", "1000"))


def ok(cond, msg):
    """Imprime [OK]/[FALHOU] (o executor procura estes marcadores) e guarda as falhas."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + msg, flush=True)
    if not cond:
        FAL.append(msg)


def descritores():
    """Descritores (Linux) ou handles (Windows) abertos por este processo; None se não der para medir."""
    return _resultado.handles_processo()


def cofres_vivos():
    gc.collect()
    return sum(1 for o in gc.get_objects() if type(o).__name__ == "Cofre")


c.NIVEIS["alto"] = (1, 8192)                               # Argon2id barato SÓ aqui (1 passada, 8 MiB = o mínimo aceito)
W = _resultado.pasta_temporaria("cofre_soak_")
P = os.path.join(W, "cofre.dat"); S = "cavalo azul come pizza na chuva 2026"
v = c.Cofre.criar(P, S, 5, 0, "alto")
v.registros.append(c.novo_item(servico="Soak", login="u", senha="Senha-0"))
v.salvar(forcar_copia=True); v.fechar(); del v
tamanho0 = os.path.getsize(P)

print(f"== {CICLOS} ciclos abrir/alterar/salvar/fechar")
PASSO = max(1, CICLOS // 10)                                # ~10 amostras ao longo da execução
AQUECE = min(50, PASSO)                                     # amostra de referência, depois do aquecimento
tracemalloc.start()
amostras = []                                               # (ciclo, descritores, threads, cofres, memória)
t0 = time.time()
for i in range(1, CICLOS + 1):
    a = c.Cofre.abrir(P, senha=S)
    a.registros[0]["senha"] = "Senha-%d" % i                # mesmo item, sempre: o cofre não deve crescer
    a.salvar(forcar_copia=(i % 25 == 0))
    if i % 100 == 0 or i == 1:                              # de vez em quando, o modo consulta (só leitura) e a troca de senha
        b = c.Cofre.abrir(P, senha=S, consulta=True); b.fechar(); del b
        a.trocar_senha(S + "x"); a.salvar(); a.trocar_senha(S); a.salvar()
    a.fechar(); del a
    if i == AQUECE or i % PASSO == 0:
        gc.collect()
        amostras.append((i, descritores(), threading.active_count(), cofres_vivos(), tracemalloc.get_traced_memory()[0]))
seg = time.time() - t0
print(f"  {CICLOS} ciclos em {seg:.1f}s ({1000 * seg / CICLOS:.1f} ms por ciclo)")
for a in amostras:
    print("  ciclo %4d | descritores %s | threads %d | Cofre vivos %d | memória %.0f KiB" % (a[0], a[1], a[2], a[3], a[4] / 1024))

ini, fim = amostras[0], amostras[-1]
print("== comparação do começo (depois do aquecimento) com o fim")
ok(ini[1] is None or fim[1] <= ini[1] + 3, f"descritores/handles não crescem: {ini[1]} -> {fim[1]}")
ok(fim[2] <= ini[2] + 1, f"threads não se acumulam: {ini[2]} -> {fim[2]}")
ok(fim[3] == 0, f"nenhuma instância de Cofre sobrando no heap ({fim[3]})")
cresc = (fim[4] - ini[4]) / 1024
ok(cresc < 512, f"memória do Python estável: {cresc:+.0f} KiB entre a 1ª amostra e a última (limite 512)")
# tendência: sem crescimento contínuo (o último terço não pode ser muito maior que o primeiro)
if len(amostras) >= 6:
    terco = len(amostras) // 3
    m1 = sum(a[4] for a in amostras[:terco]) / terco; m3 = sum(a[4] for a in amostras[-terco:]) / terco
    ok((m3 - m1) / 1024 < 512, f"sem tendência de crescimento: início {m1 / 1024:.0f} KiB, fim {m3 / 1024:.0f} KiB")

print("== a pasta e o cofre depois de tudo")
arqs = sorted(os.listdir(W))
ok(not [x for x in arqs if x.endswith(".tmp")], f"nenhum .tmp esquecido ({arqs})")
ok(len([x for x in arqs if ".bak" in x]) <= 5, "no máximo 5 cópias de segurança")
ok(os.path.getsize(P) <= tamanho0 + 8192, f"o arquivo não cresceu à toa ({tamanho0} -> {os.path.getsize(P)} bytes)")
z = c.Cofre.abrir(P, senha=S)
ok(len(z.registros) == 1 and z.registros[0]["senha"] == "Senha-%d" % CICLOS, "o cofre abre e tem o último valor gravado")
z.fechar()
tracemalloc.stop()

print("\nFALHAS: " + str(FAL) if FAL else "\nTODOS OK")
sys.exit(1 if FAL else 0)
