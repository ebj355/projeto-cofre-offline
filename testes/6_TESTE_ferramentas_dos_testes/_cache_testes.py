# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Prepara cache isolado para uma execução e remove-o ao encerrar."""
import atexit
import os
import shutil
import sys
import tempfile

RAIZ_CACHE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "CACHE"))


def preparar_cache_temporario(prefixo):
    cache = os.environ.get("COFRE_TEST_CACHE_DIR")
    proprio = not cache
    if proprio:
        os.makedirs(RAIZ_CACHE, exist_ok=True)
        cache = tempfile.mkdtemp(prefix=f"_cache_{prefixo}_", dir=RAIZ_CACHE)
    else:
        os.makedirs(cache, exist_ok=True)
    cache = os.path.abspath(cache)

    if proprio:
        def apagar_cache():
            try:
                shutil.rmtree(cache)
            except FileNotFoundError:
                pass
            except OSError as ex:
                print(f"AVISO: nao consegui remover o cache temporario {cache}: {ex}", file=sys.stderr)
                return
            try:
                os.rmdir(RAIZ_CACHE)
            except FileNotFoundError:
                pass
            except OSError as ex:
                if os.path.isdir(RAIZ_CACHE) and os.listdir(RAIZ_CACHE):
                    return
                print(f"AVISO: nao consegui remover a pasta CACHE vazia {RAIZ_CACHE}: {ex}", file=sys.stderr)

        atexit.register(apagar_cache)

    os.environ["COFRE_TEST_CACHE_DIR"] = cache
    os.environ["COFRE_TEST_HYPOTHESIS_DB"] = os.path.join(cache, "hypothesis")
    os.environ["HYPOTHESIS_STORAGE_DIRECTORY"] = os.path.join(cache, "hypothesis_storage")
    os.environ["COFRE_TEST_RUFF_CACHE"] = os.path.join(cache, "ruff")
    os.environ["RUFF_CACHE_DIR"] = os.environ["COFRE_TEST_RUFF_CACHE"]
    os.environ["COFRE_TEST_MYPY_CACHE"] = os.path.join(cache, "mypy")
    os.environ["COFRE_TEST_PYTEST_CACHE"] = os.path.join(cache, "pytest")
    os.environ["PYTHONPYCACHEPREFIX"] = os.path.join(cache, "pycache")
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    for nome in ("TEMP", "TMP", "TMPDIR"):
        os.environ[nome] = cache
    tempfile.tempdir = cache
    sys.pycache_prefix = os.environ["PYTHONPYCACHEPREFIX"]
    return cache
