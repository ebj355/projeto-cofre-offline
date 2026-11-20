"""PERMISSÕES: gravar o cofre onde não se pode (pasta somente leitura, arquivo somente leitura, acesso negado no meio da
troca). O programa tem de devolver ErroGravacao com mensagem clara (nunca PermissionError solto), marcar 'protegido' quando
for proteção de escrita (a interface então oferece o MODO CONSULTA), não deixar .tmp para trás e manter o cofre anterior
intacto. Parte 1 SIMULA a negação (vale mesmo rodando como administrador/root); parte 2 usa a permissão REAL do sistema
quando ela é aplicável (pula, dizendo, se o teste roda como root, que ignora permissões). Linux e Windows."""
import os, sys, stat, errno, hashlib, subprocess
_RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, _RAIZ); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "6_TESTE_ferramentas_dos_testes"))
import _resultado; _resultado.registrar(__file__)
import cofre_senhas as c
f = []
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome, flush=True); f.append(bool(cond))
c.NIVEIS["alto"] = (1, 8192)
W = _resultado.pasta_temporaria("cofre_perm_"); S = "cavalo azul come pizza na chuva"
def ler(p):
    with open(p, "rb") as a: return a.read()
def sha(p): return hashlib.sha256(ler(p)).hexdigest()
def novo_cofre(nome):
    d = os.path.join(W, nome); os.makedirs(d); p = os.path.join(d, "c.dat")
    v = c.Cofre.criar(p, S, 5, c.MODO_OU, "alto"); v.registros.append(c.novo_item(servico="X", login="y", senha="z")); v.salvar()
    return v, p, d
def sem_tmp(d): return not [x for x in os.listdir(d) if x.endswith(".tmp")]

print("== 1) acesso negado SIMULADO (funciona também como administrador)")
for nome, alvo, erro in (("abrir o .tmp negado", "os.open", PermissionError(errno.EACCES, "negado")),
                         ("pasta somente leitura (EROFS)", "os.open", OSError(errno.EROFS, "somente leitura")),
                         ("disco cheio", "os.open", OSError(errno.ENOSPC, "cheio")),
                         ("troca final negada", "os.replace", PermissionError(errno.EACCES, "negado"))):
    v, p, d = novo_cofre(nome.split()[0] + str(len(f)))
    antes = sha(p)
    mod, fn = alvo.split(".")
    real = getattr(__import__(mod), fn)
    def falha(*a, _real=real, _alvo=alvo, _erro=erro, **k):
        if _alvo == "os.open" and not str(a[0]).endswith(".tmp"): return _real(*a, **k)
        raise _erro
    setattr(__import__(mod), fn, falha)
    v.registros.append(c.novo_item(servico="Novo", login="n", senha="n"))
    try:
        v.salvar(); ok(False, f"{nome}: salvou?!")
    except c.ErroGravacao as ex:
        ok(len(str(ex)) > 10, f"{nome}: ErroGravacao com mensagem ('{str(ex)[:60]}')")
        if "negado" in nome or "somente" in nome or "troca" in nome:
            ok(getattr(ex, "protegido", False), f"{nome}: marcado 'protegido' (a interface oferece o modo consulta)")
    except Exception as ex:
        ok(False, f"{nome}: erro solto {type(ex).__name__}: {ex}")
    finally:
        setattr(__import__(mod), fn, real)
    ok(sha(p) == antes, f"{nome}: cofre anterior intacto"); ok(sem_tmp(d), f"{nome}: nenhum .tmp sobrou")
    v.fechar()

print("== 2) permissão REAL do sistema")
raiz = hasattr(os, "geteuid") and os.geteuid() == 0
if raiz:
    print("  [INFO] rodando como root: o sistema ignora permissões; parte real pulada (a simulada acima cobre)")
else:
    v, p, d = novo_cofre("real"); antes = sha(p)
    v.registros.append(c.novo_item(servico="Novo2", login="n", senha="n"))
    if os.name == "nt":
        subprocess.run(["icacls", d, "/deny", "%s:(WD,AD)" % os.environ.get("USERNAME", "Users")], capture_output=True)   # nega criar arquivos/pastas
    else:
        os.chmod(d, stat.S_IRUSR | stat.S_IXUSR)
    try:
        try:
            v.salvar(); ok(False, "pasta sem permissão de escrita: salvou?!")
        except c.ErroGravacao as ex:
            ok(True, f"pasta sem permissão: ErroGravacao ('{str(ex)[:60]}')"); ok(getattr(ex, "protegido", False), "pasta sem permissão: 'protegido'")
        except Exception as ex:
            ok(False, f"pasta sem permissão: erro solto {type(ex).__name__}: {ex}")
    finally:
        if os.name == "nt":
            subprocess.run(["icacls", d, "/remove:d", os.environ.get("USERNAME", "Users")], capture_output=True)
        else:
            os.chmod(d, stat.S_IRWXU)
    ok(sha(p) == antes, "pasta sem permissão: cofre anterior intacto"); ok(sem_tmp(d), "pasta sem permissão: nenhum .tmp")
    r = c.Cofre.abrir(p, senha=S, consulta=True); ok(len(r.registros) == 1, "e o cofre ainda abre em modo consulta"); r.fechar(); v.fechar()
print("\nTODOS OK" if all(f) else "\nHOUVE FALHAS")
sys.exit(0 if all(f) else 1)
