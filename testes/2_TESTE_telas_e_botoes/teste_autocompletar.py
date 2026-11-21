"""Verifica o autocomplete de marcas sem rede; use --visual para abrir a janela manual."""
import os
import sys
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from icones_marcas import (
    ALIASES, MARCAS, _ALIAS_NORMALIZADOS, AutocompletarMarcas, achar_marca, icone,
    normalizar, sugerir,
)


def verificar():
    assert normalizar("Nú Bank") == "nubank"
    assert achar_marca("Nubank Pessoal") == "nubank"
    assert achar_marca("Crefisa") == "crefisa"
    assert achar_marca("gpay") == "googlepay"
    assert achar_marca("e-social") == "esocial"
    assert MARCAS["nubank"] == ("#820AD1", "Nu")
    assert ALIASES["ml"] == "mercadolivre"
    assert all(chave in MARCAS for chave in _ALIAS_NORMALIZADOS.values())
    assert achar_marca("x") == "x"
    assert achar_marca("xy") is None
    assert ("nubank", "Nubank") in sugerir("nu")
    assert any(chave.startswith("banco") or chave == "banrisul" for chave, _ in sugerir("ban"))
    assert any(chave in ("net", "netflix", "netlify", "netshoes") for chave, _ in sugerir("net"))
    assert sugerir("Padaria") == []
    assert sugerir("") == []

    root = tk.Tk()
    root.withdraw()
    try:
        campo = ttk.Entry(root)
        preview = ttk.Label(root)
        lista = tk.Frame(root)
        auto = AutocompletarMarcas(campo, preview, lista)
        campo.insert(0, "nu")
        auto.atualizar()
        indice_nubank = auto.resultados.index(("nubank", "Nubank"))
        auto.escolher(indice_nubank)
        assert campo.get() == "Nubank"
        campo.delete(0, "end")
        campo.insert(0, "Padaria")
        auto.atualizar()
        assert not auto.resultados
        assert preview.cget("image")
        assert icone("Nubank", 24, root) is icone("Nú Bank", 24, root)
        assert icone("Padaria", 24, root) is icone(" PADARIA ", 24, root)
        assert icone("", 24, root) is not None
        assert icone("🔥", 24, root) is not None
        for n in range(500):
            assert icone(f"Servico de teste {n}", 24, root) is not None

        linha = ttk.Frame(root)
        campo_grade = ttk.Entry(linha)
        preview_grade = ttk.Label(linha)
        campo_grade.grid(row=0, column=0)
        preview_grade.grid(row=0, column=1)
        auto_grade = AutocompletarMarcas(campo_grade, preview_grade, lista)
        assert preview_grade.winfo_manager() == ""
        campo_grade.insert(0, "nu")
        auto_grade.atualizar()
        assert preview_grade.winfo_manager() == "grid"
        assert preview_grade.cget("image")
    finally:
        root.destroy()
    print("OK: normalização, sugestões, seleção, cache e 500 ícones")


def janela_visual():
    root = tk.Tk()
    root.title("Teste offline de ícones e autocomplete")
    root.geometry("440x420")
    ttk.Label(root, text="Digite: nu, ban, net ou pad").pack(anchor="w", padx=12, pady=(12, 4))
    linha = ttk.Frame(root)
    linha.pack(fill="x", padx=12)
    linha.columnconfigure(0, weight=1)
    campo = ttk.Entry(linha)
    campo.grid(row=0, column=0, sticky="ew")
    preview = ttk.Label(linha)
    preview.grid(row=0, column=1, padx=(8, 0))
    lista = tk.Frame(root, bg="#202430", highlightthickness=1, highlightbackground="#394052")
    lista.pack(fill="x", padx=12, pady=(4, 0))
    AutocompletarMarcas(campo, preview, lista)
    ttk.Label(root, text="Padaria mostra o ícone de reserva; selecione uma sugestão para preencher.",
              wraplength=410).pack(anchor="w", padx=12, pady=12)
    campo.focus_set()
    root.mainloop()


if __name__ == "__main__":
    if "--visual" in sys.argv:
        janela_visual()
    else:
        verificar()
