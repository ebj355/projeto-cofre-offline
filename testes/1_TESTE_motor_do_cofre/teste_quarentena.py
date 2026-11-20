"""Importação em QUARENTENA: identidade real do arquivo (magic bytes), cópia isolada que é destruída, prazo máximo,
esquema rígido e modelo oficial. Nada disso pode tocar o cofre.dat."""
import os, sys, tempfile, glob, zipfile, time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
import cofre_senhas as c
f = []
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
W = tempfile.mkdtemp(prefix="cofre_q_")
c._TEMP_PRIVADO["pasta"] = os.path.join(W, ".tmp_cofre"); os.makedirs(c._TEMP_PRIVADO["pasta"])
def recusa(arq, trecho, nome, **kw):
    try:
        c.ler_planilha(arq, **kw); ok(False, nome + " (deveria recusar)")
    except ValueError as ex:
        ok(trecho.lower() in str(ex).lower(), f"{nome}: {str(ex)[:70]!r}")
def sobrou(): return glob.glob(os.path.join(c._TEMP_PRIVADO["pasta"], "quarentena_*"))

# 1) programa disfarçado de planilha
exe = os.path.join(W, "planilha.xlsx"); open(exe, "wb").write(b"MZ\x90\x00" + b"\0" * 400)
recusa(exe, "programa do Windows", ".exe renomeado para .xlsx")
pdf = os.path.join(W, "x.csv"); open(pdf, "wb").write(b"%PDF-1.4 ...")
recusa(pdf, "PDF", "PDF renomeado para .csv")
sh = os.path.join(W, "y.csv"); open(sh, "wb").write(b"#!/bin/sh\nrm -rf /\n")
recusa(sh, "script", "script renomeado para .csv")
# 2) não é ZIP
lixo = os.path.join(W, "lixo.xlsx"); open(lixo, "wb").write(b"isto nao e uma planilha de verdade, so texto")
recusa(lixo, "estrutura de dados inválida", ".xlsx que não é ZIP")
ole = os.path.join(W, "velho.xlsx"); open(ole, "wb").write(c._ASSINATURA_OLE + b"\0" * 100)
recusa(ole, "formato antigo", "formato OLE/protegido")
zcsv = os.path.join(W, "z.csv"); zipfile.ZipFile(zcsv, "w").writestr("a.txt", "x")
recusa(zcsv, "csv", ".csv que é um ZIP")
xls = os.path.join(W, "a.xls"); open(xls, "wb").write(b"\0")
recusa(xls, ".xlsx", ".xls antigo")
ok(not sobrou(), "nenhuma pasta de quarentena sobrou depois das recusas")

# 3) planilha boa: lida pela cópia, quarentena destruída
modelo = os.path.join(W, "modelo.xlsx"); c.criar_modelo_planilha(modelo)
import openpyxl
wb = openpyxl.load_workbook(modelo); ws = wb["Senhas"]
ws.append(["Banco X", "joao", "Senha-Forte-77!", "", "", "", "AAA-111\nBBB-222", "nota", "Bancos", "Eu"])
wb.save(modelo)
regs, avisos = c.ler_planilha(modelo)
ok(any(r["servico"] == "Banco X" and r["codigos"].count("\n") == 1 for r in regs), "planilha do modelo é lida (com 2 códigos)")
ok(not any("não segue o MODELO" in a for a in avisos), "modelo oficial não gera aviso de fora do modelo")
ok(not sobrou(), "quarentena destruída depois da leitura")
csvp = os.path.join(W, "outro.csv"); open(csvp, "w", encoding="utf-8").write("site,usuario,senha\nLoja,ana,Segredo-123!\n")
regs, avisos = c.ler_planilha(csvp)
ok(regs and any("não segue o MODELO" in a for a in avisos), "CSV fora do modelo é lido, com aviso")
# 4) esquema rígido
gordo = os.path.join(W, "gordo.csv"); open(gordo, "w", encoding="utf-8").write("Conta / App,Login,Senha\n" + "A" * 400 + ",x,y\n")
recusa(gordo, "máximo 300", "campo acima do limite derruba tudo")
ctl = os.path.join(W, "ctl.csv"); open(ctl, "w", encoding="utf-8").write("Conta / App,Login,Senha\nBanco\x07‮X,ana,Zzzzzzzzz-12!\n")
regs, _ = c.ler_planilha(ctl)
ok(regs and "\x07" not in regs[0]["servico"] and "‮" not in regs[0]["servico"], "caracteres de controle/bidi removidos")
# 5) prazo máximo
orig = c._ler_planilha_arquivo
c._ler_planilha_arquivo = lambda caminho, *a, **k: (time.sleep(3), ([], []))[1]
t0 = time.time()
recusa(csvp, "demorou demais", "leitura lenta é cancelada", tempo_limite=1)
ok(time.time() - t0 < 2.8, "prazo respeitado")
c._ler_planilha_arquivo = orig
# 6) cofre intocado
cof = os.path.join(W, "c.dat"); v = c.Cofre.criar(cof, "cavalo azul come pizza na chuva", 5, c.MODO_OU, "alto"); v.fechar()
h0 = open(cof, "rb").read()
for arq in (exe, lixo, gordo): 
    try: c.ler_planilha(arq)
    except ValueError: pass
ok(open(cof, "rb").read() == h0, "cofre.dat intocado por importações recusadas")
print("PASSOU" if all(f) else "FALHOU", sum(f), "/", len(f))
sys.exit(0 if all(f) else 1)
