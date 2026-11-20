"""CAMPOS DE TEXTO: ao destruir uma tela ou janela de diálogo, o texto digitado nos campos (senhas, chaves) é apagado
antes; campos ligados a uma variável (textvariable) ficam como estão."""
import os, sys
RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, RAIZ)
import tkinter as tk
from tkinter import ttk
import cofre_senhas as c
f = []


def ok(cond, nome):
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome, flush=True); f.append(bool(cond))


root = tk.Tk(); c.aplicar_tema(root)
vistos = []


original = c._apagar_campo_ao_fechar


def espia_limpeza(campo):
    """Roda a limpeza real e registra o que sobrou no campo logo depois (antes de ele ser destruído)."""
    original(campo)
    vistos.append((str(campo), campo.get()))


c._apagar_campo_ao_fechar = espia_limpeza


def espiar(e, rotulo):
    """Guarda o nome do campo para achar o resultado depois."""
    nomes[str(e)] = rotulo


nomes = {}
d = tk.Toplevel(root)
senha = ttk.Entry(d, show="•"); senha.pack(); senha.insert(0, "segredo-super-secreto"); espiar(senha, "ttk")
velho = tk.Entry(d); velho.pack(); velho.insert(0, "outro-segredo"); espiar(velho, "tk")
var = tk.StringVar(value="valor-da-variavel")
ligado = ttk.Entry(d, textvariable=var); ligado.pack(); espiar(ligado, "var")
root.update()
d.destroy(); root.update()
d_ = {nomes[k]: v for k, v in vistos if k in nomes}
ok(d_.get("ttk") == "", "ttk.Entry (senha) apagado ao fechar a janela")
ok(d_.get("tk") == "", "tk.Entry apagado ao fechar a janela")
ok(d_.get("var") == "valor-da-variavel" and var.get() == "valor-da-variavel", "campo com textvariable fica intacto")
root.destroy()
print("FALHOU" if not all(f) else "TUDO OK", len(f), "verificações")
sys.exit(0 if all(f) else 1)
