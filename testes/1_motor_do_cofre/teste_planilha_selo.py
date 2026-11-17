"""Planilha modelo SELADA: o cofre confere, ao importar, que o modelo nasceu dele e que a estrutura não foi alterada.
Cobre: selo válido, linhas preenchidas depois (continua válido), estrutura adulterada (recusa), selo falso/forjado
(recusa), selo de outro cofre (aviso, sem recusa), modelo sem selo (comportamento antigo) e conteúdo malicioso em
planilha selada (continua recusado pela varredura)."""
import os, sys, tempfile, zipfile, shutil
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
import openpyxl
import cofre_senhas as c
f = []
def ok(cond, nome):
    """Registra uma verificação."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
W = tempfile.mkdtemp(prefix="selo_"); os.chdir(W)
c.Cofre.criar(os.path.join(W, "a.dat"), "cavalo azul come pizza na chuva", 5, c.MODO_OU, "alto").fechar()
c.Cofre.criar(os.path.join(W, "b.dat"), "outra senha bem diferente 12345", 5, c.MODO_OU, "alto").fechar()
def selo_de(nome):
    """(sal_k, nonce_k, wrap_k) do cofre `nome`, lidos do cabeçalho (sem senha)."""
    with open(nome, "rb") as fh: h = c._ler_cabecalho(fh.read(c.LIMITE_COFRE + 1))
    return h["sal_k"], h["nonce_k"], h["wrap_k"]
SA, SB = selo_de("a.dat"), selo_de("b.dat")

c.criar_modelo_planilha("m.xlsx", SA)
wb = openpyxl.load_workbook("m.xlsx")
ok(wb.sheetnames == ["Leia-me", "Senhas", "Listas", "_selo_cofre"], "modelo selado tem Leia-me, Senhas, Listas e a aba de selo")
ok(wb["_selo_cofre"].sheet_state == "veryHidden", "aba de selo é MUITO oculta (não aparece nem em 'Reexibir')")

# cabeçalho travado (pedido do usuário 2026-11-13): planilha protegida, só a linha 1 bloqueada, ordenar/filtrar/
# inserir/apagar linha liberados mesmo protegida (senão o Leia-me prometeria algo que a planilha recusa a fazer)
pw = wb["Senhas"]
ok(pw.protection.sheet is True, "aba 'Senhas' protegida")
ok(pw["A1"].protection.locked and pw["J1"].protection.locked, "cabeçalho (linha 1) travado, de A a J")
ok(not pw["A2"].protection.locked and not pw["J50"].protection.locked, "linhas de dados destravadas (A2 e J50)")
ok(pw.protection.sort is False and pw.protection.autoFilter is False, "ordenar/filtrar liberados mesmo com a planilha protegida")
ok(pw.protection.insertRows is False and pw.protection.deleteRows is False, "inserir/apagar linha liberados (Leia-me promete poder apagar as linhas EXEMPLO)")
ok(wb["Listas"].protection.sheet is False, "aba 'Listas' continua livre (sem proteção), para acrescentar grupo/perfil")

def importa(nome, selo=SA):
    """Importa e devolve (registros, avisos, erro)."""
    try: r, a = c.ler_planilha(nome, selo=selo); return r, a, ""
    except ValueError as e: return None, None, str(e)

r, a, e = importa("m.xlsx")
ok(r == [] and any("Selo de autenticidade confere" in x for x in a), "modelo intacto: selo CONFERE (e linhas EXEMPLO ignoradas)")

# preencher dados (o que o usuário faz) não invalida o selo, nem salvar de novo
wb = openpyxl.load_workbook("m.xlsx"); ws = wb["Senhas"]
ws["A8"], ws["B8"], ws["C8"], ws["I8"], ws["J8"] = "Meu Banco", "joao", "S3nha!Forte#2026", "Banco", "Eu"
ws["A9"], ws["C9"], ws["I9"], ws["J9"] = "Google", "OutraS3nha#9", "Google", "Eu - Trabalho"
wb.save("preenchida.xlsx")
r, a, e = importa("preenchida.xlsx")
ok(r and len(r) == 2 and {x["pessoa"] for x in r} == {"Eu", "Eu - Trabalho"} and any("confere" in x for x in a), "preencher linhas e salvar de novo: selo continua válido")

# adulteração da estrutura: renomear coluna / aba / apagar coluna
wb = openpyxl.load_workbook("m.xlsx"); wb["Senhas"]["C1"] = "Senha (editada)"; wb.save("adult1.xlsx")
r, a, e = importa("adult1.xlsx"); ok(r is None and "SELO DE AUTENTICIDADE" in e and "alterada" in e, "título de coluna alterado: importação RECUSADA")
wb = openpyxl.load_workbook("m.xlsx"); wb["Listas"].title = "Outra"; wb.save("adult2.xlsx")
r, a, e = importa("adult2.xlsx"); ok(r is None and "SELO" in e, "aba renomeada: importação RECUSADA")
wb = openpyxl.load_workbook("m.xlsx"); wb.create_sheet("Extra"); wb.save("adult3.xlsx")
r, a, e = importa("adult3.xlsx"); ok(r is None and "SELO" in e, "aba nova escondida/extra: importação RECUSADA")

# selo forjado: copiar o selo de um modelo para outra estrutura, ou mexer no mac / id
wb = openpyxl.load_workbook("m.xlsx"); wb["_selo_cofre"]["B7"] = "0" * 64; wb.save("forjado1.xlsx")
r, a, e = importa("forjado1.xlsx"); ok(r is None and "SELO" in e, "MAC trocado: RECUSADA")
wb = openpyxl.load_workbook("m.xlsx"); wb["_selo_cofre"]["B5"] = "ffffffffffffffff"; wb.save("forjado2.xlsx")
r, a, e = importa("forjado2.xlsx"); ok(r is None and "SELO" in e, "id do arquivo trocado: RECUSADA")
wb = openpyxl.load_workbook("m.xlsx"); del wb["_selo_cofre"]["A7"].parent._cells[(7, 1)]; wb.save("forjado3.xlsx")
r, a, e = importa("forjado3.xlsx"); ok(r is None and "SELO" in e, "selo incompleto: RECUSADA")
wb = openpyxl.load_workbook("m.xlsx"); wb["_selo_cofre"]["A1"] = "outra-coisa"; wb.save("forjado4.xlsx")
r, a, e = importa("forjado4.xlsx"); ok(r is None and "SELO" in e, "marca do selo trocada: RECUSADA")

# selo de OUTRO cofre: importa com aviso (não dá para provar a origem), sem recusar
r, a, e = importa("preenchida.xlsx", selo=SB)
ok(r and len(r) == 2 and any("OUTRO cofre" in x for x in a) and not any("confere" in x for x in a), "selo de outro cofre: aviso claro, sem recusar")
# sem dados do cofre (selo=None): comporta-se como planilha comum
r, a, e = importa("preenchida.xlsx", selo=None); ok(r and len(r) == 2, "sem selo do cofre para conferir: importa como planilha comum")

# modelo SEM selo (antigo) e planilha comum: mesmo comportamento de antes
c.criar_modelo_planilha("sem.xlsx")
wb = openpyxl.load_workbook("sem.xlsx"); ok(wb.sheetnames == ["Leia-me", "Senhas", "Listas"], "modelo sem selo não cria a aba de selo")
wb["Senhas"]["A8"], wb["Senhas"]["C8"] = "X", "y"; wb.save("sem2.xlsx")
r, a, e = importa("sem2.xlsx"); ok(r and len(r) == 1 and not any("confere" in x for x in a), "sem selo: importa (sem dizer que foi verificado)")

# selo bom NÃO libera conteúdo malicioso: a varredura continua valendo
with zipfile.ZipFile("preenchida.xlsx") as zi, zipfile.ZipFile("mal.xlsm", "w", zipfile.ZIP_DEFLATED) as zo:
    for i in zi.infolist(): zo.writestr(i, zi.read(i.filename))
    zo.writestr("xl/vbaProject.bin", b"\xd0\xcf\x11\xe0 fake")
r, a, e = importa("mal.xlsm"); ok(r is None and "macros" in e, "planilha SELADA com macro continua RECUSADA pela varredura")
wb = openpyxl.load_workbook("m.xlsx"); wb["Senhas"]["A8"] = "=cmd|' /C calc'!A0"; wb.save("formula.xlsx")
r, a, e = importa("formula.xlsx"); ok((r is None and "fórmula" in e.lower()) or (r is not None and not any("=cmd" in x.get("servico", "") for x in r)), "fórmula de execução em planilha selada: recusada/neutralizada")

# o selo não vaza nada secreto e é diferente a cada modelo
c.criar_modelo_planilha("m2.xlsx", SA)
s1 = {r[0].value: r[1].value for r in openpyxl.load_workbook("m.xlsx")["_selo_cofre"].iter_rows()}
s2 = {r[0].value: r[1].value for r in openpyxl.load_workbook("m2.xlsx")["_selo_cofre"].iter_rows()}
ok(s1["id_arquivo"] != s2["id_arquivo"] and s1["mac"] != s2["mac"] and s1["id_cofre"] == s2["id_cofre"], "cada modelo tem código e MAC próprios")
ok(s1["id_cofre"] != c._chave_mac_planilha(SB)[0], "cofres diferentes têm ids diferentes")

# ---- IMPORTAÇÃO ESTRITA: só o que o próprio cofre gerou e conferiu ----
def estrito(nome, selo=SA):
    """Importa exigindo o selo; devolve (registros, avisos, erro)."""
    try: r, a = c.ler_planilha(nome, selo=selo, exigir_selo=True); return r, a, ""
    except ValueError as e: return None, None, str(e)
r, a, e = estrito("preenchida.xlsx")
ok(r and len(r) == 2 and sum("🛡 OK" in x for x in a) >= 2, "ESTRITO: modelo do cofre preenchido é aceito e mostra as verificações que passaram")
r, a, e = estrito("m.xlsx"); ok(r == [], "ESTRITO: modelo intacto (só exemplos) é aceito e não importa nada")
r, a, e = estrito("sem2.xlsx"); ok(r is None and "IMPORTAÇÃO SEGURA" in e and "NÃO foi gerada" in e, "ESTRITO: planilha comum sem selo é RECUSADA")
r, a, e = estrito("preenchida.xlsx", selo=SB); ok(r is None and "IMPORTAÇÃO SEGURA" in e, "ESTRITO: selo de OUTRO cofre é RECUSADO")
r, a, e = estrito("preenchida.xlsx", selo=None); ok(r is None and "IMPORTAÇÃO SEGURA" in e, "ESTRITO: sem como conferir o selo é RECUSADO")
for n in ("adult1.xlsx", "adult2.xlsx", "adult3.xlsx", "forjado1.xlsx", "forjado2.xlsx", "forjado3.xlsx", "forjado4.xlsx"):
    r, a, e = estrito(n); ok(r is None and e, f"ESTRITO: {n} recusada")
open("x.csv", "w", encoding="utf-8").write("Conta,Login,Senha\nA,b,c\n")
r, a, e = estrito("x.csv"); ok(r is None and "IMPORTAÇÃO SEGURA" in e and "CSV" in e, "ESTRITO: CSV é RECUSADO sem ser lido")
with zipfile.ZipFile("preenchida.xlsx") as zi, zipfile.ZipFile("img.xlsx", "w", zipfile.ZIP_DEFLATED) as zo:
    for i in zi.infolist(): zo.writestr(i, zi.read(i.filename))
    zo.writestr("xl/media/a.png", b"\x89PNG\r\n\x1a\n0000")
r, a, e = estrito("img.xlsx"); ok(r is None and "parte estranha" in e, "ESTRITO: parte binária extra dentro do .xlsx é RECUSADA")
r, a, e = estrito("mal.xlsm"); ok(r is None, "ESTRITO: macro continua RECUSADA")
r, a, e = importa("img.xlsx"); ok(r is not None, "modo comum (não estrito) continua aceitando imagem inofensiva")
ok(c.IMPORTAR_SOMENTE_COM_SELO is True, "a importação do cofre está configurada como ESTRITA por padrão")

# ---- BIOMETRIA REMOVIDA: nada de digital / Windows Hello no programa ----
for nome_removido in ("MARCA_BIO", "tipo_das_credenciais", "tipo_fido_cofre", "_dicas_fido", "_biometria_disponivel"):
    ok(not hasattr(c, nome_removido), f"removido do programa: {nome_removido}")
import inspect
for fn in (c._fido_registrar, c.fido_registrar, c.fido_cadastrar_e_testar):
    ok("biometria" not in inspect.signature(fn).parameters, f"{fn.__name__} não tem mais o parâmetro 'biometria'")
ok("tipo" not in inspect.signature(c.fido_obter).parameters, "fido_obter não escolhe mais 'tipo' de autenticador")
fonte_c = inspect.getsource(c)
ok("Windows Hello" not in fonte_c and "biometri" not in fonte_c.lower() and '"platform"' not in fonte_c,
   "o código-fonte não cita biometria, Windows Hello nem autenticador de plataforma")
print("FALHAS:", f.count(False)); sys.exit(1 if False in f else 0)
