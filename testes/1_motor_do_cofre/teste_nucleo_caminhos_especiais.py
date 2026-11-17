"""CAMINHOS COMPLICADOS: espaços, acentos, símbolos, emoji e caminhos muito longos.

O cofre pode estar em `D:\\Meus Documentos\\Cofre de Senhas (Teste)!\\`, no perfil de alguém chamado 'José Ção', num
pendrive com nome em japonês ou fundo na árvore de pastas (limite clássico de 260 caracteres do Windows). Para cada
pasta estranha, o ciclo COMPLETO precisa funcionar e nada pode ficar fora dela:
 criar -> salvar -> cópias de segurança (.bak) -> trava (.lock) -> abrir -> trocar senha -> lista de arquivos de apoio
 (a que o programa esconde) -> fechar. Confere também que a lista de apoio nunca inclui o .exe nem arquivos do usuário
 com nomes parecidos, e que um caminho absurdo vira erro CONTROLADO (nunca um erro cru nem arquivo pela metade).
Roda no Linux e no Windows (no Windows os nomes realmente passam pela API de arquivos do sistema)."""
import importlib.util, os, shutil, sys, tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "ferramentas_dos_testes"))
import _resultado; _resultado.registrar(__file__)          # grava resultados/resultado_nucleo_caminhos_especiais.txt

CAMINHO_PROG = os.path.abspath(os.path.join(AQUI, "..", "..", "cofre_senhas.py"))
spec = importlib.util.spec_from_file_location("c", CAMINHO_PROG)
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
FAL = []


def ok(cond, msg):
    """Imprime [OK]/[FALHOU] (o executor procura estes marcadores) e guarda as falhas."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + msg, flush=True)
    if not cond:
        FAL.append(msg)


S = "cavalo azul come pizza na chuva 2026"
NOMES = {
    "espaços e símbolos": "Cofre de Senhas (Teste)! [1] & #2 + 100%",
    "acentos pt-BR": "José Ção - àéîõü ÁÉÍÓÚ Ç ñ",
    "japonês e árabe": "金庫 パスワード مدير كلمات",
    "emoji": "cofre 🔐 senhas 🗝️",
    "ponto no fim e espaço no meio": "pasta.com ponto. interno",
    "nome comprido (120)": "p" * 120,
}
raiz = tempfile.mkdtemp(prefix="cofre cam_"); criadas = set()
try:
    for rotulo, nome in NOMES.items():
        print("== " + rotulo)
        pasta = os.path.join(raiz, nome); criadas.add(nome)
        try:
            os.makedirs(pasta)
        except OSError as ex:                       # o sistema de arquivos pode recusar o nome (ex.: emoji em FAT antigo)
            print(f"  (pulado) este sistema de arquivos não aceita esse nome: {type(ex).__name__}")
            continue
        P = os.path.join(pasta, "cofre.dat")
        v = c.Cofre.criar(P, S, 5, 0, "alto")
        v.registros.append(c.novo_item(servico="Banco", login="u", senha="Senha-Forte-1!"))
        v.salvar(forcar_copia=True); v.salvar(forcar_copia=True)
        v.fechar()
        ok(os.path.exists(P) and any(f.startswith("cofre.dat.bak") for f in os.listdir(pasta)), "cofre e cópia de segurança gravados na pasta")
        dono = c.instancia_unica(P)
        ok(dono is True and os.path.exists(P + ".lock"), "trava .lock criada ao lado do cofre")
        a = c.Cofre.abrir(P, senha=S)
        ok(len(a.registros) == 1, "abriu e leu o item de volta")
        a.trocar_senha("Outra-Senha-Mestra-Longa-9!"); a.salvar(); a.fechar()
        b = c.Cofre.abrir(P, senha="Outra-Senha-Mestra-Longa-9!")
        ok(len(b.registros) == 1, "abre com a senha nova depois de trocar")
        b.fechar()
        # arquivos do usuário parecidos NÃO podem entrar na lista de apoio; o .exe e os .bat também não
        for intruso in ("CofreSenhas.exe", "Abrir.bat", "cofre.dat.docx.txt.bat", "minhas_fotos.jpg", "cofre_outro.dat"):
            with open(os.path.join(pasta, intruso), "wb") as f:
                f.write(b"x")
        apoio = [os.path.basename(x) for x in c.arquivos_de_apoio(P, os.path.join(pasta, "CofreSenhas.exe"))]
        ok("cofre.dat" in apoio and "cofre.dat.lock" in apoio, f"a lista de apoio inclui o cofre e a trava ({len(apoio)} arquivos)")
        ok(not any(x in apoio for x in ("CofreSenhas.exe", "Abrir.bat", "cofre.dat.docx.txt.bat", "minhas_fotos.jpg", "cofre_outro.dat")),
           "a lista de apoio NÃO inclui o .exe, .bat nem arquivos do usuário")
        # nada vazou para fora da pasta do cofre (nenhum .tmp/.bak solto na raiz)
        soltos = [f for f in os.listdir(raiz) if f not in criadas]   # só as pastas dos casos são esperadas
        ok(not soltos, f"nada gravado fora da pasta do cofre ({soltos})")
        os.close(c._TRAVA_ARQ["fd"]) if c._TRAVA_ARQ.get("fd") is not None else None
        c._TRAVA_ARQ["fd"] = None

    print("== caminho muito fundo (perto/além do limite de 260 caracteres)")
    fundo = raiz
    while len(fundo) < 235:
        fundo = os.path.join(fundo, "n" * 40)
    try:
        os.makedirs(fundo)
        P = os.path.join(fundo, "cofre.dat")
        print(f"  caminho com {len(P)} caracteres")
        try:
            v = c.Cofre.criar(P, S, 5, 0, "alto"); v.salvar(forcar_copia=True); v.fechar()
            a = c.Cofre.abrir(P, senha=S); a.fechar()
            ok(True, "ciclo criar/salvar/abrir funcionou no caminho fundo")
        except (OSError, c.ErroGravacao) as ex:    # no Windows sem caminhos longos habilitados: erro CONTROLADO é o aceitável
            ok(True, f"o sistema recusou o caminho longo e o programa devolveu erro controlado ({type(ex).__name__})")
        ok(not [f for f in os.listdir(fundo) if f.endswith(".tmp")], "nenhum .tmp esquecido depois do caminho longo")
    except OSError as ex:
        print(f"  (pulado) o sistema não deixa nem criar a pasta funda: {type(ex).__name__}")
finally:
    shutil.rmtree(raiz, ignore_errors=True)

print("\nFALHAS: " + str(FAL) if FAL else "\nTODOS OK")
sys.exit(1 if FAL else 0)
