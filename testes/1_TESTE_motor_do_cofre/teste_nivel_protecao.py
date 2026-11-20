"""Ranking de proteção: pontos e nível conforme o que está ativo (modo, memória do Argon2, FIDO, reserva, computador)."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
import cofre_senhas as c
f = []
def ok(cond, nome):
    """Registra uma verificação."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
MAX, ALTO = c.NIVEIS["maximo"][1], c.NIVEIS["alto"][1]
ch = lambda n: {"nome": n, "cred": b"x" + n.encode()}
p, n, it = c.nivel_protecao(c.MODO_S, ALTO, None)
ok(n == "Básica" and p == 35, f"só senha, memória alta: Básica ({p})")
p2, n2, _ = c.nivel_protecao(c.MODO_E, MAX, None)
ok(p2 > p and n2 == "Forte", f"senha E chave de acesso, memória máxima: {n2} ({p2})")
p3, _, _ = c.nivel_protecao(c.MODO_S, ALTO, {"chaves": [ch("Chave A")]})
ok(p3 == p + 20, "adicionar chave FIDO sobe 20 pontos")
p4, _, _ = c.nivel_protecao(c.MODO_S, ALTO, {"chaves": [ch("Chave A"), ch("Chave B")]})
ok(p4 == p3 + 7, "segunda chave (reserva) sobe mais 7")
pm, nm, itm = c.nivel_protecao(c.MODO_E, MAX, {"chaves": [ch("A"), ch("B")]}, {"n": 1})
ok(pm == 100 and nm == "Máxima", "tudo ativo (chave E, FIDO, reserva, computador, memória máxima) = 100 / Máxima")
ok(not any("igital" in r[0] or "Hello" in r[0] or r[3] == "digital" for r in itm + it), "sem nenhum item de digital / Windows Hello no ranking")
ok(all(0 <= c.nivel_protecao(m, mm, fi)[0] <= 100 for m in (0, 1, 2) for mm in (ALTO, MAX) for fi in (None, {"chaves": [ch("a")]})),
   "pontuação sempre entre 0 e 100")
ok(any(r[3] == "fido" and not r[2] for r in it), "sem FIDO: o ranking oferece 'fido' como próxima ação")
print("FALHAS:", f.count(False)); sys.exit(1 if False in f else 0)
