# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""TRAVA ENTRE INSTÂNCIAS (.lock) e CONTADOR ANTI-REVERSÃO.
1) Dois processos: o segundo recebe 'em uso' (False); a trava some sozinha quando o dono sai ou leva kill -9.
2) Sem poder criar o .lock (pendrive protegido): não trava o programa (None -> segue).
3) Reversão: arquivo principal trocado por versão velha com cópias mais novas ao lado -> alerta; abrir de novo -> some;
   uso normal nunca alerta; restaurar cópia de propósito alerta uma vez só; o contador só cresce.
4) O alerta também aparece em modo consulta e nada é gravado."""
import os, sys, time, shutil, signal, subprocess, tempfile, importlib.util
AQUI = os.path.dirname(os.path.abspath(__file__))
CAMINHO_PROG = os.path.join(AQUI, "..", "..", "cofre_senhas.py")
spec = importlib.util.spec_from_file_location("c", CAMINHO_PROG)
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
FAL = []


def ok(cond, msg):
    print(("  [OK]   " if cond else "  [FALHOU] ") + msg, flush=True)
    if not cond:
        FAL.append(msg)


FILHO = r'''
import sys, time, importlib.util
spec = importlib.util.spec_from_file_location("c", sys.argv[1])
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
r = c.instancia_unica(sys.argv[2])
print("DONO" if r else "EM_USO", flush=True)
if len(sys.argv) > 3:
    time.sleep(float(sys.argv[3]))
'''
d = tempfile.mkdtemp(); P = os.path.join(d, "cofre.dat")
S = "cavalo azul come pizza na chuva 2026"
v = c.Cofre.criar(P, S, 3, 0, "alto"); v.salvar()


def filho(*extra, esperar=True):
    p = subprocess.Popen([sys.executable, "-c", FILHO, CAMINHO_PROG, P, *extra], stdout=subprocess.PIPE, text=True)
    if esperar:
        out = p.communicate(timeout=60)[0].strip()
        return out
    return p


print("== 1) trava entre processos")
dono = filho("30", esperar=False)
ok(dono.stdout.readline().strip() == "DONO", "o primeiro processo vira o dono")
ok(os.path.exists(P + ".lock"), "o arquivo .lock existe ao lado do cofre")
ok(filho() == "EM_USO", "o segundo processo recebe EM_USO (vai abrir em modo consulta)")
ok(filho() == "EM_USO", "o terceiro também")
dono.kill(); dono.wait()                  # kill() mata sem aviso no Linux (SIGKILL) e no Windows (TerminateProcess)
ok(filho() == "DONO", "depois de kill -9 do dono a trava some sozinha (não existe trava 'velha')")
d2 = filho("0.2", esperar=False); d2.stdout.readline(); d2.wait()
ok(filho() == "DONO", "depois de uma saída normal também")
ok(os.path.getsize(P + ".lock") == 0, "o .lock é um arquivo vazio (nada sensível)")
ok(c._trava_de_arquivo(P) is True and c._trava_de_arquivo(P) is True, "no mesmo processo, pedir de novo continua True")
os.close(c._TRAVA_ARQ["fd"]); c._TRAVA_ARQ["fd"] = None

print("== 2) sem poder criar o .lock (pendrive protegido)")
real = os.open
def nega(*a, **k):
    if str(a[0]).endswith(".lock"):
        raise PermissionError(13, "negado")
    return real(*a, **k)
os.open = nega
try:
    ok(c._trava_de_arquivo(P) is None, "devolve None (sem proteção, mas o programa segue)")
    ok(c.instancia_unica(P) is True, "instancia_unica não bloqueia o programa nesse caso")
finally:
    os.open = real

print("== 3) contador anti-reversão")
d = tempfile.mkdtemp(); P = os.path.join(d, "cofre.dat")
v = c.Cofre.criar(P, S, 3, 0, "alto")
v.registros.append({"id": "a", "servico": "A", "login": "u", "senha": "s1", "notas": ""}); v.salvar(forcar_copia=True)
seqs = []
for i in range(4):
    a = c.Cofre.abrir(P, senha=S)
    seqs.append(a._seq)
    ok(not a.alerta_reversao, f"abertura normal #{i + 1} não alerta")
    a.registros.append({"id": f"n{i}", "servico": f"S{i}", "login": "u", "senha": f"x{i}", "notas": ""})
    a.salvar(forcar_copia=True)
    seqs.append(a._seq)
ok(all(y > x for x, y in zip(seqs, seqs[1:])), f"o contador só cresce: {seqs}")
novo = open(P, "rb").read()
velho = open(P + ".bak4", "rb").read()
print("  (trocando o arquivo principal por uma versão velha)")
open(P, "wb").write(velho)
a = c.Cofre.abrir(P, senha=S)
ok(a.alerta_reversao, "principal velho com cópias mais novas ao lado: ALERTA")
ok(len(a.registros) < 5, "(o conteúdo realmente voltou no tempo)")
a.fechar()
a = c.Cofre.abrir(P, senha=S)
ok(not a.alerta_reversao, "na abertura seguinte o alerta já sumiu (o contador passou de todas as cópias)")
ok(a._seq > max(seqs), "o contador passou de todos os anteriores")
a.fechar()

print("== 4) restaurar uma cópia de propósito")
d = tempfile.mkdtemp(); P = os.path.join(d, "cofre.dat")
v = c.Cofre.criar(P, S, 3, 0, "alto"); v.salvar(forcar_copia=True)
for i in range(3):
    a = c.Cofre.abrir(P, senha=S); a.registros.append({"id": f"r{i}", "servico": "S", "login": "u", "senha": "x", "notas": ""})
    a.salvar(forcar_copia=True); a.fechar()
open(P, "wb").write(b"lixo" * 50)
ok(c.restaurar_copia(P) is not None, "restaurar_copia funcionou")
a = c.Cofre.abrir(P, senha=S)
ok(not a.alerta_reversao, "restaurar a cópia MAIS NOVA (o caso normal de arquivo danificado) não gera alerta falso")
a.fechar()
shutil.copy(P + ".bak3" if os.path.exists(P + ".bak3") else P + ".bak2", P)
a = c.Cofre.abrir(P, senha=S)
ok(a.alerta_reversao, "voltar de propósito para uma cópia mais velha (com outras mais novas ao lado) avisa UMA vez")
a.fechar()
a = c.Cofre.abrir(P, senha=S)
ok(not a.alerta_reversao, "e o aviso some na abertura seguinte")
a.fechar()

print("== 5) modo consulta com cofre revertido: avisa e não grava")
a = c.Cofre.abrir(P, senha=S); a.salvar(forcar_copia=True); a.salvar(forcar_copia=True); a.fechar()
shutil.copy(P + ".bak3" if os.path.exists(P + ".bak3") else P + ".bak2", P)
antes = {n: open(os.path.join(d, n), "rb").read() for n in sorted(os.listdir(d))}
a = c.Cofre.abrir(P, senha=S, consulta=True)
ok(a.somente_leitura and a.alerta_reversao, "abriu em modo consulta e o alerta de reversão aparece")
depois = {n: open(os.path.join(d, n), "rb").read() for n in sorted(os.listdir(d))}
ok(antes == depois, "nenhum arquivo da pasta foi alterado")
a.motivo_consulta = "em_uso"
try:
    a.salvar()
    ok(False, "salvar deveria recusar")
except c.ErroGravacao as ex:
    ok("outra janela" in str(ex) or "Feche" in str(ex), "salvar é recusado com a mensagem de 'cofre em uso'")

print("\nFALHAS:", len(FAL))
for f in FAL:
    print("  -", f)
sys.exit(1 if FAL else 0)
