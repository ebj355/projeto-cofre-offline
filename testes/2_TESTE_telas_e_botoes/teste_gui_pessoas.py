# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Perfis (pessoas): lista lateral 'Eu' + 'Adicionar', grupo antigo virando pessoa, cabeçalhos de planilha 'Dono/Titular'."""
import os as _os, sys as _sys, tempfile as _tf, subprocess as _sp
_RAIZ = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".."))
def _foto(arq):
    """Captura a tela (só onde existe o ImageMagick 'import'); sem ele, ignora."""
    try: _sp.run(["import", "-window", "root", arq], check=False)
    except Exception: pass
import os, sys, subprocess, time
sys.path.insert(0, _RAIZ)
import tkinter as tk, cofre_senhas as c
from tkinter import messagebox
f = []
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
W = _tf.mkdtemp(prefix="cofre_gui_"); P = os.path.join(W, "p.dat")
if os.path.exists(P): os.remove(P)
SENHA = "cavalo azul come pizza na chuva"
v = c.Cofre.criar(P, SENHA, 5, c.MODO_OU, "alto")
for s, g in (("Banco do Brasil", "Bancos"), ("Nubank", "Bancos"), ("Gmail", "E-mail"),
             ("Itaú do pai", "pai"), ("Vivo do pai", "pai"), ("Gov.br do pai", "pai")):
    v.registros.append(c.novo_item(servico=s, login="x@y.com", senha="Senha-Forte-123!", grupo=g))
v.salvar()
messagebox.askyesno = lambda *a, **k: True
erros = []
messagebox.showerror = lambda *a, **k: erros.append(a)
root = tk.Tk(); root.geometry("1366x768"); app = c.App(root, P)
app.cofre = c.Cofre.abrir(P, senha=SENHA); app.tela_principal(); root.update()
def ids(bar): return list(bar.get_children())
ok(ids(app.lateral_pessoas) == ["p:", "__nova_pessoa__"], f"só 'Eu' + Adicionar no começo: {ids(app.lateral_pessoas)}")
ok("g:pai" in ids(app.lateral), "grupo antigo 'pai' aparece nos grupos")
ok(c._campo_do_cabecalho("Dono") == "pessoa" and c._campo_do_cabecalho("Titular") == "pessoa"
   and c._campo_do_cabecalho("Grupo") == "grupo", "importação: Dono/Titular viram Pessoa; Grupo continua grupo")
# transformar grupo em pessoa
app._grupo_para_pessoa("pai"); root.update()
pai = [r for r in app.cofre.registros if r.get("pessoa") == "Pai"]
ok(len(pai) == 3 and all(not r["grupo"] for r in pai), "grupo 'pai' virou a pessoa 'Pai' (3 contas, sem grupo)")
ok(ids(app.lateral_pessoas) == ["p:*", "p:", "p:Pai", "__nova_pessoa__"], f"pessoas: {ids(app.lateral_pessoas)}")
ok(app.filtro_pessoa.get() == "Pai" and app._conta_lista.cget("text") == "3", "mostra só as contas do Pai")
ok(app._titulo_lista.cget("text") == "Pai  ·  Todas as contas", "título: " + app._titulo_lista.cget("text"))
ok("g:Bancos" not in ids(app.lateral), "grupos do Pai não mostram os grupos do Eu")
_foto(os.path.join(W, "pai.png"))
# escolher Eu
app.lateral_pessoas.selection_set("p:"); root.update(); root.update()
ok(app._conta_lista.cget("text") == "3" and "g:Bancos" in ids(app.lateral), "Eu: 3 contas e grupos Bancos/E-mail")
# todas
app.lateral_pessoas.selection_set("p:*"); root.update(); root.update()
ok(app._conta_lista.cget("text") == "6", "Todas as pessoas: 6 contas")
_foto(os.path.join(W, "todas.png"))
# adicionar pessoa
app._pedir_nome = lambda *a, **k: "Mãe"
app._adicionar_pessoa(); root.update()
ok("p:Mãe" in ids(app.lateral_pessoas) and app.filtro_pessoa.get() == "Mãe", "adicionar pessoa 'Mãe' (sem contas ainda)")
app._pedir_nome = lambda *a, **k: "Pai"
n_antes = len(ids(app.lateral_pessoas)); app._adicionar_pessoa(); root.update(); print("cofre aberto?", app.cofre is not None, erros)
ok(len(ids(app.lateral_pessoas)) == n_antes, "não deixa repetir nome de pessoa")
# novo item com a pessoa do filtro
def novo_no_form():
    d = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)][0]
    def todos(w, cls):
        r = []
        for ch in w.winfo_children():
            if ch.winfo_class() == cls: r.append(ch)
            r += todos(ch, cls)
        return r
    combos = todos(d, "TCombobox")
    ok(any(cb.get() == "Mãe" for cb in combos), "formulário já vem com a pessoa escolhida (Mãe)")
    ents = todos(d, "TEntry"); ents[0].insert(0, "Unimed da mãe")
    _foto(os.path.join(W, "form.png"))
    [b for b in todos(d, "TButton") if b.cget("text") == "Salvar"][0].invoke()
root.after(700, novo_no_form); app.novo()
t0 = time.time()
while time.time() - t0 < 1.5: root.update(); time.sleep(0.02)
ok(any(r["servico"] == "Unimed da mãe" and r["pessoa"] == "Mãe" for r in app.cofre.registros), "conta nova salva com pessoa Mãe")
# combobox de Pessoa tem a opção de criar perfil novo (igual ao Grupo) -- reclamação real: a lista de sugestões
# parecia fechada, sem jeito óbvio de adicionar mais uma pessoa de dentro do próprio formulário
app.dialogo_registro(None); root.update()
d = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)][-1]
def _todos(w, cls):
    r = []
    for ch in w.winfo_children():
        if ch.winfo_class() == cls: r.append(ch)
        r += _todos(ch, cls)
    return r
combos = _todos(d, "TCombobox")
cp_novo = combos[1]       # grupo é o 1º combobox criado, pessoa é o 2º
ok(cp_novo.cget("values")[0] == "＋ Criar novo perfil…", f"combobox de Pessoa tem a opção de criar perfil novo primeiro: {cp_novo.cget('values')}")
cp_novo.set("＋ Criar novo perfil…"); cp_novo.event_generate("<<ComboboxSelected>>"); root.update()
ok(cp_novo.get() == "", "selecionar '＋ Criar novo perfil…' limpa o campo para digitar o nome novo")
cp_novo.insert(0, "Sobrinho")
ok(app._valor_pessoa(cp_novo.get()) == "Sobrinho", "nome novo digitado depois da opção é gravado normalmente")
d.destroy(); root.update()
# renomear e remover
app._pedir_nome = lambda *a, **k: "Papai"; app._renomear_pessoa("Pai"); root.update()
ok(sum(1 for r in app.cofre.registros if r.get("pessoa") == "Papai") == 3 and "p:Papai" in ids(app.lateral_pessoas), "renomear Pai -> Papai")
app._remover_pessoa("Papai"); root.update()
ok(not any(r.get("pessoa") == "Papai" for r in app.cofre.registros) and len(app.cofre.registros) == 7, "remover pessoa: contas passam para Eu, nada apagado")
# persistência
v2 = c.Cofre.abrir(P, senha=SENHA)
ok("Mãe" in v2.meta.get("pessoas", []) and any(r.get("pessoa") == "Mãe" for r in v2.registros), "pessoas ficam gravadas (cifradas) no cofre")
print("\nTODOS OK" if all(f) else "\nHOUVE FALHAS")
root.destroy()
