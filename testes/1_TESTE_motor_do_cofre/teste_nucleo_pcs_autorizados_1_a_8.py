# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Computadores autorizados (fator extra): autorizar 1, 2, 3 ... ate 8 computadores e conferir que funciona direito.

Como "troca de computador" sem ter 8 computadores: o teste substitui identidades_do_pc() (o MachineGuid/SMBIOS lidos
do sistema) por uma identidade simulada por numero. Todo o resto e o codigo real do cofre: Argon2, AES, gravacao em
disco e releitura do arquivo.

O que e conferido:
  * 1 PC: ativa, devolve o codigo de recuperacao UMA vez; sem "liberar mais" o 2o PC e recusado;
  * liberar mais (sim) -> 2o, 3o ... 8o PC entram; a cada entrada o arquivo e relido do disco;
  * o PC recem-autorizado abre; os de fora recebem PcNaoAutorizado SEM gastar tentativa de senha;
  * o 9o PC e recusado e nada muda; o mesmo PC duas vezes e recusado;
  * itens, senha mestra e contagem de tentativas ficam intactos em todas as etapas;
  * codigo de recuperacao abre num PC nao autorizado; um codigo novo invalida o antigo;
  * remover PCs de 8 ate 1; o removido deixa de abrir; o ultimo nao sai (so "desativar"); desativar abre em qualquer PC;
  * nao da para voltar a "so 1 PC" com mais de um autorizado;
  * arquivo hostil: secao com 0 ou 9 computadores e recusada na leitura (ArquivoInvalido).
"""
import atexit
import hashlib
import os
import shutil
import sys
import tempfile

CODIGO_PULADO = 9
SENHA = "Senha-Mestra-De-Teste-14+"

TMP = tempfile.mkdtemp(prefix="cofre_nucleo_pcs_")
atexit.register(shutil.rmtree, TMP, True)
for _v in ("LOCALAPPDATA", "XDG_CONFIG_HOME", "APPDATA"):
    os.environ[_v] = os.path.join(TMP, "dados_" + _v.lower())      # sem segredo local: so a identidade simulada
os.environ["HOME"] = os.environ["USERPROFILE"] = os.path.join(TMP, "casa")


def _raiz():
    p = os.path.abspath(os.path.dirname(__file__))
    for _ in range(8):
        if os.path.exists(os.path.join(p, "cofre_senhas.py")):
            return p
        p = os.path.dirname(p)
    print("[PULADO] nao encontrei cofre_senhas.py")
    sys.exit(CODIGO_PULADO)


sys.path.insert(0, _raiz())
try:
    import cofre_senhas as cs
except ImportError as ex:
    print(f"[PULADO] dependencia ausente: {ex}")
    sys.exit(CODIGO_PULADO)

total, falhas = 0, []


def verifica(cond, msg, detalhe=""):
    global total
    total += 1
    if cond:
        print(f"  [OK]   {msg}")
    else:
        linha = msg + (f"  ->  {detalhe}" if detalhe else "")
        print(f"  [FALHOU] {linha}")
        falhas.append(linha)
    return bool(cond)


# ---------------------------------------------------------------------------------------------------------------
# "este computador" simulado
# ---------------------------------------------------------------------------------------------------------------
PC = [1]


def identidade(n):
    return hashlib.sha256(b"cofre-teste-pc-simulado|%d" % n).digest()


cs.identidades_do_pc = lambda: [identidade(PC[0])]


def como_pc(n):
    PC[0] = n


def abrir(caminho, **kw):
    kw.setdefault("senha", SENHA)
    # consulta=True (padrao do teste): abre SEM gravar. Uma abertura normal regrava o arquivo e o cofre `cof`, que
    # o teste ainda mantem aberto, passaria a receber ConflitoGravacao em todo salvar seguinte. Quem precisa gravar
    # (cof_ref) pede consulta=False.
    kw.setdefault("consulta", True)
    return cs.Cofre.abrir(caminho, **kw)


def abre_como(caminho, n, **kw):
    """True/None: abriu (devolve o cofre) ou a excecao levantada."""
    como_pc(n)
    try:
        return abrir(caminho, **kw)
    except Exception as ex:                      # noqa: BLE001 - o teste quer saber QUAL erro
        return ex


def itens_de(cof):
    """Itens como BYTES: Cofre.fechar() zera as strings dos itens no lugar, e os literais do teste seriam atingidos."""
    return sorted((r["servico"].encode(), r["login"].encode(), r["senha"].encode()) for r in cof.registros)


ITENS = [dict(servico="Banco Azul", login="ana", senha="s1-Banco-Azul!"),
         dict(servico="Instagram", login="ana2", senha="s2-Insta-Longa!"),
         dict(servico="Netflix", login="pai", senha="s3-Netflix-2026!")]
ESPERADO = sorted((i["servico"].encode(), i["login"].encode(), i["senha"].encode()) for i in ITENS)


def principal():
    print("=== Computadores autorizados: de 1 ate 8 ===")
    caminho = os.path.join(TMP, "cofre.dat")
    como_pc(1)
    cof = cs.Cofre.criar(caminho, SENHA, max_tentativas=5, modo=cs.MODO_S, nivel="alto")
    for dados in ITENS:
        cof.registros.append(cs.novo_item(**dados))
    cof.salvar()
    tent0 = cs.tentativas_restantes(caminho)

    print("\n== 1 computador")
    verifica(cof.pc is None and cof.limite_pc() == 1, "cofre novo: sem computadores autorizados, limite 1")
    codigo = cof.pc_adicionar("PC 1")
    verifica(isinstance(codigo, str) and len(codigo) >= 30, "o 1o computador devolve o codigo de recuperacao", repr(codigo))
    cof.salvar()
    verifica(len(cof.pc["maquinas"]) == 1 and cof.pc_id_deste() is not None, "1 computador autorizado e reconhecido")
    try:
        como_pc(2)
        cof.pc_adicionar("PC 2")
        verifica(False, "2o computador sem 'liberar mais' deveria ser recusado")
    except ValueError as ex:
        verifica("limitado a 1" in str(ex), "2o computador sem 'liberar mais' e recusado com mensagem clara", str(ex))
    verifica(len(cof.pc["maquinas"]) == 1, "a lista continua com 1 computador depois da recusa")
    como_pc(1)
    r = abre_como(caminho, 1)
    verifica(not isinstance(r, Exception) and itens_de(r) == ESPERADO, "PC 1 abre o cofre do disco com os itens intactos",
             repr(r))
    if not isinstance(r, Exception):
        r.fechar()
    r = abre_como(caminho, 2)
    verifica(isinstance(r, cs.PcNaoAutorizado), "PC 2 (nao autorizado) recebe PcNaoAutorizado", repr(r))
    verifica(cs.tentativas_restantes(caminho) == tent0, "PcNaoAutorizado NAO gasta tentativa de senha",
             f"{cs.tentativas_restantes(caminho)} != {tent0}")

    print("\n== liberar mais e autorizar do 2o ao 8o")
    como_pc(1)
    cof.definir_pcs_multiplos(True)
    cof.salvar()
    verifica(cof.limite_pc() == cs.MAX_PC == 8, "'liberar mais' sobe o limite para 8", str(cof.limite_pc()))
    for n in range(2, cs.MAX_PC + 1):
        como_pc(n)
        antes = cof.estado_pc()
        try:
            cod = cof.pc_adicionar(f"PC {n}")
            cof.salvar()
        except Exception as ex:                  # noqa: BLE001
            verifica(False, f"autorizar o PC {n}", repr(ex))
            cof.restaurar_pc(antes)
            continue
        verifica(cod is None, f"PC {n}: nao gera outro codigo de recuperacao (so o 1o)")
        verifica(len(cof.pc["maquinas"]) == n, f"PC {n}: lista com {n} computadores", str(len(cof.pc["maquinas"])))
        nomes = [m["nome"] for m in cof.pc["maquinas"]]
        verifica(nomes == [f"PC {i}" for i in range(1, n + 1)], f"PC {n}: nomes e ordem corretos", str(nomes))
        ids = {m["id"] for m in cof.pc["maquinas"]}
        verifica(len(ids) == n, f"PC {n}: identificadores todos diferentes")
        # o que esta no DISCO
        r = abre_como(caminho, n)
        verifica(not isinstance(r, Exception) and itens_de(r) == ESPERADO,
                 f"PC {n}: o recem-autorizado abre o cofre relido do disco, itens intactos", repr(r))
        if not isinstance(r, Exception):
            verifica(len(r.pc["maquinas"]) == n and r.pcs_multiplos() and r.limite_pc() == 8,
                     f"PC {n}: o arquivo guarda {n} computadores e o limite 8")
            r.fechar()
        if n in (2, 4, 8):                       # varredura completa so em alguns marcos (cada abertura custa Argon2)
            for k in range(1, n + 1):
                r = abre_como(caminho, k)
                verifica(not isinstance(r, Exception) and itens_de(r) == ESPERADO,
                         f"com {n} autorizados, o PC {k} continua abrindo", repr(r))
                if not isinstance(r, Exception):
                    r.fechar()
        if n == 4:                               # com vaga sobrando, repetir um PC ja autorizado e recusado
            como_pc(2)
            try:
                cof.pc_adicionar("PC 2 de novo")
                verifica(False, "autorizar o mesmo computador duas vezes deveria ser recusado")
            except ValueError as ex:
                verifica("já está autorizado" in str(ex), "o mesmo PC duas vezes e recusado", str(ex))
            verifica(len(cof.pc["maquinas"]) == 4, "depois da repeticao recusada continuam 4 computadores")
            como_pc(n)
        if n < cs.MAX_PC:
            r = abre_como(caminho, n + 1)
            verifica(isinstance(r, cs.PcNaoAutorizado), f"com {n} autorizados, o PC {n + 1} (de fora) e recusado",
                     repr(r))
        verifica(cs.tentativas_restantes(caminho) == tent0, f"PC {n}: nenhuma tentativa gasta ate aqui",
                 f"{cs.tentativas_restantes(caminho)} != {tent0}")

    print("\n== limites")
    como_pc(9)
    antes = cof.estado_pc()
    try:
        cof.pc_adicionar("PC 9")
        verifica(False, "o 9o computador deveria ser recusado")
    except ValueError as ex:
        verifica("Limite de 8" in str(ex), "o 9o computador e recusado: 'Limite de 8 ...'", str(ex))
    verifica(len(cof.pc["maquinas"]) == 8, "depois da recusa continuam 8 computadores")
    como_pc(1)
    try:
        cof.definir_pcs_multiplos(False)
        verifica(False, "voltar a 'so 1 PC' com 8 autorizados deveria ser recusado")
    except ValueError as ex:
        verifica("Remova" in str(ex), "nao deixa limitar a 1 computador enquanto ha mais de um", str(ex))
    verifica(cof.pcs_multiplos(), "o limite 8 continua ativo depois da tentativa de reduzir")
    cof.restaurar_pc(antes)

    print("\n== nomes dos computadores (limites e Unicode)")
    caminho2 = os.path.join(TMP, "nomes.dat")
    como_pc(1)
    c2 = cs.Cofre.criar(caminho2, SENHA, max_tentativas=5, modo=cs.MODO_S, nivel="alto")
    c2.definir_pcs_multiplos(True)
    nomes_teste = ["", "A" * 200, "Computador da Sala é ç ã", "😀" * 40, "linha1\nlinha2", "<b>x</b>"]
    for i, nome in enumerate(nomes_teste, start=1):
        como_pc(i)
        try:
            c2.pc_adicionar(nome)
        except Exception as ex:                  # noqa: BLE001
            verifica(False, f"nome {nome[:12]!r}...: autorizar", repr(ex))
    try:
        c2.salvar()
        r = abre_como(caminho2, 1)
        verifica(not isinstance(r, Exception) and len(r.pc["maquinas"]) == len(nomes_teste),
                 "nomes extremos (vazio, 200 letras, emoji, quebra de linha) gravam e reabrem", repr(r))
        if not isinstance(r, Exception):
            verifica(all(len(m["nome"].encode("utf-8")) <= 60 for m in r.pc["maquinas"]),
                     "nenhum nome passa de 60 bytes no arquivo")
            verifica(r.pc["maquinas"][0]["nome"] == "Computador", "nome vazio vira 'Computador'")
            r.fechar()
    except Exception as ex:                      # noqa: BLE001
        verifica(False, "gravar/reabrir com nomes extremos", repr(ex))
    c2.fechar()

    print("\n== codigo de recuperacao")
    como_pc(99)
    r = abre_como(caminho, 99)
    verifica(isinstance(r, cs.PcNaoAutorizado), "PC 99 (de fora) nao abre so com a senha", repr(r))
    r = abre_como(caminho, 99, recuperacao=codigo)
    verifica(not isinstance(r, Exception) and itens_de(r) == ESPERADO,
             "PC 99 abre com senha + codigo de recuperacao, itens intactos", repr(r))
    if not isinstance(r, Exception):
        r.fechar()
    como_pc(1)
    novo = cof.novo_codigo_recuperacao()
    cof.salvar()
    verifica(novo != codigo and isinstance(novo, str), "novo codigo de recuperacao e diferente do antigo")
    r = abre_como(caminho, 99, recuperacao=novo)
    verifica(not isinstance(r, Exception) and itens_de(r) == ESPERADO, "o codigo NOVO abre em PC de fora", repr(r))
    if not isinstance(r, Exception):
        r.fechar()
    r = abre_como(caminho, 99, recuperacao=codigo)
    verifica(isinstance(r, cs.SenhaIncorreta), "o codigo ANTIGO deixou de funcionar", repr(r))
    como_pc(1)
    r = abre_como(caminho, 1)       # abrir direito zera/restaura a contagem
    verifica(not isinstance(r, Exception), "depois de um erro, o PC 1 ainda abre normalmente", repr(r))
    if not isinstance(r, Exception):
        r.fechar()

    print("\n== remover de 8 ate 1")
    como_pc(1)
    cof_ref = abre_como(caminho, 1, consulta=False)
    if isinstance(cof_ref, Exception):
        verifica(False, "reabrir o cofre para remover computadores", repr(cof_ref))
        return
    for n in range(8, 1, -1):
        alvo = next(m for m in cof_ref.pc["maquinas"] if m["nome"] == f"PC {n}")
        cof_ref.pc_remover(alvo["id"])
        cof_ref.salvar()
        verifica(len(cof_ref.pc["maquinas"]) == n - 1, f"PC {n} removido: restam {n - 1}")
        r = abre_como(caminho, n)
        verifica(isinstance(r, cs.PcNaoAutorizado), f"o PC {n} removido deixa de abrir", repr(r))
        r = abre_como(caminho, 1)
        verifica(not isinstance(r, Exception) and itens_de(r) == ESPERADO,
                 f"depois de remover o PC {n}, o PC 1 continua abrindo com os itens intactos", repr(r))
        if not isinstance(r, Exception):
            r.fechar()
    como_pc(1)
    try:
        cof_ref.pc_remover(cof_ref.pc["maquinas"][0]["id"])
        verifica(False, "remover o unico computador deveria ser recusado")
    except ValueError as ex:
        verifica("unico" in str(ex).lower() or "único" in str(ex), "o ultimo computador nao sai (so 'Desativar')", str(ex))
    try:
        cof_ref.definir_pcs_multiplos(False)
        cof_ref.salvar()
        verifica(cof_ref.limite_pc() == 1, "com 1 computador, voltar a 'so 1 PC' e permitido")
    except ValueError as ex:
        verifica(False, "voltar a 'so 1 PC' com 1 computador", str(ex))
    cof_ref.desativar_pc()
    cof_ref.salvar()
    r = abre_como(caminho, 99)
    verifica(not isinstance(r, Exception) and itens_de(r) == ESPERADO and r.pc is None,
             "desativar: o cofre abre em qualquer computador, sem codigo, itens intactos", repr(r))
    if not isinstance(r, Exception):
        r.fechar()
    verifica(cs.info_pc(caminho) == (False, True), "info_pc diz 'sem exigencia de computador' depois de desativar")
    cof_ref.fechar()
    cof.fechar()

    print("\n== arquivo hostil: quantidade de computadores")
    maquina = {"nome": "x", "id": bytes(8), "nonce": bytes(12), "wrap": bytes(48)}
    for qtd, deve_aceitar in ((1, True), (8, True), (0, False), (9, False), (255, False)):
        pc = {"salt": bytes(32), "rec": (bytes(16), bytes(12), bytes(48)), "maquinas": [dict(maquina)] * qtd}
        try:
            bruto = bytearray(cs._serializar_secao(None, pc))
        except Exception:                        # 255 cabe em um byte; 0 e serializavel; qualquer erro aqui e ruido
            continue
        try:
            _, lido, _ = cs._ler_secao(bytes(bruto), 0)
            aceitou = lido is not None and len(lido["maquinas"]) == qtd
        except cs.ArquivoInvalido:
            aceitou = False
        verifica(aceitou == deve_aceitar, f"leitura da secao com {qtd} computadores: "
                 f"{'aceita' if deve_aceitar else 'recusa (ArquivoInvalido)'}")


if __name__ == "__main__":
    try:
        principal()
    finally:
        cs.Cofre.executor_salvar = None
    print(f"PASSOU {total - len(falhas)} / {total}")
    print(f"FALHAS: {len(falhas)}")
    for f in falhas[:40]:
        print(f"   - {f}")
    sys.exit(1 if falhas else 0)
