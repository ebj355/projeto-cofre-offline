# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Velocidade de abertura: importação + tela de desbloqueio em menos de 2,5 s (sem contar o Argon2 de criar o cofre),
e as bibliotecas pesadas (Excel/openpyxl, FIDO) só carregam quando são usadas (lazy)."""
import os, sys, time, tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
f = []
def ok(cond, nome):
    """Registra uma verificação."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
t0 = time.perf_counter()
import tkinter as tk
import cofre_senhas as c
t_imp = time.perf_counter() - t0
P = os.path.join(tempfile.mkdtemp(prefix="ab_"), "t.dat")
c.Cofre.criar(P, "cavalo azul come pizza na chuva", 3, c.MODO_S, "alto").fechar()
melhor = 9.0
for _ in range(3):
    t1 = time.perf_counter()
    root = tk.Tk(); root.geometry("1100x700+0+0")
    app = c.App(root, P); app.mostrar_inicio(); root.update(); root.update()
    melhor = min(melhor, time.perf_counter() - t1)
    app.sair()
print(f"   importar: {t_imp:.2f} s | janela + tela de desbloqueio (melhor de 3): {melhor:.2f} s")
ok(t_imp + melhor < 2.5, f"tela de desbloqueio pronta em {t_imp + melhor:.2f} s (< 2,5 s)")
ok("openpyxl" not in sys.modules and "defusedxml" not in sys.modules, "biblioteca de Excel NÃO é carregada na abertura (carga sob demanda)")
ok("fido2" not in sys.modules, "biblioteca FIDO NÃO é carregada na abertura (carga sob demanda)")
print("FALHAS:", f.count(False)); sys.exit(1 if False in f else 0)
