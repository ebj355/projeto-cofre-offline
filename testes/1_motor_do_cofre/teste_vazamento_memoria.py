"""Vazamento e resíduos de memória (sem interface): ciclos abrir -> editar -> buscar -> fechar com tracemalloc,
teto do cache de força, zeragem de buffers e ausência de Cofre "órfão" depois de fechado."""
import gc, os, sys, tempfile, time, tracemalloc, weakref
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import cofre_senhas as c

falhas = 0
def ok(cond, nome):
    """Registra uma verificação."""
    global falhas
    print(("  [OK] " if cond else "  [FALHOU] ") + nome)
    falhas += 0 if cond else 1

# 1) cache de força tem teto e descarta o mais antigo
c._CACHE_FORCA.clear()
for i in range(c._CACHE_FORCA_MAX * 3):
    c._forca_em_cache(f"Senha-{i}-xYz!")
ok(len(c._CACHE_FORCA) <= c._CACHE_FORCA_MAX, f"cache de força limitado ({len(c._CACHE_FORCA)} <= {c._CACHE_FORCA_MAX})")
ok(c._forca_em_cache("Senha-0-xYz!") is not None, "cache continua respondendo depois de descartar")

# 2) zeragem física do buffer
ba = bytearray(b"segredo-segredo-segredo")
c._zerar(ba)
ok(all(b == 0 for b in ba), "_zerar deixa o bytearray todo em zero")
chave = bytearray(os.urandom(32)); c._zerar(chave)
ok(not any(chave), "chave (bytearray) zerada")

# 3) ciclos de vida: abrir/editar/buscar/fechar, memória não pode crescer a cada volta
d = tempfile.mkdtemp(); caminho = os.path.join(d, "c.dat")
SENHA = "Mestra-De-Teste-Aa1!-xyz"
c.Cofre.criar(caminho, SENHA, 5, c.MODO_S, "alto")   # 256 MiB por derivação (o mínimo aceito pelo formato)
v = c.Cofre.abrir(caminho, senha=SENHA)
for i in range(500):
    v.registros.append(c.novo_item(servico=f"Conta {i}", login=f"u{i}@x.com", senha=f"Pw-{i}-Zz9!qq", notas="n" * 40))
v.salvar(); v.fechar(); v = None

def ciclo():
    """Uma volta completa: abre, edita 1 item, busca, salva e fecha."""
    v = c.Cofre.abrir(caminho, senha=SENHA)
    achados = [r for r in v.registros if "Conta 4" in r.get("servico", "")]
    v.registros[0]["notas"] = "editado " + str(time.time())
    v.salvar()
    ref = weakref.ref(v)
    v.fechar()
    return ref, len(achados)

ref, n = ciclo(); gc.collect()
ok(n > 0, "busca encontrou itens no ciclo")
ok(ref() is None, "Cofre fechado não fica preso na memória (sem referência circular)")
tracemalloc.start()
for _ in range(2): ciclo()          # aquecimento (caches internos)
gc.collect(); base = tracemalloc.get_traced_memory()[0]
VOLTAS = 12
for _ in range(VOLTAS): ciclo()
gc.collect(); fim = tracemalloc.get_traced_memory()[0]
tracemalloc.stop()
cresc = (fim - base) / 1024
ok(cresc < 256, f"{VOLTAS} ciclos abrir/editar/fechar: crescimento {cresc:.0f} KiB (limite 256 KiB, sem vazamento por volta)")
ok(cresc / VOLTAS < 16, f"crescimento por ciclo {cresc / VOLTAS:.1f} KiB")

# 4) o que sobra depois de fechar: DEK zerada/solta
v = c.Cofre.abrir(caminho, senha=SENHA); v.fechar()
ok(getattr(v, "dek", None) in (None, b"", bytearray()) or not any(v.dek), "DEK não fica no objeto depois de fechar")
ok(not v.registros, "registros descartados depois de fechar")
print("FALHAS:", falhas); sys.exit(1 if falhas else 0)
