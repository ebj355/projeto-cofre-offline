# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""FONTES NOMEADAS: preparar_fontes pode ser chamada de novo (mesma janela ou outra janela) sem erro. Antes, a segunda
chamada falhava com "named font ... does not exist" no Python 3.14 do Windows (descartar o objeto Font antigo apagava a
fonte nomeada no Tk e a configuração seguinte quebrava)."""
import os, sys
RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, RAIZ)
import tkinter as tk
from tkinter import font as tkfont
import cofre_senhas as c
f = []


def ok(cond, nome):
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome, flush=True); f.append(bool(cond))


r = tk.Tk(); r.withdraw()
try:
    c.aplicar_tema(r)
    c.preparar_fontes(r)
    c.preparar_fontes(r)
    c.preparar_fontes(r)
    ok(True, "preparar_fontes 3 vezes na mesma janela (depois do tema) sem erro")
    ok("CofreTexto" in tkfont.names(r), "a fonte nomeada CofreTexto continua existindo")
    ok(all(n in tkfont.names(r) for n in ("CofreTitulo", "CofreMono", "CofreForte")), "as demais fontes nomeadas também")
    ok(int(tkfont.nametofont("CofreTexto", root=r).actual("size")) != 0, "a fonte é utilizável")
except Exception as ex:
    ok(False, f"erro inesperado: {ex!r}")
r.destroy()
r2 = tk.Tk(); r2.withdraw()
try:
    c.aplicar_tema(r2)
    ok("CofreTexto" in tkfont.names(r2), "segunda janela (depois de destruir a primeira): fontes criadas")
except Exception as ex:
    ok(False, f"segunda janela: {ex!r}")
r2.destroy()
print("\nTODOS OK" if all(f) else "\nFALHAS: %d" % f.count(False))
sys.exit(0 if all(f) else 1)
