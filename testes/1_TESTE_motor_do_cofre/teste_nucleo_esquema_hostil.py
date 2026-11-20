"""ESQUEMA HOSTIL DENTRO DO COFRE: itens com formato errado depois de decifrados.

O arquivo é autenticado (ninguém de fora o altera), mas um item pode chegar torto de uma versão antiga, de uma
importação ou de um defeito: campo com tipo errado, `id` ausente ou repetido, aninhamento absurdo, número gigante.
Antes da função `_sanear_itens` isso passava na abertura e quebrava DEPOIS (a auditoria de senhas dava AttributeError).
Confere que, para cada caso: o cofre ABRE, todo campo conhecido é texto, todo `id` é texto único, a auditoria local
e uma volta salvar/abrir funcionam, e que um cofre NORMAL passa pelo saneamento sem nenhuma alteração."""
import copy, os, sys, tempfile, importlib.util

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "6_TESTE_ferramentas_dos_testes"))
import _resultado; _resultado.registrar(__file__)          # grava resultados/resultado_nucleo_esquema_hostil.txt

CAMINHO_PROG = os.path.abspath(os.path.join(AQUI, "..", "..", "cofre_senhas.py"))
spec = importlib.util.spec_from_file_location("c", CAMINHO_PROG)
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
FAL = []


def ok(cond, msg):
    """Imprime [OK]/[FALHOU] (o executor procura estes marcadores) e guarda as falhas."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + msg, flush=True)
    if not cond:
        FAL.append(msg)


S = "cavalo azul come pizza na chuva 2026"
fundo = []
for _ in range(3000):
    fundo = [fundo]

CASOS = {
    "tipos errados (PIN lista, texto número, senha nula, notas dict)":
        [{"id": "t1", "servico": 123, "senha": None, "pin": ["a", "b"], "notas": {"x": 1}, "login": True}],
    "sem id": [{"servico": "sem id", "senha": "x"}],
    "id não textual": [{"id": 7, "servico": "id numérico"}, {"id": None, "servico": "id nulo"}, {"id": "", "servico": "id vazio"}],
    "ids repetidos": [{"id": "a", "servico": "primeiro"}, {"id": "a", "servico": "segundo"}, {"id": "a", "servico": "terceiro"}],
    "campos desconhecidos e nomes perigosos":
        [{"id": "z", "servico": "s", "__proto__": {"admin": True}, "constructor": "x", "evil": "x" * 1000}],
    "aninhamento de 3000 níveis": [{"id": "n", "servico": "s", "notas": fundo}],
    "inteiro com 5000 dígitos": [{"id": "g", "servico": "s", "notas": 10 ** 5000}],
    "float infinito/NaN": [{"id": "f", "servico": "s", "pin": float("inf"), "chave": float("nan")}],
}

for nome, regs in CASOS.items():
    print("== " + nome)
    d = tempfile.mkdtemp(prefix="cofre_esq_"); P = os.path.join(d, "cofre.dat")
    v = c.Cofre.criar(P, S, 5, 0, "alto")
    v.registros = list(regs)           # sem deepcopy: o aninhamento de 3000 níveis estoura a recursão do próprio copy
    try:
        v.salvar(); v.fechar()
    except Exception as ex:                                  # noqa: BLE001
        # o próprio salvar pode recusar (ex.: NaN não cabe no JSON estrito): tudo bem, desde que seja erro CONTROLADO
        ok(isinstance(ex, (ValueError, c.ErroGravacao, RecursionError, OverflowError)),
           f"salvar recusou de forma controlada ({type(ex).__name__}: {str(ex)[:60]})")
        continue
    try:
        a = c.Cofre.abrir(P, senha=S)
    except Exception as ex:                                  # noqa: BLE001
        ok(False, f"abrir quebrou: {type(ex).__name__}: {str(ex)[:80]}")
        continue
    ok(len(a.registros) == len(regs), f"abriu com {len(a.registros)} item(ns)")
    textos = all(isinstance(r.get(k, ""), str) for r in a.registros for k in c.CAMPOS)
    ok(textos, "todo campo conhecido é texto")
    # cópias NOVAS dos ids (caractere a caractere): fechar() zera os textos dos itens no próprio objeto
    ids = ["".join(list(r.get("id"))) if isinstance(r.get("id"), str) else r.get("id") for r in a.registros]
    servicos = ["".join(list(r.get("servico", ""))) for r in a.registros]
    evil = "".join(list(a.registros[0].get("evil", "")))
    ok(all(isinstance(i, str) and i for i in ids) and len(set(ids)) == len(ids), f"todo id é texto não vazio e único ({ids})")
    if nome.startswith("ids repetidos"):
        ok(ids[0] == "a" and servicos[0] == "primeiro", "o primeiro item com o id repetido MANTÉM o seu id")
    if nome.startswith("campos desconhecidos"):
        ok(evil == "x" * 1000, "campo desconhecido é preservado (compatível com versões futuras)")
    try:
        c.auditar_cofre(a.registros)
        ok(True, "auditoria local de senhas roda sem erro")
    except Exception as ex:                                  # noqa: BLE001
        ok(False, f"auditoria quebrou: {type(ex).__name__}: {ex}")
    try:
        a.salvar(); a.fechar()
        b = c.Cofre.abrir(P, senha=S)
        ok([r["id"] for r in b.registros] == ids, "salvar + reabrir mantém os mesmos itens e ids")
        b.fechar()
    except Exception as ex:                                  # noqa: BLE001
        ok(False, f"volta salvar/abrir quebrou: {type(ex).__name__}: {ex}")

print("== cofre NORMAL passa pelo saneamento sem mudar nada")
normal = [c.novo_item(servico=f"conta {i}", login="u", senha=f"Senha-{i}-Forte!", notas="n") for i in range(50)]
copia = copy.deepcopy(normal)
ok(c._sanear_itens(normal) == 0 and normal == copia, "0 itens corrigidos e conteúdo idêntico num cofre válido")

print("\nFALHAS: " + str(FAL) if FAL else "\nTODOS OK")
sys.exit(1 if FAL else 0)
