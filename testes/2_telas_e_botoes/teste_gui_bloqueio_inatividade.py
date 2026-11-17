"""BLOQUEIO POR INATIVIDADE: com o relógio curto, o cofre se tranca sozinho, apaga as chaves da memória (o objeto Cofre fica
zerado), derruba as janelas abertas e volta para a tela de desbloqueio; mexer no programa RENOVA o relógio (não bloqueia
em uso); e o relógio é refeito a cada bloqueio/desbloqueio sem empilhar temporizadores. Linux (xvfb-run) e Windows."""
import os, sys, time
_RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, _RAIZ); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ferramentas_dos_testes"))
import _resultado; _resultado.registrar(__file__)
import tkinter as tk, cofre_senhas as c
from tkinter import messagebox
f = []
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome, flush=True); f.append(bool(cond))
messagebox.showinfo = lambda *a, **k: None; messagebox.showerror = lambda *a, **k: None; messagebox.askyesno = lambda *a, **k: False
tk.Misc.wait_window = lambda self, window=None: None
c.NIVEIS["alto"] = (1, 8192)
W = _resultado.pasta_temporaria("cofre_idle_"); P = os.path.join(W, "i.dat"); S = "cavalo azul come pizza na chuva"
v = c.Cofre.criar(P, S, 5, c.MODO_OU, "alto"); v.registros.append(c.novo_item(servico="Banco", login="a", senha="Segredo-Idle-1!")); v.salvar(); v.fechar()
root = tk.Tk(); root.geometry("1100x700+0+0"); app = c.App(root, P)
app._app_sem_foco = lambda: False                          # foco fixo: aqui se testa SÓ o relógio de inatividade
def espera(s):
    t0 = time.time()
    while time.time() - t0 < s:
        app._ultimo_tique = time.time(); root.update(); time.sleep(0.02)       # relógio do vigia "PC dormiu" em dia
def abre():
    app.cofre = c.Cofre.abrir(P, senha=S); app.tela_principal(); root.update(); app._atividade()
app.INATIVIDADE_MS = 1200

print("== 1) sem uso, o cofre se tranca e apaga as chaves")
abre(); cofre = app.cofre
ok(app._timer_bloqueio is not None, "relógio de inatividade armado ao entrar")
app.dialogo_registro(None); root.update(); root.update()
ok(any(isinstance(w, tk.Toplevel) for w in root.winfo_children()), "há um formulário aberto")
espera(2.0)
ok(app.cofre is None, "passou o tempo: o cofre se trancou sozinho")
ok(cofre.dek is None and not cofre.registros and cofre._ks is None, "o objeto Cofre antigo ficou ZERADO (chaves e itens apagados da memória)")
ok(not any(isinstance(w, tk.Toplevel) for w in root.winfo_children()), "as janelas abertas (formulário) foram fechadas")

print("== 2) usar o programa renova o relógio")
abre()
t0 = time.time()
while time.time() - t0 < 2.6:                               # 2,6 s de uso (>1,2 s): mexer a cada ~0,5 s impede o bloqueio
    app._ultimo_tique = time.time(); app._ultima_atividade = 0; app._atividade(); espera(0.5)
ok(app.cofre is not None, "mexendo no programa, o cofre NÃO trancou em 2,6 s (limite 1,2 s)")
espera(2.0)
ok(app.cofre is None, "parou de mexer: trancou")

print("== 3) vários ciclos sem empilhar temporizadores")
for _ in range(5):
    abre(); app.bloquear(); root.update()
ok(app.cofre is None and app._timer_bloqueio is None, "após bloquear à mão não sobra relógio de inatividade pendente")
abre()
n_antes = len(root.tk.call("after", "info"))
for _ in range(10):
    app._ultima_atividade = 0; app._atividade()
ok(len(root.tk.call("after", "info")) <= n_antes + 2, "renovar o relógio 10x não empilha temporizadores")
app.bloquear(); root.update()
print("\nTODOS OK" if all(f) else "\nHOUVE FALHAS")
root.destroy(); sys.exit(0 if all(f) else 1)
