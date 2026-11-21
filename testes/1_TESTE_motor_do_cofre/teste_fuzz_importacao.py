# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Fuzzing do leitor de planilhas/CSV (ler_planilha): bytes nulos, campos gigantes, UTF-16 com BOM trocado, UTF-8 inválido,
CSV truncado, .xlsx corrompido, arquivos aleatórios. Regra: NUNCA pode estourar um erro não tratado (só ValueError/OSError
com mensagem) nem travar; o que for lido não pode trazer caractere de controle. Uso: python testes/teste_fuzz_importacao.py"""
import os, sys, random, tempfile, time, zipfile
RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, RAIZ)
D = tempfile.mkdtemp(prefix="fuzz_cofre_"); os.chdir(D)
import cofre_senhas as c
FAL = []


def ok(cond, msg):
    print(("  [OK]   " if cond else "  [FALHOU] ") + msg)
    if not cond:
        FAL.append(msg)


def tenta(nome, dados, ext=".csv"):
    """Escreve 'dados' e passa pelo leitor. Devolve ('ok', registros) | ('recusou', msg) | ('QUEBROU', repr)."""
    arq = os.path.join(D, "f" + ext)
    with open(arq, "wb") as f:
        f.write(dados)
    t0 = time.time()
    try:
        regs, av = c.ler_planilha(arq)
        r = ("ok", regs)
    except (ValueError, OSError) as ex:
        r = ("recusou", str(ex))
    except Exception as ex:                       # qualquer outra coisa = defeito
        r = ("QUEBROU", f"{type(ex).__name__}: {ex}")
    if time.time() - t0 > 20:
        r = ("QUEBROU", "demorou mais de 20 s")
    return r


def limpo(regs):
    """Nenhum texto lido pode ter caractere de controle (exceto quebra de linha nas notas)."""
    for rg in regs:
        for k, v in rg.items():
            if isinstance(v, str) and any((ord(ch) < 32 and ch not in "\n\r\t") or ord(ch) == 0x7f for ch in v):
                return False
    return True


CAB = "serviço,login,senha,notas\n"
casos = {
    "bytes nulos nos campos": (CAB + "Ban\x00co,jo\x00ao,se\x00nha,n\x00ota\n").encode("utf-8"),
    "campo de senha com 5 MB": (CAB + "Site,user," + "A" * 5_000_000 + ",nota\n").encode("utf-8"),
    "nota com 20 MB": (CAB + "Site,user,pw," + "n" * 20_000_000 + "\n").encode("utf-8"),
    "UTF-16 LE com BOM": (CAB + "Banco,joao,senha1,x\n").encode("utf-16"),
    "UTF-16 LE com BOM de BE (trocado)": b"\xfe\xff" + (CAB + "Banco,joao,senha1,x\n").encode("utf-16-le"),
    "UTF-16 BE com BOM de LE (trocado)": b"\xff\xfe" + (CAB + "Banco,joao,senha1,x\n").encode("utf-16-be"),
    "UTF-8 inválido no meio": CAB.encode("utf-8") + b"Banco,jo\xff\xfe\xc3,senha,x\n",
    "só cabeçalho": CAB.encode("utf-8"),
    "vazio": b"",
    "só quebras de linha": b"\n\n\n\r\n\r\n",
    "aspas abertas sem fechar": (CAB + 'Banco,"joao,senha,x\nOutro,u,p,n\n').encode("utf-8"),
    "milhares de colunas": (",".join(f"c{i}" for i in range(20000)) + "\n" + ",".join("x" for _ in range(20000)) + "\n").encode("utf-8"),
    "milhares de linhas": (CAB + "".join(f"S{i},u{i},p{i},n\n" for i in range(60000))).encode("utf-8"),
    "caracteres de direção (RLO) e controle": (CAB + "Ban‮co,jo\u0007ao,se\u0001nha,x\n").encode("utf-8"),
    "injeção de fórmula": (CAB + "=cmd|'/C calc'!A0,+1+1,@SUM(1),-2+3\n").encode("utf-8"),
    "binário aleatório": random.Random(1).randbytes(300_000),
}
print("== 1) arquivos CSV hostis")
for nome, dados in casos.items():
    r = tenta(nome, dados)
    ok(r[0] != "QUEBROU", f"{nome}: {r[0]}" + (f" ({r[1][:80]})" if r[0] != "ok" else f" ({len(r[1])} contas)"))
    if r[0] == "ok":
        ok(limpo(r[1]), f"{nome}: sem caracteres de controle no que foi lido")

print("== 2) .xlsx corrompido ou malicioso")
import openpyxl
wb = openpyxl.Workbook(); ws = wb.active; ws.append(["serviço", "login", "senha"]); ws.append(["A", "b", "c"]); wb.save("ok.xlsx")
bom = open("ok.xlsx", "rb").read()
rng = random.Random(3)
for nome, dados in {
    ".xlsx truncado": bom[:len(bom) // 2],
    ".xlsx com bytes trocados": bytes(b ^ 0xFF if i % 97 == 0 else b for i, b in enumerate(bom)),
    "zip vazio com extensão xlsx": b"PK\x05\x06" + b"\x00" * 18,
    "texto puro com extensão xlsx": b"isto nao e uma planilha",
    "aleatório com extensão xlsx": rng.randbytes(50_000),
}.items():
    r = tenta(nome, dados, ".xlsx")
    ok(r[0] != "QUEBROU", f"{nome}: {r[0]}" + (f" ({r[1][:80]})" if r[0] != "ok" else ""))
# bomba de descompressão: um XML interno gigante e repetitivo
import io
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z, zipfile.ZipFile("ok.xlsx") as orig:
    for nome in orig.namelist():
        z.writestr(nome, orig.read(nome))
    z.writestr("xl/lixo.xml", b"0" * 300_000_000)
r = tenta("bomba de descompressão (300 MB num xlsx)", buf.getvalue(), ".xlsx")
ok(r[0] != "QUEBROU", f"bomba de descompressão: {r[0]}" + (f" ({r[1][:80]})" if r[0] != "ok" else ""))

wb = openpyxl.Workbook(); ws = wb.active; ws.append(["serviço", "login", "senha", "notas"]); ws.append(["A", "b", "c", "n" * 5_000_000]); wb.save("grande.xlsx")
r = tenta("célula xlsx com 5 MB", open("grande.xlsx", "rb").read(), ".xlsx")
ok(r[0] != "QUEBROU", f"célula xlsx com 5 MB: {r[0]}" + (f" ({r[1][:80]})" if r[0] != "ok" else f" ({len(r[1])} contas)"))
if r[0] == "ok":
    ok(all(len(v) <= 1_000_000 for rg in r[1] for v in rg.values() if isinstance(v, str)), "célula gigante foi cortada/limitada (<= 1 MB por campo)")

print("== 3) 200 arquivos aleatórios derivados de um CSV válido (mutação de bytes)")
base = (CAB + "Banco,joao,senha1,nota\nGmail,maria,s2,x\n").encode("utf-8")
quebrou = []
for i in range(200):
    b = bytearray(base)
    for _ in range(rng.randint(1, 8)):
        b[rng.randrange(len(b))] = rng.randrange(256)
    r = tenta("mut", bytes(b))
    if r[0] == "QUEBROU":
        quebrou.append(r[1])
ok(not quebrou, f"nenhuma das 200 mutações estourou erro não tratado {quebrou[:2]}")
print("\nFALHAS:", FAL)
sys.exit(1 if FAL else 0)
