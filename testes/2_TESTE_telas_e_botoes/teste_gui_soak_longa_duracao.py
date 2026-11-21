# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""SOAK TEST DA INTERFACE: ciclos seguidos (padrão 60; 1.000 = cerca de 50 min, use COFRE_SOAK_CICLOS=1000) de desbloquear -> usar -> bloquear com o Tkinter de verdade.

Complementa o teste de 30 ciclos (teste_gui_resiliencia_uso): aqui o uso é MUITO prolongado, para evidenciar o que só
aparece depois de horas - widgets/janelas/imagens que ficam para trás, handles de arquivo e objetos GDI/USER do Windows
(cada janela esquecida custa um pouco), threads de gravação presas, instâncias de Cofre vivas e memória do Python subindo.
A cada ciclo: abre o cofre, mostra a tela principal e bloqueia; a cada 20 abre e fecha o formulário de novo item e a cada 50 salva.
Argon2id fica barato SÓ aqui (o que se mede é o gerenciamento de recursos). Ciclos: variável COFRE_SOAK_CICLOS. O soak de 1.000 ciclos do núcleo (sem janelas) roda no teste_nucleo_soak_longa_duracao."""
import gc, os, sys, threading, time, tracemalloc
_RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, _RAIZ); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "6_TESTE_ferramentas_dos_testes"))
import _resultado; _resultado.registrar(__file__)          # grava resultados/resultado_gui_soak_longa_duracao.txt
import tkinter as tk, cofre_senhas as c
from tkinter import messagebox
f = []
CICLOS = int(os.environ.get("COFRE_SOAK_CICLOS", "60"))     # cada ciclo custa ~3 s (a interface é desenhada em Python puro)
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome, flush=True); f.append(bool(cond))
messagebox.showinfo = messagebox.showwarning = lambda *a, **k: None; messagebox.showerror = lambda *a, **k: None
messagebox.askyesno = lambda *a, **k: False
tk.Misc.wait_window = lambda self, window=None: None
c.NIVEIS["alto"] = (1, 8192)                               # Argon2id barato só neste teste
W = _resultado.pasta_temporaria("cofre_gui_"); P = os.path.join(W, "s.dat"); S = "cavalo azul come pizza na chuva"
c.Cofre.criar(P, S, 50, c.MODO_OU, "alto").salvar()
root = tk.Tk(); root.geometry("1366x768+0+0"); app = c.App(root, P)


def todos(w):
    for ch in w.winfo_children():
        yield ch; yield from todos(ch)
def descritores():
    return _resultado.handles_processo()
def gdi():
    return _resultado.objetos_gdi()
def vivos():
    gc.collect()
    return sum(1 for o in gc.get_objects() if type(o).__name__ == "Cofre")
def medir(i):
    gc.collect(); root.update()
    return (i, len(list(todos(root))), descritores(), gdi(), threading.active_count(), vivos(), tracemalloc.get_traced_memory()[0])

def ciclo(i):
    app.cofre = c.Cofre.abrir(P, senha=S); app.tela_principal(); root.update()
    if i % 20 == 0:                                        # o formulário é caro de desenhar (imagens dos botões): 1 a cada 20
        app.dialogo_registro(None); root.update()
        for w in [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]:
            w.destroy()
    app.cofre.registros.append(c.novo_item(servico="S%d" % i, login="u", senha="x")) if i % 50 == 0 else None
    if i % 50 == 0:
        app.cofre.salvar()
    app.bloquear(); root.update()

tracemalloc.start()
PASSO = max(1, CICLOS // 10)
for i in range(1, 6): ciclo(i)                             # aquecimento (caches de fontes, estilos...)
for _ in range(8):                                          # aquecimento do formulário: as imagens dos botões/medidor entram em cache aos poucos
    app.cofre = c.Cofre.abrir(P, senha=S); app.tela_principal(); root.update()
    app.dialogo_registro(None); root.update()
    for w in [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]:
        w.destroy()
    app.bloquear(); root.update()
amostras = [medir(0)]
t0 = time.time()
for i in range(1, CICLOS + 1):
    ciclo(i)
    if i % PASSO == 0:
        amostras.append(medir(i))
seg = time.time() - t0
print(f"  {CICLOS} ciclos em {seg:.1f}s ({1000 * seg / CICLOS:.0f} ms por ciclo)")
for a in amostras:
    print("  ciclo %4d | widgets %d | descritores %s | GDI/USER %s | threads %d | Cofre vivos %d | memória %.0f KiB" % (
        a[0], a[1], a[2], a[3], a[4], a[5], a[6] / 1024))
ini, fim = amostras[0], amostras[-1]
ok(fim[1] <= ini[1] + 10, f"widgets não crescem: {ini[1]} -> {fim[1]}")
ok(ini[2] is None or fim[2] <= ini[2] + 3, f"descritores de arquivo não crescem: {ini[2]} -> {fim[2]}")
ok(ini[3] is None or fim[3] <= ini[3] + 20, f"objetos GDI/USER não crescem: {ini[3]} -> {fim[3]}")
ok(fim[4] <= ini[4] + 1, f"threads não se acumulam: {ini[4]} -> {fim[4]}")
# cada 50 ciclos entra um item novo no cofre (de propósito); o que não pode sobrar é instância de Cofre viva
ok(fim[5] <= ini[5] + 1, f"instâncias de Cofre vivas não crescem: {ini[5]} -> {fim[5]}")
ok((fim[6] - ini[6]) / 1024 < 2048, f"memória do Python sem crescimento descontrolado: {(fim[6] - ini[6]) / 1024:+.0f} KiB (limite 2048)")
ok(not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)], "nenhuma janela solta no fim")
root.destroy()
print("\nTODOS OK" if all(f) else f"\nFALHAS: {f.count(False)} de {len(f)}")
sys.exit(0 if all(f) else 1)
