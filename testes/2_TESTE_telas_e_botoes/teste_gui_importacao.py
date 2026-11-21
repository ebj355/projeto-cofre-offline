# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
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
PLANILHA = os.path.join(W, "imp.xlsx")
falhas = []
excecoes = []
root = tk.Tk(); app = c.App(root, P)
app.cofre = c.Cofre.criar(P, "cavalo azul come pizza na chuva", 3, 0, "alto")
app.cofre.registros.append({"id": "1", "servico": "Gmail", "login": "joao@gmail.com", "senha": "antiga", "pin": "", "notas": ""})
app.tela_principal()
c.filedialog.asksaveasfilename = lambda **k: PLANILHA
c.filedialog.askopenfilename = lambda **k: PLANILHA
respostas = []
messagebox.askyesno = lambda *a, **k: (respostas.append(a[0]), True)[1]
messagebox.showinfo = lambda *a, **k: respostas.append(a[0])
messagebox.showwarning = lambda *a, **k: respostas.append(a[0])
messagebox.showerror = lambda *a, **k: respostas.append("ERRO: " + (a[0] if a else ""))
root.report_callback_exception = lambda tipo, valor, tb: excecoes.append(repr(valor))

app.modelo_planilha()
wb = openpyxl.load_workbook(PLANILHA)
ws = wb["Senhas"]
linhas = (
    ("Banco do Brasil", "joao.silva", "S3nh@Forte!", "", "1234", "", "rec-01\nrec-02", "conta salário", "Banco", "Eu"),
    ("Gmail", "joao@gmail.com", "novasenha", "", "", "", "", "", "E-mail", "Eu"),
    ("Netflix", "familia", "net#2026", "", "", "", "", "plano premium", "Compras", "Eu"),
)
for n, valores in enumerate(linhas, start=2):
    for coluna, valor in enumerate(valores, start=1):
        ws.cell(row=n, column=coluna, value=valor)
wb.save(PLANILHA)

def ok(condicao, texto):
    print(("  [OK]   " if condicao else "  [FALHOU] ") + texto)
    if not condicao:
        falhas.append(texto)

def fluxo():
    janelas = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
    d = next((w for w in janelas if w.title() == "Conferir importação"), None)
    if d is None:
        falhas.append("a prévia da importação não abriu")
        return
    root.update()
    _foto(os.path.join(W, "previa.png"))
    def achar(w, txt):
        for ch in w.winfo_children():
            if ch.winfo_class() in ("TButton", "TCheckbutton") and ch.cget("text").startswith(txt): return ch
            r = achar(ch, txt)
            if r: return r
    atualizar = achar(d, "Atualizar")
    importar = achar(d, "Importar")
    if atualizar is None or importar is None:
        falhas.append("a prévia não mostrou as ações esperadas de atualizar/importar")
        d.destroy()
        return
    atualizar.invoke()
    importar.invoke()

root.after(500, lambda: (root.after(800, fluxo), app.importar()))
def fim():
    itens = sorted((r["servico"], r["senha"]) for r in app.cofre.registros)
    print("itens no cofre:", itens)
    ok(len(itens) == 3 and ("Banco do Brasil", "S3nh@Forte!") in itens and
       ("Gmail", "novasenha") in itens and ("Netflix", "net#2026") in itens,
       "importou as contas novas e atualizou o conflito")
    apagada = not os.path.exists(PLANILHA)
    print("planilha apagada:", apagada)
    ok(apagada, "planilha original apagada após confirmação")
    print("dialogos:", respostas)
    print("status:", app.status.cget("text"))
    reab = c.Cofre.abrir(P, senha="cavalo azul come pizza na chuva")
    print("reaberto:", len(reab.registros), "itens")
    ok(len(reab.registros) == 3, "itens importados persistem após reabrir o cofre")
    reab.fechar()
    ok(not excecoes, "nenhuma exceção não tratada nos callbacks: %r" % excecoes)
    ok(not any(x.startswith("ERRO:") for x in respostas), "nenhum erro exibido na importação: %r" % respostas)
    app._cancelar_todos_after()
    if app.cofre is not None:
        app.cofre.fechar()
    root.destroy()
    print("\nTODOS OK" if not falhas else "\nFALHAS: %d" % len(falhas))
    _sys.exit(0 if not falhas else 1)

root.after(4000, fim)
root.mainloop()
