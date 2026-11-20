"""OBJETOS SENSÍVEIS E O COLETOR DE LIXO (gc) DO PYTHON.

`teste_vazamento_memoria.py` e `teste_memoria.py` procuram sobras de senha na RAM por varredura de bytes. Este olha por
OUTRO ângulo, o do próprio interpretador: depois de `fechar()`, o que ainda está VIVO e alcançável?
1) A instância `Cofre` some de verdade (referência fraca morre) depois de fechar + soltar + gc.collect(): nenhum
   ciclo de referência (callback, executor, closure) a mantém viva no heap com as chaves dentro.
2) Todos os campos de chave viram None e a lista de itens fica vazia.
3) As chaves (dek e derivadas) capturadas ANTES de fechar estão ZERADAS depois (sobrescritas no próprio objeto).
4) Os textos secretos dos itens (senha, PIN, conta) capturados antes estão zerados depois.
5) Varredura de TODOS os objetos vivos (gc.get_objects): nenhum dict/lista/tupla do programa guarda mais a isca.
6) Repetir abrir/fechar 20 vezes não acumula instâncias de Cofre (sem vazamento de objetos por ciclo).
Limite honesto, igual ao do MODELO_DE_AMEACAS: cópias intermediárias de `str` que o Python fez por conta própria não são
garantidas; por isso o item 5 usa iscas montadas caractere a caractere e confere só o que o PROGRAMA guarda."""
import gc, os, sys, tempfile, secrets, weakref, importlib.util

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "6_TESTE_ferramentas_dos_testes"))
import _resultado; _resultado.registrar(__file__)          # grava resultados/resultado_nucleo_gc_objetos_sensiveis.txt

CAMINHO_PROG = os.path.abspath(os.path.join(AQUI, "..", "..", "cofre_senhas.py"))
spec = importlib.util.spec_from_file_location("c", CAMINHO_PROG)
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
FAL = []


def ok(cond, msg):
    """Imprime [OK]/[FALHOU] (o executor procura estes marcadores) e guarda as falhas."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + msg, flush=True)
    if not cond:
        FAL.append(msg)


def nova_isca(prefixo):
    """Texto único, montado caractere a caractere (evita que o próprio teste mantenha uma cópia compartilhada)."""
    return "".join(list(prefixo + secrets.token_hex(12)))


def instancias_vivas():
    """Quantas instâncias de Cofre o coletor de lixo ainda enxerga."""
    gc.collect()
    return sum(1 for o in gc.get_objects() if isinstance(o, c.Cofre))


def achar_isca(invertida):
    """Procura a isca como VALOR dentro de dicts/listas/tuplas vivos (o que o programa guarda). Recebe a isca ESCRITA AO
    CONTRÁRIO e a desvira só aqui dentro: assim nem o dicionário de variáveis deste teste contém a isca "de frente"
    (o programa zera o texto ORIGINAL no próprio objeto, e uma busca com ele viraria uma busca por zeros)."""
    isca = invertida[::-1]
    alvo = isca.encode()
    achados = 0
    meus = globals()                      # as variáveis deste teste (a senha mestra S fica aqui de propósito)
    for o in gc.get_objects():
        tipo = type(o)
        if o is meus:
            continue
        if tipo is dict:
            vals = list(o.values())
        elif tipo in (list, tuple):
            vals = list(o)
        else:
            continue
        for v in vals:
            if type(v) is str and isca in v:
                achados += 1
            elif type(v) in (bytes, bytearray) and alvo in bytes(v):
                achados += 1
    return achados


S = nova_isca("Mestra-") + "Aa1!"
d = tempfile.mkdtemp(prefix="cofre_gc_"); P = os.path.join(d, "cofre.dat")
c.Cofre.criar(P, S, 5, 0, "alto").salvar()

print("== 1-4) fechar + soltar + gc.collect()")
isca_senha, isca_pin, isca_conta = nova_isca("SENHAISCA"), nova_isca("PINISCA"), nova_isca("CONTAISCA")
inv = {"senha": isca_senha[::-1], "pin": isca_pin[::-1], "conta": isca_conta[::-1], "mestra": S[::-1]}  # p/ a varredura do item 5
v = c.Cofre.abrir(P, senha=S)
v.registros.append(c.novo_item(servico="Banco", senha=isca_senha, pin=isca_pin, numero_conta=isca_conta))
v.salvar(); v.fechar(); v = None
v = c.Cofre.abrir(P, senha=S)
fraca = weakref.ref(v)
# captura OS OBJETOS das chaves e dos textos ANTES de fechar (para conferir depois que foram zerados in-place)
chaves = {k: getattr(v, k, None) for k in ("dek", "_ks", "_kb", "_F", "_G", "_vkey")}
chaves = {k: o for k, o in chaves.items() if isinstance(o, (bytes, bytearray)) and len(o) >= 16}
itens = [r for r in v.registros if r.get("servico") == "Banco"]
textos = {k: itens[0][k] for k in ("senha", "pin", "numero_conta")} if itens else {}
ok(bool(chaves), f"há chaves em memória para conferir ({sorted(chaves)})")
ok(len(textos) == 3, "o item de teste foi lido de volta")
vivos_antes = [o for o in chaves.values()]
v.fechar()
ok(all(getattr(v, k, "x") in (None, [], ()) for k in ("dek", "_ks", "_kb", "_F", "_G", "_vkey", "chave_gerada")) and v.registros == [],
   "depois de fechar(): campos de chave são None e a lista de itens está vazia")
zeradas = {k: (set(bytes(o)) == {0}) for k, o in chaves.items()}
ok(all(zeradas.values()), f"as chaves capturadas antes foram ZERADAS no próprio objeto: {zeradas}")
verifica_internacao = getattr(sys, "_is_interned", None)
if verifica_internacao is None:
    print("  [PULADO] strings não são sobrescritas nesta versão do Python: não há API segura para detectar strings internadas")
else:
    zt = {k: (set(t.encode()) == {0}) for k, t in textos.items() if isinstance(t, str)}
    ok(zt and all(zt.values()), f"os textos secretos do item foram zerados no próprio objeto: {zt}")
v = None
gc.collect()
ok(fraca() is None, "a instância Cofre foi coletada (nenhum ciclo de referência a segura viva)")

print("== 5) varredura de todos os objetos vivos atrás das iscas")
# o teste mantém as iscas só nestas variáveis; depois de zeradas, as iscas ORIGINAIS não existem mais no heap
for nome in ("senha", "pin", "conta"):
    n = achar_isca(inv[nome])
    ok(n == 0, f"isca de {nome}: {n} ocorrência(s) em dict/lista/tupla vivos (esperado 0)")
ok(achar_isca(inv["mestra"]) == 0, "a senha mestra não está guardada em nenhum dict/lista/tupla vivo")

print("== 6) 20 ciclos abrir/fechar não acumulam instâncias")
base = instancias_vivas()
for _ in range(20):
    x = c.Cofre.abrir(P, senha=S); x.fechar(); x = None
depois = instancias_vivas()
ok(depois <= base, f"instâncias de Cofre vivas: antes {base}, depois de 20 ciclos {depois}")

print("\nFALHAS: " + str(FAL) if FAL else "\nTODOS OK")
sys.exit(1 if FAL else 0)
