"""Interface: dados bancários (número da conta / agência) no formulário de item.
Verifica que os campos aparecem ao marcar as caixas, salvam e sobrevivem a fechar/reabrir o cofre (cifrados),
e que a camada extra de proteção (pedir a senha mestra de novo) vale para itens bancários mesmo com a
'Proteção extra' geral DESLIGADA -- mas não se aplica a um item comum. Roda no Linux com xvfb-run."""
import os, sys, tempfile
_RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, _RAIZ)
import tkinter as tk, cofre_senhas as c
from tkinter import messagebox
f = []
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))

W = tempfile.mkdtemp(prefix="cofre_gui_"); P = os.path.join(W, "b.dat")
SENHA = "cavalo azul come pizza na chuva"
c.Cofre.criar(P, SENHA, 5, c.MODO_OU, "alto")
messagebox.showinfo = lambda *a, **k: None
messagebox.showerror = lambda *a, **k: erros.append(a)
messagebox.askyesno = lambda *a, **k: False
tk.Misc.wait_window = lambda self, window=None: None
erros = []
root = tk.Tk(); root.geometry("1366x768+0+0"); app = c.App(root, P)
app.cofre = c.Cofre.abrir(P, senha=SENHA); app.tela_principal(); root.update()

def todos(w):
    for ch in w.winfo_children():
        yield ch; yield from todos(ch)
def achar(d, txt, cls="TButton"):
    return next((w for w in todos(d) if w.winfo_class() == cls and str(w.cget("text")).startswith(txt)), None)
def topos():
    return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
def novo():
    app.dialogo_registro(None); root.update(); root.update()
    return next(w for w in topos() if w.title() == "Novo item")

# 1) campos aparecem ao marcar as caixas e são do tipo CAMPOS/CAMPOS_SECRETOS esperado
ok("numero_conta" in c.CAMPOS and "agencia" in c.CAMPOS, "numero_conta/agencia estão em CAMPOS")
ok("numero_conta" in c.CAMPOS_SECRETOS and "agencia" in c.CAMPOS_SECRETOS, "numero_conta/agencia são CAMPOS_SECRETOS")

d = novo()
for rot in ("Número da conta", "Agência"):
    cx = achar(d, rot, "TCheckbutton")
    ok(cx is not None, f"existe a caixa '{rot}'")
    cx.invoke(); root.update()
v = " | ".join(str(w.cget("text")) for w in todos(d) if w.winfo_class() == "TLabel" and w.winfo_ismapped())
ok("NÚMERO DA CONTA" in v and "AGÊNCIA" in v, "campos Número da conta / Agência aparecem marcados")

topo_ents = [w for w in todos(d) if w.winfo_class() == "TEntry" and w.winfo_ismapped()]
topo_ents[0].insert(0, "Banco Azul")     # servico
topo_ents[1].insert(0, "123.456-7")      # login
# a grade de segredos tem um rótulo (TLabel) na linha N e o campo (dentro de um Frame) na linha N+1,
# na MESMA coluna e no MESMO pai (grade) -- acha o campo de cada rótulo pela posição no grid, não pelo
# texto (vários campos compartilham o mesmo pai "grade").
def campo_por_rotulo(rot):
    lbl = next(w for w in todos(d) if w.winfo_class() == "TLabel" and str(w.cget("text")) == rot)
    pai = lbl.master
    info = lbl.grid_info()
    lin, col = int(info["row"]), int(info["column"])
    linha_w = next(w for w in pai.winfo_children()
                   if w.grid_info().get("row") == lin + 1 and w.grid_info().get("column") == col)
    return next(w for w in todos(linha_w) if w.winfo_class() == "TEntry")
e_senha = campo_por_rotulo("SENHA")
e_conta = campo_por_rotulo("NÚMERO DA CONTA")
e_agencia = campo_por_rotulo("AGÊNCIA")
e_senha.insert(0, "s3nhaDoBanco!123")
e_conta.insert(0, "00012345-6")
e_agencia.insert(0, "0921")
achar(d, "Salvar").invoke(); root.update()
ok(not erros, "sem erro ao salvar item bancário")
regs = app.cofre.registros
item = next((r for r in regs if r.get("servico") == "Banco Azul"), None)
ok(item is not None, "item bancário foi criado")
ok(item is not None and item.get("numero_conta") == "00012345-6" and item.get("agencia") == "0921",
   "número da conta e agência salvos corretamente")

# 2) persistência: fecha e reabre o cofre do arquivo (passa pela criptografia inteira)
app.cofre.fechar()
v2 = c.Cofre.abrir(P, senha=SENHA)
item2 = next((r for r in v2.registros if r.get("servico") == "Banco Azul"), None)
ok(item2 is not None and item2.get("numero_conta") == "00012345-6" and item2.get("agencia") == "0921"
   and item2.get("senha") == "s3nhaDoBanco!123",
   "dados bancários sobrevivem a fechar/reabrir o cofre (cifrados corretamente)")
app.cofre = v2

# 3) camada extra: proteção global DESLIGADA, mas item bancário sempre pede a senha mestra de novo
ok(app._protecao_global() is False, "proteção extra geral está desligada (padrão)")
ok(app._item_tem_dados_bancarios(item2) is True, "_item_tem_dados_bancarios detecta o item bancário")
antes = len(topos())
liberado = app._liberar_protegido(item2)   # não digita senha (wait_window mockado) -> deve negar
depois_topos = topos()
ok(liberado is False, "item bancário NÃO libera sem confirmar a senha mestra (mesmo com proteção geral desligada)")
ok(len(depois_topos) > antes, "abriu o diálogo pedindo a senha mestra de novo")
for w in depois_topos:
    if w not in (d,):
        try: w.destroy()
        except Exception: pass
root.update()

# item comum (sem dados bancários): não deve pedir nada, já que a proteção geral está desligada
comum = c.novo_item(servico="Email", login="x", senha="y")
app.cofre.registros.append(comum)
ok(app._item_tem_dados_bancarios(comum) is False, "_item_tem_dados_bancarios é falso para item comum")
liberado2 = app._liberar_protegido(comum)
ok(liberado2 is True, "item comum libera direto, sem pedir senha (proteção geral desligada)")

print("PASSOU" if all(f) else "FALHOU", sum(f), "/", len(f))
root.destroy()
sys.exit(0 if all(f) else 1)
