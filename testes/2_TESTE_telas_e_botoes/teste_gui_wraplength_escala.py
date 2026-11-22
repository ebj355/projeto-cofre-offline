# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Teste estatico (nao abre janela): todo wraplength numerico deve passar por _px().

Um wraplength escrito como numero puro (ex.: wraplength=440) nao acompanha a escala do Windows (125%, 150%, 200%):
o texto quebra cedo demais e a tela fica torta. A forma certa e wraplength=_px(440), ou uma variavel/expressao
ja escalada. Para um caso realmente fixo, escreva o comentario  # wraplength-fixo-ok  na mesma linha.
"""
import ast
import os
import sys


def achar_programa():
    pasta = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        cand = os.path.join(pasta, "cofre_senhas.py")
        if os.path.isfile(cand):
            return cand
        pasta = os.path.dirname(pasta)
    return None


def main():
    caminho = sys.argv[1] if len(sys.argv) > 1 else achar_programa()
    if not caminho or not os.path.isfile(caminho):
        print("[PULADO] cofre_senhas.py nao encontrado")
        return 0
    with open(caminho, encoding="utf-8") as f:
        texto = f.read()
    linhas = texto.splitlines()
    falhas = []
    for no in ast.walk(ast.parse(texto)):
        if not isinstance(no, ast.Call):
            continue
        for kw in no.keywords:
            if kw.arg != "wraplength":
                continue
            v = kw.value
            if isinstance(v, ast.Constant) and isinstance(v.value, (int, float)) and v.value:
                if "wraplength-fixo-ok" not in linhas[v.lineno - 1]:
                    falhas.append(f"linha {v.lineno}: wraplength={v.value} sem _px()")
    if falhas:
        print("[FALHOU] wraplength fixo (nao acompanha a escala da tela):")
        for x in falhas:
            print("   ", x)
        return 1
    print("[OK] todo wraplength numerico passa por _px()")
    return 0


if __name__ == "__main__":
    sys.exit(main())
