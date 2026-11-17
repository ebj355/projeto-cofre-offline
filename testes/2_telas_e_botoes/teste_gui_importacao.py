"""Importar planilha pela interface: itens entram no cofre, a planilha é apagada depois, o aviso de itens que precisam de atenção."""
import os as _os, sys as _sys, tempfile as _tf, subprocess as _sp
_RAIZ = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".."))
def _foto(arq):
    """Captura a tela (só onde existe o ImageMagick 'import'); sem ele, ignora."""
    try: _sp.run(["import", "-window", "root", arq], check=False)
    except Exception: pass
import os, sys, subprocess
sys.path.insert(0, _RAIZ)
import tkinter as tk, openpyxl, cofre_senhas as c
from tkinter import messagebox
W = _tf.mkdtemp(prefix="cofre_gui_"); P = os.path.join(W, "g.dat")
if os.path.exists(P): os.remove(P)
wb = openpyxl.Workbook(); ws = wb.active
ws.append(["Serviço", "Login", "Senha", "PIN", "Notas"])
ws.append(["Banco do Brasil", "joao.silva", "S3nh@Forte!", "1234", "conta salário"])
ws.append(["Gmail", "joao@gmail.com", "novasenha", "", ""])
ws.append(["Netflix", "familia", "net#2026", "", "plano premium"])
wb.save(os.path.join(W, "imp.xlsx"))
root = tk.Tk(); app = c.App(root, P)
app.cofre = c.Cofre.criar(P, "cavalo azul come pizza na chuva", 3, 0, "alto")
app.cofre.registros.append({"id": "1", "servico": "Gmail", "login": "joao@gmail.com", "senha": "antiga", "pin": "", "notas": ""})
app.tela_principal()
c.filedialog.askopenfilename = lambda **k: os.path.join(W, "imp.xlsx")
respostas = []
messagebox.askyesno = lambda *a, **k: (respostas.append(a[0]), True)[1]
messagebox.showinfo = lambda *a, **k: respostas.append(a[0])
def fluxo():
    d = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)][-1]
    root.update(); _foto(os.path.join(W, "previa.png"))
    def achar(w, txt):
        for ch in w.winfo_children():
            if ch.winfo_class() in ("TButton", "TCheckbutton") and ch.cget("text").startswith(txt): return ch
            r = achar(ch, txt)
            if r: return r
    achar(d, "Atualizar").invoke()
    achar(d, "Importar").invoke()
root.after(500, lambda: (root.after(800, fluxo), app.importar()))
def fim():
    print("itens no cofre:", sorted((r["servico"], r["senha"]) for r in app.cofre.registros))
    print("planilha apagada:", not os.path.exists(os.path.join(W, "imp.xlsx")))
    print("dialogos:", respostas)
    print("status:", app.status.cget("text"))
    reab = c.Cofre.abrir(P, senha="cavalo azul come pizza na chuva")
    print("reaberto:", len(reab.registros), "itens")
    root.destroy()
root.after(4000, fim)
root.mainloop()
