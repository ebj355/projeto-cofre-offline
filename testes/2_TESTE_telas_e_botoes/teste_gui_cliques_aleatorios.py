# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""'Teste do macaco': 700 ações ALEATÓRIAS (cliques, teclas, abas, busca, bloquear, redimensionar) para achar travadas; confere erros, memória, widgets e que o cofre continua íntegro."""
import os as _os, sys as _sys, tempfile as _tf, subprocess as _sp
_RAIZ = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".."))
_TESTES = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "6_TESTE_ferramentas_dos_testes")   # testes/6_TESTE_ferramentas_dos_testes/ (para achar _util_mem)
def _foto(arq):
    """Captura a tela (só onde existe o ImageMagick 'import'); sem ele, ignora."""
    try: _sp.run(["import", "-window", "root", arq], check=False)
    except Exception: pass
import os, sys, time, traceback, faulthandler, random, gc
faulthandler.dump_traceback_later(420, exit=True)
sys.path.insert(0, _RAIZ)
sys.path.insert(0, _TESTES)
from _util_mem import pico_kb   # pico de memória: resource (Linux/macOS) não existe no Windows, _util_mem cobre os dois
import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import cofre_senhas as c
W = _tf.mkdtemp(prefix="cofre_gui_"); P = os.path.join(W, "m.dat")
for f in os.listdir(W):
    if f.startswith("m.dat"): os.remove(os.path.join(W,f))
SENHA = "cavalo azul come pizza na chuva"
v = c.Cofre.criar(P, SENHA, 5, c.MODO_OU, "alto")
for i in range(60):
    v.registros.append(c.novo_item(servico=f"Conta {i}", login=f"u{i}@x.com", senha=f"Senha-Forte-{i}!", grupo=["Bancos","E-mail","pai"][i%3], notas="a\nb", pessoa=["", "Pai", "Mãe"][i%3]))
v.salvar()
erros=[]
for nome in ("showerror","showwarning","showinfo"): setattr(messagebox,nome,lambda *a,_n=nome,**k: erros.append((_n,str(a[:2]))) if (_n=="showerror" and not str(a[1:2]).startswith("('Informe")) else None)
messagebox.askyesno=lambda *a,**k: True
messagebox.askokcancel=lambda *a,**k: True
tk.Misc.wait_window=lambda self,w=None: self.update()
filedialog.asksaveasfilename=lambda *a,**k: os.path.join(W,"m_saida")
filedialog.askopenfilename=lambda *a,**k: ""
filedialog.askdirectory=lambda *a,**k: ""
root=tk.Tk(); root.geometry("1280x720")
root.report_callback_exception=lambda t,v_,tb: erros.append(("TK","".join(traceback.format_exception(t,v_,tb))[-600:]))
app=c.App(root,P)
c.escolher_impressora=lambda *a,**k: None
c.copiar_seguro_windows=lambda *a,**k: False
rnd=random.Random(7)
PERIGOSOS=("Sair","Excluir","Apagar","Destruir","Backup","Importar","Imprimir","Modelo","Desativar","Remover","Restaurar")
def abrir():
    app.cofre=c.Cofre.abrir(P,senha=SENHA); app.tela_principal(); root.update()
def widgets(w,acc):
    for ch in w.winfo_children():
        acc.append(ch); widgets(ch,acc)
    return acc
n_win=0; tempos=[]
abrir(); t_ini=time.time()
for passo in range(700):
    if app.cofre is None:
        try: abrir()
        except Exception as e: erros.append(("ABRIR",repr(e)[:200])); break
    ws=widgets(root,[])
    acao=rnd.choice(["btn","btn","btn","key","tab","lista","busca","bloq","dlgfechar","revelar","foco","resize"])
    try:
        if acao=="btn":
            bs=[w for w in ws if w.winfo_class() in ("TButton","Button") and w.winfo_ismapped()]
            bs=[b for b in bs if not any(p in str(b.cget("text")) for p in PERIGOSOS)]
            if bs: rnd.choice(bs).invoke()
        elif acao=="key":
            alvo=rnd.choice([w for w in ws if w.winfo_class() in ("TEntry","Entry","Text","Treeview")] or [root])
            for k in rnd.sample(["<Control-f>","<Control-n>","<Escape>","<Return>","<Tab>","<Down>","<Up>","<Control-a>","<Control-g>","<Delete>"],3):
                if k=="<Delete>": continue
                alvo.event_generate(k)
        elif acao=="tab":
            nb=[w for w in ws if w.winfo_class()=="TNotebook"]
            if nb:
                n=rnd.choice(nb); n.select(rnd.randrange(len(n.tabs())))
        elif acao=="lista":
            if getattr(app,"tree",None) is not None and app.tree.winfo_exists():
                f=app.tree.get_children()
                if f: app.tree.selection_set(rnd.choice(f))
        elif acao=="busca":
            if getattr(app,"campo_busca",None) is not None:
                app.campo_busca.delete(0,"end"); app.campo_busca.insert(0,rnd.choice(["a","conta 1","zzz","","Pai"]))
        elif acao=="bloq":
            if rnd.random()<0.35: app.bloquear()
        elif acao=="dlgfechar":
            for w in list(root.winfo_children()):
                if isinstance(w,tk.Toplevel): w.destroy()
        elif acao=="revelar":
            for campo in ("senha","login"):
                try: app._alternar_revelar(campo)
                except Exception as e: raise
        elif acao=="foco":
            app._talvez_ocultar(); root.update(); app._mostrar_conteudo()
        elif acao=="resize":
            root.geometry(f"{rnd.choice([900,1280,1600])}x{rnd.choice([600,720,900])}")
        root.update()
    except tk.TclError as e:
        if "invalid command" not in str(e) and "bad window path" not in str(e): erros.append(("TCL "+acao,str(e)[:200]))
    except Exception:
        erros.append(("EXC "+acao,traceback.format_exc()[-500:]))
# 40 ciclos bloquear/desbloquear
tops0=len([w for w in root.winfo_children() if isinstance(w,tk.Toplevel)])
for i in range(40):
    if app.cofre is None: abrir()
    app.bloquear(); root.update()
gc.collect(); pico=pico_kb()/1024
nw=len(widgets(root,[]))
print(f"widgets vivos no fim: {nw} | pico de memória: {pico:.0f} MB | tempo: {time.time()-t_ini:.0f}s")
print("ERROS:",len(erros))
for e in erros[:15]: print("  >>",e[0],e[1][:400])
# arquivo íntegro no fim
try:
    w=c.Cofre.abrir(P,senha=SENHA); print("cofre íntegro:",len(w.registros),"itens")
except Exception as e: print("COFRE QUEBRADO",repr(e))
print("FALHOU" if erros or nw>600 else "TODOS OK")
