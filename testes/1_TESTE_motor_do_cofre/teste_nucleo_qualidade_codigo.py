# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Qualidade de software e higiene do código-fonte, no nível de "isso aqui seria um problema de verdade se
alguém revisasse o código" (complementa o `bandit`/`flake8` já cobertos por `teste_pentest_sast.py`, que olham
padrões conhecidos de insegurança; aqui o foco é em coisas que uma ferramenta genérica não sabe que são
específicas DESTE cofre). O que é FALHA de verdade (segurança/robustez) e o que é só [INFO] (estilo, sem risco):

FALHA se encontrado:
  1) `eval`/`exec`/`pickle.loads` em qualquer lugar do código (execução de código arbitrário / desserialização
     insegura - nenhum dos dois é necessário para um cofre de senhas e a ausência total é o estado mais seguro);
  2) `subprocess` com `shell=True` (injeção de comando, caso algum dia um helper externo seja chamado);
  3) `except:` nu (sem tipo) - isso engoliria até `KeyboardInterrupt`/`SystemExit`, o que é pior que um
     `except Exception:` e pode mascarar justamente uma falha de segurança sendo detectada;
  4) `print()` passando por argumento uma variável cujo NOME sugere dado sensível (senha/chave/token/dek/pin) -
     um resquício de depuração vazando segredo no console/log seria um vazamento de dados real;
  5) comentário "TODO"/"FIXME" dentro de uma função de segurança/criptografia (`derivar_chave`, `_embrulhar`,
     `_desembrulhar`, `Cofre.abrir`, `Cofre.salvar`, `Cofre.criar`) - um "depois eu termino isso" esquecido
     justamente no núcleo de segurança é grave; fora dessas funções é só [INFO].

Só [INFO] (medidas de qualidade, não travam o teste):
  - cobertura de docstring nas funções/classes de nível superior;
  - as 5 funções mais longas do arquivo (sinal de complexidade, não uma regra rígida);
  - contagem total de TODO/FIXME no resto do arquivo."""
import ast, os, re, sys

RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, RAIZ)
CAMINHO = os.path.join(RAIZ, "cofre_senhas.py")

falhas = []
def ok(cond, nome):
    print(("  [OK] " if cond else "  [FALHOU] ") + nome)
    if not cond:
        falhas.append(nome)

fonte = open(CAMINHO, encoding="utf-8").read()
linhas = fonte.splitlines()
arvore = ast.parse(fonte)

print("1) eval / exec / pickle.loads - execução/desserialização arbitrária")
achados = re.findall(r"\b(eval|exec)\s*\(|pickle\.loads?\s*\(", fonte)
ok(not achados, f"nenhum uso de eval()/exec()/pickle.load(s)() no arquivo: {achados}")

print("\n2) subprocess com shell=True")
achados_shell = re.findall(r"subprocess\.\w+\([^)]*shell\s*=\s*True", fonte)
ok(not achados_shell, f"nenhum subprocess com shell=True: {len(achados_shell)} achado(s)")

print("\n3) except: nu (sem tipo)")
nus = [no.lineno for no in ast.walk(arvore) if isinstance(no, ast.ExceptHandler) and no.type is None]
ok(not nus, f"nenhum 'except:' nu (sem tipo) no código: linhas {nus}")

print("\n4) print() com variável de nome sensível")
NOME_SENSIVEL = re.compile(r"^(senha|chave|token|dek|pin|kek|wrap|nonce)\w*$", re.IGNORECASE)
prints_suspeitos = []
for no in ast.walk(arvore):
    if isinstance(no, ast.Call) and getattr(no.func, "id", None) == "print":
        for arg in no.args:
            if isinstance(arg, ast.Name) and NOME_SENSIVEL.match(arg.id):
                prints_suspeitos.append((arg.id, no.lineno))
ok(not prints_suspeitos, f"nenhum print() recebe diretamente uma variável com nome de dado sensível: {prints_suspeitos}")

print("\n5) TODO/FIXME dentro de função de segurança/criptografia")
FUNCOES_CRITICAS = {"derivar_chave", "_embrulhar", "_desembrulhar", "criar", "abrir", "salvar"}
todo_critico = []
todo_fora = 0
for no in ast.walk(arvore):
    if isinstance(no, ast.FunctionDef):
        ini = no.lineno
        fim = max((getattr(n, "lineno", ini) for n in ast.walk(no)), default=ini)
        corpo = "\n".join(linhas[ini - 1:fim])
        achados_f = re.findall(r"\bTODO\b|\bFIXME\b", corpo)
        if achados_f and no.name in FUNCOES_CRITICAS:
            todo_critico.append((no.name, no.lineno, achados_f))
        elif achados_f:
            todo_fora += len(achados_f)
ok(not todo_critico, f"nenhum TODO/FIXME dentro de uma função crítica de segurança: {todo_critico}")
print(f"  [INFO] TODO/FIXME fora de funções críticas (estilo, não é falha): {todo_fora}")

print("\n[INFO] Cobertura de docstring (funções e classes de nível superior)")
nivel_sup = [no for no in arvore.body if isinstance(no, (ast.FunctionDef, ast.ClassDef))]
com_doc = sum(1 for no in nivel_sup if ast.get_docstring(no))
pct = 100 * com_doc / len(nivel_sup) if nivel_sup else 0
print(f"  [INFO] {com_doc}/{len(nivel_sup)} ({pct:.0f}%) funções/classes de nível superior têm docstring")

print("\n[INFO] As 5 funções mais longas do arquivo (sinal de complexidade)")
tamanhos = []
for no in ast.walk(arvore):
    if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
        ini = no.lineno
        fim = max((getattr(n, "lineno", ini) for n in ast.walk(no)), default=ini)
        tamanhos.append((fim - ini + 1, no.name, ini))
tamanhos.sort(reverse=True)
for tam, nome, ini in tamanhos[:5]:
    print(f"  [INFO] {nome} (linha {ini}): {tam} linhas")

print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
