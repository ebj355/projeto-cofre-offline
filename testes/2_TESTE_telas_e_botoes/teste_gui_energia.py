# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Suspender o PC / bloquear a sessão (Win+L): apaga as chaves da memória e bloqueia; trocar a senha mestra pela tela e a chave de acesso nova."""
import os as _os, sys as _sys, tempfile as _tf, subprocess as _sp
_RAIZ = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".."))
def _foto(arq):
    """Captura a tela (só onde existe o ImageMagick 'import'); sem ele, ignora."""
    try: _sp.run(["import", "-window", "root", arq], check=False)
    except Exception: pass
import sys, os, tkinter as tk, tempfile
sys.path.insert(0, _RAIZ); import cofre_senhas as c
from tkinter import messagebox
messagebox.showinfo=messagebox.showwarning=messagebox.showerror=lambda *a,**k:None; messagebox.askyesno=lambda *a,**k:True
d=tempfile.mkdtemp(); P=os.path.join(d,"cofre.dat"); S="cavalo azul come pizza na chuva"
c.Cofre.criar(P,S,3,0,"alto").salvar()
root=tk.Tk(); app=c.App(root,P); app.cofre=c.Cofre.abrir(P,senha=S); app.tela_principal(); root.update()
dek=app.cofre.dek
app._ao_perigo(); root.update()
print("OK" if app.cofre is None else "FALHOU", "suspender/Win+L apaga as chaves e bloqueia")
# trocar senha pela tela (OU, aberto por senha, sem chave -> gera chave nova)
app.cofre=c.Cofre.abrir(P,senha=S); app.tela_principal(); root.update()
seq=iter(["","nova senha mestra bem longa 2026!","nova senha mestra bem longa 2026!"])
app._pedir_senha=lambda *a,**k: next(seq)
app._confirmar_senha_atual=lambda t: S
mostradas=[]; app.mostrar_chave_acesso=lambda k,m=0: mostradas.append(k)
app.trocar_senha(); root.update()
print("OK" if mostradas and c.Cofre.abrir(P,chave=mostradas[0]) else "FALHOU","trocar senha pela tela (sem chave em mãos) mostra chave nova que abre")
print("OK" if c.Cofre.abrir(P,senha="nova senha mestra bem longa 2026!") else "FALHOU","senha nova abre")
app.cofre=c.Cofre.abrir(P,senha="nova senha mestra bem longa 2026!")
app.nova_chave(); root.update()
print("OK" if len(mostradas)==2 and c.Cofre.abrir(P,chave=mostradas[1]) else "FALHOU","nova chave pela tela")
root.destroy()
