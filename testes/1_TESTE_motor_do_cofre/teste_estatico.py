# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Teste estático: nomes não definidos (NameError só apareceria na tela, em tempo de uso) e sintaxe."""
import os, subprocess, sys
f = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "cofre_senhas.py")
compile(open(f, encoding="utf-8").read(), f, "exec")
r = subprocess.run([sys.executable, "-m", "pyflakes", f], capture_output=True, text=True)
if "No module named pyflakes" in r.stderr:
    print("pyflakes ausente (pip install pyflakes): só a sintaxe foi conferida"); sys.exit(0)
ruins = [l for l in r.stdout.splitlines() if "undefined name" in l or "redefinition of unused" in l and "def " in l]
print("FALHAS:", ruins)
