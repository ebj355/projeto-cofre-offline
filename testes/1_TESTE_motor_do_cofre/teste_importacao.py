"""Importação de planilhas Excel/CSV (cabeçalhos bagunçados, Chrome, acentos, PIN com zero) e apagamento seguro.
Uso:  python testes/teste_importacao.py"""
import os, sys, tempfile
# usa o cofre_senhas.py da pasta do projeto e trabalha numa pasta temporária (não suja o repositório)
RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, RAIZ)
os.chdir(tempfile.mkdtemp(prefix="teste_cofre_"))
import os, sys, csv
import openpyxl, cofre_senhas as c
W = os.getcwd(); f = []
def ok(cond, nome):
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(cond)

# 1) planilha "bagunçada": título, cabeçalho na linha 3, acentos, colunas fora de ordem, PIN numérico
wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Bancos"
ws.append(["Minhas senhas 2026"]); ws.append([])
ws.append(["Observações", "Usuário", "Serviço", "Senha", "PIN"])
ws.append(["conta salário", "joao.silva", "Banco do Brasil", "S3nh@Forte!", 1234])
ws.append([None, "joao@gmail.com", "Gmail", "outrasenha", None])
ws.append([None, None, None, None, None])
ws.append(["só nota", None, "Sem credencial", None, None])
ws2 = wb.create_sheet("Trabalho")
ws2.append(["Site", "URL", "E-mail", "Password"])
ws2.append(["CRC Nacional", "https://crc.example", "maria", "crc#2026"])
wb.save("a.xlsx")
regs, av = c.ler_planilha("a.xlsx")
ok(len(regs) == 3, f"3 contas lidas de 2 abas ({len(regs)})")
bb = [r for r in regs if r["servico"] == "Banco do Brasil"][0]
ok(bb["login"] == "joao.silva" and bb["senha"] == "S3nh@Forte!" and bb["pin"] == "1234" and bb["notas"] == "conta salário",
   "colunas fora de ordem e com acento mapeadas certo; PIN numérico virou '1234'")
crc = [r for r in regs if r["servico"] == "CRC Nacional"][0]
ok(crc["login"] == "maria" and crc["senha"] == "crc#2026" and "https://crc.example" in crc["notas"], "aba 2 com nomes em inglês + URL nas notas")

# 2) sem cabeçalho
wb = openpyxl.Workbook(); ws = wb.active
ws.append(["Netflix", "maria", "senha123", "", "família"])
wb.save("b.xlsx")
regs, av = c.ler_planilha("b.xlsx")
ok(len(regs) == 1 and regs[0]["senha"] == "senha123" and av, "sem cabeçalho: usa ordem padrão e avisa")

# 3) CSV exportado do Chrome (name,url,username,password,note)
with open("chrome.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh); w.writerow(["name", "url", "username", "password", "note"])
    w.writerow(["accounts.google.com", "https://accounts.google.com/", "joao@gmail.com", "g00gle!", ""])
    w.writerow(["amazon.com.br", "https://www.amazon.com.br/", "joao", "amz;com,virgula", "x"])
regs, _ = c.ler_planilha("chrome.csv")
ok(len(regs) == 2 and regs[1]["senha"] == "amz;com,virgula", "CSV do Chrome, senha com ; e , preservada")

# 4) CSV brasileiro com ; e acento em cp1252
with open("br.csv", "w", encoding="cp1252", newline="") as fh:
    fh.write("Serviço;Login;Senha;PIN\r\nCaixa;josé;çãõ#1;0007\r\n")
regs, _ = c.ler_planilha("br.csv")
ok(len(regs) == 1 and regs[0]["login"] == "josé" and regs[0]["pin"] == "0007", "CSV ; em cp1252 com acentos e PIN 0007")

# 5) PIN que perdeu zero
wb = openpyxl.Workbook(); ws = wb.active; ws.append(["Serviço", "Senha", "PIN"]); ws.append(["Cartão", "x", 123]); wb.save("c.xlsx")
regs, av = c.ler_planilha("c.xlsx")
ok(any("zeros" in a for a in av), "avisa PIN com menos de 4 dígitos (zero à esquerda perdido)")

# 6) classificação de duplicados
exist = [{"id": "1", "servico": "Banco do Brasil", "login": "joao.silva", "senha": "S3nh@Forte!", "pin": "1234", "notas": ""},
         {"id": "2", "servico": "gmail", "login": "JOAO@gmail.com", "senha": "antiga", "pin": "", "notas": ""}]
regs, _ = c.ler_planilha("a.xlsx")
ins, ig, conf = c.classificar_importacao(exist, regs)
ok(len(ins) == 1 and len(ig) == 1 and len(conf) == 1, f"novo/igual/conflito = {len(ins)}/{len(ig)}/{len(conf)}")

# 7) formatos recusados
for nome, conteudo, esperado in [("x.xls", b"\xd0\xcf\x11\xe0", ".xls antigo"), ("x.txt", b"a", "Use um arquivo")]:
    open(nome, "wb").write(conteudo)
    try: c.ler_planilha(nome); res = ""
    except ValueError as e: res = str(e)
    ok(esperado in res, f"recusa {nome}")
open("ruim.xlsx", "wb").write(os.urandom(300))
try: c.ler_planilha("ruim.xlsx"); res = ""
except ValueError as e: res = str(e)
ok(("Não foi possível ler" in res or "não tem o formato" in res), "xlsx corrompido -> mensagem clara")

# 8) modelo
c.criar_modelo_planilha("modelo.xlsx")
regs, av = c.ler_planilha("modelo.xlsx")
ok(len(regs) == 0 and any("EXEMPLO" in a for a in av), "modelo intocado: linhas EXEMPLO são ignoradas (nada entra por engano)")
import openpyxl as _ox
_wb = _ox.load_workbook("modelo.xlsx")
ok(_wb.sheetnames == ["Leia-me", "Senhas", "Listas"], "modelo tem Leia-me + aba Senhas + aba Listas")
_ws = _wb["Senhas"]
for _l in _ws.iter_rows(min_row=2, max_row=7):
    _l[0].value = _l[0].value.replace("EXEMPLO - ", "")
_wb.save("modelo2.xlsx")
regs, av = c.ler_planilha("modelo2.xlsx")
ok(len(regs) == 6 and regs[0]["pin"] == "0123", "modelo preenchido é lido (PIN 0123 como texto) e a aba de ajuda NÃO vira grupo")
ok({r["pessoa"] for r in regs} == {"Eu", "Eu - Trabalho", "Pai", "Mãe"} and {"Banco", "Compras", "Google", "Trabalho", "E-mail"} <= {r["grupo"] for r in regs},
   "modelo mostra 4 perfis e vários grupos")
ok(len(regs[0]["codigos"].splitlines()) == 3, "vários códigos de recuperação na mesma célula (um por linha)")
ok(any(a.startswith("🛡 OK") for a in av), "varredura sem achados mostra o selo OK")

# 8b) varredura de segurança antes de importar
import zipfile, shutil
def _recusa(nome, trecho):
    try: c.ler_planilha(nome); return False
    except ValueError as e: return "VARREDURA" in str(e) and trecho in str(e)
def _zip_com(origem, destino, extra):
    with zipfile.ZipFile(origem) as zi, zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zo:
        for i in zi.infolist(): zo.writestr(i, zi.read(i.filename))
        for n, d in extra.items(): zo.writestr(n, d)
_zip_com("modelo2.xlsx", "macro.xlsm", {"xl/vbaProject.bin": b"\xd0\xcf\x11\xe0 fake"})
ok(_recusa("macro.xlsm", "macros"), "planilha com macro é RECUSADA")
_zip_com("modelo2.xlsx", "ole.xlsx", {"xl/embeddings/oleObject1.bin": b"x"})
ok(_recusa("ole.xlsx", "objetos embutidos"), "objeto embutido é RECUSADO")
_zip_com("modelo2.xlsx", "ext.xlsx", {"xl/externalLinks/externalLink1.xml": b"<x/>"})
ok(_recusa("ext.xlsx", "vínculos"), "vínculo externo é RECUSADO")
_zip_com("modelo2.xlsx", "exe.xlsx", {"xl/dropper.exe": b"MZ"})
ok(_recusa("exe.xlsx", "programa escondido"), "programa escondido é RECUSADO")
_zip_com("modelo2.xlsx", "trav.xlsx", {"../../evil.txt": b"x"})
ok(_recusa("trav.xlsx", "caminho interno"), "caminho com .. é RECUSADO")
_zip_com("modelo2.xlsx", "xxe.xlsx", {"xl/extra.xml": b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x "y">]><a/>'})
ok(_recusa("xxe.xlsx", "DOCTYPE"), "XML com DOCTYPE/ENTITY é RECUSADO")
_wbf = _ox.Workbook(); _wf = _wbf.active
_wf.append(["Conta / App", "Login", "Senha"]); _wf.append(["Teste", "u", "=cmd|' /c calc'!A0"])
_wbf.save("dde.xlsx")
ok(_recusa("dde.xlsx", "executar programas"), "fórmula de execução (DDE/cmd) é RECUSADA")
with open("inj.csv", "w", encoding="utf-8") as _f:
    _f.write("Conta / App,Login,Senha,Notas\n")
    _f.write('Site,joao,"Abc#1234xyz","=HYPERLINK(""http://x"",""a"")"\n')
    _f.write("Outro,maria,=Senha#Forte9,ok\n")
regs, av = c.ler_planilha("inj.csv")
ok(regs[0]["notas"].startswith("'=") and regs[1]["senha"] == "=Senha#Forte9", "CSV: nota perigosa neutralizada; SENHA que começa com = não é alterada")
ok(any("fórmula perigosa" in a for a in av), "CSV: alerta de fórmula perigosa na prévia")


# 9) import -> cofre cifrado -> abre
P = "cofre_imp.dat"
if os.path.exists(P): os.remove(P)
v = c.Cofre.criar(P, "cavalo azul come pizza na chuva", 3, 0, "alto")
regs, _ = c.ler_planilha("a.xlsx")
for r in regs:
    r = {k: r[k] for k in ("servico", "login", "senha", "pin", "notas")}; r["id"] = "x"; v.registros.append(r)
v.salvar()
bruto = open(P, "rb").read()
ok(b"S3nh@Forte!" not in bruto and b"crc#2026" not in bruto, "senhas importadas ficam cifradas no cofre")
ok(len(c.Cofre.abrir(P, senha="cavalo azul come pizza na chuva").registros) == 3, "cofre reabre com as 3 contas")

# 10) apagar planilha com segurança
c.destruir("a.xlsx")
ok(not os.path.exists("a.xlsx") and not [x for x in os.listdir(".") if len(x) == 16], "planilha sobrescrita e apagada, sem sobras")
print("\nTODOS OK" if all(f) else "\nHOUVE FALHAS")
sys.exit(0 if all(f) else 1)
