"""Ida e volta com dados ALEATÓRIOS (como o Hypothesis, sem depender dele; semente fixa e mostrada para repetir): vários ciclos de criar/editar/apagar itens
com textos de todo tipo (acentos, emoji, chinês, controle, vazio), salvar, fechar e reabrir: o que volta é IDÊNTICO ao que foi guardado. Depois vira bits do arquivo:
abrir nunca pode devolver dados DIFERENTES em silêncio, nem estourar erro não tratado (IndexError, KeyError, struct.error...)."""
import json, os, random, shutil, struct, sys
_RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, _RAIZ); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "6_ferramentas_dos_testes"))
import _resultado; _resultado.registrar(__file__)
import cofre_senhas as c
f = []
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome, flush=True); f.append(bool(cond))
SEMENTE = int(os.environ.get("COFRE_SEMENTE", "20261116"))
rnd = random.Random(SEMENTE)
print("  [info] semente %d (para repetir: COFRE_SEMENTE=%d)" % (SEMENTE, SEMENTE), flush=True)
ALFABETOS = ["abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", "áéíóúâêôãõçÁÉÍÓÚÇñü", "😀🔑🔒💥🧪", "漢字かなカナ한글", "!@#$%^&*()_+-=[]{};':\",./<>?\\|`~",
             " \t\n\r\x00\x01\x1f\x7f", "‮​ ﻿", "<script>alert(1)</script>", "=cmd|' /C calc'!A0"]
def texto():
    if rnd.random() < 0.1: return ""
    n = rnd.choice([1, 3, 10, 40, 200, 1500])
    return "".join(rnd.choice(rnd.choice(ALFABETOS)) for _ in range(n))
def foto(regs):
    """Retrato em TEXTO NOVO dos itens. Não dá para guardar os próprios dicionários: ao fechar, o cofre zera na memória os textos dos itens
    (de propósito), e uma cópia rasa/profunda compartilha esses mesmos textos e seria zerada junto."""
    return json.dumps(regs, sort_keys=True)
def item():
    return c.novo_item(servico=texto(), usuario=texto(), senha=texto(), obs=texto())

D = _resultado.pasta_temporaria("cofre_aleat_")
P = os.path.join(D, "cofre.dat"); S = "cavalo azul come pizza na chuva"
v = c.Cofre.criar(P, S, 3, c.MODO_S, "alto")
modelo = foto([])
n_itens = 0
ciclos = 8
for ciclo in range(ciclos):
    for _ in range(rnd.randint(1, 12)):
        acao = rnd.random()
        if acao < 0.6 or not v.registros:
            v.registros.append(item())
        elif acao < 0.8:
            k = rnd.randrange(len(v.registros)); v.registros[k] = dict(v.registros[k], senha=texto(), obs=texto())
        else:
            v.registros.pop(rnd.randrange(len(v.registros)))
    v.salvar()
    modelo = foto(v.registros); n_itens = len(v.registros)
    v.fechar()
    v = c.Cofre.abrir(P, senha=S)
    if foto(v.registros) != modelo:
        ok(False, "ciclo %d: o que voltou é DIFERENTE do que foi guardado (%d itens)" % (ciclo + 1, n_itens)); break
else:
    ok(True, "%d ciclos de criar/editar/apagar/salvar/reabrir: tudo voltou idêntico (último com %d itens)" % (ciclos, n_itens))
v.fechar()

# bits virados: nunca dados diferentes em silêncio, nunca erro não tratado
with open(P, "rb") as a: bruto = a.read()
INESPERADOS = (IndexError, KeyError, TypeError, AttributeError, UnicodeDecodeError, struct.error, json.JSONDecodeError, MemoryError, OverflowError, RecursionError, AssertionError, ZeroDivisionError)
silencio, inesperado, recusados, iguais = [], [], 0, 0
voltas = 24
for k in range(voltas):
    pos = rnd.randrange(len(bruto)); bit = 1 << rnd.randrange(8)
    d2 = os.path.join(D, "flip%d" % k); os.makedirs(d2)
    p2 = os.path.join(d2, "cofre.dat")
    dados = bytearray(bruto); dados[pos] ^= bit
    with open(p2, "wb") as a: a.write(dados)
    try:
        w = c.Cofre.abrir(p2, senha=S, consulta=True)
        if foto(w.registros) == modelo: iguais += 1
        else: silencio.append((pos, bit))
        w.fechar()
    except INESPERADOS as e:
        inesperado.append((pos, bit, type(e).__name__))
    except Exception:
        recusados += 1
    shutil.rmtree(d2, True)
print("  [info] %d bits virados: %d recusados com erro do programa, %d sem efeito (mesmos dados), %d suspeitos" % (voltas, recusados, iguais, len(silencio) + len(inesperado)), flush=True)
ok(not silencio, "nenhum bit virado devolveu dados DIFERENTES em silêncio %s" % (silencio[:3] or ""))
ok(not inesperado, "nenhum bit virado causou erro não tratado %s" % (inesperado[:3] or ""))
print("\nTODOS OK" if all(f) else "\nHOUVE FALHAS")
sys.exit(0 if all(f) else 1)
