"""Arquivos de apoio do cofre escondidos e protegidos depois da instalação (Oculto+Sistema+Somente leitura).
Usa um 'Windows de mentira' (atributos guardados num dicionário) para provar a lógica em qualquer sistema:
 - só o que é do cofre é marcado (cofre, cópias, .diag, .lock, logs); o PRÓPRIO PROGRAMA (.exe) NUNCA é escondido
   (é a única coisa que deve continuar visível na pasta -- não existe mais nenhum .bat/.sha256 "de fora" dele);
   um .sha256 de uma instalação ANTIGA ainda é escondido/limpo por compatibilidade; qualquer .bat e os arquivos
   do usuário também NÃO são tocados;
 - revelar desfaz exatamente a marca (e mantém outros atributos);
 - rodando o .py solto (não compilado) nada é escondido;
 - depois de revelar, o cofre abre, salva e se autodestrói normalmente."""
import os, sys, tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
import cofre_senhas as c
f = []
def ok(cond, nome):
    """Registra uma verificação."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))

W = tempfile.mkdtemp(prefix="ocultar_")
def toca(nome, dado=b"x"):
    """Cria um arquivo (ou pasta, se o nome terminar em /) dentro da pasta de teste."""
    p = os.path.join(W, nome.rstrip("/"))
    if nome.endswith("/"): os.makedirs(p, exist_ok=True)
    else: open(p, "wb").write(dado)
    return p
cofre = os.path.join(W, "cofre.dat")
senha = "cavalo azul come pizza na chuva"
v = c.Cofre.criar(cofre, senha, 5, c.MODO_S, "alto"); v.registros.append(c.novo_item(servico="B", login="a", senha="s-123")); v.salvar(); v.fechar()
for n in ("cofre.dat.bak1", "cofre.dat.bak2", "cofre.dat.diag", "cofre.dat.lock", "cofre.dat.gravar.lock", "cofre.dat.danificado",
          "CofreSenhas.exe", "CofreSenhas.sha256", "avisos_vistos.json", "instalacao_detalhada.log",
          "Abrir_Cofre.bat", "script_proprio_do_usuario.bat", "minhas_fotos.jpg", "cofre.txt", "README.md"):
    # CofreSenhas.sha256 simula sobra de uma instalação ANTIGA (limpa/escondida por compatibilidade); versões
    # atuais do instalador não criam mais esse arquivo. Abrir_Cofre.bat simula um .bat qualquer (de uma versão
    # antiga, ou um script próprio do usuário): nenhum .bat é escondido, por segurança.
    toca(n)
toca("logs/"); toca("_cb_cache/"); toca("pasta_do_usuario/")
exe = os.path.join(W, "CofreSenhas.exe")

# --- Windows de mentira: atributos em dicionário
atr = {}
FA_DIR = 0x10
def ler(p):
    """Atributos simulados (None se o arquivo não existe)."""
    if not os.path.exists(p): return None
    return atr.get(p, FA_DIR if os.path.isdir(p) else 0x20)
def grav(p, v):
    """Grava atributos simulados."""
    atr[p] = v; return True
orig = (c._ler_atributos, c._gravar_atributos)
c._ler_atributos, c._gravar_atributos = ler, grav
try:
    nomes = lambda: sorted(os.path.basename(a) for a in c.arquivos_de_apoio(cofre, exe))
    esperado = sorted(["cofre.dat", "cofre.dat.bak1", "cofre.dat.bak2", "cofre.dat.diag", "cofre.dat.lock",
                       "cofre.dat.gravar.lock",
                       "cofre.dat.danificado", "CofreSenhas.sha256", "avisos_vistos.json",
                       "instalacao_detalhada.log", "logs", "_cb_cache"])
    ok(nomes() == esperado, f"lista de apoio exata ({len(esperado)} itens)")
    ok("CofreSenhas.exe" not in nomes(), "o PRÓPRIO PROGRAMA (.exe) nunca é escondido -- é a única coisa que deve continuar visível")
    ok("Abrir_Cofre.bat" not in nomes() and "script_proprio_do_usuario.bat" not in nomes(), "nenhum .bat é escondido")
    ok(not ({"minhas_fotos.jpg", "cofre.txt", "README.md", "pasta_do_usuario"} & set(nomes())), "arquivos/pastas do usuário não são tocados")
    n = c.ocultar_apoio(cofre, exe)
    ok(n == len(esperado), f"ocultar_apoio marcou {n}")
    H, S, R = 2, 4, 1
    ok(all(ler(os.path.join(W, a)) & (H | S | R) == (H | S | R) for a in esperado if a not in ("logs", "_cb_cache")), "arquivos: Oculto+Sistema+Somente leitura")
    ok(all(ler(os.path.join(W, a)) & (H | S) == (H | S) and not ler(os.path.join(W, a)) & R for a in ("logs", "_cb_cache")), "pastas: Oculto+Sistema (sem Somente leitura)")
    ok(all(not ler(os.path.join(W, a)) & H for a in ("CofreSenhas.exe", "Abrir_Cofre.bat", "minhas_fotos.jpg", "README.md", "pasta_do_usuario")), "o resto (inclusive o próprio .exe) continua visível")
    atr[os.path.join(W, "cofre.dat")] |= 0x20 | 0x100                       # outro atributo qualquer
    c.ocultar_apoio(cofre, exe)                                              # idempotente
    m = c.revelar_apoio(cofre, exe)
    ok(m == len(esperado), f"revelar_apoio liberou {m}")
    ok(all(not ler(os.path.join(W, a)) & (H | S | R) for a in esperado), "depois de revelar nada tem Oculto/Sistema/Somente leitura")
    ok(ler(os.path.join(W, "cofre.dat")) & 0x100, "revelar preserva os outros atributos")
    # arquivo que não existe mais não quebra
    os.remove(os.path.join(W, "cofre.dat.bak2"))
    ok(c.ocultar_apoio(cofre, exe) == len(esperado) - 1, "arquivo ausente é ignorado")
    # sem programa informado: só o cofre e o apoio fixo
    ok("CofreSenhas.exe" not in [os.path.basename(a) for a in c.arquivos_de_apoio(cofre)], "sem exe informado, o programa não entra")
    c.revelar_apoio(cofre, exe)
    # pasta inexistente
    ok(c.arquivos_de_apoio(os.path.join(W, "nao_existe", "cofre.dat")) == [], "pasta inexistente → lista vazia")
finally:
    c._ler_atributos, c._gravar_atributos = orig

# --- liga/desliga
for var in ("COFRE_OCULTAR",):
    antes = os.environ.pop(var, None)
ok(c.ocultacao_ativa() is False, "rodando o .py solto (Linux/não compilado) nada é escondido")
os.environ["COFRE_OCULTAR"] = "1"; ok(c.ocultacao_ativa() is True, "COFRE_OCULTAR=1 liga")
os.environ["COFRE_OCULTAR"] = "0"; ok(c.ocultacao_ativa() is False, "COFRE_OCULTAR=0 desliga")
os.environ.pop("COFRE_OCULTAR", None)
# fora do Windows as funções reais são no-op (None / False); no Windows real elas realmente escondem/protegem o
# arquivo (é o próprio recurso sendo testado de verdade, pela 1ª vez aqui, sem o 'Windows de mentira' de cima) -
# por isso NUNCA usar "and" entre ocultar e revelar: se ocultar_apoio tiver marcado algo (n > 0), o "and" encerraria
# a expressão antes de chamar revelar_apoio, deixando cofre.dat de verdade oculto/protegido/somente-leitura e
# quebrando o v.salvar() do passo seguinte.
if c.EH_WINDOWS:
    marcados = c.ocultar_apoio(cofre, exe)
    liberados = c.revelar_apoio(cofre, exe)                                 # sempre chamado, desfaz de verdade
    ok(marcados > 0, f"no Windows ocultar_apoio esconde/protege de verdade ({marcados} marcado(s))")
    ok(liberados == marcados, f"revelar_apoio libera tudo que ocultar_apoio marcou ({liberados}/{marcados})")
    ok(c._ler_atributos(cofre) is not None, "no Windows _ler_atributos lê atributos reais (não é no-op)")
else:
    ok(c._ler_atributos(cofre) is None and c._gravar_atributos(cofre, 0) is False, "fora do Windows as funções reais não fazem nada")
    ok(c.ocultar_apoio(cofre, exe) == 0 and c.revelar_apoio(cofre, exe) == 0, "fora do Windows ocultar/revelar retornam 0")

# --- o cofre continua funcionando normalmente (revelado)
v = c.Cofre.abrir(cofre, senha=senha); v.registros.append(c.novo_item(servico="C", login="b", senha="t-456")); v.salvar()
ok(len(v.registros) == 2, "cofre abre e salva depois de revelar"); v.fechar()
c.destruir(cofre)
ok(not os.path.exists(cofre) and not os.path.exists(cofre + ".bak1"), "autodestruição apaga tudo")
print("FALHAS:", f.count(False)); sys.exit(1 if False in f else 0)
