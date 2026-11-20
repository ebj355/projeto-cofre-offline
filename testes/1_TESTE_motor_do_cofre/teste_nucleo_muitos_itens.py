"""Cofre GRANDE: 5.000 itens (textos de tamanhos variados, com acentos e emoji): cria, salva, fecha e reabre com tudo idêntico; o arquivo cresce em proporção (não explode),
salvar e abrir ficam em tempo razoável, e cada salvamento seguinte (que renova as cópias de segurança) continua íntegro. Mede o pico de memória do processo."""
import json, os, random, sys, time
_RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, _RAIZ); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "6_TESTE_ferramentas_dos_testes"))
import _resultado; _resultado.registrar(__file__)
from _util_mem import pico_kb
import cofre_senhas as c
f = []
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome, flush=True); f.append(bool(cond))
N = int(os.environ.get("COFRE_ITENS", "5000"))
rnd = random.Random(7)
PALAVRAS = ["banco", "email", "loja", "ação", "coração", "senha", "café", "😀", "漢字", "servidor", "cartão", "nuvem"]
def frase(n): return " ".join(rnd.choice(PALAVRAS) for _ in range(n))
D = _resultado.pasta_temporaria("cofre_grande_")
P = os.path.join(D, "cofre.dat"); S = "cavalo azul come pizza na chuva"
v = c.Cofre.criar(P, S, 3, c.MODO_S, "alto")
v.registros.extend(c.novo_item(servico=frase(rnd.randint(1, 4)), usuario="u%d@exemplo.com" % i, senha=frase(rnd.randint(2, 6)), obs=frase(rnd.randint(0, 30))) for i in range(N))
t0 = time.perf_counter(); v.salvar(); t_salvar = time.perf_counter() - t0
def foto(regs):
    """Retrato em TEXTO NOVO (ao fechar, o cofre zera os textos dos itens na memória: uma cópia que os compartilha seria zerada junto)."""
    return json.dumps(regs, sort_keys=True)
modelo = foto(v.registros)
tam = os.path.getsize(P)
print("  [info] %d itens: arquivo %.2f MiB, salvar %.1f s" % (N, tam / 1048576, t_salvar), flush=True)
ok(tam < N * 4096, "o arquivo cresce em proporção razoável (%.0f bytes por item, limite 4096)" % (tam / N))
ok(tam < c.LIMITE_COFRE, "continua abaixo do limite de tamanho do programa (%d MiB)" % (c.LIMITE_COFRE // 1048576))
ok(t_salvar < 60, "salvar %d itens em %.1f s (limite 60 s)" % (N, t_salvar))
v.fechar()
t0 = time.perf_counter(); v = c.Cofre.abrir(P, senha=S); t_abrir = time.perf_counter() - t0
ok(len(v.registros) == N and foto(v.registros) == modelo, "reabriu com os %d itens, todos IDÊNTICOS" % N)
ok(t_abrir < 60, "abrir em %.1f s (limite 60 s)" % t_abrir)
for r in range(3):                                           # vários salvamentos seguidos (renovam cópias e contador)
    k = rnd.randrange(N); v.registros[k] = dict(v.registros[k], obs="alterado %d 😀" % r)
    modelo = foto(v.registros)
    v.salvar()
v.fechar()
v = c.Cofre.abrir(P, senha=S)
ok(foto(v.registros) == modelo, "depois de 3 salvamentos seguidos, tudo íntegro e as alterações presentes")
v.fechar()
pico = pico_kb()
print("  [info] pico de memória do processo: %.0f MiB" % (pico / 1024), flush=True)
ok(pico < 1_500_000, "pico de memória abaixo de 1,5 GiB (%.0f MiB)" % (pico / 1024))
print("\nTODOS OK" if all(f) else "\nHOUVE FALHAS")
sys.exit(0 if all(f) else 1)
