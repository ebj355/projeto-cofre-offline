"""Senha mestra fraca recusada, checagem de vazamentos (k-anonymity, rede simulada) e tempo de bloqueio configurável."""
import os, sys, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import cofre_senhas as c
falhas = []
def ok(cond, msg):
    if not cond: falhas.append(msg)

# senha mestra: frases boas passam; previsíveis/fracas são recusadas pela força estimada
for boa in ("cavalo azul come pizza na chuva", "Mestra#Forte99", "xK9#mP2$vL8@qR5!"):
    ok(c.avaliar_senha(boa) is None, "recusou senha boa: " + boa)
for fraca in ("Corinthians2024!!", "Abcdefghij1234!", "aaaaaaaaaaaaaaZ1", "curta", "12345678901234"):
    ok(c.avaliar_senha(fraca) is not None, "aceitou senha fraca: " + fraca)

# k-anonymity: vetor conhecido do SHA-1 de "password"
pre, suf = c.hibp_dividir("password")
ok((pre, suf) == ("5BAA6", "1E4C9B93F3F0682250B6CF8331B7EE68FD8"), "SHA-1 de 'password' dividido errado: %s %s" % (pre, suf))
resp = "0018A45C4D1DEF81644B54AB7F969B88D65:3\r\n1E4C9B93F3F0682250B6CF8331B7EE68FD8:10434004\r\n0000000000000000000000000000000000A:0\r\n"
ok(c.hibp_vezes(suf, resp) == 10434004, "contagem errada")
ok(c.hibp_vezes("0000000000000000000000000000000000A", resp) == 0, "enchimento (contagem 0) contou como vazado")
ok(c.hibp_vezes("FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF", resp) == 0, "sufixo ausente contou")

chamadas = []
def falso(prefixo):
    chamadas.append(prefixo)
    return resp if prefixo == "5BAA6" else "ABCDEF0123456789ABCDEF0123456789ABC:7\r\n"
p2 = c.hibp_dividir("outra senha qualquer 9!")
pedidos = [(("Banco", "Senha"), pre, suf), (("Email", "Senha"), pre, suf), (("Site", "Senha"), *p2)]
ach = c.hibp_verificar(pedidos, baixar=falso)
ok(sorted(chamadas) == sorted({pre, p2[0]}), "mais de 1 consulta por prefixo: %s" % chamadas)
ok(all(len(x) == 5 and set(x) <= set("0123456789ABCDEF") for x in chamadas), "saiu algo além do prefixo de 5")
ok([a[0][0] for a in ach] == ["Banco", "Email"] and ach[0][1] == 10434004, "achados errados: %s" % ach)
ok(c.hibp_verificar(pedidos, baixar=falso, cancelar=lambda: True) == [], "cancelar não parou")

# a chamada de rede de verdade (urlopen trocado): só o prefixo vai na URL, HTTPS, e entradas ruins são recusadas
import urllib.request
vistos = {}
class R:
    status = 200
    def __init__(s, d=b"AAA:1\r\n"): s.d = d
    def read(s, n=-1): return s.d[:n]
    def __enter__(s): return s
    def __exit__(s, *a): return False
def urlopen_falso(req, timeout=None):
    vistos["url"] = req.full_url; vistos["h"] = dict(req.header_items()); vistos["t"] = timeout
    return vistos.get("resposta", R())
original = urllib.request.urlopen
urllib.request.urlopen = urlopen_falso
try:
    c._hibp_baixar("5BAA6")
    ok(vistos["url"] == "https://api.pwnedpasswords.com/range/5BAA6", "URL errada: " + vistos["url"])
    ok(vistos["h"].get("Add-padding") == "true" and vistos["t"], "sem enchimento/tempo limite")
    for ruim in ("5BAA61E4C9B93F3F0682250B6CF8331B7EE68FD8", "5baa6", "5BAA", "5BAA6/../x", "5BAA6?x=1", ""):
        try: c._hibp_baixar(ruim); ok(False, "aceitou prefixo ruim: %r" % ruim)
        except ValueError: pass
    vistos["resposta"] = R(b"x" * (5 * 1024 * 1024))
    try: c._hibp_baixar("5BAA6"); ok(False, "aceitou resposta gigante")
    except OSError: pass
    vistos["resposta"] = types.SimpleNamespace(status=503, read=lambda n=-1: b"", __enter__=lambda s: s, __exit__=lambda *a: False)
    class R503(R): status = 503
    vistos["resposta"] = R503()
    try: c._hibp_baixar("5BAA6"); ok(False, "aceitou status 503")
    except OSError: pass
finally:
    urllib.request.urlopen = original

# tempo de bloqueio automático: do cofre, com limites e padrão
def ms(meta, cofre=True):
    obj = types.SimpleNamespace(cofre=types.SimpleNamespace(meta=meta) if cofre else None, INATIVIDADE_MS=c.App.INATIVIDADE_MS)
    return c.App._inatividade_ms(obj)
ok(ms({}) == 180000, "padrão não é 3 min")
ok(ms({"bloqueio_min": 10}) == 600000, "10 min")
ok(ms({"bloqueio_min": 1}) == 60000 and ms({"bloqueio_min": 30}) == 1800000, "limites 1 e 30")
ok(ms({"bloqueio_min": 0}) == 180000 and ms({"bloqueio_min": 99}) == 180000 and ms({"bloqueio_min": "x"}) == 180000, "valor fora dos limites")
ok(ms({}, cofre=False) == 180000, "sem cofre")
print("FALHAS:", falhas)
