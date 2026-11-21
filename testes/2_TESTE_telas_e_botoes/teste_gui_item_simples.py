# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Interface: formulário SIMPLES de novo item (nome, grupo, pessoa, usuário, senha), sem botão 'Mais opções'. Para leigos e
idosos: poucos campos, poucos cliques. Roda no Linux com xvfb-run."""
import os, sys, tempfile
_RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, _RAIZ)
import tkinter as tk, cofre_senhas as c
from tkinter import messagebox
f = []
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
W = tempfile.mkdtemp(prefix="cofre_gui_"); P = os.path.join(W, "t.dat"); SENHA = "cavalo azul come pizza na chuva"
c.Cofre.criar(P, SENHA, 5, c.MODO_OU, "alto")
messagebox.showinfo = lambda *a, **k: None; messagebox.showerror = lambda *a, **k: erros.append(a)
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
def novo():
    app.dialogo_registro(None); root.update(); root.update()
    return next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w.title() == "Novo item")
d = novo()
ok(d.winfo_viewable(), "Novo item abre visível")
icones_cabecalho = [w for w in todos(d) if w.winfo_class() == "Canvas" and w.winfo_ismapped()
                    and len(w.find_all()) >= 2]
ok(bool(icones_cabecalho), "Novo item mostra o ícone no cabeçalho")
rotulo_ident = next(w for w in todos(d) if w.winfo_class() == "TLabel"
                    and str(w.cget("text")) == "IDENTIFICAÇÃO E ORGANIZAÇÃO")
ok(str(rotulo_ident.cget("style")) == "C.Campo.TLabel",
   "rótulos de identificação usam o fundo do cartão, sem faixa escura")
rotulo_senha = next(w for w in todos(d) if w.winfo_class() == "TLabel"
                     and str(w.cget("text")) == "SENHA")
ok(str(rotulo_senha.cget("style")) == "S2.Campo.TLabel",
   "rótulos das credenciais usam o fundo do painel")
status = next(w for w in todos(d) if w.winfo_class() == "TButton"
              and str(w.cget("text")) == "Em uso")
ok(status is not None, "estado da conta fica identificado como 'Em uso'")
vis = lambda: [str(w.cget("text")) for w in todos(d) if w.winfo_class() in ("TLabel",) and w.winfo_ismapped()]
v = " | ".join(vis())
ok("CONTA / APP" in v and "LOGIN / E-MAIL / USUÁRIO" in v and "SENHA" in v, "mostra nome, usuário e senha")
ok("GRUPO" in v and "PESSOA" in v, "mostra GRUPO e PESSOA (sem botão de modo)")
for escondido in ("PIN", "SENHA EXTRA"):
    ok(escondido not in v, f"extras escondidos até marcar a caixa: {escondido}")
ok("NOTAS" in v, "notas visíveis como seção própria")
ok(achar(d, "Mais opções") is None and achar(d, "Menos opções") is None, "NÃO existe botão 'Mais/Menos opções'")
ok(achar(d, "Criar uma senha forte") is None, "não há botão extra 'Criar uma senha forte' (o 'Gerar…' do campo basta)")
ok(achar(d, "Copiar") is None, "item novo não tem botões 'Copiar'")
ents = [w for w in todos(d) if w.winfo_class() == "TEntry" and w.winfo_ismapped()]
ok(all(not e.get() for e in ents[:3]), "dicas visuais não são gravadas nos campos vazios")
notas_vazio = next(w for w in todos(d) if w.winfo_class() == "Text" and w.winfo_ismapped())
ok(not notas_vazio.get("1.0", "end-1c").strip(), "dica de notas não é gravada no conteúdo")
ents[0].insert(0, "Banco Azul"); ents[1].insert(0, "maria@exemplo.com")
senha_campo = ents[2]; senha_campo.insert(0, c.gerar_senha(20, True, True)); root.update()
achar(d, "Salvar").invoke(); root.update()
regs = app.cofre.registros
ok(len(regs) == 1 and regs[0]["servico"] == "Banco Azul" and regs[0]["login"] == "maria@exemplo.com" and len(regs[0]["senha"]) == 20,
   "salvou nome, usuário e senha")
ok(not erros, "sem erro ao salvar")
d = novo()
seletor = next(w for w in todos(d) if w.winfo_class() == "TCombobox" and "PIN numérico" in w.cget("values"))
seletor.set("PIN numérico")
achar(d, "+ Adicionar").invoke(); root.update()
v = " | ".join(vis())
ok("PIN" in v, "adicionar a credencial mostra PIN")
ok("NOTAS" in v, "notas continuam visíveis sem caixa adicional")
d.destroy(); root.update()
# editar abre completo
app.dialogo_registro(regs[0]); root.update(); root.update()
e = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w.title() == "Editar item")
ok("GRUPO" in " | ".join(str(w.cget("text")) for w in todos(e) if w.winfo_class() == "TLabel" and w.winfo_ismapped()), "editar abre o formulário completo")
e.destroy()
# Enter salva
d = novo(); ents = [w for w in todos(d) if w.winfo_class() == "TEntry" and w.winfo_ismapped()]
ents[0].insert(0, "Loja X"); ents[0].focus_force(); root.update(); ents[0].event_generate("<Return>"); root.update()
ok(any(r["servico"] == "Loja X" for r in app.cofre.registros), "Enter no campo salva o item")
print("PASSOU" if all(f) else "FALHOU", sum(f), "/", len(f))
root.destroy(); sys.exit(0 if all(f) else 1)
