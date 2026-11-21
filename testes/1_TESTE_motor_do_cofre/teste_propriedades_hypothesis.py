# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Testes por PROPRIEDADES (Hypothesis): gera entradas aleatorias e confere que criar->salvar->fechar->abrir devolve exatamente os mesmos itens e que a leitura de CSV hostil nunca estoura erro nao tratado.
Uso: python testes/1_TESTE_motor_do_cofre/teste_propriedades_hypothesis.py  |  Saida: 0 = passou | 1 = falhou | 9 = hypothesis nao instalado. COFRE_HYPOTHESIS_EXEMPLOS (padrao 12) muda a quantidade; cada exemplo gasta ~1 s de Argon2 (nivel alto)."""
import importlib
import os
import shutil
import sys
import tempfile
import unicodedata

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(RAIZ, "testes", "6_TESTE_ferramentas_dos_testes"))
cache_testes = importlib.import_module("_cache_testes")
cache_testes.preparar_cache_temporario("hypothesis")
sys.path.insert(0, RAIZ)
try:
    from hypothesis import HealthCheck, given, settings
    from hypothesis import strategies as st
    from hypothesis.database import DirectoryBasedExampleDatabase
except ImportError as ex:
    print(f"PULADO: Hypothesis indisponivel: {ex}")
    sys.exit(9)
cs = importlib.import_module("cofre_senhas")

N = int(os.environ.get("COFRE_HYPOTHESIS_EXEMPLOS", "12"))
_db_dir = os.environ.get("COFRE_TEST_HYPOTHESIS_DB")
if _db_dir:
    os.makedirs(_db_dir, exist_ok=True)
DB = DirectoryBasedExampleDatabase(_db_dir) if _db_dir else None
CONF = settings(max_examples=N, deadline=None, derandomize=False,
                suppress_health_check=list(HealthCheck), database=DB)
# so caracteres imprimiveis: controles e substitutos sao tratados/limpos de proposito pelo cofre (ver teste_limites)
ALFABETO = st.characters(whitelist_categories=("L", "N", "P", "S", "Zs"), max_codepoint=0x2FFFF)
TEXTO = st.text(ALFABETO, min_size=1, max_size=60).filter(lambda s: s == s.strip())
SENHA = st.text(ALFABETO, min_size=cs.MIN_SENHA, max_size=80).filter(lambda s: s == s.strip())
ITEM = st.fixed_dictionaries({"servico": TEXTO, "login": TEXTO, "senha": TEXTO})


@CONF
@given(senha=SENHA, itens=st.lists(ITEM, max_size=8))
def ida_e_volta(senha, itens):
    pasta = tempfile.mkdtemp(prefix="cofre_hyp_")
    try:
        esperado = [{k: v.encode("utf-8").decode("utf-8") for k, v in i.items()} for i in itens]
        caminho = os.path.join(pasta, "cofre.dat")
        c = cs.Cofre.criar(caminho, senha, modo=cs.MODO_S, nivel="alto")
        c.registros = [dict(i) for i in itens]
        c.salvar()
        c.fechar()
        c2 = cs.Cofre.abrir(caminho, senha=senha)
        try:
            lidos = [{k: r.get(k) for k in ("servico", "login", "senha")} for r in c2.registros]
            assert lidos == esperado, "itens diferentes depois de salvar e reabrir"
        finally:
            c2.fechar()
        # a forma NFD da mesma senha tambem precisa abrir (o cofre normaliza para NFC)
        c3 = cs.Cofre.abrir(caminho, senha=unicodedata.normalize("NFD", senha))
        c3.fechar()
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


@settings(max_examples=max(N * 10, 100), deadline=None, suppress_health_check=list(HealthCheck), database=DB)
@given(dados=st.binary(max_size=4000))
def csv_hostil(dados):
    pasta = tempfile.mkdtemp(prefix="cofre_hyp_csv_")
    try:
        arq = os.path.join(pasta, "entrada.csv")
        with open(arq, "wb") as f:
            f.write(dados)
        try:
            cs._ler_planilha_arquivo(arq)
        except ValueError:
            pass    # recusa limpa e o comportamento esperado; qualquer OUTRA excecao e defeito
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


if __name__ == "__main__":
    falhas = []
    for nome, fn in (("ida_e_volta", ida_e_volta), ("csv_hostil", csv_hostil)):
        try:
            fn()
            print(f"[OK] {nome}")
        except Exception as ex:
            falhas.append(nome)
            print(f"[FALHOU] {nome}: {type(ex).__name__}: {ex}")
    print("FALHAS:", falhas)
    sys.exit(1 if falhas else 0)
