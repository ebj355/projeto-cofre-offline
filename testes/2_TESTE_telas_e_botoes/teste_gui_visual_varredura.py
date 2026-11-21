# -*- coding: utf-8 -*-
"""
Varredura VISUAL da interface da Arca (Tk real), em varias escalas do Windows e varios tamanhos de janela.

O que procura, em cada tela (criar, desbloqueio, principal e a janela "Novo item"):
  - texto cortado (o widget recebeu menos largura/altura do que pediu);
  - widget fora da janela (fora da area visivel, exceto dentro de areas com rolagem);
  - widgets de texto sobrepostos entre si;
  - widget com texto e tamanho zero;
  - contraste fraco entre texto e fundo (razao WCAG: < 3,0 falha; < 4,5 alerta);
  - rótulos cujo fundo nao combina com o cartao ou painel em que aparecem;
  - janela maior que a tela;
  - (opcional, precisa de Pillow) captura de tela e comparacao com imagem de referencia.

LIMITE HONESTO: controles que o programa desenha sozinho num Canvas (icones, cartoes, barra lateral)
nao tem "texto" para o Tk medir. Para eles, a unica protecao e a comparacao de capturas.

Uso:   python teste_gui_visual_varredura.py                       (roda as 4 escalas: 100, 125, 150, 200%)
       python teste_gui_visual_varredura.py --escala 1.5         (so uma escala)
       set COFRE_VISUAL_GRAVAR_REFERENCIA=1  -> grava as capturas atuais como referencia (rode so numa
                                                versao que voce conferiu a olho e achou correta)
Saida: [OK] / [ALERTA] / [FALHOU] / [PULADO] por verificacao; codigo de saida 1 se houver [FALHOU].
Rode de preferencia no Windows real ou na VM Windows 11. No Linux (Xvfb) as medidas de fonte diferem.
"""
import os
import sys
import subprocess
import tempfile
import shutil
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

AQUI = os.path.dirname(os.path.abspath(__file__))
ESCALAS = (1.0, 1.25, 1.5, 2.0)
TAMANHOS = ((1366, 768), (1024, 700), (1920, 1080))
SENHA = "SenhaDeTeste-visual-14c"
TIPOS_TEXTO = ("Label", "Button", "Checkbutton", "Radiobutton", "Menubutton",
               "TLabel", "TButton", "TCheckbutton", "TRadiobutton", "TMenubutton")


def achar_programa():
    """Procura cofre_senhas.py na pasta deste teste e nas pastas acima."""
    pasta = AQUI
    for _ in range(6):
        if os.path.isfile(os.path.join(pasta, "cofre_senhas.py")):
            return pasta
        pasta = os.path.dirname(pasta)
    return None


def pasta_resultados():
    pasta = AQUI
    for _ in range(6):
        r = os.path.join(pasta, "testes", "resultados")
        if os.path.isdir(r):
            return r
        pasta = os.path.dirname(pasta)
    r = os.path.join(AQUI, "resultados_visuais")
    os.makedirs(r, exist_ok=True)
    return r


# ----------------------------------------------------------------- modo "filho": uma escala
def luminancia(rgb16):
    """Luminancia relativa WCAG de uma cor (r,g,b de 0..65535)."""
    def canal(v):
        v = v / 65535.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb16
    return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)


def contraste(c1, c2):
    a, b = luminancia(c1), luminancia(c2)
    if a < b:
        a, b = b, a
    return (a + 0.05) / (b + 0.05)


def filho(escala):
    sys.path.insert(0, achar_programa())
    import tkinter as tk
    from tkinter import ttk
    import cofre_senhas as C

    # A janela pede ao Windows para sair preta em prints; so neste teste, trocamos a funcao no proprio
    # processo do teste (nenhum arquivo do programa muda e nenhuma opcao nova e criada no produto).
    C.proteger_contra_captura = lambda janela: False
    C._grab_seguro = lambda janela, *a, **k: None
    tk.Misc.focus_set = lambda self: None

    try:
        from PIL import ImageGrab, ImageChops
    except ImportError:
        ImageGrab = ImageChops = None

    achados = []          # (nivel, texto)
    relat = lambda nivel, txt: achados.append((nivel, txt))
    fundos_reportados = set()
    estilos_superficie = {
        "Card.TFrame", "Card2.TFrame", "C.TFrame", "L.TFrame", "S2.TFrame",
        "Pagina.TFrame", "Noite.TFrame", "Fundo.TFrame", "Lateral.TFrame",
        "Sup.TFrame", "Cartao.TFrame",
    }

    tmp = tempfile.mkdtemp(prefix="visual_")
    caminho = os.path.join(tmp, "cofre.dat")
    pasta_cap = os.path.join(pasta_resultados(), "capturas_visuais")
    pasta_ref = os.path.join(AQUI, "referencias_visuais")
    gravar_ref = os.environ.get("COFRE_VISUAL_GRAVAR_REFERENCIA") == "1"
    os.makedirs(pasta_cap, exist_ok=True)
    if gravar_ref:
        os.makedirs(pasta_ref, exist_ok=True)

    root = tk.Tk()
    estilo = ttk.Style(root)
    root.tk.call("tk", "scaling", escala * 96.0 / 72.0)     # simula 100/125/150/200% do Windows
    root.report_callback_exception = lambda t, v, tb: relat("FALHOU", f"excecao na interface: {t.__name__}: {v}")

    def todos(w):
        yield w
        for c in w.winfo_children():
            yield from todos(c)

    def em_canvas(w):
        p = w.master
        while p is not None:
            if isinstance(p, tk.Canvas):
                return True
            p = getattr(p, "master", None)
        return False

    def texto_de(w):
        if w.winfo_class() not in TIPOS_TEXTO:
            return ""
        try:
            return str(w.cget("text")).strip()
        except tk.TclError:
            return ""

    def checar(janela, nome):
        janela.update_idletasks()
        janela.update()
        problemas = 0
        top = janela.winfo_toplevel()
        tx, ty = top.winfo_rootx(), top.winfo_rooty()
        tw, th = top.winfo_width(), top.winfo_height()
        if tw > top.winfo_screenwidth() + 2 or th > top.winfo_screenheight() + 2:
            relat("FALHOU", f"{nome}: janela {tw}x{th} maior que a tela "
                            f"{top.winfo_screenwidth()}x{top.winfo_screenheight()}")
        for w in todos(janela):
            classe = w.winfo_class()
            if classe not in ("TLabel", "TFrame"):
                continue
            texto = texto_de(w) if classe == "TLabel" else ""
            if classe == "TLabel" and not texto:
                continue
            estilo_widget = w.cget("style") or ("TLabel" if classe == "TLabel" else "TFrame")
            if classe == "TFrame" and estilo_widget != "TFrame":
                continue
            if estilo_widget in ("Etiqueta.TLabel", "EtiquetaFraca.TLabel"):
                continue
            pai = w.master
            superficie = None
            while pai is not None:
                if pai.winfo_class() == "TFrame":
                    candidato = pai.cget("style") or "TFrame"
                    if candidato in estilos_superficie:
                        superficie = candidato
                        break
                pai = getattr(pai, "master", None)
            if superficie is None:
                continue
            fundo_widget = estilo.lookup(estilo_widget, "background")
            fundo_superficie = estilo.lookup(superficie, "background")
            if fundo_widget and fundo_superficie and fundo_widget.lower() != fundo_superficie.lower():
                problemas += 1
                chave = (classe, estilo_widget, superficie, fundo_widget.lower(), fundo_superficie.lower())
                if chave not in fundos_reportados:
                    fundos_reportados.add(chave)
                    descricao = f"'{texto[:30]}'" if texto else "um contêiner"
                    relat("FALHOU", f"{nome}: {descricao} ({classe}, estilo {estilo_widget}) usa fundo "
                                    f"{fundo_widget} dentro de {superficie} ({fundo_superficie}); pode criar "
                                    "uma faixa de cor diferente do cartão")
            problemas += 1
        irmaos = {}
        for w in todos(janela):
            try:
                if not w.winfo_ismapped():
                    continue
                txt = texto_de(w)
                largura, altura = w.winfo_width(), w.winfo_height()
                if txt:
                    if largura <= 1 or altura <= 1:
                        relat("FALHOU", f"{nome}: '{txt[:40]}' ({w.winfo_class()}) com tamanho zero")
                        problemas += 1
                        continue
                    if w.winfo_reqwidth() > largura + 1:
                        relat("FALHOU", f"{nome}: texto cortado na largura '{txt[:40]}' "
                                        f"(pediu {w.winfo_reqwidth()}px, recebeu {largura}px)")
                        problemas += 1
                    elif not em_canvas(w) and w.winfo_reqheight() > altura + 1:
                        relat("FALHOU", f"{nome}: texto cortado na altura '{txt[:40]}' "
                                        f"(pediu {w.winfo_reqheight()}px, recebeu {altura}px)")
                        problemas += 1
                    try:
                        fg, bg = w.cget("fg"), w.cget("bg")
                        cr = contraste(w.winfo_rgb(fg), w.winfo_rgb(bg))
                        if cr < 3.0:
                            relat("FALHOU", f"{nome}: contraste {cr:.1f}:1 em '{txt[:40]}' (minimo 3:1)")
                            problemas += 1
                        elif cr < 4.5:
                            relat("ALERTA", f"{nome}: contraste {cr:.1f}:1 em '{txt[:40]}' (ideal 4,5:1)")
                    except tk.TclError:
                        pass
                    irmaos.setdefault(str(w.master), []).append((w, txt))
                if not em_canvas(w) and w is not top and w.winfo_class() not in ("Toplevel", "Tk"):
                    if (w.winfo_rootx() + largura > tx + tw + 1 or w.winfo_rooty() + altura > ty + th + 1
                            or w.winfo_rootx() < tx - 1 or w.winfo_rooty() < ty - 1):
                        relat("FALHOU", f"{nome}: {w.winfo_class()} '{txt[:30]}' fora da janela")
                        problemas += 1
            except tk.TclError:
                continue
        for lista in irmaos.values():                      # sobreposicao de textos irmaos
            for i in range(len(lista)):
                a, ta = lista[i]
                for j in range(i + 1, len(lista)):
                    b, tb = lista[j]
                    try:
                        dx = min(a.winfo_rootx() + a.winfo_width(), b.winfo_rootx() + b.winfo_width()) - \
                             max(a.winfo_rootx(), b.winfo_rootx())
                        dy = min(a.winfo_rooty() + a.winfo_height(), b.winfo_rooty() + b.winfo_height()) - \
                             max(a.winfo_rooty(), b.winfo_rooty())
                    except tk.TclError:
                        continue
                    if dx > 3 and dy > 3:
                        relat("FALHOU", f"{nome}: '{ta[:25]}' sobrepoe '{tb[:25]}' ({dx}x{dy}px)")
                        problemas += 1
        if problemas == 0:
            relat("OK", f"{nome}: sem texto cortado, sobreposto, fora da janela ou com contraste fraco")
        capturar(top, nome)

    def capturar(top, nome):
        if ImageGrab is None:
            return
        nome_arq = "".join(ch if ch.isalnum() else "_" for ch in nome)
        try:
            top.update_idletasks()
            if sys.platform == "win32":
                img = ImageGrab.grab(window=top.winfo_id())
            else:
                x, y = top.winfo_rootx(), top.winfo_rooty()
                img = ImageGrab.grab(bbox=(x, y, x + top.winfo_width(), y + top.winfo_height()))
        except (tk.TclError, OSError, TypeError) as e:
            relat("ALERTA", f"{nome}: nao consegui capturar a janela ({e})")
            return
        img.save(os.path.join(pasta_cap, nome_arq + ".png"))
        # imagem totalmente preta = a janela ainda esta escondida da captura
        if img.convert("L").getextrema()[1] < 8:
            relat("FALHOU", f"{nome}: captura toda preta (proteger_contra_captura ainda ativa?)")
            return
        ref = os.path.join(pasta_ref, nome_arq + ".png")
        if gravar_ref:
            img.save(ref)
            relat("OK", f"{nome}: referencia gravada")
        elif os.path.isfile(ref):
            from PIL import Image
            antiga = Image.open(ref).convert("RGB")
            nova = img.convert("RGB")
            if antiga.size != nova.size:
                relat("FALHOU", f"{nome}: tamanho da tela mudou ({antiga.size} -> {nova.size})")
                return
            dif = ImageChops.difference(antiga, nova).convert("L").point(lambda v: 255 if v > 24 else 0)
            frac = dif.histogram()[255] / float(dif.size[0] * dif.size[1])
            if frac > 0.05:
                relat("FALHOU", f"{nome}: {frac:.1%} dos pixels mudaram em relacao a referencia")
            elif frac > 0.01:
                relat("ALERTA", f"{nome}: {frac:.1%} dos pixels mudaram em relacao a referencia")
            else:
                relat("OK", f"{nome}: igual a referencia ({frac:.2%} de diferenca)")

    def varrer_tamanhos(rotulo):
        for (w, h) in TAMANHOS:
            root.geometry(f"{w}x{h}+0+0")
            root.update()
            time.sleep(0.15)
            root.update()
            checar(root, f"[{int(escala*100)}%] {rotulo} {w}x{h}")

    def abrir_e_varrer(rotulo):
        concluido = tk.BooleanVar(master=root, value=False)
        def varrer_e_fechar():
            try:
                tops = [w for w in todos(root) if isinstance(w, tk.Toplevel)]
                if not tops:
                    relat("FALHOU", f"[{int(escala*100)}%] a janela {rotulo} nao abriu")
                for t in tops:
                    checar(t, f"[{int(escala*100)}%] {rotulo}")
                for t in tops:
                    try:
                        t.destroy()
                    except tk.TclError:
                        pass
            finally:
                concluido.set(True)

        root.after(1000, varrer_e_fechar)
        try:
            app.dialogo_registro(None)
        except Exception as e:
            relat("FALHOU", f"[{int(escala*100)}%] erro ao abrir {rotulo}: {type(e).__name__}: {e}")
        if not concluido.get():
            root.wait_variable(concluido)

    try:
        app = C.App(root, caminho)
        C.revelar_janela(root)
        root.update()
        varrer_tamanhos("tela de criar cofre")

        C.Cofre.criar(caminho, SENHA, nivel="alto").fechar()
        app.cofre = None
        app.tela_desbloqueio()
        root.update()
        varrer_tamanhos("tela de desbloqueio")

        app.cofre = C.Cofre.abrir(caminho, senha=SENHA)
        try:
            item = C.novo_item(servico="Banco com um nome bem comprido para testar o corte de texto na lista",
                               login="usuario.de.exemplo@exemplo.com", senha="S3nha-de-exemplo-visual!",
                               notas="Nota de exemplo " * 8)
            app.cofre.registros.append(item)
        except Exception as e:                                   # item de exemplo e so um enfeite
            relat("ALERTA", f"item de exemplo nao criado ({type(e).__name__}); lista fica vazia")
        app.tela_principal()
        root.update()
        varrer_tamanhos("tela principal")
        root.geometry("1366x768+0+0")
        root.update()
        modal = app._modal
        app._modal = lambda janela: None
        try:
            abrir_e_varrer("janela Novo item")
        finally:
            app._modal = modal
    except Exception as e:
        import traceback
        relat("FALHOU", f"[{int(escala*100)}%] o teste nao conseguiu montar uma tela: {type(e).__name__}: {e}")
        traceback.print_exc()
    finally:
        try:
            root.destroy()
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)
    if ImageGrab is None:
        relat("PULADO", f"[{int(escala*100)}%] Pillow nao instalado: sem captura/comparacao de imagem "
                        "(pip install pillow)")
    for nivel, txt in achados:
        print(f"[{nivel}] {txt}")
    return 1 if any(n == "FALHOU" for n, _ in achados) else 0


# ----------------------------------------------------------------- modo "pai": todas as escalas
def pai(escalas):
    if achar_programa() is None:
        print("[FALHOU] nao achei cofre_senhas.py nesta pasta nem nas de cima. Copie estes arquivos para a "
              "pasta do projeto (ex.: testes\\2_telas_e_botoes).")
        return 1
    if sys.platform != "win32":
        print("[ALERTA] fora do Windows as medidas de fonte e de escala nao valem como evidencia visual real.")
    saida = []
    falhou = False
    for e in escalas:
        print(f"\n===== escala {int(e*100)}% =====", flush=True)
        env = dict(os.environ, COFRE_TESTE_ESCALA=str(e))
        if sys.platform == "win32":
            env["COFRE_GUI_TESTS_BACKGROUND"] = "1"
        try:
            r = subprocess.run([sys.executable, os.path.abspath(__file__)], env=env, capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=900)
            texto = r.stdout + (("\n" + r.stderr) if r.stderr.strip() else "")
            rc = r.returncode
        except subprocess.TimeoutExpired:
            texto, rc = "[FALHOU] o teste passou de 15 min e foi interrompido", 1
        print(texto, flush=True)
        saida.append(f"===== escala {int(e*100)}% =====\n{texto}")
        falhou = falhou or rc != 0
    arq = os.path.join(pasta_resultados(), "resultado_teste_gui_visual_varredura.txt")
    with open(arq, "w", encoding="utf-8") as f:
        f.write("\n".join(saida))
    print(f"\nResultado gravado em: {arq}")
    print("[FALHOU] ha defeitos visuais acima." if falhou else "[OK] nenhuma falha nas escalas testadas.")
    return 1 if falhou else 0


if __name__ == "__main__":
    if os.environ.get("COFRE_TESTE_ESCALA"):
        sys.exit(filho(float(os.environ["COFRE_TESTE_ESCALA"])))
    if "--escala" in sys.argv:
        sys.exit(pai((float(sys.argv[sys.argv.index("--escala") + 1]),)))
    sys.exit(pai(ESCALAS))
