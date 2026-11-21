# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Interface (Tk): ícone de Caps Lock dentro do campo de senha e mensagens do FIDO com o próximo passo.
Roda no Windows ou no Linux (xvfb-run -a)."""
import os, sys, tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
import tkinter as tk
import cofre_senhas as c
f = []
def ok(cond, nome):
    """Registra uma verificação."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))

root = tk.Tk(); root.geometry("500x300")
app = c.App(root, os.path.join(tempfile.mkdtemp(), "x.dat"))
raiz = app.frame
fr, e = app._linha_secreta(raiz, 30)
fr.pack(); root.update()
icone = [w for w in e.winfo_children() if "Caps" in str(w.cget("text"))]
ok(len(icone) == 1, "ícone de Caps Lock existe dentro do campo")
ic = icone[0]
app._caps_ligado = staticmethod(lambda ev=None: True)
e.focus_force(); e.event_generate("<KeyPress-a>"); root.update()
ok(ic.winfo_manager() == "place" and ic.winfo_ismapped(), "Caps ligado: ícone aparece dentro do campo")
ok(ic.winfo_x() + ic.winfo_width() <= e.winfo_width() + 1, "ícone fica dentro dos limites do campo")
app._caps_ligado = staticmethod(lambda ev=None: False)
e.event_generate("<KeyRelease-a>"); root.update()
ok(not ic.winfo_ismapped(), "Caps desligado: ícone some")

# mensagens FIDO: dizem o que fazer e não começam com código técnico
from fido2.client import ClientError
def erro(cod, causa=""):
    """Monta um ClientError como o do Windows."""
    return ClientError(getattr(ClientError.ERR, cod), causa)
m = c._msg_fido(erro("TIMEOUT")); ok("Toque" in m and "piscar" in m, "tempo esgotado: manda tocar na chave")
m = c._msg_fido(erro("OTHER_ERROR", "NTE_USER_CANCELLED cancelled 0x800704c7")); ok("cancelou" in m.lower(), "cancelado: mensagem amiga")
m = c._msg_fido(erro("OTHER_ERROR", "PIN is incorrect")); ok("PIN" in m and "certo" in m, "PIN errado: manda digitar o PIN certo")
m = c._msg_fido(erro("DEVICE_INELIGIBLE")); ok("chave certa" in m, "chave não cadastrada: manda usar a certa")
m = c._msg_fido(RuntimeError("boom")); ok("Encaixe" in m and not m.startswith("Erro"), "erro genérico: orienta encaixar a chave")
root.destroy()
print("FALHAS:", f.count(False)); sys.exit(1 if False in f else 0)
