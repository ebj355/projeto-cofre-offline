"""Botões 'Copiar' do painel do item e do formulário de edição: copiam o valor certo, mostram 'Copiado', limpam a área de transferência e voltam ao normal."""
import os as _os, sys as _sys, tempfile as _tf, subprocess as _sp
_RAIZ = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".."))
def _foto(arq):
    """Captura a tela (só onde existe o ImageMagick 'import'); sem ele, ignora."""
    try: _sp.run(["import", "-window", "root", arq], check=False)
    except Exception: pass
import os, sys, subprocess, time
sys.path.insert(0, _RAIZ)
import tkinter as tk, cofre_senhas as c
f = []
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
W = _tf.mkdtemp(prefix="cofre_gui_"); P = os.path.join(W, "c.dat")
if os.path.exists(P): os.remove(P)
c.Cofre.criar(P, "cavalo azul come pizza na chuva", 3, c.MODO_OU, "alto")
root = tk.Tk(); app = c.App(root, P)
app.cofre = c.Cofre.abrir(P, senha="cavalo azul come pizza na chuva")
app.cofre.registros.append(c.novo_item(servico="Banco do Brasil", login="joao", senha="S3nha-Do-Banco!", pin="8410"))
app.tela_principal(); root.update(); app.tree.selection_set(app.cofre.registros[0]["id"]); root.update()
def todos(w, cls):
    r = []
    for ch in w.winfo_children():
        if ch.winfo_class() == cls: r.append(ch)
        r += todos(ch, cls)
    return r
bts = [b for b in todos(app.detalhe, "TButton") if str(b.cget("text")).strip() == "Copiar"]
ok(len(bts) == 3, f"painel: botão 'Copiar' com texto em login, senha e PIN ({len(bts)})")
bts[1].invoke(); root.update()
ok(root.clipboard_get() == "S3nha-Do-Banco!", "copiar a senha pelo painel funciona")
ok("Copiado" in bts[1].cget("text"), "botão mostra 'Copiado'")
ok("Ctrl+V" in app.status.cget("text") and "15 s" in app.status.cget("text"), "status: " + app.status.cget("text"))
_foto(os.path.join(W, "painel.png"))
root.after(2300, lambda: None); t0 = time.time()
while time.time() - t0 < 2.4: root.update(); time.sleep(0.02)
ok(bts[1].cget("text").strip() == "Copiar", "volta a 'Copiar' depois de 2 s")
root.clipboard_clear()
def no_form():
    d = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)][0]
    bs = [b for b in todos(d, "TButton") if b.cget("text") == "Copiar"]
    ok(len(bs) == 6, f"formulário: copiar em senha, senha extra, PIN, chave, nº da conta e agência ({len(bs)})")
    bs[0].invoke(); root.update()
    ok(root.clipboard_get() == "S3nha-Do-Banco!", "copiar pelo formulário funciona")
    root.update(); _foto(os.path.join(W, "form.png"))
    d.destroy()
root.after(600, no_form)
app.editar()
t0 = time.time()
while time.time() - t0 < 1.5: root.update(); time.sleep(0.02)
print("\nTODOS OK" if all(f) else "\nHOUVE FALHAS")
root.destroy()
