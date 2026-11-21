"""Verifica ícones de marcas; use --visual para abrir uma grade demonstrativa de 40 marcas."""
import os
import sys
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from icones_marcas import MARCAS, _nome_exibicao, achar_marca, icone, normalizar


def verificar():
    assert len(MARCAS) >= 40
    assert normalizar("Nú Bank") == "nubank"
    assert achar_marca("Nubank Pessoal") == "nubank"
    assert achar_marca("Banco do Brasil") == "bancodobrasil"
    root = tk.Tk()
    root.withdraw()
    try:
        imagens = [icone(chave, 48, root) for chave in list(MARCAS)[:40]]
        assert all(imagens)
        assert icone("Nome desconhecido", 24, root) is not None
        assert icone("", 24, root) is not None
        assert icone("🔥", 24, root) is not None
    finally:
        root.destroy()
    print("OK: 40 marcas, nomes acentuados, desconhecido, vazio e emoji")


def janela_visual():
    root = tk.Tk()
    root.title("Ícones locais de marcas — Arca")
    root.geometry("720x640")
    grade = ttk.Frame(root, padding=12)
    grade.pack(fill="both", expand=True)
    for coluna in range(5):
        grade.columnconfigure(coluna, weight=1)
    for indice, chave in enumerate(list(MARCAS)[:40]):
        linha, coluna = divmod(indice, 5)
        celula = ttk.Frame(grade, padding=8)
        celula.grid(row=linha, column=coluna, sticky="nsew", padx=4, pady=4)
        foto = icone(chave, 40, celula)
        etiqueta = ttk.Label(celula, image=foto, text=_nome_exibicao(chave), compound="top")
        etiqueta.image = foto
        etiqueta.pack()
    root.mainloop()


if __name__ == "__main__":
    if "--visual" in sys.argv:
        janela_visual()
    else:
        verificar()
