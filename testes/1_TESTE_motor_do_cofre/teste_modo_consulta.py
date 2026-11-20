"""MODO CONSULTA: pendrive protegido contra gravação. Simula a proteção bloqueando TODA escrita (open para gravar, replace,
rename, remove) dentro da pasta do cofre. Confere: a abertura normal falha com mensagem clara SEM gastar tentativa; o modo
consulta abre e mostra os itens SEM gravar nada (arquivo idêntico, byte a byte); qualquer salvamento é recusado e desfeito
na memória; senha errada nunca destrói nem conta nada nesse modo; cofre antigo (v1) pede para destravar o pendrive."""
import os, sys, errno, builtins, tempfile, importlib.util
spec = importlib.util.spec_from_file_location("c", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "cofre_senhas.py"))
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
FAL = []


def ok(cond, msg):
    print(("  [OK]   " if cond else "  [FALHOU] ") + msg, flush=True)
    if not cond:
        FAL.append(msg)


S = "cavalo azul come pizza na chuva 2026"
d = tempfile.mkdtemp(); P = os.path.join(d, "cofre.dat")
v = c.Cofre.criar(P, S, 3, 0, "alto")
for i in range(3):
    v.registros.append({"id": f"i{i}", "servico": f"Serv{i}", "login": f"u{i}", "senha": f"senha-{i}", "notas": ""})
v.salvar()
original = open(P, "rb").read()
antes_dir = sorted(os.listdir(d))
print("== 0) classificação dos erros de E/S")
ok(c._e_protecao_de_escrita(OSError(errno.EROFS, "ro")), "EROFS (sistema de arquivos somente leitura) = proteção")
ok(c._e_protecao_de_escrita(OSError(errno.EACCES, "negado")), "EACCES (acesso negado) = proteção")
e = OSError(); e.winerror = 19
ok(c._e_protecao_de_escrita(e), "winerror 19 (ERROR_WRITE_PROTECT) = proteção")
ok(not c._e_protecao_de_escrita(OSError(errno.ENOSPC, "cheio")), "ENOSPC (disco cheio) NÃO é proteção")
ok(not c._e_protecao_de_escrita(OSError(errno.ENOENT, "sumiu")), "ENOENT (pendrive removido) NÃO é proteção")

# ---- proteção de escrita simulada -------------------------------------------------------------------------------
real_open, real_replace, real_rename, real_remove = builtins.open, os.replace, os.rename, os.remove
tentativas_de_escrita = []


def _na_pasta(p):
    try:
        return os.path.abspath(os.fspath(p)).startswith(os.path.abspath(d))
    except TypeError:
        return False


def open_bloqueado(arq, modo="r", *a, **k):
    if isinstance(modo, str) and any(ch in modo for ch in "wax+") and _na_pasta(arq):
        tentativas_de_escrita.append(("open", modo))
        raise PermissionError(errno.EACCES, "Acesso negado (simulação de pendrive protegido)")
    return real_open(arq, modo, *a, **k)


def bloquear(nome, real):
    def f(a, b=None, *x, **k):
        if _na_pasta(a) or (b is not None and _na_pasta(b)):
            tentativas_de_escrita.append((nome, ""))
            raise PermissionError(errno.EACCES, "Acesso negado (simulação)")
        return real(a, b, *x, **k) if b is not None else real(a, *x, **k)
    return f


def proteger(sim):
    builtins.open = open_bloqueado if sim else real_open
    os.replace = bloquear("replace", real_replace) if sim else real_replace
    os.rename = bloquear("rename", real_rename) if sim else real_rename
    os.remove = (lambda a, *x, **k: (tentativas_de_escrita.append(("remove", "")), (_ for _ in ()).throw(PermissionError(errno.EACCES, "x")))[1]
                 if _na_pasta(a) else real_remove(a, *x, **k)) if sim else real_remove


print("== 1) abertura normal em pendrive protegido: erro claro, sem gastar tentativa")
proteger(True)
try:
    c.Cofre.abrir(P, senha=S); r = None
except c.ErroGravacao as ex:
    r = ex
finally:
    proteger(False)
ok(r is not None and r.protegido, "abrir normal levanta ErroGravacao marcado como 'protegido' (a interface oferece o modo consulta)")
ok(open(P, "rb").read() == original, "arquivo idêntico, byte a byte: nenhuma tentativa foi gasta")

print("== 2) MODO CONSULTA: abre, lê e NÃO grava nada")
tentativas_de_escrita.clear()
proteger(True)
try:
    q = c.Cofre.abrir(P, senha=S, consulta=True)
    abriu = True
except Exception as ex:
    abriu = False; print("   ", type(ex).__name__, ex)
finally:
    proteger(False)
ok(abriu and q.somente_leitura and len(q.registros) == 3 and q.registros[1]["senha"] == "senha-1", "abriu e mostra os 3 itens com as senhas")
ok(open(P, "rb").read() == original, "arquivo do cofre idêntico depois de abrir em modo consulta")
ok(sorted(os.listdir(d)) == antes_dir, f"nenhum arquivo criado nem apagado na pasta ({sorted(os.listdir(d))})")
ok(not [t for t in tentativas_de_escrita if t[0] != "open"], f"nenhum replace/rename/remove tentado ({tentativas_de_escrita[:3]})")

print("== 3) em modo consulta qualquer salvamento é recusado e desfeito na memória")
for acao in ("salvar", "transacao"):
    try:
        if acao == "salvar":
            q.salvar()
        else:
            with q.transacao():
                q.registros.append({"id": "novo", "servico": "X", "login": "", "senha": "", "notas": ""})
        r = None
    except c.ErroGravacao as ex:
        r = ex
    ok(r is not None and r.protegido, f"{acao}() recusado com ErroGravacao 'protegido'")
ok(len(q.registros) == 3, "a transação foi DESFEITA na memória (continua com 3 itens)")
try:
    q.trocar_senha("outra senha bem comprida e boa 99"); r = None
except c.ErroGravacao as ex:
    r = ex
ok(r is not None and open(P, "rb").read() == original, "trocar a senha também é recusado e o arquivo não muda")

print("== 4) senha errada em modo consulta: não conta, não destrói")
proteger(True)
try:
    resultados = []
    for _ in range(5):                               # o cofre só tem 3 tentativas: em modo normal teria sido destruído
        try:
            c.Cofre.abrir(P, senha="senha errada longa e diferente", consulta=True)
        except c.SenhaIncorreta as ex:
            resultados.append(getattr(ex, "consulta", False))
        except c.CofreDestruido:
            resultados.append("DESTRUIDO")
finally:
    proteger(False)
ok(resultados == [True] * 5, "5 senhas erradas: sempre SenhaIncorreta (modo consulta), nunca destruído")
ok(open(P, "rb").read() == original and os.path.exists(P), "arquivo intacto e com o contador cheio")
ok(c.tentativas_restantes(P) == 3, "tentativas continuam 3")
w = c.Cofre.abrir(P, senha=S)
ok(len(w.registros) == 3, "depois, com o pendrive destravado, abre normalmente")

print("== 5) cofre da versão 1 não abre em modo consulta (precisa gravar para atualizar)")
b = bytearray(open(P, "rb").read()); b[:8] = c.MAGIC_V1
open(P, "wb").write(bytes(b))
try:
    c.Cofre.abrir(P, senha=S, consulta=True); r = "abriu"
except c.ArquivoInvalido as ex:
    r = "recusou"
ok(r == "recusou", "v1 em modo consulta: recusa com orientação")
print("\nFALHAS:", FAL)
sys.exit(1 if FAL else 0)
