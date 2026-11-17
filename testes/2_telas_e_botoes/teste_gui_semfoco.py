"""Teste de interface: fora do programa por 60 s bloqueia e apaga as chaves; voltar antes disso não bloqueia."""
import os as _os, sys, tkinter as tk, tempfile, time
_RAIZ = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, _RAIZ); import cofre_senhas as c
from tkinter import messagebox
messagebox.showinfo=messagebox.showwarning=messagebox.showerror=lambda *a,**k:None; messagebox.askyesno=lambda *a,**k:True
d=tempfile.mkdtemp(); P=_os.path.join(d,"cofre.dat"); S="cavalo azul come pizza na chuva"
c.Cofre.criar(P,S,3,0,"alto").salvar()
root=tk.Tk(); app=c.App(root,P); app.cofre=c.Cofre.abrir(P,senha=S); app.tela_principal(); root.update()
fora=[True]; app._app_sem_foco=lambda: fora[0]
relogio=[time.time()]; real=time.time
c.time.time=lambda: relogio[0]
app._ultimo_tique=relogio[0]
def passo(seg):
    relogio[0]+=seg; app._ultimo_tique=relogio[0]-1     # relógio contínuo (não é "PC dormiu")
    app._vigiar_sistema(); root.update()
passo(1); passo(30)
print("OK" if app.cofre is not None else "FALHOU","30 s fora do programa: ainda aberto")
fora[0]=False; passo(2)
print("OK" if app._sem_foco_desde is None else "FALHOU","voltou ao programa: contagem zerada")
fora[0]=True; passo(1); passo(40); passo(15)
print("OK" if app.cofre is not None else "FALHOU","55 s no total após voltar: ainda aberto (a contagem recomeçou)")
passo(10)
print("OK" if app.cofre is None else "FALHOU",">=60 s fora do programa: bloqueou e apagou as chaves")
c.time.time=real
root.destroy()
