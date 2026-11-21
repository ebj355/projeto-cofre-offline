# -*- coding: utf-8 -*-
"""
Queda de energia SIMULADA durante o salvamento do cofre.

Um processo "escritor" abre um cofre descartavel e salva sem parar (cada salvamento troca um contador dentro de um
item). O teste mata esse processo de forma brusca (TerminateProcess / SIGKILL, sem nenhuma chance de limpeza) em
instantes aleatorios, varias vezes, e depois confere:

  1. o cofre ABRE (diretamente ou, se o arquivo principal estiver danificado, apos restaurar_copia);
  2. nenhum salvamento CONFIRMADO ao escritor foi perdido (contador aberto >= ultimo confirmado - tolerancia de copias);
  3. o contador nunca passa do ultimo salvamento INICIADO (nada "do futuro");
  4. a senha continua valendo e o cofre aceita um novo salvamento;
  5. sobras de .tmp e de trava nao impedem abrir de novo.

LIMITES: matar o processo NAO e o mesmo que cortar a energia da maquina (o sistema operacional ainda termina de
gravar o que ja estava no cache). Para a queda real, use a VM: com o escritor rodando, use "Desligar a energia" no
programa de VM e depois rode este mesmo teste com --so-conferir PASTA. Um pendrive puxado de verdade tambem e
ensaio manual (veja o roteiro de usabilidade/ensaios).

Uso:  python teste_queda_de_energia_simulada.py                 (30 rodadas, pasta temporaria)
      python teste_queda_de_energia_simulada.py --rodadas 100
      python teste_queda_de_energia_simulada.py --pasta H:\\teste_queda   (grava no pendrive de TESTE; nunca no real)
      python teste_queda_de_energia_simulada.py --so-conferir PASTA       (depois de desligar a VM no meio)
Codigo de saida 1 se houver [FALHOU].
"""
import os
import sys
import time
import random
import shutil
import tempfile
import subprocess

AQUI = os.path.dirname(os.path.abspath(__file__))
SENHA = "SenhaDeTeste-queda-14c"


def achar_programa():
    pasta = AQUI
    for _ in range(6):
        if os.path.isfile(os.path.join(pasta, "cofre_senhas.py")):
            return pasta
        pasta = os.path.dirname(pasta)
    return None


def carregar():
    sys.path.insert(0, achar_programa())
    import cofre_senhas as C
    return C


# ------------------------------------------------------------------ escritor (processo que sera morto)
def escritor(caminho):
    """Salva sem parar. Avisa na saida padrao: INICIO n antes de salvar e FIM n depois que salvar() voltou."""
    C = carregar()
    c = C.Cofre.abrir(caminho, senha=SENHA)
    item = c.registros[0]
    n = int(item["notas"] or 0)
    while True:
        n += 1
        print(f"INICIO {n}", flush=True)
        item["notas"] = str(n)
        c.salvar(forcar_copia=(n % 3 == 0))
        print(f"FIM {n}", flush=True)


def matar(proc):
    try:
        proc.kill()                      # Windows: TerminateProcess; Linux: SIGKILL
    except OSError:
        pass
    proc.wait()


# ------------------------------------------------------------------ conferencia
def conferir(C, caminho, minimo, maximo, rotulo):
    """Retorna (lista de falhas, contador lido, usou_restauracao)."""
    falhas, usou = [], None
    try:
        c = C.Cofre.abrir(caminho, senha=SENHA)
    except (C.ArquivoInvalido, C.ErroGravacao, OSError, ValueError) as e:
        usou = C.restaurar_copia(caminho)
        if not usou:
            return [f"{rotulo}: o cofre nao abre ({type(e).__name__}: {e}) e nao ha copia valida"], None, None
        try:
            c = C.Cofre.abrir(caminho, senha=SENHA)
        except Exception as e2:
            return [f"{rotulo}: nem a copia restaurada ({usou}) abre ({type(e2).__name__}: {e2})"], None, usou
    except C.SenhaIncorreta:
        return [f"{rotulo}: SENHA INCORRETA depois da queda (a senha mestra foi danificada!)"], None, None
    except Exception as e:
        return [f"{rotulo}: erro inesperado ao abrir: {type(e).__name__}: {e}"], None, None
    try:
        lido = int(c.registros[0]["notas"] or 0)
    except (IndexError, ValueError, KeyError):
        falhas.append(f"{rotulo}: o item de controle sumiu ou ficou ilegivel")
        c.fechar()
        return falhas, None, usou
    # copias de seguranca sao feitas so a cada 10 min/forcadas; se precisou restaurar, aceita voltar atras
    # ate a ultima copia. Sem restauracao, nenhum salvamento confirmado pode ser perdido.
    if usou is None and lido < minimo:
        falhas.append(f"{rotulo}: salvamento CONFIRMADO perdido (confirmado {minimo}, no arquivo {lido})")
    if lido > maximo:
        falhas.append(f"{rotulo}: contador {lido} maior que o ultimo salvamento iniciado ({maximo})")
    try:
        c.registros[0]["notas"] = str(max(lido, maximo) + 1)
        c.salvar()
    except Exception as e:
        falhas.append(f"{rotulo}: o cofre abriu mas nao aceitou novo salvamento ({type(e).__name__}: {e})")
    c.fechar()
    return falhas, lido, usou


def main():
    args = sys.argv[1:]
    if "--escritor" in args:
        escritor(args[args.index("--escritor") + 1])
        return 0
    if achar_programa() is None:
        print("[FALHOU] nao achei cofre_senhas.py nesta pasta nem nas de cima.")
        return 1
    C = carregar()
    if "--so-conferir" in args:
        pasta = args[args.index("--so-conferir") + 1]
        caminho = os.path.join(pasta, "cofre.dat")
        f, lido, usou = conferir(C, caminho, 0, 10 ** 9, "apos queda real")
        for x in f:
            print("[FALHOU]", x)
        if not f:
            print(f"[OK] cofre abre apos a queda (contador {lido}{', restaurado de ' + usou if usou else ''})")
        return 1 if f else 0

    rodadas = int(args[args.index("--rodadas") + 1]) if "--rodadas" in args else 30
    base = args[args.index("--pasta") + 1] if "--pasta" in args else None
    pasta = tempfile.mkdtemp(prefix="queda_", dir=base) if base else tempfile.mkdtemp(prefix="queda_")
    caminho = os.path.join(pasta, "cofre.dat")
    print(f"Pasta de teste: {pasta}  (cofre descartavel; nunca use o cofre real)")
    c = C.Cofre.criar(caminho, SENHA, nivel="alto")
    c.registros.append(C.novo_item(servico="controle", notas="0"))
    c.salvar(forcar_copia=True)
    c.fechar()

    falhas_total, restauracoes, confirmado, iniciado = 0, 0, 0, 0
    rnd = random.Random(20261120)
    for i in range(1, rodadas + 1):
        proc = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--escritor", caminho],
                                stdout=subprocess.PIPE, text=True, bufsize=1)
        alvo = time.time() + rnd.uniform(0.3, 4.0)      # momento da "queda" (sorteado)
        # le a saida sem travar: thread leitora
        import threading
        estado = {"ini": iniciado, "fim": confirmado}

        def ler():
            for linha in proc.stdout:
                p = linha.split()
                if len(p) == 2 and p[1].isdigit():
                    estado["ini" if p[0] == "INICIO" else "fim"] = int(p[1])
        t = threading.Thread(target=ler, daemon=True)
        t.start()
        while time.time() < alvo and proc.poll() is None:
            time.sleep(0.01)
        matar(proc)
        t.join(timeout=2)
        iniciado, confirmado = max(iniciado, estado["ini"]), max(confirmado, estado["fim"])
        f, lido, usou = conferir(C, caminho, confirmado, iniciado, f"rodada {i}")
        if usou:
            restauracoes += 1
        if f:
            falhas_total += len(f)
            for x in f:
                print("[FALHOU]", x)
        elif lido is not None:
            # conferir() gravou max(lido, iniciado)+1 como novo ponto de partida do proximo escritor
            confirmado = iniciado = max(lido, iniciado) + 1
            print(f"[OK] rodada {i}: morto com ~{estado['ini']} iniciados; cofre abre, contador {lido}"
                  f"{' (restaurado de ' + usou + ')' if usou else ''}")
    sobras = [n for n in os.listdir(pasta) if n.endswith(".tmp")]
    if sobras:
        print(f"[ALERTA] sobras de .tmp na pasta depois do teste: {sobras[:5]} (sao limpas na proxima abertura?)")
    print(f"\nResumo: {rodadas} quedas simuladas, {restauracoes} exigiram restaurar copia, {falhas_total} falha(s).")
    if restauracoes:
        print("[ALERTA] houve rodadas em que o arquivo principal nao abriu e a copia foi usada: "
              "investigue por que a gravacao atomica deixou o arquivo principal invalido.")
    if falhas_total == 0:
        shutil.rmtree(pasta, ignore_errors=True)
        print("[OK] nenhum dado confirmado perdido e o cofre sempre reabriu.")
        return 0
    print(f"[FALHOU] guarde a pasta para analise: {pasta}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
