"""Gerador de senhas, avaliação de força, tempo para quebrar e estruturas de impressão.
Uso:  python testes/teste_forca.py"""
import os, sys, tempfile
# usa o cofre_senhas.py da pasta do projeto e trabalha numa pasta temporária (não suja o repositório)
RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, RAIZ)
os.chdir(tempfile.mkdtemp(prefix="teste_cofre_"))
import sys, ctypes, math, re
import cofre_senhas as c
f = []
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
print("Gerador aleatório")
for n, num, sim in ((20, True, True), (12, False, False), (64, True, False)):
    amostras = [c.gerar_senha(n, num, sim) for _ in range(300)]
    ok(all(len(s) == n for s in amostras), f"tamanho {n}")
    ok(all(any(ch.isdigit() for ch in s) == num or not num and not any(ch.isdigit() for ch in s) for s in amostras), f"números={num}")
    ok(all((any(not ch.isalnum() for ch in s)) == sim for s in amostras), f"símbolos={sim}")
    ok(len(set(amostras)) == 300, "nenhuma repetida em 300")
print("Fácil de lembrar")
fr = [c.gerar_frase(5) for _ in range(200)]
ok(all(re.fullmatch(r"[A-Z][a-z]+(-[a-z]+){4}-\d{1,2}", s) for s in fr), f"formato ok (ex.: {fr[0]})")
ok(c.bits_frase(5) > 80, f"5 palavras = {c.bits_frase(5):.0f} bits (muito forte)")
print("PIN")
pins = [c.gerar_pin(6) for _ in range(500)]
ok(all(len(p) == 6 and p.isdigit() and not c.pin_obvio(p) for p in pins), "PINs de 6 dígitos sem padrões óbvios")
for p in ("1234", "0000", "1212", "1990", "2580", "987654", "111111"):
    ok(c.pin_obvio(p), f"{p} reconhecido como óbvio")
ok(not c.pin_obvio("4821") and not c.pin_obvio("730592"), "PINs aleatórios aceitos")
print("Avaliação de força")
casos = {"123456": 0, "senha123": 0, "Flamengo2024": 1, "abcd1234efgh": 1, "cavalo azul come pizza na chuva": 4,
         c.gerar_senha(20): 4, "Tr0mb0ne-Laranja": 1}
for s, esperado_min in casos.items():
    nota, rot, bits, dicas = c.avaliar_forca(s)
    if esperado_min <= 1:
        ok(nota <= esperado_min, f"'{s if len(s) < 25 else s[:6]+'…'}' -> {rot} ({bits} bits) | {dicas[0] if dicas else ''}")
    else:
        ok(nota >= esperado_min, f"'{s if len(s) < 25 else s[:6]+'…'}' -> {rot} ({bits} bits)")
print("Verificação do cofre")
regs = [c.novo_item(servico="A", senha="Flamengo2024"), c.novo_item(servico="B", senha="Flamengo2024"),
        c.novo_item(servico="C", senha=c.gerar_senha(20), pin="1234"), c.novo_item(servico="D", senha=c.gerar_senha(20))]
ach = c.auditar_cofre(regs)
ok(sum(1 for a in ach if a[2] == "Senha REPETIDA") == 2, "detecta senha repetida em A e B")
ok(any(a[1] == "pin" for a in ach), "detecta PIN óbvio em C")
ok(not any(a[0]["servico"] == "D" for a in ach), "D (forte e única) sem alertas")
print("Impressão")
L = c.linhas_impressao("TESTE", [("Senha", "x" * 130), ("Códigos", "111\n222")])
ok(any(t == "campo" and v == ("Senha", "x" * 60) for t, v in L) and sum(1 for t, v in L if t == "campo" and v[1].startswith("x")) == 3,
   "texto longo quebrado em linhas de 60")
ok(any(t == "aviso" for t, _ in L), "folha inclui aviso de guarda/destruição")
for nome, porta, esperado in (("Microsoft Print to PDF", "PORTPROMPT:", True), ("Microsoft XPS Document Writer", "PORTPROMPT:", True),
                              ("OneNote (Desktop)", "nul:", True), ("EPSON L3250 Series", "USB001", False),
                              ("HP LaserJet", "IP_192.168.0.5", False), ("Impressora", "FILE:", True)):
    ok(c.impressora_gera_arquivo(nome, porta) == esperado, f"{nome} -> {'gera arquivo (alerta)' if esperado else 'papel'}")
# tamanhos das estruturas do Windows (x64): PRINTDLGW = 120, DOCINFOW = 40
import ctypes.wintypes as _w
class wintypes:   # tamanhos reais do Windows x64 (no Linux DWORD tem 8 bytes)
    DWORD = ctypes.c_uint32; WORD = ctypes.c_uint16; HWND = HGLOBAL = HDC = HINSTANCE = ctypes.c_void_p
    LPARAM = ctypes.c_int64; LPCWSTR = ctypes.c_wchar_p
c.EH_WINDOWS = True
exec(compile("""
class _PRINTDLGW(ctypes.Structure):
    _fields_ = [("lStructSize", wintypes.DWORD), ("hwndOwner", wintypes.HWND),
                ("hDevMode", wintypes.HGLOBAL), ("hDevNames", wintypes.HGLOBAL),
                ("hDC", wintypes.HDC), ("Flags", wintypes.DWORD),
                ("nFromPage", wintypes.WORD), ("nToPage", wintypes.WORD),
                ("nMinPage", wintypes.WORD), ("nMaxPage", wintypes.WORD),
                ("nCopies", wintypes.WORD), ("hInstance", wintypes.HINSTANCE),
                ("lCustData", wintypes.LPARAM), ("lpfnPrintHook", ctypes.c_void_p),
                ("lpfnSetupHook", ctypes.c_void_p), ("lpPrintTemplateName", wintypes.LPCWSTR),
                ("lpSetupTemplateName", wintypes.LPCWSTR), ("hPrintTemplate", wintypes.HGLOBAL),
                ("hSetupTemplate", wintypes.HGLOBAL)]
class _DOCINFOW(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_int), ("lpszDocName", wintypes.LPCWSTR),
                ("lpszOutput", wintypes.LPCWSTR), ("lpszDatatype", wintypes.LPCWSTR),
                ("fwType", wintypes.DWORD)]
""", "x", "exec"))
src = open(os.path.join(RAIZ, "cofre_senhas.py"), encoding="utf-8").read()
ok(src.count('("lStructSize", wintypes.DWORD), ("hwndOwner", wintypes.HWND)') == 1, "estrutura testada é a mesma do cofre")
ok(ctypes.sizeof(_PRINTDLGW) == 120, f"PRINTDLGW = {ctypes.sizeof(_PRINTDLGW)} bytes (Windows x64 exige 120)")
ok(ctypes.sizeof(_DOCINFOW) == 40, f"DOCINFOW = {ctypes.sizeof(_DOCINFOW)} bytes (Windows x64 exige 40)")
print("\nTODOS OK" if all(f) else f"\nFALHAS: {f.count(False)}")
sys.exit(0 if all(f) else 1)

# --- revisão da avaliação de força (palavra com enfeites, tamanho, frases longas) ---
def _n(x): return c.avaliar_forca(x)[0]
assert _n("Tr0ub4dor&3") <= 1, "palavra com troca de letras e enfeites é FRACA"
assert _n("Gabriel2020") <= 1 and _n("Brasil2024!") <= 1, "palavra + ano é FRACA"
assert _n("Zq9!vT#2") <= 2 and _n("Zq9!v") == 0, "senha curta não passa de Razoável / curtíssima é muito fraca"
assert c.avaliar_forca("Zq9!vT#2mL")[2] <= 75, "10 caracteres: teto de bits"
assert _n("Zq9!vT#2mLp@8xRwQ4$k") == 4, "20 aleatórios continua Muito forte"
assert _n("kajelopubamoxinu-wesidekomatuxabi") >= 3, "palavras longas aleatórias separadas por hífen não são rebaixadas a Fraca"
assert _n("cavalo azul come pizza na chuva") >= 3, "frase de 6 palavras é forte"
assert _n("minhasenhamuitolonga123456") <= 3, "palavras coladas + sequência não é Muito forte"
print("força revisada OK")
