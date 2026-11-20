"""Auxiliar dos testes (não é um teste): faz o teste gravar o SEU PRÓPRIO arquivo de resultado em
testes/resultados/resultado_<nome-do-teste>.txt, além de mostrar tudo na tela como sempre.

Por que existe: o dono do projeto quer que cada teste tenha o seu arquivo de resultado (nome individual, sem
sobrescrever o de outro teste), para mandar só o arquivo do teste que interessa. Uso, nas primeiras linhas do teste:

    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _resultado; _resultado.registrar(__file__)

Depois disso, tudo que o teste imprime (print) vai para a tela E para o arquivo. O arquivo é sobrescrito a cada
execução DO MESMO teste (nunca o de outro). Se a pasta resultados/ não puder ser gravada (pendrive protegido,
permissão), o teste segue normalmente só com a tela: gravar o resultado é uma conveniência, nunca pode derrubar o teste."""
import atexit
import datetime
import os
import platform
import shutil
import sys
import tempfile
import time


class _Duplicador:
    """Escreve no fluxo original (tela) e no arquivo ao mesmo tempo."""

    def __init__(self, original, arquivo):
        self._original = original
        self._arquivo = arquivo

    def write(self, texto):
        self._original.write(texto)
        try:
            self._arquivo.write(texto)
        except (OSError, ValueError):
            pass
        return len(texto)

    def flush(self):
        self._original.flush()
        try:
            self._arquivo.flush()
        except (OSError, ValueError):
            pass

    def __getattr__(self, nome):          # encoding, isatty, fileno... vêm do fluxo original
        return getattr(self._original, nome)


def registrar(arquivo_do_teste):
    """Liga a gravação do resultado deste teste. Devolve o caminho do arquivo (ou None se não deu para gravar)."""
    aqui = os.path.dirname(os.path.abspath(arquivo_do_teste))
    pasta = os.path.join(os.path.dirname(aqui), "resultados")           # testes/resultados
    nome = os.path.splitext(os.path.basename(arquivo_do_teste))[0]
    nome = nome[len("teste_"):] if nome.startswith("teste_") else nome
    destino = os.path.join(pasta, "resultado_" + nome + ".txt")
    baixa_prioridade()                    # o teste nunca deixa o PC lento
    esperar_memoria(800, 120, aviso=False)
    try:
        os.makedirs(pasta, exist_ok=True)
        arq = open(destino, "w", encoding="utf-8", errors="replace")
    except OSError:
        return None
    sys.stdout = _Duplicador(sys.stdout, arq)
    sys.stderr = _Duplicador(sys.stderr, arq)
    atexit.register(arq.close)
    return destino


def pasta_temporaria(prefixo):
    """Cria uma pasta temporária do teste e GARANTE que ela some ao terminar (mesmo se o teste falhar no meio),
    para os testes não deixarem lixo (com cofres de mentira dentro) espalhado em %TEMP%. Devolve o caminho."""
    d = tempfile.mkdtemp(prefix=prefixo)
    atexit.register(shutil.rmtree, d, True)
    return d


def pasta_resultados():
    """testes/resultados (criada se faltar)."""
    pasta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resultados")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def pasta_logs():
    """O log de depuração fica JUNTO dos resultados (testes/resultados/): tudo que os testes geram numa pasta só."""
    return pasta_resultados()


def log_depuracao(titulo, nome, comando, estado, segundos, saida, inicio=None):
    """Acrescenta ao LOG DE DEPURAÇÃO (testes/resultados/log_depuracao.txt) o que um teste fez: horário, comando,
    estado, duração e a SAÍDA COMPLETA (com tracebacks). É o arquivo para abrir quando algo falha e se quer saber
    por quê, sem rodar de novo. Nunca derruba o executor: se não der para gravar, segue em silêncio."""
    try:
        arq = os.path.join(pasta_logs(), "log_depuracao.txt")
        novo = not os.path.exists(arq) or os.path.getsize(arq) == 0
        with open(arq, "a", encoding="utf-8", errors="replace") as f:
            if novo:
                f.write("LOG DE DEPURAÇÃO DO COFRE DE SENHAS\n")
                f.write("Python %s | %s | %s\n" % (sys.version.split()[0], platform.platform(), platform.machine()))
                f.write("Gerado em %s\n" % datetime.datetime.now().isoformat(timespec="seconds"))
                f.write("=" * 78 + "\n")
            f.write("\n### [%s] %s\n" % (titulo, nome))
            f.write("início: %s | duração: %.1fs | estado: %s\n" % (
                (inicio or datetime.datetime.now()).isoformat(timespec="seconds"), segundos, estado))
            f.write("comando: %s\n" % " ".join(str(x) for x in comando))
            f.write("----- saída completa -----\n%s\n" % (saida or "(sem saída)"))
            f.write("-" * 78 + "\n")
    except Exception:
        pass


def gravar_resultado_executor(nome, estado, segundos, saida):
    """Grava a saída completa de qualquer teste do executor, mesmo sem registrar() no próprio teste."""
    base = os.path.splitext(os.path.basename(nome.replace("\\", "/")))[0]
    if base.startswith("teste_"):
        base = base[len("teste_"):]
    destino = "testes/resultados/resultado_" + base + ".txt"
    marca = "[FALHOU]" if estado.startswith("FALHOU") else "[PULADO]" if estado.startswith("PULADO") else "[OK]"
    try:
        destino = os.path.join(pasta_resultados(), "resultado_" + base + ".txt")
        with open(destino, "w", encoding="utf-8", errors="replace") as f:
            f.write("%s %s | %.1f s | %s\n\n" % (marca, nome, segundos, estado))
            f.write(saida or "(sem saída do teste)\n")
    except OSError as ex:
        print("AVISO: não foi possível gravar %s: %s" % (destino, ex), file=sys.stderr)


def handles_processo():
    """Quantos descritores (Linux) ou handles (Windows) este processo tem abertos; None se não der para medir.
    No Windows as funções precisam de tipos declarados: sem isso o pseudo-handle do processo (-1) é passado como inteiro de
    32 bits, a chamada falha e devolve 0 (a checagem de vazamento ficaria vazia e sempre 'passando')."""
    try:
        return len(os.listdir("/proc/self/fd"))
    except OSError:
        pass
    try:
        import ctypes
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.GetCurrentProcess.restype = wintypes.HANDLE
        k.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k.GetProcessHandleCount.restype = wintypes.BOOL
        n = wintypes.DWORD(0)
        if k.GetProcessHandleCount(k.GetCurrentProcess(), ctypes.byref(n)) and n.value > 0:
            return int(n.value)
    except Exception:
        pass
    return None


def objetos_gdi():
    """Objetos GDI + USER do processo (Windows); None fora do Windows ou se a chamada falhar (0 conta como falha)."""
    try:
        import ctypes
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        u = ctypes.WinDLL("user32", use_last_error=True)
        k.GetCurrentProcess.restype = wintypes.HANDLE
        u.GetGuiResources.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        u.GetGuiResources.restype = wintypes.DWORD
        h = k.GetCurrentProcess()
        total = int(u.GetGuiResources(h, 0)) + int(u.GetGuiResources(h, 1))      # 0 = GDI, 1 = USER
        return total if total > 0 else None
    except Exception:
        return None


# ---------------------------------------------------------------------------------------------------------------
# Respeito ao PC de quem roda os testes: memória livre, prioridade baixa e limpeza da bateria anterior
# ---------------------------------------------------------------------------------------------------------------
def memoria_livre_mb():
    """Memória RAM disponível agora, em MiB (Windows: GlobalMemoryStatusEx; Linux: /proc/meminfo). None se não souber."""
    try:
        with open("/proc/meminfo", encoding="ascii", errors="replace") as f:
            for linha in f:
                if linha.startswith("MemAvailable:"):
                    return int(linha.split()[1]) // 1024
    except OSError:
        pass
    try:
        import ctypes

        class MEM(ctypes.Structure):
            """MEMORYSTATUSEX do Windows."""
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MEM()
        m.dwLength = ctypes.sizeof(m)
        if ctypes.WinDLL("kernel32").GlobalMemoryStatusEx(ctypes.byref(m)):
            return int(m.ullAvailPhys // (1024 * 1024))
    except Exception:
        pass
    return None


def esperar_memoria(minimo_mb=1200, espera_max_s=180, aviso=True):
    """Espera (até 'espera_max_s') o PC ter pelo menos 'minimo_mb' MiB de RAM livre antes de começar algo pesado.
    Devolve True se há memória, False se acabou o prazo (quem chama decide se segue com cuidado). Nunca levanta erro."""
    inicio = time.time()
    avisou = False
    while True:
        livre = memoria_livre_mb()
        if livre is None or livre >= minimo_mb:
            return True
        if aviso and not avisou:
            print("  (pouca memória livre: %d MiB; esperando liberar %d MiB para não travar o PC...)" % (livre, minimo_mb), flush=True)
            avisou = True
        if time.time() - inicio >= espera_max_s:
            return False
        try:
            import gc
            gc.collect()
        except Exception:
            pass
        time.sleep(2)


def baixa_prioridade():
    """Põe ESTE processo em prioridade baixa (Windows: BELOW_NORMAL; Linux: nice 10): os testes não deixam o mouse,
    o teclado e os outros programas lentos. Nunca levanta erro."""
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.GetCurrentProcess.restype = wintypes.HANDLE
            k.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            k.SetPriorityClass(k.GetCurrentProcess(), 0x00004000)        # BELOW_NORMAL_PRIORITY_CLASS
        else:
            os.nice(10)
    except Exception:
        pass


# arquivos GERADOS por uma bateria (cada bateria nova apaga os da anterior, para nunca misturar "ontem" com "hoje")
_GERADOS = ("resultado_*.txt", "RESULTADO COMPLETO.txt", "resumo_testes.md", "resumo_testes.json",
            "resultados.sarif", "log_depuracao*.txt",
            "limpeza_artefatos.txt", "cobertura_codigo.*", "cobertura_html.zip", ".coverage*", ".coveragerc", "*.tmp")


def limpar_resultados_antigos():
    """Apaga os resultados da bateria anterior em testes/resultados/ e leva para a pasta certa o que não é resultado
    (documentos .md vão para testes/6_TESTE_ferramentas_dos_testes/, relatorio_pentest.md para testes/3_TESTE_ataques_simulados/). Devolve a lista do que fez."""
    import fnmatch
    feitos = []
    pasta = pasta_resultados()
    aqui = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for nome in sorted(os.listdir(pasta)):
        caminho = os.path.join(pasta, nome)
        try:
            if os.path.isdir(caminho):
                if nome == "cobertura_html" or nome.startswith("rodada_") or nome == "ferramentas_externas":
                    shutil.rmtree(caminho, True)
                    feitos.append("apagada pasta " + nome)
                continue
            if any(fnmatch.fnmatch(nome, g) for g in _GERADOS):
                os.remove(caminho)
                feitos.append("apagado " + nome)
            elif nome.lower().endswith(".md"):
                destino = os.path.join(aqui, "3_TESTE_ataques_simulados" if nome.startswith("relatorio_pentest") else "6_TESTE_ferramentas_dos_testes", nome)
                if os.path.exists(destino):
                    os.remove(destino)
                shutil.move(caminho, destino)
                feitos.append("movido " + nome + " -> " + os.path.relpath(destino, aqui))
        except OSError as e:
            feitos.append("não deu para tratar %s: %s" % (nome, e))
    return feitos
