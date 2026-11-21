#!/usr/bin/env python3
# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Mudança de relógio e de fuso horário durante o uso (lacuna "relógio/fuso" do PLANO_DE_TESTES.md).

PCs antigos com pilha da BIOS fraca, ajuste manual de hora, correção por NTP e viagem entre fusos mexem no
relógio. O cofre depende do tempo em dois pontos:
  1) cópia de segurança automática (.bak1): renova se a data da cópia divergir do relógio atual por mais de 10 minutos;
  2) vigia da interface (App._vigiar_sistema): bloqueia se o relógio pula mais de 20 s (PC dormiu) e bloqueia
     60 s depois de perder o foco (BLOQUEIO_SEM_FOCO_S).
Não precisa de Tkinter: o vigia é chamado com um objeto de mentira no lugar da janela, e o relógio é simulado.

O que se espera (e o que cada seção cobre):
  - relógio errado NUNCA pode corromper ou perder dados, nem travar o abrir/salvar;
  - relógio errado NÃO pode desligar as proteções em silêncio: backup com data no futuro precisa continuar
    renovando, e o bloqueio por falta de foco precisa contar tempo REAL (time.monotonic), não a hora de parede.
"""
import os
import shutil
import sys
import tempfile
import threading
import time
import types
from unittest import mock

FALHAS = []


def ok(cond, msg):
    print(("  [OK]   " if cond else "  [FALHOU] ") + msg)
    if not cond:
        FALHAS.append(msg)


def _raiz():
    env = os.environ.get("COFRE_RAIZ")
    pasta = os.path.dirname(os.path.abspath(__file__))
    for p in ([env] if env else []) + [pasta]:
        while p and p != os.path.dirname(p):
            if os.path.isfile(os.path.join(p, "cofre_senhas.py")):
                return p
            p = os.path.dirname(p)
    print("ERRO: não achei cofre_senhas.py acima de", pasta)
    sys.exit(2)


sys.path.insert(0, _raiz())
import cofre_senhas as cs  # noqa: E402

SENHA = "Senha-de-teste-relogio-2026"
ANTIGO = dict(cs.NIVEIS)
cs.NIVEIS["alto"] = (1, 8192)          # custo mínimo aceito pelo formato; o teste não mede Argon2
TMP = tempfile.mkdtemp(prefix="arca_relogio_")


def novo_cofre(nome):
    pasta = os.path.join(TMP, nome)
    os.makedirs(pasta)
    caminho = os.path.join(pasta, "cofre.dat")
    return caminho, cs.Cofre.criar(caminho, SENHA, 3, cs.MODO_S, "alto")


def itens(caminho):
    c = cs.Cofre.abrir(caminho, senha=SENHA)
    try:
        return sorted(r["servico"] for r in c.registros)
    finally:
        c.fechar()


def adicionar(c, nome):
    c.registros.append(cs.novo_item(servico=nome, senha="x-" + nome))
    c.salvar()


try:
    print("1) Cópia de segurança automática com o relógio fora do lugar")
    caminho, c = novo_cofre("bak")
    b1 = caminho + ".bak1"
    ok(os.path.exists(b1), "cofre novo já nasce com a cópia .bak1")
    adicionar(c, "A")
    agora = time.time()
    ok(abs(agora - os.path.getmtime(b1)) < 120, "salvar com relógio normal mantém a .bak1 recente")

    # 1.1 relógio ficou ERRADO para o futuro numa gravação anterior: .bak1 ganhou data de 1 ano à frente
    futuro = time.time() + 365 * 86400
    os.utime(b1, (futuro, futuro))
    antes = open(b1, "rb").read()
    adicionar(c, "B")
    depois = open(b1, "rb").read()
    ok(antes != depois,
       ".bak1 com data no futuro é renovada ao salvar pela diferença absoluta, sem esperar o relógio alcançá-la")

    # 1.2 relógio volta 2 h DEPOIS de uma cópia nova: não dá para distinguir de "arquivo com data futura", então
    # renovar a cópia é aceitável (backup a mais é inofensivo; backup a menos não é). Exige-se só integridade.
    t = time.time()
    os.utime(b1, (t, t))
    with mock.patch.object(cs.time, "time", lambda: t - 7200):
        adicionar(c, "C")
    try:
        cs._ler_cabecalho(open(b1, "rb").read())
        bak_valida = True
    except Exception:      # noqa: BLE001
        bak_valida = False
    ok(bak_valida, "relógio 2 h atrás logo após uma cópia: salvar funciona e a .bak1 continua sendo um cofre válido")

    # 1.3 relógio MUITO adiantado (ano 2100): grava e abre normalmente, cópias renovam
    with mock.patch.object(cs.time, "time", lambda: t + 75 * 365 * 86400):
        adicionar(c, "D")
    c.fechar()
    ok(itens(caminho) == ["A", "B", "C", "D"], "relógio em 2100 e depois volta: os 4 itens estão íntegros")

    # 1.4 relógio absurdo (antes de 1970 / negativo) não derruba gravação nem diagnóstico
    c = cs.Cofre.abrir(caminho, senha=SENHA)
    try:
        with mock.patch.object(cs.time, "time", lambda: -5.0):
            adicionar(c, "E")
            cs.diag_registrar(cs.DIAG_GRAVACAO, OSError(28, "teste"))
        ok(True, "relógio negativo: salvar e registrar diagnóstico não levantam exceção")
    except Exception as ex:   # noqa: BLE001
        ok(False, f"relógio negativo derrubou o cofre: {type(ex).__name__}: {ex}")
    c.fechar()
    ok(itens(caminho) == ["A", "B", "C", "D", "E"], "depois do relógio negativo os 5 itens continuam íntegros")

    print("\n2) O contador de versão (seq) não depende do relógio")
    caminho, c = novo_cofre("seq")
    seqs = []
    for rel, nome in ((t, "1"), (t - 86400, "2"), (t + 86400 * 30, "3"), (t - 3600, "4")):
        with mock.patch.object(cs.time, "time", lambda rel=rel: rel):
            adicionar(c, nome)
        seqs.append(c.meta["seq"])
    ok(seqs == sorted(seqs) and len(set(seqs)) == len(seqs), f"seq cresce a cada gravação, mesmo com o relógio indo e voltando {seqs}")
    c.fechar()
    ok(itens(caminho) == ["1", "2", "3", "4"], "os 4 itens gravados com relógios diferentes abrem juntos")

    print("\n3) Fuso horário e horário de verão")
    if hasattr(time, "tzset"):
        tz0 = os.environ.get("TZ")
        try:
            caminho, c = novo_cofre("fuso")
            os.environ["TZ"] = "UTC"
            time.tzset()
            adicionar(c, "UTC")
            c.fechar()
            for tz in ("America/Sao_Paulo", "Asia/Tokyo", "Pacific/Kiritimati", "Pacific/Pago_Pago"):
                os.environ["TZ"] = tz
                time.tzset()
                c = cs.Cofre.abrir(caminho, senha=SENHA)
                adicionar(c, "em " + tz)
                import datetime
                try:
                    datetime.datetime.fromisoformat(c.ultima_abertura)
                    iso_ok = True
                except Exception:      # noqa: BLE001
                    iso_ok = c.ultima_abertura in (None, "")
                c.fechar()
                ok(iso_ok, f"fuso {tz}: abre, grava e a 'última abertura' continua legível")
            ok(len(itens(caminho)) == 5, "os 5 itens gravados em fusos diferentes abrem juntos")
        finally:
            if tz0 is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = tz0
            time.tzset()
    else:
        print("  [INFO] Windows não tem time.tzset(): troca de fuso no mesmo processo não é simulável aqui. O ciclo "
              "abrir/gravar usa só time.time() (UTC) para decidir; o fuso só afeta o texto da 'última abertura'. "
              "Para ensaio real: mudar o fuso em Configurações > Hora e idioma com o cofre aberto.")
        caminho, c = novo_cofre("fuso")
        adicionar(c, "A")
        c.fechar()
        ok(itens(caminho) == ["A"], "ciclo básico abrir/gravar/abrir no Windows")

    print("\n4) Vigia da interface (App._vigiar_sistema) com relógio de parede x relógio monotônico")
    if cs.tk is None:
        cs.tk = types.SimpleNamespace(TclError=RuntimeError)       # só para o 'except tk.TclError' do vigia

    def janela(sem_foco=False, tique=1000.0):
        return types.SimpleNamespace(
            _ocultadores=False, _app_sem_foco=lambda: sem_foco, cofre=object(), _ultimo_gc=0.0,
            _sem_foco_desde=None, _ultimo_tique=tique, bloquear=mock.Mock(),
            _espias_pedido=threading.Event(), _espias_thread=mock.Mock(), _espias_res=None, _espias_erro=None,
            root=mock.Mock(), _mostrar_conteudo=lambda: None, _invasao_em_andamento=mock.Mock(),
            _vigiar_sistema=lambda: None)

    def volta(j, parede, mono):
        """Executa uma volta do vigia com os dois relógios simulados."""
        with mock.patch.object(cs.time, "time", lambda: parede), mock.patch.object(cs.time, "monotonic", lambda: mono), \
                mock.patch.object(cs, "sessao_bloqueada", lambda: False), \
                mock.patch.object(cs, "ambiente_suspeito", lambda: None):
            cs.App._vigiar_sistema(j)

    j = janela(tique=1000.0)
    volta(j, 1002.0, 1002.0)
    ok(not j.bloquear.called, "volta normal de 2 s: não bloqueia")

    j = janela(tique=1000.0)
    volta(j, 1000.0 + 3600, 1002.0)
    ok(j.bloquear.called, "relógio pulou +1 h (PC dormiu ou hora acertada): bloqueia (falha segura)")

    j = janela(tique=1000.0)
    volta(j, 1000.0 - 3600, 1002.0)
    ok(not j.bloquear.called, "relógio voltou 1 h: não toma isso por 'PC dormiu'")

    j = janela(sem_foco=True, tique=1000.0)
    volta(j, 1000.0, 1000.0)
    bloqueou_em = None
    for k in range(1, 1 + 2 * (cs.BLOQUEIO_SEM_FOCO_S + 20) // 2):
        j._ultimo_tique = 1000.0 + 2 * (k - 1)
        volta(j, 1000.0 + 2 * k, 1000.0 + 2 * k)
        if j.bloquear.called:
            bloqueou_em = 2 * k
            break
    ok(bloqueou_em is not None and bloqueou_em <= cs.BLOQUEIO_SEM_FOCO_S + 4,
       f"sem foco, relógio normal: bloqueia após ~{cs.BLOQUEIO_SEM_FOCO_S} s (bloqueou em {bloqueou_em} s)")

    # relógio de parede VOLTA 1 h no meio da espera; o tempo real (monotônico) segue normal
    j = janela(sem_foco=True, tique=1000.0)
    volta(j, 1000.0, 1000.0)
    bloqueou_em = None
    limite_real = cs.BLOQUEIO_SEM_FOCO_S + 20
    for k in range(1, limite_real // 2 + 1):
        j._ultimo_tique = (1000.0 - 3600 + 2 * (k - 1)) if k > 1 else 1000.0
        volta(j, 1000.0 - 3600 + 2 * k, 1000.0 + 2 * k)
        if j.bloquear.called:
            bloqueou_em = 2 * k
            break
    ok(bloqueou_em is not None and bloqueou_em <= cs.BLOQUEIO_SEM_FOCO_S + 4,
       "sem foco com o relógio de parede 1 h ATRÁS: o timer monotônico ainda bloqueia em tempo real "
       f"(bloqueou em {bloqueou_em} s, sem esperar o relógio alcançar o valor antigo)")
finally:
    cs.NIVEIS.clear()
    cs.NIVEIS.update(ANTIGO)
    shutil.rmtree(TMP, ignore_errors=True)

print()
print("FALHAS:", FALHAS)
sys.exit(1 if FALHAS else 0)
