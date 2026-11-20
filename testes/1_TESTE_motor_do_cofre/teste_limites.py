"""Valores-limite, memória e vazamento: senhas extremas, itens extremos, zerar_objeto sem corromper vizinhos."""
import gc, os, secrets, sys, tempfile, unicodedata
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "6_TESTE_ferramentas_dos_testes"))  # testes/6_TESTE_ferramentas_dos_testes/ -> _util_mem.py
from _util_mem import pico_kb
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import cofre_senhas as c
falhas = []
def ok(cond, msg):
    if not cond: falhas.append(msg)
d = tempfile.mkdtemp()
# senha vazia recusada; demais extremos aceitos e reabrem
try: c.Cofre.criar(os.path.join(d, "v.dat"), "", 3, 0, "alto"); ok(False, "senha vazia aceita")
except ValueError: pass
for i, S in enumerate([" " * 14, "a" * 14, "\x00abc\x00defghij1A!", "é" * c.MAX_SENHA, "MestráAa1!xyz", "😀" * 30, "A" * c.MAX_SENHA]):
    p = os.path.join(d, "s%d.dat" % i)
    try: c.Cofre.criar(p, S, 3, 0, "alto").fechar(); c.Cofre.abrir(p, senha=S).fechar()
    except Exception as e: ok(False, "senha extrema %d: %r" % (i, e))
for i, S in enumerate(["a", "curta demais", "é" * 13]):        # abaixo do mínimo de 14: recusadas também no núcleo
    try: c.Cofre.criar(os.path.join(d, "c%d.dat" % i), S, 3, 0, "alto"); ok(False, "senha curta %d deveria ser recusada" % i)
    except ValueError: pass
for i, S in enumerate(["é" * 5000, "A" * 300_000]):      # acima de MAX_SENHA: recusadas DE PROPÓSITO (negação de serviço)
    try: c.Cofre.criar(os.path.join(d, "g%d.dat" % i), S, 3, 0, "alto"); ok(False, "senha gigante %d deveria ser recusada" % i)
    except ValueError: pass
p = os.path.join(d, "n.dat"); S = "Sênha#Forte9xyz"; c.Cofre.criar(p, S, 3, 0, "alto").fechar()
for f in ("NFC", "NFD"):
    try: c.Cofre.abrir(p, senha=unicodedata.normalize(f, S)).fechar()
    except Exception as e: ok(False, "abrir em %s: %r" % (f, e))
# itens extremos
p = os.path.join(d, "i.dat"); v = c.Cofre.criar(p, "Mestra#Forte99", 3, 0, "alto")
for val in [None, "", "\x00", "‮", "x" * 3_000_000, 123, "=cmd|' /C calc'!A0", "<script>", "'; DROP--", "\n\r\t"]:
    try: v.registros.append(c.novo_item(servico="s", senha=val, obs=val)); v.salvar()
    except Exception as e: ok(False, "item extremo %r: %r" % (str(val)[:10], e))
v.fechar()
try: c.Cofre.abrir(p, senha="Mestra#Forte99").fechar()
except Exception as e: ok(False, "reabrir após extremos: %r" % e)
# zerar_objeto: nunca toca internados/imortais/curtos/não-ASCII e não invade vizinhos
i = sys.intern("senha_interna_x"); ok(not c.zerar_objeto(i) and i == "senha_interna_x", "internado alterado")
ok(not any(c.zerar_objeto(x) for x in (None, "é" * 5, b"", b"a", 7)), "zerou o que não devia")
viz = [bytes([65 + k % 26]) * k + b"!" for k in range(2, 300)]; ref = [bytes(x) for x in viz]
compartilhado = bytes(b"segredo-compartilhado")
alias = compartilhado
ok(not c.zerar_objeto(compartilhado) and alias == b"segredo-compartilhado", "bytes compartilhados preservados")
for k in range(1, 200):
    a = "x" + secrets.token_hex(k)
    if hasattr(sys, "_is_interned") and not sys.flags.dev_mode:
        ok(c.zerar_objeto(a) and a == "\0" * len(a), "str não zerada")
    else:
        original = a
        ok(not c.zerar_objeto(a) and a == original, "str preservada sem zeragem segura neste modo")
for k in range(2, 300):
    b = bytes(secrets.token_bytes(k))
    if sys.flags.dev_mode or "debug" in os.environ.get("PYTHONMALLOC", "").lower():
        original = b
        ok(not c.zerar_objeto(b) and b == original, "bytes preservados no modo de depuração")
    else:
        ok(c.zerar_objeto(b) and b == bytes(k), "bytes não zerado")
ok(viz == ref, "vizinho corrompido")
# vazamento: 60 ciclos abrir/salvar/fechar
q = os.path.join(d, "l.dat"); M = "Mestra" + secrets.token_hex(6) + "Aa1!"; c.Cofre.criar(q, M, 3, 0, "alto").fechar()
def ciclo():
    x = c.Cofre.abrir(q, senha=M); x.registros.append(c.novo_item(servico="s", senha="x" * 20)); x.salvar(); x.fechar()
for _ in range(5): ciclo()
gc.collect(); r0 = pico_kb(); o0 = len(gc.get_objects())
for _ in range(60): ciclo()
gc.collect(); cresc = pico_kb() - r0
ok(cresc < 4096, "RSS cresceu %d KB em 60 ciclos" % cresc); ok(len(gc.get_objects()) - o0 < 500, "objetos vazando")
print("FALHAS:", falhas)
