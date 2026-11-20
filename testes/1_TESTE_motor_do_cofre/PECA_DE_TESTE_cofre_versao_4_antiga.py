#!/usr/bin/env python3
"""
Cofre de Senhas — gerenciador de senhas 100% local, criptografado, com autodestruição.
Não usa internet em nenhum momento.

Desbloqueio (escolhido ao criar o cofre):
  - DOIS FATORES: senha mestra E chave de acesso (token) obrigatórias juntas; ou
  - senha mestra OU chave de acesso.
  A chave de acesso tem 160 bits aleatórios (XXXX-XXXX-...), digitada ou lida de um .key.
  Opcional: CHAVE FIDO2 física (YubiKey etc., extensão hmac-secret/PRF) como fator extra,
  com várias chaves cadastradas (principal + reserva) e código de recuperação em papel.

Criptografia:
  - Dados cifrados em CASCATA: ChaCha20-Poly1305 dentro de AES-256-GCM, com chaves
    derivadas independentes de uma chave interna aleatória de 256 bits.
  - Senha mestra: Argon2id (Máxima: 1 GiB e 6 iterações; Alta: 256 MiB e 4 iterações).
  - Cabeçalho autenticado; dados preenchidos em blocos de 4 KiB (esconde a quantidade de itens).

Autodestruição (arquivo sobrescrito com dados aleatórios e apagado):
  - ao esgotar as tentativas (gastas ANTES de testar a senha);
  - ao detectar adulteração do arquivo ou do contador de tentativas;
  - ao detectar depurador (engenharia reversa) ligado ao programa.

Proteções de tela/teclado (Windows): janela invisível a prints e gravações, teclado
virtual embaralhado, bloqueio de cópia nos campos, área de transferência fora do
histórico, bloqueio ao minimizar/inatividade, aviso de área de trabalho remota.

Armazenamento: "cofre.dat" na MESMA pasta do programa, ou outro caminho:
    python cofre_senhas.py E:\\minha_pasta\\cofre.dat

Importação: planilhas Excel (.xlsx/.xlsm) e CSV (inclusive exportações do Chrome/Samsung Pass).

Dependências:  pip install cryptography argon2-cffi openpyxl defusedxml fido2
"""
import os
import re
import sys
import json
import base64
import math
import zlib
import shutil
import struct
import secrets
import string
import time
import threading

EH_WINDOWS = sys.platform == "win32"
if EH_WINDOWS:
    import ctypes
    from ctypes import wintypes


def _aviso_fatal(titulo, texto):
    """Mostra um aviso mesmo sem console (pythonw / .exe) e sem Tkinter."""
    try:
        if EH_WINDOWS:
            ctypes.windll.user32.MessageBoxW(None, str(texto), str(titulo), 0x10)
            return
    except Exception:
        pass
    print(f"{titulo}\n{texto}")


def _registrar_erro(texto):
    """Grava o erro em 'erro_cofre.log' ao lado do programa (só o texto do erro; nunca senhas)."""
    try:
        import datetime
        base = os.path.dirname(os.path.abspath(sys.argv[0] if sys.argv and sys.argv[0] else __file__))
        arq = os.path.join(base, "erro_cofre.log")
        try:
            if os.path.getsize(arq) > 200 * 1024:       # limite: guarda só o log anterior (.1)
                os.replace(arq, arq + ".1")
        except OSError:
            pass
        with open(arq, "a", encoding="utf-8") as f:
            f.write(f"--- {datetime.datetime.now().isoformat(timespec='seconds')} ---\n{texto}\n")
    except Exception:
        pass

try:
    from argon2.low_level import hash_secret_raw, Type
    from argon2.exceptions import HashingError
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    from cryptography.exceptions import InvalidTag
except ImportError:
    _aviso_fatal("Cofre de Senhas", "Faltam bibliotecas do Python.\n\nAbra o PowerShell e rode:\n"
                 "    python -m pip install cryptography argon2-cffi openpyxl defusedxml fido2")
    sys.exit(1)

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    from tkinter import font as tkfont
except ImportError:
    tk = None

# ----------------------------------------------------------------------------
# Núcleo criptográfico
# ----------------------------------------------------------------------------
ARQUIVO_PADRAO = "cofre.dat"

# Formato atual (v3): cascata ChaCha20-Poly1305 + AES-256-GCM, modo de desbloqueio, nível
MAGIC = b"COFRE04\x00"            # v4 = v3 + seção FIDO depois do contador
MAGIC_V3 = b"COFRE03\x00"
# MAGIC | t | m | p | max_t | modo | sal_pw | nonce_pw | wrap_pw | sal_k | nonce_k | wrap_k | nonce_chacha | nonce_aes
HEADER_FMT = ">8sIIBBB16s12s48s16s12s48s12s12s"
HEADER_LEN = struct.calcsize(HEADER_FMT)
POS_CONTADOR = HEADER_LEN          # 1 byte: tentativas restantes (fora do AAD)
POS_DADOS = HEADER_LEN + 1

# Formatos antigos, só para converter cofres criados por versões anteriores
MAGIC_V2 = b"COFRE02\x00"
HEADER_V2_FMT = ">8sIIBB16s12s48s16s12s48s12s"
MAGIC_V1 = b"COFRE01\x00"
HEADER_V1_FMT = ">8sIIBB16s12s"
HEADER_V1_LEN = struct.calcsize(HEADER_V1_FMT)

WRAP_AAD = b"COFRE02\x00"         # dado autenticado dos "embrulhos" da chave interna

MODO_OU = 0                        # abre com senha OU chave de acesso
MODO_E = 1                         # exige senha E chave de acesso juntas (dois fatores)

# Níveis do Argon2id: (iterações, memória em KiB)
NIVEIS = {"alto": (4, 262144),     # 256 MiB por tentativa
          "maximo": (6, 1048576)}  # 1 GiB por tentativa
LIMITE_COFRE = 200 * 1024 * 1024  # tamanho máximo aceito para um arquivo de cofre
RP_ID = "cofre-de-senhas.local"    # identificador do cofre para as chaves FIDO
MAX_FIDO = 8
TAM_BLOCO = 4096                   # dados preenchidos até múltiplo disto (esconde a quantidade de itens)

PARALELISMO = 2
MIN_SENHA = 14


class SenhaIncorreta(Exception):
    def __init__(self, restantes):
        super().__init__(f"Senha ou chave incorreta. Tentativas restantes: {restantes}")
        self.restantes = restantes


class CofreDestruido(Exception):
    pass


class ErroGravacao(OSError):
    """Não foi possível gravar o cofre (pendrive cheio, protegido ou removido)."""


class ArquivoInvalido(Exception):
    pass


class ArquivoCorrompido(ArquivoInvalido):
    """O arquivo do cofre está danificado (setor ruim, cópia incompleta, byte alterado).
    NUNCA apaga nada: orienta a restaurar a cópia de segurança."""


class ChaveMalFormada(Exception):
    pass


class FidoErro(Exception):
    """Problema com a chave FIDO (cancelada, ausente, não cadastrada...). Não gasta tentativa."""
    pass


class FatorFaltando(Exception):
    """Cofre em modo dois fatores: falta a senha ou a chave (não gasta tentativa)."""
    pass


class ViolacaoDetectada(Exception):
    """Senha/chave corretas, mas o conteúdo foi alterado: arquivo adulterado."""
    pass


SENHAS_COMUNS = ("senha", "password", "123456", "qwerty", "abcdef", "admin", "brasil",
                 "iloveyou", "letmein", "000000", "111111", "abc123", "teste")


def avaliar_senha(senha):
    """Retorna None se aceitável, ou o motivo da recusa."""
    if len(senha) < MIN_SENHA:
        return f"Use pelo menos {MIN_SENHA} caracteres (uma frase de 4–5 palavras é o ideal)."
    if len(set(senha)) < 8:
        return "Senha muito repetitiva. Use mais caracteres diferentes."
    if senha.isdigit():
        return "Senha só com números é fácil de adivinhar. Use palavras."
    baixa = senha.lower()
    for comum in SENHAS_COMUNS:
        if comum in baixa and len(baixa.replace(comum, "")) < 10:
            return f'A senha é baseada em "{comum}", que está em listas de senhas vazadas.'
    for seq in ("0123456789", "abcdefghijklmnopqrstuvwxyz", "qwertyuiop", "asdfghjkl"):
        for i in range(len(seq) - 5):
            if seq[i:i + 6] in baixa:
                return "A senha contém uma sequência óbvia (como 123456 ou qwerty)."
    return None


VERSAO_PROGRAMA = "2026.11.10.3"            # o instalador escolhe o cofre_senhas.py de maior versão
COMPILADO = "__compiled__" in globals()        # True no .exe gerado pelo Nuitka


def ambiente_suspeito():
    """Detecta depuradores (ferramentas de engenharia reversa) ligados ao programa."""
    if COMPILADO and sys.gettrace() is not None:
        # (Rodando como .py, IDEs como VS Code/PyCharm usam isso normalmente; não é ataque.)
        return "Um depurador Python está monitorando o programa."
    if EH_WINDOWS:
        try:
            if ctypes.windll.kernel32.IsDebuggerPresent():
                return "Um depurador está ligado ao programa."
            presente = wintypes.BOOL(False)
            ctypes.windll.kernel32.CheckRemoteDebuggerPresent(
                ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(presente))
            if presente.value:
                return "Um depurador externo está ligado ao programa."
        except Exception:
            pass
    return None


def sessao_remota():
    if EH_WINDOWS:
        try:
            return bool(ctypes.windll.user32.GetSystemMetrics(0x1000))   # SM_REMOTESESSION
        except Exception:
            return False
    return False


# ----------------------------------------------------------------------------
# Blindagem do processo (Windows): memória trancada, anti-injeção,
# sem despejo de memória em travamento e detecção de ferramentas espiãs
# ----------------------------------------------------------------------------
# Ninguém além do SYSTEM pode ler/escrever a memória, injetar código ou mudar
# estas regras; os outros programas só podem ver que o cofre existe e fechá-lo.
_SDDL_TRANCADO = "D:P(A;;GA;;;SY)(A;;0x101001;;;OW)(A;;0x101001;;;WD)"
_SDDL_NORMAL = "D:P(A;;GA;;;SY)(A;;GA;;;OW)(A;;0x101001;;;WD)"
BLINDAGEM = []                       # o que foi aplicado (para mostrar na tela)
_trava_dacl = threading.Lock()

FERRAMENTAS_ESPIAS = {
    # depuradores e desmontadores
    "x64dbg.exe", "x32dbg.exe", "x96dbg.exe", "ollydbg.exe", "windbg.exe", "windbgx.exe",
    "dbgx.shell.exe", "cdb.exe", "ntsd.exe", "kd.exe", "immunitydebugger.exe", "ida.exe",
    "ida64.exe", "idaq.exe", "idaq64.exe", "radare2.exe", "r2.exe", "binaryninja.exe",
    "dnspy.exe", "dnspy-x86.exe", "ghidrarun.exe",
    # leitores/editores de memória, injetores e copiadores de memória
    "cheatengine.exe", "cheatengine-x86_64.exe", "cheatengine-i386.exe",
    "cheatengine-x86_64-sse4-avx2.exe", "processhacker.exe", "systeminformer.exe",
    "reclass.exe", "reclass.net.exe", "reclassex64.exe", "scylla.exe", "scylla_x64.exe",
    "scylla_x86.exe", "pe-sieve32.exe", "pe-sieve64.exe", "hollows_hunter32.exe",
    "hollows_hunter64.exe", "extremeinjector.exe", "apimonitor-x64.exe", "apimonitor-x86.exe",
    "frida.exe", "frida-server.exe", "procdump.exe", "procdump64.exe", "procdump64a.exe",
    "dumpit.exe", "magnetramcapture.exe", "ramcapture.exe", "ramcapture64.exe",
    "ftk imager.exe", "memoryze.exe",
}
PREFIXOS_ESPIOES = ("winpmem",)
ACESSO_REMOTO = {
    "teamviewer.exe", "anydesk.exe", "rustdesk.exe", "aa_v3.exe", "ammyy_admin.exe",
    "rutserv.exe", "rfusclient.exe", "tvnserver.exe", "winvnc.exe", "vncserver.exe",
    "screenconnect.windowsclient.exe", "supremo.exe", "srserver.exe", "remoting_host.exe",
    "quickassist.exe", "remotepcservice.exe", "dwrcs.exe", "netsupport.exe", "client32.exe",
}


def _api():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    a = ctypes.WinDLL("advapi32", use_last_error=True)
    a.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    a.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
    a.SetKernelObjectSecurity.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p]
    a.SetKernelObjectSecurity.restype = wintypes.BOOL
    k.LocalFree.argtypes = [ctypes.c_void_p]
    k.LocalFree.restype = ctypes.c_void_p
    k.GetCurrentProcess.restype = wintypes.HANDLE
    k.GetCurrentProcess.argtypes = []
    return k, a


def _aplicar_dacl(sddl):
    """Troca as regras de acesso ao próprio processo do cofre."""
    if not EH_WINDOWS:
        return False
    try:
        k, a = _api()
        sd = ctypes.c_void_p()
        if not a.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(sd), None):
            return False
        try:
            return bool(a.SetKernelObjectSecurity(k.GetCurrentProcess(), 4, sd))   # DACL_SECURITY_INFORMATION
        finally:
            k.LocalFree(sd)
    except Exception:
        return False


class processo_liberado:
    """Afrouxa a trava de memória só durante o toque na chave FIDO (a janela do
    Windows Hello precisa conversar com o cofre) e tranca de novo logo depois."""
    def __enter__(self):
        if "memoria" in BLINDAGEM:
            with _trava_dacl:
                _aplicar_dacl(_SDDL_NORMAL)
        return self

    def __exit__(self, *exc):
        if "memoria" in BLINDAGEM:
            with _trava_dacl:
                _aplicar_dacl(_SDDL_TRANCADO)
        return False


def blindar_processo():
    """Aplica as defesas do Windows no processo do cofre. Cada uma é independente:
    se o Windows não aceitar alguma, ela é pulada e o cofre continua funcionando."""
    BLINDAGEM.clear()
    if not EH_WINDOWS:
        return BLINDAGEM
    try:
        k, _ = _api()
    except Exception:
        return BLINDAGEM
    # 1) memória trancada: outros programas não leem, não escrevem e não injetam código
    if _aplicar_dacl(_SDDL_TRANCADO):
        BLINDAGEM.append("memoria")
    # 2) políticas de mitigação do próprio Windows
    try:
        k.SetProcessMitigationPolicy.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t]
        k.SetProcessMitigationPolicy.restype = wintypes.BOOL
        for nome, politica, bits in (
                ("ganchos", 6, 0x1),          # bloqueia DLLs de ganchos globais, AppInit e LSP
                ("dlls", 10, 0x1 | 0x2 | 0x4),  # DLL só local/confiável, nunca de rede ou de baixa integridade
                ("fontes", 9, 0x1)):          # só fontes do sistema (falhas em fontes são porta de ataque)
            v = wintypes.DWORD(bits)
            try:
                if k.SetProcessMitigationPolicy(politica, ctypes.byref(v), ctypes.sizeof(v)):
                    BLINDAGEM.append(nome)
            except Exception:
                pass
    except Exception:
        pass
    # 3) a pasta atual deixa de ser usada para procurar DLLs (contra DLL falsa ao lado do programa)
    try:
        k.SetDllDirectoryW.argtypes = [wintypes.LPCWSTR]
        k.SetDllDirectoryW.restype = wintypes.BOOL
        if k.SetDllDirectoryW(""):
            BLINDAGEM.append("busca_dll")
    except Exception:
        pass
    # 4) se o cofre travar, o Windows não grava a memória dele (com senhas) em disco
    try:
        k.SetErrorMode(0x0001 | 0x0002 | 0x8000)
        wer = ctypes.WinDLL("wer.dll")
        wer.WerAddExcludedApplication.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
        wer.WerAddExcludedApplication.restype = ctypes.c_long
        buf = ctypes.create_unicode_buffer(1024)
        k.GetModuleFileNameW.argtypes = [ctypes.c_void_p, wintypes.LPWSTR, wintypes.DWORD]
        if k.GetModuleFileNameW(None, buf, 1024):
            if wer.WerAddExcludedApplication(os.path.basename(buf.value), False) >= 0:
                BLINDAGEM.append("sem_despejo")
    except Exception:
        pass
    return BLINDAGEM


def processos_abertos():
    """Nomes (minúsculos) dos programas em execução."""
    nomes = set()
    if not EH_WINDOWS:
        return nomes

    class _PE32(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]
    try:
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PE32)]
        k.Process32FirstW.restype = wintypes.BOOL
        k.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PE32)]
        k.Process32NextW.restype = wintypes.BOOL
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        h = k.CreateToolhelp32Snapshot(0x2, 0)                 # TH32CS_SNAPPROCESS
        if not h or h == ctypes.c_void_p(-1).value:
            return nomes
        try:
            pe = _PE32()
            pe.dwSize = ctypes.sizeof(_PE32)
            ok = k.Process32FirstW(h, ctypes.byref(pe))
            while ok:
                nomes.add(pe.szExeFile.lower())
                ok = k.Process32NextW(h, ctypes.byref(pe))
        finally:
            k.CloseHandle(h)
    except Exception:
        pass
    return nomes


def ferramentas_espias(nomes=None):
    nomes = processos_abertos() if nomes is None else nomes
    return sorted(n for n in nomes if n in FERRAMENTAS_ESPIAS or n.startswith(PREFIXOS_ESPIOES))


def acesso_remoto_aberto(nomes=None):
    nomes = processos_abertos() if nomes is None else nomes
    return sorted(n for n in nomes if n in ACESSO_REMOTO)


def pasta_base():
    """Pasta onde fica o programa (o cofre é salvo ao lado dele)."""
    if "__compiled__" in globals():             # executável gerado pelo Nuitka
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    if getattr(sys, "frozen", False):           # executável gerado pelo PyInstaller
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def derivar_chave(senha, sal, t, m, p):
    try:
        return hash_secret_raw(secret=senha.encode("utf-8"), salt=sal, time_cost=t,
                               memory_cost=m, parallelism=p, hash_len=32, type=Type.ID)
    except HashingError as ex:           # sem memória livre para o Argon2 (ex.: blindagem Máxima = 1 GiB)
        raise MemoryError(str(ex)) from ex


def kek_da_chave(chave_bytes, sal):
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=sal,
                info=b"cofre-chave-de-acesso").derive(chave_bytes)


def kek_combinada(kek_senha, chave_bytes, sal):
    """Modo dois fatores: a chave só existe com a senha E a chave de acesso juntas."""
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=sal,
                info=b"cofre-senha-E-chave").derive(kek_senha + chave_bytes)


def _embrulhar(kek, dek):
    nonce = secrets.token_bytes(12)
    return nonce, AESGCM(kek).encrypt(nonce, dek, WRAP_AAD)


def _desembrulhar(kek, nonce, embrulho):
    return AESGCM(kek).decrypt(nonce, embrulho, WRAP_AAD)   # InvalidTag se errado


def _subchaves(dek):
    """Duas chaves independentes para as duas camadas da cascata."""
    k_cha = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"cofre-camada-chacha20").derive(dek)
    k_aes = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"cofre-camada-aes256").derive(dek)
    return k_cha, k_aes


def _chave_dados(dek, fator_fido):
    """Sem FIDO: a chave interna. Com FIDO: chave interna + segredo do fator FIDO."""
    if fator_fido is None:
        return dek
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=b"cofre-dados-com-fido").derive(dek + fator_fido)


def _kek_fido(saida_hmac):
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=b"cofre-kek-chave-fido").derive(saida_hmac)


def _kek_recuperacao(codigo_bytes, sal):
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=sal,
                info=b"cofre-codigo-recuperacao-fido").derive(codigo_bytes)


def _serializar_fido(fido):
    if not fido:
        return b"\x00"
    out = bytearray(b"\x01")
    out.append(len(fido["chaves"]))
    out += fido["salt"]
    sal, nonce, wrap = fido["rec"]
    out += sal + nonce + wrap
    for ch in fido["chaves"]:
        nome = ch["nome"].encode("utf-8")[:60]
        out.append(len(nome))
        out += nome
        out += struct.pack(">H", len(ch["cred"])) + ch["cred"]
        out += ch["nonce"] + ch["wrap"]
    return bytes(out)


def _ler_fido(bruto, pos):
    """Lê a seção FIDO a partir de 'pos'. Retorna (fido ou None, posição final)."""
    def pegar(n):
        nonlocal pos
        if pos + n > len(bruto):
            raise ArquivoInvalido("Seção FIDO do cofre corrompida.")
        v = bruto[pos:pos + n]
        pos += n
        return v
    flag = pegar(1)[0]
    if flag == 0:
        return None, pos
    if flag != 1:
        raise ArquivoInvalido("Seção FIDO do cofre inválida (arquivo adulterado?).")
    n = pegar(1)[0]
    if not 1 <= n <= MAX_FIDO:
        raise ArquivoInvalido("Seção FIDO do cofre inválida (arquivo adulterado?).")
    fido = {"salt": pegar(32), "rec": (pegar(16), pegar(12), pegar(48)), "chaves": []}
    for _ in range(n):
        nome = pegar(pegar(1)[0]).decode("utf-8", "replace")
        cred = pegar(struct.unpack(">H", pegar(2))[0])
        if not 16 <= len(cred) <= 1023:
            raise ArquivoInvalido("Seção FIDO do cofre inválida (arquivo adulterado?).")
        fido["chaves"].append({"nome": nome, "cred": cred, "nonce": pegar(12), "wrap": pegar(48)})
    return fido, pos


def nova_chave_acesso():
    """Retorna (bytes, texto) — 160 bits em base32: XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX."""
    b = secrets.token_bytes(20)
    txt = base64.b32encode(b).decode("ascii")
    return b, "-".join(txt[i:i + 4] for i in range(0, 32, 4))


def ler_chave_acesso(texto):
    limpo = re.sub(r"[^A-Za-z2-7]", "", texto or "").upper()
    if len(limpo) != 32:
        raise ChaveMalFormada("Formato de chave de acesso inválido (devem ser 32 caracteres "
                              "A–Z e 2–7, em 8 grupos de 4).")
    return base64.b32decode(limpo)


def _gravar_atomico(caminho, dados):
    tmp = caminho + ".tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(dados)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, caminho)
    except OSError:
        try:
            os.remove(tmp)          # não deixa pela metade; o cofre original continua intacto
        except OSError:
            pass
        raise


def _copias(caminho):
    return [caminho + ".bak1", caminho + ".bak2"]


def _todas_as_copias(caminho):
    """Tudo que guarda uma versão antiga do cofre ao lado dele (inclusive o arquivo danificado)."""
    return _copias(caminho) + [caminho + ".danificado"]


def destruir(caminho):
    """Sobrescreve o arquivo (e as cópias de segurança dele) com dados aleatórios e apaga tudo."""
    for extra in _todas_as_copias(caminho):
        if os.path.exists(extra):
            try:
                _destruir_um(extra)
            except OSError:
                pass
    _destruir_um(caminho)


def apagar_copias(caminho):
    """Remove as cópias de segurança antigas (usado quando a senha/chave muda: elas ainda abririam
    com a senha antiga)."""
    for extra in _todas_as_copias(caminho):
        if os.path.exists(extra):
            try:
                _destruir_um(extra)
            except OSError:
                pass


def _rodar_copias(caminho):
    """Antes de gravar: guarda o arquivo atual como .bak1 (o .bak1 anterior vira .bak2)."""
    try:
        with open(caminho, "rb") as f:
            atual = f.read(LIMITE_COFRE)
        if atual[:7] != MAGIC[:7]:
            return
        h = _ler_cabecalho(atual)
        atual = bytearray(atual)
        atual[h["hl"]] = h["max_t"]               # a cópia nasce com o contador cheio (sem falso alarme)
        atual = bytes(atual)
        b1, b2 = _copias(caminho)
        if os.path.exists(b1):
            with open(b1, "rb") as f:
                velho = f.read(LIMITE_COFRE)
            _gravar_atomico(b2, velho)
        _gravar_atomico(b1, atual)
    except OSError:
        pass                                  # cópia de segurança é bônus; nunca impede salvar


def restaurar_copia(caminho):
    """Troca o cofre danificado pela cópia de segurança válida mais recente. Retorna o nome usado ou None.
    O arquivo danificado é guardado como .danificado (nada é apagado)."""
    for b in _copias(caminho):
        try:
            with open(b, "rb") as f:
                dados = f.read(LIMITE_COFRE)
            _ler_cabecalho(dados)
        except Exception:
            continue
        try:
            if os.path.exists(caminho):
                os.replace(caminho, caminho + ".danificado")
            _gravar_atomico(caminho, dados)
        except OSError:
            return None
        return os.path.basename(b)
    return None


def _destruir_um(caminho):
    try:
        tam = os.path.getsize(caminho)
        with open(caminho, "r+b") as f:
            for _ in range(3):
                f.seek(0)
                f.write(secrets.token_bytes(tam))
                f.flush()
                os.fsync(f.fileno())
        novo = os.path.join(os.path.dirname(caminho) or ".", secrets.token_hex(8))
        os.replace(caminho, novo)
        os.remove(novo)
    except FileNotFoundError:
        pass
    try:
        os.remove(caminho + ".tmp")
    except FileNotFoundError:
        pass


def _validar_params(t, m, p, max_t):
    if not (1 <= t <= 20 and 8192 <= m <= 1048576 and 1 <= p <= 16 and 1 <= max_t <= 50):
        raise ArquivoInvalido("Parâmetros do cofre fora do padrão (arquivo adulterado?).")


def _ler_cabecalho(bruto):
    magic = bruto[:8]
    if magic == MAGIC:
        fmt, versao = HEADER_FMT, 4
    elif magic == MAGIC_V3:
        fmt, versao = HEADER_FMT, 3
    elif magic == MAGIC_V2:
        fmt, versao = HEADER_V2_FMT, 2
    else:
        raise ArquivoInvalido("Este arquivo não é um cofre válido.")
    hl = struct.calcsize(fmt)
    if len(bruto) < hl + 1 + 16:
        raise ArquivoInvalido("Arquivo de cofre inválido ou corrompido.")
    campos = struct.unpack(fmt, bruto[:hl])
    if versao >= 3:
        (_, t, m, p, max_t, modo, sal_pw, nonce_pw, wrap_pw,
         sal_k, nonce_k, wrap_k, nonce_c, nonce_a) = campos
        if modo not in (MODO_OU, MODO_E):
            raise ArquivoInvalido("Modo do cofre inválido (arquivo adulterado?).")
    else:
        (_, t, m, p, max_t, sal_pw, nonce_pw, wrap_pw, sal_k, nonce_k, wrap_k, nonce_a) = campos
        modo, nonce_c = MODO_OU, None
    _validar_params(t, m, p, max_t)
    fido, ini = None, hl + 1
    if versao == 4:
        fido, ini = _ler_fido(bruto, hl + 1)
    if len(bruto) < ini + 16:
        raise ArquivoInvalido("Arquivo de cofre inválido ou corrompido.")
    aad = bruto[:hl] + bruto[hl + 1:ini]      # cabeçalho + seção FIDO (o contador fica de fora)
    return {"versao": versao, "hl": hl, "t": t, "m": m, "p": p, "max_t": max_t, "modo": modo,
            "sal_pw": sal_pw, "nonce_pw": nonce_pw, "wrap_pw": wrap_pw,
            "sal_k": sal_k, "nonce_k": nonce_k, "wrap_k": wrap_k,
            "nonce_c": nonce_c, "nonce_a": nonce_a, "contador": bruto[hl],
            "fido": fido, "ini_dados": ini, "aad": aad}


def info_cofre(caminho):
    """(tentativas restantes, modo, exige_fido) sem precisar de senha."""
    with open(caminho, "rb") as f:
        bruto = f.read(LIMITE_COFRE)
    if bruto[:8] == MAGIC_V1 and len(bruto) > HEADER_V1_LEN:
        return bruto[HEADER_V1_LEN], MODO_OU, False
    h = _ler_cabecalho(bruto)
    return h["contador"], h["modo"], bool(h["fido"])


def tentativas_restantes(caminho):
    return info_cofre(caminho)[0]


def _decifrar_dados(chave, h, bruto):
    corpo = bruto[h["ini_dados"]:]
    if h["versao"] >= 3:
        k_cha, k_aes = _subchaves(chave)
        interno = AESGCM(k_aes).decrypt(h["nonce_a"], corpo, h["aad"])
        texto = ChaCha20Poly1305(k_cha).decrypt(h["nonce_c"], interno, h["aad"])
    else:
        texto = AESGCM(chave).decrypt(h["nonce_a"], corpo, h["aad"])
    conteudo = json.loads(texto.rstrip(b"\0").decode("utf-8"))
    if isinstance(conteudo, list):                       # versões anteriores: só a lista de itens
        return conteudo, {}
    if not isinstance(conteudo, dict) or not isinstance(conteudo.get("itens"), list):
        raise ValueError
    meta = conteudo.get("meta") if isinstance(conteudo.get("meta"), dict) else {}
    return conteudo["itens"], meta


def _devolver_tentativa(caminho, h):
    """Desfaz o gasto de uma tentativa quando a senha nem chegou a ser testada."""
    try:
        with open(caminho, "r+b") as f:
            f.seek(h["hl"])
            f.write(bytes([h["contador"]]))
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        pass


def _gastar_tentativa(caminho, posicao, contador):
    restantes = contador - 1
    try:
        with open(caminho, "r+b") as f:
            f.seek(posicao)
            f.write(bytes([restantes]))
            f.flush()
            os.fsync(f.fileno())
    except OSError as ex:
        raise ErroGravacao("Não consigo gravar no pendrive (ele está protegido contra gravação, "
                           "cheio ou foi removido). O cofre precisa registrar a tentativa antes de abrir. "
                           "Nenhuma tentativa foi gasta.") from ex
    return restantes


def gerar_senha(n=20, numeros=True, simbolos=True):
    """Senha aleatória com o gerador criptográfico do sistema (nada passa pela internet)."""
    simb = "!@#$%&*-_=+?"
    alfabeto = string.ascii_letters + (string.digits if numeros else "") + (simb if simbolos else "")
    n = max(4, min(int(n), 128))
    while True:
        s = "".join(secrets.choice(alfabeto) for _ in range(n))
        if (any(c.islower() for c in s) and any(c.isupper() for c in s)
                and (not numeros or any(c.isdigit() for c in s))
                and (not simbolos or any(c in simb for c in s))):
            return s


_CONSOANTES = "bcdfgjlmnprstvz"
_VOGAIS = "aeiou"


def gerar_frase(palavras=5, maiuscula=True, numero=True, separador="-"):
    """Senha fácil de lembrar: palavras pronunciáveis aleatórias (ex.: Bafido-luvemo-tasi-...-7).
    Força exata: cada sílaba = 75 combinações; cada palavra tem 2 ou 3 sílabas."""
    ws = []
    for _ in range(max(3, min(int(palavras), 10))):
        nsil = 2 + secrets.randbelow(2)
        ws.append("".join(secrets.choice(_CONSOANTES) + secrets.choice(_VOGAIS) for _ in range(nsil)))
    if maiuscula:
        ws[0] = ws[0].capitalize()
    s = separador.join(ws)
    if numero:
        s += separador + str(secrets.randbelow(100))
    return s


def bits_frase(palavras, numero=True):
    import math
    por_palavra = math.log2(75 ** 2 + 75 ** 3)          # 2 ou 3 sílabas
    return palavras * por_palavra + (math.log2(100) if numero else 0)


def gerar_pin(n=6):
    """PIN numérico aleatório, recusando os óbvios (1234, 0000, 1212, anos...)."""
    n = max(4, min(int(n), 12))
    while True:
        p = "".join(str(secrets.randbelow(10)) for _ in range(n))
        if not pin_obvio(p):
            return p


def pin_obvio(p):
    if not p.isdigit():
        return False
    if len(set(p)) == 1 or p in "0123456789012" or p in "9876543210987":
        return True
    if len(p) % 2 == 0 and p == p[:2] * (len(p) // 2):
        return True                                          # 1212, 2525...
    if len(p) == 4 and (p.startswith("19") or p.startswith("20")):
        return True                                          # parece ano
    return p in ("1004", "2580", "0852", "1122", "6969", "1313", "4321", "123123", "112233",
                 "654321", "121212", "696969", "159753")


_SEQUENCIAS = ("0123456789", "abcdefghijklmnopqrstuvwxyz", "qwertyuiop", "asdfghjkl", "zxcvbnm",
               "9876543210")
_PALAVRAS_COMUNS = SENHAS_COMUNS + ("amor", "deus", "jesus", "flamengo", "corinthians", "palmeiras",
                                    "saopaulo", "santos", "vasco", "gremio", "brasil", "familia", "mudar",
                                    "trocar", "acesso", "login", "welcome", "dragon", "master", "monkey",
                                    "football", "princess", "sunshine", "senha123", "mudar123")


def avaliar_forca(senha):
    """Estimativa de força. Retorna (nota 0-4, rótulo, bits estimados, lista de recomendações)."""
    import math
    if not senha:
        return 0, "Vazia", 0, ["Preencha a senha."]
    s = senha
    baixa = s.lower()
    pool = 0
    tem_min, tem_mai = any(c.islower() for c in s), any(c.isupper() for c in s)
    tem_num = any(c.isdigit() for c in s)
    tem_sim = any(not c.isalnum() for c in s)
    pool += 26 if tem_min else 0
    pool += 26 if tem_mai else 0
    pool += 10 if tem_num else 0
    pool += 33 if tem_sim else 0
    bits = len(s) * math.log2(max(pool, 2))
    dicas = []
    # Frases de palavras: o atacante testa palavras inteiras do dicionário, não letra por letra.
    # Também reconhece trocas óbvias de letras por números/símbolos (Tr0mb0ne, s3nh@, P@ss).
    leet = str.maketrans("013457@$!|", "oieastasil")
    partes = [p for p in re.split(r"[\s\-_.,;:/+]+", s) if p]
    def parece_palavra(w):
        n = w.translate(leet)
        if len(w) < 3 or not n.isalpha() or not (w.islower() or w.istitle() or w.isupper()
                                                  or n.islower() or n.istitle()):
            return False
        nl = n.lower()
        vogais = sum(ch in "aeiou" for ch in nl) / len(nl)
        return 0.25 <= vogais <= 0.75 and not re.search(r"[^aeiou]{4,}", nl)

    palavras = [p for p in partes if parece_palavra(p)]
    letras_em_palavras = sum(len(p) for p in palavras)
    if len(palavras) >= 2 and letras_em_palavras >= 0.6 * sum(len(p) for p in partes):
        resto = [p for p in partes if p not in palavras]
        bits_frase_est = len(palavras) * math.log2(20000)              # ~20 mil palavras comuns
        bits_frase_est += sum(3 for p in palavras if not p.isalpha())   # truque de troca de letras
        bits_frase_est += sum(len(p) * math.log2(10 if p.isdigit() else 95) for p in resto)
        bits_frase_est += 2 if any(p[:1].isupper() for p in palavras) else 0
        if bits_frase_est < bits:
            bits = bits_frase_est
            if len(palavras) < 5:
                dicas.append("Frase com poucas palavras: use 5 ou mais palavras sem relação entre si.")
    # padrões que reduzem a força real
    unicos = len(set(s))
    if unicos < len(s) * 0.5:
        # poucos caracteres diferentes: o resto é repetição previsível (aaaa..., abab...)
        bits = min(bits, unicos * math.log2(max(pool, 2)) + (len(s) - unicos) * 1.0)
        dicas.append("Evite repetir os mesmos caracteres.")
    # caracteres que fazem parte de sequências (abcd, 1234, qwerty...) quase não somam força
    coberto = [False] * len(baixa)
    for i in range(len(baixa) - 3):
        trecho = baixa[i:i + 4]
        if any(trecho in seq for seq in _SEQUENCIAS):
            for j in range(i, i + 4):
                coberto[j] = True
    n_seq = sum(coberto)
    if n_seq:
        bits -= n_seq * (math.log2(max(pool, 2)) - 1.5)
        dicas.append("Evite sequências óbvias (1234, abcd, qwerty).")
    normal = baixa.translate(str.maketrans("013457@$!|", "oieastasil"))   # desfaz P@ssw0rd -> password
    for p in _PALAVRAS_COMUNS:
        # só pesa se a palavra for boa parte da senha (não por coincidência no meio de algo aleatório)
        if len(p) >= 4 and (p in baixa or p in normal) and len(p) >= 0.35 * len(s):
            sobra = max(0, len(s) - len(p) - n_seq)       # o que não é a palavra nem sequência óbvia
            bits = min(bits, 10 + sobra * 4)
            dicas.append(f'Contém "{p}", que está em listas de senhas vazadas.')
            break
    if re.search(r"(19|20)\d\d", s):
        bits -= 6
        dicas.append("Evite anos e datas (aniversários são fáceis de descobrir).")
    if s.isdigit():
        dicas.append("Só números é fraco para senha de conta (para PIN, use a avaliação de PIN).")
    if len(s) < 14:
        dicas.append("Use pelo menos 14 caracteres (o ideal é 20).")
    faltam = [n for n, t in (("letras minúsculas", tem_min), ("maiúsculas", tem_mai),
                             ("números", tem_num), ("símbolos", tem_sim)) if not t]
    if faltam and len(s) < 24:
        dicas.append("Acrescente " + ", ".join(faltam) + ".")
    bits = max(bits, 0)
    if bits < 28:
        nota, rot = 0, "Muito fraca"
    elif bits < 40:
        nota, rot = 1, "Fraca"
    elif bits < 60:
        nota, rot = 2, "Razoável"
    elif bits < 80:
        nota, rot = 3, "Forte"
    else:
        nota, rot = 4, "Muito forte"
    if nota >= 3 and not dicas:
        dicas.append("Ótima. Use esta senha em um único lugar.")
    # remove recomendações repetidas mantendo a ordem
    vistos, final = set(), []
    for d in dicas:
        if d not in vistos:
            vistos.add(d)
            final.append(d)
    return nota, rot, int(bits), final


def composicao(senha):
    mai = sum(c.isupper() for c in senha)
    mi = sum(c.islower() for c in senha)
    num = sum(c.isdigit() for c in senha)
    sim = len(senha) - mai - mi - num
    return {"total": len(senha), "maiusculas": mai, "minusculas": mi, "numeros": num, "simbolos": sim}


def texto_composicao(senha):
    c = composicao(senha)
    return (f"{c['total']} caracteres: {c['maiusculas']} maiúscula(s), {c['minusculas']} minúscula(s), "
            f"{c['numeros']} número(s), {c['simbolos']} símbolo(s)")


# Velocidades de ataque usadas nas estimativas (por tentativa e erro, em média metade das combinações)
VELOCIDADE_COFRE = 1e6        # arquivo do cofre roubado: Argon2id 1 GB — mesmo com centenas de GPUs
VELOCIDADE_SITE = 1e11        # senha vazada de um site com proteção fraca (hash rápido), muitas GPUs


def tempo_quebra(bits, por_segundo):
    """Tempo médio para descobrir a senha por tentativa e erro, em texto."""
    import math
    if bits <= 0:
        return "instantâneo"
    log_seg = (bits - 1) * math.log10(2) - math.log10(por_segundo)
    if log_seg < 0:
        return "menos de 1 segundo"
    seg = 10 ** log_seg if log_seg < 300 else float("inf")
    for limite, div, nome in ((60, 1, "segundo(s)"), (3600, 60, "minuto(s)"), (86400, 3600, "hora(s)"),
                              (86400 * 365, 86400, "dia(s)")):
        if seg < limite:
            return f"{seg / div:.0f} {nome}"
    anos = seg / (86400 * 365)
    if anos < 1000:
        return f"{anos:.0f} ano(s)"
    for limite, nome in ((1e6, "mil anos"), (1e9, "milhões de anos"), (1e12, "bilhões de anos")):
        if anos < limite:
            return f"{anos / (limite / 1000):.0f} {nome}"
    if anos < 1.4e10 * 1e3:
        return f"{anos / 1e12:.0f} trilhões de anos"
    return "muito mais que a idade do universo (13,8 bilhões de anos)"


def relatorio_forca(senha):
    """Texto completo: força, composição, tempo para descobrir e recomendações."""
    nota, rot, bits, dicas = avaliar_forca(senha)
    linhas = [f"Força: {rot} (~{bits} bits)",
              "Composição: " + texto_composicao(senha),
              "Tempo médio para descobrir por tentativa e erro:",
              f"   • arquivo do cofre roubado (protegido por Argon2id): {tempo_quebra(bits, VELOCIDADE_COFRE)}",
              f"   • se vazar de um site com proteção fraca: {tempo_quebra(bits, VELOCIDADE_SITE)}"]
    if dicas:
        linhas.append("Recomendações:")
        linhas += ["   • " + d for d in dicas[:4]]
    return nota, rot, "\n".join(linhas)


def auditar_cofre(registros):
    """Verifica todas as senhas do cofre. Retorna lista de (item, campo, problema, recomendação, gravidade)."""
    achados = []
    usos = {}
    for r in registros:
        for campo in ("senha", "senha_extra"):
            v = r.get(campo, "")
            if v:
                usos.setdefault(v, []).append((r, campo))
    for r in registros:
        for campo in ("senha", "senha_extra"):
            v = r.get(campo, "")
            if not v:
                continue
            outros = [x for x in usos[v] if x[0] is not r]
            if outros:
                nomes = ", ".join(sorted({o[0].get("servico", "?") for o in outros}))[:80]
                achados.append((r, campo, "Senha REPETIDA", f"Também usada em: {nomes}. Troque e gere "
                                "uma senha única para cada conta.", 0))
            nota, rot, bits, dicas = avaliar_forca(v)
            if nota <= 1:
                achados.append((r, campo, f"Senha {rot.lower()} (~{bits} bits)",
                                (dicas[0] if dicas else "") + " Troque pelo botão Gerar.", 1))
            elif nota == 2:
                achados.append((r, campo, f"Senha razoável (~{bits} bits)",
                                "Pode melhorar: use 20 caracteres aleatórios (botão Gerar).", 2))
        if r.get("pin") and pin_obvio(r["pin"]):
            achados.append((r, "pin", "PIN fácil de adivinhar",
                            "Evite 1234, 0000, repetições e anos. Gere um PIN aleatório.", 1))
    achados.sort(key=lambda a: (a[4], a[0].get("servico", "").lower()))
    return achados


# ----------------------------------------------------------------------------
# Impressão (Windows): manda o texto direto para a impressora, sem criar arquivo
# ----------------------------------------------------------------------------
class ImpressaoErro(Exception):
    pass


_IMPRESSORAS_ARQUIVO = ("pdf", "xps", "onenote", "fax", "print to", "send to", "imprimir em",
                        "enviar para", "snagit", "cutepdf", "dopdf", "bullzip", "image writer")


def linhas_impressao(titulo, campos):
    """Monta as linhas da folha. 'campos' = lista de (rótulo, valor)."""
    import datetime
    linhas = [("titulo", titulo), ("texto", "Impresso em " + datetime.datetime.now().strftime("%d/%m/%Y %H:%M")),
              ("texto", "")]
    for rot, valor in campos:
        partes = str(valor).splitlines() or [""]
        primeira = True
        for parte in partes:
            while True:
                pedaco, parte = parte[:60], parte[60:]
                linhas.append(("campo", (rot if primeira else "", pedaco)))
                primeira = False
                if not parte:
                    break
        linhas.append(("texto", ""))
    linhas += [("texto", ""),
               ("aviso", "GUARDE ESTA FOLHA EM LOCAL SEGURO (gaveta trancada / cofre físico)."),
               ("aviso", "Quando não precisar mais, DESTRUA (rasgue em pedaços pequenos ou queime)."),
               ("aviso", "Não fotografe e não deixe sobre a mesa ou na impressora.")]
    return linhas


if EH_WINDOWS:
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


def escolher_impressora(hwnd):
    """Abre a janela 'Imprimir' do Windows. Retorna (hdc, nome, porta) ou None se cancelar."""
    if not EH_WINDOWS:
        raise ImpressaoErro("A impressão está disponível apenas no Windows.")
    comdlg = ctypes.windll.comdlg32
    k32 = ctypes.windll.kernel32
    pd = _PRINTDLGW()
    pd.lStructSize = ctypes.sizeof(_PRINTDLGW)
    pd.hwndOwner = hwnd
    pd.Flags = 0x100 | 0x8 | 0x4 | 0x40000 | 0x100000   # RETURNDC|NOPAGENUMS|NOSELECTION|USEDEVMODECOPIES|NOCURRENTPAGE
    pd.nCopies = 1
    comdlg.PrintDlgW.argtypes = [ctypes.POINTER(_PRINTDLGW)]
    comdlg.PrintDlgW.restype = wintypes.BOOL
    if not comdlg.PrintDlgW(ctypes.byref(pd)):
        erro = comdlg.CommDlgExtendedError()
        if erro:
            raise ImpressaoErro(f"Não foi possível abrir a janela de impressão (código {erro}). "
                                "Verifique se há uma impressora instalada.")
        return None
    nome = porta = ""
    try:
        if pd.hDevNames:
            p = k32.GlobalLock(pd.hDevNames)
            if p:
                offs = (ctypes.c_ushort * 4).from_address(p)
                nome = ctypes.wstring_at(p + offs[1] * 2)
                porta = ctypes.wstring_at(p + offs[2] * 2)
                k32.GlobalUnlock(pd.hDevNames)
    finally:
        for h in (pd.hDevNames, pd.hDevMode):
            if h:
                k32.GlobalFree(h)
    if not pd.hDC:
        raise ImpressaoErro("A impressora não respondeu.")
    return pd.hDC, nome, porta


def impressora_gera_arquivo(nome, porta):
    n = (nome or "").lower()
    p = (porta or "").lower()
    return any(x in n for x in _IMPRESSORAS_ARQUIVO) or p.startswith(("file:", "portprompt", "nul"))


def imprimir_linhas(hdc, linhas):
    """Desenha as linhas na impressora (fonte Consolas, várias páginas se precisar)."""
    gdi = ctypes.windll.gdi32
    gdi.CreateFontW.restype = wintypes.HFONT
    gdi.SelectObject.restype = wintypes.HGDIOBJ
    gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi.TextOutW.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.LPCWSTR, ctypes.c_int]
    gdi.StartDocW.argtypes = [wintypes.HDC, ctypes.POINTER(_DOCINFOW)]
    for f in ("StartPage", "EndPage", "EndDoc", "AbortDoc", "DeleteDC"):
        getattr(gdi, f).argtypes = [wintypes.HDC]
    gdi.GetDeviceCaps.argtypes = [wintypes.HDC, ctypes.c_int]
    gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    dpi_x, dpi_y = gdi.GetDeviceCaps(hdc, 88), gdi.GetDeviceCaps(hdc, 90)
    altura_pag = gdi.GetDeviceCaps(hdc, 10)
    margem_x, margem_y = int(dpi_x * 0.8), int(dpi_y * 0.8)

    def fonte(pt, negrito=False):
        return gdi.CreateFontW(-int(pt * dpi_y / 72), 0, 0, 0, 700 if negrito else 400, 0, 0, 0, 1,
                               0, 0, 5, 0x31, "Consolas")

    f_titulo, f_rot, f_valor, f_texto = fonte(15, True), fonte(10, True), fonte(13, True), fonte(9)
    di = _DOCINFOW()
    di.cbSize = ctypes.sizeof(_DOCINFOW)
    di.lpszDocName = "Documento"          # nome neutro na fila de impressão
    if gdi.StartDocW(hdc, ctypes.byref(di)) <= 0:
        for fnt in (f_titulo, f_rot, f_valor, f_texto):
            gdi.DeleteObject(fnt)
        gdi.DeleteDC(hdc)
        raise ImpressaoErro("A impressora recusou o documento.")
    try:
        gdi.StartPage(hdc)
        y = margem_y
        for tipo, conteudo in linhas:
            passo = int(dpi_y * (0.42 if tipo in ("titulo", "campo") else 0.24))
            if y + passo > altura_pag - margem_y:
                gdi.EndPage(hdc)
                gdi.StartPage(hdc)
                y = margem_y
            if tipo == "campo":
                rot, valor = conteudo
                if rot:
                    gdi.SelectObject(hdc, f_rot)
                    gdi.TextOutW(hdc, margem_x, y + int(dpi_y * 0.04), rot + ":", len(rot) + 1)
                gdi.SelectObject(hdc, f_valor)
                gdi.TextOutW(hdc, margem_x + int(dpi_x * 2.0), y, valor, len(valor))
            else:
                gdi.SelectObject(hdc, f_titulo if tipo == "titulo" else f_texto)
                texto = str(conteudo)
                if texto:
                    gdi.TextOutW(hdc, margem_x, y, texto, len(texto))
            y += passo
        gdi.EndPage(hdc)
        gdi.EndDoc(hdc)
    except Exception:
        gdi.AbortDoc(hdc)
        raise
    finally:
        for fnt in (f_titulo, f_rot, f_valor, f_texto):
            gdi.DeleteObject(fnt)
        gdi.DeleteDC(hdc)


# ----------------------------------------------------------------------------
# Proteções do Windows (anti-captura de tela e área de transferência segura)
# ----------------------------------------------------------------------------
if EH_WINDOWS:
    _u32 = ctypes.windll.user32
    _k32 = ctypes.windll.kernel32
    _u32.GetAncestor.restype = wintypes.HWND
    _u32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    _u32.SetWindowDisplayAffinity.restype = wintypes.BOOL
    _u32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    _u32.OpenClipboard.restype = wintypes.BOOL
    _u32.OpenClipboard.argtypes = [wintypes.HWND]
    _u32.CloseClipboard.restype = wintypes.BOOL
    _u32.EmptyClipboard.restype = wintypes.BOOL
    _u32.SetClipboardData.restype = wintypes.HANDLE
    _u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    _u32.RegisterClipboardFormatW.restype = wintypes.UINT
    _u32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    _k32.GlobalAlloc.restype = wintypes.HGLOBAL
    _k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    _k32.GlobalLock.restype = ctypes.c_void_p
    _k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    _k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    _k32.GlobalFree.restype = wintypes.HGLOBAL
    _k32.GlobalFree.argtypes = [wintypes.HGLOBAL]


def sessao_bloqueada():
    """True se o Windows está na tela de bloqueio (Win+L), troca de usuário ou tela segura."""
    if not EH_WINDOWS:
        return False
    try:
        u = ctypes.windll.user32
        u.OpenInputDesktop.restype = wintypes.HANDLE
        h = u.OpenInputDesktop(0, False, 0x0100)          # DESKTOP_SWITCHDESKTOP
        if not h:
            return True
        ativo = u.SwitchDesktop(h)
        u.CloseDesktop(h)
        return not ativo
    except Exception:
        return False


def proteger_contra_captura(janela):
    """Faz a janela aparecer PRETA em prints, gravações de tela, acesso remoto e
    programas espiões que capturam a tela (Windows 10 versão 2004 ou superior)."""
    if not EH_WINDOWS:
        return False
    try:
        janela.update_idletasks()
        hwnd = _u32.GetAncestor(janela.winfo_id(), 2)       # GA_ROOT
        if _u32.SetWindowDisplayAffinity(hwnd, 0x11):        # WDA_EXCLUDEFROMCAPTURE
            return True
        return bool(_u32.SetWindowDisplayAffinity(hwnd, 0x01))  # WDA_MONITOR (Windows antigo)
    except Exception:
        return False


_JANELA_CLIP = []


def _janela_clipboard():
    """Janela invisível (só de mensagens) que fica como 'dona' da área de transferência.
    Sem dono, o Windows esvazia a área de transferência mas RECUSA gravar a senha nela."""
    if not _JANELA_CLIP:
        h = None
        try:
            f = _u32.CreateWindowExW
            f.restype = wintypes.HWND
            f.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                          ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                          wintypes.HINSTANCE, wintypes.LPVOID]
            h = f(0, "STATIC", None, 0, 0, 0, 0, 0, wintypes.HWND(-3), None, None, None)   # HWND_MESSAGE
        except Exception:
            h = None
        _JANELA_CLIP.append(h)
    return _JANELA_CLIP[0]


def _abrir_clipboard():
    dono = _janela_clipboard()
    for _ in range(20):
        if _u32.OpenClipboard(dono):
            return True
        time.sleep(0.025)
    return False


def _clipboard_set(formato, dados):
    h = _k32.GlobalAlloc(0x0002, len(dados))                # GMEM_MOVEABLE
    if not h:
        return False
    p = _k32.GlobalLock(h)
    ctypes.memmove(p, dados, len(dados))
    _k32.GlobalUnlock(h)
    if not _u32.SetClipboardData(formato, h):
        _k32.GlobalFree(h)
        return False
    return True


def copiar_seguro_windows(texto):
    """Copia sem entrar no histórico (Win+V), sem sincronizar com a nuvem e
    marcando o conteúdo para ser ignorado por monitores de área de transferência."""
    if not _abrir_clipboard():
        return False
    try:
        _u32.EmptyClipboard()
        ok = _clipboard_set(13, (texto + "\0").encode("utf-16-le"))   # CF_UNICODETEXT
        zero = struct.pack("<I", 0)
        for nome in ("ExcludeClipboardContentFromMonitorProcessing",
                     "CanIncludeInClipboardHistory", "CanUploadToCloudClipboard"):
            _clipboard_set(_u32.RegisterClipboardFormatW(nome), zero)
        return ok
    finally:
        _u32.CloseClipboard()


def limpar_clipboard_windows():
    if _abrir_clipboard():
        try:
            _u32.EmptyClipboard()
        finally:
            _u32.CloseClipboard()


class Cofre:
    def __init__(self, caminho, dek, max_t, registros, t=None, m=None, p=PARALELISMO, modo=MODO_OU):
        self.caminho = caminho
        self.dek = dek                  # chave interna dos dados (256 bits aleatórios)
        self.t = t if t is not None else NIVEIS["maximo"][0]
        self.m = m if m is not None else NIVEIS["maximo"][1]
        self.p = p
        self.max_t = max_t
        self.modo = modo
        self.registros = registros
        self.sal_pw = self.nonce_pw = self.wrap_pw = None
        self.sal_k = self.nonce_k = self.wrap_k = None
        self._ks = None                 # modo E: chave derivada da senha (só em memória, enquanto aberto)
        self._kb = None                 # modo E: bytes da chave de acesso (só em memória, enquanto aberto)
        self.chave_gerada = None        # texto de uma chave de acesso recém-criada, para exibir
        self.meta = {}                  # dados internos cifrados: histórico de aberturas
        self.ultima_abertura = None     # data/hora da abertura anterior a esta
        self.erros_desde_ultima = 0     # tentativas erradas entre a abertura anterior e esta
        self.fido = None                # {"salt", "rec", "chaves": [...]} quando o FIDO está ativo
        self._F = None                  # segredo do fator FIDO (só em memória, enquanto aberto)
        self._salt_pendente = None

    # ----- definição das formas de desbloqueio -----
    def _reembrulhar_e(self):
        kek = kek_combinada(self._ks, self._kb, self.sal_pw)
        self.nonce_pw, self.wrap_pw = _embrulhar(kek, self.dek)
        # campos da chave avulsa preenchidos com ruído (no modo E a chave sozinha não abre nada)
        self.sal_k, self.nonce_k, self.wrap_k = (secrets.token_bytes(16), secrets.token_bytes(12),
                                                 secrets.token_bytes(48))

    def _definir_senha(self, senha):
        self.sal_pw = secrets.token_bytes(16)
        ks = derivar_chave(senha, self.sal_pw, self.t, self.m, self.p)
        if self.modo == MODO_E:
            self._ks = ks
            if self._kb is not None:
                self._reembrulhar_e()
        else:
            self.nonce_pw, self.wrap_pw = _embrulhar(ks, self.dek)

    def _definir_chave_acesso(self):
        kb, ktxt = nova_chave_acesso()
        if self.modo == MODO_E:
            self._kb = kb
            if self._ks is not None:
                self._reembrulhar_e()
        else:
            self.sal_k = secrets.token_bytes(16)
            self.nonce_k, self.wrap_k = _embrulhar(kek_da_chave(kb, self.sal_k), self.dek)
        return ktxt

    # ----- criar / abrir -----
    @classmethod
    def criar(cls, caminho, senha, max_tentativas=5, modo=MODO_OU, nivel="maximo"):
        t, m = NIVEIS[nivel]
        c = cls(caminho, secrets.token_bytes(32), max_tentativas, [], t, m, PARALELISMO, modo)
        c._registrar_abertura({}, 0)
        c.chave_gerada = c._definir_chave_acesso()
        c._definir_senha(senha)
        c.salvar()
        _rodar_copias(caminho)                  # já nasce com uma cópia de segurança
        return c

    @classmethod
    def abrir(cls, caminho, senha=None, chave=None, fido=None, recuperacao=None):
        """Modo OU: senha OU chave. Modo E: senha E chave.
        Se o cofre exigir FIDO: 'fido' é uma função (lista_de_credenciais, salt) -> (credencial, saída)
        que toca a chave física; ou então 'recuperacao' é o código de recuperação em texto."""
        with open(caminho, "rb") as f:
            bruto = f.read(LIMITE_COFRE + 1)
        if len(bruto) > LIMITE_COFRE:
            raise ArquivoInvalido("Este arquivo é grande demais para ser um cofre.")

        if bruto[:8] == MAGIC_V1:
            if senha is None:
                raise ArquivoInvalido("Cofre da versão antiga: abra uma vez com a senha mestra "
                                      "para atualizá-lo.")
            return cls._abrir_v1(caminho, bruto, senha)

        h = _ler_cabecalho(bruto)
        # Validações que NÃO gastam tentativa (erros de digitação / fator esquecido)
        if h["modo"] == MODO_E:
            if not senha or not chave:
                raise FatorFaltando("Este cofre exige a senha mestra E a chave de acesso juntas.")
            kb = ler_chave_acesso(chave)
        else:
            kb = ler_chave_acesso(chave) if not senha else None
        rec_bytes = None
        if h["fido"]:
            if recuperacao:
                rec_bytes = ler_chave_acesso(recuperacao)
            elif fido is None:
                raise FatorFaltando("Este cofre exige também a chave FIDO (ou o código de recuperação).")

        if h["contador"] > h["max_t"] or h["contador"] == 0:
            # Contador fora do possível: arquivo danificado (ou mexido por fora). NÃO apaga nada:
            # um byte ruim no pendrive não pode custar o cofre. Orienta a restaurar a cópia.
            raise ArquivoCorrompido("O contador de tentativas do arquivo está danificado.")

        # Toque na chave FIDO ANTES de gastar a tentativa (cancelar não gasta tentativa)
        saida_fido = cred_usada = None
        if h["fido"] and rec_bytes is None:
            cred_usada, saida_fido = fido([c["cred"] for c in h["fido"]["chaves"]], h["fido"]["salt"])
            if not any(c["cred"] == cred_usada for c in h["fido"]["chaves"]):
                raise FidoErro("Esta chave FIDO não está cadastrada neste cofre.")

        restantes = _gastar_tentativa(caminho, h["hl"], h["contador"])

        ks = None
        try:
            if h["modo"] == MODO_E:
                ks = derivar_chave(senha, h["sal_pw"], h["t"], h["m"], h["p"])
                dek = _desembrulhar(kek_combinada(ks, kb, h["sal_pw"]), h["nonce_pw"], h["wrap_pw"])
            elif senha:
                kek = derivar_chave(senha, h["sal_pw"], h["t"], h["m"], h["p"])
                dek = _desembrulhar(kek, h["nonce_pw"], h["wrap_pw"])
            else:
                dek = _desembrulhar(kek_da_chave(kb, h["sal_k"]), h["nonce_k"], h["wrap_k"])
            fator = None
            if h["fido"]:
                if rec_bytes is not None:
                    sal, nonce, wrap = h["fido"]["rec"]
                    fator = _desembrulhar(_kek_recuperacao(rec_bytes, sal), nonce, wrap)
                else:
                    ch = next(c for c in h["fido"]["chaves"] if c["cred"] == cred_usada)
                    fator = _desembrulhar(_kek_fido(saida_fido), ch["nonce"], ch["wrap"])
        except InvalidTag:
            if restantes == 0:
                destruir(caminho)
                raise CofreDestruido()
            raise SenhaIncorreta(restantes)
        except (MemoryError, HashingError):
            _devolver_tentativa(caminho, h)         # faltou memória: a senha nem foi testada
            raise MemoryError("sem memória para derivar a chave") from None

        try:
            registros, meta = _decifrar_dados(_chave_dados(dek, fator), h, bruto)
        except (InvalidTag, ValueError):
            # Senha/chave CORRETAS, mas os dados não conferem: arquivo danificado ou alterado.
            # Quem chegou aqui tem a senha certa, então apagar só prejudicaria o dono: preserva o
            # arquivo, devolve a tentativa e orienta a restaurar a cópia de segurança.
            _devolver_tentativa(caminho, h)
            raise ArquivoCorrompido("O conteúdo do cofre não confere (arquivo danificado ou alterado).")

        c = cls(caminho, dek, h["max_t"], registros, h["t"], h["m"], h["p"], h["modo"])
        for k in ("sal_pw", "nonce_pw", "wrap_pw", "sal_k", "nonce_k", "wrap_k"):
            setattr(c, k, h[k])
        if h["modo"] == MODO_E:
            c._ks, c._kb = ks, kb
        c.fido, c._F = h["fido"], fator
        c._registrar_abertura(meta, h["max_t"] - h["contador"])
        try:
            c.salvar()  # regrava no formato atual: renova nonces e zera o contador de erros
        except OSError as ex:
            # Senha CERTA, mas o pendrive não deixou gravar (cheio, protegido ou removido): devolve a
            # tentativa gasta, para que o cofre não se autodestrua com a senha correta.
            _devolver_tentativa(caminho, h)
            raise ErroGravacao("A senha está certa, mas não foi possível gravar no pendrive "
                               "(ele está cheio, protegido contra gravação ou foi removido). "
                               "Nenhuma tentativa foi gasta. Libere espaço ou destrave o pendrive e tente de novo.") from ex
        return c

    @classmethod
    def _abrir_v1(cls, caminho, bruto, senha):
        if len(bruto) < HEADER_V1_LEN + 17:
            raise ArquivoInvalido("Arquivo de cofre inválido ou corrompido.")
        magic, t, m, p, max_t, sal, nonce = struct.unpack(HEADER_V1_FMT, bruto[:HEADER_V1_LEN])
        _validar_params(t, m, p, max_t)
        contador = bruto[HEADER_V1_LEN]
        if contador > max_t or contador == 0:
            raise ArquivoCorrompido("O contador de tentativas do arquivo está danificado.")
        restantes = _gastar_tentativa(caminho, HEADER_V1_LEN, contador)
        try:
            chave = derivar_chave(senha, sal, t, m, p)
            texto = AESGCM(chave).decrypt(nonce, bruto[HEADER_V1_LEN + 1:], bruto[:HEADER_V1_LEN])
        except InvalidTag:
            if restantes == 0:
                destruir(caminho)
                raise CofreDestruido()
            raise SenhaIncorreta(restantes)
        # Converte para o formato atual, com chave de acesso
        c = cls(caminho, secrets.token_bytes(32), max_t, json.loads(texto.decode("utf-8")), t, m, p)
        c.chave_gerada = c._definir_chave_acesso()
        c._definir_senha(senha)
        c.salvar()
        return c

    # ----- gravação e manutenção -----
    def salvar(self):
        nonce_c, nonce_a = secrets.token_bytes(12), secrets.token_bytes(12)
        cab = struct.pack(HEADER_FMT, MAGIC, self.t, self.m, self.p, self.max_t, self.modo,
                          self.sal_pw, self.nonce_pw, self.wrap_pw,
                          self.sal_k, self.nonce_k, self.wrap_k, nonce_c, nonce_a)
        if bool(self.fido) != (self._F is not None):
            raise ValueError("estado FIDO inconsistente")
        secao = _serializar_fido(self.fido)
        aad = cab + secao
        dados = json.dumps({"itens": self.registros, "meta": self.meta}, ensure_ascii=False).encode("utf-8")
        dados += b"\0" * (TAM_BLOCO - len(dados) % TAM_BLOCO)      # esconde o tamanho real
        k_cha, k_aes = _subchaves(_chave_dados(self.dek, self._F))
        interno = ChaCha20Poly1305(k_cha).encrypt(nonce_c, dados, aad)    # camada 1
        externo = AESGCM(k_aes).encrypt(nonce_a, interno, aad)           # camada 2
        b1 = self.caminho + ".bak1"                 # cópia de segurança: no máx. 1 a cada 10 min
        try:
            velha = (not os.path.exists(b1)) or time.time() - os.path.getmtime(b1) > 600
        except OSError:
            velha = True
        if velha:
            _rodar_copias(self.caminho)
        _gravar_atomico(self.caminho, cab + bytes([self.max_t]) + secao + externo)

    def confere_senha(self, senha):
        try:
            ks = derivar_chave(senha, self.sal_pw, self.t, self.m, self.p)
            if self.modo == MODO_E:
                return self._ks is not None and secrets.compare_digest(ks, self._ks)
            return secrets.compare_digest(_desembrulhar(ks, self.nonce_pw, self.wrap_pw), self.dek)
        except InvalidTag:
            return False

    _CAMPOS_CHAVES = ("sal_pw", "nonce_pw", "wrap_pw", "sal_k", "nonce_k", "wrap_k", "_ks", "_kb", "chave_gerada")

    def _com_desfazer(self, mudar):
        """Aplica a mudança e grava. Se a gravação falhar, DESFAZ na memória: assim um próximo salvamento
        não grava, escondido, uma senha/chave que o usuário nunca viu confirmada."""
        antes = {k: getattr(self, k, None) for k in self._CAMPOS_CHAVES}
        try:
            r = mudar()
            self.salvar()
            return r
        except Exception:
            for k, v in antes.items():
                setattr(self, k, v)
            raise

    def trocar_senha(self, nova):
        self._com_desfazer(lambda: self._definir_senha(nova))
        apagar_copias(self.caminho)        # as cópias antigas ainda abririam com a senha velha

    def gerar_nova_chave_acesso(self):
        """Cria nova chave de acesso; a anterior deixa de funcionar."""
        r = self._com_desfazer(self._definir_chave_acesso)
        apagar_copias(self.caminho)
        return r

    def _registrar_abertura(self, meta, erros_antes):
        """Guarda (cifrado) quando o cofre foi aberto e quantas tentativas erradas houve antes."""
        import datetime
        self.meta = dict(meta or {})
        self.ultima_abertura = self.meta.get("ultima_abertura")
        self.erros_desde_ultima = max(0, int(erros_antes))
        agora = datetime.datetime.now().isoformat(timespec="seconds")
        hist = [x for x in self.meta.get("historico", []) if isinstance(x, dict)][-49:]
        hist.append({"quando": agora, "erros_antes": self.erros_desde_ultima})
        self.meta["historico"] = hist
        self.meta["ultima_abertura"] = agora

    # ----- chave FIDO (as alterações só ficam valendo depois de salvar()) -----
    def salt_fido(self):
        """Salt usado para pedir o segredo à chave FIDO (o mesmo para todas as chaves do cofre)."""
        if self.fido:
            return self.fido["salt"]
        if self._salt_pendente is None:
            self._salt_pendente = secrets.token_bytes(32)
        return self._salt_pendente

    def estado_fido(self):
        import copy
        return copy.deepcopy(self.fido), self._F, self._salt_pendente

    def restaurar_fido(self, estado):
        self.fido, self._F, self._salt_pendente = estado

    def adicionar_fido(self, nome, cred, saida):
        """Cadastra uma chave. Na PRIMEIRA chave ativa o FIDO e devolve o código de recuperação."""
        codigo = None
        if not self.fido:
            self._F = secrets.token_bytes(32)
            rec_b, codigo = nova_chave_acesso()
            sal = secrets.token_bytes(16)
            n, w = _embrulhar(_kek_recuperacao(rec_b, sal), self._F)
            self.fido = {"salt": self.salt_fido(), "rec": (sal, n, w), "chaves": []}
        if len(self.fido["chaves"]) >= MAX_FIDO:
            raise ValueError(f"Limite de {MAX_FIDO} chaves FIDO atingido.")
        if any(c["cred"] == cred for c in self.fido["chaves"]):
            raise ValueError("Esta chave FIDO já está cadastrada.")
        n, w = _embrulhar(_kek_fido(saida), self._F)
        self.fido["chaves"].append({"nome": (nome or "Chave FIDO")[:40], "cred": cred, "nonce": n, "wrap": w})
        return codigo

    def remover_fido(self, cred):
        if not self.fido:
            return
        if len(self.fido["chaves"]) <= 1:
            raise ValueError("Não é possível remover a única chave. Use 'Desativar FIDO'.")
        self.fido["chaves"] = [c for c in self.fido["chaves"] if c["cred"] != cred]

    def novo_codigo_recuperacao(self):
        if not self.fido:
            raise ValueError("FIDO não está ativo.")
        rec_b, codigo = nova_chave_acesso()
        sal = secrets.token_bytes(16)
        n, w = _embrulhar(_kek_recuperacao(rec_b, sal), self._F)
        self.fido["rec"] = (sal, n, w)
        return codigo

    def desativar_fido(self):
        self.fido, self._F, self._salt_pendente = None, None, None

    def fechar(self):
        self.dek = None
        self._ks = None
        self._kb = None
        self._F = None
        self.registros = []


# ----------------------------------------------------------------------------
# Importação de planilhas (Excel .xlsx/.xlsm e CSV)
# ----------------------------------------------------------------------------
LIMITE_LINHAS = 20000
LIMITE_ARQUIVO = 50 * 1024 * 1024          # 50 MB

# Campos de cada item do cofre
CAMPOS = ("servico", "login", "senha", "senha_extra", "pin", "chave", "codigos", "notas", "grupo", "pessoa")
CAMPOS_SECRETOS = ("senha", "senha_extra", "pin", "chave", "codigos")
ROTULOS = {"servico": "Conta / App", "login": "Login", "senha": "Senha", "senha_extra": "Senha extra",
           "pin": "PIN", "chave": "Chave", "codigos": "Códigos de recuperação", "notas": "Notas",
           "grupo": "Grupo", "pessoa": "Pessoa"}


def novo_item(**valores):
    item = {c: "" for c in CAMPOS}
    item.update({k: v for k, v in valores.items() if k in CAMPOS})
    item["id"] = secrets.token_hex(8)
    return item


_SINONIMOS = {
    "servico": ("servico", "conta", "site", "nome", "name", "titulo", "title", "sistema",
                "aplicativo", "app", "banco", "plataforma", "descricao do servico", "empresa"),
    "url": ("url", "endereco", "link", "website", "origin", "origem", "login uri", "login url", "uri"),
    "login": ("login", "usuario", "user", "username", "user name", "email", "e mail",
              "cpf", "conta de acesso", "identificacao", "matricula", "login username",
              "nome de usuario", "nome do usuario", "usuario de acesso"),
    "senha_extra": ("senha extra", "senha 2", "segunda senha", "senha secundaria", "senha alternativa",
                    "senha de transacao", "senha eletronica", "assinatura eletronica", "senha adicional"),
    "senha": ("senha", "password", "pass", "pwd", "senha de acesso", "login password"),
    "pin": ("pin", "senha do cartao", "pin do cartao", "senha numerica",
            "senha de 4 digitos", "senha de 6 digitos"),
    "chave": ("chave", "key", "token", "chave de acesso", "frase secreta", "seed", "login totp", "totp",
              "otp", "otpauth"),
    "codigos": ("codigo de recuperacao", "codigos de recuperacao", "codigos", "codigo",
                "recuperacao", "backup codes", "recovery codes", "recovery"),
    "notas": ("notas", "nota", "note", "notes", "observacao", "observacoes", "obs",
              "comentario", "comentarios", "descricao", "informacoes"),
    "pessoa": ("pessoa", "titular", "dono", "dona", "de quem", "responsavel", "proprietario", "familiar"),
    "grupo": ("grupo", "categoria", "pasta", "tipo", "folder"),
}


def _normalizar(texto):
    import unicodedata
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def _campo_do_cabecalho(texto):
    n = _normalizar(texto)
    if not n:
        return None
    for campo, nomes in _SINONIMOS.items():           # igual primeiro
        if n in nomes:
            return campo
    melhor = None                                      # depois "contém": vence o nome mais longo
    for campo, nomes in _SINONIMOS.items():
        for nome in nomes:
            if len(nome) >= 4 and (nome in n) and (melhor is None or len(nome) > melhor[0]):
                melhor = (len(nome), campo)
    return melhor[1] if melhor else None


def _valor_celula(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "sim" if v else "não"
    if isinstance(v, float):
        from decimal import Decimal
        d = Decimal(repr(v))                 # forma mais curta que volta ao mesmo número (sem 'lixo' de float)
        return format(d, "f").rstrip("0").rstrip(".") if "." in format(d, "f") else format(d, "f")
    if hasattr(v, "strftime"):
        return v.strftime("%d/%m/%Y")
    return str(v).strip()


def _detectar_cabecalho(linhas):
    """Procura, nas 15 primeiras linhas, a que parece cabeçalho. Retorna (índice, mapa coluna->campo)."""
    for i, linha in enumerate(linhas[:15]):
        mapa = {}
        for col, cel in enumerate(linha):
            campo = _campo_do_cabecalho(cel)
            if campo and campo not in mapa.values():
                mapa[col] = campo
        campos = set(mapa.values())
        if len(campos) >= 2 and campos & {"senha", "login", "pin", "chave", "codigos", "senha_extra"}:
            return i, mapa
    return None, None


def _blocos_recuperacao(linhas, nome_aba):
    """Aba de códigos de recuperação sem cabeçalho: um nome (ex.: SAMSUNG) seguido dos códigos."""
    regs, atual = [], None
    for l in linhas:
        cel = [c for c in l if c]
        if not cel:
            continue
        texto_puro = not re.search(r"\d", cel[0]) and len(cel[0]) <= 60
        if texto_puro:
            atual = {"servico": cel[0], "codigos": []}
            regs.append(atual)
            cel = cel[1:]
        if not cel:
            continue
        if atual is None:
            atual = {"servico": nome_aba or "Códigos de recuperação", "codigos": []}
            regs.append(atual)
        atual["codigos"].extend(cel)
    saida = []
    for r in regs:
        if r["codigos"]:
            saida.append({"servico": r["servico"], "codigos": "\n".join(r["codigos"])})
    return saida


def _linhas_para_registros(linhas, nome_aba="", grupo=""):
    """Converte linhas (listas de valores) em itens do cofre. Nenhuma coluna com dados é perdida:
    colunas sem nome conhecido vão para as Notas."""
    avisos = []
    linhas = [[_valor_celula(c) for c in l] for l in linhas]
    linhas = [l for l in linhas if any(l)]
    if not linhas:
        return [], avisos
    idx, mapa = _detectar_cabecalho(linhas)
    rotulos_extra = {}
    if idx is None:
        if re.search(r"(?i)recupera|backup|recovery", _normalizar(nome_aba)):
            regs = []
            for b in _blocos_recuperacao(linhas, nome_aba):
                it = {c: "" for c in CAMPOS}
                it.update(b)
                it["grupo"] = grupo
                regs.append(it)
            if regs:
                avisos.append(f"{nome_aba}: lida como lista de códigos de recuperação "
                              f"({len(regs)} conta(s)). Confira na prévia.")
            return regs, avisos
        ncol = max(len(l) for l in linhas)
        ordem = {1: ["servico"], 2: ["servico", "senha"], 3: ["servico", "login", "senha"],
                 4: ["servico", "login", "senha", "senha_extra"]}.get(
                     ncol, ["servico", "login", "senha", "senha_extra"])
        mapa = dict(enumerate(ordem))
        inicio = 0
        avisos.append(f"{nome_aba or 'Planilha'}: sem cabeçalho; colunas lidas como "
                      + " | ".join(ROTULOS[c] for c in ordem)
                      + (" (as demais vão para Notas)" if ncol > len(ordem) else "") + ".")
    else:
        inicio = idx + 1
        for col, cel in enumerate(linhas[idx]):
            if col not in mapa:
                rotulos_extra[col] = cel or f"Coluna {chr(65 + col) if col < 26 else col + 1}"
    regs = []
    sem_nome = 0
    for linha in linhas[inicio:]:
        r = {c: "" for c in CAMPOS}
        r["url"] = ""
        extras = []
        for col, valor in enumerate(linha):
            if not valor:
                continue
            campo = mapa.get(col)
            if campo:
                r[campo] = (r[campo] + " " + valor).strip() if r[campo] else valor
            else:
                nome = rotulos_extra.get(col, f"Coluna {chr(65 + col) if col < 26 else col + 1}")
                nn = _normalizar(nome)
                if (nn in ("favorite", "favorito", "reprompt", "archived", "arquivado") and valor in ("0", "1", "true", "false", "sim", "não", "nao")) or (nn == "type" and valor.lower() == "login"):
                    continue                                   # metadados triviais de gerenciadores
                extras.append(f"{nome}: {valor}")
        if extras:
            r["notas"] = "\n".join(([r["notas"]] if r["notas"] else []) + extras)
        if not any(r[c] for c in CAMPOS_SECRETOS + ("login",)):
            continue
        if not r["servico"]:
            sem_nome += 1
            r["servico"] = r["url"] or r["login"] or f"{nome_aba or 'Item'} {sem_nome}"
        if r["url"] and r["url"] != r["servico"]:
            r["notas"] = (f"Site: {r['url']}\n" + r["notas"]).strip()
        r.pop("url")
        if grupo and not r["grupo"]:
            r["grupo"] = grupo
        regs.append(r)
    return regs, avisos


def ler_planilha(caminho):
    """Lê .xlsx/.xlsm/.csv e retorna (registros, avisos). Nunca grava nada no disco."""
    if os.path.getsize(caminho) > LIMITE_ARQUIVO:
        raise ValueError("Arquivo muito grande (limite de 50 MB).")
    ext = os.path.splitext(caminho)[1].lower()
    registros, avisos = [], []

    if ext in (".xlsx", ".xlsm"):
        try:
            import openpyxl
        except ImportError:
            raise ValueError("Falta a biblioteca de Excel. Rode:  pip install openpyxl defusedxml")
        try:
            wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
        except Exception as ex:
            raise ValueError(f"Não foi possível ler a planilha (está protegida por senha ou corrompida?).\n{ex}")
        try:
            varias = len(wb.worksheets) > 1
            for ws in wb.worksheets:
                linhas = []
                for linha in ws.iter_rows(values_only=True):
                    linhas.append(list(linha))
                    if len(linhas) > LIMITE_LINHAS:
                        raise ValueError(f"A aba '{ws.title}' tem mais de {LIMITE_LINHAS} linhas.")
                regs, av = _linhas_para_registros(linhas, ws.title, ws.title if varias else "")
                registros += regs
                avisos += av
        finally:
            wb.close()
    elif ext == ".csv":
        import csv
        bruto = open(caminho, "rb").read()
        for cod in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                texto = bruto.decode(cod)
                break
            except UnicodeDecodeError:
                continue
        try:
            dialeto = csv.Sniffer().sniff(texto[:5000], delimiters=",;\t")
        except csv.Error:
            dialeto = csv.excel
        import io
        linhas = list(csv.reader(io.StringIO(texto, newline=""), dialeto))
        if len(linhas) > LIMITE_LINHAS:
            raise ValueError(f"O arquivo tem mais de {LIMITE_LINHAS} linhas.")
        registros, avisos = _linhas_para_registros(linhas)
    elif ext == ".xls":
        raise ValueError("Formato .xls antigo não é suportado. Abra no Excel e use "
                         "'Salvar como' > Pasta de Trabalho do Excel (.xlsx).")
    else:
        raise ValueError("Use um arquivo .xlsx, .xlsm ou .csv.")

    vistos_dup, dups = {}, []
    for r in registros:
        k = (_normalizar(r.get("servico", "")), r.get("login", "").strip().lower())
        if k in vistos_dup and k[0]:
            dups.append(r.get("servico", ""))
        vistos_dup.setdefault(k, r)
    if dups:
        nomes = ", ".join(sorted(set(dups))[:5]) + ("…" if len(set(dups)) > 5 else "")
        avisos.append(f"{len(dups)} linha(s) repetem o mesmo serviço e login dentro da própria planilha "
                      f"({nomes}). Confira na prévia qual senha vale.")
    if any(r.get("pin", "").isdigit() and len(r["pin"]) < 4 for r in registros):
        avisos.append("Alguns PINs têm menos de 4 dígitos. Se o Excel apagou zeros à esquerda "
                      "(ex.: 0123 virou 123), corrija esses itens depois de importar.")
    return registros, avisos


def classificar_importacao(existentes, novos):
    """Separa em: novos, idênticos (ignorar) e conflitos (mesmo serviço+login, dados diferentes)."""
    indice = {(_normalizar(r.get("servico", "")), r.get("login", "").strip().lower()): r for r in existentes}
    vistos = set()
    inserir, iguais, conflitos = [], [], []
    for n in novos:
        chave = (_normalizar(n["servico"]), n["login"].strip().lower())
        assinatura = chave + tuple(n.get(c, "") for c in CAMPOS_SECRETOS)
        if assinatura in vistos:
            iguais.append(n)            # linha repetida dentro da própria planilha (idêntica)
            continue
        vistos.add(assinatura)
        atual = indice.get(chave)
        if atual is None:
            inserir.append(n)
        elif all(atual.get(c, "") == n.get(c, "") for c in CAMPOS_SECRETOS):
            iguais.append(n)
        else:
            conflitos.append((atual, n))
    return inserir, iguais, conflitos


def criar_modelo_planilha(destino):
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Senhas"
    ws.append(["Conta / App", "Login", "Senha", "Senha extra", "PIN", "Chave",
               "Códigos de recuperação", "Notas", "Grupo", "Pessoa"])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F4E78")
    ws.append(["Exemplo: Banco", "joao.silva", "MinhaSenha#2026", "Senha6dig", "0123", "",
               "", "apague esta linha", "Bancos", "Eu"])
    for col, larg in zip("ABCDEFGHI", (26, 26, 22, 18, 10, 18, 30, 30, 14)):
        ws.column_dimensions[col].width = larg
    for linha in range(2, 1001):                     # PIN e códigos como texto: mantém zeros à esquerda
        for col in "DEFG":
            ws[f"{col}{linha}"].number_format = "@"
    ws.freeze_panes = "A2"
    wb.save(destino)


# ----------------------------------------------------------------------------
# Chave FIDO2 (YubiKey, Feitian, Titan...) pelo Windows Hello / WebAuthn
# Usa a extensão PRF (hmac-secret): a chave devolve um segredo que nunca sai do chip
# sem o toque físico e o PIN da própria chave.
# ----------------------------------------------------------------------------
def _hwnd(janela):
    if not EH_WINDOWS:
        return None
    try:
        janela.update_idletasks()
        return _u32.GetAncestor(janela.winfo_id(), 2)
    except Exception:
        return None


def _fido_cliente(hwnd):
    if not EH_WINDOWS:
        raise FidoErro("A chave FIDO só funciona no Windows.")
    try:
        from fido2.client import DefaultClientDataCollector
        from fido2.client.windows import WindowsClient
    except ImportError:
        raise FidoErro("Falta a biblioteca FIDO. Rode:  pip install fido2  (ou use o instalar_cofre).")
    if not WindowsClient.is_available():
        raise FidoErro("Este Windows não oferece suporte a chaves FIDO (requer Windows 10 1903 ou mais novo).")
    coletor = DefaultClientDataCollector("https://" + RP_ID, verify=lambda *a: True)
    return WindowsClient(coletor, handle=hwnd)


def _msg_fido(ex):
    try:
        from fido2.client import ClientError
    except ImportError:
        ClientError = None
    if ClientError is not None and isinstance(ex, ClientError):
        cod = ex.code.name
        if cod == "TIMEOUT":
            return "Tempo esgotado: a chave FIDO não foi tocada."
        if cod == "DEVICE_INELIGIBLE":
            return "Esta chave FIDO não está cadastrada neste cofre."
        if cod == "CONFIGURATION_UNSUPPORTED":
            return "A chave FIDO não entregou o recurso necessário (hmac-secret / PRF). " + _diagnostico_fido()
        causa = str(ex.cause or "")
        if "cancel" in causa.lower() or "0x800704c7" in causa.lower():
            return "Operação cancelada."
        return f"A chave FIDO não respondeu como esperado ({cod}). {causa}".strip()
    return f"Erro na chave FIDO: {ex}"


def _fido_registrar(hwnd, nome="Cofre de Senhas"):
    """Cria uma credencial na chave física (1 toque + PIN da chave). Retorna o ID da credencial."""
    cli = _fido_cliente(hwnd)
    opcoes = {
        "rp": {"id": RP_ID, "name": "Cofre de Senhas"},
        "user": {"id": secrets.token_bytes(16), "name": "cofre", "displayName": nome},
        "challenge": secrets.token_bytes(32),
        "pubKeyCredParams": [{"type": "public-key", "alg": -7}, {"type": "public-key", "alg": -8},
                             {"type": "public-key", "alg": -257}],
        "timeout": 120000,
        "authenticatorSelection": {"authenticatorAttachment": "cross-platform",
                                   "residentKey": "discouraged", "userVerification": "required"},
        "attestation": "none",
        "hints": ["security-key"],
        "extensions": {"prf": {}},
    }
    try:
        r = cli.make_credential(opcoes)
    except FidoErro:
        raise
    except Exception as ex:
        raise FidoErro(_msg_fido(ex))
    prf = r.client_extension_results.prf
    if not prf or not getattr(prf, "enabled", False):
        raise FidoErro("A chave FIDO não entregou o recurso necessário (hmac-secret / PRF). " + _diagnostico_fido())
    return bytes(r.raw_id)


def _fido_obter(hwnd, creds, salt):
    """Pede o segredo à chave (1 toque + PIN). Retorna (ID da credencial usada, segredo de 32 bytes)."""
    cli = _fido_cliente(hwnd)
    pedido = {
        "challenge": secrets.token_bytes(32),
        "rpId": RP_ID,
        "allowCredentials": [{"type": "public-key", "id": c} for c in creds],
        "userVerification": "required",
        "timeout": 120000,
        "hints": ["security-key"],
        "extensions": {"prf": {"eval": {"first": salt}}},
    }
    try:
        resp = cli.get_assertion(pedido).get_response(0)
    except FidoErro:
        raise
    except Exception as ex:
        raise FidoErro(_msg_fido(ex))
    return _extrair_segredo(resp)


def _diagnostico_fido():
    """Explica por que a chave não entregou o segredo: Windows antigo, PIN ou chave antiga só U2F."""
    v = 0
    try:
        from fido2.client.win_api import WEBAUTHN_API_VERSION as v
    except Exception:
        v = 0
    if v and v < 4:
        return (f"O seu Windows ainda não entrega esse recurso das chaves de segurança (API WebAuthn v{v}). "
                "Atualize o Windows pelo Windows Update e tente de novo: a sua chave provavelmente funciona.")
    return ("Quase todas as chaves FIDO2 atuais servem (Yubico Security Key NFC preta ou azul, YubiKey 5, "
            "Feitian ePass FIDO2...). Só as chaves antigas que fazem apenas U2F não têm esse recurso. "
            "Confira também se a chave tem PIN configurado." + (f" (API WebAuthn do Windows: v{v})" if v else ""))


def _extrair_segredo(resp):
    prf = resp.client_extension_results.prf
    resultados = getattr(prf, "results", None) if prf else None
    saida = getattr(resultados, "first", None) if resultados else None
    if not saida or len(saida) != 32:
        raise FidoErro("A chave FIDO não devolveu o segredo (hmac-secret). " + _diagnostico_fido())
    return bytes(resp.raw_id), bytes(saida)


def fido_registrar(hwnd, nome="Cofre de Senhas"):
    with processo_liberado():
        return _fido_registrar(hwnd, nome)


def fido_obter(hwnd, creds, salt):
    with processo_liberado():
        return _fido_obter(hwnd, creds, salt)


def fido_cadastrar_e_testar(hwnd, salt, nome="Cofre de Senhas"):
    """Registra e confere 2 vezes que a chave devolve sempre o mesmo segredo (3 toques).
    Só depois disso a chave é ligada ao cofre — se algo variar, nada é alterado."""
    cred = fido_registrar(hwnd, nome)
    c1, s1 = fido_obter(hwnd, [cred], salt)
    c2, s2 = fido_obter(hwnd, [cred], salt)
    if c1 != cred or c2 != cred or not secrets.compare_digest(s1, s2):
        raise FidoErro("A chave respondeu de forma diferente em cada toque. Por segurança ela NÃO foi "
                       "cadastrada. Confira se ela tem PIN FIDO2 configurado e tente de novo.")
    return cred, s1


# ----------------------------------------------------------------------------
# Interface gráfica
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# Aparência: tema "Meia-noite" (escuro, acento índigo) desenhado pelo próprio programa
# ----------------------------------------------------------------------------
# Todos os botões, campos, caixas de seleção etc. são imagens geradas aqui com
# antisserrilhamento (bordas suaves) e cantos transparentes, sem arquivos extras.
# As regras de montagem dos elementos seguem o tema Sun Valley (rdbende, licença MIT).
CORES = {
    # superfícies (do fundo para a frente)
    "fundo": "#0e1016",       # janela
    "lateral": "#0b0d12",     # barra lateral
    "sup": "#151821",         # painéis e cartões
    "sup2": "#1b1f2a",        # botões em repouso
    "sup3": "#242a37",        # passar o mouse
    "sup4": "#2d3443",        # pressionado
    "campo": "#0f1218",       # campos de texto (afundados)
    "borda": "#232835",
    "borda2": "#323949",
    # texto
    "texto": "#e8eaf0",
    "suave": "#9aa2b4",
    "fraco": "#666e82",
    # acento
    "prim": "#6c63ff",
    "prim_hover": "#7e77ff",
    "prim_press": "#5a51ea",
    "prim_txt": "#a8a3ff",
    "prim_fundo": "#211f42",  # seleção / destaque suave
    # estados
    "ok": "#3dd68c", "ok_fundo": "#13291f",
    "alerta": "#f5b544", "alerta_fundo": "#2e2414",
    "perigo": "#f26b6b", "perigo_fundo": "#2e1619",
    "num": "#7cb4ff", "sim": "#f472b6",
}
# nomes antigos usados pelo resto do programa
CORES.update({
    "prim_esc": CORES["prim_press"], "prim_claro": CORES["prim_fundo"], "sel": CORES["prim_fundo"],
    "lateral_sel": "#1a1e29", "lateral_txt": "#c3c8d4", "lateral_titulo": CORES["fraco"],
    "cabecalho": CORES["fundo"], "noite": CORES["fundo"], "neutro": CORES["sup2"],
    "neutro_hover": CORES["sup3"],
})

TONS = ("#6c63ff", "#22a6c9", "#2fbf71", "#e3a03a", "#e0568f", "#9a6bff", "#3d8bfd", "#f07a3c",
        "#20b2a0", "#e05561")


# ---------- escala da tela (Windows com 125%, 150%...) ----------
ESCALA = 1.0


def _px(n):
    """Converte um tamanho pensado para 100% no tamanho real da tela."""
    return int(round(n * ESCALA))


def definir_escala(root):
    global ESCALA
    try:
        ESCALA = max(1.0, min(3.0, round(root.winfo_fpixels("1i") / 96.0, 2)))
    except tk.TclError:
        ESCALA = 1.0
    _CACHE_ICONES.clear()
    _PONTOS.clear()
    return ESCALA


# ---------- desenho antisserrilhado (função de distância → cobertura) ----------
def _hex(c):
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _sd_rrect(px, py, x0, y0, x1, y1, r):
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    qx = abs(px - cx) - ((x1 - x0) / 2 - r)
    qy = abs(py - cy) - ((y1 - y0) / 2 - r)
    return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r


def _sd_circ(px, py, cx, cy, r):
    return math.hypot(px - cx, py - cy) - r


def _sd_seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy or 1)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


class _Tela:
    """Imagem RGBA pequena, com composição 'por cima' (alfa pré-multiplicado)."""

    def __init__(self, w, h):
        self.s = ESCALA                      # as formas são descritas em tamanho 100% e desenhadas na escala real
        self.w, self.h = max(1, int(round(w * self.s))), max(1, int(round(h * self.s)))
        self.px = [0.0] * (self.w * self.h * 4)

    def pintar(self, dist, cor, alfa=1.0, bruto=False):
        r, g, b = _hex(cor)
        px = self.px
        s = self.s
        for y in range(self.h):
            for x in range(self.w):
                cob = 0.5 - (dist((x + 0.5) / s, (y + 0.5) / s) if bruto else dist((x + 0.5) / s, (y + 0.5) / s) * s)
                if cob <= 0:
                    continue
                a = (1.0 if cob >= 1 else cob) * alfa
                i = (y * self.w + x) * 4
                k = 1 - a
                px[i] = r * a + px[i] * k
                px[i + 1] = g * a + px[i + 1] * k
                px[i + 2] = b * a + px[i + 2] * k
                px[i + 3] = a + px[i + 3] * k
        return self

    # formas
    def ret(self, x0, y0, x1, y1, r, cor, alfa=1.0):
        return self.pintar(lambda x, y: _sd_rrect(x, y, x0, y0, x1, y1, r), cor, alfa)

    def contorno(self, x0, y0, x1, y1, r, cor, larg=1.0, alfa=1.0):
        m = larg / 2
        return self.pintar(lambda x, y: abs(_sd_rrect(x, y, x0 + m, y0 + m, x1 - m, y1 - m, max(r - m, 0))) - m,
                           cor, alfa)

    def circ(self, cx, cy, r, cor, alfa=1.0):
        return self.pintar(lambda x, y: _sd_circ(x, y, cx, cy, r), cor, alfa)

    def anel(self, cx, cy, r, cor, larg=1.0, alfa=1.0):
        return self.pintar(lambda x, y: abs(_sd_circ(x, y, cx, cy, r - larg / 2)) - larg / 2, cor, alfa)

    def linha(self, pontos, cor, larg=1.5, alfa=1.0):
        segs = list(zip(pontos, pontos[1:]))
        return self.pintar(lambda x, y: min(_sd_seg(x, y, a[0], a[1], b[0], b[1]) for a, b in segs) - larg / 2,
                           cor, alfa)

    def png(self):
        linhas = []
        for y in range(self.h):
            lin = bytearray(b"\x00")
            for x in range(self.w):
                i = (y * self.w + x) * 4
                a = self.px[i + 3]
                if a <= 0:
                    lin += b"\x00\x00\x00\x00"
                else:
                    lin += bytes((min(255, int(self.px[i] / a + 0.5)), min(255, int(self.px[i + 1] / a + 0.5)),
                                  min(255, int(self.px[i + 2] / a + 0.5)), min(255, int(a * 255 + 0.5))))
            linhas.append(bytes(lin))

        def bloco(tipo, dados):
            return (struct.pack(">I", len(dados)) + tipo + dados
                    + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF))
        return (b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 6, 0, 0, 0))
                + bloco(b"IDAT", zlib.compress(b"".join(linhas), 9)) + bloco(b"IEND", b""))

    def imagem(self, master):
        return tk.PhotoImage(master=master, data=base64.b64encode(self.png()), format="png")


# ---------- peças do tema ----------
def _pecas():
    """Desenha todas as peças. Retorna {nome: _Tela}."""
    C = CORES
    P = {}
    T = _Tela

    def botao(fundo, borda, foco=False, sombra=True):
        t = T(24, 24)
        if sombra:
            t.ret(0, 1, 24, 24, 6, "#000000", 0.35)
        t.ret(0, 0, 24, 23, 6, fundo)
        t.contorno(0, 0, 24, 23, 6, C["prim"] if foco else borda, 1.6 if foco else 1.0)
        return t
    P["btn"] = botao(C["sup2"], C["borda2"])
    P["btn_hover"] = botao(C["sup3"], "#3d4558")
    P["btn_press"] = botao(C["sup"], C["borda2"], sombra=False)
    P["btn_dis"] = botao("#14171e", "#22262f", sombra=False)
    P["btn_foco"] = botao(C["sup2"], C["borda2"], foco=True)
    P["btn_foco_hover"] = botao(C["sup3"], C["borda2"], foco=True)

    def acento(fundo, foco=False, sombra=True):
        t = T(24, 24)
        if sombra:
            t.ret(0, 1, 24, 24, 6, "#000000", 0.4)
        t.ret(0, 0, 24, 23, 6, fundo)
        t.pintar(lambda x, y: _sd_rrect(x, y, 0.5, 0.5, 23.5, 22.5, 5.5) if y < 3 else 9, "#ffffff", 0.10)
        if foco:
            t.contorno(0, 0, 24, 23, 6, "#ffffff", 1.6, 0.85)
        return t
    P["pri"] = acento(C["prim"])
    P["pri_hover"] = acento(C["prim_hover"])
    P["pri_press"] = acento(C["prim_press"], sombra=False)
    P["pri_dis"] = acento("#2c2a52", sombra=False)
    P["pri_foco"] = acento(C["prim"], foco=True)
    P["pri_foco_hover"] = acento(C["prim_hover"], foco=True)

    def perigo(fundo, borda, foco=False):
        t = T(24, 24)
        t.ret(0, 0, 24, 23, 6, fundo)
        t.contorno(0, 0, 24, 23, 6, C["prim"] if foco else borda, 1.6 if foco else 1.0)
        return t
    P["per"] = perigo(C["sup2"], C["borda2"])
    P["per_hover"] = perigo(C["perigo_fundo"], "#6b2a32")
    P["per_press"] = perigo("#3a1a1f", "#6b2a32")
    P["per_foco"] = perigo(C["sup2"], C["borda2"], True)

    def fantasma(fundo=None, foco=False):
        t = T(24, 24)
        if fundo:
            t.ret(0, 0, 24, 24, 6, fundo)
        if foco:
            t.contorno(0, 0, 24, 24, 6, C["prim"], 1.6)
        return t
    P["fan"] = fantasma()
    P["fan_hover"] = fantasma(C["sup3"])
    P["fan_press"] = fantasma(C["sup4"])
    P["fan_foco"] = fantasma(None, True)
    P["fan_sel"] = fantasma(C["prim_fundo"])

    def campo(borda, fundo=C["campo"], foco=False, larg=1.0):
        t = T(24, 24)
        t.ret(0, 0, 24, 24, 6, fundo)
        t.contorno(0, 0, 24, 24, 6, borda, larg)
        if foco:
            t.pintar(lambda x, y: _sd_rrect(x, y, 1, 0, 23, 23, 5.5) if y > 21 else 9, C["prim"])
        return t
    P["campo"] = campo(C["borda2"])
    P["campo_hover"] = campo("#3f4759")
    P["campo_foco"] = campo(C["prim"], foco=True, larg=1.3)
    P["campo_dis"] = campo("#22262f", fundo="#12141a")
    P["campo_erro"] = campo(C["perigo"], larg=1.3)

    def caixa(estado):
        t = T(20, 20)
        marcado = estado.startswith("sel") or estado.startswith("tri")
        dis = estado.endswith("dis")
        if marcado:
            cor = {"hover": C["prim_hover"], "press": C["prim_press"], "dis": "#2c2a52"}.get(
                estado.split("_")[-1], C["prim"])
            t.ret(1, 1, 19, 19, 5, cor)
            marca = "#8a87b8" if dis else "#ffffff"
            if estado.startswith("sel"):
                t.linha([(5.2, 10.3), (8.6, 13.6), (14.8, 6.9)], marca, 1.9)
            else:
                t.linha([(6, 10), (14, 10)], marca, 1.9)
        else:
            fundo = {"hover": C["sup3"], "press": C["sup4"]}.get(estado.split("_")[-1], C["campo"])
            borda = {"hover": "#6b7488", "dis": "#2b303b", "foco": C["prim"]}.get(estado.split("_")[-1], "#555d70")
            t.ret(1, 1, 19, 19, 5, fundo)
            t.contorno(1, 1, 19, 19, 5, borda, 1.3)
        if estado.endswith("foco"):
            t.contorno(0, 0, 20, 20, 6, C["prim_txt"], 1.0, 0.8)
        return t
    for e in ("sel", "sel_hover", "sel_press", "sel_dis", "sel_foco", "tri", "tri_hover", "tri_dis",
              "nao", "nao_hover", "nao_press", "nao_dis", "nao_foco"):
        P["chk_" + e] = caixa(e)

    def radio(estado):
        t = T(20, 20)
        if estado.startswith("sel"):
            cor = {"hover": C["prim_hover"], "press": C["prim_press"], "dis": "#2c2a52"}.get(
                estado.split("_")[-1], C["prim"])
            t.circ(10, 10, 9, cor)
            t.circ(10, 10, {"hover": 4.4, "press": 3.4}.get(estado.split("_")[-1], 3.8),
                   "#8a87b8" if estado.endswith("dis") else "#ffffff")
        else:
            fundo = {"hover": C["sup3"], "press": C["sup4"]}.get(estado.split("_")[-1], C["campo"])
            borda = {"hover": "#6b7488", "dis": "#2b303b", "foco": C["prim"]}.get(estado.split("_")[-1], "#555d70")
            t.circ(10, 10, 9, fundo)
            t.anel(10, 10, 9, borda, 1.3)
        return t
    for e in ("sel", "sel_hover", "sel_press", "sel_dis", "nao", "nao_hover", "nao_press", "nao_dis", "nao_foco"):
        P["rad_" + e] = radio(e)

    def chave(liga, estado=""):
        t = T(40, 20)
        if liga:
            cor = {"hover": C["prim_hover"], "press": C["prim_press"], "dis": "#2c2a52"}.get(estado, C["prim"])
            t.ret(1, 1, 39, 19, 9, cor)
            t.circ(29, 10, 5.4 if estado == "hover" else 5, "#8a87b8" if estado == "dis" else "#ffffff")
        else:
            fundo = {"hover": C["sup3"], "press": C["sup4"]}.get(estado, C["campo"])
            borda = {"hover": "#6b7488", "dis": "#2b303b"}.get(estado, "#555d70")
            t.ret(1, 1, 39, 19, 9, fundo)
            t.contorno(1, 1, 39, 19, 9, borda, 1.3)
            t.circ(11, 10, 5.4 if estado == "hover" else 5, "#4b5263" if estado == "dis" else C["suave"])
        if estado == "foco":
            t.contorno(0, 0, 40, 20, 10, C["prim_txt"], 1.0, 0.8)
        return t
    for e in ("", "hover", "press", "dis", "foco"):
        P["sw_on" + ("_" + e if e else "")] = chave(True, e)
        P["sw_off" + ("_" + e if e else "")] = chave(False, e)

    def cursor(estado):
        t = T(20, 20)
        t.circ(10, 10.6, 9, "#000000", 0.35)
        t.circ(10, 10, 9, "#2a3040")
        t.anel(10, 10, 9, "#3d4558", 1.0)
        r = {"hover": 5.6, "press": 4.2, "dis": 4.6}.get(estado, 4.8)
        t.circ(10, 10, r, "#4b5263" if estado == "dis" else (C["prim_hover"] if estado == "hover" else C["prim"]))
        return t
    for e in ("", "hover", "press", "dis"):
        P["cur" + ("_" + e if e else "")] = cursor(e)
    P["trilho_h"] = T(16, 4).ret(0, 0, 16, 4, 2, C["borda2"])
    P["trilho_v"] = T(4, 16).ret(0, 0, 4, 16, 2, C["borda2"])

    def rolagem(vert, cor, larg):
        if vert:
            t = T(12, 24)
            t.ret(6 - larg / 2, 2, 6 + larg / 2, 22, larg / 2, cor)
        else:
            t = T(24, 12)
            t.ret(2, 6 - larg / 2, 22, 6 + larg / 2, larg / 2, cor)
        return t
    P["rol_v"] = rolagem(True, "#3a4152", 5)
    P["rol_v_ativo"] = rolagem(True, "#5a6379", 7)
    P["rol_h"] = rolagem(False, "#3a4152", 5)
    P["rol_h_ativo"] = rolagem(False, "#5a6379", 7)
    P["vazio_v"] = T(12, 12)
    P["vazio"] = T(4, 4)

    P["prog_trilho"] = T(16, 6).ret(0, 0, 16, 6, 3, C["borda"])
    P["prog_barra"] = T(16, 6).ret(0, 0, 16, 6, 3, C["prim"])

    def cartao(fundo, borda):
        t = T(32, 32)
        t.ret(0, 0, 32, 32, 10, fundo)
        t.contorno(0, 0, 32, 32, 10, borda, 1.0)
        return t
    P["cartao"] = cartao(C["sup"], C["borda"])
    P["cartao2"] = cartao(C["sup2"], C["borda"])
    P["etiqueta"] = T(16, 16).ret(0, 0, 16, 16, 6, C["sup3"])

    def seta(direcao, cor=C["suave"], tam=(10, 6)):
        t = T(*tam)
        w, h = tam
        if direcao == "baixo":
            pts = [(1.5, 1.5), (w / 2, h - 1.5), (w - 1.5, 1.5)]
        elif direcao == "cima":
            pts = [(1.5, h - 1.5), (w / 2, 1.5), (w - 1.5, h - 1.5)]
        else:
            pts = [(1.5, 1.5), (w - 1.5, h / 2), (1.5, h - 1.5)]
        return t.linha(pts, cor, 1.4)
    P["seta_baixo"] = seta("baixo")
    P["seta_cima"] = seta("cima")
    P["seta_dir"] = seta("dir", tam=(6, 10))

    t = T(10, 10)
    t.ret(0, 9, 10, 10, 0, C["borda"])
    P["cabecalho"] = t
    P["linha"] = T(4, 4).ret(0, 0, 4, 4, 0, C["borda"])

    def aba(sel, hover=False):
        t = T(32, 32)
        if sel:
            t.ret(2, 2, 30, 30, 6, C["sup2"])
            t.ret(10, 27, 22, 30, 1.5, C["prim"])
        elif hover:
            t.ret(2, 2, 30, 30, 6, C["sup3"], 0.6)
        return t
    P["aba"] = aba(False)
    P["aba_hover"] = aba(False, True)
    P["aba_sel"] = aba(True)
    return P


def _familias(root):
    try:
        return set(tkfont.families(root))
    except tk.TclError:
        return set()


FONTES = {}


def preparar_fontes(root):
    fam = _familias(root)

    def escolher(*nomes):
        return next((n for n in nomes if n in fam), nomes[-1])
    texto = escolher("Segoe UI Variable Text", "Segoe UI", "Inter", "DejaVu Sans")
    forte = escolher("Segoe UI Variable Text Semibold", "Segoe UI Semibold", texto)
    titulo = escolher("Segoe UI Variable Display Semibold", "Segoe UI Semibold", forte)
    mono = escolher("Cascadia Mono", "Cascadia Code", "Consolas", "DejaVu Sans Mono")
    icone = escolher("Segoe Fluent Icons", "Segoe MDL2 Assets", "")
    peso = "normal" if forte != texto else "bold"
    peso_t = "normal" if titulo not in (texto, forte) or forte != texto else "bold"
    specs = {
        "CofreTexto": (texto, 10, "normal"),
        "CofrePequeno": (texto, 9, "normal"),
        "CofreForte": (forte, 10, peso),
        "CofreRotulo": (forte, 8, peso),
        "CofreSub": (titulo, 13, peso_t),
        "CofreTitulo": (titulo, 19, peso_t),
        "CofreGrande": (titulo, 24, peso_t),
        "CofreMono": (mono, 11, "normal"),
        "CofreMonoG": (mono, 14, "normal"),
    }
    for nome, (f, tam, p) in specs.items():
        try:
            FONTES[nome] = tkfont.Font(root=root, name=nome, family=f, size=tam, weight=p, exists=False)
        except tk.TclError:
            FONTES[nome] = tkfont.nametofont(nome, root=root)
            FONTES[nome].configure(family=f, size=tam, weight=p)
    FONTES["_icone"] = icone
    return FONTES


# Ícones do próprio Windows (Segoe Fluent Icons / MDL2) com símbolo reserva
ICONES = {
    "busca": ("", "⌕"), "novo": ("", "+"), "cadeado": ("", "🔒"), "aberto": ("", "🔓"),
    "copiar": ("", "⧉"), "ver": ("", "👁"), "ocultar": ("", "◡"), "editar": ("", "✎"),
    "excluir": ("", "🗑"), "imprimir": ("", "⎙"), "config": ("", "⚙"), "mais": ("", "⋯"),
    "chave": ("", "🔑"), "pessoa": ("", "👤"), "alerta": ("", "⚠"), "ok": ("", "✓"),
    "fechar": ("", "✕"), "gerar": ("", "⤨"), "importar": ("", "⤓"), "salvar": ("", "💾"),
    "grupo": ("", "▤"), "historico": ("", "⟲"), "teclado": ("", "⌨"), "digital": ("", "☝"),
    "escudo": ("", "🛡"), "info": ("", "ⓘ"), "todos": ("", "▦"), "atualizar": ("", "↻"),
    "backup": ("", "⛁"), "verificar": ("", "✔"), "tag": ("", "#"), "documento": ("", "▭"),
    "sair": ("", "⏻"), "seta": ("", "›"),
}


def icone(nome):
    """(texto, fonte) do ícone. Usa a fonte de ícones do Windows quando existe."""
    glifo, reserva = ICONES.get(nome, ("", "•"))
    if FONTES.get("_icone"):
        return glifo, (FONTES["_icone"], 12)
    return reserva, FONTES.get("CofreTexto", ("TkDefaultFont", 11))


def barra_titulo_escura(janela):
    """Barra de título escura no Windows 10/11 (combina com o tema)."""
    if not EH_WINDOWS:
        return
    try:
        import ctypes
        from ctypes import wintypes
        janela.update_idletasks()
        hwnd = ctypes.windll.user32.GetAncestor(janela.winfo_id(), 2)
        dwm = ctypes.windll.dwmapi
        sim = ctypes.c_int(1)
        for atributo in (20, 19):                         # DWMWA_USE_IMMERSIVE_DARK_MODE (novo e antigo)
            if dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), atributo, ctypes.byref(sim), 4) == 0:
                break
        r, g, b = _hex(CORES["fundo"])
        cor = ctypes.c_int(r | (g << 8) | (b << 16))     # COLORREF = 0x00BBGGRR
        dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), 35, ctypes.byref(cor), 4)   # DWMWA_CAPTION_COLOR
        r, g, b = _hex(CORES["texto"])
        cor = ctypes.c_int(r | (g << 8) | (b << 16))
        dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), 36, ctypes.byref(cor), 4)   # DWMWA_TEXT_COLOR
    except Exception:
        pass


def aplicar_tema(root):
    C = CORES
    st = ttk.Style(root)
    definir_escala(root)
    preparar_fontes(root)
    P = {n: t.imagem(root) for n, t in _pecas().items()}
    root._imagens_tema = P                      # mantém as imagens vivas
    try:
        st.theme_create("meia-noite", parent="clam")
    except tk.TclError:
        pass
    st.theme_use("meia-noite")

    root.tk_setPalette(background=C["fundo"], foreground=C["texto"], activeBackground=C["sup3"],
                       activeForeground=C["texto"], highlightColor=C["prim"], highlightBackground=C["fundo"],
                       selectBackground=C["prim"], selectForeground="#ffffff", insertBackground=C["texto"],
                       troughColor=C["sup"], disabledForeground=C["fraco"])
    for classe in ("Label", "Button", "Entry", "Text", "Checkbutton", "Radiobutton", "Listbox", "Menu",
                   "Spinbox", "Scale", "Menubutton", "Message", "TEntry", "TCombobox", "TSpinbox"):
        root.option_add(f"*{classe}.Font", "CofreTexto")
    for nome in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkCaptionFont"):
        try:
            tkfont.nametofont(nome, root=root).configure(family=FONTES["CofreTexto"].cget("family"), size=10)
        except tk.TclError:
            pass
    root.option_add("*Menu.background", C["sup2"])
    root.option_add("*Menu.foreground", C["texto"])
    root.option_add("*Menu.activeBackground", C["prim"])
    root.option_add("*Menu.activeForeground", "#ffffff")
    root.option_add("*Menu.relief", "flat")
    root.option_add("*Menu.borderWidth", 0)
    root.option_add("*Menu.activeBorderWidth", 0)
    root.option_add("*TCombobox*Listbox.background", C["sup2"])
    root.option_add("*TCombobox*Listbox.foreground", C["texto"])
    root.option_add("*TCombobox*Listbox.selectBackground", C["prim"])
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
    root.option_add("*TCombobox*Listbox.font", "CofreTexto")
    root.option_add("*TCombobox*Listbox.borderWidth", 0)
    root.option_add("*Text.background", C["campo"])
    root.option_add("*Text.relief", "flat")
    root.option_add("*Text.highlightThickness", 1)
    root.option_add("*Text.highlightBackground", C["borda2"])
    root.option_add("*Text.highlightColor", C["prim"])
    root.option_add("*Toplevel.background", C["fundo"])

    st.configure(".", background=C["fundo"], foreground=C["texto"], font="CofreTexto", bordercolor=C["borda"],
                 lightcolor=C["fundo"], darkcolor=C["fundo"], troughcolor=C["sup"], focuscolor=C["prim"],
                 selectbackground=C["prim"], selectforeground="#ffffff", insertcolor=C["texto"],
                 insertwidth=1, fieldbackground=C["campo"], borderwidth=0, relief="flat")
    st.map(".", foreground=[("disabled", C["fraco"])])

    def elemento(nome, base, mapa, **kw):
        estados = []
        for estado, img in mapa:
            estados.append((estado, P[img]))
        st.element_create(nome, "image", P[base], *estados, **kw)

    # Botões
    def botao(estilo, elem, base, mapa, padding=(14, 6), fg=C["texto"], fg_map=None, font="CofreTexto"):
        elemento(elem, base, mapa, border=_px(7), sticky="nsew")
        st.layout(estilo, [(elem, {"sticky": "nsew", "children": [
            ("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"side": "left", "expand": 1})]})]})])
        st.configure(estilo, padding=padding, anchor="center", foreground=fg, font=font)
        st.map(estilo, foreground=fg_map or [("disabled", "#5d6476")])
    padrao = [("disabled", "btn_dis"), ("pressed", "btn_press"), ("active focus", "btn_foco_hover"),
              ("active", "btn_hover"), ("focus", "btn_foco")]
    botao("TButton", "Cofre.botao", "btn", padrao, padding=(14, 7))
    botao("Pequeno.TButton", "Cofre.botaoP", "btn", padrao, padding=(10, 3), font="CofrePequeno")
    botao("Acao.TButton", "Cofre.botaoA", "btn", padrao, padding=(14, 7))
    primario = [("disabled", "pri_dis"), ("pressed", "pri_press"), ("active focus", "pri_foco_hover"),
                ("active", "pri_hover"), ("focus", "pri_foco")]
    botao("Primario.TButton", "Cofre.primario", "pri", primario, padding=(18, 7), fg="#ffffff",
          fg_map=[("disabled", "#7c79a8")], font="CofreForte")
    botao("Accent.TButton", "Cofre.primario2", "pri", primario, padding=(14, 7), fg="#ffffff",
          fg_map=[("disabled", "#7c79a8")], font="CofreForte")
    perigo = [("pressed", "per_press"), ("active", "per_hover"), ("focus", "per_foco")]
    botao("Perigo.TButton", "Cofre.perigo", "per", perigo, padding=(14, 7), fg=C["perigo"],
          fg_map=[("disabled", "#5d6476")])
    botao("AcaoPerigo.TButton", "Cofre.perigoA", "per", perigo, padding=(14, 7), fg=C["perigo"])
    fantasma = [("pressed", "fan_press"), ("active", "fan_hover"), ("focus", "fan_foco")]
    botao("Fantasma.TButton", "Cofre.fantasma", "fan", fantasma, padding=(8, 5), fg=C["suave"],
          fg_map=[("active", C["texto"]), ("disabled", "#4b5263")])
    botao("Icone.TButton", "Cofre.icone", "fan", fantasma, padding=(6, 4), fg=C["suave"],
          fg_map=[("active", C["texto"]), ("disabled", "#4b5263")])
    botao("Toolbutton", "Cofre.tool", "fan", [("pressed", "fan_press"), ("selected", "fan_sel"),
                                              ("active", "fan_hover"), ("focus", "fan_foco")], padding=(8, 5))

    # Menubutton
    elemento("Cofre.menubotao", "btn", padrao, border=_px(7), sticky="nsew")
    st.element_create("Cofre.menuseta", "image", P["seta_baixo"], sticky="e", width=_px(12))
    st.layout("TMenubutton", [("Cofre.menubotao", {"sticky": "nsew", "children": [
        ("Menubutton.padding", {"sticky": "nsew", "children": [
            ("Cofre.menuseta", {"side": "right", "sticky": ""}),
            ("Menubutton.label", {"side": "left", "expand": 1})]})]})])
    st.configure("TMenubutton", padding=(14, 6, 10, 6), foreground=C["texto"])

    # Caixas de seleção, rádio e chave liga/desliga
    elemento("Cofre.check", "chk_nao", [
        ("alternate disabled", "chk_tri_dis"), ("selected disabled", "chk_sel_dis"), ("disabled", "chk_nao_dis"),
        ("pressed alternate", "chk_tri_hover"), ("active alternate", "chk_tri_hover"), ("alternate", "chk_tri"),
        ("pressed selected", "chk_sel_press"), ("active selected", "chk_sel_hover"), ("focus selected", "chk_sel_foco"),
        ("selected", "chk_sel"), ("pressed", "chk_nao_press"), ("active", "chk_nao_hover"),
        ("focus", "chk_nao_foco")], width=_px(28), sticky="w")
    st.layout("TCheckbutton", [("Checkbutton.padding", {"sticky": "nsew", "children": [
        ("Cofre.check", {"side": "left", "sticky": ""}), ("Checkbutton.label", {"side": "left", "expand": 1, "sticky": "w"})]})])
    st.configure("TCheckbutton", padding=(0, 4), foreground=C["texto"])
    elemento("Cofre.radio", "rad_nao", [
        ("selected disabled", "rad_sel_dis"), ("disabled", "rad_nao_dis"), ("pressed selected", "rad_sel_press"),
        ("active selected", "rad_sel_hover"), ("selected", "rad_sel"), ("pressed", "rad_nao_press"),
        ("active", "rad_nao_hover"), ("focus", "rad_nao_foco")], width=_px(28), sticky="w")
    st.layout("TRadiobutton", [("Radiobutton.padding", {"sticky": "nsew", "children": [
        ("Cofre.radio", {"side": "left", "sticky": ""}), ("Radiobutton.label", {"side": "left", "expand": 1, "sticky": "w"})]})])
    st.configure("TRadiobutton", padding=(0, 4), foreground=C["texto"])
    elemento("Cofre.chave", "sw_off", [
        ("selected disabled", "sw_on_dis"), ("disabled", "sw_off_dis"), ("pressed selected", "sw_on_press"),
        ("active selected", "sw_on_hover"), ("focus selected", "sw_on_foco"), ("selected", "sw_on"),
        ("pressed", "sw_off_press"), ("active", "sw_off_hover"), ("focus", "sw_off_foco")], width=_px(50), sticky="w")
    st.layout("Switch.TCheckbutton", [("Checkbutton.padding", {"sticky": "nsew", "children": [
        ("Cofre.chave", {"side": "left", "sticky": ""}), ("Checkbutton.label", {"side": "left", "expand": 1, "sticky": "w"})]})])
    st.configure("Switch.TCheckbutton", padding=(0, 4), foreground=C["texto"])

    # Campos de texto
    campo = [("invalid", "campo_erro"), ("disabled", "campo_dis"), ("focus", "campo_foco"), ("hover", "campo_hover")]
    elemento("Cofre.campo", "campo", campo, border=_px(8), sticky="nsew")
    st.layout("TEntry", [("Cofre.campo", {"sticky": "nsew", "children": [
        ("Entry.padding", {"sticky": "nsew", "children": [("Entry.textarea", {"sticky": "nsew"})]})]})])
    st.configure("TEntry", padding=(10, 7, 10, 7), foreground=C["texto"], insertcolor=C["texto"])
    st.map("TEntry", foreground=[("disabled", C["fraco"])])
    st.element_create("Cofre.seta", "image", P["seta_baixo"], width=_px(30), sticky="")
    elemento("Cofre.campoC", "campo", [("readonly focus", "campo_foco"), ("readonly hover", "campo_hover")] + campo,
             border=_px(8), sticky="nsew")
    st.layout("TCombobox", [("Cofre.campoC", {"sticky": "nsew", "children": [
        ("Cofre.seta", {"side": "right", "sticky": "ns"}),
        ("Combobox.padding", {"sticky": "nsew", "children": [("Combobox.textarea", {"sticky": "nsew"})]})]})])
    st.configure("TCombobox", padding=(10, 7, 4, 7), foreground=C["texto"], arrowsize=12)
    st.map("TCombobox", fieldbackground=[("readonly", C["campo"])], foreground=[("disabled", C["fraco"])],
           selectbackground=[("readonly", C["campo"])], selectforeground=[("readonly", C["texto"])])
    st.configure("ComboboxPopdownFrame", borderwidth=1, relief="solid", bordercolor=C["borda2"])
    elemento("Cofre.campoS", "campo", campo, border=_px(8), sticky="nsew")
    st.element_create("Cofre.cima", "image", P["seta_cima"], width=_px(26), height=_px(14), sticky="")
    st.element_create("Cofre.baixo", "image", P["seta_baixo"], width=_px(26), height=_px(14), sticky="")
    st.layout("TSpinbox", [("Cofre.campoS", {"sticky": "nsew", "children": [
        ("Cofre.baixo", {"side": "right", "sticky": "ns"}), ("Cofre.cima", {"side": "right", "sticky": "ns"}),
        ("Spinbox.padding", {"sticky": "nsew", "children": [("Spinbox.textarea", {"sticky": "nsew"})]})]})])
    st.configure("TSpinbox", padding=(10, 6, 2, 6), foreground=C["texto"], arrowsize=12)

    # Régua (Scale), barra de progresso, rolagem
    st.element_create("CofreH.trough", "image", P["trilho_h"], border=(_px(3), _px(0)), sticky="ew")
    st.element_create("CofreV.trough", "image", P["trilho_v"], border=(_px(0), _px(3)), sticky="ns")
    elemento("Cofre.slider", "cur", [("disabled", "cur_dis"), ("pressed", "cur_press"), ("active", "cur_hover")],
             sticky="")
    st.layout("Horizontal.TScale", [("CofreH.trough", {"sticky": "ew", "children": [
        ("Cofre.slider", {"side": "left", "sticky": ""})]})])
    st.layout("Vertical.TScale", [("CofreV.trough", {"sticky": "ns", "children": [
        ("Cofre.slider", {"side": "top", "sticky": ""})]})])
    st.configure("TScale", background=C["fundo"])
    st.element_create("Cofre.trough", "image", P["prog_trilho"], border=_px(3), sticky="ew")
    st.element_create("Cofre.pbar", "image", P["prog_barra"], border=_px(3), sticky="ew")
    st.layout("Horizontal.TProgressbar", [("Cofre.trough", {"sticky": "nsew", "children": [
        ("Cofre.pbar", {"side": "left", "sticky": "ns"})]})])
    st.configure("Horizontal.TProgressbar", thickness=6)
    st.element_create("CofreRV.trough", "image", P["vazio_v"], sticky="ns")
    elemento("CofreRV.thumb", "rol_v", [("pressed", "rol_v_ativo"), ("active", "rol_v_ativo")], border=(_px(0), _px(6)),
             sticky="ns")
    st.layout("Vertical.TScrollbar", [("CofreRV.trough", {"sticky": "ns", "children": [
        ("CofreRV.thumb", {"expand": 1, "sticky": "nswe"})]})])
    st.element_create("CofreRH.trough", "image", P["vazio_v"], sticky="ew")
    elemento("CofreRH.thumb", "rol_h", [("pressed", "rol_h_ativo"), ("active", "rol_h_ativo")], border=(_px(6), _px(0)),
             sticky="ew")
    st.layout("Horizontal.TScrollbar", [("CofreRH.trough", {"sticky": "ew", "children": [
        ("CofreRH.thumb", {"expand": 1, "sticky": "nswe"})]})])

    # Separador, cartões, molduras, abas
    linha = tk.PhotoImage(master=root, width=4, height=1)       # linha de 1 pixel real, em qualquer escala
    linha.put(C["borda"], to=(0, 0, 4, 1))
    linha_v = tk.PhotoImage(master=root, width=1, height=4)
    linha_v.put(C["borda"], to=(0, 0, 1, 4))
    P["linha_px"], P["linha_v_px"] = linha, linha_v
    st.element_create("Cofre.sep", "image", linha, border=(1, 0, 1, 0), sticky="ew")
    st.element_create("Cofre.sepV", "image", linha_v, border=(0, 1, 0, 1), sticky="ns")
    st.layout("TSeparator", [("Cofre.sep", {"sticky": "ew"})])
    st.layout("Horizontal.TSeparator", [("Cofre.sep", {"sticky": "ew"})])
    st.layout("Vertical.TSeparator", [("Cofre.sepV", {"sticky": "ns"})])
    st.element_create("Cofre.cartao", "image", P["cartao"], border=_px(11), padding=6, sticky="nsew")
    st.layout("Card.TFrame", [("Cofre.cartao", {"sticky": "nsew", "children": [("Frame.padding", {"expand": 1})]})])
    st.configure("Card.TFrame", background=C["sup"])
    st.element_create("Cofre.cartao2", "image", P["cartao2"], border=_px(11), padding=6, sticky="nsew")
    st.layout("Card2.TFrame", [("Cofre.cartao2", {"sticky": "nsew", "children": [("Frame.padding", {"expand": 1})]})])
    st.configure("Card2.TFrame", background=C["sup2"])
    st.element_create("Cofre.etiqueta", "image", P["etiqueta"], border=_px(6), sticky="nsew")
    for nome, cor in (("Etiqueta.TLabel", C["texto"]), ("EtiquetaFraca.TLabel", C["fraco"])):
        st.layout(nome, [("Cofre.etiqueta", {"sticky": "nsew", "children": [
            ("Label.padding", {"sticky": "nsew", "children": [("Label.label", {"sticky": "nsew"})]})]})])
        st.configure(nome, background=C["sup2"], foreground=cor, padding=(_px(8), _px(2)), font="CofrePequeno")
    st.element_create("Cofre.moldura", "image", P["cartao"], border=_px(11), padding=10, sticky="nsew")
    st.layout("TLabelframe", [("Cofre.moldura", {"sticky": "nsew", "children": [
        ("Labelframe.padding", {"expand": 1, "sticky": "nsew"})]})])
    st.configure("TLabelframe", background=C["sup"], padding=8)
    st.configure("TLabelframe.Label", background=C["fundo"], foreground=C["suave"], font="CofreForte")
    st.element_create("Cofre.aba", "image", P["aba"], ("selected", P["aba_sel"]), ("active", P["aba_hover"]),
                      border=_px(8), padding=(14, 8), sticky="nsew")
    st.layout("TNotebook.Tab", [("Cofre.aba", {"sticky": "nsew", "children": [
        ("Notebook.label", {"sticky": ""})]})])
    st.configure("TNotebook", background=C["fundo"], borderwidth=0, tabmargins=(0, 0, 0, 8))
    st.configure("TNotebook.Tab", foreground=C["suave"], font="CofreForte")
    st.map("TNotebook.Tab", foreground=[("selected", C["texto"]), ("active", C["texto"])])

    # Listas (Treeview)
    st.element_create("Cofre.cab", "image", P["cabecalho"], border=(_px(1), _px(1), _px(1), _px(2)), padding=(10, 8), sticky="nsew")
    st.layout("Treeview.Heading", [("Cofre.cab", {"sticky": "nsew", "children": [
        ("Treeheading.padding", {"sticky": "nsew", "children": [
            ("Treeheading.image", {"side": "right", "sticky": ""}),
            ("Treeheading.text", {"sticky": "we"})]})]})])
    st.configure("Treeview.Heading", background=C["sup"], foreground=C["fraco"], font="CofreRotulo")
    st.map("Treeview.Heading", foreground=[("active", C["suave"])])
    st.configure("Treeview", background=C["sup"], fieldbackground=C["sup"], foreground=C["texto"],
                 rowheight=_px(34), borderwidth=0, font="CofreTexto")
    st.map("Treeview", background=[("selected", C["prim_fundo"])], foreground=[("selected", "#ffffff")])
    st.element_create("Cofre.indicador", "image", P["seta_dir"], ("user1", P["seta_baixo"]),
                      ("user2", P["vazio"]), width=_px(22), sticky="")
    st.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    st.layout("Treeview.Item", [("Treeitem.padding", {"sticky": "nswe", "children": [
        ("Cofre.indicador", {"side": "left", "sticky": ""}), ("Treeitem.image", {"side": "left", "sticky": ""}),
        ("Treeitem.text", {"side": "left", "sticky": ""})]})])

    # Rótulos e molduras (estilos usados pelo programa)
    for nome, fundo in (("Pagina", C["fundo"]), ("Noite", C["fundo"]), ("Fundo", C["fundo"]),
                        ("Lateral", C["lateral"]), ("Sup", C["sup"]), ("Cartao", C["sup"])):
        st.configure(f"{nome}.TFrame", background=fundo)
        st.configure(f"{nome}.TLabel", background=fundo)
    st.configure("TFrame", background=C["fundo"])
    st.configure("TLabel", background=C["fundo"], foreground=C["texto"])
    st.configure("Suave.TLabel", foreground=C["suave"])
    st.configure("Fraco.TLabel", foreground=C["fraco"])
    st.configure("Marca.TLabel", font="CofreGrande")
    st.configure("Titulo.TLabel", font="CofreTitulo")
    st.configure("H2.TLabel", font="CofreSub")
    st.configure("Campo.TLabel", foreground=C["fraco"], font="CofreRotulo")
    st.configure("Valor.TLabel", font="CofreMono")
    st.configure("Erro.TLabel", foreground=C["perigo"])
    st.configure("Ok.TLabel", foreground=C["ok"])
    st.configure("Lateral.TLabel", foreground=C["fraco"], font="CofreRotulo")
    st.configure("LateralMarca.TLabel", foreground=C["texto"], font="CofreSub")
    st.configure("Fino.TButton", padding=(12, 9))
    st.configure("Quadrado.TButton", padding=(10, 8))
    st.configure("Busca.TEntry", padding=(36, 8, 10, 8))
    st.configure("Segmento.Toolbutton", padding=(14, 6), foreground=C["suave"], font="CofreForte")
    st.map("Segmento.Toolbutton", foreground=[("selected", C["texto"]), ("active", C["texto"])])
    # Variações para widgets sobre cartões (C.) e sobre a barra lateral (L.)
    bases = ["TLabel", "Suave.TLabel", "Fraco.TLabel", "Campo.TLabel", "Valor.TLabel", "H2.TLabel",
             "Titulo.TLabel", "Marca.TLabel", "Erro.TLabel", "Ok.TLabel", "TFrame", "TButton",
             "Primario.TButton", "Accent.TButton", "Pequeno.TButton", "Acao.TButton", "Perigo.TButton",
             "AcaoPerigo.TButton", "Fantasma.TButton", "Icone.TButton", "Fino.TButton", "Quadrado.TButton", "Toolbutton",
             "Segmento.Toolbutton", "TMenubutton", "TCheckbutton", "TRadiobutton", "Switch.TCheckbutton",
             "TEntry", "TCombobox", "TSpinbox", "Horizontal.TScale", "Horizontal.TProgressbar",
             "Vertical.TScrollbar"]
    for pref, cor in (("C", C["sup"]), ("L", C["lateral"]), ("S2", C["sup2"])):
        for b in bases:
            st.configure(f"{pref}.{b}", background=cor)
    root.configure(bg=C["fundo"])
    return st


# ---------- ícones vetoriais (traço fino, estilo Windows 11) ----------
def _arco(cx, cy, r, a0, a1, n=14):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def _curva(p0, p1, p2, n=12):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]) for t in (i / n for i in range(n + 1))]


def _desenhar_icone(nome, cor, tam=16, larg=1.45):
    t = _Tela(tam, tam)
    s = tam / 16.0

    def L(*pts, w=larg):
        t.linha([(x * s, y * s) for x, y in pts], cor, w * max(s, 1) if s > 1 else w)

    def R(x0, y0, x1, y1, r, w=larg):
        t.contorno(x0 * s, y0 * s, x1 * s, y1 * s, r * s, cor, w)

    def F(x0, y0, x1, y1, r):
        t.ret(x0 * s, y0 * s, x1 * s, y1 * s, r * s, cor)

    def O(cx, cy, r, w=larg):
        t.anel(cx * s, cy * s, r * s + w / 2, cor, w)

    def P(cx, cy, r):
        t.circ(cx * s, cy * s, r * s, cor)

    if nome == "novo":
        L((8, 2.8), (8, 13.2)); L((2.8, 8), (13.2, 8))
    elif nome == "busca":
        O(7, 7, 4.3); L((10.3, 10.3), (13.6, 13.6))
    elif nome in ("cadeado", "aberto"):
        R(2.8, 7.2, 13.2, 14.2, 2.2)
        arco = _arco(8, 5.6, 3.1, 180, 360)
        if nome == "cadeado":
            L((4.9, 7.2), *arco[:1], *arco, (11.1, 7.2))
        else:
            L((4.9, 7.2), *arco[:1], *arco[:10])
        P(8, 10.6, 1.1)
    elif nome == "copiar":
        R(2.6, 5.4, 10.6, 13.6, 1.8)
        L((5.4, 5.4), (5.4, 3.6), (6.4, 2.6), (12.6, 2.6), (13.4, 3.4), (13.4, 9.6), (12.4, 10.6), (10.6, 10.6))
    elif nome in ("ver", "ocultar"):
        cima = _curva((1.6, 8), (8, 1.8), (14.4, 8))
        baixo = _curva((1.6, 8), (8, 14.2), (14.4, 8))
        L(*cima); L(*baixo); O(8, 8, 1.9)
        if nome == "ocultar":
            L((2.6, 2.6), (13.4, 13.4))
    elif nome == "editar":
        L((10.4, 2.6), (13.4, 5.6), (5.6, 13.4), (2.6, 13.4), (2.6, 10.4), (10.4, 2.6)); L((8.8, 4.2), (11.8, 7.2))
    elif nome == "excluir":
        L((2.4, 4.4), (13.6, 4.4)); L((6, 4.4), (6.4, 2.6), (9.6, 2.6), (10, 4.4))
        L((3.9, 4.4), (4.8, 13.4), (11.2, 13.4), (12.1, 4.4)); L((6.6, 7), (6.8, 11)); L((9.4, 7), (9.2, 11))
    elif nome == "imprimir":
        L((4.6, 5.8), (4.6, 2.6), (11.4, 2.6), (11.4, 5.8)); R(1.8, 5.8, 14.2, 11.4, 1.8)
        F(4.2, 9.2, 11.8, 10.6, 0); R(4.6, 9.4, 11.4, 14, 0.8)
    elif nome == "chave":
        O(5, 11, 2.7); L((6.9, 9.1), (13.4, 2.6)); L((10.6, 5.4), (12.6, 7.4)); L((12.4, 3.6), (14, 5.2))
    elif nome == "gerar":
        R(2.4, 2.4, 13.6, 13.6, 3)
        for cx, cy in ((5.6, 5.6), (8, 8), (10.4, 10.4)):
            P(cx, cy, 1.15)
    elif nome == "mais":
        for cx in (3.4, 8, 12.6):
            P(cx, 8, 1.3)
    elif nome in ("escudo", "verificar"):
        L((8, 1.8), (13.2, 3.8), (13.2, 7.6), *_curva((13.2, 7.6), (12.8, 12), (8, 14.3))[1:],
          *_curva((8, 14.3), (3.2, 12), (2.8, 7.6))[1:], (2.8, 3.8), (8, 1.8))
        if nome == "verificar":
            L((5.4, 8.1), (7.3, 10), (10.8, 6.2))
    elif nome == "ok":
        L((3, 8.6), (6.5, 12), (13, 4.6), w=larg * 1.15)
    elif nome == "alerta":
        L((8, 2), (14.4, 13.4), (1.6, 13.4), (8, 2)); L((8, 6.2), (8, 9.4)); P(8, 11.5, 0.95)
    elif nome == "info":
        O(8, 8, 6.2); L((8, 7.4), (8, 11.2)); P(8, 5.1, 0.95)
    elif nome == "grupo":
        L((1.8, 12.6), (1.8, 4.2), (2.6, 3.2), (6, 3.2), (7.6, 4.8), (13.4, 4.8), (14.2, 5.6), (14.2, 12.4),
          (13.4, 13.2), (2.6, 13.2), (1.8, 12.4))
    elif nome == "todos":
        for x0, y0 in ((2.2, 2.2), (8.8, 2.2), (2.2, 8.8), (8.8, 8.8)):
            R(x0, y0, x0 + 5, y0 + 5, 1.4)
    elif nome == "pessoa":
        O(8, 5.4, 2.6); L(*_curva((2.8, 14), (3.4, 9.2), (8, 9.2)), *_curva((8, 9.2), (12.6, 9.2), (13.2, 14))[1:])
    elif nome == "teclado":
        R(1.4, 3.8, 14.6, 12.2, 2)
        for x in (4.2, 6.7, 9.3, 11.8):
            P(x, 6.6, 0.75)
        L((5, 9.6), (11, 9.6))
    elif nome == "importar":
        L((8, 2.2), (8, 10)); L((4.8, 6.9), (8, 10), (11.2, 6.9)); L((2.4, 10.4), (2.4, 13.6), (13.6, 13.6), (13.6, 10.4))
    elif nome == "exportar":
        L((8, 10), (8, 2.2)); L((4.8, 5.3), (8, 2.2), (11.2, 5.3)); L((2.4, 10.4), (2.4, 13.6), (13.6, 13.6), (13.6, 10.4))
    elif nome == "historico":
        O(8, 8, 6); L((8, 4.6), (8, 8), (10.6, 9.6))
    elif nome == "backup":
        R(2.4, 2.4, 13.6, 13.6, 2); L((5.2, 2.4), (5.2, 5.6), (10.8, 5.6), (10.8, 2.4)); O(8, 9.8, 1.6)
    elif nome == "fechar":
        L((3.4, 3.4), (12.6, 12.6)); L((12.6, 3.4), (3.4, 12.6))
    elif nome == "seta":
        L((6, 3.4), (10.6, 8), (6, 12.6))
    elif nome == "seta_baixo":
        L((3.4, 6), (8, 10.6), (12.6, 6))
    elif nome == "tag":
        L((2.2, 2.2), (8.2, 2.2), (14, 8), (8, 14), (2.2, 8.2), (2.2, 2.2)); P(5.4, 5.4, 1.1)
    elif nome == "config":
        L((2, 4.5), (14, 4.5)); L((2, 11.5), (14, 11.5)); F(4.2, 2.6, 7.2, 6.4, 1.4); F(8.8, 9.6, 11.8, 13.4, 1.4)
    elif nome == "documento":
        L((9.4, 1.8), (3.4, 1.8), (3.4, 14.2), (12.6, 14.2), (12.6, 5), (9.4, 1.8), (9.4, 5), (12.6, 5))
        L((5.8, 8.4), (10.2, 8.4)); L((5.8, 11), (10.2, 11))
    elif nome == "atualizar":
        arco = _arco(8, 8, 5.6, -60, 230)
        L(*arco); L((12.4, 1.6), (10.8, 3.2), (13.4, 4.6))
    elif nome == "sair":
        L((6.4, 2.4), (2.4, 2.4), (2.4, 13.6), (6.4, 13.6)); L((6.4, 8), (14, 8)); L((10.8, 4.8), (14, 8), (10.8, 11.2))
    return t


_CACHE_ICONES = {}


def imagem_icone(master, nome, cor=None, tam=16):
    cor = cor or CORES["suave"]
    chave = (nome, cor, tam)
    if chave not in _CACHE_ICONES:
        _CACHE_ICONES[chave] = _desenhar_icone(nome, cor, tam).imagem(master)
    return _CACHE_ICONES[chave]


def desenhar_marca(tam=64):
    """Marca do programa: cadeado branco sobre quadrado arredondado em degradê índigo→violeta."""
    t = _Tela(tam, tam)
    s = tam / 64.0
    a, b = _hex("#7c6cff"), _hex("#4338ca")
    r0 = 15 * s
    for faixa in range(16):           # degradê diagonal por faixas finas
        f = faixa / 15
        cor = "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))
        t.pintar(lambda x, y, f=f: max(_sd_rrect(x, y, 0, 0, tam, tam, r0),
                                        abs((x + y) / (2 * tam) - f - 1 / 32) * tam - tam / 32 - 0.5), cor)
    t.pintar(lambda x, y: _sd_rrect(x, y, 0.5, 0.5, tam - 0.5, tam * 0.5, r0) if y < tam * 0.5 else 99,
             "#ffffff", 0.08)
    # cadeado
    t.ret(17 * s, 29 * s, 47 * s, 51 * s, 5 * s, "#ffffff")
    arco = _arco(32 * s, 23 * s, 9 * s, 180, 360, 20)
    t.linha([(23 * s, 30 * s)] + arco + [(41 * s, 30 * s)], "#ffffff", 4.2 * s)
    t.circ(32 * s, 38.5 * s, 3.2 * s, "#4f46e5")
    t.ret(30.6 * s, 39 * s, 33.4 * s, 45 * s, 1.2 * s, "#4f46e5")
    return t


def desenhar_avatar(cor, tam=36, raio=None):
    """Quadrado arredondado colorido (a letra é escrita por cima com o próprio Tk)."""
    t = _Tela(tam, tam)
    t.ret(0, 0, tam, tam, raio if raio is not None else tam * 0.28, cor)
    t.pintar(lambda x, y: _sd_rrect(x, y, 0, 0, tam, tam, raio if raio is not None else tam * 0.28)
             if y < tam / 2 else 99, "#ffffff", 0.07)
    return t


def brilho_radial(canvas, cx, cy, raio, cor_centro, cor_fundo, passos=48):
    """Halo suave desenhado com anéis concêntricos (fundo artístico das telas de entrada)."""
    a, b = _hex(cor_fundo), _hex(cor_centro)
    for i in range(passos, 0, -1):
        f = i / passos
        k = (1 - f) ** 2
        cor = "#%02x%02x%02x" % tuple(int(a[j] + (b[j] - a[j]) * k) for j in range(3))
        r = raio * f
        canvas.create_oval(cx - r, cy - r * 0.62, cx + r, cy + r * 0.62, fill=cor, outline=cor, tags="brilho")

def imagem_nove_fatias(master, peca, borda, w, h):
    """Monta uma imagem w×h a partir de uma peça pequena (cantos fixos, bordas e miolo repetidos)."""
    src = peca.imagem(master)
    img = tk.PhotoImage(master=master, width=max(w, 1), height=max(h, 1))
    pw, ph = peca.w, peca.h
    b = borda
    partes = [  # (origem x0,y0,x1,y1) -> (destino x0,y0,x1,y1)
        ((0, 0, b, b), (0, 0, b, b)), ((pw - b, 0, pw, b), (w - b, 0, w, b)),
        ((0, ph - b, b, ph), (0, h - b, b, h)), ((pw - b, ph - b, pw, ph), (w - b, h - b, w, h)),
        ((b, 0, b + 1, b), (b, 0, w - b, b)), ((b, ph - b, b + 1, ph), (b, h - b, w - b, h)),
        ((0, b, b, b + 1), (0, b, b, h - b)), ((pw - b, b, pw, b + 1), (w - b, b, w, h - b)),
        ((b, b, b + 1, b + 1), (b, b, w - b, h - b))]
    for (sx0, sy0, sx1, sy1), (dx0, dy0, dx1, dy1) in partes:
        if dx1 > dx0 and dy1 > dy0:
            img.tk.call(img, "copy", src, "-from", sx0, sy0, sx1, sy1, "-to", dx0, dy0, dx1, dy1,
                        "-compositingrule", "set")
    img._fonte = src
    return img


def peca_cartao(fundo, borda, raio=14):
    t = _Tela(2 * raio + 2, 2 * raio + 2)
    n = 2 * raio + 2
    t.ret(0, 0, n, n, raio, fundo)
    if borda:
        t.contorno(0, 0, n, n, raio, borda, 1.0 / t.s)
    return t, (t.w - 1) // 2


def peca_sombra(raio=14, espalhar=18, forca=0.55):
    n = 2 * (raio + espalhar) + 2
    t = _Tela(n, n)
    m = espalhar

    def dist(x, y):
        d = _sd_rrect(x, y, m, m + 4, n - m, n - m + 4, raio)
        if d <= 0:
            return -1.0
        f = max(0.0, 1 - d / espalhar)
        return 0.5 - f * f          # cobertura = f² (queda suave)
    t.pintar(dist, "#000000", forca, bruto=True)
    return t, (t.w - 1) // 2


# ---------- caixas de mensagem no tema (substituem as do Windows, que seriam brancas) ----------
# As caixas originais são guardadas assim que o programa carrega (antes de qualquer substituição)
_MB_ORIGINAIS = ({n: getattr(messagebox, n, None) for n in (
    "showinfo", "showwarning", "showerror", "askyesno", "askokcancel", "askyesnocancel", "askquestion",
    "askretrycancel")} if tk is not None else {})


def _caixa_mensagem(tipo, titulo, mensagem, botoes, padrao, cancelar, icone_nome, cor_icone, **kw):
    pai = kw.get("parent") or tk._default_root
    try:
        foco = pai.focus_get()
        if foco is not None:
            pai = foco.winfo_toplevel()
    except (tk.TclError, KeyError, AttributeError):
        pass
    d = tk.Toplevel(pai)
    d.withdraw()
    d.title(titulo or "Cofre de Senhas")
    d.resizable(False, False)
    try:
        if pai.winfo_viewable():
            d.transient(pai)
    except tk.TclError:
        pass
    C = CORES
    resultado = {"v": cancelar}
    corpo = ttk.Frame(d, padding=(24, 22, 24, 16))
    corpo.pack(fill="both", expand=True)
    topo = ttk.Frame(corpo)
    topo.pack(fill="x")
    n = _px(40)
    marca = tk.Canvas(topo, width=n, height=n, bg=C["fundo"], highlightthickness=0)
    fundo_ic = {"perigo": C["perigo_fundo"], "alerta": C["alerta_fundo"], "ok": C["ok_fundo"]}.get(
        cor_icone, C["prim_fundo"])
    marca._img = imagem_nove_fatias(d, *peca_cartao(fundo_ic, None, 12), n, n)
    marca.create_image(n // 2, n // 2, image=marca._img)
    marca._ic = imagem_icone(d, icone_nome, C.get(cor_icone, C["prim_txt"]), 20)
    marca.create_image(n // 2, n // 2, image=marca._ic)
    marca.pack(side="left", anchor="n", padx=(0, 14))
    textos = ttk.Frame(topo)
    textos.pack(side="left", fill="both", expand=True)
    ttk.Label(textos, text=titulo or "", style="H2.TLabel").pack(anchor="w")
    ttk.Label(textos, text=mensagem or "", wraplength=440, justify="left").pack(anchor="w", pady=(6, 0))
    barra = ttk.Frame(corpo)
    barra.pack(fill="x", pady=(20, 0))
    alvo_foco = None
    for rotulo, valor in reversed(botoes):
        estilo = "Primario.TButton" if valor == padrao else "TButton"
        if valor == padrao and cor_icone == "perigo" and tipo.startswith("ask"):
            estilo = "Perigo.TButton"
        b = ttk.Button(barra, text=rotulo, style=estilo,
                       command=lambda v=valor: (resultado.__setitem__("v", v), d.destroy()))
        b.pack(side="right", padx=(8, 0))
        if valor == padrao:
            alvo_foco = b
    d.bind("<Escape>", lambda e: (resultado.__setitem__("v", cancelar), d.destroy()))
    d.bind("<Return>", lambda e: (resultado.__setitem__("v", padrao), d.destroy()))
    d.protocol("WM_DELETE_WINDOW", lambda: (resultado.__setitem__("v", cancelar), d.destroy()))
    d.update_idletasks()
    try:
        x = pai.winfo_rootx() + (pai.winfo_width() - d.winfo_reqwidth()) // 2
        y = pai.winfo_rooty() + max(40, (pai.winfo_height() - d.winfo_reqheight()) // 3)
        d.geometry(f"+{max(0, x)}+{max(0, y)}")
    except tk.TclError:
        pass
    d.deiconify()
    barra_titulo_escura(d)
    proteger_contra_captura(d)
    try:
        d.grab_set()
    except tk.TclError:
        pass
    if alvo_foco is not None:
        alvo_foco.focus_set()
    d.wait_window()
    return resultado["v"]


def instalar_caixas_de_mensagem():
    """Troca as caixas de mensagem padrão pelas do tema — exceto se já tiverem sido
    substituídas por outro código (por exemplo, nos testes automáticos)."""
    if tk is None:
        return
    defs = {
        "showinfo": ("show", [("OK", "ok")], "ok", "ok", "info", "prim_txt"),
        "showwarning": ("show", [("OK", "ok")], "ok", "ok", "alerta", "alerta"),
        "showerror": ("show", [("OK", "ok")], "ok", "ok", "alerta", "perigo"),
        "askyesno": ("ask", [("Sim", True), ("Não", False)], True, False, "info", "prim_txt"),
        "askokcancel": ("ask", [("OK", True), ("Cancelar", False)], True, False, "info", "prim_txt"),
        "askyesnocancel": ("ask", [("Sim", True), ("Não", False), ("Cancelar", None)], True, None, "info",
                           "prim_txt"),
        "askquestion": ("ask", [("Sim", "yes"), ("Não", "no")], "yes", "no", "info", "prim_txt"),
        "askretrycancel": ("ask", [("Tentar de novo", True), ("Cancelar", False)], True, False, "alerta",
                           "alerta"),
    }
    for nome, (tipo, botoes, padrao, cancelar, ic, cor) in defs.items():
        atual = getattr(messagebox, nome, None)
        if atual is not _MB_ORIGINAIS.get(nome) and not getattr(atual, "_do_tema", False):
            continue                                    # foi substituída por outro código: respeita

        def caixa(title=None, message=None, _t=tipo, _b=botoes, _p=padrao, _c=cancelar, _i=ic, _cor=cor,
                  _n=nome, **kw):
            icone_n, cor_n = _i, _cor
            texto = f"{title or ''} {message or ''}".lower()
            if _n.startswith("ask") and any(p in texto for p in ("excluir", "apagar", "destru", "remover",
                                                                 "sobrescrever", "perder")):
                icone_n, cor_n = "alerta", "perigo"
            return _caixa_mensagem(_t + _n, title, message, _b, _p, _c, icone_n, cor_n, **kw)
        caixa._do_tema = True
        setattr(messagebox, nome, caixa)


def tom_para(texto):
    import hashlib
    return TONS[hashlib.sha256((texto or "?").lower().encode()).digest()[0] % len(TONS)]


# ---------- componentes da tela principal ----------
def _cortar(texto, fonte, largura):
    """Corta o texto com '…' para caber em 'largura' pixels."""
    texto = texto or ""
    if largura <= 0:
        return ""
    if fonte.measure(texto) <= largura:
        return texto
    while texto and fonte.measure(texto + "…") > largura:
        texto = texto[:-1]
    return texto + "…"


class BarraLateral(tk.Frame if tk else object):
    """Lista de grupos à esquerda (ícone, nome e contagem), com seleção destacada.
    Oferece os mesmos métodos do Treeview que o resto do programa usa."""

    def __init__(self, mestre, **kw):
        super().__init__(mestre, bg=CORES["lateral"], **kw)
        self._itens = {}
        self._ordem = []
        self._sel = None
        self._binds = {}

    # compatibilidade com ttk.Treeview
    def get_children(self, item=""):
        return tuple(self._ordem)

    def exists(self, iid):
        return iid in self._itens

    def item(self, iid, option=None):
        d = {"text": self._itens[iid]["compat"], "values": "", "tags": ""}
        return d[option] if option else d

    def selection(self):
        return (self._sel,) if self._sel in self._itens else ()

    def selection_set(self, iid):
        if iid in self._itens:
            self._selecionar(iid)

    def delete(self, *iids):
        for iid in iids:
            it = self._itens.pop(iid, None)
            if it:
                it["linha"].destroy()
                self._ordem.remove(iid)

    def tag_configure(self, *a, **kw):
        pass

    def bind(self, seq=None, func=None, add=None):
        if seq == "<<TreeviewSelect>>":
            self._binds.setdefault(seq, []).append(func)
            return
        return super().bind(seq, func, add)

    # montagem
    def definir(self, entradas, selecionado=None):
        """entradas: lista de dicts com iid, texto, n, e 'icone' (nome) ou 'cor' (bolinha);
        'secao' cria um título antes do item; 'cor_txt' muda a cor do texto."""
        for w in self.winfo_children():
            w.destroy()
        self._itens.clear()
        self._ordem.clear()
        C = CORES
        for e in entradas:
            if e.get("secao"):
                tk.Label(self, text=e["secao"].upper(), bg=C["lateral"], fg=C["fraco"], font="CofreRotulo",
                         anchor="w").pack(fill="x", padx=18, pady=(16, 6))
            linha = tk.Frame(self, bg=C["lateral"], cursor="hand2", height=_px(36))
            linha.pack(fill="x", padx=8, pady=1)
            linha.pack_propagate(False)
            barra = tk.Frame(linha, bg=C["lateral"], width=3)
            barra.pack(side="left", fill="y", pady=8)
            if e.get("cor"):
                ic = _ponto_img(self, e["cor"])
            else:
                ic = imagem_icone(self, e.get("icone", "grupo"), e.get("cor_icone") or C["suave"], 16)
            lic = tk.Label(linha, image=ic, bg=C["lateral"], width=22)
            lic.pack(side="left", padx=(9, 6))
            ltxt = tk.Label(linha, text=e["texto"], bg=C["lateral"], fg=e.get("cor_txt") or C["lateral_txt"],
                            font="CofreTexto", anchor="w")
            ltxt.pack(side="left", fill="x", expand=True)
            ln = tk.Label(linha, text=str(e.get("n", "")), bg=C["lateral"],
                          fg=e.get("cor_n") or C["fraco"], font="CofrePequeno", padx=10)
            ln.pack(side="right")
            item = {"linha": linha, "barra": barra, "partes": (linha, lic, ltxt, ln), "texto": ltxt,
                    "cor_txt": e.get("cor_txt") or C["lateral_txt"], "icone": lic, "ent": e,
                    "compat": f"  {e['texto']}  ({e.get('n', '')})"}
            self._itens[e["iid"]] = item
            self._ordem.append(e["iid"])
            for w in item["partes"]:
                if e.get("acao"):
                    w.bind("<Button-1>", lambda ev, f=e["acao"]: f())
                else:
                    w.bind("<Button-1>", lambda ev, i=e["iid"]: self._selecionar(i))
                if e.get("menu"):
                    w.bind("<Button-3>", lambda ev, f=e["menu"]: f(ev))
                w.bind("<Enter>", lambda ev, i=e["iid"]: self._pintar(i, hover=True))
                w.bind("<Leave>", lambda ev, i=e["iid"]: self._pintar(i))
        self._sel = selecionado if selecionado in self._itens else (self._ordem[0] if self._ordem else None)
        for iid in self._ordem:
            self._pintar(iid)

    def _pintar(self, iid, hover=False):
        it = self._itens.get(iid)
        if not it:
            return
        C = CORES
        sel = iid == self._sel
        fundo = C["lateral_sel"] if sel else ("#13161e" if hover else C["lateral"])
        try:
            for w in it["partes"]:
                w.configure(bg=fundo)
            it["barra"].configure(bg=C["prim"] if sel else fundo)
            it["texto"].configure(fg="#ffffff" if sel else it["cor_txt"],
                                  font="CofreForte" if sel else "CofreTexto")
            e = it["ent"]
            if not e.get("cor"):
                cor = e.get("cor_icone") or (C["prim_txt"] if sel else C["suave"])
                it["icone"].configure(image=imagem_icone(self, e.get("icone", "grupo"), cor, 16))
        except tk.TclError:
            pass

    def _selecionar(self, iid):
        anterior, self._sel = self._sel, iid
        if anterior in self._itens:
            self._pintar(anterior)
        self._pintar(iid)
        for f in self._binds.get("<<TreeviewSelect>>", []):
            f(None)


_PONTOS = {}


def _ponto_img(master, cor, tam=10):
    if (cor, tam) not in _PONTOS:
        _PONTOS[(cor, tam)] = _Tela(tam, tam).circ(tam / 2, tam / 2, tam / 2 - 0.5, cor).imagem(master)
    return _PONTOS[(cor, tam)]


class ListaContas(tk.Frame if tk else object):
    """Lista de contas com avatar e duas linhas (nome e login), desenhada num Canvas.
    Oferece os métodos do ttk.Treeview usados pelo programa (selection, item, ...)."""
    ALT = 60

    def __init__(self, mestre, **kw):
        super().__init__(mestre, bg=CORES["fundo"], **kw)
        C = CORES
        self.ALT = _px(60)
        self.canvas = tk.Canvas(self, bg=C["fundo"], highlightthickness=0, bd=0, takefocus=1)
        self.barra = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._rolagem)
        self.barra.pack(side="right", fill="y", padx=(0, 2))
        self.canvas.pack(side="left", fill="both", expand=True)
        self._linhas = []
        self._idx = {}
        self._sel = None
        self._hover = None
        self._larg = 0
        self._vazio = ("", "")
        self._imgs = {}
        c = self.canvas
        c.bind("<Configure>", lambda e: self._desenhar() if e.width != self._larg else None)
        c.bind("<Button-1>", self._clique)
        c.bind("<Motion>", self._mover)
        c.bind("<Leave>", lambda e: self._pos_hover(None))
        c.bind("<MouseWheel>", lambda e: c.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units"))
        c.bind("<Button-4>", lambda e: c.yview_scroll(-1, "units"))
        c.bind("<Button-5>", lambda e: c.yview_scroll(1, "units"))
        c.bind("<Up>", lambda e: self._andar(-1))
        c.bind("<Down>", lambda e: self._andar(1))
        c.bind("<Home>", lambda e: self._andar(-10 ** 6))
        c.bind("<End>", lambda e: self._andar(10 ** 6))
        c.configure(yscrollincrement=self.ALT // 3)

    def _rolagem(self, a, b):
        """Mostra a barra de rolagem só quando a lista não cabe na tela."""
        self.barra.set(a, b)
        try:
            precisa = float(a) > 0.0 or float(b) < 1.0
            if precisa and not self.barra.winfo_ismapped():
                self.barra.pack(side="right", fill="y", padx=(0, 2), before=self.canvas)
            elif not precisa and self.barra.winfo_ismapped():
                self.barra.pack_forget()
        except (tk.TclError, ValueError):
            pass

    # compatibilidade com ttk.Treeview
    def bind(self, seq=None, func=None, add=None):
        return self.canvas.bind(seq, func, add)

    def focus_set(self):
        self.canvas.focus_set()

    def get_children(self, item=""):
        return tuple(r["iid"] for r in self._linhas)

    def exists(self, iid):
        return iid in self._idx

    def item(self, iid, option=None):
        r = self._linhas[self._idx[iid]]
        d = {"values": [r["titulo"], r["login"], r["contem"]], "text": r["titulo"], "tags": ""}
        return d[option] if option else d

    def selection(self):
        return (self._sel,) if self._sel in self._idx else ()

    def selection_set(self, iid):
        if iid in self._idx:
            self._sel = iid
            self._pos_selecao()
            self.see(iid)
            self.canvas.event_generate("<<TreeviewSelect>>", when="tail")

    def see(self, iid):
        if iid not in self._idx:
            return
        c = self.canvas
        total = max(1, len(self._linhas) * self.ALT + _px(16))
        y0 = self._idx[iid] * self.ALT + _px(8)
        topo, base = c.canvasy(0), c.canvasy(c.winfo_height())
        if y0 < topo:
            c.yview_moveto(y0 / total)
        elif y0 + self.ALT > base:
            c.yview_moveto((y0 + self.ALT - c.winfo_height()) / total)

    def delete(self, *iids):
        self.definir([], self._vazio)

    def tag_configure(self, *a, **kw):
        pass

    # dados e desenho
    def definir(self, linhas, vazio=("", "")):
        """linhas: dicts com iid, titulo, login, sub, contem, cor, alerta (0/1/2), protegido."""
        self._linhas = linhas
        self._idx = {r["iid"]: i for i, r in enumerate(linhas)}
        self._vazio = vazio
        if self._sel not in self._idx:
            self._sel = None
        self._desenhar()

    def _img(self, chave, fabrica):
        if chave not in self._imgs:
            self._imgs[chave] = fabrica()
        return self._imgs[chave]

    def _desenhar(self):
        c = self.canvas
        C = CORES
        c.delete("all")
        w = max(c.winfo_width(), 200)
        self._larg = w
        if not self._linhas:
            titulo, sub = self._vazio
            h = max(c.winfo_height(), 300)
            if titulo:
                c.create_image(w / 2, h * 0.36 - 40, image=self._img(("vazio",), lambda: desenhar_marca(56).imagem(c)))
                c.create_text(w / 2, h * 0.36 + 12, text=titulo, fill=C["texto"], font="CofreSub")
                c.create_text(w / 2, h * 0.36 + 40, text=sub, fill=C["suave"], font="CofreTexto",
                              justify="center", width=min(420, w - 40))
            c.configure(scrollregion=(0, 0, w, h))
            return
        F, P = FONTES["CofreForte"], FONTES["CofrePequeno"]
        q = _px
        larg_hl = w - q(16)
        self._hl_sel = self._img(("sel", larg_hl), lambda: imagem_nove_fatias(
            c, *peca_cartao(C["prim_fundo"], "#34306b", 10), larg_hl, self.ALT - q(6)))
        self._hl_hover = self._img(("hov", larg_hl), lambda: imagem_nove_fatias(
            c, *peca_cartao(C["sup"], None, 10), larg_hl, self.ALT - q(6)))
        c.create_image(-999, -999, image=self._hl_hover, anchor="nw", tags="hover")
        c.create_image(-999, -999, image=self._hl_sel, anchor="nw", tags="sel")
        for i, r in enumerate(self._linhas):
            y = q(8) + i * self.ALT
            meio = y + self.ALT / 2
            av = self._img(("av", r["cor"]), lambda cor=r["cor"]: desenhar_avatar(cor, 38).imagem(c))
            c.create_image(q(36), meio, image=av)
            c.create_text(q(36), meio, text=(r["titulo"].strip()[:1] or "?").upper(), fill="#ffffff",
                          font="CofreForte")
            direita = w - q(18)
            icones = []
            if r.get("alerta"):
                icones.append(("alerta", C["perigo"] if r["alerta"] >= 2 else C["alerta"]))
            if r.get("protegido"):
                icones.append(("cadeado", C["fraco"]))
            for nome, cor in icones:
                c.create_image(direita - q(8), meio, image=imagem_icone(c, nome, cor, 16))
                direita -= q(24)
            larg_txt = direita - q(66) - q(8)
            c.create_text(q(66), meio - q(10), text=_cortar(r["titulo"], F, larg_txt), anchor="w", fill=C["texto"],
                          font="CofreForte", tags=("txt",))
            c.create_text(q(66), meio + q(11), text=_cortar(r["sub"], P, larg_txt), anchor="w", fill=C["suave"],
                          font="CofrePequeno")
        c.tag_lower("hover")
        c.tag_lower("sel")
        c.configure(scrollregion=(0, 0, w, q(16) + len(self._linhas) * self.ALT))
        self._pos_selecao()
        self._pos_hover(self._hover)

    def _pos_selecao(self):
        c = self.canvas
        if self._sel in self._idx:
            c.coords("sel", _px(8), _px(8) + self._idx[self._sel] * self.ALT + _px(3))
        else:
            c.coords("sel", -9999, -9999)

    def _pos_hover(self, i):
        self._hover = i
        c = self.canvas
        if i is not None and 0 <= i < len(self._linhas) and self._linhas[i]["iid"] != self._sel:
            c.coords("hover", _px(8), _px(8) + i * self.ALT + _px(3))
        else:
            c.coords("hover", -9999, -9999)

    def _linha_em(self, y):
        i = int((self.canvas.canvasy(y) - _px(8)) // self.ALT)
        return i if 0 <= i < len(self._linhas) else None

    def _mover(self, e):
        i = self._linha_em(e.y)
        if i != self._hover:
            self._pos_hover(i)

    def _clique(self, e):
        self.canvas.focus_set()
        i = self._linha_em(e.y)
        if i is not None:
            self.selection_set(self._linhas[i]["iid"])
            self._pos_hover(None)

    def _andar(self, passo):
        if not self._linhas:
            return "break"
        i = self._idx.get(self._sel, -1 if passo > 0 else len(self._linhas))
        i = max(0, min(len(self._linhas) - 1, i + passo))
        self.selection_set(self._linhas[i]["iid"])
        return "break"


class PainelForca(ttk.Frame if tk else object):
    """Análise de uma senha em blocos (no estilo do 1Password/Kaspersky): nota com barra,
    composição em etiquetas, tempo para descobrir e recomendações com ícones."""

    def __init__(self, mestre, app, vazio="", largura=380, pref="", compacto=False):
        super().__init__(mestre, style=pref + "TFrame")
        self.app, self.vazio, self.largura, self.pref = app, vazio, largura, pref
        self.compacto = compacto
        self._texto = ""
        self.mostrar("")

    def cget(self, chave):
        if chave == "text":                 # texto puro do relatório (usado por testes e leitores de tela)
            return self._texto
        return super().cget(chave)

    # ---- montagem ----
    def _limpar(self):
        for w in self.winfo_children():
            w.destroy()

    def _cartao(self):
        self.configure(style="Card2.TFrame", padding=(_px(14), _px(11), _px(14), _px(12)))

    def _sumir(self):
        self.configure(style=self.pref + "TFrame", padding=0)

    def _larg(self):
        try:
            w = self.winfo_width()
        except tk.TclError:
            w = 0
        return w if w > _px(120) else self.largura

    def _linha(self, pai, icone_nome, cor, texto, estilo="S2.Suave.TLabel"):
        lin = ttk.Frame(pai, style="S2.TFrame")
        lin.pack(fill="x", pady=(_px(3), 0))
        ttk.Label(lin, image=imagem_icone(self, icone_nome, cor, 14), style="S2.TLabel").pack(
            side="left", anchor="n", pady=(_px(2), 0), padx=(0, _px(8)))
        ttk.Label(lin, text=texto, style=estilo, wraplength=self._larg() - _px(64), justify="left").pack(
            side="left", fill="x")
        return lin

    def _secao(self, texto):
        ttk.Label(self, text=texto.upper(), style="S2.Campo.TLabel").pack(anchor="w", pady=(_px(12), _px(2)))

    def _cabecalho(self, nota, rot, direita, titulo=""):
        cor = self.app._CORES_FORCA[nota]
        topo = ttk.Frame(self, style="S2.TFrame")
        topo.pack(fill="x")
        if titulo:
            ttk.Label(topo, text=titulo, style="S2.Fraco.TLabel").pack(side="left", padx=(0, _px(10)))
        ttk.Label(topo, text="  " + rot, image=self.app._barra_forca(nota), compound="left", style="S2.TLabel",
                  foreground=cor, font="CofreForte").pack(side="left")
        ttk.Label(topo, text=direita, style="S2.Fraco.TLabel").pack(side="right")

    def _etiquetas(self, senha):
        cp = composicao(senha)
        itens = ((cp["maiusculas"], "maiúscula", "maiúsculas"),
                 (cp["minusculas"], "minúscula", "minúsculas"), (cp["numeros"], "número", "números"),
                 (cp["simbolos"], "símbolo", "símbolos"))
        fonte = FONTES.get("CofrePequeno")
        caixa = ttk.Frame(self, style="S2.TFrame")
        caixa.pack(fill="x", pady=(_px(10), 0))
        lin, usado = None, 0
        for n, um, varios in itens:
            texto = f"{n} {um if n == 1 else varios}"
            larg = (fonte.measure(texto) if fonte else 7 * len(texto)) + _px(16) + _px(6)
            if lin is None or usado + larg > self._larg() - _px(30):
                lin = ttk.Frame(caixa, style="S2.TFrame")
                lin.pack(fill="x", pady=(0, _px(5)))
                usado = 0
            ttk.Label(lin, text=texto, style="Etiqueta.TLabel" if n else "EtiquetaFraca.TLabel").pack(
                side="left", padx=(0, _px(6)))
            usado += larg

    def _tempos(self, bits):
        g = ttk.Frame(self, style="S2.TFrame")
        if self.compacto:
            g.pack(fill="x", pady=(_px(8), 0))
        else:
            self._secao("Tempo para descobrir por tentativa e erro")
            g.pack(fill="x")
        g.columnconfigure(0, weight=1)
        for i, (rotulo, vel) in enumerate((("Se roubarem o arquivo do cofre", VELOCIDADE_COFRE),
                                           ("Se vazar de um site com proteção fraca", VELOCIDADE_SITE))):
            texto = tempo_quebra(bits, vel).replace("muito mais que a idade do universo (13,8 bilhões de anos)",
                                                    "mais que a idade do universo")
            log_seg = (bits - 1) * math.log10(2) - math.log10(vel)
            cor = (CORES["perigo"] if log_seg < math.log10(86400 * 30) else
                   CORES["alerta"] if log_seg < math.log10(86400 * 365 * 100) else CORES["ok"])
            ttk.Label(g, text=rotulo, style="S2.Suave.TLabel").grid(row=i, column=0, sticky="w", pady=(_px(2), 0))
            ttk.Label(g, text=texto, style="S2.TLabel", foreground=cor, font="CofreForte", justify="right",
                      wraplength=int(self._larg() * 0.42)).grid(row=i, column=1, sticky="e", padx=(_px(12), 0),
                                                                pady=(_px(2), 0))

    # ---- uso ----
    def mostrar(self, senha, pin=False, titulo=""):
        """Analisa uma senha digitada (estimativa realista, com penalidades)."""
        self._limpar()
        C = CORES
        if not senha:
            self._texto = ""
            if self.vazio:
                self._cartao()
                self._linha(self, "info", C["fraco"], self.vazio, "S2.Fraco.TLabel").pack_configure(pady=0)
            else:
                self._sumir()
            return
        if pin:
            if not (pin_obvio(senha) or len(senha) < 4):
                self._texto = ""
                self._sumir()
                return
            self._texto = "PIN fácil de adivinhar. Evite 1234, 0000, repetições e anos."
            self._cartao()
            self._linha(self, "alerta", C["perigo"], "PIN fácil de adivinhar: evite 1234, 0000, repetições e anos. "
                        "Use o botão de gerar para um PIN aleatório.", "S2.TLabel").pack_configure(pady=0)
            return
        nota, rot, bits, dicas = avaliar_forca(senha)
        self._texto = relatorio_forca(senha)[2]
        self._cartao()
        n = len(senha)
        self._cabecalho(nota, rot, f"{n} caractere{'s' if n != 1 else ''}   •   ~{bits} bits", titulo)
        if not self.compacto:
            self._etiquetas(senha)
        self._tempos(bits)
        if dicas:
            if self.compacto:
                ttk.Frame(self, style="S2.TFrame", height=_px(6)).pack()
            else:
                self._secao("Recomendações" if nota <= 3 else "Avaliação")
            for d in dicas[:2 if self.compacto else 4]:
                if nota >= 3:
                    self._linha(self, "ok", C["ok"], d)
                else:
                    self._linha(self, "alerta", self.app._CORES_FORCA[nota] if nota <= 1 else C["alerta"], d)

    def mostrar_gerada(self, senha, bits, nota, veredito, uso):
        """Senha criada pelo gerador: a força é exata (vem do sorteio), não estimada."""
        self._limpar()
        self._texto = (f"{texto_composicao(senha)}\n{uso}")
        self._cartao()
        n = len(senha)
        topo = ttk.Frame(self, style="S2.TFrame")
        topo.pack(fill="x")
        ttk.Label(topo, text="Composição", style="S2.Fraco.TLabel").pack(side="left")
        ttk.Label(topo, text=f"{n} caracteres   •   ~{int(bits)} bits (exatos, do sorteio)",
                  style="S2.Fraco.TLabel").pack(side="right")
        self._etiquetas(senha)
        self._tempos(bits)
        self._secao("Indicada para")
        self._linha(self, "ok", CORES["ok"], uso)


class MenuTema:
    """Menu suspenso no tema escuro (o menu padrão do Windows seria claro)."""

    def __init__(self, app, itens):
        self.app = app
        self.itens = itens          # (rótulo, ícone, função) ou None para separador

    def abrir(self, widget, pos=None):
        C = CORES
        raiz = widget.winfo_toplevel()
        m = tk.Toplevel(raiz)
        m.wm_overrideredirect(True)
        m.configure(bg=C["borda2"])
        caixa = tk.Frame(m, bg=C["sup2"], padx=6, pady=6)
        caixa.pack(padx=1, pady=1)

        def fechar(e=None):
            try:
                m.grab_release()
                m.destroy()
            except tk.TclError:
                pass

        for it in self.itens:
            if it is None:
                tk.Frame(caixa, bg=C["borda2"], height=1).pack(fill="x", padx=6, pady=5)
                continue
            rot, ic, func = it
            linha = tk.Frame(caixa, bg=C["sup2"], cursor="hand2")
            linha.pack(fill="x")
            li = tk.Label(linha, image=imagem_icone(m, ic, C["suave"], 16), bg=C["sup2"], width=28)
            li.pack(side="left", padx=(4, 4), pady=6)
            lt = tk.Label(linha, text=rot, bg=C["sup2"], fg=C["texto"], font="CofreTexto", anchor="w", padx=4)
            lt.pack(side="left", fill="x", expand=True, padx=(0, 18))

            def pintar(cor, partes=(linha, li, lt)):
                for p in partes:
                    p.configure(bg=cor)

            def executar(e=None, f=func):
                fechar()
                self.app.root.after(10, f)
            for p in (linha, li, lt):
                p.bind("<Enter>", lambda e, pt=pintar: pt(C["sup4"]))
                p.bind("<Leave>", lambda e, pt=pintar: pt(C["sup2"]))
                p.bind("<ButtonRelease-1>", executar)
        m.update_idletasks()
        if pos:
            x, y = pos
        else:
            x = widget.winfo_rootx() + widget.winfo_width() - m.winfo_reqwidth()
            y = widget.winfo_rooty() + widget.winfo_height() + 4
        m.geometry(f"+{max(0, x)}+{y}")
        proteger_contra_captura(m)
        m.bind("<Escape>", fechar)
        m.bind("<FocusOut>", lambda e: m.after(50, fechar))

        def clique_fora(e):
            x0, y0 = m.winfo_rootx(), m.winfo_rooty()
            if not (x0 <= e.x_root < x0 + m.winfo_width() and y0 <= e.y_root < y0 + m.winfo_height()):
                fechar()
        m.bind("<Button-1>", clique_fora, add="+")
        try:
            m.grab_set()
        except tk.TclError:
            pass
        m.focus_set()
        return m


class App:
    INATIVIDADE_MS = 3 * 60 * 1000       # bloqueia após 3 min sem uso
    LIMPAR_CLIPBOARD_MS = 30 * 1000      # limpa a área de transferência após 30 s

    def __init__(self, root, caminho):
        self.root = root
        self.caminho = caminho
        self.cofre = None
        self.frame = None
        self._timer_bloqueio = None
        self._timer_clip = None
        self._clip_valor = None
        root.title("Cofre de Senhas")
        aplicar_tema(root)
        instalar_caixas_de_mensagem()
        try:
            self._icone_janela = [desenhar_marca(n).imagem(root) for n in (64, 32, 16)]
            root.iconphoto(True, *self._icone_janela)
        except tk.TclError:
            pass
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        larg, alt = min(_px(1200), int(sw * 0.94)), min(_px(780), int(sh * 0.9))
        root.geometry(f"{larg}x{alt}+{max(0, (sw - larg) // 2)}+{max(0, (sh - alt) // 3)}")
        root.minsize(min(_px(1040), larg), min(_px(660), alt))
        for ev in ("<KeyPress>", "<Button>", "<MouseWheel>"):
            root.bind_all(ev, self._atividade, add="+")
        root.bind("<Unmap>", self._ao_minimizar, add="+")
        self._ultimo_tique = time.time()
        self._tique_proc = 0
        self._ocultadores = []
        self._liberado_em = {}
        self._erros_sessao = 0
        root.bind_all("<FocusOut>", lambda e: self.root.after(250, self._talvez_ocultar), add="+")
        root.bind_all("<FocusIn>", lambda e: self._mostrar_conteudo(), add="+")
        root.after(2000, self._vigiar_sistema)
        root.protocol("WM_DELETE_WINDOW", self.sair)
        root.update()
        self.protegido = proteger_contra_captura(root)
        barra_titulo_escura(root)
        root.bind("<Map>", lambda e: proteger_contra_captura(root) if e.widget is root else None, add="+")
        self.mostrar_inicio()

    # ---------- utilidades ----------
    def _limpar_tela(self, modo="cheio"):
        """'cheio' = tela inteira; 'centro'/'topo' = cartão centralizado sobre fundo com halo suave."""
        self._mostrar_conteudo()
        if self.frame:
            self.frame.destroy()
        C = CORES
        if modo == "cheio":
            self.frame = ttk.Frame(self.root, style="Pagina.TFrame")
            self.frame.pack(fill="both", expand=True)
            return self.frame
        tela = tk.Canvas(self.root, bg=C["fundo"], highlightthickness=0, bd=0)
        tela.pack(fill="both", expand=True)
        self.frame = tela
        conteudo = ttk.Frame(tela, style="C.TFrame")
        janela = tela.create_window(0, 0, window=conteudo, anchor="center")
        tela.create_text(0, 0, text="Seus dados ficam criptografados neste computador  •  nada vai para a internet",
                         fill=C["fraco"], font="CofrePequeno", tags="rodape")
        PAD = _px(36)
        estado = {"wh": None, "desl": 0.0}

        def redesenhar(event=None):
            try:
                w, h = tela.winfo_width(), tela.winfo_height()
                if w < 50:
                    return
                cw = conteudo.winfo_reqwidth() + 2 * PAD
                ch = conteudo.winfo_reqheight() + 2 * PAD
                cy = max(ch / 2 + 18, (h - 44) / 2)
                excesso = ch + 18 + 44 - h
                if excesso > 0:                 # conteúdo maior que a janela: rola com a roda do mouse
                    estado["desl"] = max(-excesso, min(0.0, estado["desl"]))
                    cy += estado["desl"]
                else:
                    estado["desl"] = 0.0
                tela.delete("brilho")
                brilho_radial(tela, w / 2, cy - ch * 0.42, max(w, h) * 0.85, "#1e1b4b", C["fundo"])
                if estado["wh"] != (cw, ch):
                    estado["wh"] = (cw, ch)
                    tela._placa = imagem_nove_fatias(tela, *peca_cartao(C["sup"], C["borda"], 18), cw, ch)
                    tela._sombra = imagem_nove_fatias(tela, *peca_sombra(18, 26, 0.7), cw + 2 * _px(26),
                                                      ch + 2 * _px(26))
                    tela.delete("cartao")
                    tela.create_image(0, 0, image=tela._sombra, tags=("cartao", "sombra"))
                    tela.create_image(0, 0, image=tela._placa, tags=("cartao", "placa"))
                tela.coords("sombra", w / 2, cy + 6)
                tela.coords("placa", w / 2, cy)
                tela.coords(janela, w / 2, cy)
                tela.coords("rodape", w / 2, max(h - 22, cy + ch / 2 + 22))
                tela.tag_lower("cartao")
                tela.tag_lower("brilho")
            except tk.TclError:
                pass

        def rolar(event):
            if self.frame is not tela:
                return
            passo = -1 if getattr(event, "num", 0) == 4 else 1 if getattr(event, "num", 0) == 5 else \
                (-1 if event.delta > 0 else 1)
            estado["desl"] -= passo * _px(48)
            redesenhar()

        tela.bind("<Configure>", redesenhar, add="+")
        conteudo.bind("<Configure>", lambda e: redesenhar(), add="+")
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.bind(ev, rolar)
        return conteudo

    def _texto_protecao(self):
        """(texto, cor) do resumo das proteções ativas."""
        partes, faltam = [], []
        (partes if self.protegido else faltam).append("captura de tela bloqueada" if self.protegido
                                                      else "bloqueio de captura de tela")
        if EH_WINDOWS:
            if "memoria" in BLINDAGEM:
                partes.append("memória trancada")
            else:
                faltam.append("trava de memória")
            if "ganchos" in BLINDAGEM:
                partes.append("anti-injeção")
        if faltam:
            return ("Indisponível neste Windows: " + ", ".join(faltam) +
                    (".  Ativas: " + ", ".join(partes) if partes else "."), CORES["alerta"])
        return "Proteções ativas: " + "  •  ".join(partes), CORES["ok"]

    def _linha_icone(self, pai, nome, cor, texto, pref="C.", largura=400, cor_texto=None):
        """Ícone + texto com recuo (as linhas seguintes alinham com o texto, não com o ícone)."""
        lin = ttk.Frame(pai, style=pref + "TFrame")
        ttk.Label(lin, image=imagem_icone(self.root, nome, cor, 14), style=pref + "TLabel").pack(
            side="left", anchor="n", pady=(_px(2), 0), padx=(0, _px(8)))
        ttk.Label(lin, text=texto, style=pref + "Fraco.TLabel", foreground=cor_texto or CORES["fraco"],
                  wraplength=largura, justify="left").pack(side="left", fill="x")
        return lin

    def _rotulo_protecao(self, f, pref="C."):
        if self._no_disco_do_windows(self.caminho):
            self._linha_icone(f, "alerta", CORES["alerta"],
                              f"Este cofre está no disco do Windows ({self._unidade(self.caminho)}). O recomendado "
                              "é deixar o programa e o cofre no pendrive.", pref, _px(400),
                              CORES["alerta"]).pack(anchor="w", fill="x", pady=(0, 6))
        txt, cor = self._texto_protecao()
        ic = "escudo" if cor == CORES["ok"] else "alerta"
        self._linha_icone(f, ic, cor, txt, pref, _px(400), cor).pack(anchor="w", fill="x", pady=(0, 6))

    def _dica(self, widget, texto):
        """Balão de ajuda ao parar o mouse sobre 'widget'."""
        estado = {"j": None, "t": None}

        def mostrar():
            if estado["j"] is not None:
                return
            try:
                j = tk.Toplevel(widget)
                j.wm_overrideredirect(True)
                j.configure(bg=CORES["borda2"])
                tk.Label(j, text=texto, bg=CORES["sup3"], fg=CORES["texto"], font="CofrePequeno",
                         padx=10, pady=5, justify="left", wraplength=300).pack(padx=1, pady=1)
                j.update_idletasks()
                x = widget.winfo_rootx() + widget.winfo_width() // 2 - j.winfo_reqwidth() // 2
                y = widget.winfo_rooty() + widget.winfo_height() + 6
                j.geometry(f"+{max(0, x)}+{y}")
                proteger_contra_captura(j)
                estado["j"] = j
            except tk.TclError:
                pass

        def entrar(e):
            estado["t"] = widget.after(450, mostrar)

        def sair(e=None):
            if estado["t"]:
                widget.after_cancel(estado["t"])
                estado["t"] = None
            if estado["j"] is not None:
                try:
                    estado["j"].destroy()
                except tk.TclError:
                    pass
                estado["j"] = None
        widget.bind("<Enter>", entrar, add="+")
        widget.bind("<Leave>", sair, add="+")
        widget.bind("<ButtonPress>", sair, add="+")
        widget.bind("<Destroy>", sair, add="+")

    def _campo_secreto(self, mestre, largura=40, pref="", **kw):
        e = ttk.Entry(mestre, show="•", width=largura, exportselection=False, style=pref + "TEntry", **kw)
        self._bloquear_copia(e)
        return e

    def _linha_secreta(self, mestre, largura=40, pref="", olho=True):
        """Campo secreto + botão de mostrar/ocultar (olho) + botão do teclado virtual, num frame."""
        fr = ttk.Frame(mestre, style=pref + "TFrame")
        e = self._campo_secreto(fr, largura, pref)
        e.pack(side="left", fill="x", expand=True)
        if olho:
            self._botao_olho(fr, e, pref).pack(side="left", fill="y", padx=(6, 0))
        b = ttk.Button(fr, text="⌨", image=imagem_icone(self.root, "teclado", CORES["suave"], 18), compound="image",
                       style=pref + "Quadrado.TButton", takefocus=0, command=lambda: self.teclado_virtual(e))
        b.pack(side="left", fill="y", padx=(6, 0))
        self._dica(b, "Teclado virtual: digite clicando com o mouse.\nAs teclas mudam de lugar — "
                      "programas espiões de teclado não capturam.")
        return fr, e

    MOSTRAR_SENHA_MS = 30000

    def _botao_olho(self, pai, e, pref=""):
        """Olho que mostra o que está sendo digitado. Volta a esconder sozinho depois de 30 s
        (e o campo continua sem permitir copiar)."""
        estado = {"timer": None}
        b = ttk.Button(pai, text="👁", image=imagem_icone(self.root, "ver", CORES["suave"], 18), compound="image",
                       style=pref + "Quadrado.TButton", takefocus=0)

        def esconder():
            estado["timer"] = None
            try:
                e.config(show="•")
                b.config(image=imagem_icone(self.root, "ver", CORES["suave"], 18))
            except tk.TclError:
                pass

        def alternar():
            try:
                if e.cget("show"):
                    e.config(show="")
                    b.config(image=imagem_icone(self.root, "ocultar", CORES["prim_txt"], 18))
                    if estado["timer"]:
                        b.after_cancel(estado["timer"])
                    estado["timer"] = b.after(self.MOSTRAR_SENHA_MS, esconder)
                else:
                    if estado["timer"]:
                        b.after_cancel(estado["timer"])
                    esconder()
                e.focus_set()
                e.icursor("end")
            except tk.TclError:
                pass

        b.config(command=alternar)
        self._dica(b, "Mostrar ou ocultar o que você digitou.\nVolta a esconder sozinho em 30 segundos.")
        return b

    def _rotulo_campo(self, pai, texto, pref="C."):
        return ttk.Label(pai, text=texto.upper(), style=pref + "Campo.TLabel")

    def _barra_forca(self, nota, larg=72):
        """Imagem com 4 segmentos coloridos conforme a força (0 a 4)."""
        chave = ("forca", nota, larg)
        cache = self.__dict__.setdefault("_cache_barras", {})
        if chave not in cache:
            seg = (larg - 9) / 4
            t = _Tela(larg, 6)
            cor = self._CORES_FORCA[max(0, min(nota, 4))]
            acesos = 0 if nota < 0 else (nota if nota >= 1 else 1)
            for i in range(4):
                x0 = i * (seg + 3)
                t.ret(x0, 0, x0 + seg, 6, 3, cor if i < acesos else CORES["borda2"])
            cache[chave] = t.imagem(self.root)
        return cache[chave]

    def _medidor(self, mestre, entrada, pin=False, dicas_lbl=None, pref="", titulo=""):
        """Barra de força + rótulo, atualizados enquanto se digita em 'entrada'.
        Se 'dicas_lbl' for informado, ele recebe as recomendações do que melhorar."""
        lbl = ttk.Label(mestre, text="", width=26, compound="left", style=pref + "TLabel")

        painel = dicas_lbl if isinstance(dicas_lbl, PainelForca) else None

        def dicas(texto, cor=None):
            if dicas_lbl is not None and painel is None:
                try:
                    dicas_lbl.config(text=texto, foreground=cor or CORES["suave"])
                except tk.TclError:
                    pass

        def atualizar(event=None, inicial=False):
            try:
                v = entrada.get()
            except tk.TclError:
                return
            if painel is not None and not (inicial and (not v or painel.cget("text"))):
                try:
                    painel.mostrar(v, pin=pin, titulo=titulo)
                except tk.TclError:
                    pass
            if not v:
                lbl.config(text="", image="")
                dicas("")
                return
            if pin:
                ruim = pin_obvio(v) or len(v) < 4
                lbl.config(text="  " + ("PIN fácil de adivinhar" if ruim else "PIN ok"),
                           image=self._barra_forca(0 if ruim else 3), foreground=self._CORES_FORCA[0 if ruim else 3])
                dicas("• Evite 1234, 0000, repetições e anos. Use Gerar… para um PIN aleatório." if ruim
                      else "", self._CORES_FORCA[0])
                return
            nota, rot, texto = relatorio_forca(v)
            lbl.config(text="  " + rot, image=self._barra_forca(nota), foreground=self._CORES_FORCA[nota])
            dicas(texto, self._CORES_FORCA[nota] if nota <= 1 else CORES["suave"])

        entrada.bind("<KeyRelease>", atualizar, add="+")
        entrada.bind("<<Atualizar>>", atualizar, add="+")
        atualizar(inicial=True)
        return lbl

    def tela_criar(self):
        C = CORES
        f = self._limpar_tela("topo")
        topo = ttk.Frame(f, style="C.TFrame")
        topo.pack(fill="x")
        self._img_marca = desenhar_marca(52).imagem(self.root)
        ttk.Label(topo, image=self._img_marca, style="C.TLabel").pack(side="left", padx=(0, 16))
        tt = ttk.Frame(topo, style="C.TFrame")
        tt.pack(side="left", fill="x")
        ttk.Label(tt, text="Criar seu cofre", style="C.Titulo.TLabel").pack(anchor="w")
        ttk.Label(tt, text="A senha mestra protege tudo. Ela nunca sai deste computador e não pode ser recuperada.",
                  style="C.Suave.TLabel").pack(anchor="w")
        ttk.Label(tt, text=os.path.basename(self.caminho) + "   •   " + os.path.dirname(os.path.abspath(self.caminho)),
                  style="C.Fraco.TLabel").pack(anchor="w", pady=(2, 0))
        ttk.Separator(f).pack(fill="x", pady=(18, 16))

        colunas = ttk.Frame(f, style="C.TFrame")
        colunas.pack(fill="x")
        esq = ttk.Frame(colunas, style="C.TFrame", width=380)
        esq.pack(side="left", fill="y", anchor="n")
        ttk.Frame(colunas, style="C.TFrame", width=34).pack(side="left")
        tk.Frame(colunas, bg=C["borda"], width=1).pack(side="left", fill="y")
        ttk.Frame(colunas, style="C.TFrame", width=30).pack(side="left")
        dir_ = ttk.Frame(colunas, style="C.TFrame")
        dir_.pack(side="left", fill="both", expand=True, anchor="n")

        # Coluna da senha
        self._rotulo_campo(esq, f"Senha mestra  (mínimo {MIN_SENHA} caracteres)").pack(anchor="w")
        l1fr = ttk.Frame(esq, style="C.TFrame")
        l1fr.pack(fill="x", pady=(4, 0))
        l1, s1 = self._linha_secreta(l1fr, 30, "C.")
        l1.pack(side="left", fill="x", expand=True)
        bg = ttk.Button(l1fr, text="Gerar…", image=imagem_icone(self.root, "gerar", C["texto"]), compound="left",
                        style="C.Fino.TButton",
                        command=lambda: self.dialogo_gerador(s1, "frase", senha_mestra=True, extra=s2))
        bg.pack(side="left", padx=(6, 0))
        self._dica(bg, "Gera uma senha forte: escolha o tipo e o TAMANHO.\nRecomendado: frase fácil de lembrar "
                       "com 5 ou 6 palavras.")
        self._dicas_mestra = PainelForca(esq, self, largura=_px(400), pref="C.",
                                         vazio="Digite ou gere uma senha para ver a análise: força, composição, "
                                               "tempo para descobrir e recomendações.")
        self._medidor(esq, s1, dicas_lbl=self._dicas_mestra, pref="C.").pack(anchor="w", pady=(8, 0))
        self._rotulo_campo(esq, "Confirmar senha").pack(anchor="w", pady=(14, 0))
        l2, s2 = self._linha_secreta(esq, 30, "C.")
        l2.pack(fill="x", pady=(4, 0))
        confere = ttk.Label(esq, text="", style="C.TLabel")
        confere.pack(anchor="w", pady=(6, 0))
        self._dicas_mestra.pack(fill="x", pady=(10, 0))

        # Coluna das opções
        modo = tk.IntVar(value=MODO_E)
        self._rotulo_campo(dir_, "Como o cofre abre").pack(anchor="w")
        for valor, titulo, desc in (
                (MODO_E, "Senha E chave de acesso  (recomendado)",
                 "Dois fatores: quem roubar a senha ainda precisa da chave."),
                (MODO_OU, "Senha OU chave de acesso", "A chave serve como recuperação se esquecer a senha.")):
            ttk.Radiobutton(dir_, text=titulo, value=valor, variable=modo, style="C.TRadiobutton").pack(
                anchor="w", pady=(6, 0))
            ttk.Label(dir_, text=desc, style="C.Fraco.TLabel", wraplength=330).pack(anchor="w", padx=(28, 0))

        nivel = tk.StringVar(value="maximo")
        self._rotulo_campo(dir_, "Blindagem da senha").pack(anchor="w", pady=(16, 0))
        for valor, titulo, desc in (
                ("maximo", "Máxima — 1 GB por tentativa", "Abre em 3 a 8 segundos. Torna ataques inviáveis."),
                ("alto", "Alta — 256 MB por tentativa", "Para computadores com pouca memória.")):
            ttk.Radiobutton(dir_, text=titulo, value=valor, variable=nivel, style="C.TRadiobutton").pack(
                anchor="w", pady=(6, 0))
            ttk.Label(dir_, text=desc, style="C.Fraco.TLabel", wraplength=330).pack(anchor="w", padx=(28, 0))

        self._rotulo_campo(dir_, "Autodestruição").pack(anchor="w", pady=(16, 0))
        lt = ttk.Frame(dir_, style="C.TFrame")
        lt.pack(anchor="w", pady=(6, 0))
        ttk.Label(lt, text="Apagar o cofre após", style="C.TLabel").pack(side="left")
        tent = ttk.Spinbox(lt, from_=1, to=10, width=4, style="C.TSpinbox")
        tent.delete(0, "end")
        tent.insert(0, "3")
        tent.pack(side="left", padx=8)
        ttk.Label(lt, text="tentativas erradas", style="C.TLabel").pack(side="left")

        def criar(event=None):
            a, b = s1.get(), s2.get()
            problema = avaliar_senha(a)
            if problema:
                messagebox.showerror("Senha fraca", problema)
                return
            if a != b:
                messagebox.showerror("Erro", "As senhas não conferem.")
                return
            try:
                n = int(tent.get())
                if not 1 <= n <= 10:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Erro", "Tentativas deve ser um número de 1 a 10.")
                return
            if n == 1 and not messagebox.askyesno(
                    "Confirmar", "Com 1 tentativa, UM erro de digitação apaga o cofre para sempre.\n"
                                 "Tenha um backup atualizado. Continuar?"):
                return
            if modo.get() == MODO_E and not messagebox.askyesno(
                    "Modo dois fatores", "Neste modo o cofre só abre com a senha E a chave de acesso "
                    "juntas.\nPerder qualquer uma das duas = perder o cofre para sempre.\n\nContinuar?"):
                return
            self._ocupado(True)
            try:
                self.cofre = Cofre.criar(self.caminho, a, n, modo.get(), nivel.get())
            except MemoryError:
                self._ocupado(False)
                messagebox.showerror("Memória insuficiente", "Este computador não tem memória livre "
                                     "para a blindagem Máxima. Escolha a blindagem Alta.")
                return
            except OSError as ex:
                self._ocupado(False)
                messagebox.showerror("Erro", f"Não foi possível criar o arquivo:\n{ex}")
                return
            self._ocupado(False)
            chave, self.cofre.chave_gerada = self.cofre.chave_gerada, None
            self.mostrar_chave_acesso(chave, self.cofre.modo)
            self.tela_principal()
            if messagebox.askyesno("Chave FIDO (opcional)",
                                   "Cofre criado!\n\nVocê tem uma chave de segurança FIDO2 (ex.: Yubico Security Key NFC, YubiKey 5) "
                                   "para cadastrar agora como proteção extra?\n\n"
                                   "Se ainda não tem, responda 'Não'. Você pode cadastrar depois pelo botão "
                                   "'Chave FIDO' na parte de cima da tela."):
                self.gerenciar_fido()

        def conferir(event=None):
            a, b = s1.get(), s2.get()
            if not b:
                confere.config(text="", image="")
            elif a == b:
                confere.config(text="  As senhas conferem", image=imagem_icone(self.root, "ok", C["ok"], 14),
                               compound="left", foreground=C["ok"])
            else:
                confere.config(text="  Ainda não conferem", image=imagem_icone(self.root, "fechar", C["perigo"], 14),
                               compound="left", foreground=C["perigo"])

        for e in (s1, s2):
            e.bind("<KeyRelease>", conferir, add="+")
            e.bind("<<Atualizar>>", conferir, add="+")
        s2.bind("<Return>", criar)

        ttk.Separator(f).pack(fill="x", pady=(18, 14))
        rod = ttk.Frame(f, style="C.TFrame")
        rod.pack(fill="x")
        prot = ttk.Frame(rod, style="C.TFrame")
        prot.pack(side="left", fill="x", expand=True)
        self._rotulo_protecao(prot)
        ttk.Label(prot, text="Uma chave de acesso será gerada no próximo passo — guarde-a longe do cofre.",
                  style="C.Fraco.TLabel").pack(anchor="w")
        ttk.Button(rod, text="Criar cofre", style="C.Primario.TButton", command=criar,
                   image=imagem_icone(self.root, "seta", "#ffffff"), compound="right").pack(side="right")
        s1.focus_set()

    def tela_desbloqueio(self):
        C = CORES
        f = self._limpar_tela("centro")
        self._img_marca = desenhar_marca(64).imagem(self.root)
        ttk.Label(f, image=self._img_marca, style="C.TLabel").pack()
        ttk.Label(f, text="Cofre de Senhas", style="C.Titulo.TLabel").pack(pady=(12, 0))
        modo_cofre, exige_fido = MODO_OU, False
        try:
            rest, modo_cofre, exige_fido = info_cofre(self.caminho)
            info = f"{rest} tentativa{'s' if rest != 1 else ''} antes da autodestruição"
        except (ArquivoInvalido, OSError) as ex:
            info = str(ex)
        dois_fatores = modo_cofre == MODO_E
        ttk.Label(f, text="Digite a senha mestra e a chave de acesso" if dois_fatores
                  else "Desbloqueie para ver suas senhas", style="C.Suave.TLabel").pack()
        ttk.Label(f, text=os.path.basename(self.caminho), style="C.Fraco.TLabel").pack(pady=(2, 18))

        modo = tk.StringVar(value="senha")
        form = ttk.Frame(f, style="C.TFrame", width=400)
        form.pack(fill="x")
        if not dois_fatores:
            seg = ttk.Frame(form, style="C.TFrame")
            seg.pack(fill="x", pady=(0, 14))
        bloco_senha = ttk.Frame(form, style="C.TFrame")
        self._rotulo_campo(bloco_senha, "Senha mestra").pack(anchor="w")
        cx1, e_senha = self._linha_secreta(bloco_senha, 36, "C.")
        cx1.pack(fill="x", pady=(4, 0))
        bloco_chave = ttk.Frame(form, style="C.TFrame")
        lc = ttk.Frame(bloco_chave, style="C.TFrame")
        lc.pack(fill="x")
        self._rotulo_campo(lc, "Chave de acesso").pack(side="left", anchor="w")
        bt_arq = ttk.Button(lc, text="Carregar .key…", style="C.Fantasma.TButton",
                            image=imagem_icone(self.root, "importar", C["suave"], 14), compound="left")
        bt_arq.pack(side="right")
        cx2, e_chave = self._linha_secreta(bloco_chave, 36, "C.")
        cx2.pack(fill="x", pady=(2, 0))

        def mostrar_campos():
            bloco_senha.pack_forget()
            bloco_chave.pack_forget()
            if dois_fatores or modo.get() == "senha":
                bloco_senha.pack(fill="x")
            if dois_fatores or modo.get() == "chave":
                bloco_chave.pack(fill="x", pady=(12 if dois_fatores else 0, 0))

        def trocar_modo():
            e_senha.delete(0, "end")
            e_chave.delete(0, "end")
            mostrar_campos()
            (e_senha if modo.get() == "senha" else e_chave).focus_set()

        if not dois_fatores:
            for valor, texto in (("senha", "Senha mestra"), ("chave", "Chave de acesso")):
                ttk.Radiobutton(seg, text=texto, value=valor, variable=modo, command=trocar_modo,
                                style="C.Segmento.Toolbutton").pack(side="left", fill="x", expand=True)

        def carregar_arquivo():
            arq = filedialog.askopenfilename(title="Selecionar arquivo de chave",
                                             filetypes=[("Chave do cofre", "*.key"), ("Todos", "*.*")])
            if not arq:
                return
            try:
                with open(arq, "r", encoding="utf-8", errors="ignore") as fh:
                    conteudo = fh.read(200).strip()
            except OSError as ex:
                messagebox.showerror("Erro", f"Não foi possível ler o arquivo:\n{ex}")
                return
            e_chave.delete(0, "end")
            e_chave.insert(0, conteudo)
            lbl.config(text="Arquivo de chave carregado." + (" Agora digite a senha e clique em Desbloquear."
                                                             if dois_fatores else " Clique em Desbloquear."),
                       foreground=C["ok"])

        bt_arq.config(command=carregar_arquivo)
        mostrar_campos()

        usar_rec = tk.BooleanVar(value=False)
        e_rec = None
        if exige_fido:
            ff = ttk.Frame(f, style="C.TFrame")
            ff.pack(fill="x", pady=(14, 0))
            ttk.Label(ff, text="  Este cofre também exige a CHAVE FIDO. Depois de clicar em Desbloquear, toque "
                               "na chave quando ela piscar.",
                      image=imagem_icone(self.root, "chave", C["prim_txt"], 16), compound="left",
                      style="C.TLabel", wraplength=380, justify="left").pack(anchor="w")
            lrec = ttk.Frame(ff, style="C.TFrame")
            self._rotulo_campo(lrec, "Código de recuperação").pack(anchor="w")
            cx3, e_rec = self._linha_secreta(lrec, 36, "C.")
            cx3.pack(fill="x", pady=(4, 0))

            def alternar_rec():
                if usar_rec.get():
                    lrec.pack(fill="x", pady=(8, 0))
                    e_rec.focus_set()
                else:
                    e_rec.delete(0, "end")
                    lrec.pack_forget()

            ttk.Checkbutton(ff, text="Estou sem a chave FIDO — usar o código de recuperação",
                            variable=usar_rec, command=alternar_rec, style="C.TCheckbutton").pack(anchor="w",
                                                                                                    pady=(6, 0))

        def tentar(senha=None, chave=None, recuperacao=None):
            if getattr(self, "_trabalhando", False):
                return
            espias = ferramentas_espias()
            if espias:
                lbl.config(text="Há um programa capaz de ler a memória aberto: " + ", ".join(espias) +
                                ". Feche-o para desbloquear. Nenhuma tentativa foi gasta.", foreground=C["perigo"])
                return
            hwnd = _hwnd(self.root)
            provedor = None
            if exige_fido and not recuperacao:
                provedor = lambda creds, salt: fido_obter(hwnd, creds, salt)
                lbl.config(text="Toque na sua chave FIDO quando ela piscar (e digite o PIN dela se o "
                                "Windows pedir)...", foreground=C["prim_txt"])
            else:
                lbl.config(text="Verificando...", foreground=C["suave"])
            bt_abrir.state(["disabled"])
            self._trabalhando = True
            self._ocupado(True)
            self._em_segundo_plano(
                lambda: Cofre.abrir(self.caminho, senha=senha, chave=chave,
                                    fido=provedor, recuperacao=recuperacao),
                lambda cofre, erro: concluir(cofre, erro))

        def concluir(cofre, erro):
            self._trabalhando = False
            try:
                bt_abrir.state(["!disabled"])
            except tk.TclError:
                pass
            try:
                if erro is not None:
                    raise erro
                self.cofre = cofre
            except (ChaveMalFormada, FatorFaltando, FidoErro) as ex:
                self._ocupado(False)
                lbl.config(text=f"{ex} Nenhuma tentativa foi gasta.", foreground=C["alerta"])
                return
            except SenhaIncorreta as ex:
                self._erros_sessao += 1
                self._ocupado(False)
                lbl.config(text=f"Senha ou chave incorreta. Restam {ex.restantes} tentativa(s) "
                                f"antes da autodestruição.", foreground=C["perigo"])
                return
            except CofreDestruido:
                self._ocupado(False)
                messagebox.showerror("Cofre destruído",
                                     "Limite de tentativas atingido. O cofre foi apagado.")
                self.mostrar_inicio()
                return
            except ViolacaoDetectada as ex:
                self._ocupado(False)
                messagebox.showerror("VIOLAÇÃO DETECTADA",
                                     f"O arquivo do cofre foi alterado por fora do programa ({ex}).\n\n"
                                     "Por segurança ele foi DESTRUÍDO. Restaure o cofre a partir do seu "
                                     "backup (copie o arquivo de backup para esta pasta com o nome "
                                     f"{os.path.basename(self.caminho)}).")
                self.mostrar_inicio()
                return
            except MemoryError:
                self._ocupado(False)
                messagebox.showerror("Memória insuficiente", "Faltou memória livre para verificar a senha (a blindagem "
                                     "Máxima usa 1 GB). Feche o navegador e outros programas e tente de novo.\n\n"
                                     "Nenhuma tentativa foi gasta.")
                return
            except ArquivoCorrompido as ex:
                self._ocupado(False)
                self._oferecer_restauracao(str(ex))
                return
            except (ArquivoInvalido, OSError, ValueError) as ex:
                self._ocupado(False)
                messagebox.showerror("Erro", str(ex))
                return
            self._ocupado(False)
            if self.cofre.chave_gerada:      # cofre antigo convertido: mostra a nova chave
                chave_nova, self.cofre.chave_gerada = self.cofre.chave_gerada, None
                messagebox.showinfo("Cofre atualizado", "Seu cofre foi atualizado e agora também "
                                    "abre com uma chave de acesso. Guarde-a na próxima tela.")
                self.mostrar_chave_acesso(chave_nova, self.cofre.modo)
            self.tela_principal()
            self._alerta_invasao()
            if getattr(self, "_msg_abertura", ""):
                self.status.config(text=self._msg_abertura)

        def abrir(event=None):
            if getattr(self, "_trabalhando", False):
                return
            s, k = e_senha.get(), e_chave.get()
            r = e_rec.get() if (e_rec is not None and usar_rec.get()) else None
            e_senha.delete(0, "end")
            e_chave.delete(0, "end")
            if e_rec is not None:
                e_rec.delete(0, "end")
            if dois_fatores:
                tentar(senha=s, chave=k, recuperacao=r)
            elif modo.get() == "senha":
                if s:
                    tentar(senha=s, recuperacao=r)
            elif k:
                tentar(chave=k, recuperacao=r)

        e_senha.bind("<Return>", abrir)
        e_chave.bind("<Return>", abrir)
        if e_rec is not None:
            e_rec.bind("<Return>", abrir)
        bt_abrir = ttk.Button(f, text="Desbloquear", style="C.Primario.TButton", command=abrir,
                              image=imagem_icone(self.root, "aberto", "#ffffff"), compound="left")
        bt_abrir.pack(fill="x", pady=(20, 0))
        lbl = ttk.Label(f, text=info, foreground=C["alerta"], style="C.TLabel", wraplength=400, justify="center",
                        anchor="center")
        lbl.pack(fill="x", pady=(12, 0))
        ttk.Separator(f).pack(fill="x", pady=(16, 12))
        self._rotulo_protecao(f)
        self._linha_icone(f, "teclado", C["fraco"], "Dica: use o teclado da tela (botão ao lado do campo) para "
                          "digitar a senha com o mouse. Programas que gravam o teclado não capturam.", "C.",
                          _px(400)).pack(anchor="w", fill="x")
        e_senha.focus_set()


    def _ocupado(self, sim):
        self.root.config(cursor="watch" if sim else "")
        self.root.update()

    # ---------- bloquear junto com o Windows / esconder ao perder o foco ----------
    def _vigiar_sistema(self):
        agora = time.time()
        try:
            if self._ocultadores and not self._app_sem_foco():
                self._mostrar_conteudo()          # voltou ao programa: tira o aviso "Conteúdo oculto"
            if self.cofre is not None and (agora - self._ultimo_tique > 20 or sessao_bloqueada()):
                # pulo no relógio = o PC dormiu/hibernou; ou a sessão do Windows foi bloqueada
                self.bloquear()
            elif self.cofre is not None:
                suspeita = ambiente_suspeito()
                if suspeita:
                    self._invasao_em_andamento(suspeita)
                    return
                self._tique_proc = (self._tique_proc + 1) % 2
                if self._tique_proc == 0:                    # a cada ~4 s
                    espias = ferramentas_espias()
                    if espias:
                        self.bloquear()
                        messagebox.showwarning(
                            "Ferramenta espiã detectada",
                            "Foi aberto um programa capaz de ler a memória de outros programas:\n\n"
                            f"    {', '.join(espias)}\n\n"
                            "O cofre foi BLOQUEADO e as chaves apagadas da memória.\n"
                            "Feche esse programa para desbloquear de novo.")
        finally:
            self._ultimo_tique = time.time()
            try:
                self.root.after(2000, self._vigiar_sistema)
            except tk.TclError:
                pass

    def _app_sem_foco(self):
        """True só quando OUTRO programa está em primeiro plano. Ao trocar de tela o foco interno do Tk
        some por instantes (o campo focado é destruído); isso NÃO é perder o foco do programa."""
        if EH_WINDOWS:
            try:
                import ctypes
                from ctypes import wintypes
                u = ctypes.windll.user32
                u.GetForegroundWindow.restype = wintypes.HWND
                fg = u.GetForegroundWindow()
                if not fg:
                    return True
                pid = wintypes.DWORD(0)
                u.GetWindowThreadProcessId(fg, ctypes.byref(pid))
                return pid.value != os.getpid()
            except Exception:
                pass
        try:
            return self.root.focus_get() is None
        except (KeyError, tk.TclError):
            return False

    def _invasao_em_andamento(self, motivo):
        """Depurador ligado ao cofre aberto: apaga as chaves da memória e fecha (sem destruir o arquivo)."""
        try:
            if self.cofre:
                self.cofre.fechar()
            self.cofre = None
            self._limpar_clip(forcar=True)
        except Exception:
            pass
        try:                       # chaves já apagadas da memória; o ARQUIVO é preservado (pode ser falso alarme)
            self.root.withdraw()
            messagebox.showerror("Depurador detectado",
                                 f"{motivo}\n\nO cofre foi fechado e as chaves apagadas da memória. "
                                 "O arquivo NÃO foi alterado. Se você não está depurando o programa, "
                                 "feche o programa que se anexou a ele (antivírus, ferramenta de captura) "
                                 "e abra o cofre de novo.")
        finally:
            self.root.destroy()

    def _talvez_ocultar(self):
        if self.cofre is None or self._ocultadores or not self._app_sem_foco():
            return
        janelas = [self.root] + [w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)]
        for j in janelas:
            try:
                capa = tk.Frame(j, bg=CORES["fundo"], cursor="hand2")
                tk.Label(capa, text="🔒  Conteúdo oculto\n\nclique para mostrar", fg="white", bg=CORES["fundo"],
                         font="CofreSub").place(relx=0.5, rely=0.5, anchor="center")
                capa.place(x=0, y=0, relwidth=1, relheight=1)
                capa.lift()
                for w in (capa,) + tuple(capa.winfo_children()):
                    w.bind("<Button-1>", lambda e: (self._mostrar_conteudo(), self.root.focus_force()))
                self._ocultadores.append(capa)
            except tk.TclError:
                pass

    def _mostrar_conteudo(self):
        for capa in self._ocultadores:
            try:
                capa.destroy()
            except tk.TclError:
                pass
        self._ocultadores = []

    def _oferecer_restauracao(self, motivo):
        existe = any(os.path.exists(b) for b in _copias(self.caminho))
        if existe and messagebox.askyesno(
                "Arquivo do cofre danificado",
                f"{motivo}\n\nNada foi apagado e nenhuma tentativa foi gasta.\n\n"
                "Existe uma cópia de segurança automática. Restaurar a cópia mais recente agora?\n"
                "(O arquivo danificado fica guardado ao lado, como .danificado.)"):
            usada = restaurar_copia(self.caminho)
            if usada:
                messagebox.showinfo("Cofre restaurado", "Pronto. Digite a senha para abrir o cofre restaurado.")
                self.mostrar_inicio()
            else:
                messagebox.showerror("Não foi possível restaurar",
                                     "As cópias de segurança também estão ilegíveis. Use o seu backup externo.")
        elif not existe:
            messagebox.showerror("Arquivo do cofre danificado",
                                 f"{motivo}\n\nNada foi apagado e nenhuma tentativa foi gasta.\n"
                                 "Não há cópia automática ao lado: restaure o seu backup do cofre.")

    # ---------- itens protegidos ----------
    def _liberar_protegido(self, r):
        """Itens protegidos pedem a senha mestra de novo (vale por 30 s)."""
        if not r or not r.get("protegido"):
            return True
        if time.time() - self._liberado_em.get(r.get("id"), 0.0) < 30:
            return True
        if self._confirmar_senha_atual("Item protegido"):
            self._liberado_em[r.get("id")] = time.time()
            return True
        return False

    def _alerta_invasao(self):
        c = self.cofre
        erros_outros = max(0, c.erros_desde_ultima - self._erros_sessao)
        self._erros_sessao = 0
        if c.ultima_abertura:
            try:
                import datetime
                quando = datetime.datetime.fromisoformat(c.ultima_abertura).strftime("%d/%m/%Y às %H:%M")
            except ValueError:
                quando = c.ultima_abertura
        else:
            quando = None
        self._msg_abertura = f"Última abertura antes desta: {quando}." if quando else ""
        if erros_outros > 0:
            messagebox.showwarning(
                "⚠ ALERTA DE SEGURANÇA",
                f"Houve {erros_outros} tentativa(s) ERRADA(S) de abrir este cofre desde a última vez que "
                f"você o abriu{' (' + quando + ')' if quando else ''}.\n\n"
                "Se não foi você, ALGUÉM TENTOU ABRIR O SEU COFRE.\n"
                "• Verifique onde o pendrive esteve e quem teve acesso a ele.\n"
                "• Considere trocar a senha mestra e gerar uma nova chave de acesso.")

    def historico_aberturas(self):
        import datetime
        d = self._nova_janela("Histórico de aberturas")
        d.grab_set()
        fr = ttk.Frame(d, padding=(26, 22, 26, 20))
        fr.pack(fill="both", expand=True)
        self._cabecalho_dialogo(fr, "historico", "Histórico de aberturas",
                                "Registrado dentro do cofre, criptografado. 'Tentativas erradas antes' = senhas ou "
                                "chaves erradas digitadas entre uma abertura e a seguinte. Valores acima de zero "
                                "que você não reconhece indicam tentativa de invasão.")
        tree = ttk.Treeview(fr, columns=("quando", "erros"), show="headings", height=12)
        tree.heading("quando", text="Aberto em")
        tree.heading("erros", text="Tentativas erradas antes")
        tree.column("quando", width=220)
        tree.column("erros", width=200, anchor="center")
        tree.tag_configure("alerta", foreground=CORES["perigo"])
        for x in reversed(self.cofre.meta.get("historico", [])):
            try:
                q = datetime.datetime.fromisoformat(x.get("quando", "")).strftime("%d/%m/%Y %H:%M:%S")
            except ValueError:
                q = str(x.get("quando", ""))
            e = int(x.get("erros_antes", 0) or 0)
            tree.insert("", "end", values=(q, e), tags=("alerta",) if e else ())
        tree.pack(fill="both", expand=True)
        ttk.Button(fr, text="Fechar", command=d.destroy, style="Primario.TButton").pack(anchor="e", pady=(14, 0))

    def _atividade(self, event=None):
        if self.cofre is None:
            return
        agora = time.monotonic()
        if event is not None and self._timer_bloqueio and agora - getattr(self, "_ultima_atividade", 0) < 1.0:
            return                      # o mouse mexe dezenas de vezes por segundo: basta renovar 1x por segundo
        self._ultima_atividade = agora
        if self._timer_bloqueio:
            self.root.after_cancel(self._timer_bloqueio)
        self._timer_bloqueio = self.root.after(self.INATIVIDADE_MS, self.bloquear)

    def _ao_minimizar(self, event=None):
        if event is not None and event.widget is not self.root:
            return
        try:
            if self.root.state() == "iconic" and self.cofre is not None:
                self.bloquear()
        except tk.TclError:
            pass

    def _nova_janela(self, titulo, mestre=None):
        d = tk.Toplevel(mestre or self.root)
        d.title(titulo)
        d.transient(mestre or self.root)
        d.resizable(False, False)
        d.configure(bg=CORES["fundo"])
        d.update_idletasks()
        proteger_contra_captura(d)
        barra_titulo_escura(d)
        d.bind("<Map>", lambda e: proteger_contra_captura(d) if e.widget is d else None, add="+")
        return d

    @staticmethod
    def _unidade(caminho):
        return os.path.splitdrive(os.path.abspath(caminho))[0].upper()

    def _no_disco_do_windows(self, caminho):
        """O cofre, as chaves e os backups nunca deveriam ficar no disco do Windows (C:)."""
        return EH_WINDOWS and self._unidade(caminho) == os.environ.get("SystemDrive", "C:").upper()

    def _confirmar_destino(self, destino, oque, pai=None):
        if self._no_disco_do_windows(destino):
            return messagebox.askyesno(
                "Salvar no disco do Windows?",
                f"Você escolheu salvar {oque} no disco do Windows ({self._unidade(destino)}).\n\n"
                "O recomendado é um pendrive. Salvar no disco do Windows mesmo assim?", parent=pai)
        return True

    def _corpo_rolavel(self, d, padding):
        """Conteúdo do diálogo numa área que só ganha barra de rolagem se a tela for baixa demais
        (notebook com 768 px, ou zoom de 125%/150%). Em telas grandes, nada muda."""
        caixa = ttk.Frame(d)
        caixa.pack(fill="both", expand=True)
        tela = tk.Canvas(caixa, bg=CORES["fundo"], highlightthickness=0, bd=0, yscrollincrement=_px(24))
        barra = ttk.Scrollbar(caixa, orient="vertical", command=tela.yview)
        tela.configure(yscrollcommand=barra.set)
        tela.pack(side="left", fill="both", expand=True)
        fr = ttk.Frame(tela, padding=padding)
        tela.create_window(0, 0, window=fr, anchor="nw")
        estado = {"barra": False, "pos": False}

        def ajustar(event=None):
            try:
                w, h = fr.winfo_reqwidth(), fr.winfo_reqheight()
                limite = max(_px(320), int(d.winfo_screenheight() * 0.86))
                tela.configure(width=w, height=min(h, limite), scrollregion=(0, 0, w, h))
                precisa = h > limite
                if precisa != estado["barra"]:
                    estado["barra"] = precisa
                    if precisa:
                        barra.pack(side="right", fill="y")
                    else:
                        barra.pack_forget()
                        tela.yview_moveto(0)
                if not estado["pos"]:
                    estado["pos"] = True
                    d.after_idle(lambda: self._centralizar(d))
            except tk.TclError:
                pass

        def rolar(event):
            if not estado["barra"]:
                return
            num = getattr(event, "num", 0)
            passo = -1 if num == 4 else 1 if num == 5 else (-1 if event.delta > 0 else 1)
            tela.yview_scroll(passo * 2, "units")

        fr.bind("<Configure>", ajustar, add="+")
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            d.bind(ev, rolar, add="+")
        return fr

    def _centralizar(self, d):
        """Centraliza o diálogo sobre a janela principal, sem deixar sair da tela."""
        try:
            d.update_idletasks()
            w, h = d.winfo_width(), d.winfo_height()
            sw, sh = d.winfo_screenwidth(), d.winfo_screenheight()
            r = self.root
            x = r.winfo_rootx() + (r.winfo_width() - w) // 2
            y = r.winfo_rooty() + (r.winfo_height() - h) // 2
            x = max(0, min(x, sw - w))
            y = max(0, min(y, sh - h - _px(48)))
            d.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass

    @staticmethod
    def _bloquear_copia(widget):
        """Impede COPIAR e RECORTAR o conteúdo do campo (atalhos e eventos virtuais).
        Selecionar continua livre (arrastar, duplo/triplo clique, Ctrl+A), para poder apagar."""
        for seq in ("<Control-c>", "<Control-C>", "<Control-x>", "<Control-X>",
                    "<Control-Insert>", "<Shift-Delete>", "<<Copy>>", "<<Cut>>"):
            widget.bind(seq, lambda e: "break")

        def selecionar_tudo(e):
            w = e.widget
            try:
                if isinstance(w, tk.Text):
                    w.tag_remove("sel", "1.0", "end")
                    w.tag_add("sel", "1.0", "end-1c")
                    w.mark_set("insert", "end-1c")
                else:
                    w.selection_range(0, "end")
                    w.icursor("end")
            except tk.TclError:
                pass
            return "break"
        for seq in ("<Control-a>", "<Control-A>", "<Control-slash>"):
            widget.bind(seq, selecionar_tudo)

    def _selecionado(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Cofre", "Selecione um item da lista.")
            return None
        for r in self.cofre.registros:
            if r["id"] == sel[0]:
                return r
        return None

    def _salvar(self):
        try:
            self.cofre.salvar()
            return True
        except OSError as ex:
            messagebox.showerror("Erro ao salvar", f"Não foi possível gravar o cofre:\n{ex}")
            return False

    def _copiar_texto(self, valor, descricao):
        ok = copiar_seguro_windows(valor) if EH_WINDOWS else False
        if not ok:
            self.root.clipboard_clear()
            self.root.clipboard_append(valor)
        self._clip_valor = valor
        if self._timer_clip:
            self.root.after_cancel(self._timer_clip)
        self._timer_clip = self.root.after(self.LIMPAR_CLIPBOARD_MS, self._limpar_clip)
        extra = " (fora do histórico Win+V)" if ok else ""
        return (f"Copiado: {descricao}{extra}. A área de transferência será limpa em "
                f"{self.LIMPAR_CLIPBOARD_MS // 1000} s.")

    def _limpar_clip(self, forcar=False):
        self._timer_clip = None
        valor, self._clip_valor = self._clip_valor, None
        try:
            atual = self.root.clipboard_get()
        except tk.TclError:
            atual = None
        if forcar or (valor is not None and atual == valor):
            if EH_WINDOWS:
                limpar_clipboard_windows()
            try:
                self.root.clipboard_clear()
            except tk.TclError:
                pass
        try:
            if hasattr(self, "status") and self.status.winfo_exists():
                self.status.config(text="Área de transferência limpa.")
        except tk.TclError:
            pass

    # ---------- teclado virtual (contra keyloggers) ----------
    def teclado_virtual(self, alvo):
        """Digita no campo 'alvo' por cliques, sem gerar teclas no sistema.
        As teclas mudam de lugar a cada clique (contra gravação de posição do mouse)."""
        topo = alvo.winfo_toplevel()
        d = self._nova_janela("Teclado virtual", topo)
        letras = list("abcdefghijklmnopqrstuvwxyzçáéíóúãõâêôà")
        outros = list("0123456789") + list("!@#$%&*-_=+?.,;:/\\()[]{}<>'\"|~^`")
        estado = {"maiusc": False}
        embaralhar_sempre = tk.BooleanVar(value=True)
        topo_t = ttk.Frame(d, padding=(16, 14, 16, 0))
        topo_t.pack(fill="x")
        ttk.Label(topo_t, text="  Teclado virtual", image=imagem_icone(self.root, "teclado", CORES["prim_txt"], 16),
                  compound="left", font="CofreForte").pack(side="left")
        ttk.Label(topo_t, text="as teclas mudam de lugar — programas espiões não sabem o que você clicou",
                  style="Fraco.TLabel").pack(side="left", padx=(12, 0))
        grade = ttk.Frame(d, padding=(14, 12))
        grade.pack()
        botoes = []
        rnd = secrets.SystemRandom()

        def digitar(ch):
            try:
                alvo.insert("end", ch)
                alvo.event_generate("<<Atualizar>>")
            except tk.TclError:
                d.destroy()
                return
            if embaralhar_sempre.get():
                montar()

        def montar():
            for b in botoes:
                b.destroy()
            botoes.clear()
            chars = [c.upper() if estado["maiusc"] else c for c in letras] + outros
            rnd.shuffle(chars)
            for i, ch in enumerate(chars):
                b = tk.Button(grade, text=ch, width=3, font="CofreMono", takefocus=0, relief="flat", bd=0,
                              bg=CORES["sup2"], fg=CORES["texto"], activebackground=CORES["prim"],
                              activeforeground="#ffffff", highlightthickness=1,
                              highlightbackground=CORES["borda2"], padx=4, pady=6, cursor="hand2",
                              command=lambda c=ch: digitar(c))
                b.grid(row=i // 13, column=i % 13, padx=2, pady=2)
                botoes.append(b)

        def maiusc():
            estado["maiusc"] = not estado["maiusc"]
            bt_m.config(text="abc" if estado["maiusc"] else "ABC")
            montar()

        def apagar():
            try:
                n = len(alvo.get())
                if n:
                    alvo.delete(n - 1, "end")
                    alvo.event_generate("<<Atualizar>>")
            except tk.TclError:
                d.destroy()

        rod = ttk.Frame(d, padding=(16, 0, 16, 14))
        rod.pack(fill="x")
        bt_m = ttk.Button(rod, text="ABC", width=6, command=maiusc, takefocus=0)
        bt_m.pack(side="left")
        ttk.Button(rod, text="Espaço", width=14, command=lambda: digitar(" "), takefocus=0).pack(side="left", padx=4)
        ttk.Button(rod, text="⌫ Apagar", command=apagar, takefocus=0).pack(side="left")
        ttk.Checkbutton(rod, text="Embaralhar a cada tecla", variable=embaralhar_sempre, style="Switch.TCheckbutton",
                        takefocus=0).pack(side="left", padx=12)
        ttk.Button(rod, text="Concluir", command=d.destroy, takefocus=0, style="Primario.TButton").pack(side="right")
        montar()

    def _pedir_senha(self, titulo, texto):
        """Diálogo de senha protegido (substitui o simpledialog, que não tem proteção)."""
        d = self._nova_janela(titulo)
        d.grab_set()
        resultado = {"v": None}
        fr = ttk.Frame(d, padding=(26, 22, 26, 20))
        fr.pack()
        self._cabecalho_dialogo(fr, "cadeado", titulo, texto)
        linha, e = self._linha_secreta(fr, 36)
        linha.pack(fill="x")

        def ok(event=None):
            resultado["v"] = e.get()
            d.destroy()

        e.bind("<Return>", ok)
        bt = ttk.Frame(fr)
        bt.pack(fill="x", pady=(18, 0))
        ttk.Button(bt, text="OK", command=ok, style="Primario.TButton").pack(side="right")
        ttk.Button(bt, text="Cancelar", command=d.destroy).pack(side="right", padx=8)
        e.focus_set()
        self.root.wait_window(d)
        return resultado["v"]

    # ---------- janela da chave de acesso ----------
    def mostrar_chave_acesso(self, chave_txt, modo=MODO_OU):
        d = self._nova_janela("Sua chave de acesso")
        d.grab_set()
        fr = ttk.Frame(d, padding=(26, 22, 26, 20))
        fr.pack(fill="both", expand=True)
        self._cabecalho_dialogo(fr, "chave", "Sua chave de acesso",
                                "Ela aparece só agora. Guarde-a antes de fechar esta janela.", "alerta")
        if modo == MODO_E:
            aviso = ("MODO DOIS FATORES: esta chave é OBRIGATÓRIA junto com a senha mestra.\n"
                     "Ela aparece só agora.\n"
                     "• Salve em arquivo num pendrive SEPARADO do cofre e anote em papel.\n"
                     "• Se perder a chave OU a senha, o cofre NUNCA mais abre (nem os backups).")
        else:
            aviso = ("Esta chave abre o cofre SEM a senha mestra. Ela aparece só agora.\n"
                     "• Salve em arquivo num pendrive SEPARADO do cofre e/ou anote em papel.\n"
                     "• Quem tiver esta chave e o arquivo do cofre consegue abri-lo.\n"
                     "• Se perder senha E chave, não há como recuperar.")
        caixa_av = ttk.Frame(fr, style="Card2.TFrame", padding=(14, 12))
        caixa_av.pack(fill="x", pady=(0, 14))
        ttk.Label(caixa_av, text=aviso, foreground=CORES["alerta"], justify="left", style="S2.TLabel",
                  wraplength=520).pack(anchor="w")
        var = tk.StringVar(value=chave_txt)
        ent = ttk.Entry(fr, textvariable=var, width=40, font="CofreMonoG",
                        state="readonly", exportselection=False)
        self._bloquear_copia(ent)
        ent.pack(fill="x")
        msg = ttk.Label(fr, text="", foreground=CORES["suave"])
        msg.pack(anchor="w", pady=(6, 0))

        def copiar():
            msg.config(text=self._copiar_texto(chave_txt, "Chave"))

        def salvar_arquivo():
            destino = filedialog.asksaveasfilename(parent=d, title="Salvar chave de acesso (use OUTRO pendrive)",
                                                   defaultextension=".key",
                                                   initialfile="chave_cofre.key",
                                                   filetypes=[("Chave do cofre", "*.key")])
            if not destino:
                return
            if not self._confirmar_destino(destino, "a chave de acesso", d):
                return
            if self._unidade(destino) == self._unidade(self.caminho):
                if not messagebox.askyesno("Atenção", "Você está salvando a chave no MESMO pendrive do "
                                           "cofre. Quem levar esse pendrive leva o cofre e a chave juntos.\n\n"
                                           "O recomendado é OUTRO pendrive (e a chave anotada em papel).\n\n"
                                           "Salvar aqui mesmo assim?", parent=d):
                    return
            try:
                with open(destino, "w", encoding="utf-8") as f:
                    f.write(chave_txt + "\n")
                msg.config(text=f"Chave salva em: {destino}")
            except OSError as ex:
                messagebox.showerror("Erro", f"Não foi possível salvar:\n{ex}", parent=d)

        bt = ttk.Frame(fr)
        bt.pack(fill="x", pady=(14, 0))
        C = CORES
        ttk.Button(bt, text="Copiar", command=copiar, image=imagem_icone(self.root, "copiar", C["texto"]),
                   compound="left").pack(side="left")
        ttk.Button(bt, text="Salvar em arquivo (.key)", command=salvar_arquivo,
                   image=imagem_icone(self.root, "backup", C["texto"]), compound="left").pack(side="left", padx=8)
        ttk.Button(bt, text="Imprimir…", image=imagem_icone(self.root, "imprimir", C["texto"]), compound="left",
                   command=lambda: self._imprimir("COFRE DE SENHAS — CHAVE DE ACESSO",
                                                  [("Chave de acesso", chave_txt)], d)).pack(side="left")
        ttk.Button(bt, text="Já guardei a chave", command=d.destroy, style="Primario.TButton").pack(
            side="right", padx=(16, 0))
        self.root.wait_window(d)
        self._limpar_clip(forcar=True)

    # ---------- telas ----------
    def mostrar_inicio(self):
        if os.path.exists(self.caminho):
            self.tela_desbloqueio()
        else:
            self.tela_criar()

    # ---------- tela principal: grupos | contas | detalhes ----------
    def tela_principal(self):
        self._limpar_tela()
        f = self.frame
        C = CORES
        self._revelados = set()
        self.filtro_grupo = tk.StringVar(value="Todos")
        self.filtro_pessoa = tk.StringVar(value="*")       # "*" = todas; "" = Eu (titular do cofre)
        self.busca = tk.StringVar()

        # ----- Cabeçalho -----
        cab = tk.Frame(f, bg=C["fundo"], height=_px(64))
        cab.pack(fill="x")
        cab.pack_propagate(False)
        self._img_marca = desenhar_marca(30).imagem(self.root)
        tk.Label(cab, image=self._img_marca, bg=C["fundo"]).pack(side="left", padx=(20, 10))
        tk.Label(cab, text="Cofre de Senhas", bg=C["fundo"], fg=C["texto"], font="CofreSub").pack(side="left")

        busca_fr = tk.Frame(cab, bg=C["fundo"])
        busca_fr.pack(side="left", padx=(36, 0))
        self.campo_busca = ttk.Entry(busca_fr, textvariable=self.busca, width=34, style="Busca.TEntry")
        self.campo_busca.pack(side="left")
        lupa = tk.Label(self.campo_busca, image=imagem_icone(self.root, "busca", C["fraco"], 16), bg=C["campo"],
                        cursor="xterm")
        lupa.place(x=_px(11), rely=0.5, anchor="w")
        lupa.bind("<Button-1>", lambda e: self.campo_busca.focus_set())
        dica_busca = tk.Label(self.campo_busca, text="Buscar contas  (Ctrl+F)", bg=C["campo"], fg=C["fraco"],
                              font="CofreTexto", cursor="xterm")
        dica_busca.bind("<Button-1>", lambda e: self.campo_busca.focus_set())

        def dica_visivel(*a):
            try:
                if self.busca.get():
                    dica_busca.place_forget()
                else:
                    dica_busca.place(x=_px(36), rely=0.5, anchor="w")
            except tk.TclError:
                pass
        self.busca.trace_add("write", dica_visivel)
        dica_visivel()
        self.busca.trace_add("write", lambda *a: self.atualizar_lista())

        def bt(texto, icone, cmd, estilo="Fantasma.TButton", cor=None, dica=None):
            b = ttk.Button(cab, text=texto, image=imagem_icone(self.root, icone, cor or C["suave"], 16),
                           compound="left" if texto else "image", style=estilo, command=cmd)
            b.pack(side="right", padx=(0, 6))
            if dica:
                self._dica(b, dica)
            return b
        tk.Frame(cab, bg=C["fundo"], width=14).pack(side="right")
        bt("Bloquear", "cadeado", self.bloquear, "TButton", C["texto"], "Trancar o cofre agora (Ctrl+L)")
        self._menu_mais = MenuTema(self, [
            ("Importar planilha (Excel / CSV)…", "importar", self.importar),
            ("Baixar modelo de planilha…", "documento", self.modelo_planilha),
            None,
            ("Verificar senhas (força e repetidas)…", "verificar", self.verificar_senhas),
            ("Histórico de aberturas…", "historico", self.historico_aberturas),
            None,
            ("Chaves FIDO…", "chave", self.gerenciar_fido),
            ("Trocar senha mestra…", "editar", self.trocar_senha),
            ("Nova chave de acesso…", "atualizar", self.nova_chave),
            None,
            ("Backup do cofre…", "backup", self.backup),
            ("Atalhos de teclado", "teclado", self._mostrar_atalhos),
        ])
        bmais = bt("", "mais", lambda: self._menu_mais.abrir(bmais), "Icone.TButton", C["texto"], "Mais opções")
        bt("Chave FIDO", "chave", self.gerenciar_fido, dica="Cadastrar ou gerenciar chaves de segurança FIDO2")
        bt("Gerador", "gerar", lambda: self.dialogo_gerador(), dica="Gerar senha forte e testar senhas (Ctrl+G)")
        bt("Novo item", "novo", self.novo, "Primario.TButton", "#ffffff", "Adicionar conta (Ctrl+N)")
        tk.Frame(f, bg=C["borda"], height=1).pack(fill="x")

        # ----- Rodapé (barra de status) -----
        rod = tk.Frame(f, bg=C["lateral"], height=_px(30))
        rod.pack(side="bottom", fill="x")
        rod.pack_propagate(False)
        tk.Frame(f, bg=C["borda"], height=1).pack(side="bottom", fill="x")
        self.status = tk.Label(rod, text="", bg=C["lateral"], fg=C["suave"], anchor="w", font="CofrePequeno",
                               padx=16)
        self.status.pack(side="left", fill="x", expand=True)
        self.indicadores = tk.Label(rod, text="", bg=C["lateral"], fg=C["fraco"], font="CofrePequeno", padx=16)
        self.indicadores.pack(side="right")

        corpo = tk.Frame(f, bg=C["fundo"])
        corpo.pack(fill="both", expand=True)

        # ----- Coluna 1: grupos -----
        lat = tk.Frame(corpo, bg=C["lateral"], width=_px(236))
        lat.pack(side="left", fill="y")
        lat.pack_propagate(False)
        self._painel_seg = tk.Frame(lat, bg=C["lateral"])
        self._painel_seg.pack(side="bottom", fill="x", padx=12, pady=12)
        rolo = tk.Canvas(lat, bg=C["lateral"], highlightthickness=0, bd=0)
        rolo.pack(fill="both", expand=True)
        interno = tk.Frame(rolo, bg=C["lateral"])
        janela = rolo.create_window(0, 0, window=interno, anchor="nw")
        interno.bind("<Configure>", lambda e: rolo.configure(scrollregion=(0, 0, e.width, e.height)), add="+")
        rolo.bind("<Configure>", lambda e: rolo.itemconfigure(janela, width=e.width), add="+")
        self.lateral_pessoas = BarraLateral(interno)
        self.lateral_pessoas.pack(fill="x", pady=(8, 0))
        self.lateral_pessoas.bind("<<TreeviewSelect>>", self._ao_escolher_pessoa)
        self.lateral = BarraLateral(interno)
        self.lateral.pack(fill="x")
        self.lateral.bind("<<TreeviewSelect>>", self._ao_escolher_grupo)

        def rolar_lateral(event):
            try:
                if not str(event.widget).startswith(str(lat)):
                    return
                if interno.winfo_height() <= rolo.winfo_height():
                    return
                num = getattr(event, "num", 0)
                passo = -1 if num == 4 else 1 if num == 5 else (-1 if event.delta > 0 else 1)
                rolo.yview_scroll(passo * 2, "units")
            except (tk.TclError, AttributeError):
                pass
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.bind(ev, rolar_lateral)
        tk.Frame(corpo, bg=C["borda"], width=1).pack(side="left", fill="y")

        # ----- Coluna 3: detalhes -----
        self.detalhe = ttk.Frame(corpo, padding=(26, 22, 26, 18), width=_px(420), style="C.TFrame")
        self.detalhe.pack(side="right", fill="y")
        self.detalhe.pack_propagate(False)
        tk.Frame(corpo, bg=C["borda"], width=1).pack(side="right", fill="y")

        # ----- Coluna 2: contas -----
        meio = tk.Frame(corpo, bg=C["fundo"])
        meio.pack(side="left", fill="both", expand=True)
        topo_lista = tk.Frame(meio, bg=C["fundo"])
        topo_lista.pack(fill="x", padx=(22, 16), pady=(16, 6))
        self._titulo_lista = tk.Label(topo_lista, text="Todas as contas", bg=C["fundo"], fg=C["texto"],
                                      font="CofreSub", anchor="w")
        self._titulo_lista.pack(side="left")
        self._conta_lista = tk.Label(topo_lista, text="", bg=C["fundo"], fg=C["fraco"], font="CofreTexto")
        self._conta_lista.pack(side="left", padx=(10, 0), pady=(3, 0))
        self.tree = ListaContas(meio)
        self.tree.pack(fill="both", expand=True, padx=(6, 0))
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._agendar_detalhe())
        self.tree.bind("<Double-1>", lambda e: self.editar())
        self.tree.bind("<Return>", lambda e: self.editar())
        self.tree.bind("<Delete>", lambda e: self.excluir())
        self.tree.bind("<Control-c>", lambda e: (self.copiar("senha"), "break")[1])
        self.tree.bind("<Control-b>", lambda e: (self.copiar("login"), "break")[1])
        self.vazio = ttk.Label(meio, text="")

        # Atalhos
        for seq, acao in (("<Control-f>", lambda e: self.campo_busca.focus_set()),
                          ("<Control-n>", lambda e: self.novo()),
                          ("<Control-l>", lambda e: self.bloquear()),
                          ("<Control-g>", lambda e: self.dialogo_gerador())):
            self.root.bind(seq, lambda e, a=acao: a(e) if self.cofre is not None else None)
        self.campo_busca.bind("<Escape>", lambda e: self.busca.set(""))
        self.campo_busca.bind("<Down>", lambda e: (self.tree.focus_set(), self.tree._andar(1)))

        self.atualizar_lista()
        self._montar_detalhe()
        self._atualizar_indicadores()
        self._atividade()
        self._aquecer_cache()

    def _aquecer_cache(self):
        """Desenha com antecedência (aos poucos, sem travar a tela) os avatares e ícones do painel de
        detalhes, para o primeiro clique em cada conta já ser rápido."""
        C = CORES
        tarefas = [lambda c=cor: self._imagem_avatar(c, 56) for cor in TONS]
        tarefas += [lambda n=n, c=c, s=s: imagem_icone(self.root, n, c, s) for n, c, s in (
            ("copiar", C["suave"], 16), ("ver", C["suave"], 16), ("ocultar", C["suave"], 16),
            ("editar", "#ffffff", 16), ("imprimir", C["texto"], 16), ("excluir", C["perigo"], 16),
            ("cadeado", C["prim_txt"], 14), ("pessoa", C["fraco"], 32))]
        tarefas += [lambda k=k: self._barra_forca(k, 56) for k in range(5)]

        def passo():
            if not tarefas or self.cofre is None:
                return
            try:
                tarefas.pop(0)()
                self.root.after(1, passo)
            except tk.TclError:
                pass
        self.root.after(150, passo)

    def _atualizar_indicadores(self):
        C = CORES
        partes = [os.path.basename(self.caminho), "AES-256 + ChaCha20", "Argon2id"]
        try:
            self.indicadores.config(text="   •   ".join(partes))
        except (tk.TclError, AttributeError):
            pass
        # Painel de segurança na barra lateral
        p = getattr(self, "_painel_seg", None)
        if p is None:
            return
        try:
            for w in p.winfo_children():
                w.destroy()
        except tk.TclError:
            return
        txt, cor = self._texto_protecao()
        tudo_ok = cor == C["ok"]
        caixa = tk.Frame(p, bg=C["sup"], highlightthickness=1, highlightbackground=C["borda"], padx=12, pady=10)
        caixa.pack(fill="x")
        topo = tk.Frame(caixa, bg=C["sup"])
        topo.pack(fill="x")
        tk.Label(topo, image=imagem_icone(self.root, "escudo" if tudo_ok else "alerta",
                                          C["ok"] if tudo_ok else C["alerta"], 16), bg=C["sup"]).pack(side="left")
        tk.Label(topo, text="Cofre protegido" if tudo_ok else "Proteção parcial", bg=C["sup"], fg=C["texto"],
                 font="CofreForte").pack(side="left", padx=(8, 0))
        linhas = [("Captura de tela bloqueada" if self.protegido else "Captura de tela livre", self.protegido)]
        if EH_WINDOWS:
            linhas.append(("Memória trancada", "memoria" in BLINDAGEM))
            linhas.append(("Anti-injeção e anti-espiões", "ganchos" in BLINDAGEM))
        fido = self.cofre.fido if self.cofre is not None else None
        linhas.append((f"Chave FIDO: {len(fido['chaves'])}" if fido else "Chave FIDO: nenhuma", bool(fido)))
        linhas.append((f"Bloqueio automático: {self.INATIVIDADE_MS // 60000} min", True))
        for texto, bom in linhas:
            lin = tk.Frame(caixa, bg=C["sup"])
            lin.pack(fill="x", pady=(5, 0))
            tk.Label(lin, image=_ponto_img(self.root, C["ok"] if bom else C["fraco"], 6), bg=C["sup"]).pack(
                side="left", padx=(5, 9))
            tk.Label(lin, text=texto, bg=C["sup"], fg=C["suave"], font="CofrePequeno").pack(side="left")

    def _ponto(self, grupo):
        """Bolinha com a cor do grupo."""
        return _ponto_img(self.root, tom_para(grupo) if grupo else CORES["fraco"])

    def atualizar_lista(self, manter_lateral=False, so_status=False):
        if not hasattr(self, "tree") or self.cofre is None:
            return
        try:
            self.tree.winfo_exists()
        except tk.TclError:
            return
        C = CORES
        regs = self.cofre.registros
        auditoria = auditar_cofre(regs)
        alerta = {a[0]["id"] for a in auditoria if a[4] <= 1}
        grave = {a[0]["id"] for a in auditoria if a[4] == 0}
        pessoas = self._pessoas()
        varias = len(pessoas) > 1
        fp = self.filtro_pessoa.get()
        if fp != "*" and fp not in pessoas:
            fp = "*"
            self.filtro_pessoa.set("*")
        da_pessoa = [r for r in regs if fp == "*" or self._pessoa_de(r) == fp]
        filtro = self.filtro_grupo.get()
        termo = self.busca.get().lower().strip()
        visiveis = []
        for r in sorted(da_pessoa, key=lambda r: r.get("servico", "").lower()):
            g = (r.get("grupo") or "").strip()
            if filtro == "(sem grupo)" and g:
                continue
            if filtro == "⚠ Atenção" and r["id"] not in alerta:
                continue
            if filtro not in ("Todos", "(sem grupo)", "⚠ Atenção") and g != filtro:
                continue
            texto = (f'{r.get("servico", "")} {r.get("login", "")} {r.get("notas", "")} {g} '
                     f'{self._nome_pessoa(self._pessoa_de(r))}').lower()
            if termo and termo not in texto:
                continue
            visiveis.append(r)
        if not so_status:
            if not manter_lateral:
                # pessoas
                entp = []
                if varias:
                    entp.append({"iid": "p:*", "texto": "Todas as pessoas", "n": len(regs), "icone": "todos",
                                 "secao": "Pessoas"})
                for i, pe in enumerate(pessoas):
                    nome = self._nome_pessoa(pe)
                    entp.append({"iid": "p:" + pe, "texto": nome if len(nome) <= 24 else nome[:23] + "…",
                                 "n": sum(1 for r in regs if self._pessoa_de(r) == pe), "icone": "pessoa",
                                 "secao": "Pessoas" if (i == 0 and not varias) else None,
                                 "menu": lambda ev, pe=pe: self._menu_pessoa(ev, pe)})
                entp.append({"iid": "__nova_pessoa__", "texto": "Adicionar pessoa", "n": "", "icone": "novo",
                             "cor_txt": C["fraco"], "acao": self._adicionar_pessoa})
                self.lateral_pessoas.definir(entp, ("p:" + fp) if varias else "p:")
                # contas e grupos da pessoa escolhida
                alerta_p = alerta & {r["id"] for r in da_pessoa}
                ent = [{"iid": "__todos__", "texto": "Todas as contas", "n": len(da_pessoa), "icone": "todos",
                        "secao": "Contas"}]
                if alerta_p:
                    ent.append({"iid": "__atencao__", "texto": "Atenção", "n": len(alerta_p), "icone": "alerta",
                                "cor_icone": C["alerta"], "cor_n": C["alerta"]})
                grupos = sorted({(r.get("grupo") or "").strip() for r in da_pessoa} - {""}, key=str.lower)
                for i, g in enumerate(grupos):
                    n = sum(1 for r in da_pessoa if (r.get("grupo") or "").strip() == g)
                    nome = g if len(g) <= 24 else g[:23] + "…"
                    ent.append({"iid": "g:" + g, "texto": nome, "n": n, "cor": tom_para(g),
                                "secao": "Grupos" if i == 0 else None,
                                "menu": lambda ev, g=g: self._menu_grupo(ev, g)})
                sem = sum(1 for r in da_pessoa if not (r.get("grupo") or "").strip())
                if sem and grupos:
                    ent.append({"iid": "__sem__", "texto": "Sem grupo", "n": sem, "cor": C["fraco"]})
                iid = {"Todos": "__todos__", "(sem grupo)": "__sem__", "⚠ Atenção": "__atencao__"}.get(
                    filtro, "g:" + filtro)
                if not any(e["iid"] == iid for e in ent):
                    iid = "__todos__"
                    self.filtro_grupo.set("Todos")
                    filtro = "Todos"
                self.lateral.definir(ent, iid)
            linhas = []
            for r in visiveis:
                segredos = [ROTULOS[c] for c in CAMPOS_SECRETOS if r.get(c)]
                contem = ("🔒 " if r.get("protegido") else "") + ", ".join(segredos)
                if r["id"] in alerta:
                    contem = "⚠ " + contem
                sub = r.get("login") or " • ".join(segredos) or "Sem dados"
                if varias and fp == "*" and self._pessoa_de(r):
                    sub = f"{sub}   ·   {self._pessoa_de(r)}"
                linhas.append({"iid": r["id"], "titulo": r.get("servico", "") or "(sem nome)",
                               "login": r.get("login", ""), "sub": sub, "contem": contem,
                               "cor": tom_para(r.get("servico", "")),
                               "alerta": 2 if r["id"] in grave else (1 if r["id"] in alerta else 0),
                               "protegido": bool(r.get("protegido"))})
            if not regs:
                vazio = ("Nenhuma conta ainda", "Clique em  Novo item  ou importe sua planilha pelo menu  "
                                                "⋯ → Importar planilha.")
            elif not visiveis:
                vazio = ("Nada encontrado", "Nenhuma conta corresponde a esta busca ou filtro.")
            else:
                vazio = ("", "")
            self.tree.definir(linhas, vazio)
            titulo = {"Todos": "Todas as contas", "(sem grupo)": "Sem grupo", "⚠ Atenção": "Precisam de atenção"
                      }.get(filtro, filtro)
            if varias and fp != "*":
                titulo = f"{self._nome_pessoa(fp)}  ·  {titulo}"
            self._titulo_lista.config(text=titulo)
            self._conta_lista.config(text=f"{len(visiveis)}")
            self._montar_detalhe()
        if not getattr(self, "_msg_abertura", "") or so_status:
            self.status.config(text=f"{len(visiveis)} de {len(regs)} conta(s)"
                                    + (f"   •   {len(alerta)} " + ("precisa" if len(alerta) == 1 else "precisam") + " de atenção"
                                       if alerta else ""))

    def _agendar_detalhe(self):
        """Junta várias seleções seguidas (ex.: segurar a seta) numa única montagem do painel."""
        if getattr(self, "_detalhe_pendente", None):
            return

        def rodar():
            self._detalhe_pendente = None
            self._montar_detalhe()
        self._detalhe_pendente = self.root.after_idle(rodar)

    def _imagem_avatar(self, cor, tam):
        cache = self.__dict__.setdefault("_cache_avatar", {})
        if (cor, tam) not in cache:
            cache[(cor, tam)] = desenhar_avatar(cor, tam).imagem(self.root)
        return cache[(cor, tam)]

    def _montar_detalhe(self):
        if not hasattr(self, "detalhe"):
            return
        C = CORES
        r = self._selecionado_silencioso()
        try:
            filhos = self.detalhe.winfo_children()
        except tk.TclError:
            return
        # nada mudou (mesmo item, mesmos dados, mesmos campos à mostra): não remonta
        chave = None if not r else (r["id"], tuple(sorted(cp for (i, cp) in self._revelados if i == r["id"])),
                                    tuple(sorted((k, str(v)) for k, v in r.items())))
        if filhos and chave is not None and chave == getattr(self, "_detalhe_chave", None):
            return
        self._detalhe_chave = chave
        for w in filhos:
            w.destroy()
        d = self.detalhe
        if not r:
            vazio = ttk.Frame(d, style="C.TFrame")
            vazio.pack(expand=True)
            ttk.Label(vazio, image=imagem_icone(self.root, "pessoa", C["fraco"], 32), style="C.TLabel").pack()
            ttk.Label(vazio, text="Selecione uma conta", style="C.H2.TLabel").pack(pady=(12, 2))
            ttk.Label(vazio, text="Os detalhes aparecem aqui.", style="C.Suave.TLabel").pack()
            return

        topo = ttk.Frame(d, style="C.TFrame")
        topo.pack(fill="x")
        av = tk.Canvas(topo, width=_px(56), height=_px(56), bg=C["sup"], highlightthickness=0)
        av._img = self._imagem_avatar(tom_para(r.get("servico", "")), 56)
        av.create_image(_px(28), _px(28), image=av._img)
        av.create_text(_px(28), _px(28), text=(r.get("servico", "?").strip()[:1] or "?").upper(), fill="white",
                       font="CofreTitulo")
        av.pack(side="left", padx=(0, 14))
        tit = ttk.Frame(topo, style="C.TFrame")
        tit.pack(side="left", fill="x", expand=True)
        ttk.Label(tit, text=r.get("servico", ""), style="C.H2.TLabel", font="CofreTitulo",
                  wraplength=_px(280)).pack(anchor="w")
        chips = ttk.Frame(tit, style="C.TFrame")
        chips.pack(anchor="w", pady=(4, 0))
        if self._pessoa_de(r) or len(self._pessoas()) > 1:
            ttk.Label(chips, text=" " + self._nome_pessoa(self._pessoa_de(r)),
                      image=imagem_icone(self.root, "pessoa", C["prim_txt"], 14),
                      compound="left", style="C.Suave.TLabel").pack(side="left", padx=(0, 12))
        if r.get("grupo"):
            ttk.Label(chips, text=" " + r["grupo"], image=_ponto_img(self.root, tom_para(r["grupo"]), 8),
                      compound="left", style="C.Suave.TLabel").pack(side="left", padx=(0, 12))
        if r.get("protegido"):
            ttk.Label(chips, text=" Protegido", image=imagem_icone(self.root, "cadeado", C["prim_txt"], 14),
                      compound="left", style="C.TLabel", foreground=C["prim_txt"]).pack(side="left")

        # ações (embaixo)
        acoes = ttk.Frame(d, style="C.TFrame")
        acoes.pack(side="bottom", fill="x", pady=(12, 0))
        ttk.Button(acoes, text="Editar", style="C.Primario.TButton", command=self.editar,
                   image=imagem_icone(self.root, "editar", "#ffffff"), compound="left").pack(side="left")
        ttk.Button(acoes, text="Imprimir", style="C.TButton", command=self.imprimir_item,
                   image=imagem_icone(self.root, "imprimir", C["texto"]), compound="left").pack(side="left", padx=8)
        ttk.Button(acoes, text="Excluir", style="C.Perigo.TButton", command=self.excluir,
                   image=imagem_icone(self.root, "excluir", C["perigo"]), compound="left").pack(side="right")

        campos = ttk.Frame(d, style="C.TFrame")
        campos.pack(fill="both", expand=True, pady=(18, 0))
        primeiro = True
        for campo in ("login",) + CAMPOS_SECRETOS:
            valor = r.get(campo, "")
            if not valor:
                continue
            if not primeiro:
                ttk.Separator(campos).pack(fill="x", pady=10)
            primeiro = False
            secreto = campo in CAMPOS_SECRETOS
            chave = (r["id"], campo)
            aberto = chave in self._revelados
            bloco = ttk.Frame(campos, style="C.TFrame")
            bloco.pack(fill="x")
            ttk.Label(bloco, text=ROTULOS[campo].upper(), style="C.Campo.TLabel").pack(anchor="w")
            linha = ttk.Frame(bloco, style="C.TFrame")
            linha.pack(fill="x", pady=(3, 0))
            if campo == "codigos" and not aberto:
                mostra = f"••••••  ({len([x for x in valor.splitlines() if x.strip()])} código(s))"
            elif secreto and not aberto:
                mostra = "•" * min(max(len(valor), 8), 16)
            else:
                mostra = valor
            bc = ttk.Button(linha, text=" Copiar", image=imagem_icone(self.root, "copiar", C["suave"]),
                            compound="left", style="C.Icone.TButton")
            bc.config(command=lambda c=campo, b=bc: self.copiar(c) and self._copiado(b))
            bc.pack(side="right")
            self._dica(bc, f"Copiar {ROTULOS[campo].lower()} para colar em outro lugar (Ctrl+V).\n"
                           f"A área de transferência é limpa em {self.LIMPAR_CLIPBOARD_MS // 1000} s.")
            if secreto:
                bv = ttk.Button(linha, text="Ocultar" if aberto else "Mostrar",
                                image=imagem_icone(self.root, "ocultar" if aberto else "ver", C["suave"]),
                                compound="image", style="C.Icone.TButton",
                                command=lambda c=campo: self._alternar_revelar(c))
                bv.pack(side="right", padx=(0, 2))
                self._dica(bv, "Ocultar" if aberto else "Mostrar (some sozinho em 20 s)")
            ttk.Label(linha, text=mostra, style="C.Valor.TLabel" if secreto else "C.TLabel",
                      font="CofreMono" if secreto else "CofreTexto", wraplength=250, justify="left").pack(
                side="left", anchor="w")
            if campo in ("senha", "senha_extra"):
                nota, rot, bits, _ = avaliar_forca(valor)
                ttk.Label(bloco, text="  " + rot, image=self._barra_forca(nota, 56), compound="left",
                          foreground=self._CORES_FORCA[nota], style="C.TLabel", font="CofrePequeno").pack(
                    anchor="w", pady=(4, 0))
            elif campo == "pin" and pin_obvio(valor):
                ttk.Label(bloco, text="  PIN fácil de adivinhar", image=self._barra_forca(0, 56), compound="left",
                          foreground=C["perigo"], style="C.TLabel", font="CofrePequeno").pack(anchor="w", pady=(4, 0))
        if r.get("notas"):
            if not primeiro:
                ttk.Separator(campos).pack(fill="x", pady=10)
            ttk.Label(campos, text="NOTAS", style="C.Campo.TLabel").pack(anchor="w")
            ttk.Label(campos, text=r["notas"], style="C.Suave.TLabel", wraplength=350, justify="left").pack(
                anchor="w", pady=(3, 0))


    def _mostrar_atalhos(self):
        messagebox.showinfo("Atalhos de teclado",
                            "Ctrl+F   buscar\nCtrl+N   novo item\nCtrl+G   gerador de senhas\n"
                            "Ctrl+L   bloquear o cofre\n\nNa lista de contas:\n"
                            "Enter / duplo clique   editar\nCtrl+C   copiar a senha\nCtrl+B   copiar o login\n"
                            "Delete   excluir\nEsc (na busca)   limpar a busca")

    def _avisar(self, texto):
        """Mensagem temporária na barra de status."""
        try:
            self.status.config(text=texto)
            if getattr(self, "_timer_aviso", None):
                self.root.after_cancel(self._timer_aviso)
            self._timer_aviso = self.root.after(6000, lambda: self.atualizar_lista(so_status=True))
        except tk.TclError:
            pass

    def _grupos(self):
        return sorted({(r.get("grupo") or "").strip() for r in self.cofre.registros} - {""}, key=str.lower)

    def _ids_com_alerta(self):
        return {a[0]["id"] for a in auditar_cofre(self.cofre.registros) if a[4] <= 1}

    # ---------- pessoas ----------
    TITULAR = "Eu"

    @staticmethod
    def _pessoa_de(r):
        return (r.get("pessoa") or "").strip()

    def _nome_pessoa(self, pessoa):
        return pessoa or self.TITULAR

    def _valor_pessoa(self, texto):
        t = (texto or "").strip()
        return "" if t.lower() in ("", self.TITULAR.lower()) else t

    def _pessoas(self):
        """'' (Eu, o titular do cofre) primeiro, depois as outras pessoas em ordem alfabética."""
        extras = [p for p in self.cofre.meta.get("pessoas", []) if isinstance(p, str)]
        nomes = {self._pessoa_de(r) for r in self.cofre.registros} | {p.strip() for p in extras}
        nomes.discard("")
        return [""] + sorted(nomes, key=str.lower)

    def _ao_escolher_pessoa(self, event=None):
        sel = self.lateral_pessoas.selection()
        if not sel or not sel[0].startswith("p:"):
            return
        self.filtro_pessoa.set(sel[0][2:])
        self.filtro_grupo.set("Todos")
        self.root.after_idle(self.atualizar_lista)

    def _pedir_nome(self, titulo, texto, inicial=""):
        """Pequena janela para digitar um nome. Devolve o nome ou None."""
        d = self._nova_janela(titulo)
        d.grab_set()
        fr = ttk.Frame(d, padding=(24, 20, 24, 18))
        fr.pack(fill="both", expand=True)
        ttk.Label(fr, text=texto, wraplength=_px(340), justify="left").pack(anchor="w", pady=(0, 8))
        e = ttk.Entry(fr, width=32)
        e.pack(fill="x")
        e.insert(0, inicial)
        e.select_range(0, "end")
        e.focus_set()
        res = {"v": None}

        def ok(event=None):
            v = " ".join(e.get().split())
            if v:
                res["v"] = v[:40]
                d.destroy()

        bt = ttk.Frame(fr)
        bt.pack(fill="x", pady=(16, 0))
        ttk.Button(bt, text="OK", style="Primario.TButton", command=ok).pack(side="right")
        ttk.Button(bt, text="Cancelar", command=d.destroy).pack(side="right", padx=8)
        e.bind("<Return>", ok)
        d.bind("<Escape>", lambda ev: d.destroy())
        self._centralizar(d)
        d.wait_window()
        return res["v"]

    def _nome_livre(self, nome, ignorar=None):
        existentes = {self._nome_pessoa(p).lower() for p in self._pessoas() if p != ignorar}
        if nome.lower() in existentes:
            messagebox.showerror("Pessoa", f'Já existe "{nome}".')
            return False
        return True

    def _adicionar_pessoa(self):
        nome = self._pedir_nome("Adicionar pessoa", "Nome da pessoa (ex.: Pai, Mãe, Ana). As contas dela ficam "
                                                     "separadas das suas, dentro deste mesmo cofre.")
        if not nome or not self._nome_livre(nome):
            return
        lista = [p for p in self.cofre.meta.get("pessoas", []) if isinstance(p, str)]
        self.cofre.meta["pessoas"] = lista + [nome]
        if not self._salvar():
            self.cofre.meta["pessoas"] = lista
            return
        self.filtro_pessoa.set(nome)
        self.filtro_grupo.set("Todos")
        self.atualizar_lista()
        self._avisar(f'Pessoa "{nome}" adicionada. Use  Novo item  para criar contas dela.')

    def _menu_pessoa(self, event, pessoa):
        if not pessoa:
            return                              # "Eu" é o titular do cofre: não renomeia nem remove
        MenuTema(self, [("Renomear…", "editar", lambda: self._renomear_pessoa(pessoa)),
                        ("Remover pessoa…", "excluir", lambda: self._remover_pessoa(pessoa))]
                 ).abrir(event.widget, (event.x_root, event.y_root))

    def _renomear_pessoa(self, pessoa):
        novo = self._pedir_nome("Renomear pessoa", f'Novo nome para "{pessoa}":', pessoa)
        if not novo or novo == pessoa or not self._nome_livre(novo, ignorar=pessoa):
            return
        antes = [(r, r.get("pessoa")) for r in self.cofre.registros]
        lista = list(self.cofre.meta.get("pessoas", []))
        for r in self.cofre.registros:
            if self._pessoa_de(r) == pessoa:
                r["pessoa"] = novo
        self.cofre.meta["pessoas"] = [novo if p == pessoa else p for p in lista]
        if not self._salvar():
            for r, v in antes:
                r["pessoa"] = v
            self.cofre.meta["pessoas"] = lista
            return
        if self.filtro_pessoa.get() == pessoa:
            self.filtro_pessoa.set(novo)
        self.atualizar_lista()

    def _remover_pessoa(self, pessoa):
        contas = [r for r in self.cofre.registros if self._pessoa_de(r) == pessoa]
        msg = (f'Remover a pessoa "{pessoa}"?' + (f"\n\nAs {len(contas)} conta(s) dela NÃO são apagadas: "
                                                   f"passam para {self.TITULAR}." if contas else ""))
        if not messagebox.askyesno("Remover pessoa", msg):
            return
        lista = list(self.cofre.meta.get("pessoas", []))
        for r in contas:
            r["pessoa"] = ""
        self.cofre.meta["pessoas"] = [p for p in lista if p != pessoa]
        if not self._salvar():
            for r in contas:
                r["pessoa"] = pessoa
            self.cofre.meta["pessoas"] = lista
            return
        self.filtro_pessoa.set("*")
        self.atualizar_lista()

    def _menu_grupo(self, event, grupo):
        MenuTema(self, [("Transformar em pessoa", "pessoa", lambda: self._grupo_para_pessoa(grupo)),
                        ("Renomear grupo…", "editar", lambda: self._renomear_grupo(grupo))]
                 ).abrir(event.widget, (event.x_root, event.y_root))

    def _no_escopo(self, r):
        fp = self.filtro_pessoa.get()
        return fp == "*" or self._pessoa_de(r) == fp

    def _grupo_para_pessoa(self, grupo):
        """Ex.: o grupo 'pai' (vindo da aba da planilha) vira a pessoa 'Pai'."""
        contas = [r for r in self.cofre.registros if (r.get("grupo") or "").strip() == grupo and self._no_escopo(r)]
        nome = grupo[:1].upper() + grupo[1:]
        existente = next((p for p in self._pessoas() if p and p.lower() == nome.lower()), None)
        nome = existente or nome
        if not messagebox.askyesno("Transformar em pessoa",
                                   f'As {len(contas)} conta(s) do grupo "{grupo}" passam a ser da pessoa "{nome}" '
                                   "(e saem do grupo).\n\nContinuar?"):
            return
        antes = [(r, r.get("pessoa"), r.get("grupo")) for r in contas]
        for r in contas:
            r["pessoa"] = nome
            r["grupo"] = ""
        if not self._salvar():
            for r, pe, g in antes:
                r["pessoa"], r["grupo"] = pe, g
            return
        self.filtro_pessoa.set(nome)
        self.filtro_grupo.set("Todos")
        self.atualizar_lista()

    def _renomear_grupo(self, grupo):
        novo = self._pedir_nome("Renomear grupo", f'Novo nome para o grupo "{grupo}":', grupo)
        if not novo or novo == grupo:
            return
        contas = [r for r in self.cofre.registros if (r.get("grupo") or "").strip() == grupo and self._no_escopo(r)]
        for r in contas:
            r["grupo"] = novo
        if not self._salvar():
            for r in contas:
                r["grupo"] = grupo
            return
        if self.filtro_grupo.get() == grupo:
            self.filtro_grupo.set(novo)
        self.atualizar_lista()

    def _ao_escolher_grupo(self, event=None):
        sel = self.lateral.selection()
        if not sel:
            return
        alvo = {"__todos__": "Todos", "__sem__": "(sem grupo)", "__atencao__": "⚠ Atenção"}.get(sel[0])
        self.filtro_grupo.set(alvo if alvo else sel[0][2:])
        self.atualizar_lista(manter_lateral=True)

    # ---------- painel de detalhes ----------
    def _selecionado_silencioso(self):
        sel = self.tree.selection() if hasattr(self, "tree") else ()
        return next((r for r in self.cofre.registros if sel and r["id"] == sel[0]), None) if self.cofre else None

    def _alternar_revelar(self, campo):
        r = self._selecionado_silencioso()
        if not r:
            return
        chave = (r["id"], campo)
        timers = self.__dict__.setdefault("_timers_revelar", {})
        if chave in self._revelados:
            self._revelados.discard(chave)
            if chave in timers:
                try:
                    self.root.after_cancel(timers.pop(chave))
                except Exception:
                    pass
        else:
            if not self._liberar_protegido(r):
                return
            self._revelados.add(chave)
            timers[chave] = self.root.after(20000, lambda: (timers.pop(chave, None), self._revelados.discard(chave),
                                                            self._montar_detalhe()))
        self._montar_detalhe()

    # ---------- ações ----------
    def novo(self):
        self.dialogo_registro(None)

    def editar(self):
        r = self._selecionado()
        if r and self._liberar_protegido(r):
            self.dialogo_registro(r)

    def excluir(self):
        r = self._selecionado()
        if r and messagebox.askyesno("Excluir", f'Excluir "{r.get("servico", "")}"?\n\nEsta ação não pode ser desfeita.'):
            self.cofre.registros.remove(r)
            if not self._salvar():
                self.cofre.registros.append(r)
            self.atualizar_lista()
            self._montar_detalhe()

    def copiar(self, campo):
        r = self._selecionado()
        if not r or not self._liberar_protegido(r):
            return
        valor = r.get(campo, "")
        if not valor:
            self._avisar(f"Este item não tem {ROTULOS[campo]}.")
            return
        self._avisar("📋 " + self._copiar_texto(valor, ROTULOS[campo]) + "  Cole com Ctrl+V.")
        return True

    def _copiado(self, botao, com_texto=True, cor_icone=None):
        """Retorno visual no próprio botão: vira '✓ Copiado' por 2 segundos."""
        try:
            antes = (botao.cget("text"), botao.cget("image"))
            botao.config(image=imagem_icone(self.root, "ok", CORES["ok"]),
                         **({"text": " Copiado"} if com_texto else {}))

            def voltar():
                try:
                    botao.config(text=antes[0], image=antes[1])
                except tk.TclError:
                    pass
            botao.after(2000, voltar)
        except tk.TclError:
            pass

    def _copiar_campo(self, entrada, botao, nome):
        """Copia o que está num campo de senha do formulário (a cópia pelo teclado continua bloqueada)."""
        try:
            valor = entrada.get()
        except tk.TclError:
            return
        if not valor:
            return
        self._copiar_texto(valor, nome)
        self._copiado(botao, com_texto=False)

    def _texto_multilinha(self, pai, altura=4, mono=False, largura=40):
        C = CORES
        t = tk.Text(pai, width=largura, height=altura, font="CofreMono" if mono else "CofreTexto",
                    exportselection=False, undo=False, relief="flat", bd=0, padx=10, pady=8,
                    bg=C["campo"], fg=C["texto"], insertbackground=C["texto"], highlightthickness=1,
                    highlightbackground=C["borda2"], highlightcolor=C["prim"], wrap="word")
        self._bloquear_copia(t)
        return t

    def dialogo_registro(self, reg):
        C = CORES
        d = self._nova_janela("Editar item" if reg else "Novo item")
        d.grab_set()
        fr = self._corpo_rolavel(d, (26, 22, 26, 20))
        self._cabecalho_dialogo(fr, "editar" if reg else "novo", "Editar item" if reg else "Novo item",
                                "Tudo o que você digitar aqui fica criptografado dentro do cofre.")
        campos = {}

        # Conta / grupo / login
        topo = ttk.Frame(fr)
        topo.pack(fill="x")
        topo.columnconfigure(0, weight=3)
        topo.columnconfigure(1, weight=2)
        ttk.Label(topo, text=ROTULOS["servico"].upper(), style="Campo.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(topo, text="GRUPO", style="Campo.TLabel").grid(row=0, column=1, sticky="w", padx=(12, 0))
        ent = ttk.Entry(topo, width=30)
        ent.grid(row=1, column=0, sticky="ew", pady=(4, 12))
        campos["servico"] = ent
        cg = ttk.Combobox(topo, width=20, values=self._grupos())
        cg.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=(4, 12))
        cg.insert(0, (reg or {}).get("grupo", "") or (self.filtro_grupo.get()
                                                     if self.filtro_grupo.get() not in ("Todos", "(sem grupo)", "⚠ Atenção")
                                                     else ""))
        campos["grupo"] = cg
        ttk.Label(topo, text=ROTULOS["login"].upper(), style="Campo.TLabel").grid(row=2, column=0, sticky="w")
        ttk.Label(topo, text="PESSOA", style="Campo.TLabel").grid(row=2, column=1, sticky="w", padx=(12, 0))
        ent = ttk.Entry(topo, width=30)
        ent.grid(row=3, column=0, sticky="ew", pady=(4, 0))
        campos["login"] = ent
        cp = ttk.Combobox(topo, width=20, values=[self._nome_pessoa(x) for x in self._pessoas()])
        cp.grid(row=3, column=1, sticky="ew", padx=(12, 0), pady=(4, 0))
        if reg:
            cp.insert(0, self._nome_pessoa(self._pessoa_de(reg)))
        else:
            fp = self.filtro_pessoa.get()
            cp.insert(0, self._nome_pessoa("" if fp == "*" else fp))
        self._dica(cp, "De quem é esta conta. Escolha da lista ou digite um nome novo.")
        if reg:
            campos["servico"].insert(0, reg.get("servico", ""))
            campos["login"].insert(0, reg.get("login", ""))

        # Segredos
        cab_seg = ttk.Frame(fr)
        cab_seg.pack(fill="x", pady=(18, 6))
        ttk.Label(cab_seg, text="  Segredos", image=imagem_icone(self.root, "chave", C["prim_txt"], 16),
                  compound="left", font="CofreForte").pack(side="left")
        mostrar = tk.BooleanVar(value=False)
        ttk.Checkbutton(cab_seg, text="Mostrar", variable=mostrar, style="Switch.TCheckbutton",
                        command=lambda: alternar()).pack(side="right")
        grade = ttk.Frame(fr)
        grade.pack(fill="x")
        grade.columnconfigure(0, weight=1, uniform="s")
        grade.columnconfigure(1, weight=1, uniform="s")
        secretos = []
        dicas_item = PainelForca(fr, self, largura=_px(660), compacto=True)
        for i, chave in enumerate(("senha", "senha_extra", "pin", "chave")):
            col, lin = i % 2, (i // 2) * 3
            px = (0, 10) if col == 0 else (10, 0)
            ttk.Label(grade, text=ROTULOS[chave].upper(), style="Campo.TLabel").grid(row=lin, column=col, sticky="w",
                                                                                   padx=px)
            linha = ttk.Frame(grade)
            linha.grid(row=lin + 1, column=col, sticky="ew", padx=px, pady=(4, 0))
            caixa, ent = self._linha_secreta(linha, 18, olho=False)
            caixa.pack(side="left", fill="x", expand=True)
            if reg:
                ent.insert(0, reg.get(chave, ""))
            campos[chave] = ent
            secretos.append(ent)
            bcp = ttk.Button(linha, text="Copiar", style="Quadrado.TButton", takefocus=0,
                             image=imagem_icone(self.root, "copiar", C["texto"], 18), compound="image")
            bcp.config(command=lambda e=ent, b=bcp, n=ROTULOS[chave]: self._copiar_campo(e, b, n))
            bcp.pack(side="right", fill="y", padx=(6, 0))
            self._dica(bcp, f"Copiar {ROTULOS[chave].lower()} (a área de transferência é limpa em "
                            f"{self.LIMPAR_CLIPBOARD_MS // 1000} s)")
            if chave in ("senha", "senha_extra", "pin"):
                modo_g = "pin" if chave == "pin" else "aleatoria"
                bgr = ttk.Button(linha, text="Gerar…", style="Quadrado.TButton",
                                 image=imagem_icone(self.root, "gerar", C["texto"], 18), compound="image",
                                 command=lambda e=ent, m=modo_g: self.dialogo_gerador(e, m, d))
                bgr.pack(side="left", fill="y", padx=(6, 0))
                self._dica(bgr, "Gerar uma senha forte (escolha o tipo e o tamanho)")
                self._medidor(grade, ent, pin=(chave == "pin"), dicas_lbl=dicas_item,
                              titulo=ROTULOS[chave]).grid(
                    row=lin + 2, column=col, sticky="w", padx=px, pady=(6, 12))
            else:
                ttk.Frame(grade, height=8).grid(row=lin + 2, column=col)
        dicas_item.pack(fill="x", pady=(0, 6))
        campos["senha"].event_generate("<<Atualizar>>")

        ttk.Label(fr, text=ROTULOS["codigos"].upper(), style="Campo.TLabel").pack(anchor="w", pady=(10, 4))
        fc = ttk.Frame(fr)
        fc.pack(fill="x")
        codigos = self._texto_multilinha(fc, 4, mono=True)
        oculto = ttk.Label(fc, text="••••••   (oculto — ligue Mostrar)" if (reg or {}).get("codigos")
                           else "(vazio — ligue Mostrar para preencher)", style="Fraco.TLabel")
        oculto.pack(anchor="w", pady=(2, 0))
        if reg:
            codigos.insert("1.0", reg.get("codigos", ""))

        def alternar():
            s = "" if mostrar.get() else "•"
            for e in secretos:
                e.config(show=s)
            if mostrar.get():
                oculto.pack_forget()
                codigos.pack(fill="x")
            else:
                codigos.pack_forget()
                oculto.pack(anchor="w", pady=(2, 0))

        ttk.Label(fr, text="NOTAS", style="Campo.TLabel").pack(anchor="w", pady=(14, 4))
        notas = self._texto_multilinha(fr, 3)
        notas.pack(fill="x")
        if reg:
            notas.insert("1.0", reg.get("notas", ""))
        protegido = tk.BooleanVar(value=bool((reg or {}).get("protegido")))

        def salvar():
            dados = {k: e.get().strip() if k in ("grupo", "servico", "login") else e.get()
                     for k, e in campos.items()}
            dados["codigos"] = codigos.get("1.0", "end").strip("\n")
            dados["notas"] = notas.get("1.0", "end").rstrip("\n")
            dados["protegido"] = protegido.get()
            dados["pessoa"] = self._valor_pessoa(cp.get())
            if not dados["servico"]:
                messagebox.showerror("Erro", "Informe a conta / app.", parent=d)
                return
            if reg:
                antigo = dict(reg)
                reg.update(dados)
                if not self._salvar():
                    reg.clear()
                    reg.update(antigo)
                    return
            else:
                item = novo_item(**dados)
                item["protegido"] = dados["protegido"]
                self.cofre.registros.append(item)
                if not self._salvar():
                    self.cofre.registros.remove(item)
                    return
            self.atualizar_lista()
            if not reg:
                self.tree.selection_set(item["id"])
            d.destroy()

        ttk.Separator(fr).pack(fill="x", pady=(18, 14))
        rod = ttk.Frame(fr)
        rod.pack(fill="x")
        ttk.Checkbutton(rod, text="Item protegido — pedir a senha mestra para ver, copiar ou imprimir",
                        variable=protegido, style="Switch.TCheckbutton").pack(side="left")
        ttk.Button(rod, text="Salvar", command=salvar, style="Primario.TButton",
                   image=imagem_icone(self.root, "ok", "#ffffff"), compound="left").pack(side="right")
        ttk.Button(rod, text="Cancelar", command=d.destroy).pack(side="right", padx=8)
        campos["servico"].focus_set()


    def _confirmar_senha_atual(self, titulo):
        atual = self._pedir_senha(titulo, "Confirme a senha mestra atual:")
        if atual is None:
            return False
        self._ocupado(True)
        try:
            ok = self.cofre is not None and self.cofre.confere_senha(atual)
        except MemoryError:
            self._ocupado(False)
            messagebox.showerror("Memória insuficiente", "Faltou memória livre para verificar a senha (a blindagem Máxima usa 1 GB). Feche o navegador e outros programas e tente de novo.")
            return False
        self._ocupado(False)
        if not ok:
            messagebox.showerror("Erro", "Senha mestra incorreta.")
        return ok

    def trocar_senha(self):
        if not self._confirmar_senha_atual("Trocar senha"):
            return
        nova = self._pedir_senha("Trocar senha", f"Nova senha (mín. {MIN_SENHA} caracteres):")
        if nova is None:
            return
        problema = avaliar_senha(nova)
        if problema:
            messagebox.showerror("Senha fraca", problema)
            return
        conf = self._pedir_senha("Trocar senha", "Confirme a nova senha:")
        if conf != nova:
            messagebox.showerror("Erro", "As senhas não conferem.")
            return
        self._ocupado(True)
        try:
            self.cofre.trocar_senha(nova)
        except MemoryError:
            self._ocupado(False)
            messagebox.showerror("Memória insuficiente", "Faltou memória livre para trocar a senha. Feche "
                                 "outros programas e tente de novo. A senha antiga continua valendo.")
            return
        except OSError as ex:
            self._ocupado(False)
            messagebox.showerror("Erro", f"Não foi possível gravar o cofre:\n{ex}")
            return
        self._ocupado(False)
        messagebox.showinfo("Pronto", "Senha mestra alterada. A chave de acesso continua a mesma. "
                            "As cópias automáticas antigas foram apagadas. Backups SEUS, feitos antes, "
                            "continuam abrindo com a senha antiga.")

    def nova_chave(self):
        if not messagebox.askyesno("Nova chave de acesso",
                                   "Gerar uma nova chave de acesso?\n\nA chave atual (e arquivos .key "
                                   "antigos) deixarão de abrir este cofre. Backups antigos continuam "
                                   "abrindo com a chave antiga."):
            return
        if not self._confirmar_senha_atual("Nova chave de acesso"):
            return
        try:
            chave = self.cofre.gerar_nova_chave_acesso()
        except OSError as ex:
            messagebox.showerror("Erro", f"Não foi possível gravar o cofre:\n{ex}")
            return
        self.mostrar_chave_acesso(chave, self.cofre.modo)

    # ---------- importação de planilha ----------
    def modelo_planilha(self):
        destino = filedialog.asksaveasfilename(title="Salvar modelo de planilha",
                                               defaultextension=".xlsx",
                                               initialfile="modelo_importacao_cofre.xlsx",
                                               initialdir=os.path.dirname(os.path.abspath(self.caminho)),
                                               filetypes=[("Excel", "*.xlsx")])
        if not destino:
            return
        if not self._confirmar_destino(destino, "a planilha (depois de preenchida ela terá senhas sem proteção)"):
            return
        try:
            criar_modelo_planilha(destino)
        except ImportError:
            messagebox.showerror("Erro", "Falta a biblioteca de Excel. Rode:  pip install openpyxl defusedxml")
            return
        except OSError as ex:
            messagebox.showerror("Erro", f"Não foi possível salvar:\n{ex}")
            return
        messagebox.showinfo("Modelo criado", "Preencha uma linha por conta (Serviço, Login, Senha, PIN, "
                            "Notas), salve e use 'Importar planilha'.\n\nDepois de importar, apague a "
                            "planilha: ela guarda as senhas sem criptografia.")

    def importar(self):
        arq = filedialog.askopenfilename(title="Importar senhas de planilha",
                                         filetypes=[("Planilhas", "*.xlsx *.xlsm *.csv"),
                                                    ("Excel", "*.xlsx *.xlsm"), ("CSV", "*.csv")])
        if not arq:
            return
        self._ocupado(True)
        try:
            novos, avisos = ler_planilha(arq)
        except (ValueError, OSError) as ex:
            self._ocupado(False)
            messagebox.showerror("Importar planilha", str(ex))
            return
        self._ocupado(False)
        if not novos:
            messagebox.showinfo("Importar planilha", "Nenhuma conta encontrada na planilha.\n\n"
                                "Use colunas como Serviço, Login, Senha, PIN e Notas "
                                "(ou baixe o modelo pelo botão 'Modelo de planilha').")
            return
        inserir, iguais, conflitos = classificar_importacao(self.cofre.registros, novos)
        self._previa_importacao(arq, inserir, iguais, conflitos, avisos)

    def _previa_importacao(self, arq, inserir, iguais, conflitos, avisos):
        d = self._nova_janela("Conferir importação")
        d.grab_set()
        d.resizable(True, True)
        fr = ttk.Frame(d, padding=(26, 22, 26, 20))
        fr.pack(fill="both", expand=True)
        resumo = (f"Novas contas: {len(inserir)}    •    Já existem iguais (ignoradas): {len(iguais)}"
                  f"    •    Já existem com dados diferentes: {len(conflitos)}")
        self._cabecalho_dialogo(fr, "importar", "Conferir importação — " + os.path.basename(arq), resumo)
        for a in avisos:
            ttk.Label(fr, text="  " + a, image=imagem_icone(self.root, "alerta", CORES["alerta"], 14), compound="left",
                      foreground=CORES["alerta"], wraplength=760).pack(anchor="w")

        mostrar = tk.BooleanVar(value=False)
        tree = ttk.Treeview(fr, columns=("situacao", "grupo", "servico", "login", "senha", "outros", "notas"),
                            show="headings", height=14)
        for col, txt, larg in (("situacao", "Situação", 120), ("grupo", "Grupo", 110),
                               ("servico", "Conta / App", 170), ("login", "Login", 160),
                               ("senha", "Senha", 110), ("outros", "Também tem", 190),
                               ("notas", "Notas", 150)):
            tree.heading(col, text=txt)
            tree.column(col, width=larg, stretch=(col in ("servico", "notas")))
        tree.pack(fill="both", expand=True, pady=8)

        def oculto(v):
            return v if mostrar.get() else ("•" * min(len(v), 10) if v else "")

        def linha(situacao, r):
            outros = ", ".join(ROTULOS[c] for c in ("senha_extra", "pin", "chave", "codigos") if r.get(c))
            return (situacao, r.get("grupo", ""), r.get("servico", ""), r.get("login", ""),
                    oculto(r.get("senha", "")), outros, r.get("notas", "").replace("\n", " ")[:80])

        def preencher():
            tree.delete(*tree.get_children())
            for r in inserir:
                tree.insert("", "end", values=linha("Nova", r))
            for _, r in conflitos:
                tree.insert("", "end", values=linha("Dados diferentes", r))

        preencher()
        opc = ttk.Frame(fr)
        opc.pack(fill="x")
        ttk.Checkbutton(opc, text="Mostrar senhas", variable=mostrar, command=preencher,
                        style="Switch.TCheckbutton").pack(side="left")
        fp = self.filtro_pessoa.get()
        cbp = ttk.Combobox(opc, width=16, values=[self._nome_pessoa(x) for x in self._pessoas()])
        cbp.insert(0, self._nome_pessoa("" if fp == "*" else fp))
        cbp.pack(side="right")
        ttk.Label(opc, text="Pessoa destas contas:", style="Suave.TLabel").pack(side="right", padx=(0, 8))
        self._dica(cbp, "Contas da planilha sem a coluna Pessoa (ou Dono/Titular) vão para esta pessoa.")
        atualizar = tk.BooleanVar(value=False)
        if conflitos:
            ttk.Checkbutton(opc, text=f"Atualizar as {len(conflitos)} conta(s) que já existem com os "
                                      "dados da planilha", variable=atualizar,
                            style="Switch.TCheckbutton").pack(side="left", padx=20)

        def confirmar():
            backup_regs = [dict(r) for r in self.cofre.registros]
            padrao = self._valor_pessoa(cbp.get())
            for r in inserir:
                item = novo_item(**{k: r.get(k, "") for k in CAMPOS})
                if not item.get("pessoa"):
                    item["pessoa"] = padrao
                else:
                    item["pessoa"] = self._valor_pessoa(item["pessoa"])
                self.cofre.registros.append(item)
            n_atual = 0
            if atualizar.get():
                for atual, r in conflitos:
                    for c in CAMPOS_SECRETOS + ("notas", "grupo"):
                        if r.get(c):
                            atual[c] = r[c]
                    n_atual += 1
            if not self._salvar():
                self.cofre.registros[:] = backup_regs
                return
            d.destroy()
            self.atualizar_lista()
            self.status.config(text=f"Importadas {len(inserir)} conta(s); atualizadas {n_atual}.")
            self._oferecer_apagar_planilha(arq)

        bt = ttk.Frame(fr)
        bt.pack(fill="x", pady=(14, 0))
        b_ok = ttk.Button(bt, text="Importar", command=confirmar, style="Primario.TButton",
                          image=imagem_icone(self.root, "importar", "#ffffff"), compound="left")
        b_ok.pack(side="right")
        ttk.Button(bt, text="Cancelar", command=d.destroy).pack(side="right", padx=8)
        if not inserir and not conflitos:
            b_ok.config(state="disabled")
            ttk.Label(bt, text="Todas as contas da planilha já estão no cofre.").pack(side="left")
        self.root.wait_window(d)

    def _oferecer_apagar_planilha(self, arq):
        texto = ("Importação concluída.\n\nA planilha original guarda as senhas SEM criptografia. "
                 "Deseja apagá-la com segurança agora? (o arquivo é sobrescrito com dados "
                 "aleatórios e excluído — não vai para a Lixeira)\n\n"
                 "Feche a planilha no Excel antes de confirmar.")
        if not messagebox.askyesno("Apagar planilha?", texto):
            messagebox.showinfo("Lembrete", "Lembre de apagar a planilha e esvaziar a Lixeira quando "
                                "terminar de conferir.")
            return
        try:
            destruir(arq)
        except OSError as ex:
            messagebox.showerror("Erro", f"Não foi possível apagar (o arquivo está aberto no Excel?).\n{ex}")
            return
        extra = ""
        if re.search(r"(?i)onedrive|google drive|dropbox", arq):
            extra = ("\n\nATENÇÃO: o arquivo estava numa pasta sincronizada com a nuvem. Apague-o também "
                     "na Lixeira/histórico de versões do site da nuvem.")
        messagebox.showinfo("Planilha apagada", "A planilha foi sobrescrita e apagada." + extra +
                            "\n\nSe existirem outras cópias (e-mail, Downloads, pendrive), apague-as também.")

    # ---------- força da senha / gerador / verificação ----------
    _CORES_FORCA = ("#f26b6b", "#f5914e", "#f5b544", "#3dd68c", "#2fbf71")

    @staticmethod
    def _veredito(nota):
        if nota >= 3:
            return "Ótima senha!", CORES["ok"]
        if nota == 2:
            return "Hora de mudar de senha!", CORES["alerta"]
        return "Já passou da hora de trocar sua senha!", CORES["perigo"]

    @staticmethod
    def _pintar(texto_widget, senha):
        """Mostra a senha grande e colorida: letras claras, números azuis, símbolos rosa."""
        texto_widget.config(state="normal")
        texto_widget.delete("1.0", "end")
        for ch in senha:
            tag = "num" if ch.isdigit() else ("let" if ch.isalpha() else "sim")
            texto_widget.insert("end", ch, (tag, "centro"))
        texto_widget.config(state="disabled")

    def _novo_texto_senha(self, mestre, fundo=None):
        fundo = fundo or CORES["sup2"]
        t = tk.Text(mestre, height=2, width=30, font=(FONTES["CofreMono"].cget("family"), 18), relief="flat", bd=0,
                    wrap="char", exportselection=False, cursor="arrow", padx=6, pady=6,
                    highlightthickness=0, bg=fundo, fg=CORES["texto"], insertbackground=fundo,
                    selectbackground=fundo, inactiveselectbackground=fundo)
        t.tag_configure("let", foreground=CORES["texto"])
        t.tag_configure("num", foreground=CORES["num"])
        t.tag_configure("sim", foreground=CORES["sim"])
        t.tag_configure("centro", justify="center", spacing1=2)
        self._bloquear_copia(t)
        return t

    def _cabecalho_dialogo(self, pai, icone, titulo, subtitulo=None, cor=None):
        """Ícone num quadrado colorido + título e subtítulo (padrão de todas as janelas)."""
        C = CORES
        topo = ttk.Frame(pai)
        topo.pack(fill="x", pady=(0, 16))
        n = _px(40)
        cv = tk.Canvas(topo, width=n, height=n, bg=C["fundo"], highlightthickness=0)
        fundo = {"perigo": C["perigo_fundo"], "alerta": C["alerta_fundo"], "ok": C["ok_fundo"]}.get(cor, C["prim_fundo"])
        cv._a = imagem_nove_fatias(cv, *peca_cartao(fundo, None, 12), n, n)
        cv._b = imagem_icone(cv, icone, C.get(cor, C["prim_txt"]) if cor else C["prim_txt"], 20)
        cv.create_image(n // 2, n // 2, image=cv._a)
        cv.create_image(n // 2, n // 2, image=cv._b)
        cv.pack(side="left", anchor="n", padx=(0, 14))
        tx = ttk.Frame(topo)
        tx.pack(side="left", fill="x", expand=True)
        ttk.Label(tx, text=titulo, style="H2.TLabel").pack(anchor="w")
        if subtitulo:
            ttk.Label(tx, text=subtitulo, style="Suave.TLabel", wraplength=480, justify="left").pack(anchor="w")
        return topo

    def dialogo_gerador(self, alvo=None, modo_inicial="aleatoria", mestre=None, senha_mestra=False, extra=None):
        """Gerador de senhas local (estilo 1Password) + verificador (estilo Kaspersky).
        Se 'alvo' for informado, o botão 'Usar esta senha' preenche o campo (e 'extra', se houver)."""
        import math
        C = CORES
        d = self._nova_janela("Gerador de senhas", mestre)
        d.grab_set()
        cartao = self._corpo_rolavel(d, (26, 22, 26, 22))
        self._cabecalho_dialogo(cartao, "gerar", "Gerador de senhas",
                                "Gerado neste computador com o sorteio criptográfico do sistema. Nada vai para a internet.")

        tipo = tk.StringVar(value=modo_inicial)
        seg = ttk.Frame(cartao, style="Card2.TFrame", padding=4)
        seg.pack(fill="x")
        for chave, texto, ic in (("aleatoria", "Aleatória", "gerar"), ("frase", "Fácil de lembrar", "pessoa"),
                                 ("pin", "PIN", "teclado")):
            ttk.Radiobutton(seg, text=" " + texto, value=chave, variable=tipo, style="S2.Segmento.Toolbutton",
                            image=imagem_icone(self.root, ic, C["suave"], 16), compound="left",
                            command=lambda: montar_opcoes()).pack(side="left", expand=True, fill="x", padx=1)

        # Senha gerada (grande e colorida)
        caixa_fr = ttk.Frame(cartao, style="Card2.TFrame", padding=(12, 10))
        caixa_fr.pack(fill="x", pady=(16, 0))
        caixa = self._novo_texto_senha(caixa_fr)
        caixa.pack(fill="x")
        atual = {"s": ""}
        lv = ttk.Frame(cartao)
        lv.pack(fill="x", pady=(10, 0))
        barra_lbl = ttk.Label(lv)
        barra_lbl.pack(side="left")
        veredito = ttk.Label(lv, text="", font="CofreForte")
        veredito.pack(side="left", padx=(10, 0))
        bits_lbl = ttk.Label(lv, text="", style="Fraco.TLabel")
        bits_lbl.pack(side="right")

        # Personalização
        ttk.Separator(cartao).pack(fill="x", pady=14)
        linha_tam = ttk.Frame(cartao)
        linha_tam.pack(fill="x")
        rot_tam = ttk.Label(linha_tam, text="CARACTERES", style="Campo.TLabel", width=12)
        rot_tam.pack(side="left")
        tamanho = tk.IntVar(value=20)          # valor do controle deslizante
        texto_tam = tk.StringVar(value="20")   # caixa numérica (pode ficar vazia enquanto se digita)

        def do_deslizante(v):
            n = int(round(float(v)))
            if tamanho.get() != n:
                tamanho.set(n)
            texto_tam.set(str(n))
            gerar()

        def da_caixa(event=None):
            try:
                n = int(texto_tam.get())
            except ValueError:
                return                          # caixa vazia ou digitação incompleta: espera
            lo, hi = int(float(escala.cget("from"))), int(float(escala.cget("to")))
            if lo <= n <= hi:
                tamanho.set(n)
                gerar()

        escala = ttk.Scale(linha_tam, from_=8, to=64, orient="horizontal", variable=tamanho, length=280,
                           command=do_deslizante)
        escala.pack(side="left", padx=(4, 12), fill="x", expand=True)
        caixa_tam = ttk.Spinbox(linha_tam, from_=8, to=64, textvariable=texto_tam, width=4, command=da_caixa)
        caixa_tam.pack(side="left")
        caixa_tam.bind("<KeyRelease>", da_caixa)
        caixa_tam.bind("<FocusOut>", lambda e: texto_tam.set(str(tamanho.get())))
        opc = ttk.Frame(cartao)
        opc.pack(fill="x", pady=(10, 0))
        numeros, simbolos = tk.BooleanVar(value=True), tk.BooleanVar(value=True)
        maiusc, num_fim = tk.BooleanVar(value=True), tk.BooleanVar(value=True)
        info = PainelForca(cartao, self, largura=_px(540))
        info.pack(fill="x", pady=(12, 0))
        if senha_mestra:
            av = ttk.Frame(cartao, style="Card2.TFrame", padding=(12, 10))
            av.pack(fill="x", pady=(12, 0))
            ttk.Label(av, text="  ESTA SERÁ A SENHA MESTRA: decore ou anote em papel AGORA, antes de clicar em "
                               "'Usar esta senha'. Ela não será mostrada de novo e não há como recuperá-la.",
                      image=imagem_icone(self.root, "alerta", C["alerta"], 16), compound="left",
                      style="S2.TLabel", foreground=C["alerta"], wraplength=470, justify="left").pack(fill="x")

        def montar_opcoes():
            for w in opc.winfo_children():
                w.destroy()
            t = tipo.get()
            if t == "aleatoria":
                rot_tam.config(text="CARACTERES")
                escala.config(from_=8, to=64)
                caixa_tam.config(from_=8, to=64)
                tamanho.set(20)
                texto_tam.set("20")
                for texto, var in (("Números", numeros), ("Símbolos", simbolos)):
                    ttk.Checkbutton(opc, text=texto, variable=var, command=gerar,
                                    style="Switch.TCheckbutton").pack(side="left", padx=(0, 24))
            elif t == "frase":
                rot_tam.config(text="PALAVRAS")
                escala.config(from_=3, to=10)
                caixa_tam.config(from_=3, to=10)
                tamanho.set(5)
                texto_tam.set("5")
                for texto, var in (("Primeira letra maiúscula", maiusc), ("Número no final", num_fim)):
                    ttk.Checkbutton(opc, text=texto, variable=var, command=gerar,
                                    style="Switch.TCheckbutton").pack(side="left", padx=(0, 24))
            else:
                rot_tam.config(text="DÍGITOS")
                escala.config(from_=4, to=12)
                caixa_tam.config(from_=4, to=12)
                tamanho.set(6)
                texto_tam.set("6")
                ttk.Label(opc, text="Sem sequências (1234), repetições (0000) ou anos.",
                          style="Suave.TLabel").pack(side="left")
            gerar()

        def gerar(*a):
            t = tipo.get()
            try:
                n = int(round(float(tamanho.get())))
            except (tk.TclError, ValueError):
                return
            lim = {"aleatoria": (8, 64), "frase": (3, 10), "pin": (4, 12)}[t]
            n = max(lim[0], min(n, lim[1]))
            if t == "aleatoria":
                s = gerar_senha(n, numeros.get(), simbolos.get())
                bits = n * math.log2(52 + (10 if numeros.get() else 0) + (12 if simbolos.get() else 0))
                uso = "Ideal para contas de sites e apps: você não precisa decorar, ela fica no cofre."
            elif t == "frase":
                s = gerar_frase(n, maiusc.get(), num_fim.get())
                bits = bits_frase(n, num_fim.get())
                uso = "Fácil de lembrar e de digitar. Boa para senhas que você precisa decorar."
            else:
                s = gerar_pin(n)
                bits = n * math.log2(10)
                uso = "PIN aleatório."
            atual["s"] = s
            self._pintar(caixa, s)
            nota = 4 if bits >= 80 else 3 if bits >= 60 else 2 if bits >= 40 else 1
            if t == "pin":
                barra_lbl.config(image=self._barra_forca(3, 96))
                veredito.config(text=f"PIN aleatório de {n} dígitos", foreground=C["ok"])
                bits_lbl.config(text=f"{10 ** n:,} combinações".replace(",", "."))
                info._limpar()
                info._texto = "PIN aleatório."
                info._cartao()
                info._linha(info, "info", C["suave"], "A segurança de um PIN vem do limite de tentativas do banco "
                            "ou do aparelho (geralmente 3 erros bloqueiam).").pack_configure(pady=0)
                return
            txt, cor = self._veredito(nota)
            barra_lbl.config(image=self._barra_forca(nota, 96))
            veredito.config(text=txt, foreground=cor)
            bits_lbl.config(text=f"~{int(bits)} bits")
            info.mostrar_gerada(s, bits, nota, txt, uso)

        botoes = ttk.Frame(cartao)
        botoes.pack(fill="x", pady=(18, 0))
        msg = ttk.Label(cartao, text="", style="Suave.TLabel")

        def copiar():
            msg.config(text=self._copiar_texto(atual["s"], "Senha"))

        def usar():
            try:
                for campo in (alvo, extra):
                    if campo is not None:
                        campo.delete(0, "end")
                        campo.insert(0, atual["s"])
                        campo.event_generate("<<Atualizar>>")
            except tk.TclError:
                pass
            d.destroy()

        if alvo is not None:
            ttk.Button(botoes, text="Usar esta senha", command=usar, style="Primario.TButton",
                       image=imagem_icone(self.root, "ok", "#ffffff"), compound="left").pack(side="right")
            bcg = ttk.Button(botoes, text=" Copiar", style="Acao.TButton",
                             image=imagem_icone(self.root, "copiar", C["texto"]), compound="left")
            bcg.config(command=lambda: (copiar(), self._copiado(bcg)))
            bcg.pack(side="right", padx=(8, 0))
        else:
            ttk.Button(botoes, text="Copiar senha", command=copiar, style="Primario.TButton",
                       image=imagem_icone(self.root, "copiar", "#ffffff"), compound="left").pack(side="right")
        ttk.Button(botoes, text="Atualizar senha", command=gerar, style="Acao.TButton",
                   image=imagem_icone(self.root, "atualizar", C["texto"]), compound="left").pack(side="right", padx=8)
        msg.pack(fill="x", pady=(8, 0))

        # ---- verificador (estilo Kaspersky), só quando aberto sozinho ----
        if alvo is None:
            ttk.Separator(cartao).pack(fill="x", pady=(12, 14))
            ttk.Label(cartao, text="Teste sua senha", style="H2.TLabel").pack(anchor="w")
            ttk.Label(cartao, text="A verificação é feita só neste computador. Nada é enviado pela internet nem "
                                   "guardado.", style="Suave.TLabel", wraplength=500).pack(anchor="w")
            lin = ttk.Frame(cartao)
            lin.pack(fill="x", pady=(8, 6))
            teste = self._campo_secreto(lin, 40)
            teste.pack(side="left", fill="x", expand=True)
            ver = tk.BooleanVar(value=False)
            ttk.Checkbutton(lin, text="Mostrar", variable=ver, style="Switch.TCheckbutton",
                            command=lambda: teste.config(show="" if ver.get() else "•")).pack(side="left", padx=(12, 0))
            lv2 = ttk.Frame(cartao)
            lv2.pack(fill="x")
            b2 = ttk.Label(lv2)
            b2.pack(side="left")
            v2 = ttk.Label(lv2, text="", font="CofreForte")
            v2.pack(side="left", padx=(10, 0))
            i2 = PainelForca(cartao, self, largura=_px(540))
            i2.pack(fill="x", pady=(6, 0))

            def testar(event=None):
                s = teste.get()
                if not s:
                    v2.config(text="")
                    b2.config(image="")
                    i2.mostrar("")
                    return
                nota, rot, texto = relatorio_forca(s)
                t_, cor = self._veredito(nota)
                b2.config(image=self._barra_forca(nota, 96))
                v2.config(text=t_, foreground=cor)
                i2.mostrar(s)

            teste.bind("<KeyRelease>", testar, add="+")
            teste.bind("<<Atualizar>>", testar, add="+")

        montar_opcoes()
        self.root.wait_window(d)


    def verificar_senhas(self):
        achados = auditar_cofre(self.cofre.registros)
        d = self._nova_janela("Verificação das senhas")
        d.grab_set()
        d.resizable(True, True)
        fr = ttk.Frame(d, padding=(26, 22, 26, 20))
        fr.pack(fill="both", expand=True)
        rep = sum(1 for a in achados if a[2] == "Senha REPETIDA")
        fracas = sum(1 for a in achados if a[4] == 1)
        if not achados:
            self._cabecalho_dialogo(fr, "verificar", "Tudo certo!",
                                    "Nenhum problema encontrado: todas as senhas são fortes e únicas.", "ok")
        else:
            self._cabecalho_dialogo(fr, "verificar", f"{len(achados)} ponto(s) de atenção",
                                    f"Repetidas: {rep}   •   fracas ou PIN óbvio: {fracas}   •   razoáveis: "
                                    f"{len(achados) - rep - fracas}\nDê dois cliques em uma linha para abrir o item "
                                    "e trocar a senha (botão Gerar).", "alerta")
        tree = ttk.Treeview(fr, columns=("conta", "campo", "problema", "rec"), show="headings", height=14)
        for col, txt, larg in (("conta", "Conta / App", 170), ("campo", "Campo", 90),
                               ("problema", "Problema", 170), ("rec", "Recomendação", 420)):
            tree.heading(col, text=txt)
            tree.column(col, width=larg, stretch=(col == "rec"))
        tree.tag_configure("g0", foreground=CORES["perigo"])
        tree.tag_configure("g1", foreground="#f5914e")
        tree.tag_configure("g2", foreground=CORES["alerta"])
        mapa = {}
        for i, (r, campo, prob, recom, grav) in enumerate(achados):
            iid = str(i)
            mapa[iid] = r
            tree.insert("", "end", iid=iid, tags=(f"g{grav}",),
                        values=(r.get("servico", ""), ROTULOS[campo], prob, recom))
        tree.pack(fill="both", expand=True)

        def abrir(event=None):
            sel = tree.selection()
            if sel:
                d.destroy()
                if self._liberar_protegido(mapa[sel[0]]):
                    self.dialogo_registro(mapa[sel[0]])

        tree.bind("<Double-1>", abrir)
        ttk.Button(fr, text="Fechar", command=d.destroy, style="Primario.TButton").pack(anchor="e", pady=(14, 0))

    # ---------- impressão ----------
    def _imprimir(self, titulo, campos, mestre=None):
        """Imprime direto na impressora, sem criar arquivo. Avisa se a 'impressora' gera arquivo (PDF etc.)."""
        janela = mestre or self.root
        try:
            esc = escolher_impressora(_hwnd(janela))
        except ImpressaoErro as ex:
            messagebox.showerror("Imprimir", str(ex), parent=janela)
            return False
        if esc is None:
            return False
        hdc, nome, porta = esc
        if impressora_gera_arquivo(nome, porta):
            if not messagebox.askyesno(
                    "ATENÇÃO — não é uma impressora de papel",
                    f'"{nome}" cria um ARQUIVO (PDF/XPS/etc.) com as senhas SEM criptografia.\n\n'
                    "O recomendado é imprimir em uma impressora de verdade.\n\nContinuar mesmo assim?",
                    parent=janela):
                from ctypes import wintypes as _wt
                _g = ctypes.windll.gdi32
                _g.DeleteDC.argtypes = [_wt.HDC]
                _g.DeleteDC(hdc)
                return False
        try:
            imprimir_linhas(hdc, linhas_impressao(titulo, campos))
        except (ImpressaoErro, OSError) as ex:
            messagebox.showerror("Imprimir", f"Falha ao imprimir:\n{ex}", parent=janela)
            return False
        messagebox.showinfo("Imprimir", "Enviado para a impressora.\n\nPegue a folha IMEDIATAMENTE e guarde em "
                            "local seguro. Não deixe na bandeja da impressora.", parent=janela)
        return True

    def imprimir_item(self):
        r = self._selecionado()
        if not r:
            return
        disponiveis = [c for c in ("login",) + CAMPOS_SECRETOS + ("notas",) if r.get(c)]
        if not disponiveis:
            messagebox.showinfo("Imprimir", "Este item não tem dados para imprimir.")
            return
        d = self._nova_janela("Imprimir item")
        d.grab_set()
        fr = ttk.Frame(d, padding=15)
        fr.pack(fill="both", expand=True)
        ttk.Label(fr, text=f'Imprimir "{r.get("servico", "")}"', font="CofreSub").pack(anchor="w")
        ttk.Label(fr, text="Escolha o que vai na folha:").pack(anchor="w", pady=(6, 4))
        marc = {}
        for c in disponiveis:
            marc[c] = tk.BooleanVar(value=True)
            ttk.Checkbutton(fr, text=ROTULOS[c], variable=marc[c]).pack(anchor="w")
        ttk.Label(fr, text="A senha mestra será pedida antes de imprimir.", foreground=CORES["suave"]).pack(anchor="w", pady=(8, 0))
        ok = {"v": False}

        def confirmar():
            ok["v"] = True
            d.destroy()

        bt = ttk.Frame(fr)
        bt.pack(fill="x", pady=(12, 0))
        ttk.Button(bt, text="Cancelar", command=d.destroy).pack(side="right")
        ttk.Button(bt, text="Imprimir…", command=confirmar).pack(side="right", padx=5)
        self.root.wait_window(d)
        escolhidos = [c for c in disponiveis if marc[c].get()]
        if not ok["v"] or not escolhidos:
            return
        if not self._confirmar_senha_atual("Imprimir"):
            return
        campos = [(ROTULOS["servico"], r.get("servico", ""))]
        if r.get("grupo"):
            campos.append((ROTULOS["grupo"], r["grupo"]))
        campos += [(ROTULOS[c], r[c]) for c in escolhidos]
        self._imprimir("COFRE DE SENHAS — CONFIDENCIAL", campos)

    # ---------- tarefas demoradas sem travar a janela ----------
    def _em_segundo_plano(self, funcao, ao_terminar):
        resultado = {}

        def alvo():
            try:
                resultado["v"] = funcao()
            except BaseException as ex:          # repassa qualquer erro para a janela tratar
                resultado["e"] = ex

        th = threading.Thread(target=alvo, daemon=True)
        th.start()

        def checar():
            if th.is_alive():
                self.root.after(100, checar)
            else:
                ao_terminar(resultado.get("v"), resultado.get("e"))

        self.root.after(100, checar)

    def _pedir_texto(self, titulo, texto, inicial=""):
        d = self._nova_janela(titulo)
        d.grab_set()
        res = {"v": None}
        fr = ttk.Frame(d, padding=(26, 22, 26, 20))
        fr.pack()
        self._cabecalho_dialogo(fr, "editar", titulo, texto)
        e = ttk.Entry(fr, width=40)
        e.insert(0, inicial)
        e.pack(fill="x")

        def ok(event=None):
            res["v"] = e.get().strip()
            d.destroy()

        e.bind("<Return>", ok)
        bt = ttk.Frame(fr)
        bt.pack(fill="x", pady=(18, 0))
        ttk.Button(bt, text="OK", command=ok, style="Primario.TButton").pack(side="right")
        ttk.Button(bt, text="Cancelar", command=d.destroy).pack(side="right", padx=8)
        e.focus_set()
        e.select_range(0, "end")
        self.root.wait_window(d)
        return res["v"]

    def mostrar_codigo_recuperacao(self, codigo):
        """Mostra o código de recuperação e só confirma se o usuário redigitar o último bloco."""
        d = self._nova_janela("Código de recuperação da chave FIDO")
        d.grab_set()
        ok = {"v": False}
        fr = ttk.Frame(d, padding=(26, 22, 26, 20))
        fr.pack(fill="both", expand=True)
        self._cabecalho_dialogo(fr, "chave", "Código de recuperação",
                                "Para emergências: substitui a chave FIDO se você perder todas.", "alerta")
        caixa_av = ttk.Frame(fr, style="Card2.TFrame", padding=(14, 12))
        caixa_av.pack(fill="x", pady=(0, 14))
        ttk.Label(caixa_av, style="S2.TLabel", text="Use este código SOMENTE se perder TODAS as chaves FIDO. Ele substitui a chave FIDO "
                           "(a senha mestra e a chave de acesso continuam sendo exigidas).\n"
                           "• Anote em PAPEL e guarde em local seguro (gaveta trancada, cofre físico).\n"
                           "• NÃO guarde no celular, no computador, em foto ou na nuvem.\n"
                           "• Ele aparece só agora.",
                  foreground=CORES["alerta"], justify="left", wraplength=520).pack(anchor="w")
        var = tk.StringVar(value=codigo)
        ent = ttk.Entry(fr, textvariable=var, width=40, font="CofreMonoG", state="readonly",
                        exportselection=False)
        self._bloquear_copia(ent)
        ent.pack(fill="x")
        ttk.Label(fr, text="Para confirmar que anotou, digite o ÚLTIMO bloco de 4 caracteres:").pack(
            anchor="w", pady=(14, 4))
        conf = ttk.Entry(fr, width=10, font="CofreMono")
        conf.pack(anchor="w")
        msg = ttk.Label(fr, text="", foreground=CORES["perigo"])
        msg.pack(anchor="w", pady=(4, 0))

        def confirmar(event=None):
            if conf.get().strip().upper() == codigo.split("-")[-1]:
                ok["v"] = True
                d.destroy()
            else:
                msg.config(text="Não confere. Confira o que você anotou.")

        conf.bind("<Return>", confirmar)
        bt = ttk.Frame(fr)
        bt.pack(fill="x", pady=(14, 0))
        ttk.Button(bt, text="Imprimir…", command=lambda: self._imprimir(
            "COFRE DE SENHAS — CÓDIGO DE RECUPERAÇÃO FIDO", [("Código", codigo)], d)).pack(side="left")
        ttk.Button(bt, text="Já anotei — confirmar", command=confirmar, style="Primario.TButton").pack(side="right")
        ttk.Button(bt, text="Cancelar (não altera o cofre)", command=d.destroy).pack(side="right", padx=8)
        conf.focus_set()
        self.root.wait_window(d)
        return ok["v"]

    # ---------- chaves FIDO ----------
    def gerenciar_fido(self):
        d = self._nova_janela("Chaves FIDO")
        d.grab_set()
        fr = ttk.Frame(d, padding=(26, 22, 26, 20))
        fr.pack(fill="both", expand=True)
        self._cabecalho_dialogo(fr, "chave", "Chaves FIDO",
                                "Chaves de segurança físicas (YubiKey, Feitian, Titan...) como proteção extra.")
        estado = ttk.Label(fr, text="", wraplength=560, justify="left")
        estado.pack(anchor="w", pady=(4, 8))
        lista = ttk.Treeview(fr, columns=("nome",), show="headings", height=6, selectmode="browse")
        lista.heading("nome", text="Chaves cadastradas")
        lista.column("nome", width=520)
        lista.pack(fill="x")

        def atualizar():
            lista.delete(*lista.get_children())
            if self.cofre.fido:
                for i, ch in enumerate(self.cofre.fido["chaves"]):
                    lista.insert("", "end", iid=str(i), values=(ch["nome"],))
                n = len(self.cofre.fido["chaves"])
                estado.config(foreground=CORES["ok"], text=(
                    f"FIDO ATIVO: o cofre só abre com a senha/chave de acesso + uma das {n} chave(s) FIDO abaixo "
                    "(ou o código de recuperação)." + ("\n⚠ Cadastre uma SEGUNDA chave (reserva) para não "
                                                       "depender de uma só." if n == 1 else "")))
            else:
                estado.config(foreground=CORES["suave"], text=(
                    "FIDO desativado. Ao adicionar a primeira chave, o cofre passa a exigir também a chave "
                    "física para abrir, e você recebe um código de recuperação para emergências.\n"
                    "Serve quase qualquer chave de segurança FIDO2 atual: Yubico Security Key NFC (preta ou "
                    "azul), YubiKey 5, Feitian ePass FIDO2... Chave nova vem sem PIN: o Windows pede para "
                    "criar um no primeiro uso (ou em Configurações > Contas > Opções de entrada > "
                    "Chave de segurança > Gerenciar)."))
            for b in (b_rem, b_rec, b_des):
                b.config(state="normal" if self.cofre.fido else "disabled")
            self._atualizar_indicadores()

        def adicionar():
            if not self._confirmar_senha_atual("Adicionar chave FIDO"):
                return
            n = len(self.cofre.fido["chaves"]) if self.cofre.fido else 0
            nome = self._pedir_texto("Nome da chave", "Dê um nome para identificar esta chave:",
                                     "Chave principal" if n == 0 else "Chave reserva")
            if nome is None:
                return
            messagebox.showinfo("Cadastrar chave FIDO",
                                "Conecte a chave FIDO.\n\nO Windows vai pedir para TOCAR na chave 3 vezes "
                                "(e o PIN dela): 1 para cadastrar e 2 para conferir que ela responde sempre "
                                "igual.\n\nO cofre só é alterado se tudo der certo.", parent=d)
            salt = self.cofre.salt_fido()
            hwnd = _hwnd(d)
            estado.config(foreground=CORES["prim_txt"], text="Aguardando a chave FIDO... siga as janelas do Windows.")
            self._ocupado(True)
            self._em_segundo_plano(lambda: fido_cadastrar_e_testar(hwnd, salt, nome),
                                   lambda v, e: concluir_adicao(nome, v, e))

        def concluir_adicao(nome, valor, erro):
            self._ocupado(False)
            if erro is not None:
                atualizar()
                messagebox.showerror("Chave FIDO", str(erro) if isinstance(erro, FidoErro)
                                     else f"Erro inesperado: {erro}", parent=d)
                return
            cred, saida = valor
            anterior = self.cofre.estado_fido()
            try:
                codigo = self.cofre.adicionar_fido(nome, cred, saida)
            except ValueError as ex:
                self.cofre.restaurar_fido(anterior)
                messagebox.showerror("Chave FIDO", str(ex), parent=d)
                atualizar()
                return
            if codigo and not self.mostrar_codigo_recuperacao(codigo):
                self.cofre.restaurar_fido(anterior)
                messagebox.showinfo("Chave FIDO", "Cancelado. O cofre não foi alterado.", parent=d)
                atualizar()
                return
            if not self._salvar():
                self.cofre.restaurar_fido(anterior)
                atualizar()
                return
            atualizar()
            extra = ("\n\nIMPORTANTE: backups feitos ANTES de hoje continuam abrindo sem a chave FIDO. "
                     "Faça um backup novo e guarde/apague os antigos com cuidado." if codigo else "")
            messagebox.showinfo("Chave FIDO", f'Chave "{nome}" cadastrada com sucesso.' + extra, parent=d)

        def remover():
            sel = lista.selection()
            if not sel:
                messagebox.showinfo("Chaves FIDO", "Selecione a chave a remover.", parent=d)
                return
            ch = self.cofre.fido["chaves"][int(sel[0])]
            if not messagebox.askyesno("Remover chave", f'Remover a chave "{ch["nome"]}" deste cofre?\n\n'
                                       "Ela deixará de abrir o cofre.", parent=d):
                return
            if not self._confirmar_senha_atual("Remover chave FIDO"):
                return
            anterior = self.cofre.estado_fido()
            try:
                self.cofre.remover_fido(ch["cred"])
            except ValueError as ex:
                messagebox.showerror("Chaves FIDO", str(ex), parent=d)
                return
            if not self._salvar():
                self.cofre.restaurar_fido(anterior)
            atualizar()

        def novo_codigo():
            if not messagebox.askyesno("Novo código de recuperação", "Gerar um novo código de recuperação?\n\n"
                                       "O código antigo deixa de funcionar.", parent=d):
                return
            if not self._confirmar_senha_atual("Novo código de recuperação"):
                return
            anterior = self.cofre.estado_fido()
            codigo = self.cofre.novo_codigo_recuperacao()
            if not self.mostrar_codigo_recuperacao(codigo):
                self.cofre.restaurar_fido(anterior)
                return
            if not self._salvar():
                self.cofre.restaurar_fido(anterior)
            atualizar()

        def desativar():
            if not messagebox.askyesno("Desativar FIDO", "Desativar a exigência de chave FIDO?\n\nO cofre volta "
                                       "a abrir só com a senha/chave de acesso. Todas as chaves FIDO e o código "
                                       "de recuperação deixam de valer.", parent=d):
                return
            if not self._confirmar_senha_atual("Desativar FIDO"):
                return
            anterior = self.cofre.estado_fido()
            self.cofre.desativar_fido()
            if not self._salvar():
                self.cofre.restaurar_fido(anterior)
            atualizar()

        bt = ttk.Frame(fr)
        bt.pack(fill="x", pady=(14, 0))
        ttk.Button(bt, text="Adicionar chave…", command=adicionar, style="Primario.TButton",
                   image=imagem_icone(self.root, "novo", "#ffffff"), compound="left").pack(side="left")
        b_rem = ttk.Button(bt, text="Remover selecionada", command=remover)
        b_rem.pack(side="left", padx=8)
        b_rec = ttk.Button(bt, text="Novo código de recuperação", command=novo_codigo)
        b_rec.pack(side="left")
        b_des = ttk.Button(bt, text="Desativar FIDO", command=desativar, style="Perigo.TButton")
        b_des.pack(side="left", padx=8)
        ttk.Button(bt, text="Fechar", command=d.destroy).pack(side="right")
        atualizar()

    def backup(self):
        destino = filedialog.asksaveasfilename(title="Salvar backup do cofre",
                                               defaultextension=".dat",
                                               initialfile="cofre_backup.dat",
                                               initialdir=os.path.dirname(os.path.abspath(self.caminho)),
                                               filetypes=[("Cofre", "*.dat")])
        if not destino:
            return
        if not self._confirmar_destino(destino, "o backup do cofre"):
            return
        try:
            shutil.copy2(self.caminho, destino)
            messagebox.showinfo("Backup", "Backup salvo (o arquivo continua criptografado).")
        except OSError as ex:
            messagebox.showerror("Erro", f"Falha no backup:\n{ex}")

    def bloquear(self):
        self._mostrar_conteudo()
        self._liberado_em = {}
        if self._timer_bloqueio:
            self.root.after_cancel(self._timer_bloqueio)
            self._timer_bloqueio = None
        if self.cofre:
            self.cofre.fechar()
            self.cofre = None
        for w in self.root.winfo_children():
            if isinstance(w, tk.Toplevel):
                w.destroy()
        if self._clip_valor is not None:
            self._limpar_clip()
        self.tela_desbloqueio()

    def sair(self):
        if getattr(self, "_trabalhando", False) and not messagebox.askyesno(
                "Verificando a senha",
                "O cofre ainda está verificando a senha. Fechar agora GASTA uma tentativa.\n\nFechar mesmo assim?"):
            return
        if self.cofre:
            self.cofre.fechar()
        self._limpar_clip(forcar=True)
        self.root.destroy()


def main():
    if tk is None:
        _aviso_fatal("Cofre de Senhas", "Tkinter não encontrado.\n\nInstale o Python oficial de python.org "
                     "(ele já vem com Tkinter).")
        sys.exit(1)
    caminho = sys.argv[1] if len(sys.argv) > 1 else os.path.join(pasta_base(), ARQUIVO_PADRAO)
    blindar_processo()
    if EH_WINDOWS:
        try:                                          # nitidez em telas com 125%, 150%...
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
    root = tk.Tk()
    suspeita = ambiente_suspeito()
    if suspeita:
        # Depurador ligado: recusa abrir. Não destrói (antivírus e ferramentas legítimas também se anexam).
        root.withdraw()
        messagebox.showerror("Depurador detectado",
                             f"{suspeita}\n\nPor segurança o cofre não abre enquanto houver um depurador "
                             "ligado. O arquivo NÃO foi alterado. Feche o programa que se anexou a ele "
                             "e abra o cofre de novo.")
        root.destroy()
        sys.exit(2)
    nomes = processos_abertos()
    espias = ferramentas_espias(nomes)
    if espias:
        root.withdraw()
        messagebox.showerror("Ferramenta espiã aberta",
                             "Há um programa capaz de ler a memória de outros programas aberto:\n\n"
                             f"    {', '.join(espias)}\n\n"
                             "Feche-o e abra o cofre de novo. (O cofre NÃO foi alterado.)")
        root.destroy()
        sys.exit(4)
    remotos = acesso_remoto_aberto(nomes)
    if sessao_remota() or remotos:
        root.withdraw()
        quem = ("Este computador está sendo usado por ÁREA DE TRABALHO REMOTA."
                if sessao_remota() else
                "Há programa de acesso remoto aberto: " + ", ".join(remotos) + ".")
        if not messagebox.askyesno("Acesso remoto detectado",
                                   f"{quem}\nOutra pessoa pode estar vendo ou controlando o computador.\n"
                                   "(A janela do cofre aparece preta para eles, mas o controle do "
                                   "mouse e do teclado continua possível.)\n\n"
                                   "Abrir o cofre mesmo assim?"):
            root.destroy()
            sys.exit(3)
        root.deiconify()
    def erro_interno(tipo, valor, tb):
        import traceback
        _registrar_erro("".join(traceback.format_exception(tipo, valor, tb)))
        agora = time.time()
        if agora - getattr(erro_interno, "ultimo", 0) < 5:      # não empilha janelas se repetir
            return
        erro_interno.ultimo = agora
        try:
            if issubclass(tipo, MemoryError):
                messagebox.showerror("Memória insuficiente", "Faltou memória livre. Feche outros programas "
                                     "e tente de novo. Nada foi perdido.")
            else:
                messagebox.showerror("Algo deu errado", "Essa ação falhou e não foi concluída. Seus dados no "
                                     "cofre não foram alterados por ela.\n\nO detalhe técnico (sem senhas) "
                                     "ficou em erro_cofre.log, ao lado do programa.")
        except Exception:
            pass
    root.report_callback_exception = erro_interno
    App(root, caminho)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        import traceback
        _registrar_erro(traceback.format_exc())
        _aviso_fatal("Cofre de Senhas", "O cofre encontrou um erro e fechou.\n\nO detalhe foi gravado em "
                     "erro_cofre.log, ao lado do programa (sem senhas). Seus dados no cofre.dat não foram alterados.")
        sys.exit(1)
