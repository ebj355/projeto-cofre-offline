"""Interface: checagem de vazamentos (rede simulada) e janela do bloqueio automático configurável."""
import os as _os, sys as _sys, tempfile as _tf
_RAIZ = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".."))
import faulthandler; faulthandler.dump_traceback_later(90, exit=True)
import os, sys, time
sys.path.insert(0, _RAIZ)
import tkinter as tk
from tkinter import ttk, messagebox
import cofre_senhas as c
f = []
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
W = _tf.mkdtemp(prefix="cofre_gui_"); P = os.path.join(W, "s.dat")
SENHA = "cavalo azul come pizza na chuva"
v = c.Cofre.criar(P, SENHA, 5, c.MODO_OU, "alto")
v.registros.append(c.novo_item(servico="Banco", senha="password"))
v.registros.append(c.novo_item(servico="Email", senha="Zq8#unica-e-longa-77"))
v.salvar(); v.fechar()
log = []
messagebox.askyesno = lambda *a, **k: (log.append(("pergunta", a[0])) or True)
messagebox.showinfo = lambda *a, **k: log.append(("info", a[0]))
messagebox.showwarning = lambda *a, **k: log.append(("aviso", a[0]))
messagebox.showerror = lambda *a, **k: log.append(("erro", a[0]))
pedidos_rede = []
def rede_falsa(prefixo, timeout=15):
    pedidos_rede.append(prefixo)
    return ("1E4C9B93F3F0682250B6CF8331B7EE68FD8:10434004\r\n" if prefixo == "5BAA6" else "") + "0000000000000000000000000000000000A:0\r\n"
c._hibp_baixar = rede_falsa
root = tk.Tk(); app = c.App(root, P)
app.cofre = c.Cofre.abrir(P, senha=SENHA); app.tela_principal(); root.update()

def filhos(w):
    for ch in w.winfo_children():
        yield ch
        yield from filhos(ch)
def topos(): return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
def esperar(cond, seg=15):
    t = time.time()
    while time.time() - t < seg:
        root.update()
        if cond(): return True
        time.sleep(0.05)
    return False

# --- checagem de vazamentos
app.checar_vazamentos(); root.update()
ok(any(x[0] == "pergunta" and "internet" in x[1].lower() or "Checar vazamentos" in x[1] for x in log), "pede confirmação antes de usar a rede")
d = topos()[-1]
ok(esperar(lambda: any(isinstance(w, ttk.Treeview) for w in filhos(d))), "resultado aparece")
tv = next(w for w in filhos(d) if isinstance(w, ttk.Treeview))
linhas = [tv.item(i)["values"] for i in tv.get_children()]
ok(len(linhas) == 1 and linhas[0][0] == "Banco" and "10.434.004" in str(linhas[0][2]), "só a senha vazada aparece: %s" % linhas)
ok(all(len(p) == 5 for p in pedidos_rede) and "5BAA6" in pedidos_rede, "só prefixos de 5 caracteres saíram: %s" % pedidos_rede)
d.destroy(); root.update()

# --- erro de rede não quebra nada
def rede_ruim(prefixo, timeout=15): raise OSError("sem internet")
c._hibp_baixar = rede_ruim
app.checar_vazamentos(); root.update(); d = topos()[-1]
ok(esperar(lambda: any("Não foi possível" in str(w.cget("text")) for w in filhos(d) if w.winfo_class() == "TLabel")), "sem internet: avisa e não quebra")
d.destroy(); root.update()

# --- bloqueio automático configurável
ok(app._inatividade_ms() == 180000, "padrão: 3 min")
app.configurar_bloqueio(); root.update(); d = topos()[-1]
cb = next(w for w in filhos(d) if isinstance(w, ttk.Combobox))
ok("10" in cb.cget("values") and cb.get() == "3", "lista de tempos e valor atual (%s)" % cb.get())
cb.set("10")
bt = next(w for w in filhos(d) if w.winfo_class() == "TButton" and str(w.cget("text")) == "Salvar")
bt.invoke(); root.update()
ok(app.cofre.meta.get("bloqueio_min") == 10 and app._inatividade_ms() == 600000, "10 min gravado no cofre")
ok(app._timer_bloqueio is not None, "relógio de inatividade rearmado")
app.cofre.fechar()
v2 = c.Cofre.abrir(P, senha=SENHA)
ok(v2.meta.get("bloqueio_min") == 10, "continua 10 min depois de salvar e reabrir")
v2.fechar()
root.destroy()
print("FALHAS:", [i for i, x in enumerate(f) if not x])
