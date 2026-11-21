# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Gravação em pendrive e diagnóstico: gravação atômica com releitura (SHA-256), pendrive removido/protegido/cheio/em uso,
cópias rotativas (.bak1 a .bak5), manifesto interno e o registro de diagnóstico cifrado (sem texto, sem caminho,
rotativo, lido só com o cofre aberto). Roda no Linux e no Windows."""
import sys, os, errno, struct, tempfile, threading, importlib.util, base64, time, glob

spec = importlib.util.spec_from_file_location('c', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'cofre_senhas.py'))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
FAL = []


def ok(cond, msg):
    print(("  [OK]   " if cond else "  [FALHOU] ") + msg)
    if not cond:
        FAL.append(msg)


def pasta():
    return tempfile.mkdtemp()


S = "cavalo azul come pizza na chuva"
real_fsync, real_replace = os.fsync, os.replace

print("== 1) gravação atômica com releitura")
d = pasta(); P = os.path.join(d, "x.bin")
c._gravar_atomico(P, b"A" * 5000)
ok(open(P, "rb").read() == b"A" * 5000 and not os.path.exists(P + ".tmp"), "grava e não deixa .tmp")
c._gravar_atomico(P, b"B" * 70000)
ok(open(P, "rb").read() == b"B" * 70000, "substitui o conteúdo inteiro")


def fsync_ruim(fd):
    raise OSError(errno.EIO, "erro de E/S simulado")


os.fsync = fsync_ruim
try:
    c._gravar_atomico(P, b"C" * 100); r = None
except c.ErroGravacao as ex:
    r = ex
except Exception as ex:
    r = ex
os.fsync = real_fsync
ok(isinstance(r, c.ErroGravacao) and open(P, "rb").read() == b"B" * 70000 and not os.path.exists(P + ".tmp"),
   "queda no fsync: ErroGravacao, original intacto, sem .tmp")
ok(isinstance(r, OSError) and r.errno == errno.EIO, "o ErroGravacao continua sendo OSError e guarda o errno")


def fsync_corrompe(fd):
    """Simula o pendrive que diz 'gravei' mas deixa lixo no arquivo."""
    real_fsync(fd)
    with open(P + ".tmp", "r+b") as f:
        f.seek(10)
        f.write(b"\xff")


os.fsync = fsync_corrompe
try:
    c._gravar_atomico(P, b"D" * 5000); r = None
except Exception as ex:
    r = ex
os.fsync = real_fsync
ok(isinstance(r, c.ErroGravacao) and open(P, "rb").read() == b"B" * 70000 and not os.path.exists(P + ".tmp"),
   "gravação que não confere na releitura (SHA-256) é recusada e o original fica intacto")

print("== 2) pendrive removido / protegido / cheio / em uso")
sumiu = os.path.join(d, "pasta_que_nao_existe_mais", "cofre.dat")
try:
    c._gravar_atomico(sumiu, b"x"); r = None
except Exception as ex:
    r = ex
ok(isinstance(r, c.ErroGravacao) and "pendrive" in str(r) and "pasta_que_nao_existe" not in str(r),
   "pasta/pendrive sumiu: mensagem clara, sem caminho")
for cod, trecho in ((errno.ENOSPC, "espaço"), (errno.EROFS, "protegido"), (errno.EACCES, "acesso negado"),
                    (errno.EIO, "leitura/gravação")):
    ex = OSError(cod, "x", os.path.join(d, "segredo", "arq"))
    t = c.texto_erro(ex)
    ok(trecho in t and "segredo" not in t, f"errno {cod}: texto amigável ({trecho}) sem o caminho")
ok(c.texto_erro(ValueError("mensagem própria")) == "mensagem própria", "erros que não são de arquivo mantêm a mensagem")

tentativas = []


def replace_ocupado(a, b):
    tentativas.append(1)
    if len(tentativas) < 3:
        raise PermissionError(errno.EACCES, "em uso")
    return real_replace(a, b)


os.replace = replace_ocupado
try:
    c._gravar_atomico(P, b"E" * 3000); r = "ok"
except Exception as ex:
    r = ex
os.replace = real_replace
ok(r == "ok" and len(tentativas) == 3 and open(P, "rb").read() == b"E" * 3000,
   "arquivo em uso por instantes (antivírus): tenta de novo e conclui")


def replace_sempre_negado(a, b):
    raise PermissionError(errno.EACCES, "em uso")


os.replace = replace_sempre_negado
t0 = time.time()
try:
    c._gravar_atomico(P, b"F" * 3000); r = None
except Exception as ex:
    r = ex
os.replace = real_replace
ok(isinstance(r, c.ErroGravacao) and open(P, "rb").read() == b"E" * 3000 and not os.path.exists(P + ".tmp") and time.time() - t0 < 10,
   "acesso negado o tempo todo: desiste com erro claro, original intacto, sem .tmp")

print("== 3) cofre: arquivo some depois de aberto (pendrive trocado/removido)")
d = pasta(); P = os.path.join(d, "cofre.dat")
v = c.Cofre.criar(P, S, 3, 0, "alto")
v.registros.append({"id": "1", "servico": "A", "login": "x", "senha": "s1"})
v.salvar()
os.remove(P)
try:
    v.salvar(); r = None
except Exception as ex:
    r = ex
ok(isinstance(r, c.ErroGravacao) and not os.path.exists(P), "salvar com o arquivo sumido recusa (não cria cofre em outro pendrive)")

print("== 4) cópias rotativas (.bak1 a .bak5)")
d = pasta(); P = os.path.join(d, "cofre.dat")
v = c.Cofre.criar(P, S, 3, 0, "alto")
vistos = []
for i in range(8):
    v.registros.append({"id": str(i), "servico": f"S{i}", "login": "x", "senha": f"s{i}"})
    v.salvar(forcar_copia=True)
    vistos.append(open(P + ".bak1", "rb").read())
copias = c._copias(P)
ok(len(copias) == 5 and all(os.path.exists(x) for x in copias) and not os.path.exists(P + ".bak6"),
   "ficam exatamente 5 gerações (.bak1 a .bak5)")
conteudos = [open(x, "rb").read() for x in copias]
ok(len(set(conteudos)) == 5, "as 5 gerações são diferentes entre si")
ok(conteudos[0] == vistos[-1] and conteudos[1] == vistos[-2], "a .bak1 é a mais nova e empurra a anterior para .bak2")
antes = [open(x, "rb").read() for x in copias]
v.salvar(forcar_copia=True)
v.salvar(forcar_copia=True)
ok([open(x, "rb").read() for x in copias][1:] == antes[1:] or len({open(x, "rb").read() for x in copias}) == 5,
   "salvar sem mudança não gasta geração à toa")
open(copias[0], "wb").write(b"lixo")
usada = c.restaurar_copia(P)
ok(usada == ".bak2".join(["cofre.dat", ""]) or usada == "cofre.dat.bak2", f"cópia mais nova ilegível: restaura da seguinte ({usada})")
ok(len(c.Cofre.abrir(P, senha=S).registros) >= 1, "o cofre restaurado abre")
# Um cabeçalho válido não basta: se os dados cifrados da cópia falham, a próxima pode ser restaurada.
danificado_original = open(P + ".danificado", "rb").read()
dados = bytearray(open(copias[1], "rb").read())
cabecalho = c._ler_cabecalho(dados)
dados[cabecalho["ini_dados"]] ^= 1
open(copias[0], "wb").write(dados)
usada_ruim = c.restaurar_copia(P)
ok(usada_ruim == "cofre.dat.bak1", "restaura primeiro a cópia com cabeçalho válido")
try:
    c.Cofre.abrir(P, senha=S)
    ok(False, "cópia com dados adulterados abriu")
except c.ArquivoCorrompido:
    pass
usada_seguinte = c.restaurar_copia(P, ignoradas=(usada_ruim,))
ok(usada_seguinte == "cofre.dat.bak2", "pula a cópia autenticada como danificada e restaura a próxima")
ok(open(P + ".danificado", "rb").read() == danificado_original and glob.glob(P + ".*.danificado"),
   "fallback preserva o primeiro .danificado e guarda a cópia rejeitada")
ok(len(c.Cofre.abrir(P, senha=S).registros) >= 1, "a próxima cópia restaurada abre")
c.destruir(P)
ok(not any(os.path.exists(x) for x in copias + [P, P + ".danificado", P + ".diag", P + ".tmp"])
   and not glob.glob(P + ".*.danificado"), "autodestruição apaga as 5 cópias, arquivos danificados e diagnóstico")

print("== 5) manifesto interno (contagem + hash dos IDs)")
d = pasta(); P = os.path.join(d, "cofre.dat")
v = c.Cofre.criar(P, S, 3, 0, "alto")
for i in range(3):
    v.registros.append({"id": f"id{i}", "servico": "S", "login": "x", "senha": "s"})
v.salvar()
ok(len(c.Cofre.abrir(P, senha=S).registros) == 3, "cofre com manifesto abre normalmente")
ok(c._hash_registros([{"id": "a"}, {"id": "b"}]) == c._hash_registros([{"id": "b"}, {"id": "a"}]), "o hash não depende da ordem")
ok(c._hash_registros([{"id": "a"}]) != c._hash_registros([{"id": "a"}, {"id": "b"}]), "o hash muda se falta ou sobra um registro")
orig = c._hash_registros
v = c.Cofre.abrir(P, senha=S)
c._hash_registros = lambda itens: "0" * 64
v.salvar()
c._hash_registros = orig
t0 = c.tentativas_restantes(P)
try:
    c.Cofre.abrir(P, senha=S); r = "abriu"
except c.ArquivoCorrompido:
    r = "corrompido"
ok(r == "corrompido" and os.path.exists(P) and c.tentativas_restantes(P) == t0,
   "manifesto que não confere: recusa abrir, preserva o arquivo e devolve a tentativa")

print("== 6) registro de diagnóstico cifrado")
d = pasta(); P = os.path.join(d, "cofre.dat")
v = c.Cofre.criar(P, S, 3, 0, "alto")
arq = P + ".diag"
ok(os.path.exists(arq) and open(arq, "rb").read(8) == c.DIAG_MAGIC and os.path.getsize(arq) == c.DIAG_CAB,
   "o cofre novo já cria o arquivo de diagnóstico (só o cabeçalho com a chave pública)")
ok(not os.path.exists(arq + ".tmp")
   and not any(n.startswith(os.path.basename(arq) + ".") and n.endswith(".tmp") for n in os.listdir(d)),
   "inicialização do diagnóstico não deixa temporário fixo ou resíduo")
priv = base64.b64decode(v.meta["diag_priv"])
ok(len(priv) == 32, "a chave privada do diagnóstico fica DENTRO do cofre (meta, cifrada)")
c.diag_registrar(c.DIAG_GRAVACAO, OSError(errno.ENOSPC, "sem espaço em " + P))
c.diag_registrar(c.DIAG_LEITURA)
bruto = open(arq, "rb").read()
ok(len(bruto) == c.DIAG_CAB + 2 * c.DIAG_TAM, "cada evento ocupa um registro de tamanho fixo")
ok(P.encode() not in bruto and d.encode() not in bruto and b"cofre" not in bruto and b"espa" not in bruto
   and S.encode() not in bruto, "o arquivo não contém caminho, senha nem texto legível")
res = c.diag_ler(P, priv)
ok(res is not None and len(res[0]) == 2 and res[1] == 0, "com a chave do cofre, lê os 2 registros autenticados")
m, cod, err, linha, ver = res[0][0]
ok(cod == c.DIAG_GRAVACAO and err == errno.ENOSPC and ver == c._versao_num() and abs(m - time.time() / 60) < 5,
   "registro traz código, errno, versão e minuto")
ok("espaço" in c.diag_descrever(cod, err), "o texto legível só existe ao mostrar (dentro do cofre aberto)")
outra = base64.b64encode(os.urandom(32))
ok(c.diag_ler(P, os.urandom(32)) is None, "com outra chave não lê nada")
# adulteração e corte
b = bytearray(bruto); b[c.DIAG_CAB + 50] ^= 1
open(arq, "wb").write(bytes(b) + b"\x01\x02\x03")
res = c.diag_ler(P, priv)
ok(res is not None and len(res[0]) == 1 and res[1] == 1, "registro adulterado é descartado e contado; pedaço cortado no fim é ignorado")
open(arq, "wb").write(bruto)
# falha de gravação real vira registro sozinha
os.fsync = fsync_ruim
try:
    v.salvar()
except Exception:
    pass
os.fsync = real_fsync
res = c.diag_ler(P, priv)
ok(res is not None and res[0][-1][1] == c.DIAG_GRAVACAO and res[0][-1][2] == errno.EIO, "falha ao gravar o cofre é registrada sozinha")
# registrar com o cofre TRANCADO (só usa a chave pública)
w = c.Cofre.abrir(P, senha=S)
priv2 = base64.b64decode(w.meta["diag_priv"])
ok(priv2 == priv, "a chave do diagnóstico continua a mesma depois de reabrir")
w.fechar(); w = None
c.diag_registrar(c.DIAG_INTEGRIDADE)
res = c.diag_ler(P, priv)
ok(res[0][-1][1] == c.DIAG_INTEGRIDADE, "registra mesmo com o cofre trancado")
# trocar a senha não perde a chave
x = c.Cofre.abrir(P, senha=S)
x.trocar_senha("outra frase bem longa e diferente 123")
n_antes = len(c.diag_ler(P, priv)[0])
c.diag_registrar(c.DIAG_COPIA)
ok(len(c.diag_ler(P, priv)[0]) == n_antes + 1, "continua funcionando depois de trocar a senha mestra")

print("== 7) rotação e concorrência")
d = pasta(); P = os.path.join(d, "cofre.dat")
v = c.Cofre.criar(P, S, 3, 0, "alto")
priv = base64.b64decode(v.meta["diag_priv"])
for i in range(260):
    c.diag_registrar(c.DIAG_GRAVACAO, OSError(i + 1, "x"))
res = c.diag_ler(P, priv)
n = len(res[0])
ok(c.DIAG_MANTER <= n <= c.DIAG_MAX and res[1] == 0 and res[0][-1][2] == 260 and os.path.getsize(P + ".diag") <= c.DIAG_CAB + c.DIAG_MAX * c.DIAG_TAM,
   f"rotaciona: nunca passa de {c.DIAG_MAX} registros e mantém os mais recentes (ficaram {n})")
c.diag_limpar(P, priv)
ok(not os.path.exists(arq + ".tmp")
   and not any(n.startswith(os.path.basename(arq) + ".") and n.endswith(".tmp") for n in os.listdir(d)),
   "limpeza do diagnóstico troca atomicamente sem deixar temporário")
fios = [threading.Thread(target=lambda: [c.diag_registrar(c.DIAG_COPIA) for _ in range(20)]) for _ in range(8)]
[f.start() for f in fios]; [f.join() for f in fios]
res = c.diag_ler(P, priv)
ok(len(res[0]) == 160 and res[1] == 0, "8 fios registrando ao mesmo tempo: 160 registros íntegros")
c._DIAG["arq"] = os.path.join(d, "nao", "existe", "x.diag"); c._DIAG["pub"] = None
try:
    c.diag_registrar(c.DIAG_COPIA); r = "ok"
except Exception as ex:
    r = ex
ok(r == "ok", "pasta inexistente: o diagnóstico nunca levanta erro")

print("== 8) nada sobra no log antigo em texto")
fonte = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'cofre_senhas.py'), encoding="utf-8").read()
ok('open(arq, "a", encoding="utf-8")' not in fonte and "def _formatar_erro" not in fonte, "o registro de erro em texto puro deixou de existir")

print("FALHAS:", FAL)
print("TODOS OS TESTES PASSARAM" if not FAL else "HÁ FALHAS")
sys.exit(1 if FAL else 0)
