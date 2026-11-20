"""Checksum v5 e defeitos de mídia: setor zerado, setor 0xFF, cauda cortada, lixo no final, arquivo vazio, setores trocados.
Regra: nenhum desses danos pode gastar tentativa, destruir o cofre ou deixar a interface sem saída: o programa recusa abrir
(ArquivoCorrompido/ArquivoInvalido), o arquivo fica EXATAMENTE como estava e a cópia de segurança mais recente restaura o cofre."""
import os, sys, tempfile, shutil, importlib.util
spec = importlib.util.spec_from_file_location("c", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "cofre_senhas.py"))
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
FAL = []


def ok(cond, msg):
    print(("  [OK]   " if cond else "  [FALHOU] ") + msg, flush=True)
    if not cond:
        FAL.append(msg)


S = "cavalo azul come pizza na chuva 2026"
d = tempfile.mkdtemp(); P = os.path.join(d, "cofre.dat")
v = c.Cofre.criar(P, S, 5, 0, "alto"); K = v.chave_gerada
for i in range(40):
    v.registros.append({"id": f"i{i}", "servico": f"Serv{i}", "login": f"u{i}", "senha": f"Sx{i}-" + "k" * 30, "notas": "n" * 400})
v.salvar()
v.registros[0]["notas"] = "editado"; v.salvar(forcar_copia=True)     # a cópia .bak1 guarda o estado ANTERIOR (os 40 itens)
v.registros[0]["notas"] = "n" * 400; v.salvar()
bom = open(P, "rb").read(); h = c._ler_cabecalho(bom); n = len(bom)
print(f"cofre de {n} bytes; cabeçalho {h['hl']} bytes; dados a partir de {h['ini_dados']}")


def tenta(nome, dados, esperar_restauro=True):
    open(P, "wb").write(dados)
    for f in os.listdir(d):
        if f != "cofre.dat" and not f.endswith((".bak1", ".bak2", ".bak3", ".bak4", ".bak5", ".diag")):
            os.remove(os.path.join(d, f))
    try:
        c.Cofre.abrir(P, senha=S); r = "abriu"
    except (c.ArquivoCorrompido, c.ArquivoInvalido) as ex:
        r = type(ex).__name__
    except Exception as ex:
        r = "ERRO " + type(ex).__name__
    intacto = os.path.exists(P) and open(P, "rb").read() == dados
    ok(r in ("ArquivoCorrompido", "ArquivoInvalido") and intacto, f"{nome}: {r}; arquivo intacto e nada apagado")
    if len(dados) > h["hl"] and h["hl"] < len(dados):
        ok(open(P, "rb").read()[h["hl"]] == bom[h["hl"]] or r == "ArquivoInvalido", f"{nome}: contador de tentativas preservado")
    # a cópia de segurança restaura (se o cofre ainda existe como arquivo)
    if esperar_restauro:
        try:
            c.restaurar_copia(P)
            v2 = c.Cofre.abrir(P, senha=S)
            ok(len(v2.registros) == 40, f"{nome}: restaurar a cópia recupera os 40 itens")
        except Exception as ex:
            ok(False, f"{nome}: restauro falhou: {type(ex).__name__} {ex}")


# 1) danos NO CABEÇALHO e na seção FIDO (pegos pelo checksum, sem derivar nada)
z = bytearray(bom); z[0:512] = b"\x00" * 512
tenta("primeiro setor (512 B) zerado", bytes(z))
z = bytearray(bom); z[8:h["hl"]] = b"\xff" * (h["hl"] - 8)
tenta("cabeçalho todo 0xFF (magia preservada)", bytes(z))
if any(bom[h["hl"] + 1:h["ini_dados"]]):                  # só faz sentido quando há seção FIDO preenchida
    z = bytearray(bom); z[h["hl"] + 1:h["ini_dados"]] = b"\x00" * (h["ini_dados"] - h["hl"] - 1)
    tenta("seção FIDO zerada", bytes(z))
# 2) cortes e lixo
tenta("cortado ao meio", bom[:n // 2])
tenta("cortado só no último byte", bom[:-1])
tenta("cortado no meio do cabeçalho", bom[:h["hl"] - 5], esperar_restauro=True)
tenta("lixo de 4 KiB colado no fim", bom + os.urandom(4096))
tenta("zeros de preenchimento colados no fim", bom + b"\x00" * 4096)
tenta("arquivo vazio", b"")
tenta("só o cabeçalho", bom[:h["hl"] + 1])
# 3) dano nos DADOS cifrados (exige derivar a chave: poucos casos)
z = bytearray(bom); a = h["ini_dados"] + 64; z[a:a + 512] = b"\x00" * 512
tenta("setor de dados zerado", bytes(z))
z = bytearray(bom); a = h["ini_dados"] + 64; z[a:a + 512] = b"\xff" * 512
tenta("setor de dados 0xFF", bytes(z))
z = bytearray(bom)
if n > h["ini_dados"] + 2048:
    z[h["ini_dados"] + 100:h["ini_dados"] + 612], z[h["ini_dados"] + 1100:h["ini_dados"] + 1612] = z[h["ini_dados"] + 1100:h["ini_dados"] + 1612], z[h["ini_dados"] + 100:h["ini_dados"] + 612]
    tenta("dois setores de dados trocados de lugar", bytes(z))
print("\nFALHAS:", FAL)
sys.exit(1 if FAL else 0)
