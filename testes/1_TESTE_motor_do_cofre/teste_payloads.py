# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Payloads hostis nos campos (10 mil caracteres, nulos, quebras de linha, HTML/SQL, bidi, emoji): têm de ir e voltar
do arquivo cifrado sem erro e sem alteração do que é seguro guardar; e a importação tem de sanear os campos."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import cofre_senhas as c

falhas = 0
def ok(cond, nome):
    """Registra uma verificação."""
    global falhas
    print(("  [OK] " if cond else "  [FALHOU] ") + nome)
    falhas += 0 if cond else 1

PAYLOADS = {"longo": "A" * 10000, "nulo": "a\x00b\x00c", "quebra": "linha1\nlinha2\r\nlinha3",
            "html": "<script>alert(1)</script><img src=x onerror=alert(1)>", "sql": "'; DROP TABLE contas;--",
            "bidi": "abc‮FDP.exe", "emoji": "🔐🙂 çãõ ñ 日本語", "formula": "=cmd|' /C calc'!A0"}
PAYLOADS_REF = dict(PAYLOADS)   # cópias de referência (o cofre zera, ao fechar, os textos que recebeu)
PAYLOADS_REF = {k: "".join(list(t)) for k, t in PAYLOADS_REF.items()}
d = tempfile.mkdtemp(); p = os.path.join(d, "c.dat"); S = "Mestra-Payload-Aa1!-xyz"
c.Cofre.criar(p, S, 5, c.MODO_S, "alto")
v = c.Cofre.abrir(p, senha=S)
for nome, txt in PAYLOADS.items():
    cp = lambda: "".join(list(txt))
    v.registros.append(c.novo_item(servico=nome, login=cp(), senha=cp(), notas=cp()))
v.salvar(); v.fechar()
v = c.Cofre.abrir(p, senha=S)
por = {r["servico"]: r for r in v.registros}
for nome, txt in PAYLOADS.items():
    r = por.get(nome)
    txt = PAYLOADS_REF[nome]
    if r is not None and r["login"] != txt: pass
    ok(r is not None and r["login"] == txt and r["senha"] == txt and r["notas"] == txt, f"cofre guarda e devolve intacto: {nome}")
v.fechar()

# importação: um campo gigante recusa a planilha inteira; o resto sai saneado (sem controle/bidi)
try:
    c.sanear_registros([{"servico": PAYLOADS_REF["longo"], "login": "a"}]); recusou = False
except ValueError as e:
    recusou = "Nada foi importado" in str(e)
ok(recusou, "importação: campo de 10 mil caracteres recusa a planilha inteira (nada entra no cofre)")
regs = [{"servico": "s" + n, "login": t[:200], "senha": t[:900], "notas": t} for n, t in PAYLOADS_REF.items() if n != "longo"]
lim = c.sanear_registros(regs)
saida = lim[0] if isinstance(lim, tuple) else lim
ok(all("\x00" not in str(x) and "\u202e" not in str(x) for r in saida for x in r.values()), "importação: nulos e inversão de texto removidos")
print("FALHAS:", falhas); sys.exit(1 if falhas else 0)
