# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Anti-captura de tela: a janela principal e os diálogos pedem ao Windows para aparecer PRETOS em prints, gravações e acesso remoto
(SetWindowDisplayAffinity). No Windows lê de volta com GetWindowDisplayAffinity e confere que valeu; no Linux só confere o que dá (sem erro, e a proteção está ligada em todas as janelas do código)."""
import os, re, sys
_RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, _RAIZ); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "6_TESTE_ferramentas_dos_testes"))
import _resultado; _resultado.registrar(__file__)
import tkinter as tk
import cofre_senhas as c
f = []
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome, flush=True); f.append(bool(cond))
def info(t): print("  [info] " + t, flush=True)

with open(c.__file__, encoding="utf-8") as a:
    fonte = a.read()
chamadas = len(re.findall(r"proteger_contra_captura\(", fonte)) - 1          # menos a própria definição
ok(chamadas >= 6, "o código liga a proteção em %d lugares (janela principal e diálogos)" % chamadas)
ok("0x11" in fonte and "WDA_EXCLUDEFROMCAPTURE" in fonte, "usa WDA_EXCLUDEFROMCAPTURE (0x11), com WDA_MONITOR (0x01) como reserva")
ok('add="+")' in fonte and "<Map>" in fonte, "reaplica a proteção quando a janela é mapeada de novo (não se perde ao minimizar/restaurar)")

P = os.path.join(_resultado.pasta_temporaria("cofre_wda_"), "t.dat")
c.Cofre.criar(P, "cavalo azul come pizza na chuva", 3, c.MODO_S, "alto").fechar()
root = tk.Tk(); root.geometry("900x600+0+0")
try:
    app = c.App(root, P); app.mostrar_inicio(); root.update(); root.update()
    if os.name == "nt":
        from ctypes import wintypes
        import ctypes
        u = c._u32
        u.GetWindowDisplayAffinity.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u.GetWindowDisplayAffinity.restype = wintypes.BOOL
        def afinidade(janela):
            janela.update_idletasks()
            v = wintypes.DWORD(0)
            h = u.GetAncestor(janela.winfo_id(), 2)
            return v.value if u.GetWindowDisplayAffinity(h, ctypes.byref(v)) else None
        ok(app.protegido is True, "a janela principal registrou que está protegida (app.protegido)")
        a1 = afinidade(root)
        ok(a1 in (0x11, 0x01), "o Windows CONFIRMA a proteção da janela principal (afinidade lida = %s)" % (hex(a1) if a1 is not None else None))
        d = tk.Toplevel(root); d.update()
        ok(c.proteger_contra_captura(d) is True, "um diálogo também aceita a proteção")
        a2 = afinidade(d)
        ok(a2 in (0x11, 0x01), "o Windows CONFIRMA a proteção do diálogo (afinidade lida = %s)" % (hex(a2) if a2 is not None else None))
        d.destroy()
        root.iconify(); root.update(); root.deiconify(); root.update(); root.update()
        ok(afinidade(root) in (0x11, 0x01), "depois de minimizar e restaurar, a proteção continua")
    else:
        ok(c.proteger_contra_captura(root) is False, "fora do Windows: devolve False sem erro (não finge proteger)")
        info("a leitura da afinidade (GetWindowDisplayAffinity) só roda no Windows real")
finally:
    root.destroy()
print("\nTODOS OK" if all(f) else "\nHOUVE FALHAS")
sys.exit(0 if all(f) else 1)
