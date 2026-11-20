"""Interface (Tk): gerador com rodapé fixo e detalhes escondidos, 'Usar em um novo item', caixas de extras no Novo item,
grupos DENTRO de cada perfil, painel de proteção recolhido, convite do guia na 1ª entrada e troca de tela sem apagar a
janela. Roda no Windows ou no Linux (xvfb-run -a)."""
import os, sys, tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
import tkinter as tk
from tkinter import messagebox
import cofre_senhas as c
f = []
def ok(cond, nome):
    """Registra uma verificação."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
messagebox.showinfo = messagebox.showwarning = messagebox.showerror = lambda *a, **k: None
perguntas = []
messagebox.askyesno = lambda *a, **k: (perguntas.append(a), False)[1]
tk.Misc.wait_window = lambda self, window=None: None

def todos(w):
    """Todos os widgets filhos, recursivamente."""
    for x in w.winfo_children():
        yield x; yield from todos(x)
def tops(root): return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
def fecha(root):
    for w in tops(root): w.destroy()
    root.update()
def botao(d, trecho, classe="TButton"):
    for w in todos(d):
        if w.winfo_class() == classe and trecho in str(w.cget("text")) and w.winfo_ismapped(): return w
def textos(d): return [str(w.cget("text")) for w in todos(d) if w.winfo_class() in ("TLabel", "Label") and w.winfo_ismapped()]

W = tempfile.mkdtemp(prefix="ui_"); P = os.path.join(W, "t.dat"); SENHA = "cavalo azul come pizza na chuva"
v = c.Cofre.criar(P, SENHA, 5, c.MODO_OU, "alto")
v.registros.append(c.novo_item(servico="Banco Azul", login="a", senha="Xk9$mQ2!vL7@pR4#", grupo="Banco"))
v.registros.append(c.novo_item(servico="Conta do Pai", login="p", senha="Yz8#nB3@wM6$tQ1!", grupo="Banco", pessoa="Pai"))
v.salvar(); v.fechar()
root = tk.Tk(); root.geometry("1100x700+0+0")
app = c.App(root, P); root.update()
app.cofre = c.Cofre.abrir(P, senha=SENHA); app.tela_principal(); root.update()

# ---- troca de tela: a janela nunca fica transparente e a tela antiga some
alfas = []
orig = root.attributes
root.attributes = lambda *a, **k: (alfas.append(a), orig(*a, **k))[1]
app.tela_principal(); root.update()
ok(not any(a and a[0] == "-alpha" for a in alfas), "trocar de tela não pisca (nada de transparência na janela inteira)")
ok(len([w for w in root.winfo_children() if w.winfo_class() in ("TFrame", "Canvas")]) == 1, "só uma tela existe depois da troca (a antiga foi apagada)")
ok(app.frame.winfo_ismapped(), "a tela nova está visível")
root.attributes = orig

# ---- gerador avulso
app.dialogo_gerador(); root.update(); root.update()
d = tops(root)[-1]
ok(botao(d, "Usar em um novo item") is not None, "gerador avulso oferece 'Usar em um novo item'")
# senha gerada OCULTA por padrão; só o olho mostra
caixa_g = [w for w in todos(d) if w.winfo_class() == "Text"][0]
ver_g = lambda: caixa_g.get("1.0", "end").strip()
ok(set(ver_g()) == {"•"} and len(ver_g()) >= 8, "senha gerada NÃO aparece sozinha: só bolinhas")
olho = [w for w in todos(d) if w.winfo_class() == "TButton" and str(w.cget("text")) == "👁"][0]
olho.invoke(); root.update()
ok("•" not in ver_g() and len(ver_g()) >= 8, "clicar no olho mostra a senha")
olho.invoke(); root.update()
ok(set(ver_g()) == {"•"}, "clicar de novo no olho esconde")
botao(d, "Atualizar senha").invoke(); root.update()
ok(set(ver_g()) == {"•"}, "gerar outra senha mantém oculta")
for t in ("Copiar", "Atualizar senha"):
    b = botao(d, t); ok(b is not None and b.winfo_rooty() + b.winfo_height() <= d.winfo_rooty() + d.winfo_height() + 2, f"botão '{t}' está dentro da janela (rodapé fixo)")
ok(not any("Composição" in t or "TEMPO PARA" in t.upper() for t in textos(d)), "textos de análise escondidos até o clique")
ok(not any("bits" in t for t in textos(d)), "'bits' (técnico) não fica à vista")
b = botao(d, "Ver detalhes"); b.invoke(); root.update()
ok(any("Composição" in t for t in textos(d)), "'Ver detalhes' mostra a composição")
botao(d, "Esconder detalhes").invoke(); root.update()
ok(not any("Composição" in t for t in textos(d)), "'Esconder detalhes' esconde de novo")
ok(botao(d, "Testar uma senha") is not None and not any("Verificado só" in t for t in textos(d)), "teste de senha escondido atrás de botão")
for w in todos(d):
    if w.winfo_class() == "TCheckbutton":
        w.invoke(); root.update()
senha_gerada = None
botao(d, "Usar em um novo item").invoke(); root.update(); root.update()
root.after(100); root.update()
for _ in range(10): root.update()
nd = tops(root)[-1]
ok(nd.title() == "Novo item", "abre 'Novo item'")
cand = [w for w in todos(nd) if w.winfo_class() in ("TEntry", "Entry") and len(w.get()) >= 8]
ok(len(cand) == 1, "a senha gerada já vem preenchida no Novo item")

# ---- Novo item: caixas de extras e grupo
def marca(d_, rot):
    for w in todos(d_):
        if w.winfo_class() == "TCheckbutton" and str(w.cget("text")) == rot: w.invoke(); d_.update(); return True
vis = lambda: [t.upper() for t in textos(nd)]
ok(not any(t in ("PIN", "SENHA EXTRA", "CÓDIGOS DE RECUPERAÇÃO") for t in vis()), "PIN, senha extra e códigos de recuperação escondidos por padrão")
ok(marca(nd, "Senha extra") and "SENHA EXTRA" in vis(), "marcar 'Senha extra' mostra o campo")
ok(marca(nd, "PIN") and "PIN" in vis(), "marcar 'PIN' mostra o campo")
ok(marca(nd, "Código de recuperação") and "CÓDIGOS DE RECUPERAÇÃO" in vis(), "marcar 'Código de recuperação' mostra a caixa de códigos")
ok(all(w.cget("show") == "•" for w in todos(nd) if w.winfo_class() == "TEntry" and str(w.cget("show"))) and
   any(w.winfo_class() == "TEntry" and str(w.cget("show")) == "•" for w in todos(nd)), "marcar caixas NÃO revela nenhuma senha (continuam em bolinhas)")
marca(nd, "PIN"); ok("PIN" not in vis(), "desmarcar esconde")
cg = [w for w in todos(nd) if w.winfo_class() == "TCombobox" and w.winfo_ismapped()]
ok(len(cg) >= 1 and "＋ Criar novo grupo…" in list(cg[0].cget("values")), "grupo visível, com a opção '＋ Criar novo grupo…'")
cg[0].set("＋ Criar novo grupo…"); cg[0].event_generate("<<ComboboxSelected>>"); root.update()
ok(cg[0].get() == "", "criar novo grupo limpa o campo para o usuário escrever o nome que quiser")
fecha(root)

# ---- grupos DENTRO do perfil
app._pedir_nome = lambda *a, **k: "Google"
app.filtro_pessoa.set("Pai"); ok(app._novo_grupo(), "cria grupo dentro do perfil 'Pai'")
ok("Google" in app._grupos("Pai") and "Google" not in app._grupos(""), "o grupo é do perfil 'Pai' e não aparece em 'Eu'")
app.filtro_pessoa.set(""); ok(app._novo_grupo(), "o mesmo nome pode existir em outro perfil")
ok("Google" in app._grupos("") and "Google" in app._grupos("Pai"), "cada perfil tem o seu 'Google'")
app._pedir_nome = lambda *a, **k: "Google"
ok(app._novo_grupo() is False, "repetir o nome dentro do MESMO perfil é recusado")
app.cofre.meta["grupos_extra"] = ["Velho"]
ok("Velho" in app._grupos("") and "Velho" not in app._grupos("Pai"), "grupo de cofre antigo passa a ser do titular (Eu)")
app.filtro_pessoa.set("Pai"); app.atualizar_lista(); root.update()
sec = [str(w.cget("text")) for w in todos(app.lateral) if w.winfo_class() == "Label"]
ok(any(t.upper() == "GRUPOS DE PAI" for t in sec), "barra lateral mostra 'Grupos de Pai'")
ok(not any("Velho" == t for t in sec), "grupos de outro perfil não aparecem no perfil 'Pai'")

# ---- painel de proteção recolhido
app.filtro_pessoa.set("*"); app.atualizar_lista(); root.update()
caixa = list(app._painel_seg.winfo_children())[0]
n_linhas = len([w for w in caixa.winfo_children()])
ok(n_linhas == 2, "painel de proteção recolhido: escudo + barra do nível")
rot_n = [str(w.cget("text")) for w in todos(caixa) if w.winfo_class() == "Label"]
ok(any(t.startswith("Proteção: ") for t in rot_n), "mostra o nível de proteção (ranking)")
ok(not any("Ativar" == t for t in rot_n), "recolhido: sem a lista de itens")
for w in list(todos(caixa)):
    if w.winfo_class() == "Label" and str(w.cget("text")) in ("Cofre protegido", "Proteção parcial"):
        w.event_generate("<Button-1>"); break
root.update()
caixa = list(app._painel_seg.winfo_children())[0]
rot_n = [str(w.cget("text")) for w in todos(caixa) if w.winfo_class() == "Label"]
ok("Ativar" in rot_n and any("FIDO" in t for t in rot_n), "aberto: lista o que aumenta a proteção, com 'Ativar' no que falta")
app._seg_aberto = False; app._atualizar_indicadores(); root.update()
for w in todos(app._painel_seg):
    if w.winfo_class() == "Label" and w.cget("text") in ("Cofre protegido", "Proteção parcial"):
        w.event_generate("<Button-1>"); break
root.update()
caixa = list(app._painel_seg.winfo_children())[0]
ok(len(list(caixa.winfo_children())) > 1, "clicar no escudo mostra o resto das informações")
ok(not any("AES-256" in t for t in textos(app.root)), "informações técnicas (cifras) fora da tela principal")

# ---- guia na primeira entrada
app.cofre.meta.pop("tour_visto", None); perguntas.clear()
app._oferecer_passeio(); root.update()
ok(len(perguntas) == 1 and app.cofre.meta.get("tour_visto"), "guia é oferecido na primeira entrada (e marcado como visto)")
perguntas.clear(); app._oferecer_passeio(); ok(not perguntas, "não é oferecido de novo")
app.cofre.meta.pop("tour_visto", None)
t = tk.Toplevel(root); t.update()
app._oferecer_passeio(); ok(not perguntas, "com outra janela aberta, espera (não aparece por cima)")
t.destroy()
root.destroy()
print("FALHAS:", f.count(False)); sys.exit(1 if False in f else 0)
