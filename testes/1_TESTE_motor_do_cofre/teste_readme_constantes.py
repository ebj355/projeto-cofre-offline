"""Garante que os números citados no README batem com as constantes do código (documentação que diverge = achado)."""
import os, re, sys
raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, raiz)
import cofre_senhas as c
readme = open(os.path.join(raiz, "documentacao", "MANUAL_COMPLETO.md"), encoding="utf-8").read()
falhas = []
def conf(nome, ok):
    print(f"  [{'OK' if ok else 'FALHOU'}] {nome}")
    if not ok: falhas.append(nome)
App = c.App
conf("README: cópia apagada em 15 s", f"{App.LIMPAR_CLIPBOARD_MS // 1000} segundos" in readme or f"em {App.LIMPAR_CLIPBOARD_MS // 1000} s" in readme)
conf("README: olho esconde em 30 s", f"em {App.MOSTRAR_SENHA_MS // 1000} segundos" in readme)
conf("README: bloqueio por inatividade", f"{App.INATIVIDADE_MS // 60000} minutos sem uso" in readme)
conf("README: tentativas de 1 a 10", "de 1 a 10" in readme)
for ver in re.findall(r"nuitka`? (\d+\.\d+\.\d+)", readme):
    conf(f"README cita Nuitka {ver} = requirements do instalador", ver in open(os.path.join(raiz, "instalar_cofre.ps1"), encoding="utf-8-sig").read())
print("FALHAS:", falhas)
sys.exit(1 if falhas else 0)
