# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Limpeza ao bloquear: depois de bloquear não sobra lista, barra lateral, hash do detalhe com segredo nem campos revelados na memória."""
import os as _os, sys as _sys, tempfile as _tf, subprocess as _sp
_RAIZ = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".."))
def _foto(arq):
    """Captura a tela (só onde existe o ImageMagick 'import'); sem ele, ignora."""
    try: _sp.run(["import", "-window", "root", arq], check=False)
    except Exception: pass
import os, sys, gc, time, tempfile
sys.path.insert(0, _RAIZ)
import tkinter as tk
from tkinter import messagebox
import cofre_senhas as c
FAL = []
def ok(cond, msg):
    print(("  [OK]   " if cond else "  [FALHOU] ") + msg)
    if not cond: FAL.append(msg)
msgs = []
for n in ("showinfo", "showwarning", "showerror"):
    setattr(messagebox, n, lambda *a, _n=n, **k: msgs.append((_n, a[:2])))
perguntas = []
messagebox.askyesno = lambda *a, **k: (perguntas.append(a[:2]), True)[1]
S = "cavalo azul come pizza na chuva"
d = tempfile.mkdtemp(); P = os.path.join(d, "g.dat")
c.Cofre.criar(P, S, 3, c.MODO_OU, "alto")
root = tk.Tk(); app = c.App(root, P)
app.cofre = c.Cofre.abrir(P, senha=S)
ISCA = "Isca-" + os.urandom(6).hex() + "-Zq9!"
reg = c.novo_item(servico="Banco Isca", login="isca@x.com", senha=ISCA, pin="4821", codigos="CODIGO-" + ISCA)
app.cofre.registros.append(reg)
app.tela_principal(); root.update()
app.tree.selection_set(reg["id"]); root.update(); app._montar_detalhe(); root.update()
app._alternar_revelar("senha"); root.update()
ok(app._detalhe_chave is not None and not isinstance(app._detalhe_chave, tuple), "chave do detalhe é só um hash")
ok(ISCA.encode() not in app._detalhe_chave, "hash do detalhe não contém o segredo")
app.bloquear(); root.update(); gc.collect()
ok(not hasattr(app, "tree") or app.tree is None, "tree solto ao bloquear")
ok(not hasattr(app, "lateral") or app.lateral is None, "lateral solto ao bloquear")
ok(getattr(app, "_detalhe_chave", None) is None, "_detalhe_chave limpo")
ok(not app._revelados, "campos revelados esvaziados")
ok(not getattr(app, "_timers_revelar", {}), "timers de revelar cancelados")
ok(app.cofre is None, "cofre fechado")
# refs ao objeto-isca: a str da senha só pode ser referenciada pelo dict `reg` (ainda segurado aqui) e por este teste
senha_obj = reg["senha"]
refs = [r for r in gc.get_referrers(senha_obj) if r is not reg and not (isinstance(r, dict) and r.get("__name__") == "__main__") and type(r).__name__ != "frame"]
print("   referências restantes:", [type(r).__name__ for r in refs])
ok(len(refs) == 0, "nenhum outro objeto do programa aponta para a senha após bloquear")
# 1.4 clipboard recusa no Windows quando a cópia segura falha
c.EH_WINDOWS = True
c.copiar_seguro_windows = lambda v, d=None: False
c.historico_clipboard_ligado = lambda: True
app.cofre = c.Cofre.abrir(P, senha=S); app.tela_principal(); root.update()
root.clipboard_clear(); root.clipboard_append("nada")
txt = app._copiar_texto("SENHA-SECRETA", "Senha")[1]
ok("NÃO copiado" in txt and root.clipboard_get() == "nada", "se a cópia protegida falha e o histórico Win+V está ligado, recusa")
c.historico_clipboard_ligado = lambda: False
okc, txt2 = app._copiar_texto("SENHA-SECRETA", "Senha")
ok(okc and root.clipboard_get() == "SENHA-SECRETA" and "histórico Win+V está desligado" in txt2,
   "protegida falhou mas o histórico está desligado: copia pelo Tk e avisa (o botão copiar nunca fica mudo)")
root.clipboard_clear(); root.clipboard_append("nada")
c.historico_clipboard_ligado = lambda: True
reg3 = c.novo_item(servico="Loja Teste", login="l@x", senha="SenhaLoja#9")
app.cofre.registros.append(reg3); app.atualizar_lista(); root.update()
app.tree.selection_set(reg3["id"]); root.update()
ok(app.copiar("senha") is False and "NÃO copiado" in app.status.cget("text"), "copiar() recusado devolve False e a barra avisa")
from tkinter import ttk
ent = ttk.Entry(root); ent.insert(0, "segredo"); bt = ttk.Button(root, text="Copiar"); bt.pack()
app._copiar_campo(ent, bt, "Senha"); root.update()
ok(bt.cget("text") == "Copiar", "botão NÃO vira 'Copiado' quando a cópia foi recusada")
app._busca_antes = app.busca.get()
app.busca.set("termo-secreto"); root.update()
c.EH_WINDOWS = False
# aviso de bloqueio
app.INATIVIDADE_MS = 3000; app.AVISO_BLOQUEIO_MS = 2000
app._atividade(); t0 = time.time()
vi = False
while time.time() - t0 < 1.8:
    root.update(); time.sleep(0.02)
    j = getattr(app, "_janela_av_bloq", None)
    if j is not None and j.winfo_exists(): vi = True
ok(vi, "aviso 'Bloqueando em N s' aparece antes do bloqueio")
app._atividade(); root.update()
ok(getattr(app, "_janela_av_bloq", None) is None, "atividade fecha o aviso")
t0 = time.time()
while time.time() - t0 < 3.6 and app.cofre is not None:
    root.update(); time.sleep(0.02)
ok(app.cofre is None, "sem atividade o cofre bloqueia depois do aviso")
ok(not hasattr(app, "lateral_pessoas") and not hasattr(app, "busca"), "lateral_pessoas e busca soltos ao bloquear")
ok(app._selecionado() is None, "_selecionado() depois de bloquear devolve None (sem AttributeError)")
# diálogo destrutivo: Enter = Não
res = {}
def enter(titulo):
    for w in root.winfo_children():
        if isinstance(w, tk.Toplevel) and w.winfo_viewable() and w.title() == titulo:
            print("   enviando Return a", titulo, w.focus_get(), flush=True); w.focus_force(); w.event_generate("<Return>"); return
    if time.time() % 5 < 0.06: print("   procurando", titulo, [(w.title(), w.winfo_viewable(), w.winfo_ismapped()) for w in root.winfo_children() if isinstance(w, tk.Toplevel)], flush=True)
    root.after(50, lambda: enter(titulo))
root.after(300, lambda: enter("Excluir"))
messagebox.askyesno = c.__dict__["_MB_ORIGINAIS"].get("askyesno")  # restaura caixa original p/ instalar a do tema
c.instalar_caixas_de_mensagem()
r = messagebox.askyesno("Excluir", "Excluir 'X'?\n\nEsta ação não pode ser desfeita.")
ok(r is False, "Enter na confirmação de exclusão escolhe NÃO")
root.after(300, lambda: enter("Salvar"))
r = messagebox.askyesno("Salvar", "Salvar o arquivo agora?")
ok(r is True, "Enter em pergunta comum continua escolhendo Sim")
print("\nFALHAS:", FAL)
sys.exit(1 if FAL else 0)
