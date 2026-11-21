# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Reune todos os erros da rodada em logs_de_compilacao/erros de compilação."""
import datetime
import os
import shutil
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESULTADOS = os.path.join(RAIZ, "testes", "resultados")
DESTINO = os.path.join(RAIZ, "logs_de_compilacao", "erros de compilação")


def contem_erro(linhas):
    marcadores = ("[FALHOU]", "[ALERTA]", "[ERRO]", "FALHAS:", "Traceback", "ERRO:")
    return any(any(marcador in linha for marcador in marcadores) for linha in linhas)


def principal():
    os.makedirs(DESTINO, exist_ok=True)
    encontrados = []
    if os.path.isdir(RESULTADOS):
        for nome in sorted(os.listdir(RESULTADOS)):
            origem = os.path.join(RESULTADOS, nome)
            if not os.path.isfile(origem) or not nome.lower().endswith(".txt"):
                continue
            try:
                with open(origem, "r", encoding="utf-8", errors="replace") as arquivo:
                    linhas = arquivo.readlines()
            except OSError:
                continue
            if contem_erro(linhas):
                destino = os.path.join(DESTINO, nome)
                shutil.copy2(origem, destino)
                encontrados.append((nome, destino))

    agora = datetime.datetime.now().isoformat(timespec="seconds")
    consolidado = os.path.join(DESTINO, "TODOS_OS_ERROS.txt")
    with open(consolidado, "w", encoding="utf-8", newline="\n") as saida:
        saida.write("ARCA SISTEMAS - TODOS OS ERROS DA BATERIA\n")
        saida.write("Gerado em: %s\n" % agora)
        saida.write("Arquivos com erro encontrados: %d\n\n" % len(encontrados))
        for nome, caminho in encontrados:
            saida.write("=" * 78 + "\n")
            saida.write("ARQUIVO: %s\n" % nome)
            saida.write("=" * 78 + "\n")
            with open(caminho, "r", encoding="utf-8", errors="replace") as origem:
                saida.write(origem.read())
            saida.write("\n")
    print("Erros da bateria reunidos em logs_de_compilacao\\erros de compilação")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
