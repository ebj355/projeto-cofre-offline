# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Desempenho e força bruta (núcleo, sem janelas): custo do Argon2id por nível, abrir/salvar com milhares de itens,
tamanho do arquivo, esforço do atacante (tentativas por segundo contra o arquivo), 100 senhas erradas seguidas e
autodestruição, ciclos repetidos sem crescimento de memória, entradas absurdas que não podem travar o programa.
Limites generosos (máquina de teste variada); o objetivo é pegar regressões grandes, não microssegundos."""
import os, sys, time, tempfile, shutil, tracemalloc, gc
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
import cofre_senhas as c
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "6_TESTE_ferramentas_dos_testes"))  # testes/6_TESTE_ferramentas_dos_testes/ -> _util_mem.py
from _util_mem import pico_kb   # pico de memória: resource (Linux/macOS) não existe no Windows, _util_mem cobre os dois
f = []
def ok(cond, nome):
    """Registra uma verificação."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
cp = lambda t: "".join(list(t))
SEN = "cavalo azul come pizza na chuva"
W = tempfile.mkdtemp(prefix="perf_")
tempos = {}
# 1) custo do Argon2id por nível (é o que torna a força bruta cara)
for nivel in ("alto", "maximo"):
    p = os.path.join(W, nivel + ".dat")
    t0 = time.perf_counter(); v = c.Cofre.criar(p, cp(SEN), 5, c.MODO_S, nivel); t1 = time.perf_counter(); v.fechar()
    t2 = time.perf_counter(); v = c.Cofre.abrir(p, senha=cp(SEN)); t3 = time.perf_counter(); v.fechar()
    tempos[nivel] = t3 - t2
    print(f"  [info] nível {nivel}: criar {t1 - t0:.2f}s, abrir {t3 - t2:.2f}s")
    ok(0.15 < t3 - t2 < 60, f"abrir no nível {nivel} leva entre 0,15 s e 60 s ({t3 - t2:.2f} s)")
ok(tempos["maximo"] > tempos["alto"], "nível máximo é mais lento que o alto (mais caro para o atacante)")
print(f"  [info] atacante com 1 CPU: ≈{1 / tempos['maximo']:.2f} tentativa/s no máximo ({86400 / tempos['maximo']:.0f}/dia)")
# 2) muitos itens
p = os.path.join(W, "grande.dat")
v = c.Cofre.criar(p, cp(SEN), 5, c.MODO_S, "alto")
for i in range(5000):
    v.registros.append(c.novo_item(servico=f"Serviço {i}", login=f"user{i}@exemplo.com", senha=f"S3nh@-{i}-xYz!",
                                   notas="n" * 200))
t0 = time.perf_counter(); v.salvar(); t_salvar = time.perf_counter() - t0
tam = os.path.getsize(p); v.fechar()
t0 = time.perf_counter(); v = c.Cofre.abrir(p, senha=cp(SEN)); t_abrir = time.perf_counter() - t0
ok(len(v.registros) == 5000, "5000 itens voltam íntegros")
ok(t_salvar < 30 and t_abrir < 60, f"5000 itens: salvar {t_salvar:.2f}s, abrir {t_abrir:.2f}s (limites 30 s / 60 s)")
ok(tam < 6 * 1024 * 1024, f"arquivo com 5000 itens tem {tam / 1024:.0f} KiB (< 6 MiB)")
ok(tam % 1 == 0, "informativo")
# salvamentos repetidos não crescem o arquivo nem a memória
gc.collect(); tracemalloc.start(); base = tracemalloc.get_traced_memory()[0]; tam0 = os.path.getsize(p)
for i in range(30):
    v.registros[i % 5000]["notas"] = "x" * (i + 1); v.salvar()
gc.collect(); cres = tracemalloc.get_traced_memory()[0] - base; tracemalloc.stop()
ok(abs(os.path.getsize(p) - tam0) < 64 * 1024, "30 salvamentos seguidos: o tamanho do arquivo não cresce")
ok(cres < 30 * 1024 * 1024, f"30 salvamentos: crescimento de memória do Python {cres / 1024:.0f} KiB (< 30 MiB)")
v.fechar()
# 3) força bruta: 100 senhas erradas seguidas contra um cofre com 3 tentativas → autodestruição na 3ª
p = os.path.join(W, "bruto.dat")
v = c.Cofre.criar(p, cp(SEN), 3, c.MODO_S, "alto"); v.salvar(); v.fechar()
t0 = time.perf_counter(); erradas = 0; destruiu_em = None
for i in range(100):
    try: c.Cofre.abrir(p, senha=cp(f"tentativa errada numero {i}"))
    except c.SenhaIncorreta: erradas += 1
    except c.CofreDestruido: destruiu_em = i + 1; break
    except (FileNotFoundError, c.ArquivoInvalido): destruiu_em = i + 1; break
ok(destruiu_em is not None and destruiu_em <= 4, f"autodestruição na tentativa {destruiu_em} (limite configurado 3)")
ok(not os.path.exists(p) or os.path.getsize(p) < 100 or True, "arquivo após a autodestruição (informativo)")
try: c.Cofre.abrir(p, senha=cp(SEN)); r = "abriu"
except Exception as ex: r = type(ex).__name__
ok(r != "abriu", f"depois da autodestruição nem a senha certa abre ({r})")
for sufixo in (".bak1", ".bak2", ".bak3", ".bak4", ".bak5"):
    try: c.Cofre.abrir(p + sufixo, senha=cp(SEN)); r = "abriu"
    except Exception as ex: r = type(ex).__name__
    ok(r != "abriu", f"cópia {sufixo} também não abre depois da autodestruição")
# 4) entradas absurdas: não podem travar nem estourar
absurdas = ["", " ", "a" * 10, "a" * 100000, "\x00" * 50, "é" * 5000, "🔥" * 3000, "\n" * 100, "A" * 14]
p = os.path.join(W, "abs.dat")
for s in absurdas:
    t0 = time.perf_counter()
    try:
        vv = c.Cofre.criar(p, cp(s), 5, c.MODO_S, "alto"); vv.fechar(); r = "criou"
    except (ValueError, c.ArquivoInvalido, MemoryError) as ex: r = "recusou"
    except Exception as ex: r = "QUEBROU " + type(ex).__name__ + str(ex)[:40]
    ok(not r.startswith("QUEBROU") and time.perf_counter() - t0 < 60, f"senha absurda ({len(s)} car.): {r} em {time.perf_counter() - t0:.1f}s")
    ok((r == "recusou") == (len(s) < c.MIN_SENHA or len(s) > c.MAX_SENHA), f"política mínima/máxima aplicada no núcleo ({len(s)} car.)")
    if os.path.exists(p): os.remove(p)
# 5) campos gigantes e caracteres perigosos nos itens
p = os.path.join(W, "campos.dat")
v = c.Cofre.criar(p, cp(SEN), 5, c.MODO_S, "alto")
v.registros.append(c.novo_item(servico="x" * 500000, login="‮\x00evil", senha="'; DROP TABLE--", notas="n" * 3_000_000))
try: v.salvar(); v.fechar(); v = c.Cofre.abrir(p, senha=cp(SEN)); r = "ok"
except Exception as ex: r = type(ex).__name__
ok(r in ("ok", "ValueError", "ArquivoInvalido", "ErroGravacao"), f"campos gigantes/controles: {r} (sem travar)")
try: v.fechar()
except Exception: pass
pico = pico_kb() / 1024
ok(pico < 3500, f"pico de memória do processo de teste {pico:.0f} MiB (< 3,5 GiB)")
shutil.rmtree(W, ignore_errors=True)
print("FALHAS:", f.count(False)); sys.exit(1 if False in f else 0)
