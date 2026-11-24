#!/usr/bin/env python3
# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""
Arca — Cofre de Segurança, produto da Arca Sistemas.
Gerenciador de senhas 100% local, criptografado, com autodestruição.
Não faz conexões automaticamente. A consulta opcional de senhas vazadas usa HTTPS
somente quando solicitada; envia apenas o prefixo de 5 caracteres do SHA-1.

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
  - SOMENTE ao esgotar as tentativas de senha erradas (gastas ANTES de testar a senha).
  - NUNCA por arquivo danificado, contador estranho, erro de leitura ou depurador: nesses casos o
    cofre é preservado, nenhuma tentativa é gasta e o programa oferece restaurar a cópia automática.
  - O contador fica fora da parte autenticada e quem copia o arquivo ataca OFFLINE sem contador:
    o que protege o cofre é a senha forte (Argon2id) e as chaves, não a autodestruição.

Proteções de tela/teclado (Windows): janela invisível a prints e gravações, teclado
virtual embaralhado, bloqueio de cópia nos campos, área de transferência fora do
histórico, bloqueio ao minimizar/inatividade, aviso de área de trabalho remota.

Armazenamento: "cofre.dat" na MESMA pasta do programa, ou outro caminho:
    python cofre_senhas.py E:\\minha_pasta\\cofre.dat

Importação: planilhas Excel (.xlsx/.xlsm) e CSV (inclusive exportações do Chrome/Samsung Pass).

Dependências:  pip install cryptography argon2-cffi openpyxl defusedxml fido2 pillow

Mapa das seções, responsabilidades e fluxos: documentacao/GUIA_TECNICO_DO_CODIGO.md
"""
import os
import glob
import re
import sys
import hashlib
import unicodedata
import json
import base64
import math
import zlib
import struct
import stat
import secrets
import string
import time
import threading
import contextlib
import functools
import errno
import copy
import shutil
import atexit
import tempfile

EH_WINDOWS = sys.platform == "win32"
if EH_WINDOWS:
    import ctypes
    from ctypes import wintypes


def _aviso_fatal(titulo, texto):
    """Mostra um aviso mesmo sem console (pythonw / .exe) e sem Tkinter."""
    if os.environ.get("COFRE_TESTE_SEM_JANELA_FATAL") == "1":      # só os testes: não prender a bateria esperando um OK
        print(f"{titulo}\n{texto}", file=sys.stderr)
        return
    try:
        if EH_WINDOWS:
            ctypes.windll.user32.MessageBoxW(None, str(texto), str(titulo), 0x10)
            return
    except (AttributeError, OSError, ctypes.ArgumentError):
        print(f"{titulo}\n{texto}")
        return
    print(f"{titulo}\n{texto}")


_NOME_APP = "Arca"
_NOME_PRODUTO = "Arca — Cofre de Segurança"
_NOME_EMPRESA = "Arca Sistemas"


try:
    from argon2.low_level import hash_secret_raw, Type
    from argon2.exceptions import HashingError
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption
    from cryptography.exceptions import InvalidTag
except ImportError:
    _aviso_fatal(_NOME_APP, "Faltam bibliotecas do Python.\n\nAbra o PowerShell e rode:\n"
                 "    python -m pip install cryptography argon2-cffi openpyxl defusedxml fido2 pillow")
    sys.exit(1)

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    from tkinter import font as tkfont
except ImportError:
    tk = None

if not os.environ.get("PYTHONPYCACHEPREFIX"):
    _raiz_projeto = os.path.dirname(os.path.abspath(__file__))
    _cache_pyc = os.path.join(_raiz_projeto, "CACHE_PROJETO_NAO_MEXER", "testes", "pycache")
    os.environ["PYTHONPYCACHEPREFIX"] = _cache_pyc
    sys.pycache_prefix = _cache_pyc

try:
    from icones_marcas import AutocompletarMarcas, icone as icone_marca
    from icones_marcas import normalizar as normalizar_marca
except ImportError as e:
    _aviso_fatal(_NOME_APP, "Falta Pillow para desenhar os ícones locais das marcas.\n\n"
                 "Abra o PowerShell e rode:\n    python -m pip install pillow\n\n"
                 f"Detalhe: {e}")
    sys.exit(1)

# ----------------------------------------------------------------------------
# Núcleo criptográfico
# ----------------------------------------------------------------------------
ARQUIVO_PADRAO = "cofre.dat"

# Formato atual (v3): cascata ChaCha20-Poly1305 + AES-256-GCM, modo de desbloqueio, nível
MAGIC = b"COFRE05\x00"            # v5 = v4 + checksum do cabeçalho (distingue bit-rot de senha errada)
MAGIC_V4 = b"COFRE04\x00"        # v4 = v3 + seção FIDO depois do contador
MAGIC_V3 = b"COFRE03\x00"
# MAGIC | t | m | p | max_t | modo | sal_pw | nonce_pw | wrap_pw | sal_k | nonce_k | wrap_k | nonce_chacha | nonce_aes
HEADER_FMT = ">8sIIBBB16s12s48s16s12s48s12s12s"
HEADER_LEN = struct.calcsize(HEADER_FMT)
HEADER_FMT5 = HEADER_FMT + "8s"     # v5: + 8 bytes de checksum (SHA-256 truncado) de cabeçalho + seção FIDO
HEADER_LEN5 = struct.calcsize(HEADER_FMT5)
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
MODO_S = 2                         # só a senha mestra (sem chave de acesso); a chave FIDO continua opcional

# Níveis do Argon2id: (iterações, memória em KiB)
NIVEIS = {"alto": (4, 262144),     # 256 MiB por tentativa
          "maximo": (6, 1048576)}  # 1 GiB por tentativa
LIMITE_COFRE = 200 * 1024 * 1024  # tamanho máximo aceito para um arquivo de cofre
RP_ID = "cofre-de-senhas.local"    # identificador do cofre para as chaves FIDO
MAX_FIDO = 8
TENTATIVAS_PADRAO = 3             # erros seguidos até a autodestruição (muda-se dentro do cofre: ⋯ > Tentativas erradas)
TAM_BLOCO = 4096                   # dados preenchidos até múltiplo disto (esconde a quantidade de itens)

PARALELISMO = 2
MIN_SENHA = 14


class SenhaIncorreta(Exception):
    """Senha ou chave errada; guarda quantas tentativas ainda restam."""
    def __init__(self, restantes):
        """Guarda as tentativas restantes e monta a mensagem para o usuário."""
        super().__init__(f"Senha ou chave incorreta. Tentativas restantes: {restantes}")
        self.restantes = restantes


class CofreDestruido(Exception):
    """O cofre foi apagado porque as tentativas acabaram."""
    pass


class ErroGravacao(OSError):
    """Não foi possível gravar o cofre (pendrive cheio, protegido ou removido).
    `protegido` = True quando o motivo é proteção contra gravação (chave física do pendrive, política do computador
    ou somente leitura): é o caso em que a interface oferece o MODO CONSULTA."""
    protegido = False


def _e_protecao_de_escrita(ex):
    """True se o erro de E/S indica mídia/pasta somente leitura ou gravação bloqueada (e não cheia ou removida)."""
    if getattr(ex, "errno", None) in (errno.EROFS, errno.EACCES, errno.EPERM):
        return True
    return getattr(ex, "winerror", None) in (1, 5, 19)     # ERROR_INVALID_FUNCTION, ACCESS_DENIED, WRITE_PROTECT


class ConflitoGravacao(ErroGravacao):
    """O arquivo do cofre mudou desde que foi aberto (outra janela ou programa gravou nele)."""


class ArquivoInvalido(Exception):
    """O arquivo não é um cofre reconhecido (formato desconhecido ou corrompido)."""
    pass


class ArquivoCorrompido(ArquivoInvalido):
    """O arquivo do cofre está danificado (setor ruim, cópia incompleta, byte alterado).
    NUNCA apaga nada: orienta a restaurar a cópia de segurança."""


# Mensagem única do contador de tentativas fora do possível. Nada é apagado nesse caso. A causa mais comum no uso real
# é outra janela abrir o cofre neste mesmo instante (cada abertura gasta uma tentativa antes do Argon2 e devolve se a
# senha estiver certa), então a mensagem diz isso primeiro e só depois manda restaurar a cópia.
MSG_CONTADOR_DANIFICADO = ("O contador de tentativas do arquivo está danificado ou zerado. Se outra janela do cofre "
                           "estiver abrindo este arquivo agora, feche-a, aguarde alguns segundos e tente de novo. "
                           "Se continuar assim, restaure a cópia de segurança. Nada foi apagado.")


class ChaveMalFormada(Exception):
    """A chave de acesso digitada tem formato errado ou erro de digitação."""
    pass


class FidoErro(Exception):
    """Problema com a chave FIDO (cancelada, ausente, não cadastrada...). Não gasta tentativa."""
    pass


class FatorFaltando(Exception):
    """Cofre em modo dois fatores: falta a senha ou a chave (não gasta tentativa)."""
    pass


class PcNaoAutorizado(FatorFaltando):
    """O cofre exige um computador autorizado e este não está na lista (não gasta tentativa: só o código de
    recuperação abre o cofre em outro computador)."""
    pass


class ViolacaoDetectada(Exception):
    """Reservada (compatibilidade com testes antigos). NÃO é mais levantada: arquivo adulterado/danificado
    agora vira ArquivoCorrompido e o cofre é preservado, nunca destruído."""
    pass


SENHAS_COMUNS = ("senha", "password", "123456", "qwerty", "abcdef", "admin", "brasil",
                 "iloveyou", "letmein", "000000", "111111", "abc123", "teste")


def avaliar_senha(senha):
    """Retorna None se aceitável, ou o motivo da recusa."""
    if len(senha) > MAX_SENHA:
        return f"A senha tem mais de {MAX_SENHA} caracteres. Use uma frase de até {MAX_SENHA} caracteres."
    if len(senha) < MIN_SENHA:
        return (f"Para ninguém descobrir sua senha, use pelo menos {MIN_SENHA} caracteres "
                "(uma frase de 4–5 palavras é o ideal).")
    if len(set(senha)) < 8:
        return "Senha muito repetitiva: com poucos caracteres diferentes ela é fácil de adivinhar. Use mais caracteres diferentes."
    if senha.isdigit():
        return "Senha só com números é fácil de adivinhar, até por programas. Use palavras."
    baixa = senha.lower()
    for comum in SENHAS_COMUNS:
        if comum in baixa and len(baixa.replace(comum, "")) < 10:
            return f'A senha é baseada em "{comum}", que está em listas de senhas vazadas.'
    for seq in ("0123456789", "abcdefghijklmnopqrstuvwxyz", "qwertyuiop", "asdfghjkl"):
        for i in range(len(seq) - 5):
            if seq[i:i + 6] in baixa:
                return "A senha contém uma sequência óbvia (como 123456 ou qwerty)."
    nota, rotulo, bits, dicas = avaliar_forca(senha)          # entropia estimada (as listas de cima não pegam tudo)
    if nota < 2:
        return (f"Senha {rotulo.lower()} (cerca de {int(bits)} bits). "
                + (dicas[0] if dicas else "Use uma frase de palavras sem relação entre si, ou o gerador."))
    return None


VERSAO_PROGRAMA = "2026.11.22.2"            # versão do programa (mostrada pelo instalador)
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
        except (AttributeError, OSError, ctypes.ArgumentError):
            return "Não foi possível verificar se há um depurador ligado ao programa."
    return None


def sessao_remota():
    """True se o programa está numa sessão remota do Windows (Área de Trabalho Remota)."""
    if EH_WINDOWS:
        try:
            return bool(ctypes.windll.user32.GetSystemMetrics(0x1000))   # SM_REMOTESESSION
        except Exception:
            return False
    return False


# ----------------------------------------------------------------------------
# Blindagem do processo (Windows): memória trancada, anti-injeção,
# supressão de algumas caixas de erro e detecção de ferramentas espiãs
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
    """Carrega as funções do Windows (kernel32/advapi32) já com os tipos de argumento corretos."""
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
    Windows precisa conversar com o cofre) e tranca de novo logo depois."""
    def __enter__(self):
        """Afrouxa a proteção de memória do processo (a janela do Windows precisa conversar com o cofre)."""
        if "memoria" in BLINDAGEM:
            with _trava_dacl:
                _aplicar_dacl(_SDDL_NORMAL)
        return self

    def __exit__(self, *exc):
        """Tranca de novo a proteção de memória do processo."""
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
            except (AttributeError, OSError, ctypes.ArgumentError, TypeError):
                continue
    except (AttributeError, OSError, ctypes.ArgumentError, TypeError):
        pass
    # 3) a pasta atual deixa de ser usada para procurar DLLs (contra DLL falsa ao lado do programa)
    try:
        k.SetDllDirectoryW.argtypes = [wintypes.LPCWSTR]
        k.SetDllDirectoryW.restype = wintypes.BOOL
        if k.SetDllDirectoryW(""):
            BLINDAGEM.append("busca_dll")
    except (AttributeError, OSError, ctypes.ArgumentError, TypeError):
        pass
    # 3b) DLLs do sistema que NÃO são "conhecidas" do Windows (wer, wtsapi32, dwmapi, webauthn) já entram agora pelo
    #     caminho completo da System32: quando o código pedir só o nome, o Windows reaproveita a que já está carregada
    #     e uma DLL falsa colocada ao lado do programa (pendrive) nunca é consultada.
    try:
        sysdir = ctypes.create_unicode_buffer(260)
        k.GetSystemDirectoryW.argtypes = [wintypes.LPWSTR, wintypes.UINT]
        k.GetSystemDirectoryW.restype = wintypes.UINT
        if 0 < k.GetSystemDirectoryW(sysdir, 260) < 260:
            for dll in ("wer", "wtsapi32", "dwmapi", "webauthn"):
                try:
                    ctypes.WinDLL(os.path.join(sysdir.value, dll + ".dll"))
                except OSError:
                    pass
    except (AttributeError, OSError, ctypes.ArgumentError, TypeError):
        pass
    # 4) remove a exclusão WER persistente criada por versões antigas; não adiciona nada ao Registro.
    try:
        k.SetErrorMode(0x0001 | 0x0002 | 0x8000)
        wer = ctypes.WinDLL("wer.dll")
        wer.WerRemoveExcludedApplication.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
        wer.WerRemoveExcludedApplication.restype = ctypes.c_long
        wer.WerRemoveExcludedApplication("CofreSenhas.exe", False)
    except (AttributeError, OSError, ctypes.ArgumentError, TypeError):
        pass
    return BLINDAGEM


def processos_abertos():
    """Nomes (minúsculos) dos programas em execução."""
    nomes = set()
    if not EH_WINDOWS:
        return nomes

    class _PE32(ctypes.Structure):
        """Estrutura PROCESSENTRY32W do Windows (um processo da lista)."""
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
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            pe = _PE32()
            pe.dwSize = ctypes.sizeof(_PE32)
            ok = k.Process32FirstW(h, ctypes.byref(pe))
            while ok:
                nomes.add(pe.szExeFile.lower())
                ok = k.Process32NextW(h, ctypes.byref(pe))
        finally:
            k.CloseHandle(h)
    except (AttributeError, OSError, ctypes.ArgumentError, TypeError) as ex:
        raise OSError("Não foi possível verificar os processos abertos.") from ex
    return nomes


def ferramentas_espias(nomes=None):
    """Lista os programas abertos capazes de ler a memória de outros (depuradores, dumpers)."""
    nomes = processos_abertos() if nomes is None else nomes
    return sorted(n for n in nomes if n in FERRAMENTAS_ESPIAS or n.startswith(PREFIXOS_ESPIOES))


def acesso_remoto_aberto(nomes=None):
    """Lista os programas de acesso remoto abertos (AnyDesk, TeamViewer etc.)."""
    nomes = processos_abertos() if nomes is None else nomes
    return sorted(n for n in nomes if n in ACESSO_REMOTO)


def pasta_base():
    """Pasta onde fica o programa (o cofre é salvo ao lado dele)."""
    if "__compiled__" in globals():             # executável gerado pelo Nuitka
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    if getattr(sys, "frozen", False):           # executável gerado pelo PyInstaller
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def memoria_fisica_livre():
    """Memória física disponível agora, em bytes (None se o sistema não informar)."""
    try:
        if os.name == "nt":
            class _MemStatus(ctypes.Structure):
                """Estrutura MEMORYSTATUSEX do Windows (GlobalMemoryStatusEx): memória física e virtual."""
                _fields_ = [("tam", ctypes.c_ulong), ("carga", ctypes.c_ulong),
                            ("total_fis", ctypes.c_ulonglong), ("livre_fis", ctypes.c_ulonglong),
                            ("total_pag", ctypes.c_ulonglong), ("livre_pag", ctypes.c_ulonglong),
                            ("total_vir", ctypes.c_ulonglong), ("livre_vir", ctypes.c_ulonglong),
                            ("livre_ext", ctypes.c_ulonglong)]
            ms = _MemStatus()
            ms.tam = ctypes.sizeof(ms)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
                return int(ms.livre_fis)
            return None
        with open("/proc/meminfo", encoding="ascii") as f:
            for linha in f:
                if linha.startswith("MemAvailable:"):
                    return int(linha.split()[1]) * 1024
    except (AttributeError, OSError, ValueError, ctypes.ArgumentError, TypeError):
        return None
    return None


def nivel_recomendado():
    """Nível de blindagem sugerido para ESTE computador: 'maximo' (1 GiB) só se há memória livre de sobra
    (>= 2,5 GiB); em PCs fracos sugere 'alto' (256 MiB), para o Windows não precisar usar o arquivo de paginação
    (que gravaria pedaços da derivação no disco). Se o sistema não informar, mantém 'maximo'."""
    livre = memoria_fisica_livre()
    if livre is not None and livre < int(NIVEIS["maximo"][1]) * 1024 * 2.5:
        return "alto"
    return "maximo"


def exigir_memoria(m_kib):
    """Recusa ANTES de derivar quando não há memória física para o Argon2 (m_kib KiB) com folga de 25%:
    sem isso o Windows passa a usar o disco (paginação), o computador engasga e a janela parece travada.
    Levanta MemoryError (a interface já explica e NÃO gasta tentativa)."""
    livre = memoria_fisica_livre()
    if livre is not None and livre < int(m_kib) * 1024 * 1.25:
        raise MemoryError("memória física livre insuficiente para o Argon2")


def derivar_chave(senha, sal, t, m, p):
    """Deriva a chave a partir da senha com Argon2id (custo t, memória m, paralelismo p)."""
    exigir_memoria(m)
    try:
        return hash_secret_raw(secret=senha.encode("utf-8"), salt=sal, time_cost=t,
                               memory_cost=m, parallelism=p, hash_len=32, type=Type.ID)
    except HashingError as ex:           # sem memória livre para o Argon2 (ex.: blindagem Máxima = 1 GiB)
        raise MemoryError(str(ex)) from ex


def kek_da_chave(chave_bytes, sal):
    """Deriva a chave de embrulho a partir da chave de acesso (HKDF-SHA256)."""
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=sal,
                info=b"cofre-chave-de-acesso").derive(chave_bytes)


def kek_combinada(kek_senha, chave_bytes, sal):
    """Modo dois fatores: a chave só existe com a senha E a chave de acesso juntas."""
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=sal,
                info=b"cofre-senha-E-chave").derive(kek_senha + chave_bytes)


def _embrulhar(kek, dek):
    """Cifra a chave dos dados (DEK) com a chave de embrulho (AES-GCM); devolve nonce e embrulho."""
    nonce = secrets.token_bytes(12)
    return nonce, AESGCM(kek).encrypt(nonce, dek, WRAP_AAD)


def _desembrulhar(kek, nonce, embrulho):
    """Abre o embrulho da DEK; levanta InvalidTag se a chave estiver errada."""
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


def _fator_total(fator_fido, fator_pc):
    """Fator que entra na chave dos dados: sem computador autorizado é o do FIDO (formato antigo, igual byte a byte);
    com ele, mistura os dois (o computador é um fator A MAIS, nunca uma alternativa à chave FIDO)."""
    if fator_pc is None:
        return fator_fido
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=b"cofre-fator-fido-mais-computador").derive((fator_fido or b"") + fator_pc)


def _kek_pc(material, sal):
    """Chave de embrulho do fator 'computador autorizado', derivada da identidade deste computador."""
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=sal,
                info=b"cofre-kek-computador").derive(material)


def _kek_fido(saida_hmac):
    """Deriva a chave de embrulho a partir do segredo devolvido pela chave FIDO."""
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=b"cofre-kek-chave-fido").derive(saida_hmac)


def _kek_recuperacao(codigo_bytes, sal):
    """Deriva a chave de embrulho a partir do código de recuperação."""
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=sal,
                info=b"cofre-codigo-recuperacao-fido").derive(codigo_bytes)


def _serializar_fido(fido):
    """Transforma os dados FIDO do cofre (credenciais, sais, embrulhos) em bytes para o arquivo."""
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


MAX_PC = 8                      # computadores autorizados por cofre


def _serializar_secao(fido, pc):
    """Seção de fatores extras do arquivo: o byte de marca diz o que vem depois (1 = FIDO, 2 = computadores,
    3 = os dois). Sem computadores é IDÊNTICA à seção FIDO antiga: cofres antigos continuam abrindo."""
    if not pc:
        return _serializar_fido(fido)
    out = bytearray([(1 if fido else 0) | 2])
    if fido:
        out += _serializar_fido(fido)[1:]
    out.append(len(pc["maquinas"]))
    out += pc["salt"]
    sal, nonce, wrap = pc["rec"]
    out += sal + nonce + wrap
    for m in pc["maquinas"]:
        nome = m["nome"].encode("utf-8")[:60]
        out.append(len(nome))
        out += nome
        out += m["id"] + m["nonce"] + m["wrap"]
    return bytes(out)


def _ler_secao(bruto, pos):
    """Lê a seção de fatores extras a partir de 'pos'. Retorna (fido ou None, pc ou None, posição final)."""
    def pegar(n):
        """Lê n bytes da seção e avança a posição."""
        nonlocal pos
        if pos + n > len(bruto):
            raise ArquivoInvalido("Seção FIDO do cofre corrompida.")
        v = bruto[pos:pos + n]
        pos += n
        return v
    flag = pegar(1)[0]
    if flag == 0:
        return None, None, pos
    if flag not in (1, 2, 3):
        raise ArquivoInvalido("Seção FIDO do cofre inválida (arquivo adulterado?).")
    fido = pc = None
    if flag & 1:
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
    if flag & 2:
        n = pegar(1)[0]
        if not 1 <= n <= MAX_PC:
            raise ArquivoInvalido("Seção de computadores do cofre inválida (arquivo adulterado?).")
        pc = {"salt": pegar(32), "rec": (pegar(16), pegar(12), pegar(48)), "maquinas": []}
        for _ in range(n):
            nome = pegar(pegar(1)[0]).decode("utf-8", "replace")
            pc["maquinas"].append({"nome": nome, "id": pegar(8), "nonce": pegar(12), "wrap": pegar(48)})
    return fido, pc, pos


def _ler_fido(bruto, pos):
    """Lê a seção de fatores extras e devolve (fido ou None, posição final) — a posição final vale também com
    computadores autorizados (usada pelo checksum e para achar onde começam os dados)."""
    fido, _, fim = _ler_secao(bruto, pos)
    return fido, fim


# ---- identidade do computador (fator "computador autorizado") ---------------------------------------------------
# Usa só o que quase nunca muda: o MachineGuid do Windows e o UUID da placa-mãe (SMBIOS). NÃO usa disco, placa de rede,
# IP nem nome do computador (trocam com upgrade, Wi-Fi/cabo ou renomeação). Reinstalar o Windows muda o MachineGuid:
# nesse caso o computador precisa ser autorizado de novo (pelo código de recuperação ou por outro computador autorizado).
def _machine_guid():
    """MachineGuid do Windows (ou /etc/machine-id fora do Windows, para desenvolvimento). b'' se não achar."""
    try:
        if EH_WINDOWS:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                                winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                return str(winreg.QueryValueEx(k, "MachineGuid")[0]).strip().lower().encode("ascii", "ignore")
        with open("/etc/machine-id", "rb") as f:
            return f.read(64).strip().lower()
    except Exception:
        return b""


def _uuid_de_smbios(tabela):
    """UUID do 'System Information' (tipo 1) numa tabela SMBIOS bruta; None se faltar ou for valor de fábrica inútil
    (tudo 00 ou tudo FF). Só lê bytes: não executa nada."""
    i, n = 0, len(tabela)
    while i + 4 <= n:
        tipo, tam = tabela[i], tabela[i + 1]
        if tam < 4 or i + tam > n:
            break
        if tipo == 1 and tam >= 0x19:
            u = bytes(tabela[i + 8:i + 24])
            return None if u in (bytes(16), b"\xff" * 16) else u
        if tipo == 127:
            break
        j = i + tam
        while j + 1 < n and not (tabela[j] == 0 and tabela[j + 1] == 0):
            j += 1
        i = j + 2
    return None


def _smbios_uuid():
    """UUID da placa-mãe lido da tabela SMBIOS do firmware (API nativa do Windows, sem processos externos)."""
    if not EH_WINDOWS:
        return None
    try:
        f = ctypes.windll.kernel32.GetSystemFirmwareTable
        f.argtypes = [wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        f.restype = wintypes.DWORD
        tam = f(0x52534D42, 0, None, 0)                    # 'RSMB'
        if not 8 < tam < 4 * 1024 * 1024:
            return None
        buf = ctypes.create_string_buffer(tam)
        if f(0x52534D42, 0, buf, tam) != tam:
            return None
        raw = bytes(buf.raw)
        return _uuid_de_smbios(raw[8:8 + struct.unpack("<I", raw[4:8])[0]])
    except Exception:
        return None


def identidades_do_pc():
    """Lista de identidades deste computador (32 bytes cada), da preferida para a reserva: [MachineGuid+UUID da
    placa-mãe, só MachineGuid]. A autorização grava com a primeira; a abertura aceita qualquer uma. Vazia se o
    computador não puder ser identificado."""
    guid = _machine_guid()
    if not guid:
        return []
    so_guid = hashlib.sha256(b"cofre-pc-v1|G|" + guid).digest()
    uid = _smbios_uuid()
    if uid:
        return [hashlib.sha256(b"cofre-pc-v1|GU|" + guid + b"|" + uid).digest(), so_guid]
    return [so_guid]


# ---- segredo local do computador (reforço opcional do "computador autorizado") ----------------------------------
# Um segredo aleatório de 32 bytes guardado NESTE computador, cifrado pelo Windows (DPAPI, preso ao usuário do Windows):
# %LOCALAPPDATA%\\CofreSenhas\\pc_local.bin. Se o computador foi autorizado com o reforço, a identidade dele passa a
# depender desse segredo: saber o MachineGuid/UUID (que qualquer programa lê) deixa de bastar. Pendrive + senha sozinhos
# não abrem; outro usuário do Windows ou outro computador também não (DPAPI). Perdeu o segredo (Windows reinstalado,
# outro usuário)? Abra com o código de recuperação e autorize de novo.
if EH_WINDOWS:
    class _Blob(ctypes.Structure):
        """DATA_BLOB da API do Windows (tamanho + ponteiro) usado pela DPAPI."""
        _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(dado, proteger):
    """CryptProtectData/CryptUnprotectData (escopo do usuário, sem janela). Devolve bytes ou None se falhar."""
    if not EH_WINDOWS:
        return None
    try:
        crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
        entrada = _Blob(len(dado), ctypes.cast(ctypes.create_string_buffer(dado, len(dado)), ctypes.POINTER(ctypes.c_ubyte)))
        entropia_b = b"cofre-segredo-local-v1"
        entropia = _Blob(len(entropia_b), ctypes.cast(ctypes.create_string_buffer(entropia_b, len(entropia_b)),
                                                      ctypes.POINTER(ctypes.c_ubyte)))
        saida = _Blob()
        if proteger:
            ok = crypt32.CryptProtectData(ctypes.byref(entrada), _NOME_APP, ctypes.byref(entropia), None, None, 1,
                                          ctypes.byref(saida))
        else:
            ok = crypt32.CryptUnprotectData(ctypes.byref(entrada), None, ctypes.byref(entropia), None, None, 1,
                                            ctypes.byref(saida))
        if not ok:
            return None
        try:
            return ctypes.string_at(saida.pbData, saida.cbData)
        finally:
            kernel32.LocalFree(saida.pbData)
    except Exception:
        return None


def _arquivo_segredo_local():
    """Caminho do arquivo do segredo local deste computador/usuário (fora do pendrive, de propósito)."""
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "CofreSenhas", "pc_local.bin")


def segredo_local(criar=False):
    """Segredo local de 32 bytes deste computador (None se não existe/não abre). criar=True cria se faltar.
    No Windows é protegido pela DPAPI; fora dele (só desenvolvimento) fica em arquivo comum."""
    arq = _arquivo_segredo_local()
    bruto = None
    # como em _trocar, mas com bem mais fôlego (24 x 0,25s = 6s): no Windows o antivírus/indexador pode segurar um
    # arquivo (e a PASTA) recém-criados por mais tempo do que um arquivo já existente sendo só atualizado - e é
    # exatamente a situação aqui: "Autorizar este computador" (com reforço) acaba de CRIAR a pasta e o arquivo, e
    # quase no mesmo instante a tela de computadores chama pc_id_deste/segredo_local para atualizar a lista. 6
    # tentativas (1,5s) já resolveram o caso comum, mas numa pasta nova o antivírus pode demorar mais que isso.
    for _ in range(24):
        try:
            with open(arq, "rb") as f:
                bruto = f.read(4096)
            break
        except PermissionError:
            time.sleep(0.25)
        except OSError:
            break        # não existe (ainda) ou outro erro real: não adianta tentar de novo
    if bruto is not None:
        dado = _dpapi(bruto, False) if EH_WINDOWS else bruto
        if dado and len(dado) == 32:
            return dado
    if not criar:
        return None
    novo = secrets.token_bytes(32)
    gravar = _dpapi(novo, True) if EH_WINDOWS else novo
    if not gravar:
        return None
    try:
        os.makedirs(os.path.dirname(arq), exist_ok=True)
        _gravar_atomico(arq, gravar)
    except OSError:
        return None
    return novo


def _com_segredo_local(material, seg):
    """Mistura o segredo local na identidade do computador (HMAC-SHA256)."""
    import hmac
    return hmac.new(seg, b"cofre-pc-local|" + material, hashlib.sha256).digest()


def _variantes_do_pc():
    """[(nivel, material)] que podem abrir a embalagem deste computador: primeiro as REFORÇADAS com o segredo local
    (se ele existe e abre), depois as básicas. O que vale é a embalagem: quem a fez sem o segredo só abre sem ele."""
    base = identidades_do_pc()
    seg = segredo_local()
    saida = [("local", _com_segredo_local(m, seg)) for m in base] if seg else []
    return saida + [("basico", m) for m in base]


def _id_pc(sal, material):
    """Identificador curto (8 bytes) de um computador dentro de UM cofre (depende do sal do cofre)."""
    return hashlib.sha256(b"cofre-id-pc|" + sal + material).digest()[:8]


def _achar_g_nivel(pc):
    """(G, nivel) se ESTE computador está autorizado no cofre ('local' = com o segredo do Windows, 'basico'); None se não."""
    for nivel, material in _variantes_do_pc():
        idm = _id_pc(pc["salt"], material)
        for m in pc["maquinas"]:
            if m["id"] == idm:
                try:
                    return _desembrulhar(_kek_pc(material, pc["salt"]), m["nonce"], m["wrap"]), nivel
                except InvalidTag:
                    continue
    return None


def _achar_g(pc):
    """Fator 'computador' (G) se ESTE computador está autorizado no cofre; None se não estiver."""
    r = _achar_g_nivel(pc)
    return r[0] if r else None


def _dv_chave(b):
    """2 caracteres de verificação (10 bits): um erro de digitação é percebido SEM gastar tentativa."""
    d = hashlib.sha256(b"cofre-dv" + b).digest()
    alfabeto = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    return alfabeto[d[0] & 31] + alfabeto[d[1] & 31]


def nova_chave_acesso():
    """Retorna (bytes, texto): 160 bits em base32 + 2 caracteres de verificação.
    Formato: XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XX"""
    b = secrets.token_bytes(20)
    txt = base64.b32encode(b).decode("ascii") + _dv_chave(b)
    return b, "-".join(txt[i:i + 4] for i in range(0, 34, 4))


def ler_chave_acesso(texto):
    """Lê a chave de acesso digitada (32 caracteres + 2 de verificação), ignora separadores e confere o erro de digitação."""
    limpo = re.sub(r"[^A-Za-z2-7]", "", texto or "").upper()
    if len(limpo) not in (32, 34):          # 32 = chaves antigas (sem dígitos de verificação)
        raise ChaveMalFormada("Formato de chave de acesso inválido (32 caracteres A–Z e 2–7 mais 2 de "
                              "verificação, em grupos de 4).")
    b = base64.b32decode(limpo[:32])
    if len(limpo) == 34 and not secrets.compare_digest(limpo[32:], _dv_chave(b)):
        raise ChaveMalFormada("A chave tem um erro de digitação (os 2 caracteres finais de verificação "
                              "não batem). Confira e digite de novo.")
    return b


# ---- Arquivo de chave SELADO (.key): só este cofre o decifra e o carrega ----
MAGIC_CHAVE = b"CKEY\x00\x00\x00\x01"            # 8 bytes: identifica o formato do arquivo de chave


def _selo_do_cofre(sal_k, nonce_k, wrap_k):
    """(identificador público, chave de selagem) deste cofre, tirados dos campos da chave de acesso gravados no
    cabeçalho dele. Outro cofre (ou a mesma chave depois de trocada) gera outro par: o arquivo não abre."""
    base = bytes(sal_k) + bytes(nonce_k) + bytes(wrap_k)
    ident = hashlib.sha256(b"cofre-id-arquivo-chave" + base).digest()[:8]
    kek = HKDF(algorithm=hashes.SHA256(), length=32, salt=bytes(sal_k),
               info=b"cofre-arquivo-chave-v1").derive(base)
    return ident, kek


def selar_chave_acesso(texto_chave, sal_k, nonce_k, wrap_k):
    """Transforma a chave de acesso (texto) em um ARQUIVO CIFRADO que só este cofre decifra:
    MAGIC | id do cofre | nonce | ChaCha20-Poly1305(chave). Quem pegar só o arquivo não vê a chave, e
    qualquer byte alterado faz o carregamento falhar."""
    chave = ler_chave_acesso(texto_chave)
    ident, kek = _selo_do_cofre(sal_k, nonce_k, wrap_k)
    nonce = secrets.token_bytes(12)
    return MAGIC_CHAVE + ident + nonce + ChaCha20Poly1305(kek).encrypt(nonce, chave, MAGIC_CHAVE + ident)


def arquivo_de_chave_e_selado(dados):
    """True se o conteúdo lido de um .key é do formato selado (e não texto puro de versões antigas)."""
    return bytes(dados[:8]) == MAGIC_CHAVE


def abrir_chave_selada(dados, sal_k, nonce_k, wrap_k):
    """Decifra um arquivo de chave selado com os dados DESTE cofre e devolve a chave em texto (XXXX-XXXX-...).
    Erros em português: outro cofre, chave trocada ou arquivo danificado (nada disso gasta tentativa)."""
    dados = bytes(dados)
    if len(dados) < 8 + 8 + 12 + 16 + 20 or dados[:8] != MAGIC_CHAVE:
        raise ChaveMalFormada("Este arquivo não é uma chave do cofre (ou está incompleto).")
    ident, kek = _selo_do_cofre(sal_k, nonce_k, wrap_k)
    if not secrets.compare_digest(dados[8:16], ident):
        raise ChaveMalFormada("Este arquivo de chave é de outro cofre, ou a chave/senha deste cofre foi trocada "
                              "depois de salvá-lo. Use a chave anotada em papel ou gere um arquivo novo.")
    try:
        chave = ChaCha20Poly1305(kek).decrypt(dados[16:28], dados[28:], MAGIC_CHAVE + ident)
    except InvalidTag:
        raise ChaveMalFormada("O arquivo de chave está danificado ou foi alterado. Use a chave anotada em papel.") from None
    txt = base64.b32encode(chave).decode("ascii") + _dv_chave(chave)
    return "-".join(txt[i:i + 4] for i in range(0, 34, 4))


def chave_de_arquivo(caminho_cofre, dados):
    """Lê o conteúdo de um .key escolhido na tela de desbloqueio: se for selado, decifra com o cabeçalho do cofre
    em 'caminho_cofre'; se for texto puro (versões antigas), devolve o texto. Não grava nada."""
    if not arquivo_de_chave_e_selado(dados):
        try:
            return bytes(dados[:200]).decode("ascii").strip()      # texto puro (versões antigas) é só ASCII
        except UnicodeDecodeError:
            raise ChaveMalFormada("Este arquivo não é uma chave do cofre (ou está danificado).") from None
    with open(caminho_cofre, "rb") as f:
        h = _ler_cabecalho(f.read(LIMITE_COFRE + 1))
    return abrir_chave_selada(dados, h["sal_k"], h["nonce_k"], h["wrap_k"])


def _zerar(buf):
    """Sobrescreve com zeros um bytearray (limitado: o Python não deixa zerar str/bytes nem as cópias
    internas do json e da biblioteca de criptografia)."""
    try:
        n = len(buf)
        if n:
            ctypes.memset((ctypes.c_char * n).from_buffer(buf), 0, n)
    except Exception:
        for i in range(len(buf)):
            buf[i] = 0


def zerar_objeto(o, permitir_compartilhado=False):
    """Melhor esforço (só CPython): sobrescreve com zeros o conteúdo de um `bytes` ou de um `str` ASCII, que o
    Python normalmente não deixa apagar. Ignora objetos de 0 ou 1 caractere (o Python os compartilha) e, por padrão,
    também não toca em objetos compartilhados. `permitir_compartilhado` é reservado à limpeza de segredos ao fechar
    o cofre: os aliases passam a ver zeros."""
    try:
        if sys.implementation.name != "cpython" or sys.flags.dev_mode or "debug" in os.environ.get("PYTHONMALLOC", "").lower():
            return False
        t = type(o)
        if t is bytes:
            n = len(o)
        elif t is str and o.isascii():
            n = len(o)
        else:
            return False
        if n < 2:
            return False
        if t is str:
            is_interned = getattr(sys, "_is_interned", None)
            if is_interned is None or is_interned(o):
                return False                # sem a API de detecção, não arriscar alterar texto compartilhado
        if not permitir_compartilhado and sys.getrefcount(o) > 4:
            return False                    # não sobrescrever objetos compartilhados
        import ctypes as _ct
        _ct.memset(id(o) + sys.getsizeof(o) - n - 1, 0, n)
        return True
    except Exception:
        return False


def varrer_memoria_livre(blocos_por_tamanho=6000):
    """Melhor esforço: o Python reaproveita os blocos pequenos que liberou. Aloca muitos objetos de cada
    tamanho (preenchidos com zeros) para sobrescrever restos de textos já descartados (cópias de senhas
    que o json e outras bibliotecas fizeram e que não dá para apagar individualmente). Não garante nada."""
    try:
        import gc
        gc.collect()
        for tam in range(16, 520, 8):
            lote = [bytes(tam) for _ in range(blocos_por_tamanho)]
            lote2 = ["\0" * (tam - 49 if tam > 49 else 1) for _ in range(blocos_por_tamanho // 4)]
            del lote, lote2
        # blocos maiores (buffers que o json e a criptografia deixaram ao crescer): o malloc os reaproveita
        for tam in list(range(576, 8192, 64)) + list(range(8192, 65537, 2048)):
            grandes = [bytearray(tam) for _ in range(12)]
            del grandes
        gc.collect()
        return True
    except Exception:
        return False


# ----------------------------------------------------------------------------
# Erros de leitura/gravação (pendrive removido, protegido, cheio, em uso)
# ----------------------------------------------------------------------------
def _causa_io(err, win=None):
    """Causa provável, em português e SEM caminho de arquivo, para um código de erro do sistema."""
    if err == errno.ENOSPC or win in (39, 112):
        return "não há espaço livre no pendrive"
    if err == errno.EROFS or win == 19:
        return "o pendrive está protegido contra gravação"
    if err in (errno.EACCES, errno.EPERM) or win in (5, 32, 33):
        return "acesso negado ou arquivo em uso por outro programa (antivírus, Excel, indexador)"
    if err in (errno.ENOENT, errno.ENODEV, errno.ENXIO, errno.ENOTDIR) or win in (2, 3, 21, 22, 55, 59, 64, 67, 121, 1167):
        return "o pendrive foi removido ou ficou inacessível"
    if err == errno.EIO or win in (23, 483, 1104, 1117):
        return "erro de leitura/gravação no pendrive (removido, mal encaixado ou com defeito)"
    if err:
        return f"falha de leitura/gravação (código {err})"
    return "falha de leitura/gravação"


def descrever_erro_io(ex):
    """Texto curto e seguro para o usuário a partir de um erro de arquivo (nunca inclui o caminho)."""
    if isinstance(ex, (ErroGravacao, ArquivoInvalido)):
        return str(ex)
    return "Falha ao acessar o arquivo: " + _causa_io(getattr(ex, "errno", None), getattr(ex, "winerror", None)) + "."


def texto_erro(ex):
    """Mensagem para mostrar na tela: erros de arquivo viram texto amigável; os demais mantêm a própria mensagem."""
    return descrever_erro_io(ex) if isinstance(ex, OSError) else str(ex)


def _trocar(origem, destino):
    """os.replace com novas tentativas: no Windows o antivírus/indexador às vezes segura o arquivo por instantes."""
    ultimo = None
    for i in range(8):                        # espera crescente (0,25 s ... 0,75 s, ~4 s ao todo): pendrive lento, antivírus, indexador
        try:
            os.replace(origem, destino)
            return
        except PermissionError as ex:
            ultimo = ex
            time.sleep(0.25 * (1 + i // 3))
        except OSError as ex:                 # E/S abrupta (dispositivo ocupado/sumiu por instantes): tenta de novo
            if getattr(ex, "winerror", None) not in (32, 33, 21, 1117) and ex.errno not in (16, 5):
                raise
            ultimo = ex
            time.sleep(0.25 * (1 + i // 3))
    raise ultimo


def _sincronizar_pasta(caminho):
    """Pede ao sistema que grave também a entrada da pasta (Linux/macOS; no Windows o NTFS/FAT já faz no replace)."""
    if EH_WINDOWS:
        return
    try:
        fd = os.open(os.path.dirname(os.path.abspath(caminho)) or ".", os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def _gravar_atomico(caminho, dados):
    """Grava num arquivo temporário (mesma pasta), força a gravação física, RELÊ e confere o SHA-256 do que ficou
    gravado e só então troca pelo definitivo (os.replace). Se o pendrive sair no meio, o arquivo original continua
    intacto. Qualquer falha vira ErroGravacao com texto claro e o temporário é apagado.
    O .tmp é SEMPRE um arquivo novo que este processo cria (O_CREAT|O_EXCL, e O_NOFOLLOW onde existe): se alguém
    plantar um link simbólico com esse nome antes (apontando para outro arquivo qualquer que o usuário possa
    escrever), o link é removido primeiro e a escrita nunca passa por ele - sem isso, a gravação seguiria o link
    e sobrescreveria o arquivo de destino do link em vez de criar o cofre, e o cofre final acabaria sendo, ele
    mesmo, um link para esse outro lugar (achado real de pentest, corrigido aqui)."""
    _limpar_temporarios_interrompidos(caminho)
    tmp = f"{caminho}.{os.getpid()}.tmp"     # um temporário POR PROCESSO: dois processos nunca trocam o .tmp um do outro
    esperado = hashlib.sha256(dados).digest()
    try:
        try:
            os.remove(tmp)   # remove qualquer resquício (inclusive um link plantado) ANTES de criar o novo;
        except FileNotFoundError:   # os.remove nunca segue o link - só desfaz a entrada, não toca no alvo dele
            pass
        descritor = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(descritor, "wb") as f:
            f.write(dados)
            f.flush()
            os.fsync(f.fileno())
        with open(tmp, "rb") as f:                        # confere o que REALMENTE foi parar no disco
            lido = f.read(len(dados) + 1)
        ok = len(lido) == len(dados) and secrets.compare_digest(hashlib.sha256(lido).digest(), esperado)
        del lido
        if not ok:
            raise OSError(errno.EIO, "a gravação não confere com o que foi enviado")
        _trocar(tmp, caminho)
        _sincronizar_pasta(caminho)
    except OSError as ex:
        try:
            os.remove(tmp)          # não deixa pela metade; o cofre original continua intacto
        except OSError:
            pass
        diag_registrar(DIAG_GRAVACAO, ex)
        if isinstance(ex, ErroGravacao):
            raise
        novo = ErroGravacao("Não consegui gravar no pendrive: " + _causa_io(ex.errno, getattr(ex, "winerror", None))
                            + ". O cofre anterior continua intacto.")
        novo.errno = ex.errno
        novo.protegido = _e_protecao_de_escrita(ex)      # pasta/arquivo somente leitura: a tela oferece o MODO CONSULTA
        raise novo from ex


def _limpar_temporarios_interrompidos(caminho):
    """Apaga temporários de gravação apenas quando o processo que os criou já terminou."""
    prefixo = caminho + "."
    for temporario in glob.glob(glob.escape(caminho) + ".*.tmp"):
        nome = temporario[len(prefixo):-4]
        if not nome.isdecimal() or len(nome) > 10:
            continue
        pid = int(nome)
        if pid <= 0:
            continue
        if EH_WINDOWS:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel32.GetExitCodeProcess.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                erro = ctypes.get_last_error()
                if erro != 87:                   # ERROR_INVALID_PARAMETER: o processo já não existe
                    diag_registrar(DIAG_GRAVACAO, ctypes.WinError(erro))
                    continue
        else:
            try:
                os.kill(pid, 0)
            except PermissionError:
                continue
            except OverflowError:
                continue
            except OSError as ex:
                if ex.errno != errno.ESRCH:
                    diag_registrar(DIAG_GRAVACAO, ex)
                    continue
            else:
                continue
        if EH_WINDOWS and handle:
            try:
                codigo_saida = wintypes.DWORD()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(codigo_saida)):
                    diag_registrar(DIAG_GRAVACAO, ctypes.WinError(ctypes.get_last_error()))
                    continue
                if codigo_saida.value == 259:    # STILL_ACTIVE
                    continue
            finally:
                kernel32.CloseHandle(handle)
        try:
            os.remove(temporario)
        except FileNotFoundError:
            pass
        except OSError as ex:
            diag_registrar(DIAG_GRAVACAO, ex)


# ----------------------------------------------------------------------------
# Registro de diagnóstico: local, rotativo, minimalista e CIFRADO.
# Só guarda números (código do evento, errno, linha do programa, versão, minuto) - nunca texto, caminho, senha,
# hash ou memória. Cada registro é selado com a chave PÚBLICA do cofre (X25519 + ChaCha20-Poly1305), então dá
# para registrar mesmo com o cofre trancado; a chave privada fica DENTRO do cofre (meta), e só o cofre aberto lê.
# ----------------------------------------------------------------------------
DIAG_MAGIC = b"CDIAG02\x00"
DIAG_REG = struct.Struct(">BHiHII24s28s28s")  # versão do registro, código, errno, linha, versão do programa, minutos,
                                              # tipo do erro, função onde parou, função que a chamou (só nomes de código)
DIAG_TAM = 32 + 12 + DIAG_REG.size + 16       # chave efêmera + nonce + dado + etiqueta
DIAG_CAB = len(DIAG_MAGIC) + 32               # magic + chave pública
DIAG_MAX = 200                                # ao passar disso, mantém só os DIAG_MANTER mais recentes
DIAG_MANTER = 100
(DIAG_NAO_TRATADO, DIAG_INTERFACE, DIAG_GRAVACAO, DIAG_COPIA, DIAG_LEITURA, DIAG_INTEGRIDADE,
 DIAG_CONFLITO, DIAG_RESTAURADO, DIAG_BACKUP, DIAG_REVERSAO) = range(1, 11)
DIAG_CODIGOS = {
    DIAG_NAO_TRATADO: "Erro inesperado que fechou o programa",
    DIAG_INTERFACE: "Erro inesperado numa ação da tela",
    DIAG_GRAVACAO: "Falha ao gravar o cofre",
    DIAG_COPIA: "Falha ao criar a cópia de segurança",
    DIAG_LEITURA: "Falha ao ler o cofre",
    DIAG_INTEGRIDADE: "Dados do cofre danificados (integridade)",
    DIAG_CONFLITO: "Gravação recusada: o arquivo mudou ou sumiu",
    DIAG_RESTAURADO: "Cofre restaurado de uma cópia de segurança",
    DIAG_BACKUP: "Falha ao gravar backup ou exportação",
    DIAG_REVERSAO: "Cofre abriu mais antigo que uma cópia de segurança (possível reversão)",
}
_DIAG = {"arq": None, "pub": None}
_TRAVA_DIAG = threading.Lock()


def _versao_num():
    """VERSAO_PROGRAMA como número (2026.11.11.4 -> 2026111104) para caber no registro."""
    try:
        p = [int(x) for x in VERSAO_PROGRAMA.split(".")][:4]
        p += [0] * (4 - len(p))
        return min(p[0] * 1000000 + p[1] * 10000 + p[2] * 100 + p[3], 4294967295)
    except Exception:
        return 0


def _diag_chave(priv_ou_eph, par_pub, epub):
    """Chave simétrica de um registro: HKDF do segredo X25519 (sal = chave efêmera + chave pública do cofre)."""
    segredo = priv_ou_eph.exchange(X25519PublicKey.from_public_bytes(par_pub))
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=epub, info=b"cofre-diag-v1").derive(segredo)


def _bytes_pub(chave_privada):
    """Os 32 bytes da chave pública de uma chave X25519."""
    return chave_privada.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def _diag_selar(pub, dado):
    """Sela um registro para a chave pública do cofre (caixa selada: só quem tem a privada abre)."""
    eph = X25519PrivateKey.generate()
    epub = _bytes_pub(eph)
    chave = _diag_chave(eph, pub, epub + pub)
    nonce = secrets.token_bytes(12)
    return epub + nonce + ChaCha20Poly1305(chave).encrypt(nonce, dado, DIAG_MAGIC)


def _diag_abrir(priv_bytes, reg):
    """Abre um registro selado com a chave privada do cofre; levanta InvalidTag se foi adulterado."""
    priv = X25519PrivateKey.from_private_bytes(priv_bytes)
    epub, nonce, ct = reg[:32], reg[32:44], reg[44:]
    chave = _diag_chave(priv, epub, epub + _bytes_pub(priv))
    return ChaCha20Poly1305(chave).decrypt(nonce, ct, DIAG_MAGIC)


def _gravar_diag_atomico(arq, dados):
    """Troca o arquivo de diagnóstico por um temporário exclusivo na mesma pasta."""
    pasta = os.path.dirname(arq) or "."
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(arq) + ".", suffix=".tmp", dir=pasta)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(dados)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, arq)
    except OSError:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _com_apoio_liberado(f):
    """Decorador: roda a função dentro de apoio_liberado() (definida mais abaixo; é procurada só na hora da chamada).
    Serve para as operações que gravam no cofre ou perto dele, que precisam do arquivo liberado por instantes."""
    @functools.wraps(f)
    def interno(*a, **k):
        with apoio_liberado():
            return f(*a, **k)
    return interno


def diag_definir(caminho_cofre):
    """Diz onde fica o registro de diagnóstico (ao lado do cofre, com o nome do cofre + .diag)."""
    with _TRAVA_DIAG:
        _DIAG["arq"] = os.path.abspath(caminho_cofre) + ".diag"
        _DIAG["pub"] = None


@_com_apoio_liberado
def diag_iniciar(caminho_cofre, pub):
    """Garante que o arquivo de registro existe e pertence a esta chave pública (senão recomeça vazio)."""
    arq = os.path.abspath(caminho_cofre) + ".diag"
    with _TRAVA_DIAG:
        _DIAG["arq"], _DIAG["pub"] = arq, pub
        try:
            with open(arq, "rb") as f:
                if f.read(DIAG_CAB) == DIAG_MAGIC + pub:
                    return
        except OSError:
            pass
        try:
            _gravar_diag_atomico(arq, DIAG_MAGIC + pub)
        except OSError:
            pass


def _diag_rotacionar(arq):
    """Mantém só os registros mais recentes (reescreve por arquivo temporário + troca atômica)."""
    with open(arq, "rb") as f:
        bruto = f.read()
    corpo = bruto[DIAG_CAB:]
    n = len(corpo) // DIAG_TAM
    novo = bruto[:DIAG_CAB] + corpo[max(0, n - DIAG_MANTER) * DIAG_TAM:n * DIAG_TAM]
    _gravar_diag_atomico(arq, novo)


def _diag_bytes(texto, n):
    """Texto (só nomes de código) em ASCII com no máximo n bytes, para caber no registro de tamanho fixo."""
    return str(texto or "").encode("ascii", "replace")[:n]


def _diag_local(ex=None, tb=None):
    """(tipo do erro, função onde parou, função que a chamou, linha) do ponto deste programa onde o erro ocorreu.
    Só nomes de classe/função e número de linha: nunca a mensagem do erro, caminhos ou valores."""
    tipo = type(ex).__name__ if ex is not None else ""
    nome = os.path.basename(__file__)
    quadros = []                                          # (arquivo é este?, linha, função), do mais externo ao mais interno
    if tb is None and ex is not None:
        tb = getattr(ex, "__traceback__", None)
    if tb is not None:
        t = tb
        while t is not None:
            c = t.tb_frame.f_code
            quadros.append((os.path.basename(c.co_filename) == nome, min(t.tb_lineno, 65535), c.co_name))
            t = t.tb_next
    else:                                                 # sem traceback (evento sem exceção): usa quem chamou o registro
        f = sys._getframe(1)
        while f is not None:
            c = f.f_code
            if c.co_name not in ("diag_registrar", "interno", "_diag_local", "diag_referencia"):
                quadros.insert(0, (os.path.basename(c.co_filename) == nome, min(f.f_lineno, 65535), c.co_name))
                if len(quadros) >= 6:
                    break
            f = f.f_back
    proprios = [q for q in quadros if q[0]] or quadros[:1]
    if not proprios:
        return tipo, "", "", 0
    linha, func = proprios[-1][1], proprios[-1][2]
    chamador = proprios[-2][2] if len(proprios) > 1 else ""
    return tipo, func, chamador, linha


def diag_referencia(ex=None, tb=None):
    """Linha curta para mostrar na hora do erro e para o suporte: versão, tipo do erro, função e linha."""
    tipo, func, _chamador, linha = _diag_local(ex, tb)
    partes = [f"v{_versao_num()}", tipo or "sem exceção", func or "?", f"L{linha}"]
    return " · ".join(partes)


@_com_apoio_liberado
def diag_registrar(codigo, ex=None, tb=None):
    """Acrescenta um registro cifrado ao diagnóstico. NUNCA levanta erro e nunca guarda texto, caminho ou segredo:
    só o código do evento, o errno do sistema, o tipo do erro, a função e a linha do programa, a versão e o minuto."""
    try:
        arq = _DIAG["arq"]
        if not arq:
            return
        err = 0
        if ex is not None:
            try:
                err = int(getattr(ex, "errno", 0) or 0)
            except (TypeError, ValueError):
                err = 0
            if not -2 ** 31 <= err < 2 ** 31:
                err = 0
        tipo, func, chamador, linha = _diag_local(ex, tb)
        dado = DIAG_REG.pack(2, int(codigo) & 0xFFFF, err, linha, _versao_num(), int(time.time() // 60) & 0xFFFFFFFF,
                             _diag_bytes(tipo, 24), _diag_bytes(func, 28), _diag_bytes(chamador, 28))
        with _TRAVA_DIAG:
            pub = _DIAG["pub"]
            if pub is None:
                with open(arq, "rb") as f:
                    cab = f.read(DIAG_CAB)
                if len(cab) != DIAG_CAB or cab[:len(DIAG_MAGIC)] != DIAG_MAGIC:
                    return                     # ainda não há registro (cofre nunca foi aberto aqui): nada a fazer
                pub = _DIAG["pub"] = cab[len(DIAG_MAGIC):]
            if os.path.getsize(arq) >= DIAG_CAB + DIAG_MAX * DIAG_TAM:
                _diag_rotacionar(arq)
            with open(arq, "ab") as f:
                f.write(_diag_selar(pub, dado))
    except (OSError, ValueError, AttributeError, ctypes.ArgumentError, TypeError):
        return None


def diag_ler(caminho_cofre, priv_bytes):
    """Igual a diag_ler_completo, mas cada registro traz só (minuto, código, errno, linha, versão)."""
    res = diag_ler_completo(caminho_cofre, priv_bytes)
    if res is None:
        return None
    return [r[:5] for r in res[0]], res[1]


def diag_ler_completo(caminho_cofre, priv_bytes):
    """Lê o registro com a chave privada do cofre. Devolve (lista de (minuto, código, errno, linha, versão, tipo, função,
    chamador), quantidade
    de registros que não passaram na autenticação) ou None se o arquivo é de outra chave/não existe."""
    arq = os.path.abspath(caminho_cofre) + ".diag"
    try:
        with open(arq, "rb") as f:
            bruto = f.read(DIAG_CAB + DIAG_MAX * DIAG_TAM * 4)
        pub = _bytes_pub(X25519PrivateKey.from_private_bytes(priv_bytes))
        if bruto[:DIAG_CAB] != DIAG_MAGIC + pub:
            return None
    except (OSError, ValueError):
        return None
    regs, ruins = [], 0
    corpo = bruto[DIAG_CAB:]
    for i in range(len(corpo) // DIAG_TAM):          # um registro cortado no fim (queda de energia) é ignorado
        try:
            v, cod, err, linha, ver, minuto, tipo, func, cham = DIAG_REG.unpack(
                _diag_abrir(priv_bytes, corpo[i * DIAG_TAM:(i + 1) * DIAG_TAM]))
            regs.append((minuto, cod, err, linha, ver, *(x.rstrip(b"\x00").decode("ascii", "replace")
                                                         for x in (tipo, func, cham))))
        except Exception:
            ruins += 1
    return regs, ruins


@_com_apoio_liberado
def diag_limpar(caminho_cofre, priv_bytes):
    """Esvazia o registro (mantém a chave pública)."""
    pub = _bytes_pub(X25519PrivateKey.from_private_bytes(priv_bytes))
    arq = os.path.abspath(caminho_cofre) + ".diag"
    with _TRAVA_DIAG:
        _DIAG["arq"], _DIAG["pub"] = arq, pub
        _gravar_diag_atomico(arq, DIAG_MAGIC + pub)


def diag_descrever(codigo, err):
    """Frase legível para um registro (só para mostrar dentro do cofre aberto)."""
    t = DIAG_CODIGOS.get(codigo, f"Evento {codigo}")
    return t + (f" – {_causa_io(err)}" if err else "")


def diag_relatorio(regs):
    """Texto simples (sem segredos) com todos os registros, do mais novo ao mais antigo, para copiar e enviar."""
    import datetime
    linhas = [f"Relatório de diagnóstico do Cofre de Senhas - programa v{_versao_num()}"]
    for minuto, cod, err, linha, ver, tipo, func, cham in reversed(regs):
        q = datetime.datetime.fromtimestamp(minuto * 60).strftime("%d/%m/%Y %H:%M")
        onde = f"{func or '?'} (linha {linha})" + (f", chamada por {cham}" if cham else "")
        linhas.append(f"- {q} | v{ver} | {diag_descrever(cod, err)} | erro: {tipo or '-'}"
                      f"{f' (errno {err})' if err else ''} | onde: {onde}")
    return "\n".join(linhas)


MAX_SENHA = 1024                      # maior senha mestra aceita (caracteres): acima disso só serve para esgotar CPU/memória
MAX_AVALIAR = 256                     # a estimativa de força olha no máximo estes caracteres (evita custo enorme em textos gigantes)
GC_PERIODICO_S = 120                  # coleta de lixo do Python a cada tanto tempo com o cofre aberto (junto da varredura de RAM)
BLOQUEIO_SEM_FOCO_S = 60            # fora do programa por tanto tempo (s): bloqueia e apaga as chaves da RAM
GERACOES_COPIA = 5                 # .bak1 (mais nova) até .bak5 (mais antiga)


def _copias(caminho):
    """Caminhos das cópias de segurança rotativas (.bak1 a .bak5) do cofre, da mais nova para a mais antiga."""
    return [f"{caminho}.bak{i}" for i in range(1, GERACOES_COPIA + 1)]


def _todas_as_copias(caminho):
    """Tudo que guarda uma versão antiga do cofre ao lado dele (inclusive o arquivo danificado)."""
    return (_copias(caminho) + [caminho + ".danificado", caminho + ".pre-v5", caminho + ".tmp"]
            + glob.glob(glob.escape(caminho) + ".*.danificado")
            + glob.glob(glob.escape(caminho) + ".*.tmp"))        # sobras de gravações interrompidas (um .tmp por processo)


def destruir_arquivo(caminho):
    """Sobrescreve e apaga UM arquivo (ex.: a planilha importada). Não mexe em nenhum irmão."""
    _destruir_um(caminho)


@_com_apoio_liberado
def destruir(caminho):
    """Autodestruição do cofre: sobrescreve o conteúdo e as cópias; arquivos auxiliares de trava podem permanecer."""
    for extra in _todas_as_copias(caminho):
        if os.path.exists(extra):
            try:
                _destruir_um(extra)
            except OSError:
                pass
    for extra in [caminho + ".diag", caminho + ".diag.tmp"] + \
            glob.glob(glob.escape(caminho) + ".diag.*.tmp"):        # o registro de diagnóstico também some
        try:
            _destruir_um(extra)
        except OSError:
            pass
    # Não desvincule as travas: outro processo pode estar usando o mesmo arquivo para sincronizar gravações.
    _destruir_um(caminho)


@_com_apoio_liberado
def apagar_copias(caminho):
    """Remove as cópias antigas (elas ainda abririam com a senha antiga). Retorna a lista das que NÃO
    foi possível apagar."""
    falhas = []
    for extra in _todas_as_copias(caminho):
        if os.path.exists(extra):
            try:
                _destruir_um(extra)
            except OSError:
                falhas.append(os.path.basename(extra))
            if os.path.exists(extra):
                falhas.append(os.path.basename(extra))
    return sorted(set(falhas))


def _rodar_copias(caminho):
    """Antes de gravar: guarda o arquivo atual como .bak1 e empurra as anteriores (.bak1 vira .bak2 ... .bak4 vira
    .bak5; a mais antiga sai). Se o arquivo atual é idêntico ao .bak1, não gasta uma geração."""
    try:
        try:
            with open(caminho, "rb") as f:
                atual = f.read(LIMITE_COFRE)
        except FileNotFoundError:
            return                                # primeira gravação: ainda não há o que copiar
        if atual[:6] != b"COFRE0":
            return
        h = _ler_cabecalho(atual)
        atual = bytearray(atual)
        atual[h["hl"]] = h["max_t"]               # a cópia nasce com o contador cheio (sem falso alarme)
        atual = bytes(atual)
        copias = _copias(caminho)
        try:
            with open(copias[0], "rb") as f:
                if f.read(LIMITE_COFRE + 1) == atual:
                    return
        except OSError:
            pass
        for i in range(len(copias) - 1, 0, -1):    # renomear é atômico: nunca deixa uma cópia pela metade
            if os.path.exists(copias[i - 1]):
                _trocar(copias[i - 1], copias[i])
        _gravar_atomico(copias[0], atual)
    except Exception as ex:
        diag_registrar(DIAG_COPIA, ex)             # cópia de segurança é bônus; nunca impede salvar


def restaurar_copia(caminho, ignoradas=()):
    """Troca o cofre danificado pela cópia de segurança válida mais recente. Retorna o nome usado ou None.
    O arquivo danificado é guardado como .danificado (nada é apagado)."""
    ignoradas = set(ignoradas)
    for b in _copias(caminho):
        if os.path.basename(b) in ignoradas:
            continue
        try:
            with open(b, "rb") as f:
                dados = f.read(LIMITE_COFRE)
            _ler_cabecalho(dados)
        except (OSError, ArquivoInvalido, ValueError, TypeError, struct.error):
            continue
        try:
            if os.path.exists(caminho):
                danificado = caminho + ".danificado"
                if os.path.exists(danificado):
                    danificado = caminho + "." + secrets.token_hex(4) + ".danificado"
                os.replace(caminho, danificado)
            _gravar_atomico(caminho, dados)
        except OSError:
            return None
        diag_registrar(DIAG_RESTAURADO)
        return os.path.basename(b)
    return None


def _destruir_um(caminho):
    """Apaga um arquivo sobrescrevendo-o antes (3 vezes); atalho ou hard link só perde o nome, para não atingir outro arquivo."""
    try:
        st = os.lstat(caminho)
        if stat.S_ISLNK(st.st_mode) or st.st_nlink > 1:
            # Atalho (link simbólico) ou arquivo com outros nomes (hard link): sobrescrever atingiria
            # outro arquivo. Só remove este nome.
            os.remove(caminho)
            return
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
    for sobra in [caminho + ".tmp"] + glob.glob(glob.escape(caminho) + ".*.tmp"):
        try:
            os.remove(sobra)
        except FileNotFoundError:
            pass


def _validar_params(t, m, p, max_t):
    """Recusa parâmetros de Argon2 absurdos (um arquivo adulterado poderia pedir memória infinita)."""
    if not (1 <= t <= 20 and 8192 <= m <= 1048576 and 1 <= p <= 16 and 1 <= max_t <= 50):
        raise ArquivoInvalido("Parâmetros do cofre fora do padrão (arquivo adulterado?).")


def _variantes(senha):
    """A mesma senha com acento pode ter bytes diferentes (NFC x NFD) conforme o teclado/sistema.
    Tenta as formas equivalentes (a tentativa já foi gasta uma única vez)."""
    vistos, saida = set(), []
    for f in (None, "NFC", "NFD", "NFKC"):
        s = senha if f is None else unicodedata.normalize(f, senha)
        if s not in vistos:
            vistos.add(s)
            saida.append(s)
    return saida


def _checar_checksum(bruto, hl):
    """v5: confere o checksum de cabeçalho + seção FIDO. Se não bater, o arquivo está danificado
    (bit-rot, cópia cortada): NÃO é senha errada, então não gasta tentativa nem destrói nada."""
    erro = ArquivoCorrompido("O cabeçalho do cofre está danificado (o pendrive pode ter um setor ruim).")
    try:
        _, fim = _ler_fido(bruto, hl + 1)
    except ArquivoInvalido:
        raise erro from None
    esperado = hashlib.sha256(bruto[:hl - 8] + bruto[hl + 1:fim]).digest()[:8]
    if not secrets.compare_digest(esperado, bruto[hl - 8:hl]):
        raise erro


def _hl_do_magic(magic):
    """Tamanho do cabeçalho de cada versão do formato (COFRE03 a COFRE05)."""
    return {MAGIC: HEADER_LEN5, MAGIC_V4: HEADER_LEN, MAGIC_V3: HEADER_LEN,
            MAGIC_V2: struct.calcsize(HEADER_V2_FMT), MAGIC_V1: HEADER_V1_LEN}.get(magic)


def _assinatura(bruto):
    """Hash do arquivo SEM o byte do contador (que muda a cada tentativa)."""
    hl = _hl_do_magic(bruto[:8])
    if hl is None or len(bruto) <= hl:
        return hashlib.sha256(bruto).digest()
    return hashlib.sha256(bruto[:hl] + bruto[hl + 1:]).digest()


def _ler_cabecalho(bruto):
    """Lê e valida o cabeçalho do arquivo (COFRE04/05) e devolve seus campos; ArquivoCorrompido se não bater."""
    magic = bruto[:8]
    if magic == MAGIC:
        fmt, versao = HEADER_FMT5, 5
    elif magic == MAGIC_V4:
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
    if versao == 5:
        _checar_checksum(bruto, hl)               # ANTES de qualquer outra coisa: bit-rot não gasta tentativa
        campos = campos[:-1]
    if versao >= 3:
        (_, t, m, p, max_t, modo, sal_pw, nonce_pw, wrap_pw,
         sal_k, nonce_k, wrap_k, nonce_c, nonce_a) = campos
        if modo not in (MODO_OU, MODO_E, MODO_S):
            raise ArquivoInvalido("Modo do cofre inválido (arquivo adulterado?).")
    else:
        (_, t, m, p, max_t, sal_pw, nonce_pw, wrap_pw, sal_k, nonce_k, wrap_k, nonce_a) = campos
        modo, nonce_c = MODO_OU, None
    _validar_params(t, m, p, max_t)
    fido, pc, ini = None, None, hl + 1
    if versao >= 4:
        fido, pc, ini = _ler_secao(bruto, hl + 1)
    if len(bruto) < ini + 16:
        raise ArquivoInvalido("Arquivo de cofre inválido ou corrompido.")
    aad = bruto[:hl] + bruto[hl + 1:ini]      # cabeçalho + seção FIDO (o contador fica de fora)
    return {"versao": versao, "hl": hl, "t": t, "m": m, "p": p, "max_t": max_t, "modo": modo,
            "sal_pw": sal_pw, "nonce_pw": nonce_pw, "wrap_pw": wrap_pw,
            "sal_k": sal_k, "nonce_k": nonce_k, "wrap_k": wrap_k,
            "nonce_c": nonce_c, "nonce_a": nonce_a, "contador": bruto[hl],
            "fido": fido, "pc": pc, "ini_dados": ini, "aad": aad}


def info_cofre(caminho):
    """(tentativas restantes, modo, exige_fido) sem precisar de senha."""
    with open(caminho, "rb") as f:
        bruto = f.read(LIMITE_COFRE)
    if bruto[:8] == MAGIC_V1 and len(bruto) > HEADER_V1_LEN:
        return bruto[HEADER_V1_LEN], MODO_OU, False
    h = _ler_cabecalho(bruto)
    return h["contador"], h["modo"], bool(h["fido"])


def info_pc(caminho):
    """(exige_pc, este_computador_esta_autorizado) sem precisar de senha. Cofre sem a exigência: (False, True)."""
    try:
        with open(caminho, "rb") as f:
            bruto = f.read(LIMITE_COFRE)
        h = _ler_cabecalho(bruto)
    except (OSError, ArquivoInvalido, ArquivoCorrompido):
        return False, True
    if not h.get("pc"):
        return False, True
    return True, _achar_g(h["pc"]) is not None


def tentativas_restantes(caminho):
    """Quantas tentativas erradas ainda restam, lendo só o cabeçalho (sem senha)."""
    return info_cofre(caminho)[0]


def _hash_registros(itens):
    """SHA-256 (hex) da contagem e dos IDs dos registros (os IDs são sorteados e não revelam nada). Entra no manifesto
    interno para pegar registros faltando ou sobrando; o conteúdo já é protegido pela criptografia autenticada, e
    por isso este cálculo não serializa os dados de novo (não deixa cópias de senhas na memória)."""
    ids = sorted(str(r.get("id", "")) for r in itens)
    return hashlib.sha256((str(len(itens)) + "\n" + "\n".join(ids)).encode("utf-8")).hexdigest()


def _json_do_cofre(registros, meta):
    """Serializa o conteúdo do cofre (JSON, só ASCII) num bytearray JÁ no tamanho final, preenchido com zeros até
    múltiplo de TAM_BLOCO (o que esconde o tamanho real). Faz um registro por vez e apaga cada pedaço intermediário:
    um json.dumps do cofre inteiro cresceria um buffer por realocação e deixaria cópias das senhas em blocos
    liberados da memória; assim sobram só blocos pequenos, que varrer_memoria_livre sobrescreve."""
    pedacos, sensiveis = [], []

    def sensivel(obj):
        """Serializa um objeto, guarda o resultado para apagar depois e devolve os bytes."""
        t = json.dumps(obj, ensure_ascii=True)
        b = t.encode("ascii")
        zerar_objeto(t)
        sensiveis.append(b)
        return b
    try:
        pedacos.append(b'{"itens": [')
        for i, r in enumerate(registros):
            if i:
                pedacos.append(b", ")
            pedacos.append(sensivel(r))
        pedacos.append(b'], "meta": ')
        pedacos.append(sensivel(meta))
        pedacos.append(b', "n": %d, "h": "%s"}' % (len(registros), _hash_registros(registros).encode("ascii")))
        total = sum(len(x) for x in pedacos)
        dados = bytearray(total + TAM_BLOCO - total % TAM_BLOCO)
        pos = 0
        for x in pedacos:
            dados[pos:pos + len(x)] = x
            pos += len(x)
        return dados
    finally:
        for x in sensiveis:
            zerar_objeto(x)


def _sanear_itens(itens):
    """Deixa os itens recém-decifrados no ESQUEMA que o resto do programa espera, sem tocar em dado válido.

    Por que existe: o arquivo é autenticado (ninguém de fora consegue alterá-lo), mas um item pode vir com formato
    errado de uma versão antiga, de uma importação ou de um defeito: o PIN como lista, o texto como número ou nulo,
    o `id` ausente ou repetido. Antes isso passava e quebrava DEPOIS, longe da causa (auditoria de senhas com
    AttributeError, lista da tela com id repetido). Aqui, uma vez só, na abertura:
      - campo textual conhecido (CAMPOS, exceto `ativo`) que não é texto vira texto: None -> "", número/booleano -> str,
        lista/dict -> JSON;
      - valor legado de `ativo` que não seja booleano vira booleano, preservando a regra de `_item_ativo`;
      - `id` ausente, não textual ou repetido ganha um id novo (o primeiro item com aquele id mantém o seu);
      - campos desconhecidos são mantidos como estão (compatível com versões futuras).
    Devolve quantos itens foram corrigidos (0 num cofre normal: nada muda e nada é regravado por isso)."""
    corrigidos = 0
    vistos = set()
    for item in itens:
        mudou = False
        for campo in CAMPOS:
            if campo == "ativo":
                if campo in item and not isinstance(item[campo], bool):
                    item[campo] = _item_ativo(item)
                    mudou = True
                continue
            valor = item.get(campo, "")
            if isinstance(valor, str):
                continue
            if campo not in item and valor == "":
                continue
            try:
                if valor is None:
                    novo_valor = ""
                elif isinstance(valor, (bool, int, float)):
                    novo_valor = str(valor)        # inteiro com mais de 4300 dígitos: ValueError do próprio Python
                else:
                    novo_valor = json.dumps(valor, ensure_ascii=False)
            except (TypeError, ValueError, RecursionError, OverflowError):
                novo_valor = ""                    # irrecuperável (aninhamento absurdo, número gigante): campo vazio
            item[campo] = novo_valor
            mudou = True
        ident = item.get("id")
        if not isinstance(ident, str) or not ident or ident in vistos:
            ident = secrets.token_hex(8)
            while ident in vistos:
                ident = secrets.token_hex(8)
            item["id"] = ident
            mudou = True
        vistos.add(ident)
        corrigidos += mudou
    return corrigidos


def _decifrar_dados(chave, h, bruto):
    """Decifra a seção de dados (ChaCha20-Poly1305 sobre AES-256-GCM) e devolve o conteúdo; apaga da memória os intermediários."""
    corpo = bruto[h["ini_dados"]:]
    interno = None
    k_cha = k_aes = None
    try:
        if h["versao"] >= 3:
            k_cha, k_aes = _subchaves(chave)
            interno = AESGCM(k_aes).decrypt(h["nonce_a"], corpo, h["aad"])
            texto = ChaCha20Poly1305(k_cha).decrypt(h["nonce_c"], interno, h["aad"])
        else:
            texto = AESGCM(chave).decrypt(h["nonce_a"], corpo, h["aad"])
        limpo = texto.rstrip(b"\0")
        decodificado = limpo.decode("utf-8")
        try:
            conteudo = json.loads(decodificado)
        finally:                      # apaga (melhor esforço) as cópias do texto em claro que não vão mais ser usadas
            for _o in (decodificado, limpo, texto, interno):
                zerar_objeto(_o)
    finally:
        # as subchaves por operação (deriváveis de novo a partir da DEK) também não deveriam sobreviver na RAM
        # além do necessário — mesmo tratamento que o resto dos segredos desta função.
        zerar_objeto(k_cha)
        zerar_objeto(k_aes)
    if isinstance(conteudo, list):                       # versões anteriores: só a lista de itens
        if all(isinstance(r, dict) for r in conteudo):
            _sanear_itens(conteudo)
        return conteudo, {}
    if not isinstance(conteudo, dict) or not isinstance(conteudo.get("itens"), list):
        raise ValueError
    meta = conteudo.get("meta") if isinstance(conteudo.get("meta"), dict) else {}
    if not all(isinstance(r, dict) for r in conteudo["itens"]):
        raise ValueError                                  # itens fora do esquema: arquivo danificado
    if "n" in conteudo or "h" in conteudo:               # manifesto interno: contagem e hash dos registros
        if conteudo.get("n") != len(conteudo["itens"]) or not isinstance(conteudo.get("h"), str):
            raise ValueError
        if not secrets.compare_digest(_hash_registros(conteudo["itens"]), conteudo["h"]):
            raise ValueError
    _sanear_itens(conteudo["itens"])                     # depois da conferência de integridade (o hash é do original)
    return conteudo["itens"], meta


def _seq_de(meta):
    """Contador de salvamentos ("seq") guardado dentro dos dados cifrados (0 se não houver ou for inválido)."""
    try:
        v = int((meta or {}).get("seq", 0))
        return v if 0 <= v < 2 ** 62 else 0
    except (TypeError, ValueError):
        return 0


def _maior_seq_nas_copias(caminho, chave):
    """Maior contador de salvamentos entre as cópias .bak1-.bak5 que abrem com esta chave de dados (0 se nenhuma).
    Não deriva senha nenhuma (usa a chave já aberta), então é rápido. Cópia ilegível, de outra chave ou de formato
    antigo é ignorada. Cada cópia só pode ser MAIS ANTIGA que o arquivo principal; se alguma for mais nova, o
    principal foi trocado por uma versão velha (ou o usuário restaurou uma cópia de propósito)."""
    maior = 0
    for b in _copias(caminho):
        try:
            with open(b, "rb") as f:
                bruto = f.read(LIMITE_COFRE + 1)
            if len(bruto) > LIMITE_COFRE or bruto[:8] == MAGIC_V1:
                continue
            itens, meta = _decifrar_dados(chave, _ler_cabecalho(bruto), bruto)
            for r in itens:                      # só queremos o contador: apaga do que for texto (objetos desta leitura)
                for v in r.values():
                    zerar_objeto(v)
            maior = max(maior, _seq_de(meta))
        except (OSError, ArquivoInvalido, InvalidTag, ValueError, TypeError, UnicodeError, struct.error):
            continue
    return maior


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
    """Grava no arquivo uma tentativa a menos; no zero, destrói o cofre."""
    restantes = contador - 1
    try:
        with open(caminho, "r+b") as f:
            f.seek(posicao)
            f.write(bytes([restantes]))
            f.flush()
            os.fsync(f.fileno())
    except OSError as ex:
        novo = ErroGravacao("Não consigo gravar no pendrive (ele está protegido contra gravação, "
                            "cheio ou foi removido). O cofre precisa registrar a tentativa antes de abrir. "
                            "Nenhuma tentativa foi gasta.")
        novo.protegido = _e_protecao_de_escrita(ex)
        raise novo from ex
    return restantes


def gastar_tentativa_arquivo(caminho):
    """Gasta UMA tentativa do cofre em 'caminho' (usada quando a chave digitada vem repetidamente num formato
    impossível: isso deixa de ser 'erro de digitação' e passa a contar). No zero, destrói o cofre.
    Devolve quantas tentativas restam."""
    with open(caminho, "rb") as f:
        bruto = f.read(LIMITE_COFRE + 1)
    h = _ler_cabecalho(bruto)
    if h["contador"] > h["max_t"] or h["contador"] == 0:
        raise ArquivoCorrompido(MSG_CONTADOR_DANIFICADO)
    restantes = _gastar_tentativa(caminho, h["hl"], h["contador"])
    if restantes == 0:
        destruir(caminho)
        raise CofreDestruido()
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


_SIL = len(_CONSOANTES) * len(_VOGAIS)                  # 75 sílabas possíveis


def gerar_frase(palavras=5, maiuscula=True, numero=True, separador="-"):
    """Senha fácil de lembrar: palavras pronunciáveis aleatórias (ex.: Bafido-luvemo-tasi-...-7).
    Cada palavra é sorteada UNIFORMEMENTE entre todas as palavras de 2 ou 3 sílabas
    (75^2 + 75^3 possibilidades), então a força calculada em bits_frase é exata."""
    ws = []
    for _ in range(max(3, min(int(palavras), 10))):
        r = secrets.randbelow(_SIL ** 2 + _SIL ** 3)
        nsil = 2 if r < _SIL ** 2 else 3
        if nsil == 3:
            r -= _SIL ** 2
        sils = []
        for _i in range(nsil):
            r, d = divmod(r, _SIL)
            sils.append(_CONSOANTES[d // len(_VOGAIS)] + _VOGAIS[d % len(_VOGAIS)])
        ws.append("".join(sils))
    if maiuscula:
        ws[0] = ws[0].capitalize()
    s = separador.join(ws)
    if numero:
        s += separador + str(secrets.randbelow(100))
    return s


def bits_frase(palavras, numero=True):
    """Bits de entropia de uma frase sorteada (palavras da lista e número)."""
    import math
    por_palavra = math.log2(_SIL ** 2 + _SIL ** 3)      # sorteio uniforme sobre 2 ou 3 sílabas
    return palavras * por_palavra + (math.log2(100) if numero else 0)


def gerar_pin(n=6):
    """PIN numérico aleatório, recusando os óbvios (1234, 0000, 1212, anos...)."""
    n = max(4, min(int(n), 12))
    while True:
        p = "".join(str(secrets.randbelow(10)) for _ in range(n))
        if not pin_obvio(p):
            return p


def pin_obvio(p):
    """True se o PIN é previsível (repetido, sequência, data comum)."""
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
    s = senha[:MAX_AVALIAR]               # texto gigante não deve custar CPU/memória (negação de serviço)
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
    # Palavras: o atacante testa palavras inteiras do dicionário (com trocas óbvias como Tr0ub4dor e números no fim),
    # não letra por letra. Vale para UMA palavra com enfeites (Gabriel2020, Tr0ub4dor&3) e para frases.
    leet = str.maketrans("013457@$!|", "oieastasil")
    partes = [p for p in re.split(r"[\s\-_.,;:/+]+", s) if p]

    def nucleo(w):
        """Separa um trecho em (prefixo, miolo, sufixo): prefixo/sufixo são números e símbolos nas pontas."""
        m = re.fullmatch(r"([^A-Za-zÀ-ÿ]*)(.*?[A-Za-zÀ-ÿ])([^A-Za-zÀ-ÿ]*)", w)
        return m.groups() if m else ("", w, "")

    def parece_palavra(w):
        """True se o miolo parece uma palavra comum (mesmo com troca de letras por números)."""
        n = unicodedata.normalize("NFD", w.translate(leet))
        n = "".join(ch for ch in n if not unicodedata.combining(ch))
        if len(w) < 3 or not n.isalpha() or not (w.islower() or w.istitle() or w.isupper()
                                                  or n.islower() or n.istitle()):
            return False
        nl = n.lower()
        vogais = sum(ch in "aeiou" for ch in nl) / len(nl)
        return 0.25 <= vogais <= 0.75 and not re.search(r"[^aeiou]{4,}", nl)

    def bits_palavra(w):
        """Bits para adivinhar um trecho-palavra: ~14,3 bits por palavra comum (20 mil) mais as 'enfeites' previsíveis.
        Palavras longas não são do dicionário (juntam-se várias): cada letra além de 8 soma 2,6 bits."""
        pre, miolo, suf = nucleo(w)
        base = math.log2(20000) + max(0, len(miolo) - 8) * 2.6
        base += 2 * sum(ch in "013457@$!|" for ch in miolo)                       # trocas de letra por número/símbolo
        base += 1 if miolo[:1].isupper() else 0
        base += sum(math.log2(10) if ch.isdigit() else 5 for ch in pre + suf)       # números/símbolos nas pontas
        return base

    palavras = [p for p in partes if parece_palavra(nucleo(p)[1])]
    letras_em_palavras = sum(len(nucleo(p)[1]) for p in palavras)
    if palavras and letras_em_palavras >= 0.6 * sum(len(p) for p in partes):
        resto = [p for p in partes if p not in palavras]
        bits_frase_est = sum(bits_palavra(p) for p in palavras)
        bits_frase_est += sum(len(p) * math.log2(10 if p.isdigit() else 95) for p in resto)
        if bits_frase_est < bits:
            bits = bits_frase_est
            if len(palavras) == 1:
                dicas.append("É uma palavra comum com enfeites (número no fim, letra trocada): fácil de adivinhar. "
                             "Use uma senha aleatória do gerador.")
            elif len(palavras) < 5:
                dicas.append("Frase com poucas palavras: use 5 ou mais palavras sem relação entre si, ou "
                             "uma senha aleatória do gerador.")
    # padrões que reduzem a força real
    unicos = len(set(s))
    if unicos < len(s) * 0.5:
        # poucos caracteres diferentes: o resto é repetição previsível (aaaa..., abab...)
        reduzido = min(bits, unicos * math.log2(max(pool, 2)) + (len(s) - unicos) * 1.0)
        if reduzido < bits:
            bits = reduzido
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
    # o tamanho também conta: senha curta nunca passa de certa nota, por mais "misturada" que pareça
    teto = 35 if len(s) < 8 else 55 if len(s) < 10 else 75 if len(s) < 12 else None
    if teto is not None and bits > teto:
        bits = teto
        dicas.append(f"Tem só {len(s)} caracteres: quanto mais longa, mais difícil de quebrar (use 14 ou mais).")
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
    """Conta maiúsculas, minúsculas, dígitos e símbolos de uma senha."""
    mai = sum(c.isupper() for c in senha)
    mi = sum(c.islower() for c in senha)
    num = sum(c.isdigit() for c in senha)
    sim = len(senha) - mai - mi - num
    return {"total": len(senha), "maiusculas": mai, "minusculas": mi, "numeros": num, "simbolos": sim}


def texto_composicao(senha):
    """Descreve em texto a composição da senha (ex.: '2 maiúsculas, 8 minúsculas...')."""
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


_CACHE_FORCA = {}
_CACHE_FORCA_MAX = 1000          # teto de itens: ao passar disso descarta o mais antigo (FIFO)


def _forca_em_cache(senha):
    """avaliar_forca com cache. A chave é o SHA-256 da senha (a senha em si não fica guardada); o cache
    é esvaziado ao bloquear o cofre."""
    k = hashlib.sha256(senha.encode("utf-8", "surrogatepass")).digest()
    r = _CACHE_FORCA.get(k)
    if r is None:
        while len(_CACHE_FORCA) >= _CACHE_FORCA_MAX:
            _CACHE_FORCA.pop(next(iter(_CACHE_FORCA)))      # dicts guardam a ordem de inserção: sai o mais antigo
        r = _CACHE_FORCA[k] = avaliar_forca(senha)
    return r


HIBP_URL = "https://api.pwnedpasswords.com/range/"


def hibp_dividir(senha):
    """(prefixo de 5, sufixo de 35) do SHA-1 da senha, em maiúsculas. Só o prefixo pode sair do computador."""
    h = hashlib.sha1(senha.encode("utf-8", "surrogatepass"), usedforsecurity=False).hexdigest().upper()
    par = (h[:5], h[5:])
    zerar_objeto(h)
    return par


def _hibp_baixar(prefixo, timeout=15):
    """Baixa a lista de sufixos conhecidos daquele prefixo (k-anonymity do Have I Been Pwned).
    Sai pela rede SOMENTE os 5 caracteres do prefixo, por HTTPS com verificação do certificado."""
    if not re.fullmatch(r"[0-9A-F]{5}", prefixo):
        raise ValueError("prefixo inválido")
    import urllib.request
    if not HIBP_URL.startswith("https://"):          # nunca aceita file:, ftp: nem http: (sem criptografia)
        raise ValueError("endereço do serviço precisa ser HTTPS")
    pedido = urllib.request.Request(HIBP_URL + prefixo, headers={"Add-Padding": "true", "User-Agent": "CofreSenhas-local"})  # noqa: S310 - https conferido na linha anterior
    with urllib.request.urlopen(pedido, timeout=timeout) as r:   # nosec B310 - esquema https conferido acima  # noqa: S310
        if r.status != 200:
            raise OSError(f"o serviço respondeu {r.status}")
        dados = r.read(4 * 1024 * 1024 + 1)
    if len(dados) > 4 * 1024 * 1024:
        raise OSError("resposta grande demais")
    return dados.decode("ascii", "replace")


def hibp_vezes(sufixo, texto):
    """Quantas vezes o sufixo aparece na resposta (0 = não achou). Linhas de enchimento (contagem 0) não contam."""
    import hmac
    achou = 0
    for linha in texto.splitlines():
        h, _, n = linha.strip().partition(":")
        if hmac.compare_digest(h.strip().upper().encode("ascii", "replace"), sufixo.encode("ascii", "replace")):
            try:
                achou = max(achou, int(n))
            except ValueError:
                pass
    return achou


def hibp_verificar(pedidos, baixar=None, ao_andar=None, cancelar=None):
    """pedidos = [(rótulo, prefixo, sufixo)]. Faz UMA consulta por prefixo diferente e compara os sufixos aqui.
    Devolve [(rótulo, vezes)] só dos que apareceram em vazamentos, do mais vazado para o menos."""
    baixar = baixar or _hibp_baixar
    grupos = {}
    for rotulo, pre, suf in pedidos:
        grupos.setdefault(pre, []).append((rotulo, suf))
    achados = []
    for i, (pre, lista) in enumerate(grupos.items(), 1):
        if cancelar is not None and cancelar():
            break
        texto = baixar(pre)
        for rotulo, suf in lista:
            n = hibp_vezes(suf, texto)
            if n > 0:
                achados.append((rotulo, n))
        if ao_andar is not None:
            ao_andar(i)
    return sorted(achados, key=lambda x: -x[1])


def limpar_cache_auditoria():
    """Esvazia o cache das avaliações de força (chamado ao bloquear)."""
    _CACHE_FORCA.clear()


def auditar_cofre(registros):
    """Verifica todas as senhas do cofre. Retorna lista de (item, campo, problema, recomendação, gravidade)."""
    achados = []
    usos = {}
    nomes_cache, contagem, multi, ordenados = {}, {}, {}, {}
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
            grupo = usos[v]
            if v not in multi:
                multi[v] = len({id(x[0]) for x in grupo}) > 1
            if multi[v]:                   # repetida (sem varrer o grupo inteiro a cada item: evita custo quadrático)
                chave_g = (v, r.get("servico", "?"))
                if chave_g not in nomes_cache:
                    cont = contagem.get(v)
                    if cont is None:
                        cont = contagem[v] = {}
                        for x in grupo:
                            n_ = x[0].get("servico", "?")
                            cont[n_] = cont.get(n_, 0) + 1
                    proprio = r.get("servico", "?")
                    if v not in ordenados:
                        ordenados[v] = sorted(cont)
                    saida, tam = [], 0
                    for n_ in ordenados[v]:          # só os primeiros nomes (a mensagem corta em 80 caracteres)
                        if n_ == proprio and cont[n_] == 1:
                            continue
                        saida.append(n_)
                        tam += len(n_) + 2
                        if tam > 90:
                            break
                    nomes_cache[chave_g] = ", ".join(saida)[:80]
                nomes = nomes_cache[chave_g]
                outros = True
            else:
                outros = False
            if outros:
                achados.append((r, campo, "Senha REPETIDA", f"Também usada em: {nomes}. Troque e gere "
                                "uma senha única para cada conta.", 0))
            nota, rot, bits, dicas = _forca_em_cache(v)
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
    """Falha ao imprimir (sem impressora, cancelado ou impressora que gera arquivo)."""
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
        """Estrutura PRINTDLGW do Windows (caixa de diálogo de impressão)."""
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
        """Estrutura DOCINFOW do Windows (nome do documento na fila de impressão)."""
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
    """True se a impressora grava em arquivo (PDF, XPS, OneNote...), o que deixaria o segredo no disco."""
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
        """Cria uma fonte GDI do tamanho em pontos pedido (negrito opcional)."""
        return gdi.CreateFontW(-int(pt * dpi_y / 72), 0, 0, 0, 700 if negrito else 400, 0, 0, 0, 1,
                               0, 0, 5, 0x31, "Consolas")

    f_titulo, f_rot, f_valor, f_texto = fonte(15, True), fonte(10, True), fonte(13, True), fonte(9)
    di = _DOCINFOW()
    di.cbSize = ctypes.sizeof(_DOCINFOW)
    di.lpszDocName = "Documento_Sistema"  # nome genérico na fila de impressão (não revela o que é)
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
    _u32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    _u32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    _u32.RegisterClipboardFormatW.restype = wintypes.UINT
    _u32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    _k32.GlobalAlloc.restype = wintypes.HGLOBAL
    _k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    _k32.GlobalLock.restype = ctypes.c_void_p
    _k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    _k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    _k32.GlobalFree.restype = wintypes.HGLOBAL
    _k32.GlobalFree.argtypes = [wintypes.HGLOBAL]


_MUTEX = None
_HOOKS = []


def sistema_de_arquivos(caminho):
    """Nome do sistema de arquivos do volume do cofre em MAIÚSCULAS (NTFS, EXFAT, FAT32, REFS...), ou '' se não der
    para saber (não é Windows, caminho de rede, erro). Só consulta; não grava nada."""
    if not EH_WINDOWS:
        return ""
    try:
        raiz = os.path.splitdrive(os.path.abspath(caminho))[0]
        if len(raiz) != 2 or raiz[1] != ":":
            return ""
        nome = ctypes.create_unicode_buffer(64)
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.GetVolumeInformationW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_void_p,
                                            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32]
        if not k.GetVolumeInformationW(raiz + "\\", None, 0, None, None, None, nome, 64):
            return ""
        return nome.value.strip().upper()
    except Exception:
        return ""


def hibernacao_ligada():
    """True se a hibernação está ligada neste Windows (o Windows grava a RAM inteira em hiberfil.sys ao hibernar, e chaves
    ou senhas abertas iriam junto para o disco do computador); False se desligada; None se não der para saber (não é
    Windows ou o registro não respondeu). Só lê o registro; não precisa de administrador."""
    if not EH_WINDOWS:
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Power") as k:
            return bool(winreg.QueryValueEx(k, "HibernateEnabled")[0])
    except Exception:
        return None


AVISO_HIBERNACAO = ("A hibernação está LIGADA neste computador: se ele hibernar com o cofre aberto, o Windows grava a memória "
                    "(com senhas e chaves) no disco dele. O programa bloqueia antes de hibernar, mas o ideal é desligar a "
                    "hibernação (powercfg /h off, como administrador) e usar BitLocker no disco C:.")


def aviso_sistema_de_arquivos(fs):
    """Texto de alerta quando o volume NÃO guarda permissões de arquivo (FAT/FAT32/exFAT); '' para NTFS/ReFS/desconhecido.
    Sem permissões, qualquer programa deste PC pode trocar o .exe e o cofre.dat: o BitLocker To Go passa a ser obrigatório."""
    if str(fs).upper() in ("FAT", "FAT32", "EXFAT"):
        return (f"Este pendrive está em {fs}, que NÃO guarda permissões de arquivo: qualquer programa deste computador "
                "pode trocar o programa ou o cofre. O BitLocker To Go no pendrive é OBRIGATÓRIO (e o ideal é formatar "
                "em NTFS). O arquivo cofre.dat continua cifrado, mas o programa poderia ser trocado por um falso.")
    return ""


NOME_AVISOS_VISTOS = "avisos_vistos.json"   # avisos informativos que o usuário já viu (aparecem só 1 vez, não a cada abertura)


def _caminho_avisos(pasta=None):
    """Caminho do arquivo que lembra quais avisos iniciais já foram mostrados (fica ao lado do programa)."""
    return os.path.join(pasta or pasta_base(), NOME_AVISOS_VISTOS)


def aviso_ja_visto(texto, pasta=None):
    """True se este aviso informativo (identificado pelo hash do texto) já foi mostrado antes neste pendrive.
    Qualquer falha de leitura conta como 'não visto': na dúvida, avisa."""
    try:
        with open(_caminho_avisos(pasta), encoding="utf-8") as f:
            vistos = json.load(f)
        return hashlib.sha256(str(texto).encode("utf-8")).hexdigest()[:16] in vistos.get("vistos", [])
    except (OSError, ValueError, AttributeError):
        return False


def marcar_aviso_visto(texto, pasta=None):
    """Guarda que o aviso foi mostrado (só o hash do texto; nada secreto). Falha de gravação é ignorada."""
    try:
        caminho = _caminho_avisos(pasta)
        try:
            with open(caminho, encoding="utf-8") as f:
                vistos = list(json.load(f).get("vistos", []))
        except (OSError, ValueError, AttributeError):
            vistos = []
        h = hashlib.sha256(str(texto).encode("utf-8")).hexdigest()[:16]
        if h not in vistos:
            vistos.append(h)
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump({"vistos": vistos[-20:]}, f)
    except OSError:
        pass


NOME_PASTA_TEMP = ".tmp_cofre"              # pasta temporária PRIVADA do programa (fica ao lado do .exe, no pendrive)
NOME_MARCADOR_NTFS = "exigir_ntfs.txt"      # se este arquivo existir ao lado do .exe, o cofre só abre em NTFS/ReFS
_TEMP_PRIVADO = {"pasta": None}


# ---- ARQUIVOS DE APOIO ESCONDIDOS E PROTEGIDOS (só no programa compilado, no Windows) --------------------------------
# Depois da instalação a pasta do cofre não deve exibir nem deixar editar nada além do programa (.exe): o cofre
# (.dat) e suas cópias/registros/pastas de apoio ficam com os atributos Oculto + Sistema + Somente leitura. O .exe
# continua SEMPRE visível e sem essas marcas -- é a ÚNICA coisa que o usuário precisa ver e abrir, como qualquer
# programa instalado. Não existe nenhum .bat nem .sha256 "ao lado" dele (versões antigas tinham Abrir_Cofre.bat +
# CofreSenhas.sha256; foram removidos de propósito: um arquivo solto na mesma pasta pode ser trocado JUNTO com o
# .exe por quem já tem acesso de escrita ali, então não protegia contra ninguém -- ver verificar_integridade() no
# App e MODELO_DE_AMEACAS.md). Ao ABRIR o cofre os atributos são retirados (precisa gravar); ao FECHAR, voltam. Se o
# programa cair, os arquivos ficam visíveis (falha segura: nada fica "preso"). É uma camada de DISCRETO/ANTI-
# -ACIDENTE, não de controle de acesso: quem abre "mostrar ocultos" ainda vê os arquivos. A proteção real do
# conteúdo é a cifra (e o BitLocker do pendrive).
_ATTR_SOMENTE_LEITURA = 0x1
_ATTR_OCULTO = 0x2
_ATTR_SISTEMA = 0x4
_ATTR_DIRETORIO = 0x10
NOMES_APOIO_FIXOS = (NOME_AVISOS_VISTOS, "instalacao_detalhada.log", "logs", NOME_PASTA_TEMP,
                     NOME_MARCADOR_NTFS)


def _ler_atributos(caminho):
    """Atributos de arquivo do Windows (None se não for Windows ou se o arquivo não existe)."""
    if not EH_WINDOWS:
        return None
    try:
        v = ctypes.windll.kernel32.GetFileAttributesW(str(caminho))
    except Exception:
        return None
    return None if v in (-1, 0xFFFFFFFF) else int(v)


def _gravar_atributos(caminho, valor):
    """Grava os atributos de arquivo do Windows. True se deu certo."""
    if not EH_WINDOWS:
        return False
    try:
        return bool(ctypes.windll.kernel32.SetFileAttributesW(str(caminho), int(valor)))
    except Exception:
        return False


def ocultacao_ativa():
    """True se este processo deve esconder os arquivos de apoio: só no Windows e só no programa compilado
    (rodando o .py solto, a pasta é de desenvolvimento e nada é escondido). COFRE_OCULTAR=1 força (testes)."""
    if os.environ.get("COFRE_OCULTAR") == "1":
        return True
    if os.environ.get("COFRE_OCULTAR") == "0":
        return False
    return EH_WINDOWS and ("__compiled__" in globals() or bool(getattr(sys, "frozen", False)))


def arquivos_de_apoio(caminho_cofre, executavel=None):
    """Lista (só os que existem) de tudo que o cofre deixa na pasta e deve ficar escondido: o cofre e todo arquivo que
    começa com o nome dele (.bak1-.bak5, .diag, .lock, .danificado, ...), e as pastas/arquivos de apoio (logs,
    avisos, temporária). NUNCA inclui o programa (.exe) nem qualquer .bat nem arquivos do usuário -- o .exe é a
    única coisa que deve continuar sempre visível na pasta. 'executavel' só serve para limpar um .sha256 deixado
    por uma instalação de versão antiga (hoje o instalador não cria mais esse arquivo ao lado do programa)."""
    pasta = os.path.dirname(os.path.abspath(caminho_cofre))
    nome = os.path.basename(caminho_cofre)
    achados = []
    try:
        itens = os.listdir(pasta)
    except OSError:
        return achados
    exe = os.path.basename(executavel) if executavel else None
    por_nome = set(NOMES_APOIO_FIXOS)
    if exe:
        por_nome.add(os.path.splitext(exe)[0] + ".sha256")   # limpeza de instalação antiga (não é mais criado)
    for item in sorted(itens):
        if item.lower().endswith(".bat"):
            continue
        if item in por_nome or item == nome or item.startswith(nome + "."):
            achados.append(os.path.join(pasta, item))
    return achados


def _familia_do_cofre(caminho_cofre, executavel=None):
    """Só o cofre e as cópias/trava/diagnóstico dele (nome do cofre + '.algo'); sem avisos, logs, pasta temporária."""
    nome = os.path.basename(caminho_cofre)
    return [a for a in arquivos_de_apoio(caminho_cofre, executavel)
            if os.path.basename(a) == nome or os.path.basename(a).startswith(nome + ".")]


def ocultar_apoio(caminho_cofre, executavel=None, so_cofre=False):
    """Esconde e protege os arquivos de apoio (Oculto+Sistema+Somente leitura; pastas: Oculto+Sistema).
    so_cofre=True marca apenas a família do cofre (usado durante a sessão, ver apoio_liberado).
    Retorna quantos foram marcados. Nunca levanta erro: é uma camada extra, não pode derrubar o programa."""
    n = 0
    for arq in (_familia_do_cofre(caminho_cofre, executavel) if so_cofre else arquivos_de_apoio(caminho_cofre, executavel)):
        atual = _ler_atributos(arq)
        if atual is None:
            continue
        marca = _ATTR_OCULTO | _ATTR_SISTEMA
        if not (atual & _ATTR_DIRETORIO):
            marca |= _ATTR_SOMENTE_LEITURA
        if _gravar_atributos(arq, atual | marca):
            n += 1
    return n


def revelar_apoio(caminho_cofre, executavel=None, so_cofre=False):
    """Desfaz ocultar_apoio (precisa ser feito antes de gravar: arquivo oculto/somente leitura não se sobrescreve).
    so_cofre=True libera apenas a família do cofre. Retorna quantos foram liberados."""
    n = 0
    for arq in (_familia_do_cofre(caminho_cofre, executavel) if so_cofre else arquivos_de_apoio(caminho_cofre, executavel)):
        atual = _ler_atributos(arq)
        if atual is None:
            continue
        sem = atual & ~(_ATTR_OCULTO | _ATTR_SISTEMA | _ATTR_SOMENTE_LEITURA)
        if sem == atual or _gravar_atributos(arq, sem):
            n += 1
    return n


# --- Ocultação DURANTE a sessão: o cofre e as cópias ficam escondidos o tempo todo e só são liberados no instante de
# cada operação que grava (salvar, abrir/contar tentativa, criar, apagar, diagnóstico). Antes só escondiam ao sair, então
# com o programa aberto (ou depois de um fechamento brusco) o arquivo ficava à vista no Explorer.
_APOIO = {"caminho": None, "exe": None, "prof": 0}
_APOIO_TRAVA = threading.Lock()        # protege só o contador de profundidade (gravações podem vir de outra thread)


def apoio_ativar(caminho_cofre, executavel=None):
    """Liga a ocultação contínua para este cofre e já esconde a família dele agora."""
    with _APOIO_TRAVA:
        _APOIO.update(caminho=caminho_cofre, exe=executavel, prof=0)
    ocultar_apoio(caminho_cofre, executavel, so_cofre=True)


@contextlib.contextmanager
def apoio_liberado():
    """Libera (mostra, tira o somente-leitura) a família do cofre só enquanto o bloco roda e esconde de novo no fim,
    mesmo se der erro. Reentrante e seguro entre threads; sem a ocultação ligada não faz nada."""
    if _APOIO["caminho"] is None:
        yield
        return
    with _APOIO_TRAVA:
        _APOIO["prof"] += 1
        primeiro = _APOIO["prof"] == 1
    if primeiro:
        revelar_apoio(_APOIO["caminho"], _APOIO["exe"], so_cofre=True)
    try:
        yield
    finally:
        with _APOIO_TRAVA:
            _APOIO["prof"] -= 1
            ultimo = _APOIO["prof"] == 0
        if ultimo:
            ocultar_apoio(_APOIO["caminho"], _APOIO["exe"], so_cofre=True)


def unidade_removivel(caminho):
    """True se o arquivo está numa unidade REMOVÍVEL do Windows (pendrive/cartão: GetDriveTypeW == DRIVE_REMOVABLE).
    Fora do Windows, ou se não der para saber, devolve False. Só serve para o texto de aviso durante a gravação."""
    if not EH_WINDOWS or not caminho:
        return False
    try:
        raiz = os.path.splitdrive(os.path.abspath(caminho))[0] + "\\"
        return ctypes.windll.kernel32.GetDriveTypeW(raiz) == 2          # DRIVE_REMOVABLE
    except Exception:
        return False


def politica_exigir_ntfs(pasta=None):
    """True se o dono pediu para o cofre RECUSAR abrir em pendrive sem permissões de arquivo (FAT/FAT32/exFAT): variável de
    ambiente COFRE_EXIGIR_NTFS=1 ou arquivo `exigir_ntfs.txt` ao lado do programa. Padrão: desligado (só alerta)."""
    if os.environ.get("COFRE_EXIGIR_NTFS", "").strip().lower() in ("1", "true", "sim", "yes"):
        return True
    try:
        return os.path.isfile(os.path.join(pasta or pasta_base(), NOME_MARCADOR_NTFS))
    except OSError:
        return False


def limpar_temporarios():
    """Apaga a pasta temporária privada do programa (e tudo dentro dela). Roda ao sair e também ao iniciar (resto de uma
    queda). Nunca segue atalho/junção e nunca mexe em arquivos fora dessa pasta. Sem erro se ela não existir."""
    pasta = _TEMP_PRIVADO["pasta"]
    if not pasta:
        return
    try:
        if os.path.isdir(pasta) and not os.path.islink(pasta):
            shutil.rmtree(pasta, ignore_errors=True)
    except OSError:
        pass


def isolar_temporarios(base=None):
    """REDUZ RASTROS NO COMPUTADOR HOSPEDEIRO: manda TEMP/TMP/TMPDIR (e o `tempfile`) deste processo para uma pasta
    privada `.tmp_cofre` ao lado do programa, de modo que qualquer arquivo temporário criado por uma biblioteca ou
    pelos comandos de apoio fique no pendrive e seja apagado ao sair, em vez de ficar no %TEMP% do usuário do Windows.
    NÃO apaga nada no perfil do host (varrer pastas alheias poderia destruir arquivos de outros programas).
    Retorna o caminho da pasta, ou None se não deu (pendrive protegido contra gravação, atalho no lugar): nesse caso
    tudo continua como estava. Chamar só na instância que é dona da trava (a segunda não deve apagar a pasta da primeira)."""
    pasta = os.path.join(base or pasta_base(), NOME_PASTA_TEMP)
    try:
        if os.path.islink(pasta):
            return None
        _TEMP_PRIVADO["pasta"] = pasta
        limpar_temporarios()                         # resto de uma queda anterior
        os.makedirs(pasta, mode=0o700, exist_ok=True)
        if not os.access(pasta, os.W_OK):
            raise OSError("pasta temporária sem escrita")
    except OSError:
        _TEMP_PRIVADO["pasta"] = None
        return None
    import tempfile
    for var in ("TEMP", "TMP", "TMPDIR"):
        os.environ[var] = pasta
    tempfile.tempdir = pasta
    atexit.register(limpar_temporarios)
    return pasta


_TRAVA_ARQ = {"fd": None, "caminho": None}


@contextlib.contextmanager
def _trava_gravacao(caminho):
    """Serializa a conferência de versão e a troca atômica entre processos."""
    caminho_trava = caminho + ".gravar.lock"
    fd = os.open(caminho_trava, os.O_RDWR | os.O_CREAT, 0o600)
    travado = False
    try:
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"\0")
        os.lseek(fd, 0, os.SEEK_SET)
        if EH_WINDOWS:
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        travado = True
        yield
    finally:
        if travado:
            try:
                if EH_WINDOWS:
                    import msvcrt
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
        else:
            os.close(fd)


def _trava_de_arquivo(caminho):
    """Trava de arquivo ENTRE PROCESSOS (vale entre sessões do Windows, entre letras de unidade e em qualquer
    sistema): cria/abre `<cofre>.lock` (arquivo vazio) e pede uma trava exclusiva e imediata. O sistema operacional
    solta a trava sozinho se o programa morrer (não há trava 'velha'). Retorna True = este processo é o dono;
    False = outro processo já é o dono; None = não deu para criar/travar (ex.: pendrive protegido contra gravação)."""
    chave = os.path.abspath(caminho)
    if _TRAVA_ARQ["fd"] is not None and _TRAVA_ARQ["caminho"] == chave:
        return True
    try:
        fd = os.open(caminho + ".lock", os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        return None
    try:
        if EH_WINDOWS:
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as ex:
        try:
            os.close(fd)
        except OSError:
            pass
        ocupado = ex.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK, 36) or \
            getattr(ex, "winerror", None) in (32, 33)          # 32/33 = violação de compartilhamento/de trava
        return False if ocupado else None
    _TRAVA_ARQ["fd"], _TRAVA_ARQ["caminho"] = fd, chave           # fica aberto até o programa fechar
    return True


def instancia_unica(caminho):
    """False se este cofre já estiver aberto em outra janela/processo (duas janelas gravando = uma sobrescreve a
    outra). Duas camadas: trava de arquivo `.lock` (a principal) e, no Windows, um mutex nomeado da sessão (vale
    também quando o `.lock` não pode ser criado). Quem recebe False abre o cofre em MODO CONSULTA."""
    global _MUTEX
    dono = _trava_de_arquivo(caminho)
    if dono is False:
        return False
    if not EH_WINDOWS:
        return True
    try:
        try:                                   # identidade do ARQUIVO (volume + índice): H:, I: e UNC dão o mesmo
            st = os.stat(caminho)
            ident = f"{st.st_dev}:{st.st_ino}"
        except OSError:
            ident = os.path.abspath(caminho).lower()
        nome = "Local\\CofreSenhas_" + hashlib.sha256(ident.encode("utf-8")).hexdigest()[:24]
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateMutexW.restype = ctypes.c_void_p
        k.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        _MUTEX = k.CreateMutexW(None, False, nome)
        return ctypes.get_last_error() != 183          # ERROR_ALREADY_EXISTS
    except Exception:
        return True


def hook_energia(root, ao_perigo):
    """Windows: avisa ANTES de suspender/hibernar e quando a sessão é bloqueada (Win+L), para apagar as
    chaves da memória antes que o Windows grave a RAM no disco (hiberfil.sys). Também limpa ao desligar."""
    if not EH_WINDOWS:
        return None
    try:
        u = ctypes.WinDLL("user32", use_last_error=True)
        PROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)
        u.GetParent.restype = ctypes.c_void_p
        u.GetParent.argtypes = [ctypes.c_void_p]
        u.SetWindowLongPtrW.restype = ctypes.c_void_p
        u.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        u.CallWindowProcW.restype = ctypes.c_ssize_t
        u.CallWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
        hwnd = u.GetParent(root.winfo_id()) or root.winfo_id()
        estado = {"antigo": None}

        def proc(h, msg, w, lp):
            """Procedimento de janela: ao detectar suspensão, bloqueio ou desligamento, chama a rotina de perigo."""
            try:
                if (msg == 0x218 and w in (0x4, 0x0)) or (msg == 0x2B1 and w in (0x7, 0x2)) \
                        or (msg == 0x16 and w):      # PBT_APMSUSPEND / sessão bloqueada / desligando
                    ao_perigo()
            except (tk.TclError, OSError, RuntimeError, ValueError, TypeError) as ex:
                diag_registrar(DIAG_INTERFACE, ex)
            return u.CallWindowProcW(estado["antigo"], h, msg, w, lp)

        cb = PROC(proc)
        estado["cb"] = cb
        estado["antigo"] = u.SetWindowLongPtrW(hwnd, -4, ctypes.cast(cb, ctypes.c_void_p))
        if not estado["antigo"]:
            return None
        wts = None
        try:
            wts = ctypes.WinDLL("wtsapi32")
            wts.WTSRegisterSessionNotification(ctypes.c_void_p(hwnd), 0)
        except (AttributeError, OSError, ctypes.ArgumentError, TypeError):
            wts = None

        def desfazer():
            """Ao sair: devolve o WndProc original e cancela o aviso de sessão."""
            try:
                if wts is not None:
                    wts.WTSUnRegisterSessionNotification(ctypes.c_void_p(hwnd))
            except (AttributeError, OSError, ctypes.ArgumentError):
                pass
            try:
                u.SetWindowLongPtrW(hwnd, -4, ctypes.c_void_p(estado["antigo"]))
            except (AttributeError, OSError, ctypes.ArgumentError):
                pass
        estado["desfazer"] = desfazer
        _HOOKS.append(estado)
        return estado
    except Exception:
        return None


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


_ERRO_CLIP = [""]      # último motivo de falha da cópia protegida (aparece na mensagem para facilitar o diagnóstico)


def _anotar_erro_clip(etapa):
    """Guarda a etapa que falhou e o código de erro do Windows (GetLastError)."""
    try:
        _ERRO_CLIP[0] = f"{etapa} (erro {ctypes.GetLastError()})"
    except Exception:
        _ERRO_CLIP[0] = etapa


def _abrir_clipboard(dono="auto"):
    """Abre a área de transferência do Windows (até 40 tentativas de 25 ms: antivírus e gerenciadores a seguram
    por instantes). 'dono' é a janela dona; 'auto' usa a janela invisível do cofre."""
    if dono == "auto":
        dono = _janela_clipboard()
    for _ in range(40):
        if _u32.OpenClipboard(dono):
            return True
        time.sleep(0.025)
    _anotar_erro_clip("OpenClipboard")
    return False


def _clipboard_set(formato, dados):
    """Coloca dados na área de transferência no formato indicado."""
    h = _k32.GlobalAlloc(0x0002, len(dados))                # GMEM_MOVEABLE
    if not h:
        _anotar_erro_clip("GlobalAlloc")
        return False
    p = _k32.GlobalLock(h)
    if not p:
        _anotar_erro_clip("GlobalLock")
        _k32.GlobalFree(h)
        return False
    origem = (ctypes.c_ubyte * len(dados)).from_buffer(dados) if isinstance(dados, bytearray) else dados
    ctypes.memmove(p, origem, len(dados))
    _k32.GlobalUnlock(h)
    if not _u32.SetClipboardData(formato, h):
        _anotar_erro_clip("SetClipboardData")
        _k32.GlobalFree(h)
        return False
    return True


def copiar_seguro_windows(texto, dono_alternativo=None):
    """Copia sem entrar no histórico (Win+V), sem sincronizar com a nuvem e
    marcando o conteúdo para ser ignorado por monitores de área de transferência.
    Tenta primeiro com a janela invisível do cofre como dona; se o Windows recusar, tenta com a janela
    principal ('dono_alternativo') e confere no fim se o texto realmente entrou."""
    donos = ["auto"]
    if dono_alternativo:
        donos.append(dono_alternativo)
    for dono in donos:
        if not _abrir_clipboard(dono):
            continue
        ok = False
        try:
            _u32.EmptyClipboard()
            dados = bytearray((texto + "\0").encode("utf-16-le"))
            try:
                ok = _clipboard_set(13, dados)   # CF_UNICODETEXT
            finally:
                dados[:] = b"\0" * len(dados)
            if ok:
                zero = struct.pack("<I", 0)
                for nome in ("ExcludeClipboardContentFromMonitorProcessing",
                             "CanIncludeInClipboardHistory", "CanUploadToCloudClipboard"):
                    _clipboard_set(_u32.RegisterClipboardFormatW(nome), zero)
        finally:
            _u32.CloseClipboard()
        if ok and _u32.IsClipboardFormatAvailable(13):
            return True
    return False


def historico_clipboard_ligado():
    """True se o histórico da área de transferência do Windows (Win+V) estiver ligado, ou se não der para saber.
    Com o histórico desligado, a cópia comum do Tk não deixa a senha guardada em lugar nenhum além da própria
    área de transferência (que o cofre limpa em segundos)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Clipboard") as k:
            return int(winreg.QueryValueEx(k, "EnableClipboardHistory")[0]) != 0
    except FileNotFoundError:
        return False            # chave ausente = nunca ligado
    except Exception:
        return True             # não deu para saber: trata como ligado (mais seguro)


def sequencia_clipboard():
    """Número que o Windows incrementa a cada mudança da área de transferência (None se indisponível)."""
    if not EH_WINDOWS:
        return None
    try:
        return int(_u32.GetClipboardSequenceNumber())
    except Exception:
        return None


def limpar_clipboard_windows():
    """Esvazia a área de transferência do Windows."""
    if _abrir_clipboard():
        try:
            _u32.EmptyClipboard()
        finally:
            _u32.CloseClipboard()


_TRAVA_SALVAR = threading.RLock()


class Cofre:
    """O cofre em memória: cria/abre/salva o arquivo (COFRE05),
    guarda a chave dos dados (DEK), as formas de desbloqueio (senha, chave, FIDO, recuperação), a contagem de tentativas com autodestruição e as cópias de segurança."""
    somente_leitura = False       # True no MODO CONSULTA: aberto sem gravar nada (pendrive protegido ou cofre em uso)
    motivo_consulta = "protegido"  # no modo consulta: "protegido" (pendrive sem gravação) ou "em_uso" (outra janela o tem aberto)
    _seq = 0                      # contador de salvamentos deste arquivo (vai dentro dos dados cifrados)
    _seq_copias = 0               # maior contador visto nas cópias .bak ao abrir
    alerta_reversao = False       # True se, ao abrir, havia uma cópia MAIS NOVA que o arquivo principal

    def __init__(self, caminho, dek, max_t, registros, t=None, m=None, p=PARALELISMO, modo=MODO_OU):
        """Cria o objeto do cofre em memória com a DEK, os registros e os parâmetros de derivação."""
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
        self.pc = None                  # {"salt", "rec", "maquinas": [...]} quando há computadores autorizados
        self._G = None                  # segredo do fator "computador" (só em memória, enquanto aberto)
        self._salt_pendente = None
        self._vkey = None               # verificador rápido da senha (HMAC com chave só desta sessão)
        self._vmacs = None

    def _armar_verificador(self, senha):
        """Guarda, só em memória, HMACs (chave aleatória da sessão) das formas Unicode da senha digitada.
        Serve para reconfirmar a senha em itens protegidos sem repetir o Argon2 (vários segundos)."""
        import hmac
        vkey = secrets.token_bytes(32)
        self._vkey = vkey
        self._vmacs = [hmac.new(vkey, v.encode("utf-8", "surrogatepass"), "sha256").digest()
                       for v in _variantes(senha)]

    # ----- definição das formas de desbloqueio -----
    def _reembrulhar_e(self):
        """No modo E (senha e chave), refaz o embrulho da DEK com a chave combinada."""
        kek = kek_combinada(self._ks, self._kb, self.sal_pw)
        self.nonce_pw, self.wrap_pw = _embrulhar(kek, self.dek)
        # campos da chave avulsa preenchidos com ruído (no modo E a chave sozinha não abre nada)
        self.sal_k, self.nonce_k, self.wrap_k = (secrets.token_bytes(16), secrets.token_bytes(12),
                                                 secrets.token_bytes(48))

    def _definir_senha(self, senha, normalizar=True):
        """Define a senha mestra: deriva a chave, troca sal e embrulho só depois de tudo dar certo."""
        if not isinstance(senha, str) or not senha:
            raise ValueError("A senha mestra não pode ser vazia.")   # senão o cofre nasceria sem como abrir pela senha
        if len(senha) > MAX_SENHA:
            raise ValueError(f"A senha mestra tem mais de {MAX_SENHA} caracteres.")
        if normalizar:
            senha = unicodedata.normalize("NFC", senha)      # forma única para senhas novas
        # Deriva PRIMEIRO (pode falhar por falta de memória) e só depois troca o estado:
        # um erro aqui deixa sal, chave e embrulho exatamente como estavam.
        sal = secrets.token_bytes(16)
        ks = derivar_chave(senha, sal, self.t, self.m, self.p)
        antes = (self.sal_pw, self._ks, self.nonce_pw, self.wrap_pw,
                 self.sal_k, self.nonce_k, self.wrap_k, self._vkey, self._vmacs)
        try:
            self.sal_pw = sal
            self._ks = ks
            self._armar_verificador(senha)
            if self.modo == MODO_E:
                if self._kb is not None:
                    self._reembrulhar_e()
            else:
                self.nonce_pw, self.wrap_pw = _embrulhar(ks, self.dek)
        except BaseException:
            (self.sal_pw, self._ks, self.nonce_pw, self.wrap_pw,
             self.sal_k, self.nonce_k, self.wrap_k, self._vkey, self._vmacs) = antes
            raise

    def _definir_chave_acesso(self):
        """Gera uma chave de acesso nova e devolve o texto dela (mostrado ao usuário uma vez)."""
        kb, ktxt = nova_chave_acesso()
        self._kb = kb
        if self.modo == MODO_E:
            if self._ks is not None:
                self._reembrulhar_e()
        else:
            self.sal_k = secrets.token_bytes(16)
            self.nonce_k, self.wrap_k = _embrulhar(kek_da_chave(kb, self.sal_k), self.dek)
        return ktxt

    # ----- criar / abrir -----
    @classmethod
    @_com_apoio_liberado
    def criar(cls, caminho, senha, max_tentativas=5, modo=MODO_OU, nivel="maximo"):
        """Cria um cofre novo no caminho, já salva e faz a primeira cópia de segurança."""
        if not isinstance(senha, str) or len(senha) < MIN_SENHA:      # a tela já avisa; aqui é a última barreira
            raise ValueError(f"A senha mestra precisa ter pelo menos {MIN_SENHA} caracteres.")
        t, m = NIVEIS[nivel]
        c = cls(caminho, secrets.token_bytes(32), max_tentativas, [], t, m, PARALELISMO, modo)
        c._registrar_abertura({}, 0)
        if modo == MODO_S:                      # só senha: não existe chave de acesso; os campos dela são só ruído
            c.sal_k, c.nonce_k, c.wrap_k = secrets.token_bytes(16), secrets.token_bytes(12), secrets.token_bytes(48)
            c.chave_gerada = None
        else:
            c.chave_gerada = c._definir_chave_acesso()
        c._definir_senha(senha)
        c.salvar()
        _rodar_copias(caminho)                  # já nasce com uma cópia de segurança
        return c

    @classmethod
    @_com_apoio_liberado
    def abrir(cls, caminho, senha=None, chave=None, fido=None, recuperacao=None, consulta=False):
        """Modo OU: senha OU chave. Modo E: senha E chave.
        consulta=True (MODO CONSULTA, p/ pendrive protegido contra gravação): abre SEM gravar nada: não conta tentativa
        (nada pode ser registrado, então a autodestruição não existe nesse modo), não regrava o arquivo e o cofre
        resultante recusa qualquer salvamento.
        Se o cofre exigir FIDO: 'fido' é uma função (lista_de_credenciais, salt) -> (credencial, saída)
        que toca a chave física; ou então 'recuperacao' é o código de recuperação em texto."""
        for destino in (caminho, *_copias(caminho)):
            _limpar_temporarios_interrompidos(destino)
        with open(caminho, "rb") as f:
            bruto = f.read(LIMITE_COFRE + 1)
        if len(bruto) > LIMITE_COFRE:
            raise ArquivoInvalido("Este arquivo é grande demais para ser um cofre.")

        if bruto[:8] == MAGIC_V1:
            if senha is None:
                raise ArquivoInvalido("Cofre da versão antiga: abra uma vez com a senha mestra "
                                      "para atualizá-lo.")
            if len(senha) > MAX_SENHA:
                raise ChaveMalFormada(f"A senha digitada tem mais de {MAX_SENHA} caracteres: confira o que foi digitado.")
            if consulta:
                raise ArquivoInvalido("Este cofre é de uma versão antiga e precisa ser atualizado (gravado) uma vez: "
                                      "destrave o pendrive para gravação e abra de novo.")
            return cls._abrir_v1(caminho, bruto, senha)

        h = _ler_cabecalho(bruto)
        assin = _assinatura(bruto)
        if h["versao"] < 5 and not consulta and not os.path.exists(caminho + ".pre-v5"):
            try:                                 # cópia do cofre ORIGINAL, fora da rotação, antes de migrar
                orig = bytearray(bruto)
                orig[h["hl"]] = h["max_t"]
                _gravar_atomico(caminho + ".pre-v5", bytes(orig))
            except OSError:
                pass
        # Validações que NÃO gastam tentativa (erros de digitação / fator esquecido)
        if senha and len(senha) > MAX_SENHA:
            raise ChaveMalFormada(f"A senha digitada tem mais de {MAX_SENHA} caracteres: confira o que foi digitado "
                                  "(ou colado) no campo.")
        if h["modo"] == MODO_E:
            if not senha or not chave:
                raise FatorFaltando("Este cofre exige a senha mestra E a chave de acesso juntas.")
            kb = ler_chave_acesso(chave)
        elif h["modo"] == MODO_S:
            if not senha:
                raise FatorFaltando("Este cofre abre só com a senha mestra. Digite a senha.")
            kb = None                   # modo só-senha: qualquer chave digitada é ignorada
        else:
            kb = ler_chave_acesso(chave) if not senha else None
        rec_bytes = None
        if h["fido"] or h["pc"]:
            if recuperacao:
                rec_bytes = ler_chave_acesso(recuperacao)
            elif h["fido"] and fido is None:
                raise FatorFaltando("Este cofre exige também a chave FIDO (ou o código de recuperação).")
        g_pc = None
        if h["pc"] and rec_bytes is None:        # computador autorizado: conferido ANTES de gastar tentativa
            g_pc = _achar_g(h["pc"])
            if g_pc is None:
                raise PcNaoAutorizado("Este computador não está autorizado neste cofre. Para abrir aqui, use o "
                                      "código de recuperação (ou abra num computador autorizado).")

        if h["contador"] > h["max_t"] or h["contador"] == 0:
            # Contador fora do possível: arquivo danificado (ou mexido por fora). NÃO apaga nada:
            # um byte ruim no pendrive não pode custar o cofre. Orienta a restaurar a cópia.
            raise ArquivoCorrompido(MSG_CONTADOR_DANIFICADO)

        exigir_memoria(h["m"])          # sem memória: avisa já (antes do toque FIDO e sem gastar tentativa)

        # Toque na chave FIDO ANTES de gastar a tentativa (cancelar não gasta tentativa)
        saida_fido = cred_usada = None
        if h["fido"] and rec_bytes is None:
            cred_usada, saida_fido = fido([c["cred"] for c in h["fido"]["chaves"]], h["fido"]["salt"])
            if not any(c["cred"] == cred_usada for c in h["fido"]["chaves"]):
                raise FidoErro("Esta chave FIDO não está cadastrada neste cofre.")

        restantes = h["contador"] if consulta else _gastar_tentativa(caminho, h["hl"], h["contador"])

        ks = None
        try:
            dek = None
            cand_ok = None
            if h["modo"] == MODO_E:
                for cand in _variantes(senha):
                    ks = derivar_chave(cand, h["sal_pw"], h["t"], h["m"], h["p"])
                    try:
                        dek = _desembrulhar(kek_combinada(ks, kb, h["sal_pw"]), h["nonce_pw"], h["wrap_pw"])
                        cand_ok = cand
                        break
                    except InvalidTag:
                        continue
            elif senha:
                for cand in _variantes(senha):
                    ks = derivar_chave(cand, h["sal_pw"], h["t"], h["m"], h["p"])
                    try:
                        dek = _desembrulhar(ks, h["nonce_pw"], h["wrap_pw"])
                        cand_ok = cand
                        break
                    except InvalidTag:
                        continue
            else:
                dek = _desembrulhar(kek_da_chave(kb, h["sal_k"]), h["nonce_k"], h["wrap_k"])
            if dek is None:
                raise InvalidTag()
            fator = None
            if h["fido"]:
                if rec_bytes is not None:
                    sal, nonce, wrap = h["fido"]["rec"]
                    fator = _desembrulhar(_kek_recuperacao(rec_bytes, sal), nonce, wrap)
                else:
                    ch = next(c for c in h["fido"]["chaves"] if c["cred"] == cred_usada)
                    fator = _desembrulhar(_kek_fido(saida_fido), ch["nonce"], ch["wrap"])
            fator_g = g_pc
            if h["pc"] and rec_bytes is not None:
                sal, nonce, wrap = h["pc"]["rec"]
                fator_g = _desembrulhar(_kek_recuperacao(rec_bytes, sal), nonce, wrap)
        except InvalidTag:
            if consulta:                            # nada foi gasto nem pode ser destruído: só informa
                erro = SenhaIncorreta(restantes)
                erro.consulta = True
                raise erro from None
            if restantes == 0:
                destruir(caminho)
                raise CofreDestruido() from None
            raise SenhaIncorreta(restantes) from None
        except (MemoryError, HashingError):
            if not consulta:
                _devolver_tentativa(caminho, h)     # faltou memória: a senha nem foi testada
            raise MemoryError("sem memória para derivar a chave") from None

        try:
            registros, meta = _decifrar_dados(_chave_dados(dek, _fator_total(fator, fator_g)), h, bruto)
        except (InvalidTag, ValueError):
            # Senha/chave CORRETAS, mas os dados não conferem: arquivo danificado ou alterado.
            # Quem chegou aqui tem a senha certa, então apagar só prejudicaria o dono: preserva o
            # arquivo, devolve a tentativa e orienta a restaurar a cópia de segurança.
            if not consulta:
                _devolver_tentativa(caminho, h)
            raise ArquivoCorrompido("O conteúdo do cofre não confere (arquivo danificado ou alterado).") from None

        c = cls(caminho, dek, h["max_t"], registros, h["t"], h["m"], h["p"], h["modo"])
        c._seq = _seq_de(meta)
        c._seq_copias = _maior_seq_nas_copias(caminho, _chave_dados(dek, _fator_total(fator, fator_g)))
        c.alerta_reversao = c._seq_copias > c._seq           # arquivo principal mais VELHO que uma cópia: reversão?
        for k in ("sal_pw", "nonce_pw", "wrap_pw", "sal_k", "nonce_k", "wrap_k"):
            setattr(c, k, h[k])
        c._ks = ks if (senha or h["modo"] == MODO_E) else None   # só em memória, enquanto aberto
        if senha and cand_ok is not None:
            c._armar_verificador(cand_ok)
        c._kb = kb
        c._assin = assin
        if c.alerta_reversao and not consulta:
            diag_registrar(DIAG_REVERSAO)
        if consulta:                       # MODO CONSULTA: devolve o cofre pronto para leitura, sem gravar NADA
            c.fido, c._F = h["fido"], fator
            c.pc, c._G = h["pc"], fator_g
            c.meta = dict(meta or {})
            c.ultima_abertura = c.meta.get("ultima_abertura")
            c.erros_desde_ultima = 0
            c.somente_leitura = True
            return c
        if cand_ok is not None and cand_ok != unicodedata.normalize("NFC", cand_ok):
            c._definir_senha(unicodedata.normalize("NFC", cand_ok))
        c.fido, c._F = h["fido"], fator
        c.pc, c._G = h["pc"], fator_g
        c._registrar_abertura(meta, h["max_t"] - h["contador"])
        try:
            c.salvar()  # regrava no formato atual: renova nonces e zera o contador de erros
        except ConflitoGravacao:
            _devolver_tentativa(caminho, h)
            raise
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
        """Abre um cofre no formato antigo (v1), gastando uma tentativa, para migrá-lo ao formato atual."""
        if len(bruto) < HEADER_V1_LEN + 17:
            raise ArquivoInvalido("Arquivo de cofre inválido ou corrompido.")
        magic, t, m, p, max_t, sal, nonce = struct.unpack(HEADER_V1_FMT, bruto[:HEADER_V1_LEN])
        _validar_params(t, m, p, max_t)
        contador = bruto[HEADER_V1_LEN]
        if contador > max_t or contador == 0:
            raise ArquivoCorrompido(MSG_CONTADOR_DANIFICADO)
        exigir_memoria(m)
        restantes = _gastar_tentativa(caminho, HEADER_V1_LEN, contador)
        try:
            chave = derivar_chave(senha, sal, t, m, p)
            texto = AESGCM(chave).decrypt(nonce, bruto[HEADER_V1_LEN + 1:], bruto[:HEADER_V1_LEN])
        except InvalidTag:
            if restantes == 0:
                # O formato v1 não tem como distinguir "senha errada" de "cofre atual com 1 bit danificado no
                # nome do formato" (os campos t/m/p caem nos mesmos lugares). Por isso aqui NUNCA se destrói:
                # devolve a tentativa e orienta. (Quem já migrou para o formato atual não passa por este caminho.)
                _devolver_tentativa(caminho, {"hl": HEADER_V1_LEN, "contador": contador})
                raise ArquivoCorrompido("Senha incorreta, ou o arquivo está danificado. Nada foi apagado. "
                                        "Se este é um cofre atual, restaure uma cópia de segurança (.bak1).") from None
            raise SenhaIncorreta(restantes) from None
        # Converte para o formato atual, com chave de acesso
        c = cls(caminho, secrets.token_bytes(32), max_t, json.loads(texto.decode("utf-8")), t, m, p)
        c.chave_gerada = c._definir_chave_acesso()
        c._definir_senha(senha)
        c.salvar()
        return c

    # ----- gravação e manutenção -----
    executor_salvar = None        # a tela define: roda o salvamento numa thread e mantém a janela respondendo

    def salvar(self, forcar_copia=False):
        """Salva o cofre (um salvamento por vez); com forcar_copia, renova também as cópias de segurança.
        Na tela, a gravação (lenta num pendrive FAT32) roda FORA da thread da janela: ela não congela nem
        aparece como 'Não está respondendo'."""
        exec_ = Cofre.executor_salvar
        if exec_ is not None and threading.current_thread() is threading.main_thread():
            return exec_(lambda: self._salvar_travado(forcar_copia))
        return self._salvar_travado(forcar_copia)

    @_com_apoio_liberado
    def _salvar_travado(self, forcar_copia=False):
        """Pega a trava de salvamento e grava (corpo de `salvar`, pronto para rodar em outra thread)."""
        with _TRAVA_SALVAR:                       # um salvamento por vez (evita corrida no .tmp)
            return self._salvar_sem_trava(forcar_copia)

    def _salvar_sem_trava(self, forcar_copia=False):
        """Serializa, cifra e grava o cofre de forma atômica, conferindo se outra instância o alterou; quem chama já segura a trava."""
        if self.somente_leitura:
            erro = ErroGravacao("Modo consulta: nada pode ser adicionado, alterado ou apagado nesta sessão. "
                                + ("Feche a outra janela do cofre e abra de novo."
                                   if self.motivo_consulta == "em_uso" else
                                   "Destrave o pendrive e abra o cofre de novo."))
            erro.protegido = True
            raise erro
        nonce_c, nonce_a = secrets.token_bytes(12), secrets.token_bytes(12)
        cab = struct.pack(HEADER_FMT, MAGIC, self.t, self.m, self.p, self.max_t, self.modo,
                          self.sal_pw, self.nonce_pw, self.wrap_pw,
                          self.sal_k, self.nonce_k, self.wrap_k, nonce_c, nonce_a)
        if bool(self.fido) != (self._F is not None) or bool(self.pc) != (self._G is not None):
            raise ValueError("estado FIDO/computador inconsistente")
        secao = _serializar_secao(self.fido, self.pc)
        cab += hashlib.sha256(cab + secao).digest()[:8]          # v5: checksum (bit-rot x senha errada)
        aad = cab + secao
        seq = max(self._seq, self._seq_copias) + 1                  # sempre maior que o de qualquer cópia: o aviso de reversão some
        meta_gravar = dict(self.meta)
        meta_gravar["seq"] = seq
        dados = _json_do_cofre(self.registros, meta_gravar)         # já preenchido até múltiplo de TAM_BLOCO
        k_cha, k_aes = _subchaves(_chave_dados(self.dek, _fator_total(self._F, self._G)))
        try:
            try:
                interno = ChaCha20Poly1305(k_cha).encrypt(nonce_c, dados, aad)    # camada 1 (lê o bytearray direto: sem cópia)
            finally:
                _zerar(dados)
            externo = AESGCM(k_aes).encrypt(nonce_a, interno, aad)           # camada 2
        finally:
            # subchaves por operação: mesmo tratamento do resto dos segredos (eram as únicas que escapavam da zeragem)
            zerar_objeto(k_cha)
            zerar_objeto(k_aes)
        saida = cab + bytes([self.max_t]) + secao + externo
        with _trava_gravacao(self.caminho):
            b1 = self.caminho + ".bak1"                 # cópia de segurança: no máx. 1 a cada 10 min
            try:
                velha = (not os.path.exists(b1)) or abs(time.time() - os.path.getmtime(b1)) > 600
            except OSError:
                velha = True
            # A trava abrange esta checagem e a substituição: sem ela, dois processos podiam
            # validar a mesma assinatura e o último a renomear apagava a gravação do primeiro.
            assin = getattr(self, "_assin", None)
            if assin is not None:
                try:
                    with open(self.caminho, "rb") as f:
                        atual = f.read(LIMITE_COFRE)
                except FileNotFoundError:
                    diag_registrar(DIAG_CONFLITO)
                    raise ErroGravacao("O arquivo do cofre não está mais no lugar (o pendrive foi removido ou trocado?). "
                                       "Nada foi gravado. Encaixe o pendrive de novo e tente outra vez; se ele estiver "
                                       "encaixado, feche e abra o cofre.") from None
                if _assinatura(atual) != assin:
                    diag_registrar(DIAG_CONFLITO)
                    raise ConflitoGravacao("O arquivo do cofre foi alterado por outra janela ou programa depois "
                                           "que você o abriu. Nada foi gravado. Bloqueie e abra o cofre de novo.")
            if velha or forcar_copia:
                _rodar_copias(self.caminho)
            _gravar_atomico(self.caminho, saida)
            self._assin = _assinatura(saida)
            self._seq = seq
            self.meta["seq"] = seq

    def confere_chave_acesso(self, texto):
        """Confere se o texto digitado é a chave de acesso DESTE cofre (abre o cadeado dela no cabeçalho). Não gasta
        tentativa e não deixa nada gravado. Cofre 'só senha' não tem chave: devolve True (nada a conferir).
        Chave mal formada ou errada devolve False."""
        if self.modo == MODO_S:
            return True
        try:
            kb = ler_chave_acesso(texto)
            if self._kb is not None:                 # aberto com a chave (modo E sempre): compara com a da sessão
                return secrets.compare_digest(bytes(kb), bytes(self._kb))
            dek = _desembrulhar(kek_da_chave(kb, self.sal_k), self.nonce_k, self.wrap_k)     # modo OU aberto só com senha
            return secrets.compare_digest(dek, self.dek)
        except (ChaveMalFormada, InvalidTag, ValueError, TypeError):
            return False

    def confere_senha(self, senha):
        """Confere a senha digitada com a da sessão em tempo constante (sem curto-circuito)."""
        if not isinstance(senha, str) or len(senha) > MAX_SENHA:
            return False
        if self._vmacs:                          # caminho rápido: compara com o verificador da sessão
            import hmac
            vk = self._vkey
            digs = [hmac.new(vk, v.encode("utf-8", "surrogatepass"), "sha256").digest()
                    for v in _variantes(senha)]
            achou = False
            for d in digs:                       # sem curto-circuito: sempre compara todos os pares
                for m in self._vmacs:
                    achou |= secrets.compare_digest(d, m)
            return achou
        for cand in _variantes(senha):
            ks = derivar_chave(cand, self.sal_pw, self.t, self.m, self.p)
            try:
                if self.modo == MODO_E:
                    if self._ks is not None and secrets.compare_digest(ks, self._ks):
                        return True
                elif secrets.compare_digest(_desembrulhar(ks, self.nonce_pw, self.wrap_pw), self.dek):
                    return True
            except InvalidTag:
                pass
        return False

    @contextlib.contextmanager
    def transacao(self, forcar_copia=False):
        """Altera itens/meta e grava. Se algo falhar (inclusive a gravação), volta TUDO ao que era antes,
        na memória: nunca fica, escondido, uma mudança que o usuário viu recusada."""
        antes_r = copy.deepcopy(self.registros)
        antes_m = copy.deepcopy(self.meta)
        try:
            yield self
            self.salvar(forcar_copia=forcar_copia)
        except BaseException:
            self.registros[:] = antes_r
            self.meta.clear()
            self.meta.update(antes_m)
            raise

    _CAMPOS_CHAVES = ("dek", "sal_pw", "nonce_pw", "wrap_pw", "sal_k", "nonce_k", "wrap_k", "_ks", "_kb",
                      "chave_gerada", "_vkey", "_vmacs")

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

    def trocar_senha(self, nova, chave_acesso=None):
        """Troca a senha mestra E a chave interna dos dados (DEK), recifrando tudo. Assim quem tem a senha
        antiga e uma cópia velha do arquivo NÃO consegue abrir o arquivo novo.
        Modo OU precisa também reembrulhar a DEK com a chave de acesso: usa a que está em memória, a que
        for passada (texto), ou, se nenhuma, GERA uma chave nova. Retorna o texto da chave nova ou None."""
        if not isinstance(nova, str) or len(nova) < MIN_SENHA:        # última barreira (a tela já avisa)
            raise ValueError(f"A senha mestra precisa ter pelo menos {MIN_SENHA} caracteres.")
        def mudar():
            """Operação interna da troca de senha, executada numa transação que desfaz tudo se falhar."""
            texto = None
            kb = self._kb
            if self.modo == MODO_OU:
                if kb is None and chave_acesso:
                    kb = ler_chave_acesso(chave_acesso)
                    try:
                        certo = secrets.compare_digest(
                            _desembrulhar(kek_da_chave(kb, self.sal_k), self.nonce_k, self.wrap_k), self.dek)
                    except InvalidTag:
                        certo = False
                    if not certo:
                        raise ChaveMalFormada("Essa chave de acesso não confere com a deste cofre.")
                if kb is None:
                    kb, texto = nova_chave_acesso()
            self.dek = secrets.token_bytes(32)          # chave interna NOVA: o que a senha velha abria morre
            self._kb = kb
            self._definir_senha(nova)
            if self.modo == MODO_OU:
                self.sal_k = secrets.token_bytes(16)
                self.nonce_k, self.wrap_k = _embrulhar(kek_da_chave(kb, self.sal_k), self.dek)
            if texto:
                self.chave_gerada = None
            return texto
        r = self._com_desfazer(mudar)
        self.copias_nao_apagadas = apagar_copias(self.caminho)   # ainda abririam com a senha velha
        return r

    def gerar_nova_chave_acesso(self, senha=None):
        """Cria nova chave de acesso E nova chave interna (DEK). A chave anterior deixa de funcionar.
        No modo OU também precisa da senha para reembrulhar a DEK: usa a de memória ou a passada."""
        if self.modo == MODO_S:
            raise ValueError("Este cofre abre só com a senha mestra: não tem chave de acesso.")

        def mudar():
            """Operação interna da troca de chave de acesso, numa transação."""
            if self._ks is None:
                if not senha:
                    raise ValueError("Informe a senha mestra para gerar uma nova chave de acesso.")
                self._ks = derivar_chave(unicodedata.normalize("NFC", senha), self.sal_pw, self.t, self.m, self.p)
                if self.modo == MODO_OU and not self.confere_senha(senha):
                    raise ChaveMalFormada("Senha mestra incorreta.")
            self.dek = secrets.token_bytes(32)
            ktxt = self._definir_chave_acesso()
            if self.modo == MODO_OU:
                self.nonce_pw, self.wrap_pw = _embrulhar(self._ks, self.dek)
            return ktxt
        r = self._com_desfazer(mudar)
        self.copias_nao_apagadas = apagar_copias(self.caminho)
        return r

    def adicionar_chave_acesso(self, novo_modo, senha=None):
        """Cofre criado SO com senha mestra: acrescenta depois a chave de acesso (sem recriar o cofre).
        novo_modo = MODO_E (senha E chave juntas, recomendado) ou MODO_OU (senha OU chave).
        Gera chave de acesso nova e chave interna (DEK) nova, como em gerar_nova_chave_acesso. Se a gravacao falhar,
        volta tudo ao que era (inclusive o modo). Devolve o texto da chave, que e mostrado UMA vez."""
        if self.modo != MODO_S:
            raise ValueError("Este cofre já tem chave de acesso.")
        if novo_modo not in (MODO_E, MODO_OU):
            raise ValueError("Modo inválido: escolha 'senha E chave' ou 'senha OU chave'.")

        def mudar():
            """Operacao interna: reembrulha a chave dos dados conforme o novo modo (numa transacao)."""
            if self._ks is None:
                if not senha:
                    raise ValueError("Informe a senha mestra para adicionar a chave de acesso.")
                if not self.confere_senha(senha):
                    raise ChaveMalFormada("Senha mestra incorreta.")
                self._ks = derivar_chave(unicodedata.normalize("NFC", senha), self.sal_pw, self.t, self.m, self.p)
            self.dek = secrets.token_bytes(32)           # chave interna nova: copias antigas (so com senha) morrem
            self.modo = novo_modo
            ktxt = self._definir_chave_acesso()
            if novo_modo == MODO_OU:                     # no E o embrulho ja foi refeito com senha+chave
                self.nonce_pw, self.wrap_pw = _embrulhar(self._ks, self.dek)
            return ktxt
        modo_antes = self.modo
        try:
            r = self._com_desfazer(mudar)
        except BaseException:
            self.modo = modo_antes
            raise
        self.copias_nao_apagadas = apagar_copias(self.caminho)   # ainda abririam so com a senha
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
        self.meta.setdefault("schema", 1)       # versão do esquema dos dados cifrados (p/ migrações futuras)
        self._diag_garantir()

    def _diag_garantir(self):
        """Cria (uma vez) o par de chaves do registro de diagnóstico: a privada fica aqui dentro, cifrada com o cofre;
        a pública vai no cabeçalho do arquivo .diag, para registrar falhas mesmo com o cofre trancado."""
        try:
            raw = base64.b64decode(self.meta.get("diag_priv", ""), validate=True)
            if len(raw) != 32:
                raise ValueError
            priv = X25519PrivateKey.from_private_bytes(raw)
        except Exception:
            priv = X25519PrivateKey.generate()
            self.meta["diag_priv"] = base64.b64encode(
                priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())).decode("ascii")
        try:
            diag_iniciar(self.caminho, _bytes_pub(priv))
        except (OSError, ValueError, TypeError):
            pass

    # ----- chave FIDO (as alterações só ficam valendo depois de salvar()) -----
    def salt_fido(self):
        """Salt usado para pedir o segredo à chave FIDO (o mesmo para todas as chaves do cofre)."""
        if self.fido:
            return self.fido["salt"]
        if self._salt_pendente is None:
            self._salt_pendente = secrets.token_bytes(32)
        return self._salt_pendente

    def verificar_estado_arquivos(self):
        """Confere, SEM alterar nada, o arquivo principal e as cópias automáticas (.bak1-.bak5) com a chave já
        aberta. Devolve o resultado de cada parte para a tela "Verificar integridade do cofre".
        Cada conferência é uma tupla (situação, itens, salvamento, detalhe); situação: "ok", "ausente", "antiga"
        (formato antigo, não conferível), "falha" (conteúdo não confere) ou "erro" (não foi possível ler)."""
        chave = _chave_dados(self.dek, _fator_total(self._F, self._G))

        def conferir(caminho):
            """Lê e decifra um arquivo de cofre e confere o manifesto interno (contagem e hash dos itens)."""
            try:
                with open(caminho, "rb") as f:
                    bruto = f.read(LIMITE_COFRE + 1)
            except FileNotFoundError:
                return ("ausente", 0, 0, "")
            except OSError as ex:
                return ("erro", 0, 0, texto_erro(ex))
            if len(bruto) > LIMITE_COFRE:
                return ("falha", 0, 0, "arquivo maior que o limite aceito")
            if bruto[:8] == MAGIC_V1:
                return ("antiga", 0, 0, "formato antigo")
            try:
                itens, meta = _decifrar_dados(chave, _ler_cabecalho(bruto), bruto)
            except (ArquivoInvalido, InvalidTag, ValueError, TypeError, UnicodeError, struct.error):
                return ("falha", 0, 0, "o conteúdo não confere (danificado ou alterado)")
            total = len(itens)
            for r in itens:                      # só queremos o resultado: apaga o texto em claro desta leitura
                for v in r.values():
                    zerar_objeto(v)
            return ("ok", total, _seq_de(meta), "")

        sobras = [os.path.basename(x) for x in [self.caminho + ".danificado"] + glob.glob(
            glob.escape(self.caminho) + ".*.danificado") if os.path.exists(x)]
        return {
            "principal": conferir(self.caminho),
            "copias": [(os.path.basename(c), *conferir(c)) for c in _copias(self.caminho)],
            "sobras": sorted(set(sobras)),
            "reversao": bool(self.alerta_reversao),
            "consulta": bool(self.somente_leitura),
        }

    def estado_fido(self):
        """Guarda uma cópia do estado FIDO para poder desfazer a operação."""
        import copy
        return copy.deepcopy(self.fido), self._F, self._salt_pendente

    def restaurar_fido(self, estado):
        """Devolve o estado FIDO guardado por estado_fido."""
        self.fido, self._F, self._salt_pendente = estado

    def _definir_codigo(self):
        """Gera UM código de recuperação para todos os fatores extras ativos (FIDO e/ou computadores): o mesmo
        código abre o cofre sem a chave FIDO e em qualquer computador. Devolve o texto; o código antigo deixa de valer."""
        rec_b, codigo = nova_chave_acesso()
        for secao, fator in ((self.fido, self._F), (self.pc, self._G)):
            if secao:
                sal = secrets.token_bytes(16)
                n, w = _embrulhar(_kek_recuperacao(rec_b, sal), fator)
                secao["rec"] = (sal, n, w)
        return codigo

    def adicionar_fido(self, nome, cred, saida):
        """Cadastra uma chave. Na PRIMEIRA chave ativa o FIDO e devolve o código de recuperação."""
        codigo = None
        if not self.fido:
            self._F = secrets.token_bytes(32)
            self.fido = {"salt": self.salt_fido(), "rec": None, "chaves": []}
            codigo = self._definir_codigo()
        if len(self.fido["chaves"]) >= MAX_FIDO:
            raise ValueError(f"Limite de {MAX_FIDO} chaves FIDO atingido.")
        if any(c["cred"] == cred for c in self.fido["chaves"]):
            raise ValueError("Esta chave FIDO já está cadastrada.")
        n, w = _embrulhar(_kek_fido(saida), self._F)
        self.fido["chaves"].append({"nome": (nome or "Chave FIDO")[:40], "cred": cred, "nonce": n, "wrap": w})
        return codigo

    def remover_fido(self, cred):
        """Remove uma credencial FIDO do cofre."""
        if not self.fido:
            return
        if len(self.fido["chaves"]) <= 1:
            raise ValueError("Não é possível remover a única chave. Use 'Desativar FIDO'.")
        self.fido["chaves"] = [c for c in self.fido["chaves"] if c["cred"] != cred]

    def novo_codigo_recuperacao(self):
        """Gera um novo código de recuperação do FIDO e devolve o texto dele."""
        if not self.fido and not self.pc:
            raise ValueError("FIDO não está ativo.")
        return self._definir_codigo()

    def desativar_fido(self):
        """Desliga a exigência da chave FIDO neste cofre."""
        self.fido, self._F, self._salt_pendente = None, None, None

    # ----- computadores autorizados (fator A MAIS; as alterações só ficam valendo depois de salvar()) -----
    def estado_pc(self):
        """Guarda uma cópia do estado dos computadores para poder desfazer a operação."""
        return copy.deepcopy(self.pc), self._G, copy.deepcopy(self.fido), self._F

    def restaurar_pc(self, estado):
        """Devolve o estado guardado por estado_pc."""
        self.pc, self._G, self.fido, self._F = estado

    def pcs_multiplos(self):
        """True se o usuário respondeu SIM a 'tem mais computadores para autorizar?'. Padrão: não (só 1 PC)."""
        return bool(self.meta.get("pcs_multiplos"))

    def limite_pc(self):
        """Quantos computadores podem estar autorizados: 1 até o usuário liberar mais; no máximo MAX_PC."""
        return MAX_PC if self.pcs_multiplos() else 1

    def definir_pcs_multiplos(self, sim):
        """Muda a resposta. Não deixa voltar para 'só 1 PC' enquanto houver mais de um autorizado."""
        if not sim and self.pc and len(self.pc["maquinas"]) > 1:
            raise ValueError("Remova os outros computadores antes de limitar o cofre a 1 computador.")
        self.meta["pcs_multiplos"] = bool(sim)

    def pc_adicionar(self, nome, local=False):
        """Autoriza ESTE computador. No PRIMEIRO ativa a exigência e devolve o código de recuperação (texto);
        nos seguintes devolve None. Precisa do cofre aberto (a chave dos dados já está na memória).
        local=True: reforça com o segredo local protegido pelo Windows (DPAPI); se não der, recusa (não enfraquece em silêncio)."""
        ids = identidades_do_pc()
        if not ids:
            raise ValueError("Não consegui identificar este computador (sem MachineGuid).")
        material = ids[0]
        if local:
            seg = segredo_local(criar=True)
            if not seg:
                raise ValueError("Não consegui criar o segredo local protegido pelo Windows neste computador.")
            material = _com_segredo_local(material, seg)
        codigo = None
        if not self.pc:
            self._G = secrets.token_bytes(32)
            self.pc = {"salt": secrets.token_bytes(32), "rec": None, "maquinas": []}
            codigo = self._definir_codigo()
        if len(self.pc["maquinas"]) >= self.limite_pc():
            if self.limite_pc() <= 1:
                raise ValueError("O cofre está limitado a 1 computador. Para autorizar outro, responda SIM a "
                                 f"'Tem mais computadores para autorizar?' (libera até {MAX_PC}).")
            raise ValueError(f"Limite de {MAX_PC} computadores autorizados atingido.")
        idm = _id_pc(self.pc["salt"], material)
        if any(m["id"] == idm for m in self.pc["maquinas"]):
            raise ValueError("Este computador já está autorizado.")
        n, w = _embrulhar(_kek_pc(material, self.pc["salt"]), self._G)
        self.pc["maquinas"].append({"nome": (nome or "Computador")[:40], "id": idm, "nonce": n, "wrap": w})
        return codigo

    def pc_remover(self, idm):
        """Tira um computador da lista (pelo id). Para tirar o último, use desativar_pc."""
        if not self.pc:
            return
        if len(self.pc["maquinas"]) <= 1:
            raise ValueError("Não é possível remover o único computador. Use 'Desativar'.")
        self.pc["maquinas"] = [m for m in self.pc["maquinas"] if m["id"] != idm]

    def desativar_pc(self):
        """Desliga a exigência de computador autorizado (o cofre volta a abrir em qualquer computador)."""
        self.pc, self._G = None, None

    def pc_id_deste(self):
        """Id (8 bytes) deste computador na lista do cofre, ou None se ele não está autorizado."""
        if not self.pc:
            return None
        for _, material in _variantes_do_pc():
            idm = _id_pc(self.pc["salt"], material)
            if any(m["id"] == idm for m in self.pc["maquinas"]):
                return idm
        return None

    def pc_nivel_deste(self):
        """'local' (reforçado com o segredo do Windows), 'basico', ou None se este computador não está na lista."""
        r = _achar_g_nivel(self.pc) if self.pc else None
        return r[1] if r else None

    def fechar(self):
        """Descarta as chaves e os itens da memória. Além de soltar as referências, sobrescreve com zeros
        (melhor esforço, só CPython) as chaves e os textos dos itens, para não sobrarem na RAM do processo."""
        with _TRAVA_SALVAR:
            for k in ("dek", "_ks", "_kb", "_F", "_G", "_vkey", "chave_gerada"):
                zerar_objeto(getattr(self, k, None), permitir_compartilhado=True)
            for m in (self._vmacs or []):
                zerar_objeto(m, permitir_compartilhado=True)
            for r in (self.registros or []):
                if isinstance(r, dict):
                    for v in r.values():
                        zerar_objeto(v, permitir_compartilhado=True)
            self.dek = None
            self._vkey = self._vmacs = None
            self._ks = None
            self._kb = None
            self._F = None
            self._G = None
            self.chave_gerada = None
            self.registros = []


# ----------------------------------------------------------------------------
# Importação de planilhas (Excel .xlsx/.xlsm e CSV)
# ----------------------------------------------------------------------------
LIMITE_LINHAS = 20000
LIMITE_ARQUIVO = 50 * 1024 * 1024          # 50 MB

# Campos de cada item do cofre
# "numero_conta" e "agencia" são os dados bancários (conta e agência): além de ficarem ocultos e criptografados
# como qualquer segredo (CAMPOS_SECRETOS), um item que tenha qualquer um dos dois preenchido SEMPRE pede a senha
# mestra de novo para ser visto, copiado ou editado -- mesmo com a "Proteção extra" (⋯ → Segurança) desligada
# para o resto do cofre. É a camada extra de segurança específica para dados bancários (ver _liberar_protegido).
CAMPOS = ("servico", "login", "senha", "senha_extra", "pin", "chave", "numero_conta", "agencia", "codigos",
          "notas", "grupo", "pessoa", "ativo")
CAMPOS_SECRETOS = ("senha", "senha_extra", "pin", "chave", "numero_conta", "agencia", "codigos")
ROTULOS = {"servico": "Conta / App", "login": "Login", "senha": "Senha", "senha_extra": "Senha extra",
           "pin": "PIN", "chave": "Chave", "numero_conta": "Número da conta", "agencia": "Agência",
           "codigos": "Códigos de recuperação", "notas": "Notas", "grupo": "Grupo", "pessoa": "Pessoa"}


def novo_item(**valores):
    """Cria um item (conta) com todos os campos vazios e um id novo; aceita valores iniciais."""
    item = {c: "" for c in CAMPOS}
    item["ativo"] = True
    item.update({k: v for k, v in valores.items() if k in CAMPOS})
    item["id"] = secrets.token_hex(8)
    return item


def _item_ativo(item):
    """Interpreta itens antigos/importados sem estado salvo como ativos."""
    return item.get("ativo", True) not in (False, 0, "0", "False", "false")


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
    """Texto sem acento, em minúsculas e sem pontuação, para comparar títulos de coluna."""
    import unicodedata
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def _campo_do_cabecalho(texto):
    """Descobre a qual campo do cofre um título de coluna da planilha corresponde."""
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


_CONTROLES = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")


def _limpar_texto(s):
    """Tira caracteres de controle e de direção de texto (RLO etc.), que forjam nomes na tela."""
    return _CONTROLES.sub("", s)


def _valor_celula(v):
    """Converte o valor de uma célula (número, data, texto) em texto limpo, sem caracteres de controle."""
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
    return _limpar_texto(str(v)).strip()


def _detectar_cabecalho(linhas):
    """Procura, nas 15 primeiras linhas, a que parece cabeçalho. Retorna (índice, mapa coluna->campo)."""
    for i, linha in enumerate(linhas[:15]):
        mapa = {}
        for col, cel in enumerate(linha):
            if re.search(r"\d", str(cel or "")):
                campo = None
            else:
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
    for lnh in linhas:
        cel = [c for c in lnh if c]
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
    linhas = [[_valor_celula(c) for c in lnh] for lnh in linhas]
    linhas = [lnh for lnh in linhas if any(lnh)]
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
        ncol = max(len(lnh) for lnh in linhas)
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


# ----------------------------------------------------------------------------
# Varredura de segurança de planilhas ANTES de importar
# ----------------------------------------------------------------------------
_FORMULA_PERIGOSA = re.compile(
    r"(?i)(\bDDE(AUTO)?\b|cmd\s*\||powershell|mshta|wscript|cscript|regsvr32|rundll32|msiexec|certutil|bitsadmin"
    r"|\|\s*'?\s*/c\b|WEBSERVICE\s*\(|IMPORT(DATA|XML|HTML|RANGE|FEED)\s*\(|HYPERLINK\s*\(|\bCALL\s*\(|"
    r"\bREGISTER(\.ID)?\s*\(|\bEXEC\s*\()")
_ENDERECO_PERIGOSO = re.compile(r"(?i)(file:|javascript:|vbscript:|data:text/html|\\\\[\w.$-]+\\|ms-[a-z]+:|search-ms:)")
_PARTES_PERIGOSAS_ZIP = (
    ("vbaproject.bin", "macros (código que roda dentro do Excel)"),
    ("/activex/", "controles ActiveX"),
    ("/embeddings/", "objetos embutidos (arquivos dentro da planilha)"),
    ("/externallinks/", "vínculos com outras planilhas ou endereços externos"),
    ("connections.xml", "conexões de dados externas"),
    ("oleobject", "objetos OLE embutidos"),
    ("/vmldrawing", None),
)
_EXTENSOES_EXECUTAVEIS = (".exe", ".dll", ".bat", ".cmd", ".ps1", ".js", ".vbs", ".lnk", ".scr", ".msi", ".com", ".jar",
                          ".hta", ".wsf", ".pif")


_PARTES_PERMITIDAS_ESTRITO = (".xml", ".rels", ".vml")          # num modelo do cofre só existe texto XML


def varrer_planilha(caminho, estrito=False):
    """Varredura de segurança do ARQUIVO antes de ler qualquer dado. Retorna (bloqueios, alertas).
    'bloqueios' = motivos para RECUSAR a importação (macros, objetos embutidos, vínculos externos, fórmulas de
    execução, zip suspeito). 'alertas' = coisas para o usuário saber. Nada é executado nem aberto: só se lê o
    conteúdo compactado como bytes. 'estrito' = só partes de texto XML são aceitas (qualquer outra parte dentro do
    arquivo, como imagem, binário ou programa, recusa a importação)."""
    bloqueios, alertas = [], []
    ext = os.path.splitext(caminho)[1].lower()
    if ext == ".xlsm":
        alertas.append("O arquivo é .xlsm (pode conter macros). Se tiver macro, a importação é recusada.")
    if ext not in (".xlsx", ".xlsm"):
        return bloqueios, alertas
    import zipfile
    try:
        with zipfile.ZipFile(caminho) as z:
            infos = z.infolist()
            if len(infos) > 5000:
                bloqueios.append(f"O arquivo tem {len(infos)} partes internas (o normal é menos de 100): suspeito.")
            achados, links_ext, n_formulas, formulas_ruins = set(), 0, 0, []
            for i in infos:
                nome = i.filename.replace("\\", "/")
                baixo = nome.lower()
                if nome.startswith("/") or ".." in nome.split("/") or re.match(r"^[A-Za-z]:", nome):
                    bloqueios.append("O arquivo tem um caminho interno malicioso (tentativa de gravar fora da pasta).")
                    break
                if i.flag_bits & 0x1:
                    bloqueios.append("O arquivo está protegido por senha: abra no Excel, remova a proteção e salve "
                                     "de novo.")
                    break
                if baixo.endswith(_EXTENSOES_EXECUTAVEIS):
                    bloqueios.append(f"Há um programa escondido dentro da planilha ({os.path.basename(nome)}).")
                elif estrito and not nome.endswith("/") and not baixo.endswith(_PARTES_PERMITIDAS_ESTRITO) \
                        and "printersettings" not in baixo:
                    bloqueios.append(f"Há uma parte estranha dentro da planilha ({os.path.basename(nome)}): um modelo do "
                                     "cofre só tem texto.")
                for trecho, descricao in _PARTES_PERIGOSAS_ZIP:
                    if descricao and trecho in "/" + baixo:
                        achados.add(descricao)
            for d in sorted(achados):
                bloqueios.append(f"A planilha contém {d}. O cofre NÃO importa isso. Abra no Excel e use 'Salvar como' > "
                                 "Pasta de Trabalho do Excel (.xlsx) ou CSV, só com os valores.")
            for i in infos:
                baixo = i.filename.lower()
                if i.file_size > 64 * 1024 * 1024 or not baixo.endswith((".xml", ".rels")):
                    continue
                with z.open(i) as f:
                    pedaco = f.read(8 * 1024 * 1024 + 1)
                if re.search(rb"<!(DOCTYPE|ENTITY)", pedaco[:4096], re.I):
                    bloqueios.append("Uma parte interna usa declarações XML perigosas (DOCTYPE/ENTITY): importação recusada.")
                    break
                if baixo.endswith(".rels"):
                    links_ext += len(re.findall(rb'TargetMode="External"', pedaco))
                    continue
                if baixo.startswith("xl/worksheets/"):
                    for m in re.finditer(rb"<f[^>]*>([^<]{1,2000})</f>", pedaco):
                        n_formulas += 1
                        txt = m.group(1).decode("utf-8", "replace")
                        if _FORMULA_PERIGOSA.search(txt) and len(formulas_ruins) < 3:
                            formulas_ruins.append(txt[:40])
            if formulas_ruins:
                bloqueios.append("Há fórmula(s) que tentam executar programas ou acessar a internet "
                                 f"(ex.: {formulas_ruins[0]!r}). Importação recusada.")
            if n_formulas:
                alertas.append(f"{n_formulas} célula(s) com fórmula: só o valor mostrado é lido; a fórmula em si não é "
                               "guardada nem executada.")
            if links_ext:
                alertas.append(f"{links_ext} link(s) para endereços externos no arquivo: o cofre NÃO os abre.")
    except zipfile.BadZipFile:
        pass                                                 # quem trata arquivo corrompido é o leitor
    return bloqueios, alertas


def varrer_registros(registros):
    """Varredura do CONTEÚDO já lido (xlsx ou csv): células com cara de fórmula de execução, endereços perigosos
    (file:, javascript:, \\\\servidor\\pasta) e campos gigantes. Em campos de texto comum (conta, login, notas, grupo,
    pessoa) a célula suspeita é neutralizada com uma aspa no início. Senhas nunca são alteradas. Retorna alertas."""
    n_formula = n_end = n_gigante = 0
    for r in registros:
        for k, v in r.items():
            if not isinstance(v, str) or not v:
                continue
            if len(v) > 20000:
                n_gigante += 1
            comum = k in ("servico", "login", "notas", "grupo", "pessoa")
            if v[:1] in "=+-@" and _FORMULA_PERIGOSA.search(v):
                n_formula += 1
                if comum:
                    r[k] = "'" + v
            if _ENDERECO_PERIGOSO.search(v):
                n_end += 1
    alertas = []
    if n_formula:
        alertas.append(f"{n_formula} campo(s) com texto de fórmula perigosa (ex.: =cmd|...). Nos campos comuns foi "
                       "neutralizado com uma aspa no início; confira a prévia.")
    if n_end:
        alertas.append(f"{n_end} campo(s) com endereço de risco (file:, javascript:, caminho de rede). Não são abertos.")
    if n_gigante:
        alertas.append(f"{n_gigante} campo(s) gigantes (mais de 20 mil caracteres): confira se é isso mesmo.")
    return alertas


# Assinaturas ("magic bytes") de arquivos que NÃO são planilhas: programas, PDF, pacotes. Uma planilha .xlsx começa com
# "PK\x03\x04" (é um ZIP); um .csv é texto puro. Qualquer outra identidade é recusada antes de abrir.
_ASSINATURAS_PROIBIDAS = ((b"MZ", "um programa do Windows (.exe/.dll)"), (b"\x7fELF", "um programa executável"),
                          (b"%PDF", "um PDF"), (b"#!", "um script"), (b"Rar!", "um pacote RAR"),
                          (b"7z\xbc\xaf", "um pacote 7-Zip"), (b"\xca\xfe\xba\xbe", "um programa executável"),
                          (b"\xcf\xfa\xed\xfe", "um programa executável"), (b"MSCF", "um instalador CAB"))
_ASSINATURA_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"          # Excel antigo (.xls) ou arquivo protegido por senha
LIMITES_CAMPO = {"servico": 300, "login": 300, "grupo": 300, "pessoa": 300, "senha": 1000, "senha_extra": 1000,
                 "pin": 100, "chave": 2000, "codigos": 20000, "notas": 10000}
TEMPO_LIMITE_LEITURA_S = 90                 # leitura da planilha: passou disso, a importação é abortada


def verificar_assinatura(cabeca, ext):
    """Confere a IDENTIDADE REAL do arquivo pelos primeiros bytes, não pela extensão. Levanta ValueError (mensagem
    humana) se um '.xlsx' for na verdade um programa, PDF etc., ou se não tiver a estrutura de uma planilha."""
    for assin, nome in _ASSINATURAS_PROIBIDAS:
        if cabeca.startswith(assin):
            raise ValueError(f"Este arquivo se diz planilha, mas por dentro é {nome}. Por segurança ele foi recusado "
                             "e nada foi aberto.")
    if ext in (".xlsx", ".xlsm"):
        if cabeca.startswith(_ASSINATURA_OLE):
            raise ValueError("Esta planilha está no formato antigo do Excel ou protegida por senha. Abra no Excel, "
                             "tire a senha e use 'Salvar como' > Pasta de Trabalho do Excel (.xlsx).")
        if not cabeca.startswith(b"PK\x03\x04"):
            raise ValueError("Estrutura de dados inválida: o arquivo não tem o formato de uma planilha .xlsx. "
                             "Nada foi importado.")
    elif ext == ".csv" and (cabeca.startswith(b"PK\x03\x04") or cabeca.startswith(_ASSINATURA_OLE)):
        raise ValueError("Estrutura de dados inválida: este '.csv' é na verdade uma planilha compactada. Salve-o "
                         "como CSV de verdade (texto) ou use o .xlsx.")


def sanear_registros(registros):
    """Validação RÍGIDA de esquema antes de qualquer coisa entrar no cofre: cada campo é texto, sem caracteres de controle
    (exceto quebra de linha em notas/códigos) e dentro do limite de tamanho. 'Ou está perfeito, ou é recusado':
    um campo fora do padrão derruba a importação inteira, sem tentar adivinhar. Devolve a mesma lista (campos limpos)."""
    for n, r in enumerate(registros, 1):
        for k, v in list(r.items()):
            if k not in LIMITES_CAMPO:
                continue
            if not isinstance(v, str):
                raise ValueError(f"Estrutura de dados inválida (item {n}, campo '{k}'). Nada foi importado.")
            if len(v) > LIMITES_CAMPO[k]:
                raise ValueError(f"Estrutura de dados inválida: o campo '{k}' do item {n} tem {len(v)} caracteres "
                                 f"(máximo {LIMITES_CAMPO[k]}). Nada foi importado.")
            if k in ("notas", "codigos"):
                limpo = _CONTROLES_SEM_QUEBRA.sub("", v)
            else:
                limpo = _limpar_texto(v)
            r[k] = limpo
    return registros


_CONTROLES_SEM_QUEBRA = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u202a-\u202e\u2066-\u2069]")


def _destruir_quarentena(pasta):
    """Sobrescreve e apaga os arquivos da zona de quarentena e remove a pasta (sem seguir atalhos)."""
    try:
        for nome in os.listdir(pasta):
            alvo = os.path.join(pasta, nome)
            try:
                if os.path.isfile(alvo) and not os.path.islink(alvo):
                    _destruir_um(alvo)
            except OSError:
                pass
        shutil.rmtree(pasta, ignore_errors=True)
    except OSError:
        pass


IMPORTAR_SOMENTE_COM_SELO = True     # True: o cofre só importa planilhas GERADAS POR ELE (modelo com selo conferido)


def ler_planilha(caminho, tempo_limite=None, selo=None, exigir_selo=False):
    """Importação em QUARENTENA. Retorna (registros, avisos). Etapas, todas antes de tocar no cofre:
    1) lê o arquivo UMA vez para a memória (limite 50 MB) e confere os 'magic bytes' (identidade real);
    2) analisa CSV diretamente dessa captura imutável; XLSX/XLSM são copiados para a quarentena privada;
    3) varre e lê a captura/cópia, só com bibliotecas Python, sem abrir Excel nem nenhum programa externo, com prazo;
    4) valida o esquema (tipos, tamanhos, caracteres de controle);
    5) destrói a quarentena de XLSX/XLSM. Qualquer falha descarta tudo: o cofre.dat nem chega a ser tocado.
    'selo' = (sal_k, nonce_k, wrap_k) do cofre aberto: com ele o SELO DE AUTENTICIDADE da planilha (modelo gerado
    pelo cofre) é conferido; selo falso ou estrutura alterada recusa a importação.
    'exigir_selo' = True: aceita SOMENTE planilha .xlsx com selo válido deste cofre (CSV, planilha comum, selo de
    outro cofre ou sem selo são recusados antes de ler qualquer dado)."""
    import threading
    import tempfile
    ext = os.path.splitext(caminho)[1].lower()
    with open(caminho, "rb") as fo:
        dados = fo.read(LIMITE_ARQUIVO + 1)
    if len(dados) > LIMITE_ARQUIVO:
        raise ValueError("Arquivo muito grande (limite de 50 MB).")
    if ext not in (".xlsx", ".xlsm", ".csv"):
        return _ler_planilha_arquivo(caminho, selo, exigir_selo)   # mensagens humanas de formato não suportado
    verificar_assinatura(dados[:16], ext)
    if ext == ".csv":
        quarentena = None
        copia = caminho
        dados_csv = dados
    else:
        raiz = _TEMP_PRIVADO["pasta"] or tempfile.gettempdir()
        quarentena = os.path.join(raiz, "quarentena_" + secrets.token_hex(6))
        os.makedirs(quarentena, mode=0o700, exist_ok=False)
        copia = os.path.join(quarentena, "entrada" + ext)
        dados_csv = None
    resultado, erro = [], []
    try:
        if dados_csv is None:
            with open(copia, "wb") as fq:
                fq.write(dados)
            del dados

        def trabalho():
            """Lê e valida a cópia da quarentena (roda numa thread para poder ter prazo)."""
            try:
                regs, avisos = _ler_planilha_arquivo(copia, selo, exigir_selo, dados_csv=dados_csv)
                resultado.append((sanear_registros(regs), avisos))
            except BaseException as ex:                  # noqa: BLE001 - qualquer falha vira recusa da importação
                erro.append(ex)
        th = threading.Thread(target=trabalho, daemon=True)
        th.start()
        th.join(tempo_limite or TEMPO_LIMITE_LEITURA_S)
        if th.is_alive():
            raise ValueError("A leitura da planilha demorou demais e foi cancelada por segurança. Nada foi importado.")
        if erro:
            e = erro[0]
            if isinstance(e, (ValueError, OSError)):
                raise e
            raise ValueError("Estrutura de dados inválida: não foi possível ler a planilha com segurança. "
                             "Nada foi importado.") from None
        return resultado[0]
    finally:
        if quarentena is not None:
            _destruir_quarentena(quarentena)


def _ler_planilha_arquivo(caminho, selo=None, exigir_selo=False, dados_csv=None):
    """Lê .xlsx/.xlsm/.csv e retorna (registros, avisos). Nunca grava nada no disco.
    Em .xlsx/.xlsm confere o selo de autenticidade (se 'selo' do cofre foi informado). CSV pode receber a captura
    original em memória para evitar gravar texto aberto em disco."""
    tamanho = len(dados_csv) if dados_csv is not None else os.path.getsize(caminho)
    if tamanho > LIMITE_ARQUIVO:
        raise ValueError("Arquivo muito grande (limite de 50 MB).")
    ext = os.path.splitext(caminho)[1].lower()
    registros, avisos = [], []
    _segue_modelo_oficial = False
    if exigir_selo and ext not in (".xlsx", ".xlsm"):
        raise ValueError("IMPORTAÇÃO SEGURA: o cofre só aceita a planilha GERADA POR ELE.\n\n"
                         "Arquivos CSV e outros formatos não têm como ser confirmados pelo cofre. Baixe o modelo em  "
                         "⋯ > Baixar modelo de planilha,  cole suas linhas na aba 'Senhas' e salve como .xlsx.\n\n"
                         "Nada foi lido nem importado.")
    bloqueios, alertas_varredura = varrer_planilha(caminho, estrito=exigir_selo)   # ANTES de ler qualquer dado
    if bloqueios:
        raise ValueError("VARREDURA DE SEGURANÇA: importação recusada.\n\n• " + "\n• ".join(bloqueios) +
                         "\n\nNada foi lido nem importado.")

    if ext in (".xlsx", ".xlsm"):
        try:
            import openpyxl
        except ImportError:
            raise ValueError("Falta a biblioteca de Excel. Rode:  pip install openpyxl defusedxml") from None
        try:
            import zipfile
            with zipfile.ZipFile(caminho) as z:                 # zip bomb: limita o tamanho descompactado
                total = sum(i.file_size for i in z.infolist())
                comp = max(1, sum(i.compress_size for i in z.infolist()))
                maior = max((i.file_size for i in z.infolist()), default=0)
                if maior > 200 * 1024 * 1024 or total > 400 * 1024 * 1024 or (total > 20 * 1024 * 1024 and total / comp > 200):
                    raise ValueError("A planilha descompactada é grande demais (ou suspeita). Importação recusada.")
        except zipfile.BadZipFile:
            raise ValueError("Não foi possível ler a planilha (arquivo corrompido ou protegido por senha).") from None
        try:
            wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
        except Exception as ex:
            raise ValueError(f"Não foi possível ler a planilha (está protegida por senha ou corrompida?).\n{ex}") from None
        try:
            estado_selo, texto_selo = verificar_selo_planilha(wb, selo)
            if estado_selo == "adulterado":
                raise ValueError("SELO DE AUTENTICIDADE: importação recusada.\n\n" + texto_selo +
                                 "\n\nNada foi lido nem importado. Baixe um modelo novo em  ⋯ > Baixar modelo de planilha  "
                                 "e preencha apenas as linhas da aba 'Senhas'.")
            if exigir_selo and estado_selo != "ok":
                motivo = {"ausente": "Esta planilha NÃO foi gerada por este cofre (não tem o selo de autenticidade).",
                          "outro_cofre": texto_selo,
                          "desconhecido": "O cofre não conseguiu conferir o selo desta planilha."}.get(estado_selo, texto_selo)
                raise ValueError("IMPORTAÇÃO SEGURA: o cofre só aceita a planilha GERADA POR ELE e confirmada pelo selo.\n\n"
                                 + motivo + "\n\nBaixe o modelo em  ⋯ > Baixar modelo de planilha,  cole suas linhas na "
                                 "aba 'Senhas' (só os dados) e importe o arquivo salvo.\n\nNada foi lido nem importado.")
            if estado_selo == "ok":
                _segue_modelo_oficial = True
                avisos.append("🛡 OK Selo de autenticidade confere: " + texto_selo)
                avisos.append("🛡 OK Estrutura idêntica à gerada pelo cofre (abas e títulos das colunas intactos).")
            elif estado_selo == "outro_cofre":
                avisos.append("🛡 " + texto_selo)
            abas = [w for w in wb.worksheets if not _ABAS_DE_AJUDA.match(w.title or "")]
            varias = len(abas) > 1
            for ws in abas:
                linhas, cheias, vazias_seguidas = [], 0, 0
                for linha in ws.iter_rows(values_only=True, max_col=60):
                    if not any(c not in (None, "") for c in linha):
                        vazias_seguidas += 1            # linhas só formatadas: não contam no limite
                        if vazias_seguidas > 2000:
                            break                       # o resto da aba é formatação vazia
                        linhas.append([])
                        continue
                    vazias_seguidas = 0
                    cheias += 1
                    linhas.append(list(linha))
                    if cheias > LIMITE_LINHAS:
                        raise ValueError(f"A aba '{ws.title}' tem mais de {LIMITE_LINHAS} linhas com dados.")
                if any(lnh[:len(CABECALHO_MODELO)] == list(CABECALHO_MODELO) for lnh in linhas[:5] if lnh):
                    _segue_modelo_oficial = True            # cabeçalho idêntico ao do modelo gerado pelo cofre
                regs, av = _linhas_para_registros(linhas, ws.title, ws.title if varias else "")
                registros += regs
                avisos += av
        finally:
            wb.close()
    elif ext == ".csv":
        import csv
        if dados_csv is None:
            with open(caminho, "rb") as fcsv:
                bruto = fcsv.read(LIMITE_ARQUIVO + 1)
        else:
            bruto = dados_csv
        if b"\0" in bruto[:65536]:
            raise ValueError("Este arquivo parece binário, não um CSV de texto.")
        for cod in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                texto = bruto.decode(cod)
                break
            except UnicodeDecodeError:
                continue
        linhas_brutas = texto.splitlines()
        primeira = linhas_brutas[0].strip() if linhas_brutas else ""
        if primeira.lower().startswith("sep=") and len(primeira) >= 4:
            primeira = linhas_brutas[1].strip() if len(linhas_brutas) > 1 else ""
            inicio_texto = texto.find("\n")
            if inicio_texto >= 0:
                texto = texto[inicio_texto + 1:]
        candidatos = []
        for delimitador in (",", ";", "\t"):
            conta = 0
            aspas = False
            for caractere in primeira:
                if caractere == '"':
                    aspas = not aspas
                elif not aspas and caractere == delimitador:
                    conta += 1
            candidatos.append((conta, delimitador))
        _, delimitador = max(candidatos, key=lambda item: item[0])
        if max((item[0] for item in candidatos), default=0) == 0:
            delimitador = ","
        dialeto = csv.excel
        dialeto.delimiter = delimitador
        import io
        try:
            linhas = list(csv.reader(io.StringIO(texto, newline=""), dialeto))
        except csv.Error as ex:             # ex.: campo com mais de 128 mil caracteres, ou CSV malformado
            raise ValueError("O CSV tem um campo gigante (mais de 128 mil caracteres) ou está malformado. "
                             f"Importação recusada. ({ex})") from None
        if len(linhas) > LIMITE_LINHAS:
            raise ValueError(f"O arquivo tem mais de {LIMITE_LINHAS} linhas.")
        if any([str(x).strip() for x in lnh[:len(CABECALHO_MODELO)]] == list(CABECALHO_MODELO) for lnh in linhas[:5] if lnh):
            _segue_modelo_oficial = True
        registros, avisos = _linhas_para_registros(linhas)
    elif ext == ".xls":
        raise ValueError("Formato .xls antigo não é suportado. Abra no Excel e use "
                         "'Salvar como' > Pasta de Trabalho do Excel (.xlsx).")
    else:
        raise ValueError("Use um arquivo .xlsx, .xlsm ou .csv.")

    alertas_varredura += varrer_registros(registros)
    if not _segue_modelo_oficial:
        avisos.insert(0, "ℹ Esta planilha não segue o MODELO OFICIAL do cofre (⋯ > Baixar modelo): as colunas foram "
                         "reconhecidas pelo nome. Para menos surpresas, use o modelo.")
    avisos = ["🛡 " + a for a in alertas_varredura] + avisos
    if not alertas_varredura:
        avisos.insert(0, "🛡 OK Varredura de segurança: nada suspeito (sem macros, objetos embutidos, vínculos externos "
                         "nem fórmulas de execução).")
    n_exemplos = sum(1 for r in registros if _e_exemplo(r))
    if n_exemplos:
        registros = [r for r in registros if not _e_exemplo(r)]
        avisos.append(f"{n_exemplos} linha(s) de EXEMPLO (Conta começando com 'EXEMPLO') foram ignoradas.")
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


_ABAS_DE_AJUDA = re.compile(r"(?i)^\s*(como preencher|leia[- ]?me|instru[cç][oõ]es|ajuda|lea[- ]?me|listas|_selo_cofre)\b")


def _e_exemplo(registro):
    """True se a linha é de EXEMPLO do modelo (Conta começando com 'EXEMPLO'): não é importada."""
    return _normalizar(registro.get("servico", "")).startswith("exemplo")


CABECALHO_MODELO = ("Conta / App", "Login", "Senha", "Senha extra", "PIN", "Chave")      # começo do cabeçalho do modelo


ABA_SELO = "_selo_cofre"                    # aba MUITO oculta com o selo de autenticidade da planilha
MARCA_SELO = "COFRE-SELO-V1"
ABAS_DO_MODELO = ("Leia-me", "Senhas", "Listas")
CABECALHO_COMPLETO = ("Conta / App", "Login", "Senha", "Senha extra", "PIN", "Chave",
                      "Códigos de recuperação", "Notas", "Grupo", "Pessoa")


def _chave_mac_planilha(selo):
    """(id público do cofre em hex, chave HMAC) tirados do cabeçalho do cofre (sal_k, nonce_k, wrap_k). Só quem tem
    este cofre consegue conferir; ninguém sem ele consegue fabricar um selo válido."""
    sal_k, nonce_k, wrap_k = selo
    ident, _kek = _selo_do_cofre(sal_k, nonce_k, wrap_k)
    base = bytes(sal_k) + bytes(nonce_k) + bytes(wrap_k)
    chave = HKDF(algorithm=hashes.SHA256(), length=32, salt=bytes(sal_k), info=b"cofre-selo-planilha-v1").derive(base)
    return ident.hex(), chave


def _esqueleto_planilha(abas_visiveis, cabecalho):
    """Hash (SHA-256) da ESTRUTURA da planilha: nomes das abas visíveis e título das colunas. O que o
    usuário digita nas linhas de dados não entra: só a estrutura é selada (o Excel regrava o arquivo inteiro ao
    salvar, mas não muda abas nem títulos)."""
    dados = json.dumps({"abas": list(abas_visiveis), "cabecalho": [str(c or "").strip() for c in cabecalho]},
                       ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(dados.encode("utf-8")).hexdigest()


def _mac_selo(chave, ident, tipo, criado, id_arq, esqueleto):
    """HMAC-SHA256 dos campos do selo."""
    import hmac
    msg = "|".join((MARCA_SELO, ident, tipo, criado, id_arq, esqueleto)).encode("utf-8")
    return hmac.new(chave, msg, hashlib.sha256).hexdigest()


def verificar_selo_planilha(wb, selo):
    """Confere o selo de autenticidade de uma planilha aberta (openpyxl). Retorna (estado, texto):
    'ausente' (não é um modelo selado), 'desconhecido' (cofre sem dados para conferir), 'ok' (gerada por ESTE cofre
    e com a estrutura intacta), 'outro_cofre' (selo válido de outro cofre: origem não comprovável aqui) ou
    'adulterado' (diz ser deste cofre, mas a estrutura ou o selo foram alterados/falsificados)."""
    import hmac
    aba = next((w for w in wb.worksheets if w.title == ABA_SELO), None)
    if aba is None:
        return "ausente", ""
    if selo is None:
        return "desconhecido", ""
    campos = {}
    try:
        for lin in aba.iter_rows(min_row=1, max_row=12, max_col=2, values_only=True):
            if lin and lin[0] is not None:
                campos[str(lin[0])] = "" if len(lin) < 2 or lin[1] is None else str(lin[1])
    except Exception:                                     # noqa: BLE001 - aba ilegível = selo inválido
        return "adulterado", "O selo da planilha está ilegível."
    if MARCA_SELO not in campos or not all(k in campos for k in ("id_cofre", "tipo", "criado_utc", "id_arquivo",
                                                                 "esqueleto", "mac")):
        return "adulterado", "A planilha tem uma aba de selo incompleta ou falsificada."
    try:
        ident, chave = _chave_mac_planilha(selo)
    except Exception:                                     # noqa: BLE001
        return "desconhecido", ""
    if campos["id_cofre"] != ident:
        return "outro_cofre", ("Planilha com selo de OUTRO cofre (ou de antes de uma reinstalação): não dá para comprovar "
                               "a origem. A varredura de segurança normal foi aplicada.")
    visiveis = [w.title for w in wb.worksheets if w.title != ABA_SELO and getattr(w, "sheet_state", "visible") == "visible"]
    cab = ()
    senhas = next((w for w in wb.worksheets if w.title == "Senhas"), None)
    if senhas is not None:
        for lin in senhas.iter_rows(min_row=1, max_row=1, max_col=len(CABECALHO_COMPLETO), values_only=True):
            cab = tuple(lin)
            break
    esq = _esqueleto_planilha(visiveis, cab)
    esperado = _mac_selo(chave, ident, campos["tipo"], campos["criado_utc"], campos["id_arquivo"], campos["esqueleto"])
    if not hmac.compare_digest(esperado, campos["mac"]):
        return "adulterado", "O selo de autenticidade não confere: o arquivo foi alterado depois de gerado pelo cofre, ou o selo é falso."
    if not hmac.compare_digest(esq, campos["esqueleto"]):
        return "adulterado", ("A estrutura da planilha (abas ou títulos das colunas) foi alterada depois de gerada pelo "
                              "cofre.")
    return "ok", f"modelo gerado por este cofre em {campos['criado_utc'][:10]} (código {campos['id_arquivo']}), estrutura intacta."


def criar_modelo_planilha(destino, selo=None):
    """Grava a planilha modelo em visual corporativo/BI (paleta slate + azul, tipografia Segoe UI/Consolas, grade
    nítida, filtro e formatação condicional de qualidade de dado) — pedido do usuário 2026-11-13, que mandou uma
    versão própria editada à mão como referência de nível "cooportativo empresarial". Aba 'Leia-me' (como usar,
    regras de segurança e o que é cada coluna), aba 'Senhas' (tabela com exemplos de vários perfis e grupos; o
    cofre ignora as linhas EXEMPLO) e aba 'Listas' (grupos e perfis sugeridos, editáveis). Com 'selo' = (sal_k,
    nonce_k, wrap_k) do cofre, grava também a aba muito oculta com o SELO DE AUTENTICIDADE: o cofre confere, ao
    importar, que o arquivo nasceu dele e que a estrutura não foi adulterada. Nada aqui muda a LINHA 1 da aba
    'Senhas' (continua sendo o cabeçalho real, lido por _ler_planilha_arquivo/verificar_selo_planilha) nem o
    texto das colunas (CABECALHO_COMPLETO) nem os nomes/ordem das abas (ABAS_DO_MODELO): só a aparência.
    Pedido do usuário 2026-11-13: o CABEÇALHO (linha 1) da aba 'Senhas' fica TRAVADO (célula bloqueada + planilha
    protegida, sem senha -- é só proteção contra arraste/edição por acidente, não segurança: qualquer um destrava
    em Revisão > Desproteger planilha) para nunca "sair do lugar"; ordenar (ex.: pela seta do cabeçalho "Conta /
    App" > Classificar de A a Z) continua liberado e NUNCA arrasta o cabeçalho para dentro dos dados -- com a
    linha 1 bloqueada, o Excel recusa qualquer ordenação cuja seleção inclua o cabeçalho. Não há como a planilha
    se reordenar SOZINHA sem fórmula/macro (ambas são bloqueadas de propósito na importação, por segurança -- ver
    varrer_planilha); o que existe é essa ordenação de um clique, sempre disponível, sem precisar destravar nada.
    Isto não muda o selo: _esqueleto_planilha só olha nomes de aba e texto do cabeçalho, nunca proteção/formatação."""
    import openpyxl
    from datetime import UTC, datetime
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.formatting.rule import FormulaRule
    # Paleta "slate + azul" (tons do Tailwind CSS, de leitura profissional e neutra, como em painéis de BI):
    NAVY = "1E293B"                      # slate-800: cabeçalho da tabela e barra de título do Leia-me
    AZUL, AZUL_CLARO, CINZA = "2563EB", "EFF6FF", "F8FAFC"     # blue-600 / blue-50 / slate-50: seções e zebra
    VERDE, AMBAR = "15803D", "B45309"    # green-700 / amber-700: regras de segurança do Leia-me
    BORDA_COR = "CBD5E1"                 # slate-300: bordas finas e nítidas em toda a grade de dados
    CINZA_EXEMPLO, TEXTO_EXEMPLO = "F1F5F9", "64748B"          # slate-100 / slate-500: linhas EXEMPLO
    VERM_BG, VERM_TXT = "FEF2F2", "991B1B"                     # red-50 / red-800: avisos e célula incompleta
    AMB_BG = "FFFBEB"                    # amber-50: aviso de senha curta
    FONTE, FONTE_MONO = "Segoe UI", "Consolas"      # Consolas nos campos "tipo senha": alinha 0/O e 1/l/I
    fino = Side(style="thin", color="D0D5DD")
    borda = Border(left=fino, right=fino, top=fino, bottom=fino)
    fino2 = Side(style="thin", color=BORDA_COR)
    borda2 = Border(left=fino2, right=fino2, top=fino2, bottom=fino2)
    wb = openpyxl.Workbook()

    # ---------------- Leia-me ----------------
    la = wb.active
    la.title = "Leia-me"
    la.sheet_view.showGridLines = False
    for col, larg in zip("ABCDE", (4, 30, 52, 30, 4), strict=False):
        la.column_dimensions[col].width = larg
    la.merge_cells("B1:D1")
    la["B1"] = "Planilha de importação — Arca"
    la["B1"].font = Font(name=FONTE, bold=True, size=18, color="FFFFFF")
    la["B1"].fill = PatternFill("solid", fgColor=NAVY)
    la["B1"].alignment = Alignment(vertical="center", indent=1)
    la.row_dimensions[1].height = 40
    la.merge_cells("B2:D2")
    la["B2"] = "Preencha a aba “Senhas”, salve e importe no cofre. Leva cerca de 1 minuto."
    la["B2"].font = Font(name=FONTE, italic=True, color="64748B")
    la["B2"].alignment = Alignment(indent=1)
    linha = 4

    def titulo(texto):
        """Título de seção em faixa azul."""
        nonlocal linha
        la.merge_cells(start_row=linha, start_column=2, end_row=linha, end_column=4)
        c = la.cell(row=linha, column=2, value=texto)
        c.font = Font(name=FONTE, bold=True, size=12, color=AZUL)
        c.fill = PatternFill("solid", fgColor=AZUL_CLARO)
        c.alignment = Alignment(indent=1, vertical="center")
        la.row_dimensions[linha].height = 24
        linha += 1
    titulo("COMO USAR — 5 passos")
    passos = (
        ("1", "Abra a aba “Senhas”", "Cada LINHA é uma conta. As linhas EXEMPLO mostram o jeito certo; o cofre as ignora (pode apagá-las)."),
        ("2", "Escolha o PERFIL (coluna Pessoa)", "Quem é o dono da conta: Eu, Pai, Mãe, Eu - Trabalho... Pode criar quantos perfis quiser: o cofre cria sozinho."),
        ("3", "Escolha o GRUPO (coluna Grupo)", "A categoria dentro do perfil: Banco, Compras, Google, E-mail... ou um nome seu. O grupo pertence ao perfil da linha."),
        ("4", "Preencha o resto (opcional)", "Só “Conta / App” é obrigatória. Códigos de recuperação: vários na mesma célula, um por linha (Alt+Enter)."),
        ("5", "Salve e importe", "No cofre: menu  ⋯  >  Importar planilha. Ele confere o selo, faz a varredura de segurança e mostra uma PRÉVIA antes de gravar."),
    )
    for n, t, d in passos:
        la.cell(row=linha, column=2, value=f"{n}.  {t}").font = Font(name=FONTE, bold=True)
        la.cell(row=linha, column=2).alignment = Alignment(vertical="top", wrap_text=True, indent=1)
        la.merge_cells(start_row=linha, start_column=3, end_row=linha, end_column=4)
        c = la.cell(row=linha, column=3, value=d)
        c.font = Font(name=FONTE)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        la.row_dimensions[linha].height = 34
        linha += 1
    linha += 1
    titulo("SEGURANÇA — leia antes de importar")
    regras = (
        ("🛡  Selo de autenticidade", "Esta planilha traz um selo que só o SEU cofre sabe conferir. Se alguém alterar a estrutura (abas ou títulos), a importação é recusada."),
        ("🚫  Sem macros e sem fórmulas", "Nunca use macros, links externos, objetos embutidos ou fórmulas. O cofre bloqueia tudo isso e só lê o texto das células."),
        ("🗑  Apague depois", "A planilha guarda as senhas SEM criptografia. Depois de importar, apague o arquivo (e esvazie a lixeira)."),
        ("💾  Guarde no pendrive", "Preencha e salve a planilha no pendrive do cofre, nunca na nuvem nem em e-mail."),
    )
    for t, d in regras:
        c = la.cell(row=linha, column=2, value=t)
        c.font = Font(name=FONTE, bold=True, color=VERDE if t.startswith("🛡") else AMBAR if t.startswith("🗑") else "334155")
        c.alignment = Alignment(vertical="top", wrap_text=True, indent=1)
        la.merge_cells(start_row=linha, start_column=3, end_row=linha, end_column=4)
        c2 = la.cell(row=linha, column=3, value=d)
        c2.font = Font(name=FONTE)
        c2.alignment = Alignment(wrap_text=True, vertical="top")
        la.row_dimensions[linha].height = 34
        linha += 1
    linha += 1
    titulo("O QUE É CADA COLUNA")
    for j, h in enumerate(("Coluna", "Para que serve", "Exemplo"), start=2):
        c = la.cell(row=linha, column=j, value=h)
        c.font = Font(name=FONTE, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=NAVY)
        c.alignment = Alignment(indent=1)
    linha += 1
    colunas = (
        ("Conta / App  (obrigatória)", "Nome do site, app ou cartão.", "Banco Azul"),
        ("Login", "Usuário, e-mail ou número da conta.", "joao.silva"),
        ("Senha", "A senha principal.", "MinhaSenha#2026"),
        ("Senha extra", "Segunda senha (ex.: senha de transações).", "Senha6dig"),
        ("PIN", "Número curto (cartão, celular). Mantém o zero à esquerda.", "0123"),
        ("Chave", "Chave de acesso, token ou frase secreta.", "chave-longa-aqui"),
        ("Códigos de recuperação", "Vários códigos, um por linha dentro da célula.", "abcd-1234-efgh"),
        ("Notas", "Qualquer observação.", "cartão final 1234"),
        ("Grupo", "Categoria da conta DENTRO do perfil (Banco, Compras, Google...).", "Banco"),
        ("Pessoa", "Perfil dono da conta (Eu, Pai, Mãe, Eu - Trabalho...).", "Eu"),
    )
    for k, (col, serve, ex) in enumerate(colunas):
        for j, v in enumerate((col, serve, ex), start=2):
            c = la.cell(row=linha, column=j, value=v)
            c.border = borda
            c.alignment = Alignment(wrap_text=True, vertical="top", indent=1)
            c.fill = PatternFill("solid", fgColor=CINZA if k % 2 else "FFFFFF")
            c.font = Font(name=FONTE, bold=(j == 2))
        linha += 1
    linha += 1
    la.merge_cells(start_row=linha, start_column=2, end_row=linha, end_column=4)
    c = la.cell(row=linha, column=2,
                value="💡  Para reorganizar pela conta: na aba “Senhas”, clique na setinha do cabeçalho “Conta / "
                      "App” e escolha “Classificar de A a Z”. O cabeçalho fica TRAVADO (não é possível editá-lo "
                      "nem arrastá-lo para dentro da ordenação) -- ele nunca sai do lugar.")
    c.font = Font(name=FONTE, italic=True, color="334155")
    c.alignment = Alignment(wrap_text=True, vertical="top", indent=1)
    la.row_dimensions[linha].height = 34
    linha += 1
    la.page_setup.orientation = "portrait"
    la.page_setup.fitToWidth = 1
    la.sheet_properties.pageSetUpPr = openpyxl.worksheet.properties.PageSetupProperties(fitToPage=True)

    # ---------------- Senhas ----------------
    ws = wb.create_sheet("Senhas")
    ws.sheet_view.showGridLines = False                 # grade fina e explícita (abaixo) no lugar da grade padrão do Excel
    ws.append(list(CABECALHO_COMPLETO))
    COLS_SEGREDO = "CDEFG"            # Senha, Senha extra, PIN, Chave, Códigos: fonte Consolas (0/O e 1/l/I não se confundem)
    COLS_CENTRO = "EIJ"               # PIN, Grupo, Pessoa: colunas curtas/categóricas, centralizadas como no cabeçalho
    for c in ws[1]:
        c.font = Font(name=FONTE, bold=True, size=11, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=NAVY)
        c.border = Border(left=fino2, right=fino2, top=fino2, bottom=Side(style="medium", color=NAVY))
        c.alignment = Alignment(vertical="center", wrap_text=True,
                                 horizontal="center" if c.column_letter in COLS_CENTRO else "left", indent=1)
        c.protection = Protection(locked=True)        # cabeçalho TRAVADO (ver ws.protection.sheet mais abaixo):
                                                        # nunca é editado, arrastado nem entra numa ordenação
    ws.row_dimensions[1].height = 32
    # Nota (balão) sobre o cabeçalho avisando que as linhas cinzentas são só exemplo: um comentário/balão em vez
    # de uma linha nova no topo, de propósito — o cabeçalho PRECISA continuar na linha 1 (é o que o selo de
    # autenticidade e a importação conferem; ver _esqueleto_planilha/verificar_selo_planilha e
    # _ler_planilha_arquivo, que leem a linha 1 como cabeçalho). Aparece ao passar o mouse ou clicar na célula.
    from openpyxl.comments import Comment
    ws["A1"].comment = Comment("As linhas CINZENTAS abaixo (\"EXEMPLO - ...\") são só modelo: o cofre as ignora "
                               "ao importar. Pode apagá-las e preencher as suas por cima.", "Arca Sistemas",
                               width=260, height=90)
    exemplos = (
        ("EXEMPLO - Banco Azul", "joao.silva", "MinhaSenha#2026", "Senha6dig", "0123", "",
         "abcd-1234-efgh\nijkl-5678-mnop\nqrst-9012-uvwx", "Linhas EXEMPLO são ignoradas pelo cofre", "Banco", "Eu"),
        ("EXEMPLO - Loja Online", "joao@email.com", "OutraSenha#77", "", "", "", "", "", "Compras", "Eu"),
        ("EXEMPLO - Conta Google", "joao@gmail.com", "Terceira#Senha9", "", "", "", "", "", "Google", "Eu"),
        ("EXEMPLO - Sistema da Empresa", "joao.trab", "Trab#Senha55", "", "", "", "", "", "Trabalho", "Eu - Trabalho"),
        ("EXEMPLO - Banco do Pai", "pai.silva", "SenhaDoPai#1", "", "4321", "", "", "", "Banco", "Pai"),
        ("EXEMPLO - E-mail da Mãe", "mae@email.com", "SenhaDaMae#2", "", "", "", "", "", "E-mail", "Mãe"),
    )
    for ex in exemplos:
        ws.append(list(ex))
    ultima = 1 + 100
    for linha_n in range(2, ultima + 1):
        for col in "DEFG":                              # PIN, chave e códigos como texto: mantém zeros à esquerda
            ws[f"{col}{linha_n}"].number_format = "@"
        for c in ws[linha_n][:10]:
            mono = c.column_letter in COLS_SEGREDO
            c.font = Font(name=FONTE_MONO if mono else FONTE, size=10)
            c.border = borda2
            c.alignment = Alignment(wrap_text=True, vertical="top",
                                     horizontal="center" if c.column_letter in COLS_CENTRO else "left")
            c.protection = Protection(locked=False)    # linhas de dados ficam DESTRAVADAS (só o cabeçalho é travado)
    for linha_ex in ws.iter_rows(min_row=2, max_row=1 + len(exemplos)):
        for c in linha_ex:
            mono = c.column_letter in COLS_SEGREDO
            c.font = Font(name=FONTE_MONO if mono else FONTE, size=10, italic=True, color=TEXTO_EXEMPLO)
            c.fill = PatternFill("solid", fgColor=CINZA_EXEMPLO)
    for col, larg in zip("ABCDEFGHIJ", (30, 26, 22, 16, 10, 20, 32, 34, 18, 18), strict=False):
        ws.column_dimensions[col].width = larg
    ws.auto_filter.ref = f"A1:J{ultima}"                 # filtro/ordenação (estilo BI) sem a faixa zebrada de um Table
    ws.freeze_panes = "B2"
    ws.sheet_properties.tabColor = NAVY
    # Cabeçalho TRAVADO (pedido do usuário 2026-11-13): com a planilha protegida e só a linha 1 bloqueada
    # (Protection(locked=True) acima; as células de dados ficam locked=False), o Excel recusa editar ou arrastar
    # o cabeçalho, e recusa qualquer ordenação cuja seleção inclua a linha 1 -- o cabeçalho nunca "sai do lugar".
    # SEM senha de propósito: é só trava contra acidente (como o freeze_panes acima), não segurança -- qualquer
    # um desprotege em Revisão > Desproteger planilha, sem pedir nada. 'sort' e 'autoFilter' = False LIBERAM essas
    # ações mesmo com a planilha protegida (é assim que dá para ordenar pela conta -- seta do cabeçalho > Classificar
    # -- sem precisar desproteger nada); 'insertRows'/'deleteRows' = False mantêm o que o Leia-me já promete
    # ("pode apagar as linhas EXEMPLO", "escolha o grupo... ou crie um novo" implica poder acrescentar linha).
    # Não muda o selo: _esqueleto_planilha só olha nomes de aba e texto do cabeçalho (ver comentário na função).
    ws.protection.sheet = True
    ws.protection.sort = False
    ws.protection.autoFilter = False
    ws.protection.insertRows = False
    ws.protection.deleteRows = False
    ws.protection.formatCells = False
    ws.protection.formatColumns = False
    ws.protection.formatRows = False
    ws.protection.selectLockedCells = False              # pode clicar no cabeçalho (ver o comentário/balão), só não editar
    # Qualidade de dado em tempo real (estilo painel de BI): linha começada sem nome da conta, e senha digitada
    # com menos de 8 caracteres (fora das linhas EXEMPLO) ganham destaque visual na hora, antes mesmo de abrir o cofre.
    ws.conditional_formatting.add(
        f"A2:J{ultima}",
        FormulaRule(formula=["AND(ISBLANK($A2),COUNTA($B2:$J2)>0)"], fill=PatternFill("solid", fgColor=AMB_BG)))
    ws.conditional_formatting.add(
        f"C2:C{ultima}",
        FormulaRule(formula=['AND(NOT(ISBLANK($C2)),LEFT($A2,7)<>"EXEMPLO",LEN($C2)<8)'],
                    fill=PatternFill("solid", fgColor=VERM_BG), font=Font(name=FONTE_MONO, size=10, color=VERM_TXT)))
    rodape = ultima + 1                                  # aviso de segurança sempre visível, logo abaixo da tabela
    ws.merge_cells(start_row=rodape, start_column=1, end_row=rodape, end_column=10)
    c = ws.cell(row=rodape, column=1,
                value="⚠  Esta planilha guarda os dados SEM criptografia. Depois de importar no cofre, apague este "
                      "arquivo com segurança (⋯ > Importar planilha já oferece isso) e esvazie a Lixeira.")
    c.font = Font(name=FONTE, bold=True, size=10, color=VERM_TXT)
    c.fill = PatternFill("solid", fgColor=VERM_BG)
    c.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
    ws.row_dimensions[rodape].height = 30
    ws.page_setup.orientation = "landscape"             # se alguém imprimir (ex.: conferência), cabe tudo numa página de largura
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = openpyxl.worksheet.properties.PageSetupProperties(fitToPage=True)

    # ---------------- Listas ----------------
    li = wb.create_sheet("Listas")
    li.sheet_view.showGridLines = False
    li["A1"], li["B1"] = "Grupos sugeridos", "Perfis sugeridos"
    for c in (li["A1"], li["B1"]):
        c.font = Font(name=FONTE, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=NAVY)
    grupos = ("Banco", "Compras", "Google", "Redes sociais", "E-mail", "Trabalho", "Streaming", "Jogos", "Governo", "Saúde")
    perfis = ("Eu", "Eu - Trabalho", "Pai", "Mãe", "Esposa", "Marido", "Filho", "Filha")
    for i in range(30):
        c1 = li.cell(row=2 + i, column=1, value=grupos[i] if i < len(grupos) else None)
        c2 = li.cell(row=2 + i, column=2, value=perfis[i] if i < len(perfis) else None)
        c1.border = c2.border = borda
        c1.font = c2.font = Font(name=FONTE, size=10)
    li["D1"] = "Acrescente os seus nas colunas ao lado (as listas da aba Senhas leem daqui). Grupo e perfil novos também podem ser digitados direto: o cofre cria sozinho."
    li["D1"].font = Font(name=FONTE, size=10, italic=True, color=TEXTO_EXEMPLO)
    li["D1"].alignment = Alignment(wrap_text=True, vertical="top")
    li.column_dimensions["A"].width = 24
    li.column_dimensions["B"].width = 24
    li.column_dimensions["D"].width = 50
    li.sheet_properties.tabColor = "94A3B8"              # slate-400: tom neutro, discreto ao lado do azul-marinho das outras abas
    for col, rot, intervalo, dica in (("I", "Grupo", "=Listas!$A$2:$A$31", "Escolha um grupo da lista ou digite um nome novo. O grupo pertence ao perfil desta linha."),
                                      ("J", "Pessoa", "=Listas!$B$2:$B$31", "Perfil dono da conta: Eu, Pai, Mãe... ou um nome novo.")):
        dv = DataValidation(type="list", formula1=intervalo, allow_blank=True, showErrorMessage=False,
                            showInputMessage=True, promptTitle=rot, prompt=dica)
        ws.add_data_validation(dv)
        dv.add(f"{col}2:{col}{ultima}")

    # ---------------- Selo de autenticidade ----------------
    if selo is not None:
        ident, chave = _chave_mac_planilha(selo)
        criado = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        id_arq = secrets.token_hex(8)
        esq = _esqueleto_planilha(ABAS_DO_MODELO, CABECALHO_COMPLETO)
        mac = _mac_selo(chave, ident, "modelo", criado, id_arq, esq)
        se = wb.create_sheet(ABA_SELO)
        for k, v in ((MARCA_SELO, ""), ("id_cofre", ident), ("tipo", "modelo"), ("criado_utc", criado),
                     ("id_arquivo", id_arq), ("esqueleto", esq), ("mac", mac)):
            se.append([k, v])
        se.sheet_state = "veryHidden"
    wb.active = 0                                    # abre no Leia-me
    wb.save(destino)


# ----------------------------------------------------------------------------
# Chave FIDO2 (YubiKey, Feitian, Titan...) pela API WebAuthn do Windows
# Usa a extensão PRF (hmac-secret): a chave devolve um segredo que nunca sai do chip
# sem o toque físico e o PIN da própria chave.
# ----------------------------------------------------------------------------
def _hwnd(janela):
    """Identificador (HWND) da janela principal, usado pela API WebAuthn do Windows."""
    if not EH_WINDOWS:
        return None
    try:
        janela.update_idletasks()
        return _u32.GetAncestor(janela.winfo_id(), 2)
    except Exception:
        return None


def _fido_cliente(hwnd):
    """Cria o cliente WebAuthn do Windows para falar com a chave FIDO."""
    if not EH_WINDOWS:
        raise FidoErro("A chave FIDO só funciona no Windows.")
    try:
        from fido2.client import DefaultClientDataCollector
        from fido2.client.windows import WindowsClient
    except ImportError:
        raise FidoErro("Falta a biblioteca FIDO. Rode:  pip install fido2  (ou use o instalar_cofre).") from None
    if not WindowsClient.is_available():
        raise FidoErro("Este Windows não oferece suporte a chaves FIDO (requer Windows 10 1903 ou mais novo).")
    coletor = DefaultClientDataCollector("https://" + RP_ID, verify=lambda *a: True)
    return WindowsClient(coletor, handle=hwnd)


def nivel_protecao(modo, m, fido, pc=None):
    """Ranking de proteção do cofre (0 a 100) a partir do que está ATIVO: modo, memória do Argon2 e credenciais FIDO.
    Devolve (pontos, nome do nível, itens). Cada item: (rótulo, pontos, ativo, ação), onde 'ação' diz o que o
    usuário ainda pode ligar ('fido', 'reserva', 'pc') ou None quando não dá para mudar depois de criado."""
    chaves = (fido or {}).get("chaves", []) if fido else []
    itens = [("Senha mestra", 30, True, None)]
    if modo == MODO_E:
        itens.append(("Chave de acesso obrigatória (senha E chave)", 25, True, None))
    elif modo == MODO_OU:
        itens.append(("Chave de acesso (senha OU chave)", 12, True, None))
    else:
        itens.append(("Chave de acesso (só se escolhida ao criar o cofre)", 25, False, None))
    itens.append(("Chave de segurança FIDO (USB/NFC)", 20, bool(chaves), "fido"))
    itens.append(("Segunda chave de reserva", 7, len(chaves) >= 2, "reserva"))
    itens.append(("Computador autorizado (fator extra)", 10, bool(pc), "pc"))
    if m >= NIVEIS["maximo"][1]:
        itens.append(("Proteção máxima contra tentativas (1 GB)", 10, True, None))
    else:
        itens.append(("Proteção alta contra tentativas (256 MB)", 5, True, None))
    pontos = min(sum(p for _, p, ativo, _ in itens if ativo), 100)
    if modo == MODO_OU:
        pontos = min(pontos, 100)
    nome = "Básica" if pontos < 40 else "Boa" if pontos < 65 else "Forte" if pontos < 90 else "Máxima"
    return pontos, nome, itens


def _msg_fido(ex):
    """Traduz o erro do FIDO/Windows numa mensagem curta que diz o PRÓXIMO PASSO (sem código técnico na
    frente). O código original vai entre parênteses, no fim, só para o diagnóstico."""
    try:
        from fido2.client import ClientError
    except ImportError:
        ClientError = None
    if ClientError is not None and isinstance(ex, ClientError):
        cod = ex.code.name
        causa = str(ex.cause or "")
        baixa = causa.lower()
        if "cancel" in baixa or "0x800704c7" in baixa:
            return "Você cancelou. Tente de novo e toque na chave quando ela piscar."
        if "pin" in baixa and any(x in baixa for x in ("not set", "not_set", "notset", "no pin", "not configured", "0x35")):
            return ("A chave ainda não tem PIN. Crie um PIN nela (Configurações do Windows > Contas > Opções de entrada > "
                    "Chave de segurança > Gerenciar) e tente de novo.")
        if "pin" in baixa and any(x in baixa for x in ("blocked", "locked", "auth_blocked", "0x32", "0x34")):
            return ("O PIN da chave está BLOQUEADO (erros demais). Só desbloqueia redefinindo a chave, o que APAGA as "
                    "credenciais dela. Para abrir o cofre agora use a segunda chave ou o código de recuperação.")
        if "pin" in baixa and any(x in baixa for x in ("incorrect", "invalid", "wrong", "incorret", "0x8010006")):
            return ("O PIN da chave não confere. Digite o PIN certo da chave (ela bloqueia depois de poucos erros).")
        if cod == "TIMEOUT":
            return "A chave não foi tocada a tempo. Toque nela quando a luz piscar e tente de novo."
        if cod == "DEVICE_INELIGIBLE":
            return "Esta chave não é a cadastrada neste cofre. Use a chave certa."
        if cod == "CONFIGURATION_UNSUPPORTED":
            return "Esta chave não tem o recurso necessário. " + _diagnostico_fido()
        return (f"Não deu certo com a chave. Confira se ela está bem encaixada, toque nela quando piscar "
                f"e tente de novo. ({cod})")
    return f"Não consegui falar com a chave FIDO. Encaixe a chave e tente de novo. ({type(ex).__name__})"


def _fido_registrar(hwnd, nome=_NOME_APP):
    """Cria uma credencial na chave física (1 toque + PIN da chave). Retorna o ID da credencial."""
    cli = _fido_cliente(hwnd)
    opcoes = {
        "rp": {"id": RP_ID, "name": _NOME_APP},
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
        raise FidoErro(_msg_fido(ex)) from None
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
        "extensions": {"prf": {"eval": {"first": salt}}},
    }
    try:
        resp = cli.get_assertion(pedido).get_response(0)
    except FidoErro:
        raise
    except Exception as ex:
        raise FidoErro(_msg_fido(ex)) from None
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
    """Extrai o segredo da extensão PRF (hmac-secret) da resposta da chave."""
    prf = resp.client_extension_results.prf
    resultados = getattr(prf, "results", None) if prf else None
    saida = getattr(resultados, "first", None) if resultados else None
    if not saida or len(saida) != 32:
        raise FidoErro("A chave FIDO não devolveu o segredo (hmac-secret). " + _diagnostico_fido())
    return bytes(resp.raw_id), bytes(saida)


def fido_registrar(hwnd, nome=_NOME_APP):
    """Cadastra uma chave FIDO nova (toque físico e PIN dela) e devolve os dados da credencial."""
    with processo_liberado():
        return _fido_registrar(hwnd, nome)


def fido_obter(hwnd, creds, salt):
    """Pede à chave FIDO o segredo da credencial e do sal."""
    with processo_liberado():
        return _fido_obter(hwnd, creds, salt)


def fido_cadastrar_e_testar(hwnd, salt, nome=_NOME_APP):
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
    "fraco": "#8891a8",      # contraste >= 4,5:1 sobre fundo, painéis, campos e destaques (WCAG AA)
    # acento
    "prim": "#5a51ea",         # texto branco: 5,5:1 (WCAG AA)
    "prim_hover": "#6c63ff",
    "prim_press": "#4b43d1",
    "prim_txt": "#a8a3ff",
    "prim_fundo": "#211f42",  # seleção / destaque suave
    "prim_fg": "#ffffff",
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

CORES_BASE = dict(CORES)
PALETAS = {
    "Roxo (atual)": CORES_BASE.copy(),
    "Obsidiana": {
        **CORES_BASE, "fundo": "#111315", "lateral": "#0d0f11", "sup": "#181a1e",
        "sup2": "#1f2228", "sup3": "#252932", "sup4": "#30353d", "campo": "#121417",
        "borda": "#242830", "borda2": "#2c303a", "texto": "#f3f4f6", "suave": "#9ca3af",
        "fraco": "#8b919e", "prim": "#059669", "prim_hover": "#10b981", "prim_press": "#047857",
        "prim_txt": "#34d399", "prim_fundo": "#102c24", "prim_fg": "#ffffff",
        "ok": "#34d399", "ok_fundo": "#102c24", "alerta": "#f59e0b", "alerta_fundo": "#30230e",
        "perigo": "#f05252", "perigo_fundo": "#301819", "num": "#7dd3fc", "sim": "#f472b6",
    },
    "Claro": {
        **CORES_BASE, "fundo": "#f4f5f7", "lateral": "#eceef2", "sup": "#ffffff",
        "sup2": "#f1f3f5", "sup3": "#e8ebf0", "sup4": "#dfe3e9", "campo": "#f9fafb",
        "borda": "#e2e5ea", "borda2": "#d1d5db", "texto": "#111827", "suave": "#4b5563",
        "fraco": "#626875", "prim": "#1d4ed8", "prim_hover": "#2563eb", "prim_press": "#1e40af",
        "prim_txt": "#2563eb", "prim_fundo": "#dbeafe", "prim_fg": "#ffffff",
        "ok": "#15803d", "ok_fundo": "#dcfce7", "alerta": "#b45309", "alerta_fundo": "#fef3c7",
        "perigo": "#b91c1c", "perigo_fundo": "#fee2e2", "num": "#1d4ed8", "sim": "#be185d",
    },
    "Terminal": {
        **CORES_BASE, "fundo": "#090a0b", "lateral": "#08090b", "sup": "#0e1013",
        "sup2": "#14171c", "sup3": "#171b22", "sup4": "#22262e", "campo": "#08090b",
        "borda": "#1c2026", "borda2": "#282d37", "texto": "#e5e7eb", "suave": "#94a3b8",
        "fraco": "#8391a6", "prim": "#0ea5e9", "prim_hover": "#38bdf8", "prim_press": "#0284c7",
        "prim_txt": "#38bdf8", "prim_fundo": "#102b38", "prim_fg": "#041019",
        "ok": "#34d399", "ok_fundo": "#102c24", "alerta": "#fbbf24", "alerta_fundo": "#30250e",
        "perigo": "#f87171", "perigo_fundo": "#301819", "num": "#38bdf8", "sim": "#f472b6",
    },
    "Azul (Novo Item)": {
        **CORES_BASE, "fundo": "#0b101d", "lateral": "#090e1a", "sup": "#111827",
        "sup2": "#182235", "sup3": "#202d43", "sup4": "#2b3a54", "campo": "#090e1a",
        "borda": "#202b3d", "borda2": "#334155", "texto": "#f8fafc", "suave": "#cbd5e1",
        "fraco": "#94a3b8", "prim": "#2563eb", "prim_hover": "#3b82f6", "prim_press": "#1d4ed8",
        "prim_txt": "#93c5fd", "prim_fundo": "#172554", "prim_fg": "#ffffff",
        "ok": "#34d399", "ok_fundo": "#102c24", "alerta": "#fbbf24", "alerta_fundo": "#30250e",
        "perigo": "#fb7185", "perigo_fundo": "#301819", "num": "#7dd3fc", "sim": "#f472b6",
    },
    "Rosa": {
        **CORES_BASE, "fundo": "#160e14", "lateral": "#100a0f", "sup": "#21151e",
        "sup2": "#2c1c28", "sup3": "#392533", "sup4": "#48303f", "campo": "#180f16",
        "borda": "#382631", "borda2": "#503743", "texto": "#f8f1f5", "suave": "#d2bcc8",
        "fraco": "#b18b9f", "prim": "#b45382", "prim_hover": "#c86c9a", "prim_press": "#934267",
        "prim_txt": "#e7a9c5", "prim_fundo": "#3a2030", "prim_fg": "#ffffff",
        "ok": "#34d399", "ok_fundo": "#102c24", "alerta": "#fbbf24", "alerta_fundo": "#30250e",
        "perigo": "#fb7185", "perigo_fundo": "#301819", "num": "#7dd3fc", "sim": "#f0a8d0",
    },
}
TEMA_PADRAO = "Roxo (atual)"
TEMA_ATUAL = TEMA_PADRAO


def _caminho_preferencias():
    """Preferências visuais globais, sem senhas nem dados de cofres."""
    if EH_WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "CofreSenhas", "preferencias.json")


def _luminancia_wcag(cor):
    """Calcula a luminância relativa de uma cor sRGB para escolher texto legível."""
    canais = [v / 255 for v in _hex(cor)]
    canais = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in canais]
    return 0.2126 * canais[0] + 0.7152 * canais[1] + 0.0722 * canais[2]


def _contraste_wcag(a, b):
    """Calcula a razão de contraste WCAG entre duas cores."""
    l1, l2 = sorted((_luminancia_wcag(a), _luminancia_wcag(b)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def _texto_contraste(fundo):
    """Seleciona entre texto claro e escuro o que tiver maior contraste com o fundo."""
    claro, escuro = "#ffffff", "#111827"
    return max((claro, escuro), key=lambda cor: _contraste_wcag(cor, fundo))


def _cores_da_paleta(nome):
    """Devolve uma paleta independente, incluindo aliases antigos usados pela interface."""
    cores = PALETAS.get(nome)
    if cores is None:
        raise ValueError(f"Tema desconhecido: {nome}")
    cores = dict(cores)
    cores["prim_fg"] = _texto_contraste(cores["prim"])
    cores.update({
        "prim_esc": cores["prim_press"], "prim_claro": cores["prim_fundo"], "sel": cores["prim_fundo"],
        "lateral_sel": cores["prim_fundo"], "lateral_txt": cores["texto"], "lateral_titulo": cores["fraco"],
        "cabecalho": cores["fundo"], "noite": cores["fundo"], "neutro": cores["sup2"],
        "neutro_hover": cores["sup3"],
    })
    return cores


_IMAGENS_APOSENTADAS = []              # imagens da paleta anterior, mantidas vivas até a próxima troca


def _definir_tema(nome):
    """Aplica os valores globais de cor e limpa imagens cacheadas com a paleta anterior."""
    global TEMA_ATUAL, _IMAGENS_APOSENTADAS
    novas = _cores_da_paleta(nome)
    # As telas antigas ainda estão visíveis até a nova ficar pronta e seus botões usam estas imagens: se o cache
    # fosse esvaziado agora, o Python apagaria as imagens do Tk e qualquer redesenho da tela antiga daria
    # "image doesn't exist". Guardamos a geração anterior viva até a PRÓXIMA troca de tema.
    _IMAGENS_APOSENTADAS = [dict(_CACHE_ICONES), dict(_PONTOS)]
    CORES.clear()
    CORES.update(novas)
    TEMA_ATUAL = nome
    _CACHE_ICONES.clear()
    _PONTOS.clear()


def _carregar_preferencia_tema():
    """Lê a única preferência global de aparência; arquivo ausente significa o roxo padrão."""
    caminho = _caminho_preferencias()
    if not os.path.exists(caminho):
        return TEMA_PADRAO
    try:
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
        if not isinstance(dados, dict):
            raise ValueError("Formato da preferência não reconhecido.")
        nome = dados.get("tema", TEMA_PADRAO)
        if nome == "Personalizada":
            nome = dados.get("base", TEMA_PADRAO)
        if not isinstance(nome, str) or nome not in PALETAS:
            raise ValueError("Tema salvo não é reconhecido.")
        return nome
    except (OSError, ValueError, TypeError) as ex:
        print(f"AVISO: não foi possível ler a preferência de aparência: {ex}", file=sys.stderr)
        return TEMA_PADRAO


def _salvar_preferencia_tema(nome):
    """Salva a aparência global de forma atômica, sem registrar dados do cofre."""
    if not isinstance(nome, str) or nome not in PALETAS:
        raise ValueError(f"Tema desconhecido: {nome}")
    caminho = _caminho_preferencias()
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    dados = {"tema": nome}
    fd, temporario = tempfile.mkstemp(prefix="preferencias-", suffix=".tmp", dir=os.path.dirname(caminho))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporario, caminho)
    except OSError:
        try:
            os.unlink(temporario)
        except OSError:
            pass
        raise


def apagar_dados_locais(segredo=False):
    """Apaga o que o programa guarda FORA do cofre, em %LOCALAPPDATA%\\CofreSenhas: a preferência de aparência
    (sempre) e, com segredo=True, também o segredo local deste computador (pc_local.bin). Remove a pasta se
    ela ficar vazia. Nunca levanta erro; devolve os nomes do que foi apagado.
    segredo=False é o padrão de propósito: outro cofre neste computador pode depender desse segredo."""
    apagados = []
    alvos = [_caminho_preferencias()] + glob.glob(glob.escape(os.path.join(os.path.dirname(_caminho_preferencias()),
                                                                           "preferencias-")) + "*.tmp")
    if segredo:
        alvos.append(_arquivo_segredo_local())
    for alvo in alvos:
        try:
            if os.path.isfile(alvo):
                _destruir_um(alvo)
                apagados.append(os.path.basename(alvo))
        except OSError:
            pass
    for pasta in {os.path.dirname(a) for a in alvos}:
        try:
            os.rmdir(pasta)                 # só remove se estiver vazia
        except OSError:
            pass
    return apagados


TONS = ("#6c63ff", "#22a6c9", "#2fbf71", "#e3a03a", "#e0568f", "#9a6bff", "#3d8bfd", "#f07a3c",
        "#20b2a0", "#e05561")


# ---------- escala da tela (Windows com 125%, 150%...) ----------
ESCALA = 1.0


def _px(n):
    """Converte um tamanho pensado para 100% no tamanho real da tela."""
    return int(round(n * ESCALA))


def definir_escala(root):
    """Ajusta a escala de desenho ao zoom do Windows (DPI)."""
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
    """Converte '#rrggbb' em (r, g, b)."""
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _sd_rrect(px, py, x0, y0, x1, y1, r):
    """Distância assinada de um ponto a um retângulo de cantos arredondados (para desenho suavizado)."""
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    qx = abs(px - cx) - ((x1 - x0) / 2 - r)
    qy = abs(py - cy) - ((y1 - y0) / 2 - r)
    return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r


def _sd_circ(px, py, cx, cy, r):
    """Distância assinada de um ponto a um círculo."""
    return math.hypot(px - cx, py - cy) - r


def _sd_seg(px, py, ax, ay, bx, by):
    """Distância de um ponto a um segmento de reta."""
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy or 1)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


class _Tela:
    """Imagem RGBA pequena, com composição 'por cima' (alfa pré-multiplicado)."""

    def __init__(self, w, h):
        """Cria uma tela de pixels RGBA para desenhar formas suavizadas."""
        self.s = ESCALA                      # as formas são descritas em tamanho 100% e desenhadas na escala real
        self.w, self.h = max(1, int(round(w * self.s))), max(1, int(round(h * self.s)))
        self.px = [0.0] * (self.w * self.h * 4)

    def pintar(self, dist, cor, alfa=1.0, bruto=False):
        """Pinta os pixels cuja distância assinada é negativa, com borda suave (antisserrilhado)."""
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
        """Retângulo arredondado preenchido."""
        return self.pintar(lambda x, y: _sd_rrect(x, y, x0, y0, x1, y1, r), cor, alfa)

    def contorno(self, x0, y0, x1, y1, r, cor, larg=1.0, alfa=1.0):
        """Contorno de retângulo arredondado."""
        m = larg / 2
        return self.pintar(lambda x, y: abs(_sd_rrect(x, y, x0 + m, y0 + m, x1 - m, y1 - m, max(r - m, 0))) - m,
                           cor, alfa)

    def circ(self, cx, cy, r, cor, alfa=1.0):
        """Círculo preenchido."""
        return self.pintar(lambda x, y: _sd_circ(x, y, cx, cy, r), cor, alfa)

    def anel(self, cx, cy, r, cor, larg=1.0, alfa=1.0):
        """Anel (contorno de círculo)."""
        return self.pintar(lambda x, y: abs(_sd_circ(x, y, cx, cy, r - larg / 2)) - larg / 2, cor, alfa)

    def linha(self, pontos, cor, larg=1.5, alfa=1.0):
        """Linha formada por vários segmentos."""
        segs = list(zip(pontos, pontos[1:], strict=False))
        return self.pintar(lambda x, y: min(_sd_seg(x, y, a[0], a[1], b[0], b[1]) for a, b in segs) - larg / 2,
                           cor, alfa)

    def png(self):
        """Codifica a tela como PNG (sem biblioteca de imagem)."""
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
            """Monta um bloco (chunk) do PNG com tamanho e CRC."""
            return (struct.pack(">I", len(dados)) + tipo + dados
                    + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF))
        return (b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 6, 0, 0, 0))
                + bloco(b"IDAT", zlib.compress(b"".join(linhas), 9)) + bloco(b"IEND", b""))

    def imagem(self, master):
        """Converte a tela numa imagem do Tk."""
        return tk.PhotoImage(master=master, data=base64.b64encode(self.png()), format="png")


# ---------- peças do tema ----------
def _pecas():
    """Desenha todas as peças. Retorna {nome: _Tela}."""
    C = CORES
    P = {}
    T = _Tela

    def botao(fundo, borda, foco=False, sombra=True):
        """Desenha o botão comum nos 4 estados."""
        t = T(24, 24)
        if sombra:
            t.ret(0, 1, 24, 24, 6, "#000000", 0.35)
        t.ret(0, 0, 24, 23, 6, fundo)
        t.contorno(0, 0, 24, 23, 6, C["prim"] if foco else borda, 1.6 if foco else 1.0)
        return t
    P["btn"] = botao(C["sup2"], C["borda2"])
    P["btn_hover"] = botao(C["sup3"], C["borda2"])
    P["btn_press"] = botao(C["sup"], C["borda2"], sombra=False)
    P["btn_dis"] = botao(C["sup"], C["borda"], sombra=False)
    P["btn_foco"] = botao(C["sup2"], C["borda2"], foco=True)
    P["btn_foco_hover"] = botao(C["sup3"], C["borda2"], foco=True)

    def acento(fundo, foco=False, sombra=True):
        """Desenha o botão de destaque (cor principal)."""
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
    P["pri_dis"] = acento(C["prim_fundo"], sombra=False)
    P["pri_foco"] = acento(C["prim"], foco=True)
    P["pri_foco_hover"] = acento(C["prim_hover"], foco=True)

    def perigo(fundo, borda, foco=False):
        """Desenha o botão de ação perigosa."""
        t = T(24, 24)
        t.ret(0, 0, 24, 23, 6, fundo)
        t.contorno(0, 0, 24, 23, 6, C["prim"] if foco else borda, 1.6 if foco else 1.0)
        return t
    P["per"] = perigo(C["sup2"], C["borda2"])
    P["per_hover"] = perigo(C["perigo_fundo"], C["perigo"])
    P["per_press"] = perigo(C["perigo_fundo"], C["perigo"])
    P["per_foco"] = perigo(C["sup2"], C["borda2"], True)

    def fantasma(fundo=None, foco=False):
        """Desenha o botão discreto (sem fundo até passar o mouse)."""
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
        """Desenha o fundo dos campos de texto."""
        t = T(24, 24)
        t.ret(0, 0, 24, 24, 6, fundo)
        t.contorno(0, 0, 24, 24, 6, borda, larg)
        if foco:
            t.pintar(lambda x, y: _sd_rrect(x, y, 1, 0, 23, 23, 5.5) if y > 21 else 9, C["prim"])
        return t
    P["campo"] = campo(C["borda2"])
    P["campo_hover"] = campo(C["borda2"], fundo=C["sup2"])
    P["campo_foco"] = campo(C["prim"], foco=True, larg=1.3)
    P["campo_dis"] = campo(C["borda"], fundo=C["sup"])
    P["campo_erro"] = campo(C["perigo"], larg=1.3)

    def caixa(estado):
        """Desenha a caixa de seleção (checkbutton) no estado dado."""
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
        """Desenha o botão de opção (radiobutton) no estado dado."""
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
        """Desenha o interruptor ligado/desligado."""
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
        """Desenha o cursor do controle deslizante."""
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
        """Desenha a barra de rolagem (vertical ou horizontal)."""
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
        """Desenha o cartão (painel com borda)."""
        t = T(32, 32)
        t.ret(0, 0, 32, 32, 10, fundo)
        t.contorno(0, 0, 32, 32, 10, borda, 1.0)
        return t
    P["cartao"] = cartao(C["sup"], C["borda"])
    P["cartao2"] = cartao(C["sup2"], C["borda"])
    P["etiqueta"] = T(16, 16).ret(0, 0, 16, 16, 6, C["sup3"])

    def seta(direcao, cor=C["suave"], tam=(10, 6)):
        """Desenha uma seta na direção indicada."""
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
        """Desenha uma aba (selecionada ou com o mouse em cima)."""
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
    """Nomes das famílias de fonte instaladas."""
    try:
        return set(tkfont.families(root))
    except tk.TclError:
        return set()


FONTES = {}


def preparar_fontes(root):
    """Escolhe as famílias de fonte disponíveis (com alternativas) e registra as fontes nomeadas do programa."""
    fam = _familias(root)

    def escolher(*nomes):
        """Devolve a primeira fonte da lista que existe; senão, a última."""
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
        "CofreRotulo": (forte, 9, peso),
        "CofreSub": (titulo, 13, peso_t),
        "CofreTitulo": (titulo, 19, peso_t),
        "CofreGrande": (titulo, 24, peso_t),
        "CofreMono": (mono, 11, "normal"),
        "CofreMonoG": (mono, 14, "normal"),
    }
    for nome, (f, tam, p) in specs.items():
        atual = FONTES.get(nome)
        if atual is not None:
            try:                                    # chamada repetida (troca de tema): só reajusta a fonte que já existe
                atual.configure(family=f, size=tam, weight=p)
                continue
            except tk.TclError:
                pass                                # era de outra janela (já destruída): cria de novo abaixo
        try:
            FONTES[nome] = tkfont.Font(root=root, name=nome, family=f, size=tam, weight=p, exists=False)
        except tk.TclError:
            # o nome já existe nesta janela: usa a existente SEM descartar o objeto antigo antes (descartar um objeto
            # Font apaga a fonte nomeada no Tk e a configuração seguinte falharia com "named font does not exist")
            novo = tkfont.Font(root=root, name=nome, exists=True)
            novo.configure(family=f, size=tam, weight=p)
            FONTES[nome] = novo
    FONTES["_icone"] = icone
    return FONTES


# Ícones do próprio Windows (Segoe Fluent Icons / MDL2) com símbolo reserva
ICONES = {
    "busca": ("", "⌕"), "novo": ("", "+"), "cadeado": ("", "🔒"), "aberto": ("", "🔓"),
    "copiar": ("", "⧉"), "ver": ("", "👁"), "ocultar": ("", "◡"), "editar": ("", "✎"),
    "excluir": ("", "🗑"), "imprimir": ("", "⎙"), "config": ("", "⚙"), "mais": ("", "⋯"),
    "chave": ("", "🔑"), "pessoa": ("", "👤"), "alerta": ("", "⚠"), "ok": ("", "✓"),
    "fechar": ("", "✕"), "gerar": ("", "⤨"), "importar": ("", "⤓"), "salvar": ("", "💾"),
    "grupo": ("", "▤"), "historico": ("", "⟲"), "teclado": ("", "⌨"),
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
    except (AttributeError, tk.TclError):
        pass


def _apagar_campo_ao_fechar(campo):
    """Apaga o conteúdo digitado num campo de texto ANTES de ele ser destruído (senhas e chaves não ficam esperando o
    coletor de lixo). Campos ligados a uma variável (textvariable) ficam como estão, porque o programa pode ainda ler a
    variável depois. Silencioso se o campo já não existir."""
    try:
        if str(campo.cget("textvariable")) == "":
            campo.delete(0, "end")
    except (AttributeError, tk.TclError):
        pass


def _instalar_limpeza_de_campos():
    """Faz todo campo de texto (tk.Entry e ttk.Entry) se apagar ao ser destruído: vale para telas e janelas de diálogo,
    pois destruir um contêiner destrói os filhos pelo mesmo método."""
    if tk is None or getattr(tk.Entry, "_cofre_limpa", False):
        return
    for classe in (tk.Entry, ttk.Entry):
        original = classe.destroy

        def destruir(self, _orig=original):
            """Apaga o texto do campo e só então o destrói."""
            _apagar_campo_ao_fechar(self)
            _orig(self)
        classe.destroy = destruir
    tk.Entry._cofre_limpa = True


_GERACAO_TEMA_TTK = 0                  # contador: um nome de tema ttk novo a cada aplicar_tema()


def aplicar_tema(root):
    """Aplica cores, fontes e estilos ttk do tema atual a todos os widgets do programa."""
    C = CORES
    st = ttk.Style(root)
    definir_escala(root)
    preparar_fontes(root)
    _instalar_limpeza_de_campos()                # apaga o texto digitado de todo campo que for destruído (senhas, chaves)
    pecas = _pecas()
    P = {}
    T0 = {n: (t.w, t.h) for n, t in pecas.items()}      # tamanho original (mínimo dos elementos ampliados)
    for n, t in pecas.items():
        # botões e campos: o ttk "ladrilha" o miolo da imagem para esticar. Com miolo de 8x8 px, um campo de
        # 400x46 px custava ~300 ladrilhos a cada desenho (≈10 ms por campo = lag ao abrir telas). Com o miolo
        # ampliado (mesmo desenho, mais pixels iguais) são poucos ladrilhos.
        borda_n = next((b for pref, b in FAMILIAS_AMPLIADAS.items() if n.startswith(pref)), None)
        if borda_n is not None:
            P[n] = imagem_ampliada(root, t, _px(borda_n))
        else:
            P[n] = t.imagem(root)
    root._imagens_tema = P                      # mantém as imagens vivas
    # Cada aplicação cria um tema ttk NOVO (nome único). Recriar os elementos (element_create) num tema que já os
    # tem dá "Duplicate element" -- era o que travava o cofre ao trocar as cores (2ª chamada desta função).
    global _GERACAO_TEMA_TTK
    _GERACAO_TEMA_TTK += 1
    nome_tema_ttk = f"meia-noite-{_GERACAO_TEMA_TTK}"
    st.theme_create(nome_tema_ttk, parent="clam")
    st.theme_use(nome_tema_ttk)

    root.tk_setPalette(background=C["fundo"], foreground=C["texto"], activeBackground=C["sup3"],
                       activeForeground=C["texto"], highlightColor=C["prim"], highlightBackground=C["fundo"],
                       selectBackground=C["prim"], selectForeground=C["prim_fg"], insertBackground=C["texto"],
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
    root.option_add("*Menu.activeForeground", C["prim_fg"])
    root.option_add("*Menu.relief", "flat")
    root.option_add("*Menu.borderWidth", 0)
    root.option_add("*Menu.activeBorderWidth", 0)
    root.option_add("*TCombobox*Listbox.background", C["sup2"])
    root.option_add("*TCombobox*Listbox.foreground", C["texto"])
    root.option_add("*TCombobox*Listbox.selectBackground", C["prim"])
    root.option_add("*TCombobox*Listbox.selectForeground", C["prim_fg"])
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
                 selectbackground=C["prim"], selectforeground=C["prim_fg"], insertcolor=C["texto"],
                 insertwidth=1, fieldbackground=C["campo"], borderwidth=0, relief="flat")
    st.map(".", foreground=[("disabled", C["fraco"])])

    def elemento(nome, base, mapa, **kw):
        """Cria um elemento ttk com imagens para cada estado (normal, foco, desabilitado...)."""
        estados = []
        for estado, img in mapa:
            estados.append((estado, P[img]))
        if base in T0 and base.startswith(tuple(FAMILIAS_AMPLIADAS)) and "border" in kw:
            kw.setdefault("width", T0[base][0])      # tamanho mínimo = o da peça original (a imagem ampliada é maior)
            kw.setdefault("height", T0[base][1])
        st.element_create(nome, "image", P[base], *estados, **kw)

    # Botões
    def botao(estilo, elem, base, mapa, padding=(14, 6), fg=C["texto"], fg_map=None, font="CofreTexto"):
        """Define o estilo de um tipo de botão (elemento, margens, cores e fonte)."""
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
    botao("Primario.TButton", "Cofre.primario", "pri", primario, padding=(18, 7), fg=C["prim_fg"],
          fg_map=[("disabled", C["fraco"])], font="CofreForte")
    botao("Accent.TButton", "Cofre.primario2", "pri", primario, padding=(14, 7), fg=C["prim_fg"],
          fg_map=[("disabled", C["fraco"])], font="CofreForte")
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
    # O Tk só trata o clique como "subir/descer" se o nome do elemento termina em uparrow/downarrow
    st.element_create("Cofre.uparrow", "image", P["seta_cima"], width=_px(26), height=_px(14), sticky="")
    st.element_create("Cofre.downarrow", "image", P["seta_baixo"], width=_px(26), height=_px(14), sticky="")
    st.layout("TSpinbox", [("Cofre.campoS", {"sticky": "nsew", "children": [
        ("Cofre.downarrow", {"side": "right", "sticky": "ns"}), ("Cofre.uparrow", {"side": "right", "sticky": "ns"}),
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
    st.element_create("Cofre.cartao", "image", P["cartao"], border=_px(11), padding=6, sticky="nsew",
                      width=T0["cartao"][0], height=T0["cartao"][1])
    st.layout("Card.TFrame", [("Cofre.cartao", {"sticky": "nsew", "children": [("Frame.padding", {"expand": 1})]})])
    st.configure("Card.TFrame", background=C["sup"])
    st.element_create("Cofre.cartao2", "image", P["cartao2"], border=_px(11), padding=6, sticky="nsew",
                      width=T0["cartao2"][0], height=T0["cartao2"][1])
    st.layout("Card2.TFrame", [("Cofre.cartao2", {"sticky": "nsew", "children": [("Frame.padding", {"expand": 1})]})])
    st.configure("Card2.TFrame", background=C["sup2"])
    st.element_create("Cofre.etiqueta", "image", P["etiqueta"], border=_px(6), sticky="nsew",
                      width=T0["etiqueta"][0], height=T0["etiqueta"][1])
    for nome, cor in (("Etiqueta.TLabel", C["texto"]), ("EtiquetaFraca.TLabel", C["fraco"])):
        st.layout(nome, [("Cofre.etiqueta", {"sticky": "nsew", "children": [
            ("Label.padding", {"sticky": "nsew", "children": [("Label.label", {"sticky": "nsew"})]})]})])
        st.configure(nome, background=C["sup2"], foreground=cor, padding=(_px(8), _px(2)), font="CofrePequeno")
    st.element_create("Cofre.moldura", "image", P["cartao"], border=_px(11), padding=10, sticky="nsew",
                      width=T0["cartao"][0], height=T0["cartao"][1])
    st.layout("TLabelframe", [("Cofre.moldura", {"sticky": "nsew", "children": [
        ("Labelframe.padding", {"expand": 1, "sticky": "nsew"})]})])
    st.configure("TLabelframe", background=C["sup"], padding=8)
    st.configure("TLabelframe.Label", background=C["fundo"], foreground=C["suave"], font="CofreForte")
    st.element_create("Cofre.aba", "image", P["aba"], ("selected", P["aba_sel"]), ("active", P["aba_hover"]),
                      border=_px(8), padding=(14, 8), sticky="nsew", width=T0["aba"][0], height=T0["aba"][1])
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
    st.map("Treeview", background=[("selected", C["prim_fundo"])], foreground=[("selected", C["texto"])])
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
    """Pontos de um arco de círculo."""
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def _curva(p0, p1, p2, n=12):
    """Pontos de uma curva de Bézier de 3 pontos."""
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]) for t in (i / n for i in range(n + 1))]


def _desenhar_icone(nome, cor, tam=16, larg=1.45):
    """Desenha um ícone vetorial (por nome, cor e tamanho) numa tela interna suavizada, sem depender de arquivos de imagem."""
    t = _Tela(tam, tam)
    s = tam / 16.0

    def L(*pts, w=larg):
        """Traça uma linha do ícone."""
        t.linha([(x * s, y * s) for x, y in pts], cor, w * max(s, 1) if s > 1 else w)

    def R(x0, y0, x1, y1, r, w=larg):
        """Contorno de retângulo do ícone."""
        t.contorno(x0 * s, y0 * s, x1 * s, y1 * s, r * s, cor, w)

    def F(x0, y0, x1, y1, r):
        """Retângulo preenchido do ícone."""
        t.ret(x0 * s, y0 * s, x1 * s, y1 * s, r * s, cor)

    def A(cx, cy, r, w=larg):
        """Anel do ícone."""
        t.anel(cx * s, cy * s, r * s + w / 2, cor, w)

    def P(cx, cy, r):
        """Ponto (círculo preenchido) do ícone."""
        t.circ(cx * s, cy * s, r * s, cor)

    if nome == "novo":
        L((8, 2.8), (8, 13.2))
        L((2.8, 8), (13.2, 8))
    elif nome == "busca":
        A(7, 7, 4.3)
        L((10.3, 10.3), (13.6, 13.6))
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
        L(*cima)
        L(*baixo)
        A(8, 8, 1.9)
        if nome == "ocultar":
            L((2.6, 2.6), (13.4, 13.4))
    elif nome == "editar":
        L((10.4, 2.6), (13.4, 5.6), (5.6, 13.4), (2.6, 13.4), (2.6, 10.4), (10.4, 2.6))
        L((8.8, 4.2), (11.8, 7.2))
    elif nome == "excluir":
        L((2.4, 4.4), (13.6, 4.4))
        L((6, 4.4), (6.4, 2.6), (9.6, 2.6), (10, 4.4))
        L((3.9, 4.4), (4.8, 13.4), (11.2, 13.4), (12.1, 4.4))
        L((6.6, 7), (6.8, 11))
        L((9.4, 7), (9.2, 11))
    elif nome == "imprimir":
        L((4.6, 5.8), (4.6, 2.6), (11.4, 2.6), (11.4, 5.8))
        R(1.8, 5.8, 14.2, 11.4, 1.8)
        F(4.2, 9.2, 11.8, 10.6, 0)
        R(4.6, 9.4, 11.4, 14, 0.8)
    elif nome == "chave":
        A(5, 11, 2.7)
        L((6.9, 9.1), (13.4, 2.6))
        L((10.6, 5.4), (12.6, 7.4))
        L((12.4, 3.6), (14, 5.2))
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
        L((8, 2), (14.4, 13.4), (1.6, 13.4), (8, 2))
        L((8, 6.2), (8, 9.4))
        P(8, 11.5, 0.95)
    elif nome == "info":
        A(8, 8, 6.2)
        L((8, 7.4), (8, 11.2))
        P(8, 5.1, 0.95)
    elif nome == "grupo":
        L((1.8, 12.6), (1.8, 4.2), (2.6, 3.2), (6, 3.2), (7.6, 4.8), (13.4, 4.8), (14.2, 5.6), (14.2, 12.4),
          (13.4, 13.2), (2.6, 13.2), (1.8, 12.4))
    elif nome == "todos":
        for x0, y0 in ((2.2, 2.2), (8.8, 2.2), (2.2, 8.8), (8.8, 8.8)):
            R(x0, y0, x0 + 5, y0 + 5, 1.4)
    elif nome == "pessoa":
        A(8, 5.4, 2.6)
        L(*_curva((2.8, 14), (3.4, 9.2), (8, 9.2)), *_curva((8, 9.2), (12.6, 9.2), (13.2, 14))[1:])
    elif nome == "teclado":
        R(1.4, 3.8, 14.6, 12.2, 2)
        for x in (4.2, 6.7, 9.3, 11.8):
            P(x, 6.6, 0.75)
        L((5, 9.6), (11, 9.6))
    elif nome == "importar":
        L((8, 2.2), (8, 10))
        L((4.8, 6.9), (8, 10), (11.2, 6.9))
        L((2.4, 10.4), (2.4, 13.6), (13.6, 13.6), (13.6, 10.4))
    elif nome == "exportar":
        L((8, 10), (8, 2.2))
        L((4.8, 5.3), (8, 2.2), (11.2, 5.3))
        L((2.4, 10.4), (2.4, 13.6), (13.6, 13.6), (13.6, 10.4))
    elif nome == "historico":
        A(8, 8, 6)
        L((8, 4.6), (8, 8), (10.6, 9.6))
    elif nome == "backup":
        R(2.4, 2.4, 13.6, 13.6, 2)
        L((5.2, 2.4), (5.2, 5.6), (10.8, 5.6), (10.8, 2.4))
        A(8, 9.8, 1.6)
    elif nome == "fechar":
        L((3.4, 3.4), (12.6, 12.6))
        L((12.6, 3.4), (3.4, 12.6))
    elif nome == "seta":
        L((6, 3.4), (10.6, 8), (6, 12.6))
    elif nome == "seta_baixo":
        L((3.4, 6), (8, 10.6), (12.6, 6))
    elif nome == "tag":
        L((2.2, 2.2), (8.2, 2.2), (14, 8), (8, 14), (2.2, 8.2), (2.2, 2.2))
        P(5.4, 5.4, 1.1)
    elif nome == "config":
        L((2, 4.5), (14, 4.5))
        L((2, 11.5), (14, 11.5))
        F(4.2, 2.6, 7.2, 6.4, 1.4)
        F(8.8, 9.6, 11.8, 13.4, 1.4)
    elif nome == "documento":
        L((9.4, 1.8), (3.4, 1.8), (3.4, 14.2), (12.6, 14.2), (12.6, 5), (9.4, 1.8), (9.4, 5), (12.6, 5))
        L((5.8, 8.4), (10.2, 8.4))
        L((5.8, 11), (10.2, 11))
    elif nome == "atualizar":
        arco = _arco(8, 8, 5.6, -60, 230)
        L(*arco)
        L((12.4, 1.6), (10.8, 3.2), (13.4, 4.6))
    elif nome == "sair":
        L((6.4, 2.4), (2.4, 2.4), (2.4, 13.6), (6.4, 13.6))
        L((6.4, 8), (14, 8))
        L((10.8, 4.8), (14, 8), (10.8, 11.2))
    return t


_CACHE_ICONES = {}


def imagem_icone(master, nome, cor=None, tam=16):
    """Imagem do ícone pelo nome, cor e tamanho (com cache)."""
    cor = cor or CORES["suave"]
    chave = (nome, cor, tam)
    if chave not in _CACHE_ICONES:
        _CACHE_ICONES[chave] = _desenhar_icone(nome, cor, tam).imagem(master)
    return _CACHE_ICONES[chave]


def desenhar_marca(tam=64):
    """Marca Arca: cofre azul-marinho e dourado com fechadura central."""
    t = _Tela(tam, tam)
    s = tam / 64.0
    azul, dourado = "#102748", "#E9AE39"
    t.pintar(lambda x, y: _sd_rrect(x, y, 0.5 * s, 0.5 * s, tam - 0.5 * s,
                                    tam - 0.5 * s, 12 * s), azul)
    t.ret(8 * s, 7 * s, 56 * s, 57 * s, 9 * s, dourado)
    t.ret(11 * s, 10 * s, 53 * s, 54 * s, 7 * s, azul)
    t.ret(14 * s, 13 * s, 50 * s, 51 * s, 5 * s, dourado)
    t.ret(16 * s, 15 * s, 48 * s, 49 * s, 4 * s, azul)
    t.circ(32 * s, 31 * s, 14 * s, dourado)
    t.circ(32 * s, 31 * s, 10.5 * s, azul)
    for angulo in range(0, 360, 45):
        a = math.radians(angulo)
        p1 = (32 * s + math.cos(a) * 7.6 * s, 31 * s + math.sin(a) * 7.6 * s)
        p2 = (32 * s + math.cos(a) * 9.2 * s, 31 * s + math.sin(a) * 9.2 * s)
        t.linha([p1, p2], dourado, 1.2 * s)
    t.circ(32 * s, 30 * s, 3.4 * s, dourado)
    t.ret(30.8 * s, 32 * s, 33.2 * s, 41 * s, 1.2 * s, dourado)
    t.ret(7 * s, 21 * s, 11 * s, 27 * s, 1.5 * s, dourado)
    t.ret(7 * s, 38 * s, 11 * s, 44 * s, 1.5 * s, dourado)
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
        cor = "#{:02x}{:02x}{:02x}".format(*(int(a[j] + (b[j] - a[j]) * k) for j in range(3)))
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


# peças esticadas por ladrilhamento -> borda (px a 100%) usada no elemento ttk correspondente (ver montar_tema)
FAMILIAS_AMPLIADAS = {"btn": 7, "pri": 7, "per": 7, "fan": 7, "campo": 8, "cartao": 11, "etiqueta": 6, "aba": 8}


def imagem_ampliada(master, tela, borda, lado=96):
    """Versão maior de uma peça esticável: cantos e bordas iguais, miolo repetido até 'lado' px (100% de zoom).
    Visualmente idêntica à original; só reduz o número de ladrilhos que o ttk desenha ao esticar."""
    alvo = max(int(round(lado * ESCALA)), 2 * borda + 2)
    return imagem_nove_fatias(master, tela, borda, alvo, alvo)


def peca_cartao(fundo, borda, raio=14):
    """Imagem do cartão arredondado para o tema."""
    t = _Tela(2 * raio + 2, 2 * raio + 2)
    n = 2 * raio + 2
    t.ret(0, 0, n, n, raio, fundo)
    if borda:
        t.contorno(0, 0, n, n, raio, borda, 1.0 / t.s)
    return t, (t.w - 1) // 2


def peca_sombra(raio=14, espalhar=18, forca=0.55):
    """Imagem de uma sombra suave sob os cartões."""
    n = 2 * (raio + espalhar) + 2
    t = _Tela(n, n)
    m = espalhar

    def dist(x, y):
        """Intensidade da sombra em cada ponto."""
        d = _sd_rrect(x, y, m, m + 4, n - m, n - m + 4, raio)
        if d <= 0:
            return -1.0
        f = max(0.0, 1 - d / espalhar)
        return 0.5 - f * f          # cobertura = f² (queda suave)
    t.pintar(dist, "#000000", forca, bruto=True)
    return t, (t.w - 1) // 2


def _grab_seguro(d, limite=2.0):
    """grab_set() depois de a janela aparecer (em PC lento, antes disso dá TclError). Espera no máximo
    'limite' segundos, sem travar se a janela nunca aparecer (ex.: pai minimizado)."""
    try:
        if d.state() == "withdrawn":       # ainda escondida (sendo montada): o grab é feito quando ela aparecer
            d._quer_grab = True
            return
        d.update_idletasks()
        fim = time.monotonic() + limite
        while not d.winfo_viewable() and time.monotonic() < fim:
            d.update()
            time.sleep(0.01)
        d.grab_set()
    except tk.TclError:
        pass


# ---------- caixas de mensagem no tema (substituem as do Windows, que seriam brancas) ----------
# As caixas originais são guardadas assim que o programa carrega (antes de qualquer substituição)
_MB_ORIGINAIS = ({n: getattr(messagebox, n, None) for n in (
    "showinfo", "showwarning", "showerror", "askyesno", "askokcancel", "askyesnocancel", "askquestion",
    "askretrycancel")} if tk is not None else {})


def _caixa_mensagem(tipo, titulo, mensagem, botoes, padrao, cancelar, icone_nome, cor_icone, **kw):
    """Caixa de mensagem própria, no tema do programa, com ícone e botões; devolve o botão escolhido."""
    pai = kw.get("parent") or tk._default_root
    try:
        foco = pai.focus_get()
        if foco is not None:
            pai = foco.winfo_toplevel()
    except (tk.TclError, KeyError, AttributeError):
        pass
    d = tk.Toplevel(pai)
    d.withdraw()
    d.title(titulo or _NOME_APP)
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
    ttk.Label(textos, text=mensagem or "", wraplength=_px(440), justify="left").pack(anchor="w", pady=(6, 0))
    barra = ttk.Frame(corpo)
    barra.pack(fill="x", pady=(20, 0))
    alvo_foco = None
    for rotulo, valor in reversed(botoes):
        estilo = "Primario.TButton" if valor == padrao else "TButton"
        if cor_icone == "perigo" and tipo.startswith("ask") and valor in (True, "yes"):
            estilo = "Perigo.TButton"          # o botão que EXECUTA a ação perigosa fica vermelho
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
    anterior_teste = _primeiro_plano_de_teste()      # so em teste: quem tem o foco agora
    d.deiconify()
    d.update_idletasks()
    _reforcar_segundo_plano_de_teste(d, anterior_teste)   # so em teste: a caixa nao rouba o foco do usuario
    barra_titulo_escura(d)
    proteger_contra_captura(d)
    _grab_seguro(d)
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
                  _n=nome, perigoso=None, **kw):
            """perigoso=True: ação destrutiva, Enter escolhe "Não". perigoso=None: adivinha pelo texto
            (só como rede de segurança); perigoso=False: nunca trata como perigosa."""
            icone_n, cor_n = _i, _cor
            texto = f"{title or ''} {message or ''}".lower()
            padrao_n = _p
            if _n.startswith("ask") and perigoso is True:
                icone_n, cor_n = "alerta", "perigo"
                padrao_n = _c
            elif _n.startswith("ask") and perigoso is None and any(p in texto for p in (
                    "excluir", "apagar", "destru", "remover", "sobrescrever", "perder", "última tentativa",
                    "desativar", "nova chave", "novo código", "substituir", "menos seguro",
                    "fechar agora", "fechar mesmo",
                    "disco do windows")):
                icone_n, cor_n = "alerta", "perigo"
                padrao_n = _c                  # em ações destrutivas o Enter escolhe "Não"
            return _caixa_mensagem(_t + _n, title, message, _b, padrao_n, _c, icone_n, cor_n, **kw)
        caixa._do_tema = True
        setattr(messagebox, nome, caixa)


def _janela_teste_em_segundo_plano(root):
    """Em testes automatizados, revela a janela sem ativá-la nem tirá-la de trás do app do usuário."""
    if not EH_WINDOWS or os.environ.get("COFRE_GUI_TESTS_BACKGROUND") != "1":
        return
    u = ctypes.windll.user32
    u.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
    u.GetAncestor.restype = wintypes.HWND
    hwnd = u.GetAncestor(wintypes.HWND(root.winfo_id()), 2)
    if not hwnd:
        raise ctypes.WinError(ctypes.get_last_error())
    get_style = getattr(u, "GetWindowLongPtrW", u.GetWindowLongW)
    set_style = getattr(u, "SetWindowLongPtrW", u.SetWindowLongW)
    get_style.argtypes = (wintypes.HWND, ctypes.c_int)
    get_style.restype = ctypes.c_ssize_t
    set_style.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
    set_style.restype = ctypes.c_ssize_t
    ctypes.set_last_error(0)
    estilo = get_style(hwnd, -20)
    if not estilo and ctypes.get_last_error():
        raise ctypes.WinError(ctypes.get_last_error())
    ctypes.set_last_error(0)
    anterior = set_style(hwnd, -20, estilo | 0x08000000)  # WS_EX_NOACTIVATE
    if not anterior and ctypes.get_last_error():
        raise ctypes.WinError(ctypes.get_last_error())
    u.SetWindowPos.argtypes = (
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, wintypes.UINT,
    )
    u.SetWindowPos.restype = wintypes.BOOL
    flags = 0x0001 | 0x0002 | 0x0010 | 0x0020  # NOSIZE | NOMOVE | NOACTIVATE | FRAMECHANGED
    if not u.SetWindowPos(hwnd, wintypes.HWND(1), 0, 0, 0, 0, flags):  # HWND_BOTTOM
        raise ctypes.WinError(ctypes.get_last_error())


def _primeiro_plano_de_teste():
    """So em teste (COFRE_GUI_TESTS_BACKGROUND=1): devolve a janela que esta em primeiro plano AGORA, para devolver o
    foco a ela depois de mostrar a janela do cofre. Fora do teste devolve 0 e nada acontece."""
    if not EH_WINDOWS or os.environ.get("COFRE_GUI_TESTS_BACKGROUND") != "1":
        return 0
    try:
        u = ctypes.windll.user32
        u.GetForegroundWindow.restype = wintypes.HWND
        return u.GetForegroundWindow() or 0
    except (OSError, AttributeError):
        return 0


def _reforcar_segundo_plano_de_teste(root, anterior):
    """So em teste: o Tk cria a janela de verdade so quando ela e mostrada e, ao criar, perde o estilo
    WS_EX_NOACTIVATE aplicado antes. Aplica de novo com a janela ja mostrada e devolve o foco a quem o tinha."""
    if not EH_WINDOWS or os.environ.get("COFRE_GUI_TESTS_BACKGROUND") != "1":
        return
    try:
        _janela_teste_em_segundo_plano(root)
        if anterior:
            u = ctypes.windll.user32
            u.SetForegroundWindow.argtypes = (wintypes.HWND,)
            u.SetForegroundWindow.restype = wintypes.BOOL
            u.SetForegroundWindow(anterior)
    except (OSError, AttributeError):
        pass                                  # modo de teste: se nao der, o teste visual do .exe aponta a falha


def revelar_janela(root):
    """Mostra a janela principal só depois de pronta: deixa-a invisível (transparência 0) enquanto o Tk desenha tudo,
    e a revela de uma vez. Assim a tela aparece inteira e estruturada, sem 'se montar' na frente do usuário."""
    _janela_teste_em_segundo_plano(root)
    anterior_teste = _primeiro_plano_de_teste()
    try:
        root.attributes("-alpha", 0.0)
    except tk.TclError:
        pass
    try:
        root.deiconify()
        root.update()
    except tk.TclError:
        pass
    _reforcar_segundo_plano_de_teste(root, anterior_teste)   # so em teste
    try:
        root.attributes("-alpha", 1.0)
    except tk.TclError:
        pass


def sem_piscar(funcao):
    """Decorador das telas grandes: a tela nova é montada FORA da janela (sem aparecer) enquanto a antiga continua
    visível; no fim, uma troca única (apaga a antiga e mostra a nova de uma vez). Nada pisca nem some: antes a
    janela inteira ficava transparente durante a montagem, o que dava um "apagão" a cada troca de tela.
    O 'finally' garante a troca mesmo se a montagem falhar (a janela nunca fica sem tela)."""
    @functools.wraps(funcao)
    def interno(self, *args, **kwargs):
        """Monta a tela nova fora da janela e publica a troca no fim."""
        try:
            return funcao(self, *args, **kwargs)
        finally:
            try:
                self._publicar_tela()
                self.root.update_idletasks()
                self.root.update()
            except tk.TclError:
                pass
    return interno


def chave_ordem_alfabetica(texto):
    """Chave de ordenação alfabética que ignora maiúsculas e acentos (Álamo fica junto de Alamo)."""
    base = unicodedata.normalize("NFD", str(texto or "")).casefold()
    return "".join(c for c in base if not unicodedata.combining(c)).strip()


def tom_para(texto):
    """Cor estável para um texto (o avatar de cada grupo ou pessoa tem sempre a mesma cor)."""
    import hashlib
    return TONS[hashlib.sha256((texto or "?").lower().encode()).digest()[0] % len(TONS)]


_MONOGRAMAS_SERVICOS = {
    "nubank": "NU", "inter": "IN", "itau": "IT", "bradesco": "BR", "santander": "SA", "caixa": "CX",
    "banco do brasil": "BB", "bancodobrasil": "BB", "bb": "BB", "c6 bank": "C6", "c6bank": "C6",
    "c6": "C6", "btg pactual": "BTG", "btgpactual": "BTG", "btg": "BTG", "mercado pago": "MP",
    "mercadopago": "MP", "picpay": "PP",
    "wise": "WI", "paypal": "PY", "xp": "XP", "rico": "RI", "clear": "CL", "binance": "BN",
    "instagram": "IG", "whatsapp": "WA", "tiktok": "TK", "facebook": "FB", "linkedin": "LI",
    "twitter": "X", "x": "X", "pinterest": "PI", "discord": "DC", "telegram": "TG", "reddit": "RD",
    "twitch": "TW", "google drive": "GD", "drive google": "GD", "googledrive": "GD", "drive": "GD",
    "gmail": "GM", "google": "GO",
    "outlook": "MS",
    "microsoft": "MS", "icloud": "AP", "apple": "AP", "yahoo": "YH", "onedrive": "OD", "dropbox": "DB",
    "notion": "NO", "youtube": "YT", "netflix": "NF", "spotify": "SP", "amazon prime video": "PV",
    "amazonprimevideo": "PV", "prime video": "PV", "primevideo": "PV", "disney plus": "DI", "disneyplus": "DI",
    "disney": "DI", "amazon": "AM", "mercado livre": "ML", "mercadolivre": "ML",
    "shopee": "SH", "aliexpress": "AX", "github": "GH", "gitlab": "GL", "chatgpt": "AI", "openai": "AI",
    "figma": "FG", "canva": "CV", "steam": "ST", "playstation": "PS", "xbox": "XB", "riot games": "RG",
    "riotgames": "RG", "riot": "RG", "epic games": "EG", "epicgames": "EG", "epic": "EG",
}
_MONOGRAMAS_CATEGORIAS = {
    "banco": "BC", "bancos": "BC", "financas": "BC", "financeiro": "BC", "pagamentos": "BC",
    "carteira": "BC", "investimentos": "BC", "corretora": "BC", "rede social": "RS", "redes sociais": "RS",
    "mensagens": "RS", "comunicacao": "RS", "email": "EM", "e mail": "EM", "conta": "EM",
    "identidade": "EM", "nuvem": "NV", "produtividade": "NV", "streaming": "ST", "loja": "LO",
    "compras": "LO", "assinaturas": "LO", "trabalho": "TI", "desenvolvimento": "TI", "codigo": "TI",
    "jogos": "JG", "lazer": "JG",
}


def _normalizar_nome_visual(texto):
    """Normaliza nomes e URLs para reconhecer serviços sem diferenciar acentos ou pontuação."""
    sem_acentos = unicodedata.normalize("NFKD", str(texto or ""))
    ascii_nome = sem_acentos.encode("ascii", "ignore").decode("ascii").casefold()
    return re.sub(r"[^a-z0-9]+", " ", ascii_nome).strip()


_PALAVRAS_GRUPO = {
    "Banco": ("nubank itau bradesco bancodobrasil bb caixa santander inter c6 c6bank btg btgpactual safra sicredi "
              "sicoob banrisul neon next willbank pagbank pagseguro picpay mercadopago paypal pix wise revolut "
              "original pan xp rico clear nuinvest genial binance mercadobitcoin bitcoin coinbase bitso metamask "
              "tradingview corretora investimentos cartao visa mastercard elo amex americanexpress hipercard "
              "alelo sodexo ticket vr stone cielo ton sumup infinitepay recargapay crefisa bmg agibank daycoval "
              "creditas seguro seguros porto portoseguro allianz mapfre unimed amil"),
    "Redes sociais": ("instagram insta facebook fb whatsapp zap wpp telegram x twitter tiktok linkedin pinterest "
                      "snapchat reddit discord twitch threads kwai bluesky tumblr signal messenger wechat tinder "
                      "bumble badoo quora medium kick onlyfans patreon behance dribbble"),
    "E-mail": ("gmail google outlook hotmail yahoo icloud apple protonmail email mail onedrive googledrive drive "
               "dropbox mega mediafire nuvem microsoft office365"),
    "Trabalho": ("github gitlab bitbucket slack zoom notion trello asana teams figma canva adobe aws azure "
                 "cloudflare vercel netlify heroku docker npm openai chatgpt claude anthropic gemini perplexity "
                 "wordpress godaddy hostinger hostgator locaweb jira calendly evernote shopify wix"),
    "Streaming": ("netflix primevideo prime disney disneyplus max hbo hbomax globoplay paramount paramountplus "
                  "appletv crunchyroll starplus telecine premiere spotify deezer applemusic youtubemusic tidal "
                  "soundcloud audible dazn espn mubi plutotv tubi vimeo youtube twitchprime kindle"),
    "Jogos": ("steam epic epicgames playstation psn xbox nintendo riot riotgames battlenet ea ubisoft roblox "
              "minecraft garena gog origin blizzard valorant freefire pubg fortnite genshin rockstar bethesda "
              "supercell faceit gamersclub leagueoflegends lol cs2 dota2 betano bet365 blaze"),
    "Compras": ("amazon mercadolivre ml shopee aliexpress magalu americanas casasbahia shein kabum olx temu ifood "
                "magazineluiza rappi ubereats carrefour netshoes centauro renner zara fastshop pontofrio correios loja"),
    "Governo": ("gov govbr inss receita receitafederal detran sus cnh fgts carteira ctps cartorio serasa spc sefaz "
                "prefeitura tribunal cpf cnpj mei esocial bolsafamilia cadunico ipva iptu"),
}
_GRUPO_DA_PALAVRA = {p_: g_ for g_, ps_ in _PALAVRAS_GRUPO.items() for p_ in ps_.split()}


def grupo_recomendado(servico):
    """Tipo de grupo que combina com o nome da conta digitada ('Bradesco' -> 'Banco', 'Instagram' -> 'Redes
    sociais'...), ou None se nao reconhecer. E so uma RECOMENDACAO: nada e escolhido sem o usuario aceitar."""
    nome = _normalizar_nome_visual(servico)
    if len(nome) < 2:
        return None
    junto = nome.replace(" ", "")
    if junto in _GRUPO_DA_PALAVRA:
        return _GRUPO_DA_PALAVRA[junto]
    for t in nome.split():
        if t in _GRUPO_DA_PALAVRA and (len(t) > 1 or t == junto):
            return _GRUPO_DA_PALAVRA[t]
        if t.startswith("banco") or t.startswith("bank") or t.endswith("bank"):
            return "Banco"
    return None


def marca_servico(servico, grupo=""):
    """Retorna um monograma local e discreto, sem buscar ou reproduzir logos oficiais."""
    nome = _normalizar_nome_visual(servico)
    for alias in sorted(_MONOGRAMAS_SERVICOS, key=len, reverse=True):
        if re.search(rf"(?:^| ){re.escape(alias)}(?: |$)", nome):
            return _MONOGRAMAS_SERVICOS[alias]
    categoria = _normalizar_nome_visual(grupo)
    for alias in sorted(_MONOGRAMAS_CATEGORIAS, key=len, reverse=True):
        if re.search(rf"(?:^| ){re.escape(alias)}(?: |$)", categoria):
            return _MONOGRAMAS_CATEGORIAS[alias]
    return ""


# ---------- componentes da tela principal ----------
def _cortar(texto, fonte, largura):
    """Corta o texto com '…' para caber em 'largura' pixels."""
    texto = texto or ""
    if largura <= 0:
        return ""
    if fonte.measure(texto) <= largura:
        return texto
    inicio, fim = 0, len(texto)
    while inicio < fim:
        meio = (inicio + fim + 1) // 2
        if fonte.measure(texto[:meio] + "…") <= largura:
            inicio = meio
        else:
            fim = meio - 1
    return texto[:inicio] + "…"


class BarraLateral(tk.Frame if tk else object):
    """Lista paginada de grupos à esquerda (ícone, nome e contagem), sem rolagem.
    Oferece os mesmos métodos do Treeview que o resto do programa usa."""

    def __init__(self, mestre, max_linhas=8, **kw):
        """Cria a lista compacta de grupos/pessoas com a mesma interface de um Treeview."""
        super().__init__(mestre, bg=CORES["lateral"], **kw)
        self._itens = {}
        self._ordem = []
        self._sel = None
        self._binds = {}
        self._entradas = []
        self._indice = {}
        self._pagina = 0
        self._max_linhas = max(1, int(max_linhas))
        self._assinatura = None
        self._nav = tk.Frame(self, bg=CORES["lateral"])
        self._btn_anterior = ttk.Button(self._nav, text="‹", width=3, command=lambda: self._mudar_pagina(-1))
        self._btn_anterior.pack(side="left")
        self._rotulo_pagina = tk.Label(self._nav, bg=CORES["lateral"], fg=CORES["fraco"],
                                       font="CofrePequeno")
        self._rotulo_pagina.pack(side="left", expand=True)
        self._btn_proxima = ttk.Button(self._nav, text="›", width=3, command=lambda: self._mudar_pagina(1))
        self._btn_proxima.pack(side="right")
        self._nav.pack(side="bottom", fill="x", padx=8, pady=(2, 4))

    # compatibilidade com ttk.Treeview
    def get_children(self, item=""):
        """Ids das linhas, na ordem."""
        return tuple(self._ordem)

    def exists(self, iid):
        """True se a linha existe."""
        return iid in self._indice

    def item(self, iid, option=None):
        """Dados de uma linha (texto, valores, marcas)."""
        ent = self._entradas[self._indice[iid]]
        d = {"text": f"  {ent['texto']}  ({ent.get('n', '')})", "values": "", "tags": ""}
        return d[option] if option else d

    def selection(self):
        """Linha selecionada."""
        return (self._sel,) if self._sel in self._indice else ()

    def selection_set(self, iid):
        """Seleciona uma linha."""
        if iid in self._indice:
            pagina = self._indice[iid] // self._max_linhas
            if pagina != self._pagina:
                self._pagina = pagina
                self._desenhar()
            self._selecionar(iid)

    def delete(self, *iids):
        """Remove linhas."""
        remover = set(iids)
        if remover:
            self.definir([e for e in self._entradas if e["iid"] not in remover],
                         self._sel if self._sel not in remover else None)

    def tag_configure(self, *a, **kw):
        """Sem efeito (existe só para parecer um Treeview)."""
        pass

    def bind(self, seq=None, func=None, add=None):
        """Liga um evento; o de seleção é tratado internamente."""
        if seq == "<<TreeviewSelect>>":
            self._binds.setdefault(seq, []).append(func)
            return
        return super().bind(seq, func, add)

    # montagem
    def definir(self, entradas, selecionado=None):
        """entradas: lista de dicts com iid, texto, n, e 'icone' (nome) ou 'cor' (bolinha);
        'secao' cria um título antes do item; 'cor_txt' muda a cor do texto. Linhas demais são paginadas."""
        assinatura = tuple((e["iid"], e.get("secao"), e["texto"], str(e.get("n", "")), e.get("icone"), e.get("cor"),
                            e.get("cor_txt"), e.get("cor_icone"), e.get("cor_n")) for e in entradas)
        mesma = assinatura == self._assinatura
        antiga, pagina_antiga = self._sel, self._pagina
        self._assinatura = assinatura
        self._entradas = list(entradas)
        self._indice = {e["iid"]: i for i, e in enumerate(self._entradas)}
        self._ordem = [e["iid"] for e in self._entradas]
        nova = selecionado if selecionado in self._indice else (self._ordem[0] if self._ordem else None)
        self._sel = nova
        if nova is not None:
            self._pagina = self._indice[nova] // self._max_linhas
        else:
            self._pagina = min(self._pagina, max(0, (len(self._entradas) - 1) // self._max_linhas))
        if not mesma or pagina_antiga != self._pagina or not self._itens:
            self._desenhar()
            return
        for iid, it in self._itens.items():
            it["ent"] = self._entradas[self._indice[iid]]
        for iid in {antiga, nova}:
            self._pintar(iid)
        self._atualizar_paginacao()

    def _atualizar_paginacao(self):
        """Mostra controles apenas quando há mais de uma página."""
        total = max(1, (len(self._entradas) + self._max_linhas - 1) // self._max_linhas)
        if total <= 1:
            self._nav.pack_forget()
            return
        self._nav.pack(side="bottom", fill="x", padx=8, pady=(2, 4))
        self._rotulo_pagina.config(text=f"{self._pagina + 1}/{total}")
        self._btn_anterior.config(state="normal" if self._pagina > 0 else "disabled")
        self._btn_proxima.config(state="normal" if self._pagina + 1 < total else "disabled")

    def _mudar_pagina(self, passo):
        """Troca a página sem rolagem."""
        total = max(1, (len(self._entradas) + self._max_linhas - 1) // self._max_linhas)
        pagina = max(0, min(total - 1, self._pagina + passo))
        if pagina != self._pagina:
            self._pagina = pagina
            self._desenhar()

    def _desenhar(self):
        """Desenha somente a página atual."""
        for w in self.winfo_children():
            if w is not self._nav:
                w.destroy()
        self._itens.clear()
        C = CORES
        inicio = self._pagina * self._max_linhas
        fim = min(len(self._entradas), inicio + self._max_linhas)
        secao_atual = ""
        for e in self._entradas[:inicio]:
            if e.get("secao"):
                secao_atual = e["secao"]
        if inicio and inicio < fim and not self._entradas[inicio].get("secao") and secao_atual:
            tk.Label(self, text=secao_atual.upper(), bg=C["lateral"], fg=C["fraco"], font="CofreRotulo",
                     anchor="w").pack(fill="x", padx=18, pady=(16, 6))
        for e in self._entradas[inicio:fim]:
            if e.get("secao"):
                secao_atual = e["secao"]
                tk.Label(self, text=e["secao"].upper(), bg=C["lateral"], fg=C["fraco"], font="CofreRotulo",
                         anchor="w").pack(fill="x", padx=18, pady=(8, 3) if ESCALA >= 2.0 else (16, 6))
            altura_linha = 36 if ESCALA >= 2.0 else _px(36)
            linha = tk.Frame(self, bg=C["lateral"], cursor="hand2", height=altura_linha)
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
            if ESCALA >= 2.0:
                linha.configure(height=max(altura_linha, ltxt.winfo_reqheight() + 4, ln.winfo_reqheight() + 4))
            item = {"linha": linha, "barra": barra, "partes": (linha, lic, ltxt, ln), "texto": ltxt,
                    "cor_txt": e.get("cor_txt") or C["lateral_txt"], "icone": lic, "ent": e,
                    "compat": f"  {e['texto']}  ({e.get('n', '')})"}
            self._itens[e["iid"]] = item
            for w in item["partes"]:
                if e.get("acao"):
                    w.bind("<Button-1>", lambda ev, f=e["acao"]: f())
                else:
                    w.bind("<Button-1>", lambda ev, i=e["iid"]: self._selecionar(i))
                if e.get("menu"):
                    w.bind("<Button-3>", lambda ev, f=e["menu"]: f(ev))
                w.bind("<Enter>", lambda ev, i=e["iid"]: self._pintar(i, hover=True))
                w.bind("<Leave>", lambda ev, i=e["iid"]: self._pintar(i))
        self._atualizar_paginacao()
        for iid in self._itens:
            self._pintar(iid)

    def item_em(self, x_root, y_root):
        """Id da linha que está sob o ponto (coordenadas da tela) ou None. Usado ao soltar uma conta arrastada."""
        for iid, it in self._itens.items():
            try:
                lin = it["linha"]
                x0, y0 = lin.winfo_rootx(), lin.winfo_rooty()
                if x0 <= x_root < x0 + lin.winfo_width() and y0 <= y_root < y0 + lin.winfo_height():
                    return iid
            except tk.TclError:
                continue
        return None

    def destacar_alvo(self, iid):
        """Destaca a linha que receberia a conta arrastada (None tira o destaque)."""
        for i in self._ordem:
            self._pintar(i, hover=(i == iid))

    def _pintar(self, iid, hover=False):
        """Redesenha uma linha (normal, passando o mouse ou selecionada)."""
        it = self._itens.get(iid)
        if not it:
            return
        C = CORES
        sel = iid == self._sel
        fundo = C["lateral_sel"] if sel else (C["sup3"] if hover else C["lateral"])
        try:
            for w in it["partes"]:
                w.configure(bg=fundo)
            it["barra"].configure(bg=C["prim"] if sel else fundo)
            it["texto"].configure(fg=C["texto"] if sel else it["cor_txt"],
                                  font="CofreForte" if sel else "CofreTexto")
            e = it["ent"]
            if not e.get("cor"):
                cor = e.get("cor_icone") or (C["prim_txt"] if sel else C["suave"])
                it["icone"].configure(image=imagem_icone(self, e.get("icone", "grupo"), cor, 16))
        except tk.TclError:
            pass

    def _selecionar(self, iid):
        """Seleciona a linha, repinta a anterior e avisa quem escuta."""
        anterior, self._sel = self._sel, iid
        if anterior in self._itens:
            self._pintar(anterior)
        self._pintar(iid)
        for f in self._binds.get("<<TreeviewSelect>>", []):
            f(None)


_PONTOS = {}


def _ponto_img(master, cor, tam=10):
    """Imagem de um ponto colorido (com cache)."""
    if (cor, tam) not in _PONTOS:
        _PONTOS[(cor, tam)] = _Tela(tam, tam).circ(tam / 2, tam / 2, tam / 2 - 0.5, cor).imagem(master)
    return _PONTOS[(cor, tam)]


class ListaContas(tk.Frame if tk else object):
    """Lista paginada de contas com avatar e duas linhas (nome e login), desenhada num Canvas.
    Oferece os métodos do ttk.Treeview usados pelo programa (selection, item, ...)."""
    ALT = 60

    def __init__(self, mestre, **kw):
        """Cria a lista de contas (canvas paginado, seleção e estado vazio)."""
        super().__init__(mestre, bg=CORES["fundo"], **kw)
        C = CORES
        self.ALT = _px(60)
        self._pagina = 0
        self._por_pagina = 1
        self._nav = ttk.Frame(self)
        self._btn_anterior = ttk.Button(self._nav, text="‹ Anterior", style="Acao.TButton",
                                        command=lambda: self._mudar_pagina(-1))
        self._btn_anterior.pack(side="left")
        self._rotulo_pagina = ttk.Label(self._nav, style="Fraco.TLabel")
        self._rotulo_pagina.pack(side="left", expand=True)
        self._btn_proxima = ttk.Button(self._nav, text="Próxima ›", style="Acao.TButton",
                                       command=lambda: self._mudar_pagina(1))
        self._btn_proxima.pack(side="right")
        self._nav.pack(side="bottom", fill="x", padx=12, pady=(4, 8))
        self.canvas = tk.Canvas(self, bg=C["fundo"], highlightthickness=0, bd=0, takefocus=1)
        self.canvas.pack(side="left", fill="both", expand=True)
        self._linhas = []
        self._idx = {}
        self._sel = None
        self._hover = None
        self._larg = 0
        self._vazio = ("", "")
        self._imgs = {}
        self.ao_soltar = None           # função(iid_da_conta, x_root, y_root) chamada ao soltar uma conta arrastada
        self.ao_arrastar = None         # função(x_root, y_root) chamada enquanto arrasta (para destacar o alvo)
        self.ao_menu = None             # função(iid_da_conta, evento) chamada no clique direito
        self._arraste = None
        c = self.canvas
        c.bind("<Configure>", self._ao_redimensionar)
        c.bind("<Button-1>", self._clique)
        c.bind("<B1-Motion>", self._arrastando)
        c.bind("<ButtonRelease-1>", self._soltou)
        c.bind("<Button-3>", self._clique_direito)
        c.bind("<Motion>", self._mover)
        c.bind("<Leave>", lambda e: self._pos_hover(None))
        c.bind("<Up>", lambda e: self._andar(-1))
        c.bind("<Down>", lambda e: self._andar(1))
        c.bind("<Home>", lambda e: self._andar(-10 ** 6))
        c.bind("<End>", lambda e: self._andar(10 ** 6))

    def _ao_redimensionar(self, evento):
        """Ajusta o número de contas por página ao espaço realmente disponível."""
        try:
            por_pagina = max(1, (evento.height - _px(16)) // self.ALT)
            mudou_pagina = por_pagina != self._por_pagina
            mudou_largura = evento.width != self._larg
            if mudou_pagina:
                self._por_pagina = por_pagina
                self._pagina = min(self._pagina, self._ultima_pagina())
                self._atualizar_paginacao()
            if mudou_pagina or mudou_largura:
                self._desenhar()
        except (tk.TclError, AttributeError):
            pass

    def _ultima_pagina(self):
        return max(0, (len(self._linhas) - 1) // max(1, self._por_pagina))

    def _atualizar_paginacao(self):
        """Atualiza a navegação por páginas, sem barra ou rolagem."""
        total = max(1, self._ultima_pagina() + 1)
        if total <= 1:
            self._nav.pack_forget()
            return
        self._nav.pack(side="bottom", fill="x", padx=12, pady=(4, 8))
        self._rotulo_pagina.config(text=f"{self._pagina + 1} de {total}  ·  {len(self._linhas)} contas")
        self._btn_anterior.config(state="normal" if self._pagina > 0 else "disabled")
        self._btn_proxima.config(state="normal" if self._pagina < total - 1 else "disabled")

    def _mudar_pagina(self, passo):
        """Vai à página anterior ou seguinte."""
        pagina = max(0, min(self._ultima_pagina(), self._pagina + passo))
        if pagina != self._pagina:
            self._pagina = pagina
            self._desenhar()

    # compatibilidade com ttk.Treeview
    def bind(self, seq=None, func=None, add=None):
        """Liga um evento ao canvas da lista."""
        return self.canvas.bind(seq, func, add)

    def focus_set(self):
        """Dá o foco do teclado à lista."""
        self.canvas.focus_set()

    def get_children(self, item=""):
        """Ids dos itens mostrados, na ordem."""
        return tuple(r["iid"] for r in self._linhas)

    def exists(self, iid):
        """True se o item está na lista."""
        return iid in self._idx

    def item(self, iid, option=None):
        """Dados de uma linha (texto, valores, marcas)."""
        r = self._linhas[self._idx[iid]]
        d = {"values": [r["titulo"], r["login"], r["contem"]], "text": r["titulo"], "tags": ""}
        return d[option] if option else d

    def selection(self):
        """Item selecionado."""
        return (self._sel,) if self._sel in self._idx else ()

    def selection_set(self, iid):
        """Seleciona um item e mostra a página que o contém."""
        if iid in self._idx:
            self._sel = iid
            self._pos_selecao()
            self.see(iid)
            self.canvas.event_generate("<<TreeviewSelect>>", when="tail")

    def see(self, iid):
        """Vai à página que contém o item."""
        if iid not in self._idx:
            return
        pagina = self._idx[iid] // max(1, self._por_pagina)
        if pagina != self._pagina:
            self._pagina = pagina
            self._desenhar()

    def delete(self, *iids):
        """Esvazia a lista."""
        self.definir([], self._vazio)

    def tag_configure(self, *a, **kw):
        """Sem efeito (existe só para parecer um Treeview)."""
        pass

    # dados e desenho
    def definir(self, linhas, vazio=("", "")):
        """linhas: dicts com iid, titulo, login, sub, contem, cor, alerta (0/1/2)."""
        assinatura = (tuple(tuple(sorted((k, str(v)) for k, v in r.items())) for r in linhas), tuple(vazio))
        igual = assinatura == getattr(self, "_assinatura", None)
        selecao_anterior = self._sel
        self._assinatura = assinatura
        self._linhas = linhas
        self._idx = {r["iid"]: i for i, r in enumerate(linhas)}
        self._vazio = vazio
        if self._sel is not None and self._sel not in self._idx:
            self._sel = None
            igual = False
        if self._sel in self._idx:
            self._pagina = self._idx[self._sel] // max(1, self._por_pagina)
        else:
            self._pagina = min(self._pagina, self._ultima_pagina())
        self._atualizar_paginacao()
        if not igual:                      # lista idêntica: não apaga e redesenha tudo (evita piscar)
            self._desenhar()
        elif selecao_anterior != self._sel:
            self._pos_selecao()

    def _img(self, chave, fabrica):
        """Imagem com cache para o desenho das linhas."""
        if chave not in self._imgs:
            self._imgs[chave] = fabrica()
        return self._imgs[chave]

    def _desenhar(self):
        """Desenha a lista de contas no canvas (grupos, linhas, seleção e o aviso de lista vazia)."""
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
        q = _px
        larg_hl = w - q(16)
        self._hl_sel = self._img(("sel", larg_hl), lambda: imagem_nove_fatias(
            c, *peca_cartao(C["prim_fundo"], C["borda2"], 10), larg_hl, self.ALT - q(6)))
        self._hl_hover = self._img(("hov", larg_hl), lambda: imagem_nove_fatias(
            c, *peca_cartao(C["sup"], None, 10), larg_hl, self.ALT - q(6)))
        c.create_image(-999, -999, image=self._hl_hover, anchor="nw", tags="hover")
        c.create_image(-999, -999, image=self._hl_sel, anchor="nw", tags="sel")
        self._feitas = set()
        visiveis = min(self._por_pagina, len(self._linhas) - self._pagina * self._por_pagina)
        c.configure(scrollregion=(0, 0, w, max(c.winfo_height(), q(16) + visiveis * self.ALT)))
        self._garantir_visiveis()
        self._pos_selecao()
        self._pos_hover(self._hover)

    def _garantir_visiveis(self):
        """Desenha apenas as contas da página atual."""
        c = self.canvas
        if not self._linhas or not hasattr(self, "_feitas"):
            return
        q = _px
        C = CORES
        F, P = FONTES["CofreForte"], FONTES["CofrePequeno"]
        w = self._larg or max(c.winfo_width(), 200)
        inicio = self._pagina * self._por_pagina
        fim = min(len(self._linhas), inicio + self._por_pagina)
        novas = False
        for i in range(inicio, fim):
            if i in self._feitas:
                continue
            self._feitas.add(i)
            novas = True
            r = self._linhas[i]
            y = q(8) + (i - inicio) * self.ALT
            meio = y + self.ALT / 2
            servico = r.get("titulo", "")
            av = self._img(("marca", normalizar_marca(servico), q(38)),
                           lambda servico=servico: icone_marca(servico, q(38), master=c))
            c.create_image(q(36), meio, image=av)
            direita = w - q(18)
            icones = []
            if r.get("alerta"):
                icones.append(("alerta", C["perigo"] if r["alerta"] >= 2 else C["alerta"]))
            for nome, cor in icones:
                c.create_image(direita - q(8), meio, image=imagem_icone(c, nome, cor, 16))
                direita -= q(24)
            larg_txt = direita - q(66) - q(8)
            c.create_text(q(66), meio - q(10), text=_cortar(r["titulo"], F, larg_txt), anchor="w", fill=C["texto"],
                          font="CofreForte", tags=("txt",))
            c.create_text(q(66), meio + q(11), text=_cortar(r["sub"], P, larg_txt), anchor="w", fill=C["suave"],
                          font="CofrePequeno")
        if novas:
            c.tag_lower("hover")
            c.tag_lower("sel")

    def _pos_selecao(self):
        """Posiciona o retângulo de seleção."""
        c = self.canvas
        inicio = self._pagina * self._por_pagina
        if self._sel in self._idx and inicio <= self._idx[self._sel] < inicio + self._por_pagina:
            local = self._idx[self._sel] - inicio
            c.coords("sel", _px(8), _px(8) + local * self.ALT + _px(3))
        else:
            c.coords("sel", -9999, -9999)

    def _pos_hover(self, i):
        """Posiciona o destaque da linha sob o mouse."""
        self._hover = i
        c = self.canvas
        inicio = self._pagina * self._por_pagina
        if i is not None and inicio <= i < min(len(self._linhas), inicio + self._por_pagina) and \
                self._linhas[i]["iid"] != self._sel:
            local = i - inicio
            c.coords("hover", _px(8), _px(8) + local * self.ALT + _px(3))
        else:
            c.coords("hover", -9999, -9999)

    def _linha_em(self, y):
        """Índice da linha na altura y do canvas."""
        i = self._pagina * self._por_pagina + int((y - _px(8)) // self.ALT)
        return i if 0 <= i < len(self._linhas) else None

    def _mover(self, e):
        """Acompanha o mouse para destacar a linha."""
        i = self._linha_em(e.y)
        if i != self._hover:
            self._pos_hover(i)

    def _clique(self, e):
        """Seleciona a linha clicada (e guarda onde começou, para detectar o arrastar)."""
        self.canvas.focus_set()
        self._x0, self._y0 = e.x, e.y
        i = self._linha_em(e.y)
        if i is not None:
            self.selection_set(self._linhas[i]["iid"])
            self._pos_hover(None)

    def _clique_direito(self, e):
        """Clique direito numa conta: seleciona e abre o menu de ações dela (mover para uma pessoa, etc.)."""
        self.canvas.focus_set()
        i = self._linha_em(e.y)
        if i is None:
            return
        iid = self._linhas[i]["iid"]
        self.selection_set(iid)
        if self.ao_menu:
            self.ao_menu(iid, e)

    def _arrastando(self, e):
        """Arrastar uma conta: mostra uma etiqueta flutuante com o nome e destaca o destino sob o mouse."""
        if self._arraste is None:
            if self._sel not in self._idx or abs(e.x - getattr(self, "_x0", e.x)) + abs(e.y - getattr(self, "_y0", e.y)) < 8:
                return
            i = self._idx[self._sel]
            try:
                j = tk.Toplevel(self)
                j.overrideredirect(True)
                j.attributes("-topmost", True)
                tk.Label(j, text="  " + self._linhas[i]["titulo"][:40] + "  ", bg=CORES["prim_fundo"],
                         fg=CORES["texto"],
                         font="CofreForte", padx=10, pady=6).pack()
            except tk.TclError:
                return
            self._arraste = {"iid": self._sel, "janela": j}
            self.canvas.configure(cursor="hand2")
        try:
            self._arraste["janela"].geometry(f"+{e.x_root + 14}+{e.y_root + 10}")
        except tk.TclError:
            pass
        if self.ao_arrastar:
            self.ao_arrastar(e.x_root, e.y_root)

    def _soltou(self, e):
        """Soltar a conta arrastada: avisa o programa para onde ela foi solta."""
        arr, self._arraste = self._arraste, None
        if arr is None:
            return
        try:
            arr["janela"].destroy()
            self.canvas.configure(cursor="")
        except tk.TclError:
            pass
        if self.ao_arrastar:
            self.ao_arrastar(None, None)
        if self.ao_soltar:
            self.ao_soltar(arr["iid"], e.x_root, e.y_root)

    def _andar(self, passo):
        """Move a seleção pelo teclado (setas, Page Up/Down)."""
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
        """Cria o painel que mostra a avaliação de força de uma senha."""
        super().__init__(mestre, style=pref + "TFrame")
        self.app, self.vazio, self.largura, self.pref = app, vazio, largura, pref
        self.compacto = compacto
        self._texto = ""
        self.mostrar("")

    def cget(self, chave):
        """Devolve o texto puro do relatório (usado pelos testes) ou a opção pedida."""
        if chave == "text":                 # texto puro do relatório (usado por testes e leitores de tela)
            return self._texto
        return super().cget(chave)

    # ---- montagem ----
    def _limpar(self):
        """Remove o conteúdo anterior do painel."""
        for w in self.winfo_children():
            w.destroy()

    def _cartao(self):
        """Dá ao painel a aparência de cartão."""
        self.configure(style="Card2.TFrame", padding=(_px(14), _px(11), _px(14), _px(12)))

    def _sumir(self):
        """Esconde o painel (sem senha para avaliar)."""
        self.configure(style=self.pref + "TFrame", padding=0)

    def _larg(self):
        """Largura disponível para o texto."""
        try:
            w = self.winfo_width()
        except tk.TclError:
            w = 0
        return w if w > _px(120) else self.largura

    def _linha(self, pai, icone_nome, cor, texto, estilo="S2.Suave.TLabel"):
        """Uma linha com ícone e texto."""
        lin = ttk.Frame(pai, style="S2.TFrame")
        lin.pack(fill="x", pady=(_px(3), 0))
        ttk.Label(lin, image=imagem_icone(self, icone_nome, cor, 14), style="S2.TLabel").pack(
            side="left", anchor="n", pady=(_px(2), 0), padx=(0, _px(8)))
        ttk.Label(lin, text=texto, style=estilo, wraplength=self._larg() - _px(64), justify="left").pack(
            side="left", fill="x")
        return lin

    def _secao(self, texto):
        """Título de seção do painel."""
        ttk.Label(self, text=texto.upper(), style="S2.Campo.TLabel").pack(anchor="w", pady=(_px(12), _px(2)))

    def _cabecalho(self, nota, rot, direita, titulo=""):
        """Cabeçalho com a nota (muito fraca a excelente)."""
        cor = self.app._CORES_FORCA[nota]
        topo = ttk.Frame(self, style="S2.TFrame")
        topo.pack(fill="x")
        if titulo:
            ttk.Label(topo, text=titulo, style="S2.Fraco.TLabel").pack(side="left", padx=(0, _px(10)))
        ttk.Label(topo, text="  " + rot, image=self.app._barra_forca(nota), compound="left", style="S2.TLabel",
                  foreground=cor, font="CofreForte").pack(side="left")
        ttk.Label(topo, text=direita, style="S2.Fraco.TLabel").pack(side="right")

    def _etiquetas(self, senha):
        """Etiquetas com a composição da senha (maiúsculas, dígitos, símbolos...)."""
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
        """Tempo estimado para quebrar a senha em cada cenário de ataque."""
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
        """Guarda a janela e os itens (rótulo, ícone, função) do menu."""
        self.app = app
        self.itens = itens          # (rótulo, ícone, função) ou None para separador

    def abrir(self, widget, pos=None):
        """Abre o menu suspenso junto ao widget indicado."""
        C = CORES
        raiz = widget.winfo_toplevel()
        m = tk.Toplevel(raiz)
        m.wm_overrideredirect(True)
        m.configure(bg=C["borda2"])
        caixa = tk.Frame(m, bg=C["sup2"], padx=6, pady=6)
        caixa.pack(padx=1, pady=1)

        def fechar(e=None):
            """Fecha o menu."""
            try:
                m.grab_release()
                m.destroy()
            except tk.TclError:
                pass

        for it in self.itens:
            if it is None:
                tk.Frame(caixa, bg=C["borda2"], height=1).pack(fill="x", padx=6, pady=5)
                continue
            if isinstance(it, str):
                # Cabeçalho de seção (não clicável): separa itens de uso geral dos de segurança no menu "…"
                # (pedido do usuário 2026-11-13: antes vinham todos misturados numa lista só).
                tk.Label(caixa, text=it.upper(), bg=C["sup2"], fg=C["fraco"], font="CofrePequeno",
                         anchor="w", padx=4).pack(fill="x", pady=(8, 2))
                continue
            rot, ic, func = it
            linha = tk.Frame(caixa, bg=C["sup2"], cursor="hand2")
            linha.pack(fill="x")
            li = tk.Label(linha, image=imagem_icone(m, ic, C["suave"], 16), bg=C["sup2"], width=28)
            li.pack(side="left", padx=(4, 4), pady=6)
            lt = tk.Label(linha, text=rot, bg=C["sup2"], fg=C["texto"], font="CofreTexto", anchor="w", padx=4)
            lt.pack(side="left", fill="x", expand=True, padx=(0, 18))

            def pintar(cor, partes=(linha, li, lt)):
                """Pinta o item sob o mouse."""
                for p in partes:
                    p.configure(bg=cor)

            def executar(e=None, f=func):
                """Fecha o menu e executa a função do item."""
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
            """Fecha o menu se o clique foi fora dele."""
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


class TourGuiado:
    """Passeio guiado por seção: escurece a janela, desenha um retângulo AMARELO em volta da área explicada e mostra
    um cartão com o que ela faz e como usar. O usuário clica em 'Próximo' para ir à área seguinte.
    passos: lista de (função que devolve o widget a destacar ou None, título, texto); None = cartão central."""
    COR_DESTAQUE = "#facc15"
    MARGEM = 6

    def __init__(self, app, base, passos, ao_fechar=None):
        """Guarda os passos e a janela-base (a janela principal ou o diálogo que está sendo explicado)."""
        self.app, self.base, self.passos, self.ao_fechar = app, base, list(passos), ao_fechar
        self.i = -1
        self.pecas = []          # janelas de escurecimento e de borda
        self.cartao = None
        self.ativo = False

    # ---------- ciclo de vida ----------
    def iniciar(self):
        """Começa o passeio no primeiro passo."""
        self.ativo = True
        self.app._tour = self
        try:
            self.base.bind("<Configure>", self._reposicionar, add="+")
            self.base.bind("<FocusIn>", self._reposicionar, add="+")
            self.base.bind("<Map>", self._reposicionar, add="+")
        except tk.TclError:
            pass
        self._ir(0)

    def encerrar(self):
        """Fecha o passeio e remove todas as janelas auxiliares."""
        if not self.ativo:
            return
        self.ativo = False
        self._limpar()
        if self.cartao is not None:
            try:
                self.cartao.destroy()
            except tk.TclError:
                pass
            self.cartao = None
        if getattr(self.app, "_tour", None) is self:
            self.app._tour = None
        if self.ao_fechar:
            self.ao_fechar()

    def _limpar(self):
        """Remove as peças de escurecimento/borda do passo atual."""
        for w in self.pecas:
            try:
                w.destroy()
            except tk.TclError:
                pass
        self.pecas = []

    # ---------- navegação ----------
    def _ir(self, i, sentido=1):
        """Vai para o passo i (pulando os que não têm área visível agora); passou do fim = encerra."""
        while 0 <= i < len(self.passos):
            alvo_fn = self.passos[i][0]
            try:
                alvo = alvo_fn() if alvo_fn else None
            except Exception:
                alvo = None
            if alvo_fn is None or (alvo is not None and self._visivel(alvo)):
                self.i = i
                self._mostrar(alvo)
                return
            i += sentido
        if i >= len(self.passos):
            self.encerrar()
        elif i < 0:
            self._ir(0)

    @staticmethod
    def _visivel(w):
        """True se o widget existe, está na tela e tem tamanho."""
        try:
            return bool(w.winfo_exists() and w.winfo_ismapped() and w.winfo_width() > 4 and w.winfo_height() > 4)
        except tk.TclError:
            return False

    def _retangulo(self, w):
        """(x, y, largura, altura) do widget em coordenadas da tela."""
        return w.winfo_rootx(), w.winfo_rooty(), w.winfo_width(), w.winfo_height()

    def _peca(self, x, y, w, h, cor, alpha=None):
        """Cria uma janelinha sem borda (retângulo colorido, opcionalmente translúcido) numa posição da tela."""
        j = tk.Toplevel(self.base)
        j.overrideredirect(True)
        j.configure(bg=cor)
        try:
            j.attributes("-topmost", True)
            if alpha is not None:
                j.attributes("-alpha", alpha)
        except tk.TclError:
            pass
        j.geometry(f"{max(1, int(w))}x{max(1, int(h))}+{int(x)}+{int(y)}")
        j.bind("<Button-1>", lambda e: "break")
        self.pecas.append(j)
        return j

    def _mostrar(self, alvo):
        """Desenha o escurecimento + retângulo amarelo para o passo atual e abre o cartão de texto."""
        self._limpar()
        base = self.base
        base.update_idletasks()
        bx, by, bw, bh = base.winfo_rootx(), base.winfo_rooty(), base.winfo_width(), base.winfo_height()
        escuro = 0.62
        if alvo is None:
            self._peca(bx, by, bw, bh, "#000000", escuro)
            rect = None
        else:
            m = self.MARGEM
            x, y, w, h = self._retangulo(alvo)
            x0, y0 = max(bx, x - m), max(by, y - m)
            x1, y1 = min(bx + bw, x + w + m), min(by + bh, y + h + m)
            rect = (x0, y0, x1 - x0, y1 - y0)
            self._peca(bx, by, bw, y0 - by, "#000000", escuro)                       # acima
            self._peca(bx, y1, bw, by + bh - y1, "#000000", escuro)                  # abaixo
            self._peca(bx, y0, x0 - bx, y1 - y0, "#000000", escuro)                  # à esquerda
            self._peca(x1, y0, bx + bw - x1, y1 - y0, "#000000", escuro)             # à direita
            if EH_WINDOWS:                                    # área explicada: quase invisível, mas não deixa clicar
                self._peca(x0, y0, x1 - x0, y1 - y0, "#000000", 0.01)
            e = 3
            cor = self.COR_DESTAQUE
            self._peca(x0 - e, y0 - e, x1 - x0 + 2 * e, e, cor)                       # borda amarela (4 lados)
            self._peca(x0 - e, y1, x1 - x0 + 2 * e, e, cor)
            self._peca(x0 - e, y0, e, y1 - y0, cor)
            self._peca(x1, y0, e, y1 - y0, cor)
        self._abrir_cartao(rect, (bx, by, bw, bh))

    def _abrir_cartao(self, rect, base):
        """Monta o cartão com título, texto e os botões Anterior / Próximo / Pular, perto da área destacada."""
        C = CORES
        if self.cartao is not None:
            try:
                self.cartao.destroy()
            except tk.TclError:
                pass
        _, titulo, texto = self.passos[self.i]
        c = tk.Toplevel(self.base)
        c.overrideredirect(True)
        c.configure(bg=self.COR_DESTAQUE)
        try:
            c.attributes("-topmost", True)
        except tk.TclError:
            pass
        corpo = tk.Frame(c, bg=C["sup"], padx=18, pady=14)
        corpo.pack(padx=2, pady=2)
        topo = tk.Frame(corpo, bg=C["sup"], cursor="fleur")
        topo.pack(fill="x")
        tk.Label(topo, text="⠿  " + titulo, bg=C["sup"], fg=C["texto"], font="CofreSub", anchor="w",
                 cursor="fleur").pack(side="left")
        tk.Label(topo, text=f"{self.i + 1} de {len(self.passos)}", bg=C["sup"], fg=C["fraco"], font="CofrePequeno").pack(
            side="right")
        # Arrastar pelo título: o cartão às vezes cobria o que o usuário queria olhar e não dava para tirá-lo
        # do caminho (pedido do usuário 2026-11-13). Só o CARTÃO se move; o retângulo amarelo de destaque
        # continua marcando a área de verdade. Vale só para este passo: o próximo redesenha na posição padrão.
        for w in (topo,) + tuple(topo.winfo_children()):
            w.bind("<ButtonPress-1>", self._iniciar_arraste)
            w.bind("<B1-Motion>", self._arrastar)
        tk.Label(corpo, text=texto, bg=C["sup"], fg=C["texto"], font="CofreTexto", justify="left", anchor="w",
                 wraplength=_px(340)).pack(fill="x", pady=(8, 12))
        bt = tk.Frame(corpo, bg=C["sup"])
        bt.pack(fill="x")
        ultimo = self.i == len(self.passos) - 1
        ttk.Button(bt, text="Concluir" if ultimo else "Próximo  ▶", style="Primario.TButton",
                   command=lambda: self._ir(self.i + 1)).pack(side="right")
        if self.i > 0:
            ttk.Button(bt, text="◀ Anterior", command=lambda: self._ir(self.i - 1, -1)).pack(side="right", padx=8)
        if not ultimo:
            ttk.Button(bt, text="Pular passeio", style="Fantasma.TButton", command=self.encerrar).pack(side="left")
        c.bind("<Return>", lambda e: self._ir(self.i + 1))
        c.bind("<Right>", lambda e: self._ir(self.i + 1))
        c.bind("<Left>", lambda e: self._ir(self.i - 1, -1))
        c.bind("<Escape>", lambda e: self.encerrar())
        c.update_idletasks()
        cw, ch = c.winfo_reqwidth(), c.winfo_reqheight()
        bx, by, bw, bh = base
        if rect is None:
            x, y = bx + (bw - cw) // 2, by + (bh - ch) // 2
        else:
            rx, ry, rw, rh = rect
            gap = _px(14)
            opcoes = ((rx + rw + gap, ry), (rx - cw - gap, ry), (rx, ry + rh + gap), (rx, ry - ch - gap))
            x, y = next(((ox, oy) for ox, oy in opcoes
                         if ox >= bx and oy >= by and ox + cw <= bx + bw and oy + ch <= by + bh), None) or \
                (bx + (bw - cw) // 2, by + bh - ch - gap)
            y = max(by + 4, min(y, by + bh - ch - 4))
        c.geometry(f"+{int(x)}+{int(y)}")
        c.lift()
        try:
            c.focus_force()
        except tk.TclError:
            pass
        self.cartao = c
        self._arraste = None

    def _iniciar_arraste(self, event):
        """Começa a arrastar o cartão pelo título (guarda onde o dedo/mouse pegou o cartão)."""
        if self.cartao is None:
            return
        self._arraste = (event.x_root - self.cartao.winfo_x(), event.y_root - self.cartao.winfo_y())

    def _arrastar(self, event):
        """Move o cartão junto com o mouse enquanto o botão está pressionado."""
        if self.cartao is None or not self._arraste:
            return
        dx, dy = self._arraste
        try:
            self.cartao.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")
        except tk.TclError:
            pass

    def _reposicionar(self, event=None):
        """Se a janela mudar de tamanho/lugar, ou voltar ao primeiro plano, durante o passeio, redesenha o passo
        atual. Também escuta <FocusIn>/<Map> da janela base (não só <Configure>): sem isso, se a janela
        principal fosse reativada por baixo das peças do passeio (achado real 2026-11-13: usuário viu a tela
        principal "abaixar" e o passeio continuar como se nada tivesse mudado), o escurecimento e o retângulo
        amarelo podiam ficar na posição antiga ou atrás da janela, em vez de realinhar com ela."""
        if not self.ativo or (event is not None and event.widget is not self.base):
            return
        if getattr(self, "_agendado", None):
            return

        def refazer():
            """Redesenha o passo atual (só uma vez por rajada de eventos)."""
            self._agendado = None
            if self.ativo:
                self._ir(self.i)
        try:
            self._agendado = self.base.after(120, refazer)
        except tk.TclError:
            pass


class App:
    """Janela principal: telas de criar/desbloquear/principal, bloqueio automático, área de transferência protegida e os diálogos (itens, pessoas, importação, FIDO, histórico)."""
    INATIVIDADE_MS = 3 * 60 * 1000       # padrão: bloqueia após 3 min sem uso (o usuário pode mudar: 1 a 30 min)
    INATIVIDADE_OPCOES = (1, 2, 3, 5, 10, 15, 30)
    LIMPAR_CLIPBOARD_MS = 15 * 1000      # limpa a área de transferência após 15 s

    # ---------- Inicialização da janela e esqueleto da tela ----------

    def __init__(self, root, caminho, em_uso=False):
        """Cria a janela, o estado do cofre e os temporizadores de vigilância e bloqueio.
        em_uso=True: outra janela/processo já tem este cofre aberto; esta abre só em MODO CONSULTA (sem gravar)."""
        self.root = root
        self.caminho = caminho
        self.em_uso = em_uso
        diag_definir(caminho)                  # onde guardar o registro de diagnóstico (cifrado) deste cofre
        self.cofre = None
        self._restauracoes_tentadas = None
        self.frame = None
        self._timer_bloqueio = None
        self._timer_clip = None
        self._clip_valor = None
        self.tema = _carregar_preferencia_tema()
        _definir_tema(self.tema)
        root.title(_NOME_PRODUTO)
        aplicar_tema(root)
        instalar_caixas_de_mensagem()
        try:
            self._icone_janela = [desenhar_marca(n).imagem(root) for n in (64, 32, 16)]
            root.iconphoto(True, *self._icone_janela)
        except tk.TclError:
            pass
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        area_x, area_y, area_larg, area_alt = 0, 0, sw, sh
        if EH_WINDOWS:
            class RECT(ctypes.Structure):
                _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                            ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

            try:
                area = RECT()
                if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(area), 0):
                    area_x, area_y = area.left, area.top
                    area_larg, area_alt = area.right - area.left, area.bottom - area.top
            except (AttributeError, OSError, ctypes.ArgumentError, TypeError):
                pass
        larg = min(_px(1500), max(_px(640), area_larg - _px(64)))
        alt = min(_px(960), max(1, area_alt - _px(132)))
        x = area_x + max(0, (area_larg - larg - _px(16)) // 2)
        y = area_y + max(0, (area_alt - alt - _px(48)) // 2)
        root.geometry(f"{larg}x{alt}+{x}+{y}")
        root.minsize(min(_px(1040), larg), min(_px(660), alt))
        for ev in ("<KeyPress>", "<Button>", "<MouseWheel>"):
            root.bind_all(ev, self._atividade, add="+")
        root.bind("<Unmap>", self._ao_minimizar, add="+")
        self._ultimo_tique = time.time()
        self._tique_proc = 0
        self._sem_foco_desde = None       # desde quando outro programa está em primeiro plano
        self._ocultadores = []
        self._liberado_em = {}
        self._erros_sessao = 0
        self._timer_ocultar = None
        root.bind_all("<FocusOut>", lambda e: self._agendar_ocultar(), add="+")
        root.bind_all("<FocusIn>", lambda e: self._mostrar_conteudo(), add="+")
        self._salvando = False
        Cofre.executor_salvar = self._executar_salvamento
        self._espias_res = None
        self._espias_erro = None
        self._espias_thread = None
        self._espias_pedido = threading.Event()
        self._espias_parar = threading.Event()
        root.after(2000, self._vigiar_sistema)
        self._hook_energia = hook_energia(root, self._ao_perigo)
        root.protocol("WM_DELETE_WINDOW", self.sair)
        root.update()
        self.protegido = proteger_contra_captura(root)
        barra_titulo_escura(root)
        root.bind("<Map>", lambda e=None: proteger_contra_captura(root) if e is None or e.widget is root else None,
                  add="+")
        self.mostrar_inicio()

    # ---------- utilidades ----------
    def _publicar_tela(self):
        """Faz a troca de tela: apaga a antiga e mostra a nova de uma vez, sem quadro intermediário vazio."""
        pendente = getattr(self, "_tela_pendente", None)
        if not pendente:
            return
        self._tela_pendente = None
        novo, antigo = pendente
        try:
            if antigo is not None and antigo is not novo:
                antigo.destroy()
            if novo.winfo_exists():
                novo.pack(fill="both", expand=True)
        except tk.TclError:
            pass

    def _limpar_tela(self, modo="cheio"):
        """'cheio' = tela inteira; 'centro'/'topo' = cartão centralizado sobre fundo com halo suave."""
        if getattr(self, "_tour", None) is not None:
            self._tour.encerrar()
        rodape_criar = getattr(self, "_rodape_criar", None)
        if rodape_criar is not None:
            rodape_criar.destroy()
            self._rodape_criar = None
        self._publicar_tela()                              # se havia uma troca pendente, conclui antes
        self._mostrar_conteudo()
        for nome in ("_timer_busca", "_timer_aviso"):      # atrasos da tela antiga não podem mexer na nova
            t_ = getattr(self, nome, None)
            if t_:
                try:
                    self.root.after_cancel(t_)
                except (tk.TclError, ValueError):
                    pass
                setattr(self, nome, None)
        antigo = self.frame                                # continua visível até a tela nova ficar pronta
        C = CORES
        if modo == "cheio":
            self.frame = ttk.Frame(self.root, style="Pagina.TFrame")
            self._tela_pendente = (self.frame, antigo)
            self.root.after_idle(self._publicar_tela)      # garantia, se o montador não usar @sem_piscar
            return self.frame
        tela = tk.Canvas(self.root, bg=C["fundo"], highlightthickness=0, bd=0)
        self.frame = tela
        self._tela_pendente = (tela, antigo)
        self.root.after_idle(self._publicar_tela)
        conteudo = ttk.Frame(tela, style="C.TFrame")
        janela = tela.create_window(0, 0, window=conteudo, anchor="n")   # ancorado no TOPO: o que aparece/some embaixo nao mexe no resto
        tela.create_text(0, 0, text="Criptografado e só neste computador",
                         fill=C["fraco"], font="CofrePequeno", tags="rodape")
        PAD = _px(24)
        estado = {"wh": None, "maxw": 0, "maxh": 0}

        def redesenhar(event=None):
            """Recentraliza o conteúdo quando a janela muda de tamanho."""
            try:
                w, h = tela.winfo_width(), tela.winfo_height()
                if w < 50:
                    return
                # O cartao so CRESCE enquanto esta tela existe (nunca encolhe): trocar de opcao, abrir/fechar uma
                # explicacao ou mudar o numero de linhas de um texto nao faz mais a tela "se redimensionar".
                cw = max(conteudo.winfo_reqwidth() + 2 * PAD, estado["maxw"])
                ch = max(conteudo.winfo_reqheight() + 2 * PAD, estado["maxh"])
                estado["maxw"], estado["maxh"] = cw, ch
                cy = max(ch / 2 + 18, (h - 44) / 2)
                tela.delete("brilho")
                brilho_radial(tela, w / 2, cy - ch * 0.42, max(w, h) * 0.85, C["prim_fundo"], C["fundo"])
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
                tela.coords(janela, w / 2, cy - ch / 2 + PAD)
                tela.coords("rodape", w / 2, max(h - 22, cy + ch / 2 + 22))
                tela.tag_lower("cartao")
                tela.tag_lower("brilho")
            except tk.TclError:
                pass

        tela.bind("<Configure>", redesenhar, add="+")
        conteudo.bind("<Configure>", lambda e: redesenhar(), add="+")
        return conteudo

    def _ligar_raiz(self, sequencia, funcao):
        """bind() na janela principal que SUBSTITUI a ligação anterior de verdade: apaga também o comando Tcl antigo.
        (O bind simples do Tk troca a ligação, mas deixa o comando antigo vivo — e ele segura a tela inteira, com as
        imagens, na memória: um vazamento de objetos GDI/USER a cada bloqueio/desbloqueio.)"""
        ligacoes = self.__dict__.setdefault("_ligacoes_raiz", {})
        novo = self.root.bind(sequencia, funcao)
        antigo = ligacoes.get(sequencia)
        if antigo:
            try:
                self.root.deletecommand(antigo)
            except tk.TclError:
                pass
        ligacoes[sequencia] = novo

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

    def _rotulo_protecao(self, f, pref="C.", compacto=False):
        """Mostra o aviso de proteção do arquivo (fora do pendrive, sem proteção etc.)."""
        largura = _px(250 if compacto else 360)
        lado = "left" if compacto else "top"

        def com_ajuda(curto, longo, cor, titulo):
            """Linha de aviso curta; o texto completo abre no '?'."""
            lin = self._linha_icone(f, "alerta", cor, curto, pref, largura, cor)
            lin.pack(side=lado, anchor="w", fill="x", expand=compacto,
                     padx=(0, _px(8)) if compacto else (0, 0), pady=(0, 0 if compacto else 6))
            self._ajuda(lin, titulo, longo, CORES["fundo"]).pack(
                side="left" if compacto else "right", anchor="n")
        if self._no_disco_do_windows(self.caminho):
            com_ajuda(f"Cofre no disco do Windows ({self._unidade(self.caminho)}).",
                      f"Este cofre está no disco do Windows ({self._unidade(self.caminho)}). O recomendado "
                      "é deixar o programa e o cofre no pendrive.", CORES["alerta"], "Cofre no disco do Windows")
        aviso_fs = aviso_sistema_de_arquivos(sistema_de_arquivos(self.caminho))
        if aviso_fs:
            com_ajuda("Pendrive sem permissões de arquivo.", aviso_fs, CORES["perigo"], "Pendrive sem permissões")
        if hibernacao_ligada():
            com_ajuda("Hibernação ligada neste PC.", AVISO_HIBERNACAO, CORES["alerta"], "Hibernação ligada")
        txt, cor = self._texto_protecao()
        ic = "escudo" if cor == CORES["ok"] else "alerta"
        self._linha_icone(f, ic, cor, txt, pref, largura, cor).pack(
            side=lado, anchor="w", fill="x", expand=compacto, pady=(0, 0 if compacto else 6))

    # ---------- Widgets auxiliares reutilizáveis (ajuda, dicas, campos de senha, medidor de força) ----------

    def _ajuda(self, pai, titulo, texto, fundo=None):
        """Pequeno botão '?' : o texto na tela fica curto e o resto aparece neste pop-up quando a pessoa pedir.
        Devolve o botão (o chamador faz pack/grid)."""
        b = tk.Label(pai, text="?", bg=fundo or CORES["fundo"], fg=CORES["prim_txt"], font="CofreForte",
                     cursor="hand2", padx=7, takefocus=1)
        b.bind("<Button-1>", lambda e: self._popup_ajuda(titulo, texto))
        b.bind("<Return>", lambda e: self._popup_ajuda(titulo, texto))
        b.bind("<space>", lambda e: self._popup_ajuda(titulo, texto))
        self._dica(b, "Mais informações")
        return b

    def _popup_ajuda(self, titulo, texto):
        """Pop-up com o texto completo de uma ajuda '?'. Fecha com Esc, Enter ou 'Entendi'."""
        d = self._nova_janela(titulo)
        fr = ttk.Frame(d, padding=(24, 20, 24, 18))
        fr.pack(fill="both", expand=True)
        ttk.Label(fr, text=titulo, style="H2.TLabel").pack(anchor="w")
        ttk.Label(fr, text=texto, wraplength=_px(420), justify="left").pack(anchor="w", pady=(10, 16))
        ttk.Button(fr, text="Entendi", style="Primario.TButton", command=d.destroy).pack(anchor="e")
        for seq in ("<Escape>", "<Return>"):
            d.bind(seq, lambda e: d.destroy())
        self._modal(d)
        return d

    def _dica(self, widget, texto):
        """Balão de ajuda ao parar o mouse sobre 'widget'."""
        estado = {"j": None, "t": None}

        def mostrar():
            """Mostra a dica (tooltip) junto ao widget."""
            if estado["j"] is not None:
                return
            try:
                j = tk.Toplevel(widget)
                j.wm_overrideredirect(True)
                j.configure(bg=CORES["borda2"])
                tk.Label(j, text=texto, bg=CORES["sup3"], fg=CORES["texto"], font="CofrePequeno",
                         padx=10, pady=5, justify="left", wraplength=_px(300)).pack(padx=1, pady=1)
                j.update_idletasks()
                x = widget.winfo_rootx() + widget.winfo_width() // 2 - j.winfo_reqwidth() // 2
                y = widget.winfo_rooty() + widget.winfo_height() + 6
                j.geometry(f"+{max(0, x)}+{y}")
                proteger_contra_captura(j)
                estado["j"] = j
            except tk.TclError:
                pass

        def entrar(e):
            """O mouse entrou: agenda a dica."""
            estado["t"] = widget.after(450, mostrar)

        def sair(e=None):
            """O mouse saiu: cancela e esconde a dica."""
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

    def _pista_entrada(self, entrada, texto):
        """Mostra uma dica visual sobre o campo, sem inserir esse texto no valor digitado."""
        try:
            fundo = ttk.Style(self.root).lookup(entrada.cget("style") or "TEntry", "fieldbackground")
        except tk.TclError:
            fundo = ""
        rotulo = tk.Label(entrada, text=texto, bg=fundo or CORES["campo"], fg=CORES["fraco"],
                          font="CofreTexto", anchor="w", padx=2, bd=0, cursor="xterm")

        def atualizar(event=None):
            """Exibe a dica enquanto o campo estiver vazio."""
            try:
                if entrada.get():
                    rotulo.place_forget()
                else:
                    rotulo.place(x=_px(8), rely=0.5, anchor="w")
                    rotulo.lift()
            except tk.TclError:
                pass

        entrada._pista_atualizar = atualizar
        rotulo.bind("<Button-1>", lambda e: entrada.focus_set())
        for evento in ("<FocusIn>", "<FocusOut>", "<KeyRelease>", "<<Paste>>", "<<Clear>>", "<Configure>"):
            entrada.bind(evento, atualizar, add="+")
        atualizar()
        return atualizar

    def _pista_texto(self, entrada, texto):
        """Dica visual para caixa multilinha, sem virar parte do texto salvo."""
        rotulo = tk.Label(entrada, text=texto, bg=CORES["campo"], fg=CORES["fraco"],
                          font="CofreTexto", anchor="nw", justify="left", padx=2, pady=1, bd=0,
                          cursor="xterm")

        def atualizar(event=None):
            """Exibe a dica enquanto a caixa estiver vazia."""
            try:
                vazio = not entrada.get("1.0", "end-1c").strip()
                if not vazio:
                    rotulo.place_forget()
                else:
                    rotulo.place(x=_px(10), y=_px(8))
                    rotulo.lift()
            except tk.TclError:
                pass

        rotulo.bind("<Button-1>", lambda e: entrada.focus_set())
        for evento in ("<FocusIn>", "<FocusOut>", "<KeyRelease>", "<<Paste>>", "<<Clear>>", "<Configure>"):
            entrada.bind(evento, atualizar, add="+")
        atualizar()
        return atualizar

    def _campo_secreto(self, mestre, largura=40, pref="", placeholder="••••••••••••", **kw):
        """Campo de senha (caracteres ocultos) que não deixa copiar nem recortar o conteúdo."""
        e = ttk.Entry(mestre, show="•", width=largura, exportselection=False, style=pref + "TEntry", **kw)
        self._bloquear_copia(e)
        if placeholder:
            self._pista_entrada(e, placeholder)
        return e

    @staticmethod
    def _caps_ligado(evento=None):
        """True se o Caps Lock está ligado (no Windows, pelo estado real da tecla)."""
        try:
            if sys.platform == "win32":
                import ctypes
                return bool(ctypes.windll.user32.GetKeyState(0x14) & 1)
        except (AttributeError, OSError, ctypes.ArgumentError):
            pass
        try:
            return bool(evento is not None and (int(evento.state) & 2))
        except Exception:
            return False

    def _aviso_caps(self, campo, aviso):
        """Mostra 'CAPS LOCK LIGADO' ao lado de um campo de senha enquanto a tecla estiver ligada
        (com autodestruição, errar a senha por causa disso é o erro mais caro e mais evitável)."""
        estado = {"v": False}

        def atualizar(ev=None):
            """Mostra ou esconde o aviso de Caps Lock ligado."""
            try:
                lig = self._caps_ligado(ev)
                dentro = aviso.master is campo          # ícone dentro do campo (place) ou texto ao lado (pack)
                if lig and not estado["v"]:
                    if dentro:
                        aviso.place(relx=1.0, x=-6, rely=0.5, anchor="e")
                    else:
                        aviso.pack(side="left", padx=(8, 0))
                    estado["v"] = True
                elif not lig and estado["v"]:
                    aviso.place_forget() if dentro else aviso.pack_forget()
                    estado["v"] = False
            except tk.TclError:
                pass
        campo.bind("<KeyPress>", atualizar, add="+")
        campo.bind("<KeyRelease>", atualizar, add="+")
        campo.bind("<FocusIn>", atualizar, add="+")
        campo.bind("<FocusOut>", lambda ev: ((aviso.place_forget() if aviso.master is campo else aviso.pack_forget()),
                                             estado.update(v=False)), add="+")
        atualizar()

    def _linha_secreta(self, mestre, largura=40, pref="", olho=True, placeholder="••••••••••••"):
        """Campo secreto + botão de mostrar/ocultar (olho) + botão do teclado virtual, num frame."""
        fr = ttk.Frame(mestre, style=pref + "TFrame")
        e = self._campo_secreto(fr, largura, pref, placeholder=placeholder)
        e.pack(side="left", fill="x", expand=True)
        if olho:
            self._botao_olho(fr, e, pref).pack(side="left", fill="y", padx=(6, 0))
        b = ttk.Button(fr, text="⌨", image=imagem_icone(self.root, "teclado", CORES["suave"], 18), compound="image",
                       style=pref + "Quadrado.TButton", takefocus=0, command=lambda: self.teclado_virtual(e))
        b.pack(side="left", fill="y", padx=(6, 0))
        self._dica(b, "Teclado virtual: digite clicando com o mouse.\nAs teclas mudam de lugar — "
                      "programas espiões de teclado não capturam.")
        # ícone discreto DENTRO do campo (à direita do texto), com a mesma cor de fundo do campo
        try:
            fundo = ttk.Style(self.root).lookup(pref + "TEntry", "fieldbackground") or CORES["fundo"]
        except tk.TclError:
            fundo = CORES["fundo"]
        aviso = tk.Label(e, text="⇪ Caps", fg=CORES["alerta"], bg=fundo, font="CofreForte", bd=0, padx=2)
        self._dica(aviso, "Caps Lock ligado: as letras saem em MAIÚSCULAS.\nDesligue antes de digitar a senha.")
        self._aviso_caps(e, aviso)
        return fr, e

    MOSTRAR_SENHA_MS = 30000

    def _botao_olho(self, pai, e, pref=""):
        """Olho que mostra o que está sendo digitado. Volta a esconder sozinho depois de 30 s
        (e o campo continua sem permitir copiar)."""
        estado = {"timer": None}
        b = ttk.Button(pai, text="👁", image=imagem_icone(self.root, "ver", CORES["suave"], 18), compound="image",
                       style=pref + "Quadrado.TButton", takefocus=0)

        def esconder():
            """Volta a ocultar o campo depois de alguns segundos."""
            estado["timer"] = None
            try:
                e.config(show="•")
                b.config(image=imagem_icone(self.root, "ver", CORES["suave"], 18))
            except tk.TclError:
                pass

        def alternar():
            """Mostra ou oculta o texto do campo (mostra por pouco tempo)."""
            try:
                if e.cget("show"):
                    e.config(show="")
                    b.config(image=imagem_icone(self.root, "ocultar", CORES["prim_txt"], 18))
                    if estado["timer"]:
                        b.after_cancel(estado["timer"])
                    estado["timer"] = self._depois_do_widget(b, self.MOSTRAR_SENHA_MS, esconder)
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
        """Rótulo em maiúsculas de um campo."""
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
            """Mostra as dicas de melhoria da senha."""
            if dicas_lbl is not None and painel is None:
                try:
                    dicas_lbl.config(text=texto, foreground=cor or CORES["suave"])
                except tk.TclError:
                    pass

        estado = {"ultimo": None, "pendente": None}

        def pintar_painel(v):
            """Redesenha o painel detalhado (feito logo após a digitação parar, para não pesar a escrita)."""
            estado["pendente"] = None
            try:
                painel.mostrar(v, pin=pin, titulo=titulo)
            except tk.TclError:
                pass

        def atualizar(event=None, inicial=False, forcar=False, ja=False):
            """Reavalia a senha digitada e atualiza o medidor de força (só se o texto mudou).
            ja=True: pinta o painel detalhado imediatamente (usado ao montar um diálogo, para ele já nascer completo)."""
            try:
                v = entrada.get()
            except tk.TclError:
                return
            if v == estado["ultimo"] and not (inicial or forcar):
                return
            estado["ultimo"] = v
            if painel is not None and not (inicial and (not v or painel.cget("text"))):
                if estado["pendente"] is not None:
                    try:
                        entrada.after_cancel(estado["pendente"])
                    except (tk.TclError, ValueError):
                        pass
                try:
                    if inicial or ja or not v:
                        pintar_painel(v)
                    else:
                        estado["pendente"] = entrada.after(70, lambda v=v: pintar_painel(v))
                except tk.TclError:
                    return
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

        def vigiar():
            """Confere o campo a cada 150 ms: pega colar com o mouse, teclado virtual, 'desfazer' e qualquer
            mudança que não gere tecla (a avaliação acompanha o campo em tempo real)."""
            try:
                if not entrada.winfo_exists():
                    return
                if entrada.get() != estado["ultimo"]:
                    atualizar()
                entrada.after(150, vigiar)
            except tk.TclError:
                pass

        for ev in ("<KeyRelease>", "<<Paste>>", "<<Cut>>", "<<Clear>>", "<ButtonRelease-1>", "<FocusIn>"):
            entrada.bind(ev, atualizar, add="+")
        entrada.bind("<<Atualizar>>", lambda e: atualizar(forcar=True), add="+")
        entrada.bind("<<AtualizarJa>>", lambda e: atualizar(forcar=True, ja=True), add="+")
        atualizar(inicial=True)
        entrada.after(150, vigiar)
        return lbl

    @sem_piscar
    # ---------- Telas de criação do cofre e de desbloqueio ----------

    def tela_criar(self):
        """Tela de criação do cofre: modo de desbloqueio, força da senha, nível de blindagem e tentativas; a chave de acesso gerada aparece uma única vez."""
        C = CORES
        f = self._limpar_tela("topo")
        topo = ttk.Frame(f, style="C.TFrame")
        topo.pack(fill="x")
        self._img_marca = desenhar_marca(52).imagem(self.root)
        ttk.Label(topo, image=self._img_marca, style="C.TLabel").pack(side="left", padx=(0, 16))
        tt = ttk.Frame(topo, style="C.TFrame")
        tt.pack(side="left", fill="x")
        tit = ttk.Frame(tt, style="C.TFrame")
        tit.pack(anchor="w")
        ttk.Label(tit, text="Criar seu cofre", style="C.Titulo.TLabel").pack(side="left")
        self._ajuda(tit, "Senha mestra",
                    "A senha mestra protege tudo. Ela nunca sai deste computador e não pode ser recuperada: "
                    "se a esquecer, ninguém consegue abrir o cofre.\n\nLocal do cofre:\n"
                    + os.path.abspath(self.caminho), CORES["fundo"]).pack(side="left", padx=(8, 0))
        ttk.Label(tt, text="Defina a senha e a forma de abrir o cofre.",
                  style="C.Suave.TLabel").pack(anchor="w")
        ttk.Separator(f).pack(fill="x", pady=(10, 8))

        colunas = ttk.Frame(f, style="C.TFrame")
        colunas.pack(fill="x")
        esq = ttk.Frame(colunas, style="Card.TFrame", width=_px(380), padding=(_px(12), _px(10)))
        esq.pack(side="left", fill="y", anchor="n")
        ttk.Frame(colunas, style="C.TFrame", width=_px(18)).pack(side="left")
        dir_ = ttk.Frame(colunas, style="Card.TFrame", padding=(_px(12), _px(10)))
        dir_.pack(side="left", fill="both", expand=True, anchor="n")

        ttk.Label(esq, text="1. Defina a senha mestra", style="C.H2.TLabel",
                  image=imagem_icone(self.root, "cadeado", C["prim_txt"], 16), compound="left").pack(anchor="w")
        ttk.Label(esq, text="Se esquecer esta senha, não será possível recuperar o cofre.",
                  style="C.Suave.TLabel", wraplength=_px(340), justify="left").pack(anchor="w", pady=(3, 8))
        ttk.Label(esq, text="Faça backup cifrado fora do pendrive. Cópias locais podem ser apagadas após erros.",
                  style="C.Suave.TLabel", wraplength=_px(340), justify="left",
                  foreground=C["alerta"]).pack(anchor="w", pady=(0, 8))
        self._rotulo_campo(esq, f"Nova senha  (mínimo {MIN_SENHA} caracteres)").pack(anchor="w")
        l1fr = ttk.Frame(esq, style="C.TFrame")
        l1fr.pack(fill="x", pady=(4, 0))
        l1, s1 = self._linha_secreta(l1fr, 30, "C.", placeholder="Crie uma senha longa")
        l1.pack(side="left", fill="x", expand=True)
        bg = ttk.Button(l1fr, text="Gerar…", image=imagem_icone(self.root, "gerar", C["texto"]), compound="left",
                        style="C.Fino.TButton",
                        command=lambda: self.dialogo_gerador(s1, "frase", senha_mestra=True, extra=s2))
        bg.pack(side="left", padx=(6, 0))
        self._dica(bg, "Gera uma senha forte: escolha o tipo e o TAMANHO.\nRecomendado: frase fácil de lembrar "
                       "com 5 ou 6 palavras.")
        self._dicas_mestra = PainelForca(esq, self, largura=_px(400), pref="C.",
                                         vazio="A análise aparece quando você digitar a senha.")
        self._medidor(esq, s1, dicas_lbl=self._dicas_mestra, pref="C.").pack(anchor="w", pady=(8, 0))
        self._rotulo_campo(esq, "Confirme a senha").pack(anchor="w", pady=(14, 0))
        l2, s2 = self._linha_secreta(esq, 30, "C.", placeholder="Repita a senha mestra")
        l2.pack(fill="x", pady=(4, 0))
        confere = ttk.Label(esq, text="", style="C.TLabel")
        confere.pack(anchor="w", pady=(6, 0))
        self._dicas_mestra.pack(fill="x", pady=(6, 0))

        modo = tk.IntVar(value=MODO_E)
        usar_fido = tk.BooleanVar(value=False)

        def atualizar_proximo():
            """Explica o que vai acontecer depois da criação conforme as opções escolhidas."""
            if modo.get() == MODO_S:
                texto = "Depois de criar, o cofre abrirá com a senha mestra."
            elif modo.get() == MODO_E:
                texto = "Guarde a chave de acesso; ela aparece uma vez."
            else:
                texto = "A chave: ela também poderá abrir o cofre sozinha."
            if usar_fido.get():
                texto += " O cadastro da chave física será solicitado."
            proximo.config(text="PRÓXIMO PASSO: " + texto)

        cab_modo = ttk.Frame(dir_, style="C.TFrame")
        cab_modo.pack(anchor="w", fill="x")
        ttk.Label(cab_modo, text="2. Escolha como abrir", style="C.H2.TLabel",
                  image=imagem_icone(self.root, "chave", C["prim_txt"], 16), compound="left").pack(side="left")
        self._ajuda(cab_modo, "Como o cofre abre",
                    "• Só senha mestra: a forma mais simples. Quem souber a senha abre.\n\n"
                    "• Senha E chave de acesso (recomendado): dois fatores. A chave aparece uma única vez, "
                    "agora; quem descobrir só a senha, ou só a chave, não abre.\n\n"
                    "• Senha OU chave de acesso: qualquer uma das duas abre. A chave serve de recuperação se "
                    "você esquecer a senha, mas é menos seguro.\n\n"
                    "• Chave FIDO (opcional, soma-se a qualquer modo): uma chave física USB/NFC com toque. "
                    "Perdendo a chave, o código de recuperação em papel a substitui. Só passa a valer depois de "
                    "cadastrar a primeira chave (próximo passo).",
                    CORES["fundo"]).pack(side="left", padx=(4, 0))
        ttk.Label(dir_, text="Escolha como abrir o cofre.",
                  style="C.Suave.TLabel", wraplength=_px(420), justify="left").pack(anchor="w", pady=(4, 2))

        cartoes = {}

        def atualizar_cartoes(variavel):
            """Destaca com o acento do cofre a opção selecionada em cada grupo."""
            for valor, cartao in cartoes.get(id(variavel), ()):
                selecionado = variavel.get() == valor
                cartao.configure(highlightbackground=C["prim"] if selecionado else C["borda"],
                                 highlightthickness=_px(2))      # espessura FIXA: so a cor muda (senao o cartao "pula")

        def opcao_cartao(pai, variavel, valor, titulo, descricao, comando=None):
            """Opção de segurança em cartão clicável, com explicação e seleção destacada."""
            cartao = tk.Frame(pai, bg=C["sup2"], bd=0, cursor="hand2",
                              highlightbackground=C["borda"], highlightcolor=C["prim"],
                              highlightthickness=_px(2))
            cartao.pack(fill="x", pady=(_px(3), 0))
            corpo = ttk.Frame(cartao, style="Card2.TFrame", padding=(_px(8), _px(4)))
            corpo.pack(fill="both", expand=True)

            def mudou():
                """Atualiza o destaque e qualquer resumo dependente da seleção."""
                atualizar_cartoes(variavel)
                if comando:
                    comando()

            radio = ttk.Radiobutton(corpo, text=titulo, value=valor, variable=variavel,
                                    style="S2.TRadiobutton", command=mudou)
            radio.pack(anchor="w", fill="x")
            detalhe = ttk.Label(corpo, text=descricao, style="S2.Suave.TLabel",
                                wraplength=_px(420), justify="left")
            detalhe.pack(anchor="w", padx=(_px(28), 0), pady=(_px(1), 0))
            cartoes.setdefault(id(variavel), []).append((valor, cartao))

            def selecionar(event=None):
                """Seleciona também ao clicar na área explicativa do cartão."""
                variavel.set(valor)
                mudou()
                return "break"

            cartao.bind("<Button-1>", selecionar, add="+")
            detalhe.bind("<Button-1>", selecionar, add="+")
            detalhe.configure(cursor="hand2")
            atualizar_cartoes(variavel)
            return cartao

        opcao_cartao(dir_, modo, MODO_S, "Só senha mestra",
                     "Só a senha abre o cofre. Use uma frase longa e exclusiva.", atualizar_proximo)
        opcao_cartao(dir_, modo, MODO_E, "Senha E chave de acesso  (recomendado)",
                     "Exige senha e chave juntas; guarde a chave em local seguro.", atualizar_proximo)
        opcao_cartao(dir_, modo, MODO_OU, "Senha OU chave de acesso",
                     "Qualquer uma abre; oferece menos proteção.",
                     atualizar_proximo)

        fido = ttk.Frame(dir_, style="Card2.TFrame", padding=(_px(8), _px(4)))
        fido.pack(fill="x", pady=(_px(4), 0))
        ttk.Checkbutton(fido, text="Exigir também a chave FIDO", variable=usar_fido,
                        style="S2.TCheckbutton", command=atualizar_proximo).pack(anchor="w")
        ttk.Label(fido, text="Opcional: chave física USB/NFC; cadastro após criar.",
                  style="S2.Suave.TLabel", wraplength=_px(420), justify="left").pack(
                      anchor="w", padx=(_px(28), 0))

        ttk.Separator(dir_).pack(fill="x", pady=(_px(8), _px(6)))
        nivel = tk.StringVar(value=nivel_recomendado())      # PC com pouca RAM livre começa em "Alta" (sem paginação)
        cab_nivel = ttk.Frame(dir_, style="C.TFrame")
        cab_nivel.pack(anchor="w", fill="x")
        ttk.Label(cab_nivel, text="3. Proteção contra tentativas", style="C.H2.TLabel",
                  image=imagem_icone(self.root, "escudo", C["ok"], 16), compound="left").pack(side="left")
        self._ajuda(cab_nivel, "Proteção contra tentativas",
                    "Define quanta memória cada tentativa de adivinhar a senha pode usar. Mais memória dificulta "
                    "tentativas automatizadas, mas também exige mais recursos deste computador.\n\n"
                    "• Máxima (1 GB): escolha se o computador tiver memória livre suficiente.\n"
                    "• Alta (256 MB): alternativa para computadores com pouca memória livre.",
                    CORES["fundo"]).pack(side="left", padx=(4, 0))
        ttk.Label(dir_, text="Alta é indicada para computadores com pouca memória livre.",
                  style="C.Suave.TLabel", wraplength=_px(420), justify="left").pack(anchor="w", pady=(2, 1))
        opcao_cartao(dir_, nivel, "maximo", "Máxima — 1 GB por tentativa",
                     "Maior proteção; requer mais memória.")
        opcao_cartao(dir_, nivel, "alto", "Alta — 256 MB por tentativa",
                     "Alternativa para pouca memória.")
        proximo_fr = ttk.Frame(dir_, style="C.TFrame")
        proximo_fr.pack(fill="x", pady=(_px(6), 0))
        proximo = ttk.Label(proximo_fr, text="", style="C.Suave.TLabel", wraplength=_px(420), justify="left")
        proximo.pack(anchor="w")
        # Reserva a altura do MAIOR texto possivel: trocar de opcao nao muda mais a altura da tela.
        modo_orig, fido_orig, altura_max = modo.get(), usar_fido.get(), 0
        for m_ in (MODO_S, MODO_E, MODO_OU):
            for fi_ in (False, True):
                modo.set(m_)
                usar_fido.set(fi_)
                atualizar_proximo()
                proximo.update_idletasks()
                altura_max = max(altura_max, proximo.winfo_reqheight())
        modo.set(modo_orig)
        usar_fido.set(fido_orig)
        proximo_fr.configure(height=altura_max)
        proximo_fr.pack_propagate(False)
        atualizar_proximo()

        def criar(event=None):
            """Valida os campos da tela e cria o cofre em segundo plano."""
            a, b = s1.get(), s2.get()
            problema = avaliar_senha(a)
            if problema:
                messagebox.showerror("Senha fraca", problema)
                return
            if a != b:
                messagebox.showerror("Erro", "As senhas não conferem.")
                return
            n = TENTATIVAS_PADRAO            # o limite de erros se ajusta DEPOIS, dentro do cofre (⋯ > Tentativas erradas)
            if modo.get() == MODO_E and not messagebox.askyesno(
                    "Modo dois fatores", "Neste modo o cofre só abre com a senha E a chave de acesso "
                    "juntas.\nPerder qualquer uma das duas = perder o cofre para sempre.\n\nContinuar?"):
                return
            if modo.get() == MODO_OU and not messagebox.askyesno(
                    "Modo OU — menos seguro", "Neste modo a chave de acesso (ou o arquivo .key) abre o cofre "
                    "SOZINHA, sem a senha. A segurança passa a ser a do pior dos dois fatores.\n\n"
                    "O recomendado é o modo de dois fatores (senha E chave). Continuar mesmo assim?", perigoso=True):
                return
            self._ocupado(True)
            try:
                self.cofre = self._com_espera(
                    lambda: Cofre.criar(self.caminho, a, n, modo.get(), nivel.get()), "Criando o cofre…")
            except MemoryError:
                self._ocupado(False)
                messagebox.showerror("Memória insuficiente", "Este computador não tem memória livre "
                                     "para a blindagem Máxima. Escolha a blindagem Alta.")
                return
            except OSError as ex:
                self._ocupado(False)
                messagebox.showerror("Erro", f"Não foi possível criar o arquivo:\n{texto_erro(ex)}")
                return
            self._ocupado(False)
            zerar_objeto(a)                  # a senha digitada não precisa mais ficar na memória
            zerar_objeto(b)
            chave, self.cofre.chave_gerada = self.cofre.chave_gerada, None
            if chave:                        # modo "só senha" não tem chave de acesso para mostrar
                self.mostrar_chave_acesso(chave, self.cofre.modo)
                zerar_objeto(chave)
            self.tela_principal()
            self._autorizar_primeiro_pc_na_criacao()
            self.root.after(700, self._oferecer_passeio)      # 1ª entrada: oferece o guia (espera janelas abertas)
            if usar_fido.get():              # marcou "Exigir também a chave FIDO": cadastra já
                self.gerenciar_fido()

        def conferir(event=None):
            """Confere se a senha e a confirmação são iguais."""
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

        rod = ttk.Frame(self.root, style="C.TFrame", padding=(_px(36), 0, _px(36), _px(8)))
        self._rodape_criar = rod
        rod.pack(side="bottom", fill="x")
        ttk.Separator(rod).pack(fill="x", pady=(0, _px(10)))
        linha_rodape = ttk.Frame(rod, style="C.TFrame")
        linha_rodape.pack(fill="x")
        prot = ttk.Frame(linha_rodape, style="C.TFrame")
        prot.pack(side="left", fill="x", expand=True)
        self._rotulo_protecao(prot, compacto=True)
        ttk.Button(linha_rodape, text="Criar cofre", style="C.Primario.TButton", command=criar,
               image=imagem_icone(self.root, "seta", C["prim_fg"]), compound="right").pack(
                       side="right", padx=(12, 0), anchor="n")
        s1.focus_set()

    @sem_piscar
    def tela_desbloqueio(self):
        """Tela de desbloqueio: pede senha, chave ou FIDO conforme o modo do cofre e abre em segundo plano; erros de formato não gastam tentativa."""
        C = CORES
        f = self._limpar_tela("centro")
        self._img_marca = desenhar_marca(64).imagem(self.root)
        ttk.Label(f, image=self._img_marca, style="C.TLabel").pack()
        ttk.Label(f, text=_NOME_PRODUTO, style="C.Titulo.TLabel").pack(pady=(12, 0))
        modo_cofre, exige_fido = MODO_OU, False
        rest = None
        exige_pc, pc_ok = False, True
        try:
            rest, modo_cofre, exige_fido = info_cofre(self.caminho)
            exige_pc, pc_ok = info_pc(self.caminho)
            info = ""                           # as tentativas que restam já aparecem no selo (sem repetir o texto)
        except (ArquivoInvalido, OSError) as ex:
            info = str(ex)
        dois_fatores = modo_cofre == MODO_E
        so_senha = modo_cofre == MODO_S
        ttk.Frame(f, style="C.TFrame", height=_px(14)).pack()
        # Selo SEMPRE visível com as tentativas que ainda restam (atualiza a cada senha errada)
        linha_chip = ttk.Frame(f, style="C.TFrame")
        linha_chip.pack(pady=(0, 14))
        chip = tk.Label(linha_chip, text="", bg=C["sup2"], fg=C["alerta"], font="CofreForte", padx=14, pady=6)
        chip.pack(side="left")
        self._ajuda(linha_chip, "Autodestruição",
                    "Se a senha (ou a chave) for digitada ERRADA o número de vezes mostrado, o cofre é apagado "
                    "para sempre.\n\nSó contam tentativas erradas: abrir e fechar o programa não gasta nenhuma, e ao "
                    "acertar o contador volta ao máximo. No Modo Consulta nada é gravado, então nada é contado.",
                    C["fundo"]).pack(side="left", padx=(6, 0))

        def atualizar_chip(restam, consulta=False):
            """Atualiza o selo de tentativas restantes (amarelo; vermelho quando restam 2 ou menos)."""
            if consulta:
                chip.config(text="MODO CONSULTA: sem contagem", fg=C["suave"])
            elif restam is None:
                chip.config(text="", bg=C["sup"])
            else:
                chip.config(text=f"Tentativas restantes: {restam}",
                            fg=C["perigo"] if restam <= 2 else C["alerta"], bg=C["sup2"])

        atualizar_chip(rest, consulta=self.em_uso)

        modo = tk.StringVar(value="senha")
        form = ttk.Frame(f, style="C.TFrame", width=400)
        form.pack(fill="x")
        if not dois_fatores and not so_senha:
            seg = ttk.Frame(form, style="C.TFrame")
            seg.pack(fill="x", pady=(0, 14))
        bloco_senha = ttk.Frame(form, style="C.TFrame")
        self._rotulo_campo(bloco_senha, "Senha mestra").pack(anchor="w")
        cx1, e_senha = self._linha_secreta(bloco_senha, 36, "C.", placeholder="Senha mestra")
        cx1.pack(fill="x", pady=(4, 0))
        bloco_chave = ttk.Frame(form, style="C.TFrame")
        lc = ttk.Frame(bloco_chave, style="C.TFrame")
        lc.pack(fill="x")
        self._rotulo_campo(lc, "Chave de acesso").pack(side="left", anchor="w")
        bt_arq = ttk.Button(lc, text="Carregar .key…", style="C.Fantasma.TButton",
                            image=imagem_icone(self.root, "importar", C["suave"], 14), compound="left")
        bt_arq.pack(side="right")
        cx2, e_chave = self._linha_secreta(bloco_chave, 36, "C.", placeholder="Chave de acesso")
        cx2.pack(fill="x", pady=(2, 0))

        def mostrar_campos():
            """Mostra só os campos exigidos pelo modo do cofre."""
            bloco_senha.pack_forget()
            bloco_chave.pack_forget()
            if dois_fatores or modo.get() == "senha":
                bloco_senha.pack(fill="x")
            if dois_fatores or modo.get() == "chave":
                bloco_chave.pack(fill="x", pady=(12 if dois_fatores else 0, 0))

        def trocar_modo():
            """Alterna entre senha, chave e recuperação, limpando os campos."""
            e_senha.delete(0, "end")
            e_chave.delete(0, "end")
            mostrar_campos()
            (e_senha if modo.get() == "senha" else e_chave).focus_set()

        if not dois_fatores and not so_senha:
            for valor, texto in (("senha", "Senha mestra"), ("chave", "Chave de acesso")):
                ttk.Radiobutton(seg, text=texto, value=valor, variable=modo, command=trocar_modo,
                                style="C.Segmento.Toolbutton").pack(side="left", fill="x", expand=True)

        def carregar_arquivo():
            """Lê a chave de acesso de um arquivo .key escolhido."""
            arq = filedialog.askopenfilename(title="Selecionar arquivo de chave",
                                             filetypes=[("Chave do cofre", "*.key"), ("Todos", "*.*")])
            if not arq:
                return
            try:
                with open(arq, "rb") as fh:
                    bruto = fh.read(4096)
                conteudo = chave_de_arquivo(self.caminho, bruto)      # selado: decifra com o cabeçalho deste cofre
            except ChaveMalFormada as ex:
                lbl.config(text=f"{ex} Nenhuma tentativa foi gasta.", foreground=C["alerta"])
                return
            except (OSError, ArquivoInvalido, ValueError) as ex:
                messagebox.showerror("Erro", f"Não foi possível ler o arquivo:\n{texto_erro(ex)}")
                return
            e_chave.delete(0, "end")
            e_chave.insert(0, conteudo)
            lbl.config(text="Chave carregada ✓", foreground=C["ok"])

        bt_arq.config(command=carregar_arquivo)
        mostrar_campos()

        usar_rec = tk.BooleanVar(value=False)
        e_rec = None
        pc_bloqueado = exige_pc and not pc_ok        # este computador não está na lista: só o código de recuperação abre
        if exige_fido or pc_bloqueado:
            ff = ttk.Frame(f, style="C.TFrame")
            ff.pack(fill="x", pady=(14, 0))
            if pc_bloqueado:
                texto_ff = ("  Este computador não está autorizado neste cofre. Use o código de recuperação."
                            if not exige_fido else
                            "  Este cofre exige a chave FIDO e este computador não está autorizado: use o código de recuperação.")
            else:
                texto_ff = "  Este cofre exige também a chave FIDO."
            ttk.Label(ff, text=texto_ff,
                      image=imagem_icone(self.root, "chave", C["prim_txt"], 16), compound="left",
                      style="C.TLabel", wraplength=_px(380), justify="left").pack(anchor="w")
            lrec = ttk.Frame(ff, style="C.TFrame")
            self._rotulo_campo(lrec, "Código de recuperação").pack(anchor="w")
            cx3, e_rec = self._linha_secreta(lrec, 36, "C.", placeholder="Código de recuperação")
            cx3.pack(fill="x", pady=(4, 0))

            def alternar_rec():
                """Alterna o uso do código de recuperação."""
                if usar_rec.get():
                    lrec.pack(fill="x", pady=(8, 0))
                    e_rec.focus_set()
                else:
                    e_rec.delete(0, "end")
                    lrec.pack_forget()

            if pc_bloqueado:
                usar_rec.set(True)                    # não há outra forma de abrir aqui: o campo já aparece
                alternar_rec()
            else:
                ttk.Checkbutton(ff, text="Estou sem a chave FIDO — usar o código de recuperação",
                                variable=usar_rec, command=alternar_rec, style="C.TCheckbutton").pack(anchor="w",
                                                                                                        pady=(6, 0))

        def tentar(senha=None, chave=None, recuperacao=None, consulta=False):
            """Faz a tentativa de abertura em segundo plano (antes confere se há espiões).
            consulta=True: MODO CONSULTA (pendrive protegido contra gravação; não grava nada)."""
            if getattr(self, "_trabalhando", False):
                return
            consulta = consulta or self.em_uso          # cofre aberto em outra janela: esta só lê
            espias = ferramentas_espias()
            if espias:
                lbl.config(text="Há um programa capaz de ler a memória aberto: " + ", ".join(espias) +
                                ". Feche-o para desbloquear. Nenhuma tentativa foi gasta.", foreground=C["perigo"])
                return
            if pc_bloqueado and not recuperacao:
                lbl.config(text="Este computador não está autorizado neste cofre: digite o código de recuperação. "
                                "Nenhuma tentativa foi gasta.", foreground=C["alerta"])
                return
            hwnd = _hwnd(self.root)
            provedor = None
            if exige_fido and not recuperacao:
                def provedor(creds, salt):
                    return fido_obter(hwnd, creds, salt)
                lbl.config(text="Toque na sua chave FIDO quando ela piscar (e digite o PIN dela se o "
                                "Windows pedir)...", foreground=C["prim_txt"])
            else:
                # "Verificando..." sozinho, parado na tela, parecia travado durante a derivação Argon2id da
                # proteção Máxima (1 GB/6 iterações, de propósito bem pesada contra força bruta): pode levar
                # vários segundos de verdade, então aqui ela pulsa e avisa o motivo (achado real 2026-11-13:
                # usuário relatou "extrema lentidão" na primeira abertura). Isso é só feedback visual: o
                # custo do Argon2id em si não muda (reduzi-lo enfraqueceria a defesa contra o cofre roubado).
                inicio_verif = time.time()
                def _tique_verificando(i=inicio_verif):
                    if not getattr(self, "_trabalhando", False):
                        return
                    decorrido = time.time() - i
                    pontos = "." * (1 + int(decorrido * 2) % 3)
                    extra = ("  (a proteção Máxima usa 1 GB de memória de propósito: pode levar vários segundos)"
                             if decorrido > 2.5 else "")
                    try:
                        lbl.config(text="Verificando" + pontos + extra, foreground=C["suave"])
                    except tk.TclError:
                        return
                    self.root.after(350, _tique_verificando)
                _tique_verificando()
            bt_abrir.state(["disabled"])
            self._trabalhando = True
            self._ocupado(True)
            self._em_segundo_plano(
                lambda: Cofre.abrir(self.caminho, senha=senha, chave=chave,
                                    fido=provedor, recuperacao=recuperacao, consulta=consulta),
                lambda cofre, erro: concluir(cofre, erro, (senha, chave, recuperacao)))

        def consulta_ou_em_uso():
            """True se esta tela está no modo consulta/em uso (nada é contado nesses casos)."""
            return bool(self.em_uso)

        def concluir(cofre, erro, digitados=()):
            """Recebe o resultado da abertura: mostra o erro (senha errada, chave, FIDO) ou entra na tela principal; apaga da memória o que foi digitado."""
            self._trabalhando = False
            # Pendrive protegido contra gravação: guarda o que foi digitado só até o usuário decidir sobre o MODO CONSULTA
            protegido = isinstance(erro, ErroGravacao) and erro.protegido
            if not protegido:
                for _seg in digitados:                   # o que foi digitado já foi usado: apaga da memória
                    zerar_objeto(_seg)
            try:
                bt_abrir.state(["!disabled"])
            except tk.TclError:
                pass
            try:
                if erro is not None:
                    raise erro
                self.cofre = cofre
                self._restauracoes_tentadas = None
                self._erros_formato = 0
                if self.em_uso:
                    self.cofre.motivo_consulta = "em_uso"
            except (ChaveMalFormada, FatorFaltando, FidoErro) as ex:
                self._ocupado(False)
                if isinstance(ex, ChaveMalFormada) and not (consulta_ou_em_uso()):
                    # Erro de digitação da chave é perdoado só nas 3 primeiras vezes da sessão; depois conta,
                    # para ninguém "testar" chaves de graça na tela de desbloqueio.
                    self._erros_formato = getattr(self, "_erros_formato", 0) + 1
                    if self._erros_formato > 3:
                        try:
                            restam_f = gastar_tentativa_arquivo(self.caminho)
                        except CofreDestruido:
                            apagar_dados_locais()          # a preferência de cor também não pode sobrar
                            messagebox.showerror("Cofre destruído", "Limite de tentativas atingido. O cofre foi apagado.")
                            self.mostrar_inicio()
                            return
                        except (OSError, ArquivoInvalido, ArquivoCorrompido):
                            restam_f = None
                        if restam_f is not None:
                            self._erros_sessao += 1
                            lbl.config(text=f"{ex} Esta tentativa foi CONTADA. Restam {restam_f}.", foreground=C["perigo"])
                            atualizar_chip(restam_f)
                            return
                    lbl.config(text=f"{ex} Não contou como tentativa (só as 3 primeiras; depois cada erro conta).",
                               foreground=C["alerta"])
                    return
                lbl.config(text=f"{ex} Nenhuma tentativa foi gasta.", foreground=C["alerta"])
                return
            except SenhaIncorreta as ex:
                self._erros_sessao += 1
                self._ocupado(False)
                if getattr(ex, "consulta", False):
                    lbl.config(text="Senha ou chave incorreta. Modo consulta: esta tentativa não é contada.", foreground=C["perigo"])
                    return
                lbl.config(text=f"Senha ou chave incorreta. Restam {ex.restantes}.", foreground=C["perigo"])
                restam_ = ex.restantes
                atualizar_chip(restam_)
                chip.config(bg=C["perigo"], fg=_texto_contraste(C["perigo"]))
                self._depois_do_widget(chip, 900, lambda: atualizar_chip(restam_))
                return
            except CofreDestruido:
                self._ocupado(False)
                apagar_dados_locais()                      # a preferência de cor também não pode sobrar
                messagebox.showerror("Cofre destruído",
                                     "Limite de tentativas atingido. O cofre foi apagado.")
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
                diag_registrar(DIAG_INTEGRIDADE, ex)
                if self._restauracoes_tentadas is not None:
                    usada = restaurar_copia(self.caminho, ignoradas=self._restauracoes_tentadas)
                    if usada:
                        self._restauracoes_tentadas.append(usada)
                        messagebox.showwarning(
                            "Outra cópia selecionada",
                            "A cópia restaurada não passou pela verificação de integridade após a senha ser "
                            "confirmada. Selecionei a próxima cópia automática; digite a senha novamente. "
                            "Nenhuma tentativa foi gasta.")
                    else:
                        self._restauracoes_tentadas = None
                        messagebox.showerror(
                            "Cópias automáticas danificadas",
                            "A cópia restaurada também está danificada e não há outra cópia automática legível. "
                            "Use o backup cifrado externo.")
                    self.mostrar_inicio()
                    return
                self._oferecer_restauracao(str(ex))
                return
            except ErroGravacao as ex:
                self._ocupado(False)
                diag_registrar(DIAG_LEITURA, ex)
                if not ex.protegido:
                    messagebox.showerror("Erro", texto_erro(ex))
                    return
                # O pendrive não deixa gravar (chave física, política do computador ou somente leitura): oferece o MODO CONSULTA
                if messagebox.askyesno(
                        "Pendrive protegido contra gravação",
                        "Este pendrive (ou este computador) não permite gravar.\n\n"
                        "Posso abrir o cofre em MODO CONSULTA: você vê e copia suas senhas, mas nada pode ser "
                        "adicionado, alterado ou apagado nesta sessão. Como nada é gravado, as tentativas de senha "
                        "não são contadas (a autodestruição não age neste modo).\n\nAbrir em modo consulta?"):
                    s_, k_, r_ = (list(digitados) + [None, None, None])[:3]
                    tentar(senha=s_, chave=k_, recuperacao=r_, consulta=True)   # a nova tentativa apaga os textos ao terminar
                else:
                    for _seg in digitados:
                        zerar_objeto(_seg)
                return
            except (ArquivoInvalido, OSError, ValueError) as ex:
                self._ocupado(False)
                diag_registrar(DIAG_LEITURA, ex)
                messagebox.showerror("Erro", texto_erro(ex))
                return
            self._ocupado(False)
            if self.cofre.chave_gerada:      # cofre antigo convertido: mostra a nova chave
                chave_nova, self.cofre.chave_gerada = self.cofre.chave_gerada, None
                messagebox.showinfo("Cofre atualizado", "Seu cofre foi atualizado e agora também "
                                    "abre com uma chave de acesso. Guarde-a na próxima tela.")
                self.mostrar_chave_acesso(chave_nova, self.cofre.modo)
                zerar_objeto(chave_nova)
            self.tela_principal()
            if os.environ.get("COFRE_SEM_VERIFICACAO_INICIAL") != "1":     # testes de interface podem desligar
                self.verificar_integridade_cofre(automatica=True)
            self._alerta_invasao()
            if getattr(self, "_msg_abertura", ""):
                try:                       # a verificação/alerta acima abrem janelas: a tela pode ter sido trocada ou bloqueada
                    self.status.config(text=self._msg_abertura)
                except tk.TclError:
                    pass
            self.root.after(700, self._oferecer_passeio)

        def abrir(event=None):
            """Confere o aviso de última tentativa e chama `tentar` com o que foi digitado."""
            if getattr(self, "_trabalhando", False):
                return
            try:
                restam = tentativas_restantes(self.caminho)
            except Exception:
                restam = None
            if restam == 1 and not messagebox.askyesno(
                    "ÚLTIMA tentativa",
                    "Esta é a ÚLTIMA tentativa. Se a senha ou a chave estiver errada, o cofre será "
                    "DESTRUÍDO e só o seu backup externo o traz de volta.\n\nTem certeza de que digitou "
                    "certo? (Dica: use o olho para conferir o que digitou.)", perigoso=True):
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
                              image=imagem_icone(self.root, "aberto", C["prim_fg"]), compound="left")
        bt_abrir.pack(fill="x", pady=(20, 0))
        lbl = ttk.Label(f, text=info, foreground=C["alerta"], style="C.TLabel", wraplength=_px(400), justify="center",
                        anchor="center")
        lbl.pack(fill="x", pady=(12, 0), before=bt_abrir)           # o aviso fica ACIMA do botão, junto dos campos
        bt_abrir.pack_configure(pady=(12, 0))
        # REVELAÇÃO PROGRESSIVA: a tela inicial mostra só o essencial (senha, botão, tentativas). Estado da proteção,
        # avisos do pendrive, hibernação e dicas ficam num painel "Avançado", montado só se a pessoa abrir.
        avancado = ttk.Frame(f, style="C.TFrame")
        estado_av = {"montado": False, "aberto": False}
        try:
            ha_aviso = bool(aviso_sistema_de_arquivos(sistema_de_arquivos(self.caminho))) or hibernacao_ligada() \
                or self._no_disco_do_windows(self.caminho)
        except Exception:
            ha_aviso = False
        bt_av = ttk.Button(f, style="C.Fantasma.TButton",
                           image=imagem_icone(self.root, "info", C["alerta"] if ha_aviso else C["fraco"], 14),
                           compound="left")

        def texto_botao_av():
            """Rótulo do botão: 'Avançado' (com ⚠ se houver aviso) e a seta do estado."""
            return ("Avançado" + ("  ⚠ avisos" if ha_aviso else "") + ("  ▴" if estado_av["aberto"] else "  ▾"))

        def alternar_avancado():
            """Abre ou fecha o painel avançado (estado da proteção, avisos e dicas)."""
            if not estado_av["aberto"]:
                if not estado_av["montado"]:
                    estado_av["montado"] = True
                    ttk.Separator(avancado).pack(fill="x", pady=(0, 10))
                    self._rotulo_protecao(avancado)
                    lin_t = self._linha_icone(avancado, "teclado", C["fraco"],
                                              "Teclado da tela disponível ao lado do campo.", "C.", _px(360))
                    lin_t.pack(anchor="w", fill="x")
                    self._ajuda(lin_t, "Teclado da tela", "Use o teclado da tela (botão ao lado do campo) para "
                                "digitar a senha com o mouse. Programas que gravam o teclado não capturam o que "
                                "você clica.", C["fundo"]).pack(side="right", anchor="n")
                avancado.pack(fill="x", pady=(8, 0))
                estado_av["aberto"] = True
            else:
                avancado.pack_forget()
                estado_av["aberto"] = False
            bt_av.config(text=texto_botao_av())
        bt_av.config(text=texto_botao_av(), command=alternar_avancado)
        bt_av.pack(pady=(14, 0))
        e_senha.focus_set()


    def _ocupado(self, sim):
        """Liga ou desliga o cursor de espera."""
        self.root.config(cursor="watch" if sim else "")
        self.root.update()
        if not sim:
            self._ultimo_tique = time.time()      # o Argon2 trava a janela por segundos: não é "o PC dormiu"

    # ---------- bloquear junto com o Windows / esconder ao perder o foco ----------
    # ---------- Vigilância de segurança: foco da janela, captura de tela, invasão e ocultação automática ----------

    def _monitorar_espias(self):
        """Mantém um único trabalhador para verificar processos sem criar um thread novo a cada ciclo."""
        while True:
            self._espias_pedido.wait()
            self._espias_pedido.clear()
            if self._espias_parar.is_set():
                return
            try:
                self._espias_res = ferramentas_espias()
            except Exception as ex:
                self._espias_erro = ex

    def _parar_monitor_espias(self):
        """Acorda e encerra o trabalhador de verificação antes de fechar a janela."""
        self._espias_parar.set()
        self._espias_pedido.set()
        thread = self._espias_thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1)

    def _vigiar_sistema(self):
        """Vigia periódica: bloqueia se o PC dormiu, se a sessão foi travada ou se surgiu ferramenta espiã/depurador."""
        agora_parede = time.time()
        agora = time.monotonic()
        try:
            if self._ocultadores and not self._app_sem_foco():
                self._mostrar_conteudo()          # voltou ao programa: tira o aviso "Conteúdo oculto"
            # Fora do programa por muito tempo (navegador, outro app): apaga as chaves da RAM e pede a senha de novo,
            # reduzindo o que um despejo de memória acidental poderia revelar.
            if self.cofre is not None and agora - getattr(self, "_ultimo_gc", 0.0) >= GC_PERIODICO_S:
                self._ultimo_gc = agora
                import gc
                gc.collect()                       # solta objetos soltos (restos de textos) junto da varredura de RAM
            if self.cofre is not None and self._app_sem_foco():
                if self._sem_foco_desde is None:
                    self._sem_foco_desde = agora
                elif agora - self._sem_foco_desde >= BLOQUEIO_SEM_FOCO_S:
                    self._sem_foco_desde = None
                    self._ultimo_tique = agora_parede
                    self.bloquear()
                    return
            else:
                self._sem_foco_desde = None
            if self.cofre is not None and (agora_parede - getattr(self, "_ultimo_tique", agora_parede) > 20 or sessao_bloqueada()):
                # pulo no relógio = o PC dormiu/hibernou; ou a sessão do Windows foi bloqueada
                self.bloquear()
            elif self.cofre is not None:
                suspeita = ambiente_suspeito()
                if suspeita:
                    self._invasao_em_andamento(suspeita)
                    return
                # a cada ~2 s (a lista de processos é lida em outra thread, sem travar a tela, por isso dá para
                # verificar a cada volta e não só de 4 em 4 segundos: fecha mais rápido a janela entre alguém abrir
                # um depurador/forense e o cofre perceber e se bloquear)
                espias = self._espias_res                # resultado da leitura anterior
                self._espias_res = None
                if self._espias_erro is not None:
                    ex, self._espias_erro = self._espias_erro, None
                    diag_registrar(DIAG_INTERFACE, ex)
                    self._invasao_em_andamento(
                        "Não foi possível verificar os programas abertos. O cofre foi fechado por segurança.",
                        titulo="Verificação de segurança indisponível")
                    return
                if self._espias_thread is None:
                    self._espias_thread = threading.Thread(target=self._monitorar_espias, daemon=True)
                    self._espias_thread.start()
                self._espias_pedido.set()
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
            except (AttributeError, OSError, ctypes.ArgumentError, TypeError):
                pass
        try:
            return self.root.focus_get() is None
        except (KeyError, tk.TclError):
            return False

    def _invasao_em_andamento(self, motivo, titulo="Depurador detectado"):
        """Depurador ligado ao cofre aberto: apaga as chaves da memória e fecha (sem destruir o arquivo)."""
        try:
            if self.cofre:
                self.cofre.fechar()
            self.cofre = None
            self._limpar_clip(forcar=True)
        except (AttributeError, OSError, RuntimeError, tk.TclError, ValueError) as ex:
            diag_registrar(DIAG_INTERFACE, ex)
        try:                       # chaves já apagadas da memória; o ARQUIVO é preservado (pode ser falso alarme)
            self.root.withdraw()
            messagebox.showerror(titulo,
                                 f"{motivo}\n\nO cofre foi fechado e as chaves apagadas da memória. "
                                 "O arquivo NÃO foi alterado. Se você não está depurando o programa, "
                                 "feche o programa que se anexou a ele (antivírus, ferramenta de captura) "
                                 "e abra o cofre de novo.")
        finally:
            self._parar_monitor_espias()
            self.root.destroy()

    OCULTAR_APOS_MS = 1500

    def _agendar_ocultar(self):
        """Agenda UMA checagem de foco (FocusOut dispara a cada troca de campo e quando uma notificação do Windows ou
        do antivírus pisca por cima). Só cobre a tela se o programa continuar sem foco depois de 1,5 s; assim a
        janela não 'pisca' preta a cada aviso passageiro."""
        if self._timer_ocultar is not None:
            return
        try:
            self._timer_ocultar = self.root.after(self.OCULTAR_APOS_MS, self._disparar_ocultar)
        except tk.TclError:
            self._timer_ocultar = None

    def _disparar_ocultar(self):
        """Fim da espera: libera o timer e cobre o conteúdo se o foco realmente se foi."""
        self._timer_ocultar = None
        self._talvez_ocultar()

    def _talvez_ocultar(self):
        """Cobre o conteúdo se o programa perdeu o foco (contra captura de tela e espiões)."""
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
        """Tira a capa de 'conteúdo oculto'."""
        for capa in self._ocultadores:
            try:
                capa.destroy()
            except tk.TclError:
                pass
        self._ocultadores = []

    def _oferecer_restauracao(self, motivo):
        """Oferece restaurar uma cópia de segurança quando o arquivo está danificado."""
        existe = any(os.path.exists(b) for b in _copias(self.caminho))
        if self.em_uso:                      # outra janela é a dona do arquivo: esta não troca nada nele
            messagebox.showerror("Arquivo do cofre danificado",
                                 f"{motivo}\n\nEste cofre está aberto em outra janela, então esta (só leitura) não "
                                 "restaura nada. Feche as duas janelas e abra o cofre de novo.")
            return
        if existe and messagebox.askyesno(
                "Arquivo do cofre danificado",
                f"{motivo}\n\nNada foi apagado e nenhuma tentativa foi gasta.\n\n"
                "Existe uma cópia de segurança automática. Restaurar a cópia mais recente agora?\n"
                "(O arquivo danificado fica guardado ao lado, como .danificado.)"):
            usada = restaurar_copia(self.caminho)
            if usada:
                self._restauracoes_tentadas = [usada]
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
    def _protecao_global(self):
        """Proteção extra (pedir a senha mestra de novo para ver/copiar) é uma única opção para TODO o cofre, não mais
        por item (era uma reclamação real: a caixinha "Item protegido" por item deixava o formulário poluído e
        confuso). Se o cofre ainda não tem a opção salva (cofre antigo, de antes desta mudança), herda o valor de
        quem já tinha ALGUM item marcado como protegido -- assim quem já usava a proteção continua protegido, em vez
        de a troca desligar a proteção de todo mundo silenciosamente."""
        g = self.cofre.meta.get("protecao_global")
        if g is None:
            return any(r.get("protegido") for r in self.cofre.registros)
        return bool(g)

    def _item_tem_dados_bancarios(self, r):
        """Verdadeiro se o item tem número da conta e/ou agência preenchidos."""
        return bool((r.get("numero_conta") or "").strip() or (r.get("agencia") or "").strip())

    def _liberar_protegido(self, r):
        """Com a proteção extra ligada (ajuste global), TODO item pede a senha mestra de novo (vale por 30 s).
        Dados bancários (número da conta / agência) SEMPRE pedem a senha mestra de novo para ser vistos, copiados
        ou editados -- mesmo com a proteção extra DESLIGADA para o resto do cofre: são sensíveis o bastante para
        merecer essa camada extra por padrão, sem depender do usuário ter ligado o ajuste geral."""
        if not r:
            return True
        bancario = self._item_tem_dados_bancarios(r)
        if not self._protecao_global() and not bancario:
            return True
        if time.time() - self._liberado_em.get(r.get("id"), 0.0) < 30:
            return True
        titulo = "Dados bancários protegidos" if bancario else "Item protegido"
        if self._confirmar_senha_atual(titulo):
            self._liberado_em[r.get("id")] = time.time()
            return True
        return False

    def configurar_protecao_extra(self):
        """Janela para ligar/desligar a proteção extra (pedir a senha mestra de novo para ver ou copiar) para TODO o
        cofre de uma vez -- substitui a antiga caixinha "Item protegido" que existia em cada item separadamente."""
        d = self._nova_janela("Proteção extra")
        self._modal(d)
        fr = ttk.Frame(d, padding=(26, 22, 26, 20))
        fr.pack(fill="both", expand=True)
        self._cabecalho_dialogo(fr, "cadeado", "Proteção extra",
                                "Com isto ligado, ver ou copiar a senha de QUALQUER item pede a senha mestra de novo "
                                "(a confirmação vale por 30 segundos).")
        var = tk.BooleanVar(value=self._protecao_global())
        ttk.Checkbutton(fr, text="Pedir a senha mestra de novo para ver ou copiar",
                        variable=var, style="Switch.TCheckbutton").pack(anchor="w", pady=(4, 0))
        ttk.Label(fr, text="Dados bancários (número da conta / agência) sempre pedem, mesmo com isto desligado.",
                  style="Fraco.TLabel").pack(anchor="w", pady=(6, 0))

        def salvar():
            """Grava a escolha dentro do cofre (numa transação)."""
            ligar = var.get()

            def mudar():
                """Guarda o ajuste global no cofre (dentro da transação)."""
                self.cofre.meta["protecao_global"] = ligar
            if self._transacao(mudar):
                d.destroy()
        ttk.Button(fr, text="Salvar", command=salvar, style="Primario.TButton").pack(anchor="e", pady=(16, 0))

    def _alerta_invasao(self):
        """Avisa, ao abrir, que houve tentativas erradas feitas por outra pessoa desde o último uso."""
        c = self.cofre
        if c is None:                      # o cofre pode ter sido bloqueado enquanto a janela de integridade estava aberta
            self._erros_sessao = 0
            return
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
        """Janela com o histórico cifrado de aberturas (data e tentativas erradas antes de cada uma)."""
        import datetime
        d = self._nova_janela("Histórico de aberturas")
        self._modal(d)
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

    # ---------- Diagnóstico, bloqueio por inatividade e número de tentativas ----------

    def ver_diagnostico(self):
        """Janela com o registro de diagnóstico: só códigos de falhas do sistema (gravação, leitura, integridade),
        guardados cifrados ao lado do cofre e legíveis apenas com o cofre aberto. Não mostra caminhos nem segredos."""
        import datetime
        try:
            priv = base64.b64decode(self.cofre.meta.get("diag_priv", ""), validate=True)
            res = diag_ler_completo(self.caminho, priv)
        except Exception:
            priv, res = None, None
        d = self._nova_janela("Diagnóstico")
        self._modal(d)
        fr = ttk.Frame(d, padding=(26, 22, 26, 20))
        fr.pack(fill="both", expand=True)
        self._cabecalho_dialogo(fr, "info", "Diagnóstico",
                                "Registro interno de falhas do sistema (gravação, leitura, integridade). Fica cifrado "
                                "ao lado do cofre e guarda só códigos e nomes de função: nunca senhas, caminhos ou conteúdo. Os 200 "
                                "mais recentes são mantidos.")
        tree = ttk.Treeview(fr, columns=("quando", "o_que", "erro", "onde"), show="headings", height=12)
        tree.heading("quando", text="Quando")
        tree.heading("o_que", text="O que aconteceu")
        tree.heading("erro", text="Tipo do erro")
        tree.heading("onde", text="Onde (função · linha · versão)")
        tree.column("quando", width=120)
        tree.column("o_que", width=270)
        tree.column("erro", width=110)
        tree.column("onde", width=240)
        n_ruins = 0
        regs_completos = []
        if res:
            regs_completos, n_ruins = res
            for minuto, cod, err, linha, ver, tipo, func, _cham in reversed(regs_completos):
                q = datetime.datetime.fromtimestamp(minuto * 60).strftime("%d/%m/%Y %H:%M")
                tree.insert("", "end", values=(q, diag_descrever(cod, err), tipo or "-",
                                               f"{func or '?'} · L{linha} · v{ver}"))
        tree.pack(fill="both", expand=True)
        detalhe = ttk.Label(fr, text="Clique numa linha para ver o detalhe do erro.", style="Fraco.TLabel",
                            wraplength=_px(640), justify="left")
        detalhe.pack(anchor="w", pady=(8, 0))

        def mostrar_detalhe(_e=None):
            """Explica por extenso o registro selecionado."""
            sel = tree.selection()
            if not sel:
                return
            minuto, cod, err, linha, ver, tipo, func, cham = list(reversed(regs_completos))[tree.index(sel[0])]
            detalhe.configure(text=f"{diag_descrever(cod, err)}. Tipo: {tipo or 'não informado'}. Parou na função "
                                   f"{func or '?'} (linha {linha})" + (f", chamada por {cham}" if cham else "")
                                   + f". Versão do programa: {ver}.")
        tree.bind("<<TreeviewSelect>>", mostrar_detalhe)
        if res is None:
            aviso = "Ainda não há registro (nenhuma falha anotada) ou ele pertence a outra versão deste cofre."
        elif n_ruins:
            aviso = f"{n_ruins} registro(s) não passaram na verificação (arquivo alterado ou cortado) e foram ignorados."
        else:
            aviso = "Nenhuma falha anotada." if not res[0] else "Registros verificados (autenticados)."
        ttk.Label(fr, text=aviso, style="Fraco.TLabel", wraplength=_px(640)).pack(anchor="w", pady=(10, 0))
        bt = ttk.Frame(fr)
        bt.pack(fill="x", pady=(12, 0))

        def limpar():
            """Esvazia o registro de diagnóstico depois de confirmar."""
            if priv is None or not messagebox.askyesno("Limpar diagnóstico", "Apagar todos os registros de diagnóstico?",
                                                       parent=d):
                return
            try:
                diag_limpar(self.caminho, priv)
            except OSError as ex:
                messagebox.showerror("Erro", texto_erro(ex), parent=d)
                return
            d.destroy()
        def copiar_relatorio():
            """Copia um texto sem segredos com todos os erros, para colar numa conversa de suporte."""
            if not regs_completos:
                messagebox.showinfo("Diagnóstico", "Não há erros anotados para copiar.", parent=d)
                return
            d.clipboard_clear()
            d.clipboard_append(diag_relatorio(regs_completos))
            detalhe.configure(text="Relatório copiado. Cole-o na conversa de suporte (não contém senhas nem caminhos).")
        ttk.Button(bt, text="Limpar registro", command=limpar).pack(side="left")
        ttk.Button(bt, text="Copiar relatório", command=copiar_relatorio).pack(side="left", padx=(8, 0))
        ttk.Button(bt, text="Fechar", command=d.destroy, style="Primario.TButton").pack(side="right")

    @staticmethod
    def _hash_proprio_programa():
        """SHA-256 (hex) do ARQUIVO do programa em execução, lido do disco agora mesmo. None se não for o programa
        compilado, ou se não der para ler. Isto é só informativo: não é uma prova de integridade (um programa já
        adulterado poderia simplesmente mentir sobre o próprio hash) -- serve para o usuário comparar à mão com o
        número que o instalador mostrou e pediu para ser anotado em papel. Por isso não existe mais nenhum arquivo
        .sha256 ao lado do .exe: um arquivo solto na mesma pasta pode ser troCADO junto com o programa, então não
        protegia contra ninguém que já tivesse acesso de escrita na pasta -- só o papel (fora do pendrive) protege."""
        if not COMPILADO:
            return None
        try:
            h = hashlib.sha256()
            with open(os.path.abspath(sys.argv[0]), "rb") as f:
                for bloco in iter(lambda: f.read(1 << 20), b""):
                    h.update(bloco)
            return h.hexdigest()
        except OSError:
            return None

    def verificar_integridade_cofre(self, automatica=False):
        """Tela "Verificar integridade do cofre": estado do arquivo principal e das cópias automáticas, mostrada
        assim que o cofre abre (automatica=True) e também no menu Segurança. Só lê; nunca grava nem altera nada."""
        if self.cofre is None:
            return
        C = CORES
        try:
            r = self.cofre.verificar_estado_arquivos()
        except Exception as ex:                      # a conferência nunca pode impedir o uso do cofre
            diag_registrar(DIAG_INTEGRIDADE, ex)
            r = None
        d = self._nova_janela("Verificar integridade do cofre")
        self._modal(d)
        fr = ttk.Frame(d, padding=(26, 22, 26, 20))
        fr.pack(fill="both", expand=True)
        linhas = []                                   # (símbolo, cor, texto)
        if r is None:
            nivel, resumo = "atencao", "Não foi possível conferir agora. Veja o Diagnóstico e tente de novo."
        else:
            sit, itens, seq, det = r["principal"]
            problema = sit in ("falha", "erro", "ausente") or r["reversao"] or any(
                c[1] == "falha" for c in r["copias"])
            if sit == "ok":
                linhas.append(("✔", C["ok"], f"Arquivo principal: íntegro  ({itens} item(ns), salvamento nº {seq})"))
            else:
                linhas.append(("✖", C["perigo"], "Arquivo principal: " + ("não encontrado" if sit == "ausente" else
                              "NÃO confere" + (f" — {det}" if det else ""))))
            boas = 0
            for i, (_nome, csit, citens, cseq, cdet) in enumerate(r["copias"], 1):
                rotulo = f"Cópia automática {i}" + (" (mais nova)" if i == 1 else "")
                if csit == "ok":
                    boas += 1
                    linhas.append(("✔", C["ok"], f"{rotulo}: íntegra  ({citens} item(ns), salvamento nº {cseq})"))
                elif csit == "ausente":
                    linhas.append(("•", C["fraco"], f"{rotulo}: ainda não existe"))
                elif csit == "antiga":
                    linhas.append(("•", C["fraco"], f"{rotulo}: formato antigo (não conferida)"))
                else:
                    linhas.append(("✖", C["perigo"], f"{rotulo}: DANIFICADA" + (f" — {cdet}" if cdet else "")))
            if r["reversao"]:
                linhas.append(("✖", C["perigo"], "Uma cópia automática é mais NOVA que o arquivo principal: ele pode "
                                                  "ter sido trocado por uma versão antiga. Confira seus itens mais recentes."))
            if r["sobras"]:
                linhas.append(("!", C["alerta"], "Há arquivo(s) danificado(s) guardado(s) ao lado do cofre: "
                               + ", ".join(r["sobras"])))
            if r["consulta"]:
                linhas.append(("!", C["alerta"], "Modo consulta: nada é gravado nesta sessão, então não são criadas cópias novas."))
            if problema:
                nivel, resumo = "problema", "PROBLEMA encontrado. Não altere nada ainda; veja abaixo."
                linhas.append(("!", C["alerta"], "Se preciso, restaure uma cópia automática ou o backup cifrado externo."))
            elif boas == 0 or r["sobras"] or r["consulta"]:
                nivel, resumo = "atencao", "Cofre íntegro, mas com ressalvas (veja abaixo)."
                if boas == 0:
                    linhas.append(("!", C["alerta"], "Nenhuma cópia automática legível ainda. Faça um backup cifrado externo em Backup do cofre."))
            else:
                nivel, resumo = "ok", "Cofre íntegro. Arquivo principal e cópias automáticas conferem."
        cor = {"ok": C["ok"], "atencao": C["alerta"], "problema": C["perigo"]}[nivel]
        self._cabecalho_dialogo(fr, "escudo", "Verificar integridade do cofre",
                                "Estado do arquivo do cofre antes de você usá-lo. Esta conferência só lê; não altera nada.")
        ttk.Label(fr, text=resumo, foreground=cor, wraplength=_px(640), justify="left").pack(anchor="w", pady=(4, 12))
        caixa = ttk.Frame(fr, style="Card2.TFrame", padding=(14, 12))
        caixa.pack(fill="x")
        for simbolo, cor_l, texto in linhas:
            linha = ttk.Frame(caixa, style="Card2.TFrame")
            linha.pack(fill="x", pady=2)
            ttk.Label(linha, text=simbolo, foreground=cor_l, style="S2.TLabel", width=2).pack(side="left", anchor="n")
            ttk.Label(linha, text=texto, style="S2.TLabel", wraplength=_px(600), justify="left").pack(side="left")
        bt = ttk.Frame(fr)
        bt.pack(fill="x", pady=(16, 0))
        ttk.Button(bt, text="Verificar o programa (.exe)…", command=self.verificar_integridade).pack(side="left")
        ttk.Button(bt, text="Fechar", command=d.destroy, style="Primario.TButton").pack(side="right")
        d.bind("<Escape>", lambda e: d.destroy())
        if automatica:
            self.root.wait_window(d)                  # o aviso de abertura só aparece depois de você ver o estado

    def verificar_integridade(self):
        """Mostra o SHA-256 do próprio programa (.exe), para comparar à mão com o número anotado em papel na
        instalação. Hoje não há mais nenhum arquivo separado (.bat ou .sha256) ao lado do programa: tudo o que é
        do software está dentro do próprio arquivo compilado, e não há nada "de fora" para mexer ou copiar."""
        d = self._nova_janela("Verificar integridade do programa")
        self._modal(d)
        fr = ttk.Frame(d, padding=(26, 22, 26, 20))
        fr.pack(fill="both", expand=True)
        self._cabecalho_dialogo(fr, "escudo", "Verificar integridade do programa",
                                "Compare o código abaixo com o SHA-256 que você anotou em PAPEL quando instalou o "
                                "cofre. Se forem diferentes, este programa foi substituído: não digite sua senha "
                                "mestra -- reinstale a partir do zero num computador de confiança.")
        try:
            caminho_exe = os.path.abspath(sys.argv[0])
        except Exception:
            caminho_exe = "?"
        ttk.Label(fr, text=caminho_exe, style="Fraco.TLabel", wraplength=_px(640)).pack(anchor="w")
        h = self._hash_proprio_programa()
        if h:
            caixa = tk.Text(fr, height=2, width=46, font=(FONTES["CofreMonoG"].cget("family"), 14), relief="flat",
                            bd=0, wrap="char", exportselection=True, cursor="arrow", padx=6, pady=6,
                            highlightthickness=0, bg=CORES["sup2"], fg=CORES["texto"],
                            insertbackground=CORES["sup2"], selectbackground=CORES["prim_fundo"])
            caixa.tag_configure("normal", justify="center", spacing1=2)
            grupos = [h[i:i + 8] for i in range(0, len(h), 8)]
            caixa.insert("end", "  ".join(grupos), "normal")
            caixa.config(state="disabled")
            caixa.pack(fill="x", pady=(14, 0))
        else:
            ttk.Label(fr, text="Não foi possível calcular agora (programa não compilado, ou sem permissão de "
                      "leitura do próprio arquivo).", style="Fraco.TLabel", wraplength=_px(640)).pack(anchor="w",
                      pady=(14, 0))
        aviso = ttk.Frame(fr, style="Card2.TFrame", padding=(14, 12))
        aviso.pack(fill="x", pady=(16, 0))
        linha_aviso = ttk.Frame(aviso, style="Card2.TFrame")
        linha_aviso.pack(fill="x")
        ttk.Label(linha_aviso, style="S2.TLabel", justify="left",
                  text="Conferência MANUAL: o programa não pode provar o próprio número sozinho.").pack(side="left")
        self._ajuda(linha_aviso, "Por que conferir à mão",
                     "Isto não é uma prova automática: um programa já adulterado poderia mentir sobre o próprio "
                     "número, então o cofre não confia nele sozinho (por isso não existe mais um arquivo .sha256 "
                     "'de fora' guardando o valor esperado -- quem troca o programa também trocaria esse arquivo). "
                     "A proteção real do CONTEÚDO do cofre é a cifra (Argon2id + ChaCha20-Poly1305/AES-256-GCM); a "
                     "do PROGRAMA contra troca é o BitLocker do pendrive e o número anotado em papel, fora do "
                     "computador.", CORES["fundo"]).pack(side="left", padx=(6, 0))
        ttk.Button(fr, text="Fechar", command=d.destroy, style="Primario.TButton").pack(anchor="e", pady=(16, 0))

    def _atividade(self, event=None):
        """Registra que o usuário mexeu no programa (reinicia o relógio de inatividade)."""
        if self.cofre is None:
            return
        agora = time.monotonic()
        if event is not None and self._timer_bloqueio and agora - getattr(self, "_ultima_atividade", 0) < 1.0:
            return                      # o mouse mexe dezenas de vezes por segundo: basta renovar 1x por segundo
        self._ultima_atividade = agora
        if self._timer_bloqueio:
            self.root.after_cancel(self._timer_bloqueio)
        self._timer_bloqueio = self.root.after(self._inatividade_ms(), self.bloquear)
        self._rearmar_aviso_bloqueio()

    AVISO_BLOQUEIO_MS = 15000

    def _inatividade_ms(self):
        """Tempo sem uso até bloquear: o escolhido pelo usuário (guardado, cifrado, dentro do cofre) ou o padrão."""
        try:
            m = int(self.cofre.meta.get("bloqueio_min", 0))
        except (AttributeError, TypeError, ValueError):
            m = 0
        return m * 60000 if 1 <= m <= 30 else self.INATIVIDADE_MS

    def configurar_bloqueio(self):
        """Janela para escolher após quantos minutos sem uso o cofre se tranca sozinho e apaga as chaves da memória."""
        d = self._nova_janela("Bloqueio automático")
        self._modal(d)
        fr = ttk.Frame(d, padding=(26, 22, 26, 20))
        fr.pack(fill="both", expand=True)
        self._cabecalho_dialogo(fr, "cadeado", "Bloqueio automático",
                                "O cofre se tranca sozinho e apaga as chaves da memória depois deste tempo sem uso.")
        var = tk.StringVar(value=str(self._inatividade_ms() // 60000))
        linha = ttk.Frame(fr)
        linha.pack(fill="x")
        ttk.Label(linha, text="Bloquear após").pack(side="left")
        ttk.Combobox(linha, textvariable=var, values=[str(m) for m in self.INATIVIDADE_OPCOES],
                     state="readonly", width=5).pack(side="left", padx=8)
        ttk.Label(linha, text="minuto(s) sem uso").pack(side="left")
        ttk.Label(linha, text="").pack(side="left", padx=2)
        self._ajuda(linha, "Bloqueio automático", "Menos tempo é mais seguro. Ao perder o foco por alguns segundos, "
                    "o conteúdo também é coberto.", CORES["fundo"]).pack(side="left")

        def salvar():
            """Grava a escolha dentro do cofre (numa transação) e reinicia o relógio de inatividade."""
            n = int(var.get())

            def mudar():
                """Guarda o tempo escolhido no cofre (dentro da transação)."""
                self.cofre.meta["bloqueio_min"] = n
            if self._transacao(mudar):
                d.destroy()
                self._atividade()
                self._atualizar_indicadores()
        ttk.Button(fr, text="Salvar", command=salvar, style="Primario.TButton").pack(anchor="e", pady=(16, 0))

    def configurar_tentativas(self):
        """Dentro do cofre: quantos erros seguidos de senha antes da autodestruição (1 a 10). Pede a senha mestra e
        grava no cabeçalho do cofre; backups antigos continuam com o limite antigo."""
        if self.cofre is None:
            return
        d = self._nova_janela("Tentativas erradas")
        self._modal(d)
        fr = ttk.Frame(d, padding=(26, 22, 26, 20))
        fr.pack(fill="both", expand=True)
        self._cabecalho_dialogo(fr, "cadeado", "Tentativas erradas",
                                "Depois deste número de erros seguidos, o cofre é apagado para sempre.")
        valor = tk.IntVar(value=int(self.cofre.max_t))
        linha = ttk.Frame(fr)
        linha.pack(pady=(4, 0))
        rot = ttk.Label(linha, textvariable=valor, font="CofreTitulo", width=3, anchor="center")

        def passo(delta):
            """Sobe ou desce o número (de 1 a 10)."""
            valor.set(max(1, min(10, valor.get() + delta)))
        ttk.Button(linha, text="−", width=3, command=lambda: passo(-1), style="Acao.TButton").pack(side="left")
        rot.pack(side="left", padx=12)
        ttk.Button(linha, text="+", width=3, command=lambda: passo(1), style="Acao.TButton").pack(side="left")
        self._ajuda(linha, "Tentativas erradas", "Só contam erros de senha ou chave. Abrir e fechar o programa não gasta "
                    "nenhuma e, ao acertar, o contador volta ao máximo. Com 1, UM erro de digitação apaga o cofre: "
                    "tenha sempre um backup.", CORES["fundo"]).pack(side="left", padx=(14, 0))

        def salvar():
            """Pede a senha mestra e grava o novo limite no cofre."""
            n = valor.get()
            if n == self.cofre.max_t:
                d.destroy()
                return
            if n == 1 and not messagebox.askyesno(
                    "Confirmar", "Com 1 tentativa, UM erro de digitação apaga o cofre para sempre.\n"
                                 "Tenha um backup atualizado. Continuar?", parent=d, perigoso=True):
                return
            if not self._confirmar_senha_atual("Tentativas erradas"):
                return
            antes = self.cofre.max_t
            self.cofre.max_t = n
            if self._transacao(lambda: None):
                d.destroy()
                messagebox.showinfo("Tentativas erradas", f"Pronto: o cofre apaga após {n} erro(s) seguido(s).\n\n"
                                    "Backups e cópias antigas continuam com o limite antigo.")
            else:
                self.cofre.max_t = antes
        ttk.Button(fr, text="Salvar", command=salvar, style="Primario.TButton").pack(anchor="e", pady=(16, 0))

    def _fechar_aviso_bloqueio(self):
        """Fecha o aviso flutuante de bloqueio iminente."""
        t = getattr(self, "_timer_av_bloq", None)
        if t:
            try:
                self.root.after_cancel(t)
            except (tk.TclError, ValueError):
                pass
        self._timer_av_bloq = None
        j = getattr(self, "_janela_av_bloq", None)
        if j is not None:
            try:
                j.destroy()
            except (tk.TclError, ValueError):
                pass
        self._janela_av_bloq = None

    def _rearmar_aviso_bloqueio(self):
        """Avisa 15 s antes de bloquear (edição aberta seria perdida). Qualquer clique/tecla cancela."""
        self._fechar_aviso_bloqueio()
        if self._inatividade_ms() <= self.AVISO_BLOQUEIO_MS:
            return
        self._timer_av_bloq = self.root.after(self._inatividade_ms() - self.AVISO_BLOQUEIO_MS,
                                              self._mostrar_aviso_bloqueio)

    def _mostrar_aviso_bloqueio(self):
        """Mostra o aviso flutuante (protegido contra captura de tela) de que o cofre está prestes a bloquear."""
        self._timer_av_bloq = None
        if self.cofre is None:
            return
        try:
            j = tk.Toplevel(self.root)
            j.overrideredirect(True)
            j.attributes("-topmost", True)
            j.configure(bg=CORES["alerta"])
            rot = tk.Label(j, bg=CORES["alerta"], fg=_texto_contraste(CORES["alerta"]), padx=18, pady=10,
                           font="CofreForte")
            rot.pack()
            self._janela_av_bloq = j
            proteger_contra_captura(j)
            j.update_idletasks()
            x = self.root.winfo_rootx() + self.root.winfo_width() - j.winfo_reqwidth() - 24
            y = self.root.winfo_rooty() + self.root.winfo_height() - j.winfo_reqheight() - 40
            j.geometry(f"+{max(0, x)}+{max(0, y)}")
            for w in (j, rot):
                w.bind("<Button-1>", lambda e: self._atividade())
            restante = {"s": self.AVISO_BLOQUEIO_MS // 1000}

            def tique():
                """Atualiza a contagem regressiva do aviso e bloqueia ao chegar a zero."""
                if self._janela_av_bloq is not j or self.cofre is None:
                    return
                rot.config(text=f"Bloqueando em {restante['s']} s — clique ou mexa no teclado para continuar")
                restante["s"] -= 1
                if restante["s"] >= 0:
                    self._timer_av_bloq = self.root.after(1000, tique)
            tique()
        except tk.TclError:
            self._janela_av_bloq = None

    def _ao_minimizar(self, event=None):
        """Bloqueia o cofre quando a janela é minimizada."""
        if event is not None and event.widget is not self.root:
            return
        try:
            if self.root.state() == "iconic" and self.cofre is not None:
                self.bloquear()
        except tk.TclError:
            pass

    # ---------- Utilitários genéricos de janela e diálogo ----------

    def _nova_janela(self, titulo, mestre=None):
        """Cria uma janela de diálogo no tema do programa, protegida contra captura de tela."""
        d = tk.Toplevel(mestre or self.root)
        d.withdraw()                      # fica escondida enquanto o conteúdo é montado (não aparece "se construindo")
        d.title(titulo)
        d.transient(mestre or self.root)
        d.resizable(False, False)
        d.configure(bg=CORES["fundo"])
        d.update_idletasks()
        proteger_contra_captura(d)
        barra_titulo_escura(d)
        d.bind("<Map>", lambda e=None: proteger_contra_captura(d) if e is None or e.widget is d else None, add="+")
        d.after(0, lambda: self._revelar_dialogo(d))
        return d

    def _revelar_dialogo(self, d):
        """Mostra o diálogo já montado e centralizado, de uma vez. Se alguém pediu o 'grab' (modal) enquanto ele
        estava escondido, faz agora."""
        try:
            if not d.winfo_exists() or d.state() != "withdrawn":
                return
            d.update_idletasks()
            preparar = getattr(d, "_preparar_corpo", None)
            if preparar is not None:
                preparar()                 # tamanho final decidido ANTES de aparecer
            self._centralizar(d)
            anterior_teste = _primeiro_plano_de_teste()   # so em teste
            d.deiconify()
            d.update_idletasks()
            _reforcar_segundo_plano_de_teste(d, anterior_teste)   # so em teste: dialogo nao rouba o foco
            if getattr(d, "_quer_grab", False):
                _grab_seguro(d)
        except tk.TclError:
            pass

    def _depois_do_widget(self, widget, ms, funcao):
        """after() ligado à vida do widget: se ele for destruído antes da hora, o timer é cancelado
        (senão o Tcl reclama de 'invalid command name' depois que a janela fecha)."""
        r = {"id": None}

        def rodar():
            """Executa a função agendada."""
            r["id"] = None
            try:
                if widget.winfo_exists():
                    funcao()
            except tk.TclError:
                pass

        def cancelar(e=None):
            """Cancela o agendamento se o widget foi destruído."""
            if e is not None and e.widget is not widget:
                return
            if r["id"]:
                try:
                    widget.after_cancel(r["id"])
                except (AttributeError, tk.TclError, ValueError):
                    pass
                r["id"] = None
        r["id"] = widget.after(ms, rodar)
        widget.bind("<Destroy>", cancelar, add="+")
        return r["id"]

    @staticmethod
    def _modal(d):
        """Torna a janela modal. Em máquinas lentas o grab falha se a janela ainda não apareceu:
        espera (no máximo 2 s) ficar visível e nunca levanta TclError."""
        _grab_seguro(d)

    @staticmethod
    def _unidade(caminho):
        """Letra da unidade (C:, H:...) de um caminho."""
        return os.path.splitdrive(os.path.abspath(caminho))[0].upper()

    def _no_disco_do_windows(self, caminho):
        """O cofre, as chaves e os backups nunca deveriam ficar no disco do Windows (C:)."""
        return EH_WINDOWS and self._unidade(caminho) == os.environ.get("SystemDrive", "C:").upper()

    def _confirmar_destino(self, destino, oque, pai=None):
        """Pergunta antes de gravar algo no disco do Windows em vez do pendrive."""
        if self._no_disco_do_windows(destino):
            return messagebox.askyesno(
                "Salvar no disco do Windows?",
                f"Você escolheu salvar {oque} no disco do Windows ({self._unidade(destino)}).\n\n"
                "O recomendado é um pendrive. Salvar no disco do Windows mesmo assim?", parent=pai, perigoso=True)
        return True

    def _corpo_dialogo(self, d, padding, rodape=None):
        """Mantém o rodapé visível e só permite rolagem vertical quando o corpo não cabe na tela."""
        area = ttk.Frame(d)
        area.pack(fill="both", expand=True)
        canvas = tk.Canvas(area, bg=CORES["fundo"], highlightthickness=0, bd=0)
        barra = ttk.Scrollbar(area, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=barra.set)
        fr = ttk.Frame(canvas, padding=padding)
        janela = canvas.create_window((0, 0), window=fr, anchor="nw")
        canvas.pack(side="left", fill="both", expand=True)
        estado = {"pos": False, "pendente": None, "aplicado": None, "rolagem": False, "lmax": 0, "amax": 0}

        def ajustar_largura(event):
            canvas.itemconfigure(janela, width=event.width)

        def aplicar():
            """Dimensiona o corpo e ativa rolagem apenas se a altura disponível for insuficiente."""
            estado["pendente"] = None
            try:
                d.update_idletasks()
                w = fr.winfo_reqwidth()
                h = fr.winfo_reqheight()
                reserva = rodape.winfo_reqheight() if rodape is not None else 0
                sw, sh = d.winfo_screenwidth(), d.winfo_screenheight()
                if rodape is not None:
                    w = max(w, rodape.winfo_reqwidth())
                largura = min(max(w, _px(860)), max(_px(640), sw - _px(48)))
                piso = getattr(d, "_altura_padrao", None) or _px(520)
                altura = min(max(h + reserva, piso), max(_px(420), sh - _px(64)))
                # O dialogo so CRESCE (nunca encolhe) enquanto aberto: abrir/fechar "detalhes" ou trocar de opcao
                # nao faz a janela ficar mudando de tamanho e de posicao.
                largura = max(largura, estado["lmax"])
                altura = max(altura, estado["amax"])
                estado["lmax"], estado["amax"] = largura, altura
                corpo_altura = max(1, altura - reserva)
                rolagem = h > corpo_altura
                if rolagem != estado["rolagem"]:
                    if rolagem:
                        barra.pack(side="right", fill="y")
                    else:
                        barra.pack_forget()
                    estado["rolagem"] = rolagem
                    d.update_idletasks()
                canvas.configure(height=corpo_altura, scrollregion=canvas.bbox("all"))
                dimensoes = (largura, altura, rolagem)
                if dimensoes == estado["aplicado"]:
                    return
                estado["aplicado"] = dimensoes
                d.geometry(f"{largura}x{altura}")
                d.update_idletasks()
                canvas.configure(scrollregion=canvas.bbox("all"))
                if not estado["pos"]:
                    estado["pos"] = True
                    d.after_idle(lambda: self._centralizar(d))
            except tk.TclError:
                pass

        def configurar_corpo(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            ajustar()

        def ajustar(event=None):
            """Agrupa as mudanças de tamanho do conteúdo para evitar redimensionamentos repetidos."""
            if estado["pendente"] is not None:
                try:
                    d.after_cancel(estado["pendente"])
                except (tk.TclError, ValueError):
                    pass
            try:
                estado["pendente"] = d.after(30, aplicar)
            except tk.TclError:
                pass

        canvas.bind("<Configure>", ajustar_largura, add="+")
        fr.bind("<Configure>", configurar_corpo, add="+")
        if rodape is not None:
            rodape.bind("<Configure>", ajustar, add="+")

        def preparar():
            """Mede o conteúdo antes de mostrar o diálogo."""
            if estado["pendente"] is not None:
                try:
                    d.after_cancel(estado["pendente"])
                except (tk.TclError, ValueError):
                    pass
                estado["pendente"] = None
            estado["aplicado"] = None
            aplicar()
            d.update_idletasks()
        d._preparar_corpo = preparar
        return fr

    def _centralizar(self, d):
        """Centraliza o diálogo sobre a janela principal, sem deixar sair da tela."""
        try:
            d.update_idletasks()
            visivel = d.winfo_viewable()
            if visivel:
                w, h = d.winfo_width(), d.winfo_height()
            else:                          # ainda escondida: o tamanho "real" é o pedido pelo conteúdo
                w, h = d.winfo_reqwidth(), d.winfo_reqheight()
            sw, sh = d.winfo_screenwidth(), d.winfo_screenheight()
            r = self.root
            x = r.winfo_rootx() + (r.winfo_width() - w) // 2
            y = r.winfo_rooty() + (r.winfo_height() - h) // 2
            x = max(0, min(x, sw - w))
            y = max(0, min(y, sh - h - _px(48)))
            d.geometry(f"+{x}+{y}" if visivel else f"{w}x{h}+{x}+{y}")
        except tk.TclError:
            pass

    def _recalcular_dialogo(self, d):
        """Ajusta o tamanho e a posição do diálogo depois que seu conteúdo muda."""
        d.update_idletasks()
        preparar = getattr(d, "_preparar_corpo", None)
        if callable(preparar):
            preparar()
        self._centralizar(d)

    @staticmethod
    def _bloquear_copia(widget):
        """Impede COPIAR e RECORTAR o conteúdo do campo (atalhos e eventos virtuais).
        Selecionar continua livre (arrastar, duplo/triplo clique, Ctrl+A), para poder apagar."""
        for seq in ("<Control-c>", "<Control-C>", "<Control-x>", "<Control-X>",
                    "<Control-Insert>", "<Shift-Delete>", "<<Copy>>", "<<Cut>>"):
            widget.bind(seq, lambda e: "break")

        def selecionar_tudo(e):
            """Seleciona todo o texto do campo (Ctrl+A)."""
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

    # ---------- Salvar, desfazer e área de transferência protegida ----------

    def _selecionado(self):
        """Item selecionado na lista (ou None); avisa se não há seleção."""
        if not hasattr(self, "tree") or self.cofre is None:
            return None
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Cofre", "Selecione um item da lista.")
            return None
        for r in self.cofre.registros:
            if r["id"] == sel[0]:
                return r
        return None

    def _salvar(self, forcar_copia=False):
        """Salva o cofre e mostra erro claro se falhar."""
        try:
            self.cofre.salvar(forcar_copia=forcar_copia)
            return True
        except OSError as ex:
            messagebox.showerror("Erro ao salvar", f"Não foi possível gravar o cofre:\n{texto_erro(ex)}")
            return False

    def _transacao(self, mudar, forcar_copia=False):
        """Roda 'mudar()' dentro de Cofre.transacao(); True se gravou, False (com aviso) se desfez."""
        try:
            with self.cofre.transacao(forcar_copia=forcar_copia):
                mudar()
            return True
        except OSError as ex:
            messagebox.showerror("Erro ao salvar", f"Não foi possível gravar o cofre:\n{texto_erro(ex)}")
            return False

    def _copiar_texto(self, valor, descricao):
        """Copia para a área de transferência de forma protegida e agenda a limpeza.
        No Windows tenta a cópia fora do histórico (Win+V). Se o Windows recusar e o histórico estiver DESLIGADO,
        copia pelo Tk (a senha não fica guardada em lugar nenhum); com o histórico ligado, recusa."""
        ok = False
        aviso = ""
        if EH_WINDOWS:
            try:
                dono_alt = int(_u32.GetAncestor(self.root.winfo_id(), 2) or 0) or None
            except Exception:
                dono_alt = None
            ok = copiar_seguro_windows(valor, dono_alt)
            if not ok:
                if historico_clipboard_ligado():    # sem as marcas de exclusão a senha iria para o Win+V / nuvem
                    return False, (f"NÃO copiado ({descricao}): o Windows recusou a cópia protegida "
                                   f"[{_ERRO_CLIP[0] or 'sem detalhe'}] e o histórico Win+V está ligado. "
                                   "Use o olho para ver o valor e digite.")
                aviso = " (cópia comum; o histórico Win+V está desligado)"
        if not ok:
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(valor)
                self.root.update_idletasks()
            except tk.TclError:
                return False, f"NÃO copiado ({descricao}): a área de transferência não respondeu. Tente de novo."
        self._clip_valor = valor
        self._clip_seq = sequencia_clipboard() if (EH_WINDOWS or ok) else None
        if self._timer_clip:
            self.root.after_cancel(self._timer_clip)
        self._timer_clip = self.root.after(self.LIMPAR_CLIPBOARD_MS, self._limpar_clip)
        extra = " (fora do histórico Win+V)" if ok else aviso
        return True, (f"Copiado: {descricao}{extra}. A área de transferência será limpa em "
                      f"{self.LIMPAR_CLIPBOARD_MS // 1000} s.")

    def _limpar_clip(self, forcar=False):
        """Limpa a área de transferência (só se o conteúdo ainda for o que o cofre copiou)."""
        self._timer_clip = None
        valor, self._clip_valor = self._clip_valor, None
        seq, self._clip_seq = getattr(self, "_clip_seq", None), None
        try:
            atual = self.root.clipboard_get()
        except tk.TclError:
            atual = None
        # Se ninguém mexeu na área de transferência desde a nossa cópia (número de sequência do Windows igual),
        # o conteúdo ainda é a senha, mesmo que o Tk não consiga lê-lo: apaga assim mesmo.
        ainda_nosso = valor is not None and seq is not None and sequencia_clipboard() == seq
        if forcar or ainda_nosso or (valor is not None and atual == valor):
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
        zerar_objeto(valor)          # a cópia Python do que foi copiado (senha/nota) não precisa mais ficar na RAM
        zerar_objeto(atual)          # idem para a cópia lida de volta da área de transferência, se houver

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
            """Insere no campo a tecla clicada e, se o embaralhamento estiver ligado, troca as teclas de lugar."""
            try:
                alvo.insert("end", ch)
                alvo.event_generate("<<Atualizar>>")
            except tk.TclError:
                d.destroy()
                return
            conta.config(text=f"{len(alvo.get())} caracteres digitados")
            if embaralhar_sempre.get():
                montar()

        def montar():
            """Embaralha as teclas SEM recriá-las: as mesmas 80 teclas só trocam de letra. (Antes cada clique destruía e
            recriava todas, o que piscava, atrasava e perdia o efeito de 'apertar' da tecla.)"""
            chars = [c.upper() if estado["maiusc"] else c for c in letras] + outros
            rnd.shuffle(chars)
            if not botoes:                                        # só na primeira vez: cria as teclas
                for i in range(len(chars)):
                    b = tk.Button(grade, text="", width=3, font="CofreMono", takefocus=0, relief="flat", bd=0,
                                  bg=CORES["sup2"], fg=CORES["texto"], activebackground=CORES["prim"],
                                  activeforeground="#ffffff", highlightthickness=1,
                                  highlightbackground=CORES["borda2"], padx=4, pady=6, cursor="hand2")
                    b.grid(row=i // 13, column=i % 13, padx=2, pady=2)
                    botoes.append(b)
            for b, ch in zip(botoes, chars, strict=False):
                b.config(text=ch, command=lambda c=ch: digitar(c))

        def maiusc():
            """Alterna maiúsculas no teclado virtual."""
            estado["maiusc"] = not estado["maiusc"]
            bt_m.config(text="abc" if estado["maiusc"] else "ABC")
            montar()

        def apagar():
            """Apaga o último caractere do campo."""
            try:
                n = len(alvo.get())
                if n:
                    alvo.delete(n - 1, "end")
                    alvo.event_generate("<<Atualizar>>")
                conta.config(text=f"{len(alvo.get())} caracteres digitados")
            except tk.TclError:
                d.destroy()

        conta = ttk.Label(d, text="0 caracteres digitados", style="Fraco.TLabel")
        conta.pack(anchor="w", padx=18)
        rod = ttk.Frame(d, padding=(16, 6, 16, 14))
        rod.pack(fill="x")
        d.bind("<Escape>", lambda e: d.destroy())
        bt_m = ttk.Button(rod, text="ABC", width=6, command=maiusc, takefocus=0)
        bt_m.pack(side="left")
        ttk.Button(rod, text="Espaço", width=14, command=lambda: digitar(" "), takefocus=0).pack(side="left", padx=4)
        ttk.Button(rod, text="⌫ Apagar", command=apagar, takefocus=0).pack(side="left")
        ttk.Checkbutton(rod, text="Embaralhar a cada tecla", variable=embaralhar_sempre, style="Switch.TCheckbutton",
                        takefocus=0).pack(side="left", padx=12)
        ttk.Button(rod, text="Concluir", command=d.destroy, takefocus=0, style="Primario.TButton").pack(side="right")
        try:
            conta.config(text=f"{len(alvo.get())} caracteres digitados")
        except tk.TclError:
            pass
        montar()

    # ---------- Chave de acesso e montagem da tela principal ----------

    def _pedir_senha(self, titulo, texto, medidor=False):
        """Diálogo de senha protegido (substitui o simpledialog, que não tem proteção).
        Com medidor=True mostra, em tempo real, a avaliação da força e do tempo para quebrar a senha."""
        d = self._nova_janela(titulo)
        self._modal(d)
        resultado = {"v": None}
        fr = ttk.Frame(d, padding=(26, 22, 26, 20))
        fr.pack()
        self._cabecalho_dialogo(fr, "cadeado", titulo, texto)
        linha, e = self._linha_secreta(fr, 36, placeholder="Senha mestra")
        linha.pack(fill="x")
        if medidor:
            painel_forca = PainelForca(fr, self, largura=_px(420))
            painel_forca.pack(fill="x", pady=(10, 0))
            self._medidor(fr, e, dicas_lbl=painel_forca).pack(anchor="w", pady=(6, 0))

        def ok(event=None):
            """Confirma a senha digitada."""
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
        """Mostra a chave de acesso recém-gerada (só aparece agora) com opção de copiar, salvar em arquivo e imprimir
        (a chave de acesso e o código de recuperação são as ÚNICAS coisas que o cofre imprime)."""
        d = self._nova_janela("Sua chave de acesso")
        self._modal(d)
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
        ttk.Label(caixa_av, text="Aparece só agora: guarde-a antes de fechar.", foreground=CORES["alerta"],
                  justify="left", style="S2.TLabel", wraplength=_px(440)).pack(side="left", anchor="w")
        self._ajuda(caixa_av, "Guarde a chave", aviso, CORES["alerta"]).pack(side="right")
        var = tk.StringVar(value=chave_txt)
        ent = ttk.Entry(fr, textvariable=var, width=40, font="CofreMonoG",
                        state="readonly", exportselection=False)
        self._bloquear_copia(ent)
        ent.pack(fill="x")
        msg = ttk.Label(fr, text="", foreground=CORES["suave"])
        msg.pack(anchor="w", pady=(6, 0))

        def copiar():
            """Copia a chave de acesso."""
            msg.config(text=self._copiar_texto(chave_txt, "Chave")[1])

        def salvar_arquivo():
            """Salva a chave de acesso num arquivo .key (de preferência em outro pendrive)."""
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
                                           "Salvar aqui mesmo assim?", parent=d, perigoso=True):
                    return
            try:
                c_ = self.cofre
                selado = selar_chave_acesso(chave_txt, c_.sal_k, c_.nonce_k, c_.wrap_k)   # cifrado: só este cofre lê
                with open(destino, "wb") as f:
                    f.write(selado)
                    f.flush()
                    os.fsync(f.fileno())
                msg.config(text="Arquivo de chave protegido salvo. Só este cofre consegue lê-lo.")
            except OSError as ex:
                messagebox.showerror("Erro", f"Não foi possível salvar:\n{texto_erro(ex)}", parent=d)

        bt = ttk.Frame(fr)
        bt.pack(fill="x", pady=(14, 0))
        C = CORES
        ttk.Button(bt, text="Copiar", command=copiar, image=imagem_icone(self.root, "copiar", C["texto"]),
                   compound="left").pack(side="left")
        ttk.Button(bt, text="Salvar arquivo protegido (.key)", command=salvar_arquivo,
                   image=imagem_icone(self.root, "backup", C["texto"]), compound="left").pack(side="left", padx=8)
        def imprimir_chave():
            """Imprime SÓ a chave de acesso (cópia de emergência; pede a senha mestra), direto na impressora."""
            self._imprimir("ARCA — CHAVE DE ACESSO", [("Chave de acesso", chave_txt)], mestre=d)

        ttk.Button(bt, text="Imprimir só a chave…", command=imprimir_chave,
                   image=imagem_icone(self.root, "imprimir", C["texto"]), compound="left").pack(side="left")
        lp_ = ttk.Frame(fr)
        lp_.pack(anchor="w", pady=(8, 0))
        ttk.Label(lp_, text="Impressão bloqueada para senhas; liberada só para esta cópia de emergência "
                  "(pede a senha mestra).", style="C.Fraco.TLabel", wraplength=_px(470), justify="left").pack(side="left")
        self._ajuda(lp_, "Sobre imprimir", "O cofre só imprime a chave de acesso e o código de recuperação (senhas, "
                    "itens, backups e a senha mestra nunca são impressos) e pede a senha mestra antes."
                    "\n\nO Windows guarda o que você imprime "
                    "na fila de impressão (uma pasta no disco C:) até o fim do trabalho, e impressoras de rede mandam "
                    "o conteúdo pela rede: use uma impressora USB sua, pegue a folha na hora e guarde em local seguro. "
                    "Anotar à mão continua sendo a forma mais segura.", CORES["fundo"]).pack(side="left")
        ttk.Button(bt, text="Já guardei a chave", command=d.destroy, style="Primario.TButton").pack(
            side="right", padx=(16, 0))
        self.root.wait_window(d)
        self._limpar_clip(forcar=True)

    # ---------- telas ----------
    def mostrar_inicio(self):
        """Mostra a tela inicial: criar o cofre ou desbloquear o existente."""
        if os.path.exists(self.caminho):
            self.tela_desbloqueio()
        else:
            self.tela_criar()

    # ---------- tela principal: grupos | contas | detalhes ----------
    @sem_piscar
    def tela_principal(self):
        """Tela principal: lista de itens com busca e filtros por grupo/pessoa, painel de detalhes e barra de ações."""
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
        if self.cofre is not None and self.cofre.somente_leitura:
            motivo = ("este cofre está aberto em OUTRA janela" if self.cofre.motivo_consulta == "em_uso"
                      else "pendrive protegido contra gravação")
            tk.Label(f, text=f"MODO CONSULTA: {motivo}. Você pode ver e copiar, mas nada "
                             "será salvo nesta sessão.", bg=C["alerta"], fg=_texto_contraste(C["alerta"]), font="CofreSub",
                     wraplength=_px(900), justify="center", pady=_px(4)).pack(fill="x", before=cab)
        if self.cofre is not None and self.cofre.alerta_reversao:
            tk.Label(f, text="ATENÇÃO: este cofre abriu num estado MAIS ANTIGO que uma cópia de segurança dele. Se você "
                             "não restaurou uma cópia de propósito, o arquivo pode ter sido trocado por uma versão velha: "
                             "confira se os itens e senhas mais recentes estão aqui.", bg=C["perigo"],
                     fg=_texto_contraste(C["perigo"]),
                     font="CofreSub", wraplength=_px(900), justify="center", pady=_px(4)).pack(fill="x", before=cab)
            if not getattr(self, "_reversao_avisada", False):
                self._reversao_avisada = True
                self.root.after(300, lambda: messagebox.showwarning(
                    "Possível reversão do cofre",
                    "Este cofre abriu num estado MAIS ANTIGO que uma cópia de segurança dele.\n\n"
                    "Se você restaurou uma cópia de propósito, é normal. Se não, alguém (ou algum programa) pode ter "
                    "trocado o arquivo por uma versão velha: confira se os itens e senhas mais recentes estão aqui e, "
                    "se faltar algo, use a cópia .bak mais nova (ou o seu backup externo)."))
        self._img_marca = desenhar_marca(30).imagem(self.root)
        tk.Label(cab, image=self._img_marca, bg=C["fundo"]).pack(side="left", padx=(20, 10))
        marca_texto = tk.Frame(cab, bg=C["fundo"])
        marca_texto.pack(side="left")
        tk.Label(marca_texto, text=_NOME_APP, bg=C["fundo"], fg=C["texto"],
                 font="CofreSub").pack(anchor="w")
        tk.Label(marca_texto, text=_NOME_EMPRESA.upper(), bg=C["fundo"], fg=C["fraco"],
                 font="CofreTexto").pack(anchor="w")

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
            """Mostra o texto de dica da busca só enquanto o campo está vazio."""
            try:
                if self.busca.get():
                    dica_busca.place_forget()
                else:
                    dica_busca.place(x=_px(36), rely=0.5, anchor="w")
            except tk.TclError:
                pass
        self.busca.trace_add("write", dica_visivel)
        dica_visivel()
        self.busca.trace_add("write", lambda *a: self._agendar_busca())

        def bt(texto, icone, cmd, estilo="Fantasma.TButton", cor=None, dica=None):
            """Cria um botão da barra de ações (texto, ícone, comando)."""
            b = ttk.Button(cab, text=texto, image=imagem_icone(self.root, icone, cor or C["suave"], 16),
                           compound="left" if texto else "image", style=estilo, command=cmd)
            b.pack(side="right", padx=(0, 6))
            if dica:
                self._dica(b, dica)
            return b
        tk.Frame(cab, bg=C["fundo"], width=14).pack(side="right")
        b_ajuda = ttk.Button(cab, text="?", width=3, style="TButton",
                             command=lambda: MenuTema(self, [
                                 ("Passeio guiado desta tela", "info", self.passeio_principal),
                                 ("Guia de uso e atalhos", "teclado", self._mostrar_atalhos)]).abrir(b_ajuda))
        b_ajuda.pack(side="right", padx=(0, 6))
        self._btn_ajuda = b_ajuda
        self._dica(b_ajuda, "Ajuda: passeio guiado e guia de uso")
        self._btn_bloquear = bt("Bloquear", "cadeado", self.bloquear, "TButton", C["texto"], "Trancar o cofre agora (Ctrl+L)")
        self._menu_mais = MenuTema(self, [
            "Uso geral",
            ("Aparência e cores…", "config", self.dialogo_aparencia),
            ("Importar planilha (Excel / CSV)…", "importar", self.importar),
            ("Baixar modelo de planilha…", "documento", self.modelo_planilha),
            ("Gerador e teste de senhas…  (Ctrl+G)", "gerar", lambda: self.dialogo_gerador()),
            ("Verificar senhas (força e repetidas)…", "verificar", self.verificar_senhas),
            ("Histórico de aberturas…", "historico", self.historico_aberturas),
            ("Diagnóstico…", "info", self.ver_diagnostico),
            ("Backup do cofre…", "backup", self.backup),
            None,
            "Segurança",
            ("Verificar integridade do cofre…", "escudo", self.verificar_integridade_cofre),
            ("Verificar integridade do programa…", "escudo", self.verificar_integridade),
            ("Segurança adicional (visão geral)…", "escudo", self.tela_seguranca_adicional),
            ("Chaves FIDO…", "chave", self.gerenciar_fido),
            ("Computadores autorizados…", "cadeado", self.gerenciar_computadores),
            ("Trocar senha mestra…", "editar", self.trocar_senha),
            *([] if self.cofre.modo == MODO_S else [("Nova chave de acesso…", "atualizar", self.nova_chave)]),
            ("Bloqueio automático…", "cadeado", self.configurar_bloqueio),
            ("Proteção extra (pedir senha mestra de novo)…", "cadeado", self.configurar_protecao_extra),
            ("Tentativas erradas…", "cadeado", self.configurar_tentativas),
        ])
        bmais = bt("", "mais", lambda: self._menu_mais.abrir(bmais), "Icone.TButton", C["texto"], "Mais opções")
        bt("Chave FIDO", "chave", self.gerenciar_fido, dica="Cadastrar ou gerenciar chaves de segurança FIDO2")
        self._btn_novo = bt("Novo item", "novo", self.novo, "Primario.TButton", C["prim_fg"],
                            "Adicionar conta (Ctrl+N)")
        self._btn_mais = bmais
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
        interno = tk.Frame(lat, bg=C["lateral"])
        interno.pack(fill="both", expand=True)
        self.lateral_pessoas = BarraLateral(interno, max_linhas=4)
        self.lateral_pessoas.pack(fill="x", pady=(8, 0))
        self.lateral_pessoas.bind("<<TreeviewSelect>>", self._ao_escolher_pessoa)
        self.lateral = BarraLateral(interno, max_linhas=8)
        self.lateral.pack(fill="x")
        self.lateral.bind("<<TreeviewSelect>>", self._ao_escolher_grupo)
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
        topo_lista.pack(fill="x", padx=(14, 16), pady=(16, 6))
        self._titulo_lista = tk.Label(topo_lista, text="Todas as contas", bg=C["fundo"], fg=C["texto"],
                                      font="CofreSub", anchor="w")
        self._titulo_lista.pack(side="left")
        self._conta_lista = tk.Label(topo_lista, text="", bg=C["fundo"], fg=C["fraco"], font="CofreTexto")
        self._conta_lista.pack(side="left", padx=(10, 0), pady=(3, 0))
        self.ordem_az = True                                # padrão: ordem alfabética (A → Z)
        self._btn_ordem = ttk.Button(topo_lista, text="A → Z", style="Acao.TButton", width=7,
                                     command=self._alternar_ordem)
        self._btn_ordem.pack(side="right")
        self._dica(self._btn_ordem, "Troca a ordem da lista: A → Z (alfabética) ou Z → A.")
        self.tree = ListaContas(meio)
        self.tree.pack(fill="both", expand=True, padx=(6, 0))
        self.tree.ao_soltar = self._soltar_conta
        self.tree.ao_arrastar = self._destacar_destino
        self.tree.ao_menu = self._menu_conta
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
            self._ligar_raiz(seq, lambda e, a=acao: a(e) if self.cofre is not None else None)
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
            """Pré-desenha uma imagem por vez e agenda a próxima, sem travar a tela."""
            if not tarefas or self.cofre is None:
                return
            try:
                tarefas.pop(0)()
                self.root.after(1, passo)
            except tk.TclError:
                pass
        self.root.after(150, passo)

    # ---------- Lista de contas: indicadores, ordenação, busca e painel de detalhe ----------

    def _atualizar_indicadores(self):
        """Atualiza a barra de status (arquivo, cifras, derivação de chave e última abertura)."""
        C = CORES
        partes = ["Criptografado neste computador"]     # os detalhes técnicos ficam no botão  ?  (Guia de uso)
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
        aberto = getattr(self, "_seg_aberto", False)           # recolhido por padrão: só o escudo
        caixa = tk.Frame(p, bg=C["sup"], highlightthickness=1, highlightbackground=C["borda"], padx=12, pady=8,
                         cursor="hand2")
        caixa.pack(fill="x")
        topo = tk.Frame(caixa, bg=C["sup"], cursor="hand2")
        topo.pack(fill="x")
        seta = tk.Label(topo, text="▾" if aberto else "▸", bg=C["sup"], fg=C["fraco"], font="CofrePequeno",
                        cursor="hand2")
        seta.pack(side="right")
        escudo = tk.Label(topo, image=imagem_icone(self.root, "escudo" if tudo_ok else "alerta",
                                                   C["ok"] if tudo_ok else C["alerta"], 16), bg=C["sup"],
                          cursor="hand2")
        escudo.pack(side="left")
        rotulo = tk.Label(topo, text="Cofre protegido" if tudo_ok else "Proteção parcial", bg=C["sup"],
                          fg=C["texto"], font="CofreForte", cursor="hand2")
        rotulo.pack(side="left", padx=(8, 0))

        pts, nivel, itens_nivel = nivel_protecao(self.cofre.modo, self.cofre.m, self.cofre.fido, self.cofre.pc) \
            if self.cofre is not None else (0, "Básica", [])
        cor_nivel = C["perigo"] if pts < 40 else C["alerta"] if pts < 65 else C["ok"]
        faixa = tk.Frame(caixa, bg=C["sup"], cursor="hand2")
        faixa.pack(fill="x", pady=(6, 0))
        barra = tk.Canvas(faixa, height=6, bg=C["sup2"], highlightthickness=0, cursor="hand2")
        barra.pack(fill="x")
        barra.bind("<Configure>", lambda e, b=barra: (b.delete("all"), b.create_rectangle(
            0, 0, int(e.width * pts / 100), 6, fill=cor_nivel, width=0)))
        tk.Label(faixa, text=f"Proteção: {nivel}  ({pts}/100)", bg=C["sup"], fg=cor_nivel, font="CofrePequeno",
                 cursor="hand2", wraplength=_px(160), justify="left").pack(anchor="w", pady=(3, 0))

        def alternar(event=None):
            """Mostra ou esconde os detalhes da proteção (captura de tela, memória, FIDO, bloqueio automático)."""
            self._seg_aberto = not getattr(self, "_seg_aberto", False)
            self._atualizar_indicadores()
        for w in (caixa, topo, escudo, rotulo, seta, faixa) + tuple(faixa.winfo_children()):
            w.bind("<Button-1>", alternar)
        if not aberto:
            return
        tk.Label(caixa, text="O QUE AUMENTA A PROTEÇÃO", bg=C["sup"], fg=C["fraco"], font="CofrePequeno").pack(
            anchor="w", pady=(10, 0))
        for rot, pt, ativo, acao in itens_nivel:
            lin = tk.Frame(caixa, bg=C["sup"])
            lin.pack(fill="x", pady=(4, 0))
            tk.Label(lin, image=_ponto_img(self.root, C["ok"] if ativo else C["fraco"], 6), bg=C["sup"]).pack(
                side="left", padx=(5, 9))
            tk.Label(lin, text=rot, bg=C["sup"], fg=C["texto"] if ativo else C["suave"], font="CofrePequeno",
                     wraplength=_px(170), justify="left").pack(side="left")
            tk.Label(lin, text=f"+{pt}" if not ativo else "✓", bg=C["sup"], fg=C["fraco"] if not ativo else C["ok"],
                     font="CofrePequeno").pack(side="right")
            if acao and not ativo:
                b = tk.Label(lin, text="Ativar", bg=C["sup"], fg=C["prim_txt"], font="CofrePequeno", cursor="hand2")
                b.pack(side="right", padx=(0, 8))
                b.bind("<Button-1>", lambda e, a=acao: self.gerenciar_computadores() if a == "pc" else self.gerenciar_fido())
            elif not ativo:
                # Sem "acao" (hoje só a chave de acesso, quando não escolhida ao criar o cofre): não dá para
                # ligar na hora, mas clicar não pode continuar sem fazer NADA (achado do usuário 2026-11-13) —
                # abre a tela "Segurança adicional", que explica o porquê e o caminho possível.
                b = tk.Label(lin, text="Por quê?", bg=C["sup"], fg=C["prim_txt"], font="CofrePequeno", cursor="hand2")
                b.pack(side="right", padx=(0, 8))
                b.bind("<Button-1>", lambda e: self.tela_seguranca_adicional())
        bt_tudo = tk.Label(caixa, text="Ver tudo e ativar  ›", bg=C["sup"], fg=C["prim_txt"], font="CofrePequeno",
                           cursor="hand2")
        bt_tudo.pack(anchor="e", pady=(8, 0))
        bt_tudo.bind("<Button-1>", lambda e: self.tela_seguranca_adicional())
        tk.Frame(caixa, bg=C["borda"], height=1).pack(fill="x", pady=(8, 0))
        linhas = [("Captura de tela bloqueada" if self.protegido else "Captura de tela livre", self.protegido)]
        if EH_WINDOWS:
            linhas.append(("Memória trancada", "memoria" in BLINDAGEM))
            linhas.append(("Anti-injeção e anti-espiões", "ganchos" in BLINDAGEM))
        fido = self.cofre.fido if self.cofre is not None else None
        linhas.append((f"Chave FIDO: {len(fido['chaves'])}" if fido else "Chave FIDO: nenhuma", bool(fido)))
        pcs = self.cofre.pc if self.cofre is not None else None
        linhas.append((f"Computadores autorizados: {len(pcs['maquinas'])}" if pcs else "Computadores autorizados: nenhum",
                       bool(pcs)))
        linhas.append((f"Bloqueio automático: {self._inatividade_ms() // 60000} min", True))
        for texto, bom in linhas:
            lin = tk.Frame(caixa, bg=C["sup"])
            lin.pack(fill="x", pady=(5, 0))
            tk.Label(lin, image=_ponto_img(self.root, C["ok"] if bom else C["fraco"], 6), bg=C["sup"]).pack(
                side="left", padx=(5, 9))
            tk.Label(lin, text=texto, bg=C["sup"], fg=C["suave"], font="CofrePequeno").pack(side="left")

    def _ponto(self, grupo):
        """Bolinha com a cor do grupo."""
        return _ponto_img(self.root, tom_para(grupo) if grupo else CORES["fraco"])

    def _alternar_ordem(self):
        """Alterna a lista de contas entre A → Z e Z → A."""
        self.ordem_az = not getattr(self, "ordem_az", True)
        try:
            self._btn_ordem.config(text="A → Z" if self.ordem_az else "Z → A")
        except (tk.TclError, AttributeError):
            pass
        self.atualizar_lista(manter_lateral=True)

    def atualizar_lista(self, manter_lateral=False, so_status=False):
        """Recarrega a lista de itens aplicando busca e filtros e mantém a seleção."""
        if not hasattr(self, "tree") or self.cofre is None:
            return
        try:
            self.tree.winfo_exists()
        except tk.TclError:
            return
        if not manter_lateral and not so_status:
            self._cache_auditoria_lista = None
            self._cache_lista_ordenada = {}
        C = CORES
        regs = self.cofre.registros
        auditoria = getattr(self, "_cache_auditoria_lista", None)
        if auditoria is None:
            auditoria = self._cache_auditoria_lista = auditar_cofre(regs)
        alerta = {a[0]["id"] for a in auditoria if a[4] <= 1}
        grave = {a[0]["id"] for a in auditoria if a[4] == 0}
        pessoas = self._pessoas()
        varias = len(pessoas) > 1
        fp = self.filtro_pessoa.get()
        if fp != "*" and fp not in pessoas:
            fp = "*"
            self.filtro_pessoa.set("*")
        da_pessoa = regs if fp == "*" else [r for r in regs if self._pessoa_de(r) == fp]
        filtro = self.filtro_grupo.get()
        termo = self.busca.get().lower().strip()
        visiveis = []
        ordenadas = getattr(self, "_cache_lista_ordenada", None)
        if ordenadas is None:
            ordenadas = self._cache_lista_ordenada = {}
        if fp not in ordenadas:
            ordenadas[fp] = sorted(da_pessoa, key=lambda r: chave_ordem_alfabetica(r.get("servico", "")))
        registros_ordenados = ordenadas[fp]
        if not getattr(self, "ordem_az", True):
            registros_ordenados = reversed(registros_ordenados)
        for r in registros_ordenados:
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
                grupos = sorted(({(r.get("grupo") or "").strip() for r in da_pessoa}
                                 | set(self._grupos_vazios(None if fp == "*" else fp))) - {""},
                                key=chave_ordem_alfabetica)
                rot_grupos = f"Grupos de {self._nome_pessoa(fp)}" if (varias and fp != "*") else "Grupos"
                for i, g in enumerate(grupos):
                    n = sum(1 for r in da_pessoa if (r.get("grupo") or "").strip() == g)
                    nome = g if len(g) <= 24 else g[:23] + "…"
                    ent.append({"iid": "g:" + g, "texto": nome, "n": n, "cor": tom_para(g),
                                "secao": rot_grupos if i == 0 else None,
                                "menu": lambda ev, g=g: self._menu_grupo(ev, g)})
                sem = sum(1 for r in da_pessoa if not (r.get("grupo") or "").strip())
                if sem and grupos:
                    ent.append({"iid": "__sem__", "texto": "Sem grupo", "n": sem, "cor": C["fraco"]})
                ent.append({"iid": "__novo_grupo__", "texto": "Novo grupo", "n": "", "icone": "novo",
                            "cor_txt": C["fraco"], "acao": self._novo_grupo,
                            "secao": rot_grupos if not grupos else None})
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
                contem = ", ".join(segredos)
                if r["id"] in alerta:
                    contem = "⚠ " + contem
                sub = r.get("login") or " • ".join(segredos) or "Sem dados"
                if varias and fp == "*" and self._pessoa_de(r):
                    sub = f"{sub}   ·   {self._pessoa_de(r)}"
                titulo = r.get("servico", "") or "(sem nome)"
                linhas.append({"iid": r["id"], "titulo": titulo,
                               "login": r.get("login", ""), "sub": sub, "contem": contem,
                               "cor": None,
                               "marca": None, "grupo": g,
                               "alerta": 2 if r["id"] in grave else (1 if r["id"] in alerta else 0)})
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

    def _agendar_busca(self):
        """Debounce da busca (150 ms) e sem recriar as barras laterais a cada letra."""
        t = getattr(self, "_timer_busca", None)
        if t:
            try:
                self.root.after_cancel(t)
            except (AttributeError, tk.TclError, OSError, ValueError):
                pass

        def rodar():
            """Executa a busca depois que o usuário parou de digitar."""
            self._timer_busca = None
            try:
                if not self.tree.winfo_exists():       # a tela foi trocada enquanto o atraso corria
                    return
            except (AttributeError, tk.TclError):
                return
            self.atualizar_lista(manter_lateral=True)
        self._timer_busca = self.root.after(150, rodar)

    def _agendar_detalhe(self):
        """Junta várias seleções seguidas (ex.: segurar a seta) numa única montagem do painel."""
        if getattr(self, "_detalhe_pendente", None):
            return

        def rodar():
            """Mostra o detalhe do item depois que a seleção assentou."""
            self._detalhe_pendente = None
            self._montar_detalhe()
        self._detalhe_pendente = self.root.after_idle(rodar)

    def _imagem_avatar(self, cor, tam):
        """Imagem redonda com a inicial, na cor do grupo (com cache)."""
        cache = self.__dict__.setdefault("_cache_avatar", {})
        if (cor, tam) not in cache:
            cache[(cor, tam)] = desenhar_avatar(cor, tam).imagem(self.root)
        return cache[(cor, tam)]

    def _montar_detalhe(self):
        """Monta o painel de detalhes do item selecionado (campos secretos ocultos, copiar, mostrar)."""
        if not hasattr(self, "detalhe"):
            return
        C = CORES
        r = self._selecionado_silencioso()
        try:
            filhos = self.detalhe.winfo_children()
        except tk.TclError:
            return
        # nada mudou (mesmo item, mesmos dados, mesmos campos à mostra): não remonta
        chave = None if not r else hashlib.sha256(repr((
            r["id"], tuple(sorted(cp for (i, cp) in self._revelados if i == r["id"])),
            tuple(sorted((k, str(v)) for k, v in r.items())))).encode("utf-8", "replace")).digest()
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
        marca = marca_servico(r.get("servico", ""), r.get("grupo", ""))
        av._img = self._imagem_avatar(C["prim_fundo"] if marca else C["sup3"], 56)
        av.create_image(_px(28), _px(28), image=av._img)
        av.create_text(_px(28), _px(28), text=marca or (r.get("servico", "?").strip()[:1] or "?").upper(),
                       fill=C["texto"], font="CofreTitulo")
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
        ttk.Label(chips, text="Ativa" if _item_ativo(r) else "Desativada",
                  style="C.TLabel", foreground=C["ok"] if _item_ativo(r) else C["fraco"]).pack(
                      side="left", padx=(0, 12))
        if self._protecao_global():          # agora é um ajuste do cofre todo (⋯ → Segurança → Proteção extra), não por item
            ttk.Label(chips, text=" Proteção extra ativa", image=imagem_icone(self.root, "cadeado", C["prim_txt"], 14),
                      compound="left", style="C.TLabel", foreground=C["prim_txt"]).pack(side="left")

        # ações (embaixo)
        acoes = ttk.Frame(d, style="C.TFrame")
        acoes.pack(side="bottom", fill="x", pady=(12, 0))
        ttk.Button(acoes, text="Editar", style="C.Primario.TButton", command=self.editar,
                   image=imagem_icone(self.root, "editar", "#ffffff"), compound="left").pack(side="left")
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
            if campo == "codigos" and aberto:
                ttk.Label(linha, text=f"{len([x for x in valor.splitlines() if x.strip()])} código(s)",
                          style="C.Fraco.TLabel").pack(side="left", anchor="w")
                for n_cod, cod in enumerate((x.strip() for x in valor.splitlines() if x.strip()), 1):
                    lc = ttk.Frame(bloco, style="C.TFrame")
                    lc.pack(fill="x", pady=(4, 0))
                    bcod = ttk.Button(lc, text=" Copiar", image=imagem_icone(self.root, "copiar", C["suave"]),
                                      compound="left", style="C.Icone.TButton")
                    bcod.config(command=lambda c_=cod, b_=bcod, n_=n_cod: self._copiar_codigo(c_, b_, n_))
                    bcod.pack(side="right")
                    ttk.Label(lc, text=f"{n_cod}.", style="C.Fraco.TLabel", width=3).pack(side="left", anchor="n")
                    ttk.Label(lc, text=cod, style="C.Valor.TLabel", font="CofreMono", wraplength=_px(190),
                              justify="left").pack(side="left", anchor="w", fill="x", expand=True)
            else:
                ttk.Label(linha, text=mostra, style="C.Valor.TLabel" if secreto else "C.TLabel",
                          font="CofreMono" if secreto else "CofreTexto", wraplength=_px(250), justify="left").pack(
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
            ttk.Label(campos, text=r["notas"], style="C.Suave.TLabel", wraplength=_px(350), justify="left").pack(
                anchor="w", pady=(3, 0))


    # ---------- Passeio guiado e atalhos de teclado ----------

    def passeio_principal(self):
        """Passeio guiado da tela principal: cada área é destacada em amarelo, com o que faz e como usar."""
        if getattr(self, "_tour", None) is not None:
            self._tour.encerrar()
        def g(nome):
            return lambda: getattr(self, nome, None)
        passos = [
            (None, "Bem-vindo ao seu cofre",
             "Vou mostrar, uma área de cada vez, para que serve cada parte da tela e como usar (cerca de 1 minuto). "
             "Clique em Próximo para continuar. Você pode repetir este passeio quando quiser no botão  ?  ."),
            (g("lateral_pessoas"), "1. Perfis (pessoas)",
             "'Eu' guarda as suas contas. Clique em 'Adicionar pessoa' para criar outro perfil (Pai, Mãe, Ana...): "
             "as contas de cada um ficam separadas, no mesmo cofre. Para passar uma conta para outro perfil, "
             "ARRASTE-a da lista até o nome dele."),
            (g("lateral"), "2. Grupos (categorias)",
             "Aqui ficam as categorias que VOCÊ inventa: Banco, Compras, Redes sociais... Clique em 'Novo grupo' para "
             "criar e arraste contas para dentro. Botão direito num grupo: renomear ou remover (as contas não são apagadas)."),
            (lambda: getattr(self, "campo_busca", None), "3. Busca",
             "Digite parte do nome da conta, do login ou das notas e a lista filtra na hora. Atalho: Ctrl+F."),
            (g("_btn_ordem"), "4. Ordem da lista",
             "A lista vem em ordem alfabética (A → Z). Clique para inverter (Z → A)."),
            (g("tree"), "5. Lista de contas",
             "Clique numa conta para ver os detalhes. Duplo clique edita. Ctrl+C copia a senha. Botão direito: mover "
             "para outro perfil ou criar um perfil novo com ela. Arraste para mover para um perfil ou grupo."),
            (g("detalhe"), "6. Detalhes da conta",
             "Senhas aparecem ocultas (••••). 'Mostrar' revela por 20 segundos; 'Copiar' copia e a área de transferência "
             "é limpa em 15 s. Os códigos de recuperação têm um botão Copiar para CADA código."),
            (g("_btn_novo"), "7. Novo item",
             "Cria uma conta: nome, grupo, login, senha (o botão de gerar cria uma senha forte), códigos de recuperação "
             "e notas. Dentro do formulário há um passeio só dele."),
            (g("_btn_mais"), "8. Mais opções  ⋯",
             "Importar planilha (com varredura de segurança), baixar o modelo de planilha, gerador e teste de senhas, "
             "verificar senhas fracas ou repetidas, backup, trocar a senha mestra, chaves FIDO e bloqueio automático."),
            (g("_btn_ajuda"), "9. Ajuda  ?",
             "Aqui você reabre este passeio e o guia com os atalhos de teclado."),
            (g("_btn_bloquear"), "10. Bloquear",
             "Tranca o cofre na hora (Ctrl+L). Ele também tranca sozinho depois de alguns minutos sem uso."),
            (None, "Pronto!",
             "Dica: comece criando seus perfis e grupos, depois importe sua planilha pelo menu ⋯ (baixe o modelo primeiro: "
             "ele tem um passo a passo)."),
        ]
        TourGuiado(self, self.root, passos).iniciar()

    def _oferecer_passeio(self, tentativa=0):
        """Na primeira vez que o cofre abre (logo depois de CRIAR o cofre, ou no 1º desbloqueio), oferece o passeio
        guiado e guarda que já foi oferecido. Se houver outra janela aberta (chave de acesso, cadastro FIDO...), espera
        ela fechar para o convite não aparecer por cima nem ser perdido."""
        try:
            if self.cofre is None or self.cofre.meta.get("tour_visto") or self.cofre.somente_leitura:
                return
            if any(isinstance(w, tk.Toplevel) and w.winfo_viewable() for w in self.root.winfo_children()):
                if tentativa < 60:                       # até ~90 s esperando
                    self.root.after(1500, lambda: self._oferecer_passeio(tentativa + 1))
                return
        except (AttributeError, tk.TclError):
            return
        if messagebox.askyesno("Passeio guiado", "Quer um passeio rápido (1 minuto) mostrando, área por área, "
                               "para que serve cada parte do cofre e como usar?\n\n(Depois você pode repetir no "
                               "botão  ?  do alto da tela.)"):
            self.root.after(150, self.passeio_principal)
        self._transacao(lambda: self.cofre.meta.__setitem__("tour_visto", True))

    def _mostrar_atalhos(self):
        """Guia de uso (botão '?'): atalhos de teclado e como organizar contas, perfis, grupos e códigos."""
        messagebox.showinfo("Guia de uso",
                            "ATALHOS\n"
                            "Ctrl+F   buscar          Ctrl+N   novo item\n"
                            "Ctrl+G   gerador de senhas          Ctrl+L   bloquear o cofre\n"
                            "Na lista: Enter ou duplo clique = editar; Ctrl+C = copiar a senha;\n"
                            "Ctrl+B = copiar o login; Delete = excluir; Esc (na busca) = limpar.\n\n"
                            "ORGANIZAR\n"
                            "• Perfis (pessoas): 'Adicionar pessoa' na barra da esquerda. Para mudar uma conta de perfil, "
                            "ARRASTE-a até o perfil ou use o clique direito > 'Mover para…'.\n"
                            "• Grupos (Banco, Compras, Redes sociais…): 'Novo grupo' na barra da esquerda; arraste contas "
                            "para dentro ou escolha o grupo ao editar a conta.\n"
                            "• Botão 'A → Z' sobre a lista: troca para Z → A.\n\n"
                            "CÓDIGOS DE RECUPERAÇÃO\n"
                            "Ao editar a conta, ligue 'Mostrar' e use 'Colar vários códigos' (um por linha). Na tela da "
                            "conta, cada código tem o seu botão Copiar.\n\n"
                            "IMPORTAR\n"
                            "Menu ⋯ > Importar planilha. O cofre faz uma varredura de segurança do arquivo antes.\n\n"
                            "INFORMAÇÕES TÉCNICAS\n"
                            f"Arquivo do cofre: {os.path.basename(self.caminho)}\n"
                            f"Pasta: {os.path.dirname(os.path.abspath(self.caminho))}\n"
                            "Criptografia: ChaCha20-Poly1305 dentro de AES-256-GCM (duas camadas).\n"
                            "Derivação da senha: Argon2id (resistente a placas de vídeo).\n"
                            f"Versão do programa: {VERSAO_PROGRAMA}\n"
                            "Nada sai deste computador: o cofre não usa a internet.")

    def _avisar(self, texto):
        """Mensagem temporária na barra de status."""
        try:
            self.status.config(text=texto)
            if getattr(self, "_timer_aviso", None):
                self.root.after_cancel(self._timer_aviso)
            self._timer_aviso = self.root.after(6000, lambda: self.atualizar_lista(so_status=True))
        except tk.TclError:
            pass

    SUGESTOES_GRUPO = ("Banco", "Compras", "Redes sociais", "E-mail", "Trabalho", "Streaming", "Jogos", "Governo")

    # ---------- Pessoas e grupos (organização dos itens) ----------

    def _pessoa_ativa(self):
        """Perfil em que as ações de grupo acontecem agora: o escolhido na barra lateral ('' = Eu). Com 'Todas as
        pessoas' selecionado, vale o titular (Eu)."""
        fp = self.filtro_pessoa.get()
        return "" if fp == "*" else fp

    def _grupos_vazios(self, pessoa=None):
        """Grupos criados pelo usuário DENTRO de um perfil, que ainda podem não ter nenhuma conta (guardados no cofre
        em meta['grupos_pessoa'] = {perfil: [grupos]}). pessoa=None devolve os de todos os perfis. Cofres antigos
        tinham uma lista única ('grupos_extra'): ela passa a pertencer ao titular (Eu)."""
        gp = self.cofre.meta.get("grupos_pessoa", {})
        gp = gp if isinstance(gp, dict) else {}
        antigos = [g for g in self.cofre.meta.get("grupos_extra", []) if isinstance(g, str) and g.strip()]

        def da(p):
            """Grupos vazios do perfil p, sem repetir."""
            lista = [g for g in gp.get(p, []) if isinstance(g, str) and g.strip()] + (antigos if p == "" else [])
            return list(dict.fromkeys(lista))
        if pessoa is not None:
            return da(pessoa)
        return list(dict.fromkeys(g for p in (set(gp) | {""}) for g in da(p)))

    def _guardar_grupos_vazios(self, pessoa, lista):
        """Grava a lista de grupos vazios de um perfil (e migra a lista única antiga para o titular). Chamar
        dentro de uma transação."""
        gp = self.cofre.meta.get("grupos_pessoa", {})
        gp = dict(gp) if isinstance(gp, dict) else {}
        antigos = [g for g in self.cofre.meta.pop("grupos_extra", []) if isinstance(g, str) and g.strip()]
        if antigos:
            gp[""] = list(dict.fromkeys(list(gp.get("", [])) + antigos))
        gp[pessoa] = list(dict.fromkeys(lista))
        self.cofre.meta["grupos_pessoa"] = {k: v for k, v in gp.items() if v}

    def _grupos(self, pessoa=None):
        """Nomes dos grupos de um perfil (com contas dele ou criados vazios), em ordem alfabética. pessoa=None:
        de todos os perfis."""
        regs = self.cofre.registros if self.cofre is not None else []     # cofre bloqueado no meio: lista vazia, sem erro
        usados = {(r.get("grupo") or "").strip() for r in regs
                  if pessoa is None or self._pessoa_de(r) == pessoa}
        return sorted((usados | set(self._grupos_vazios(pessoa))) - {""}, key=chave_ordem_alfabetica)

    def _grupos_sugeridos(self, pessoa=None):
        """Grupos do perfil primeiro; depois sugestões comuns (Banco, Compras, Redes sociais...) que ainda não existem."""
        mine = self._grupos(pessoa)
        minhas = {chave_ordem_alfabetica(g) for g in mine}
        return mine + [g for g in self.SUGESTOES_GRUPO if chave_ordem_alfabetica(g) not in minhas]

    _SINONIMOS_GRUPO = {
        "Banco": {"banco", "bancos", "bancosefinancas", "financas", "financeiro", "finanicas"},
        "Redes sociais": {"redessociais", "redesocial", "social", "sociais", "redes"},
        "E-mail": {"email", "emails", "emailenuvem", "nuvem", "google"},
        "Trabalho": {"trabalho", "work", "profissional", "dev", "desenvolvimento"},
        "Streaming": {"streaming", "entretenimento", "filmes", "musica", "series"},
        "Jogos": {"jogos", "games", "game"},
        "Compras": {"compras", "lojas", "loja", "shopping"},
        "Governo": {"governo", "gov", "documentos"},
    }

    def _nome_grupo_recomendado(self, servico):
        """Nome do grupo a RECOMENDAR para esta conta: um grupo que o usuario ja tem e combina com o tipo (ex.:
        'Bancos'); se nao tiver, o nome padrao ('Banco'). None quando o tipo nao e reconhecido."""
        tipo = grupo_recomendado(servico)
        if tipo is None:
            return None
        sinonimos = self._SINONIMOS_GRUPO.get(tipo, set()) | {chave_ordem_alfabetica(tipo).replace(" ", "")}
        for g in self._grupos_sugeridos():
            if chave_ordem_alfabetica(g).replace(" ", "") in sinonimos:
                return g
        return tipo

    def _novo_grupo(self, mover_id=None):
        """Cria um grupo (categoria) com o nome que o usuário quiser DENTRO do perfil escolhido; com mover_id, já
        coloca essa conta nele."""
        pessoa = self._pessoa_ativa()
        dono = self._nome_pessoa(pessoa)
        nome = self._pedir_nome("Novo grupo", f"Nome do grupo de {dono} (ex.: Banco, Compras, Google, Redes sociais). "
                                              "Você pode criar quantos quiser e arrastar contas para dentro dele.")
        if not nome:
            return False
        if chave_ordem_alfabetica(nome) in {chave_ordem_alfabetica(g) for g in self._grupos(pessoa)}:
            messagebox.showerror("Grupo", f'{dono} já tem o grupo "{nome}".')
            return False

        def mudar():
            """Guarda o grupo novo na lista de grupos deste perfil."""
            self._guardar_grupos_vazios(pessoa, self._grupos_vazios(pessoa) + [nome])
        if not self._transacao(mudar):
            return False
        if self.filtro_pessoa.get() == "*":
            self.filtro_pessoa.set("")                # o grupo nasceu no titular: mostra o perfil dele
        self.filtro_grupo.set(nome)
        if mover_id:
            return self._mover_conta(mover_id, grupo=nome)
        self.atualizar_lista()
        self._avisar(f'Grupo "{nome}" criado em {dono}. Arraste contas para ele ou escolha-o ao editar uma conta.')
        return True

    def _remover_grupo(self, grupo):
        """Remove o grupo do perfil atual (as contas NÃO são apagadas: ficam sem grupo)."""
        n = sum(1 for r in self.cofre.registros if (r.get("grupo") or "").strip() == grupo and self._no_escopo(r))
        if not messagebox.askyesno("Remover grupo", f'Remover o grupo "{grupo}"?' +
                                   (f"\n\nAs {n} conta(s) NÃO são apagadas: ficam sem grupo." if n else "")):
            return

        def mudar():
            """Tira o grupo da lista do perfil e solta as contas dele."""
            for r in self.cofre.registros:
                if (r.get("grupo") or "").strip() == grupo and self._no_escopo(r):
                    r["grupo"] = ""
            for p in self._donos_do_escopo():
                self._guardar_grupos_vazios(p, [g for g in self._grupos_vazios(p) if g != grupo])
        if not self._transacao(mudar):
            return
        if self.filtro_grupo.get() == grupo:
            self.filtro_grupo.set("Todos")
        self.atualizar_lista()

    def _donos_do_escopo(self):
        """Perfis afetados pelas ações de grupo: só o escolhido, ou todos se 'Todas as pessoas' estiver marcado."""
        fp = self.filtro_pessoa.get()
        return list(self._pessoas()) if fp == "*" else [fp]

    def _ids_com_alerta(self):
        """Ids dos itens com achados graves na auditoria (gravidade 0 ou 1)."""
        return {a[0]["id"] for a in auditar_cofre(self.cofre.registros) if a[4] <= 1}

    # ---------- pessoas ----------
    TITULAR = "Eu"

    @staticmethod
    def _pessoa_de(r):
        """Pessoa dona do item ('' = titular)."""
        return (r.get("pessoa") or "").strip()

    def _nome_pessoa(self, pessoa):
        """Nome para mostrar da pessoa (o titular tem nome padrão)."""
        return pessoa or self.TITULAR

    def _valor_pessoa(self, texto):
        """Valor gravado para a pessoa escolhida no formulário."""
        t = (texto or "").strip()
        return "" if t.lower() in ("", self.TITULAR.lower()) else t

    def _pessoas(self):
        """'' (Eu, o titular do cofre) primeiro, depois as outras pessoas em ordem alfabética."""
        extras = [p for p in self.cofre.meta.get("pessoas", []) if isinstance(p, str)]
        nomes = {self._pessoa_de(r) for r in self.cofre.registros} | {p.strip() for p in extras}
        nomes.discard("")
        return [""] + sorted(nomes, key=str.lower)

    def _ao_escolher_pessoa(self, event=None):
        """Filtra a lista pela pessoa escolhida na barra lateral."""
        sel = self.lateral_pessoas.selection()
        if not sel or not sel[0].startswith("p:"):
            return
        self.filtro_pessoa.set(sel[0][2:])
        self.filtro_grupo.set("Todos")
        self.root.after_idle(self.atualizar_lista)

    def _pedir_nome(self, titulo, texto, inicial=""):
        """Pequena janela para digitar um nome. Devolve o nome ou None."""
        d = self._nova_janela(titulo)
        self._modal(d)
        fr = ttk.Frame(d, padding=(24, 20, 24, 18))
        fr.pack(fill="both", expand=True)
        ttk.Label(fr, text=texto, wraplength=_px(340), justify="left").pack(anchor="w", pady=(0, 8))
        e = ttk.Entry(fr, width=32)
        e.pack(fill="x")
        e.insert(0, inicial)
        if not inicial:
            self._pista_entrada(e, "Digite um nome")
        e.select_range(0, "end")
        e.focus_set()
        res = {"v": None}

        def ok(event=None):
            """Confirma o nome digitado (espaços normalizados)."""
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
        """True se nenhuma outra pessoa tem esse nome."""
        existentes = {self._nome_pessoa(p).lower() for p in self._pessoas() if p != ignorar}
        if nome.lower() in existentes:
            messagebox.showerror("Pessoa", f'Já existe "{nome}".')
            return False
        return True

    # ---------- mover contas entre perfis (pessoas) e grupos: arrastar ou menu ----------
    def _alvo_em(self, x_root, y_root):
        """Destino sob o mouse: ('pessoa', iid) na barra de pessoas, ('grupo', iid) na de grupos, ou None."""
        for tipo, barra in (("pessoa", getattr(self, "lateral_pessoas", None)), ("grupo", getattr(self, "lateral", None))):
            if barra is None:
                continue
            try:
                iid = barra.item_em(x_root, y_root)
            except tk.TclError:
                iid = None
            if iid:
                return tipo, iid
        return None

    def _destacar_destino(self, x_root, y_root):
        """Enquanto arrasta uma conta, destaca o perfil ou grupo que a receberia."""
        alvo = self._alvo_em(x_root, y_root) if x_root is not None else None
        for tipo, barra in (("pessoa", getattr(self, "lateral_pessoas", None)), ("grupo", getattr(self, "lateral", None))):
            if barra is not None:
                try:
                    barra.destacar_alvo(alvo[1] if alvo and alvo[0] == tipo else None)
                except tk.TclError:
                    pass

    def _soltar_conta(self, id_conta, x_root, y_root):
        """Conta solta sobre uma pessoa (muda de perfil), sobre 'Adicionar pessoa' (cria o perfil novo e move a conta)
        ou sobre um grupo (muda de grupo)."""
        alvo = self._alvo_em(x_root, y_root)
        if not alvo or self.cofre is None:
            return
        tipo, iid = alvo
        if tipo == "pessoa":
            if iid == "__nova_pessoa__":
                self._mover_para_nova_pessoa(id_conta)
            elif iid.startswith("p:") and iid != "p:*":
                self._mover_conta(id_conta, pessoa=iid[2:])
        else:
            if iid == "__novo_grupo__":
                self._novo_grupo(mover_id=id_conta)
            elif iid == "__sem__":
                self._mover_conta(id_conta, grupo="")
            elif iid.startswith("g:"):
                self._mover_conta(id_conta, grupo=iid[2:])

    def _mover_conta(self, id_conta, pessoa=None, grupo=None):
        """Muda a pessoa e/ou o grupo de uma conta (numa transação) e atualiza a tela."""
        reg = next((r for r in self.cofre.registros if r.get("id") == id_conta), None)
        if reg is None:
            return False
        antes = (self._pessoa_de(reg), (reg.get("grupo") or "").strip())
        depois = (antes[0] if pessoa is None else pessoa, antes[1] if grupo is None else grupo)
        if antes == depois:
            return False

        def mudar():
            """Grava a nova pessoa e/ou o novo grupo no item."""
            reg["pessoa"], reg["grupo"] = depois
        if not self._transacao(mudar):
            return False
        self.atualizar_lista()
        destino = self._nome_pessoa(depois[0]) if pessoa is not None else (depois[1] or "sem grupo")
        self._avisar(f'"{reg.get("servico", "")}" movida para {destino}.')
        return True

    def _mover_para_nova_pessoa(self, id_conta):
        """Cria um perfil novo (pede o nome) e já move a conta para ele."""
        nome = self._pedir_nome("Novo perfil", "Nome do perfil novo (ex.: Pai, Mãe, Trabalho). A conta escolhida já "
                                               "vai para ele.")
        if not nome or not self._nome_livre(nome):
            return False

        def mudar():
            """Acrescenta o perfil à lista do cofre."""
            lista = [x for x in self.cofre.meta.get("pessoas", []) if isinstance(x, str)]
            self.cofre.meta["pessoas"] = lista + [nome]
        if not self._transacao(mudar):
            return False
        return self._mover_conta(id_conta, pessoa=nome)

    def _menu_conta(self, id_conta, evento):
        """Clique direito numa conta: mover para outro perfil (pessoa) ou criar um perfil novo com ela."""
        reg = next((r for r in self.cofre.registros if r.get("id") == id_conta), None) if self.cofre else None
        if reg is None:
            return
        itens = []
        for pe in self._pessoas():
            if pe != self._pessoa_de(reg):
                itens.append((f"Mover para {self._nome_pessoa(pe)}", "pessoa",
                              lambda pe=pe: self._mover_conta(id_conta, pessoa=pe)))
        itens.append(None)
        itens.append(("Criar perfil novo com esta conta…", "novo", lambda: self._mover_para_nova_pessoa(id_conta)))
        MenuTema(self, itens).abrir(evento.widget, (evento.x_root, evento.y_root))

    def _adicionar_pessoa(self):
        """Pede o nome e adiciona uma pessoa (numa transação)."""
        nome = self._pedir_nome("Adicionar pessoa", "Nome da pessoa (ex.: Pai, Mãe, Ana). As contas dela ficam "
                                                     "separadas das suas, dentro deste mesmo cofre.")
        if not nome or not self._nome_livre(nome):
            return
        def mudar():
            """Acrescenta a pessoa à lista do cofre."""
            lista = [p for p in self.cofre.meta.get("pessoas", []) if isinstance(p, str)]
            self.cofre.meta["pessoas"] = lista + [nome]
        if not self._transacao(mudar):
            return
        self.filtro_pessoa.set(nome)
        self.filtro_grupo.set("Todos")
        self.atualizar_lista()
        self._avisar(f'Pessoa "{nome}" adicionada. Use  Novo item  para criar contas dela.')

    def _menu_pessoa(self, event, pessoa):
        """Menu de clique direito de uma pessoa (renomear, remover)."""
        if not pessoa:
            return                              # "Eu" é o titular do cofre: não renomeia nem remove
        MenuTema(self, [("Renomear…", "editar", lambda: self._renomear_pessoa(pessoa)),
                        ("Remover pessoa…", "excluir", lambda: self._remover_pessoa(pessoa))]
                 ).abrir(event.widget, (event.x_root, event.y_root))

    def _renomear_pessoa(self, pessoa):
        """Pede o novo nome e renomeia a pessoa em todos os itens (numa transação)."""
        novo = self._pedir_nome("Renomear pessoa", f'Novo nome para "{pessoa}":', pessoa)
        if not novo or novo == pessoa or not self._nome_livre(novo, ignorar=pessoa):
            return
        def mudar():
            """Troca o nome da pessoa em todos os itens."""
            for r in self.cofre.registros:
                if self._pessoa_de(r) == pessoa:
                    r["pessoa"] = novo
            self.cofre.meta["pessoas"] = [novo if p == pessoa else p for p in self.cofre.meta.get("pessoas", [])]
        if not self._transacao(mudar):
            return
        if self.filtro_pessoa.get() == pessoa:
            self.filtro_pessoa.set(novo)
        self.atualizar_lista()

    def _remover_pessoa(self, pessoa):
        """Remove a pessoa depois de confirmar; os itens voltam ao titular."""
        contas = [r for r in self.cofre.registros if self._pessoa_de(r) == pessoa]
        msg = (f'Remover a pessoa "{pessoa}"?' + (f"\n\nAs {len(contas)} conta(s) dela NÃO são apagadas: "
                                                   f"passam para {self.TITULAR}." if contas else ""))
        if not messagebox.askyesno("Remover pessoa", msg, perigoso=True):
            return
        def mudar():
            """Passa os itens da pessoa para o titular e a tira da lista."""
            for r in self.cofre.registros:
                if self._pessoa_de(r) == pessoa:
                    r["pessoa"] = ""
            self.cofre.meta["pessoas"] = [p for p in self.cofre.meta.get("pessoas", []) if p != pessoa]
        if not self._transacao(mudar):
            return
        self.filtro_pessoa.set("*")
        self.atualizar_lista()

    def _menu_grupo(self, event, grupo):
        """Menu de clique direito de um grupo (renomear, transformar em pessoa)."""
        MenuTema(self, [("Transformar em pessoa", "pessoa", lambda: self._grupo_para_pessoa(grupo)),
                        ("Renomear grupo…", "editar", lambda: self._renomear_grupo(grupo)),
                        ("Remover grupo…", "excluir", lambda: self._remover_grupo(grupo))]
                 ).abrir(event.widget, (event.x_root, event.y_root))

    def _no_escopo(self, r):
        """True se o item pertence à pessoa selecionada no filtro."""
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
        ids = {r["id"] for r in contas}

        def mudar():
            """Converte o grupo em pessoa em todos os itens."""
            for r in self.cofre.registros:
                if r["id"] in ids:
                    r["pessoa"] = nome
                    r["grupo"] = ""
        if not self._transacao(mudar):
            return
        self.filtro_pessoa.set(nome)
        self.filtro_grupo.set("Todos")
        self.atualizar_lista()

    def _renomear_grupo(self, grupo):
        """Pede o novo nome e renomeia o grupo em todos os itens (numa transação)."""
        novo = self._pedir_nome("Renomear grupo", f'Novo nome para o grupo "{grupo}":', grupo)
        if not novo or novo == grupo:
            return
        contas = [r for r in self.cofre.registros if (r.get("grupo") or "").strip() == grupo and self._no_escopo(r)]
        ids = {r["id"] for r in contas}

        def mudar():
            """Troca o nome do grupo em todos os itens."""
            for r in self.cofre.registros:
                if r["id"] in ids:
                    r["grupo"] = novo
            for p in self._donos_do_escopo():
                self._guardar_grupos_vazios(p, [novo if g == grupo else g for g in self._grupos_vazios(p)])
        if not self._transacao(mudar):
            return
        if self.filtro_grupo.get() == grupo:
            self.filtro_grupo.set(novo)
        self.atualizar_lista()

    def _ao_escolher_grupo(self, event=None):
        """Filtra a lista pelo grupo escolhido na barra lateral."""
        sel = self.lateral.selection()
        if not sel:
            return
        alvo = {"__todos__": "Todos", "__sem__": "(sem grupo)", "__atencao__": "⚠ Atenção"}.get(sel[0])
        self.filtro_grupo.set(alvo if alvo else sel[0][2:])
        self.atualizar_lista(manter_lateral=True)

    # ---------- painel de detalhes ----------
    def _selecionado_silencioso(self):
        """Item selecionado, sem avisar quando não há."""
        sel = self.tree.selection() if hasattr(self, "tree") else ()
        return next((r for r in self.cofre.registros if sel and r["id"] == sel[0]), None) if self.cofre else None

    def _alternar_revelar(self, campo):
        """Mostra ou oculta um campo secreto no detalhe (item protegido pede a senha mestra)."""
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
                except tk.TclError:
                    pass
        else:
            if not self._liberar_protegido(r):
                return
            self._revelados.add(chave)
            timers[chave] = self.root.after(20000, lambda: (timers.pop(chave, None), self._revelados.discard(chave),
                                                            self._montar_detalhe()))
        self._montar_detalhe()

    # ---------- ações ----------
    # ---------- Ações do item: novo, editar, excluir, copiar ----------

    def novo(self):
        """Abre o formulário de item novo."""
        self.dialogo_registro(None)

    def editar(self):
        """Abre o formulário do item selecionado (item protegido pede a senha mestra)."""
        r = self._selecionado()
        if r and self._liberar_protegido(r):
            self.dialogo_registro(r)

    def excluir(self):
        """Exclui o item selecionado depois de confirmar (numa transação)."""
        r = self._selecionado()
        if r and messagebox.askyesno("Excluir", f'Excluir "{r.get("servico", "")}"?\n\nEsta ação não pode ser desfeita.\n'
                'As cópias automáticas (.bak1 a .bak5) e seus backups antigos ainda guardam este item, cifrado, '
                'até serem substituídos.', perigoso=True):
            rid = r["id"]
            self._transacao(lambda: self.cofre.registros.__delitem__(
                next(i for i, x in enumerate(self.cofre.registros) if x["id"] == rid)), forcar_copia=True)
            self.atualizar_lista()
            self._montar_detalhe()

    def copiar(self, campo):
        """Copia um campo do item selecionado (item protegido pede a senha mestra)."""
        r = self._selecionado()
        if not r or not self._liberar_protegido(r):
            return
        valor = r.get(campo, "")
        if not valor:
            self._avisar(f"Este item não tem {ROTULOS[campo]}.")
            return
        ok, texto = self._copiar_texto(valor, ROTULOS[campo])
        self._avisar(("📋 " + texto + "  Cole com Ctrl+V.") if ok else ("⚠ " + texto))
        return ok

    def _copiado(self, botao, com_texto=True, cor_icone=None):
        """Retorno visual no próprio botão: vira '✓ Copiado' por 2 segundos."""
        try:
            antes = (botao.cget("text"), botao.cget("image"))
            botao.config(image=imagem_icone(self.root, "ok", CORES["ok"]),
                         **({"text": " Copiado"} if com_texto else {}))

            def voltar():
                """Volta o botão ao texto normal depois de mostrar 'Copiado'."""
                try:
                    botao.config(text=antes[0], image=antes[1])
                except tk.TclError:
                    pass
            self._depois_do_widget(botao, 2000, voltar)
        except tk.TclError:
            pass

    def _copiar_codigo(self, codigo, botao, numero):
        """Copia UM código de recuperação (item protegido pede a senha mestra antes)."""
        r = self._selecionado()
        if not r or not self._liberar_protegido(r):
            return False
        ok, texto = self._copiar_texto(codigo, f"Código {numero}")
        self._avisar(("📋 " + texto + "  Cole com Ctrl+V.") if ok else ("⚠ " + texto))
        if ok:
            self._copiado(botao)
        return ok

    def _copiar_campo(self, entrada, botao, nome):
        """Copia o que está num campo de senha do formulário (a cópia pelo teclado continua bloqueada)."""
        try:
            valor = entrada.get()
        except tk.TclError:
            return
        if not valor:
            return
        ok, texto = self._copiar_texto(valor, nome)
        if ok:
            self._copiado(botao, com_texto=False)
        else:
            self._avisar("⚠ " + texto)

    def _texto_multilinha(self, pai, altura=4, mono=False, largura=40):
        """Caixa de texto de várias linhas no tema."""
        C = CORES
        t = tk.Text(pai, width=largura, height=altura, font="CofreMono" if mono else "CofreTexto",
                    exportselection=False, undo=False, relief="flat", bd=0, padx=10, pady=8,
                    bg=C["campo"], fg=C["texto"], insertbackground=C["texto"], highlightthickness=1,
                    highlightbackground=C["borda2"], highlightcolor=C["prim"], wrap="word")
        self._bloquear_copia(t)
        return t

    def dialogo_aparencia(self):
        """Escolhe um dos seis temas prontos e salva a preferência global neste computador."""
        d = self._nova_janela("Aparência e cores")
        self._modal(d)
        fr = ttk.Frame(d, padding=(_px(24), _px(18), _px(24), _px(18)))
        fr.pack(fill="both", expand=True)
        self._cabecalho_dialogo(fr, "config", "Aparência e cores",
                                "A escolha vale para todos os cofres neste computador.")
        ttk.Label(fr, text="Escolha um dos seis temas", style="Campo.TLabel").pack(anchor="w", pady=(8, 6))
        escolha = tk.StringVar(value=self.tema)

        for nome, paleta in PALETAS.items():
            linha = ttk.Frame(fr, style="Card2.TFrame", padding=(_px(10), _px(6)))
            linha.pack(fill="x", pady=2)
            ttk.Radiobutton(linha, text=nome, value=nome, variable=escolha).pack(side="left", anchor="w")
            amostras = tk.Canvas(linha, width=_px(104), height=_px(20), bg=CORES["sup2"], highlightthickness=0)
            amostras.pack(side="right")
            for i, cor in enumerate((paleta["fundo"], paleta["sup"], paleta["prim"], paleta["texto"])):
                x = _px(3 + i * 25)
                amostras.create_rectangle(x, _px(3), x + _px(18), _px(17), fill=cor, outline=paleta["borda2"])

        ttk.Separator(fr).pack(fill="x", pady=(16, 10))
        botoes = ttk.Frame(fr)
        botoes.pack(fill="x")
        ttk.Button(botoes, text="Cancelar", command=d.destroy).pack(side="right", padx=(8, 0))

        def aplicar_escolha():
            """Persiste o tema antes de reconstruir a interface com as novas cores."""
            nome = escolha.get()
            try:
                _salvar_preferencia_tema(nome)
            except OSError as ex:
                messagebox.showerror("Aparência", f"Não foi possível salvar a preferência global:\n{texto_erro(ex)}",
                                     parent=d)
                return

            estado = {
                "grupo": self.filtro_grupo.get(),
                "pessoa": self.filtro_pessoa.get(),
                "busca": self.busca.get(),
                "id": (self._selecionado_silencioso() or {}).get("id"),
            }
            _definir_tema(nome)
            self.tema = nome
            d.destroy()
            aplicar_tema(self.root)
            self.tela_principal()
            self.filtro_grupo.set(estado["grupo"])
            self.filtro_pessoa.set(estado["pessoa"])
            self.busca.set(estado["busca"])
            self.atualizar_lista()
            if estado["id"] is not None:
                try:
                    self.tree.selection_set(estado["id"])
                except tk.TclError:                    # o item não aparece com o filtro atual: não é motivo para travar
                    pass

        ttk.Button(botoes, text="Aplicar", command=aplicar_escolha, style="Primario.TButton").pack(side="right")
        d.bind("<Escape>", lambda e: d.destroy())

    # ---------- Diálogo de edição/criação de um item (o formulário completo) ----------

    def dialogo_registro(self, reg, senha_inicial=None):
        """Formulário de um item (novo ou edição): campos, gerador de senha, grupo, pessoa e proteção; limpa o texto digitado antes de gravar.
        'senha_inicial' (só em item novo): senha já preenchida, vinda do botão "Usar em um novo item" do gerador."""
        C = CORES
        if self.cofre is None:             # o cofre acabou de bloquear: não abre formulário sobre um cofre fechado
            return None
        d = self._nova_janela("Editar item" if reg else "Novo item")
        self._modal(d)
        rodape = ttk.Frame(d, padding=(_px(26), _px(8), _px(26), _px(16)))
        rodape.pack(side="bottom", fill="x")          # Salvar/Cancelar ficam SEMPRE visíveis (fora da rolagem)
        fr = self._corpo_dialogo(d, (20, 16, 20, 10), rodape=rodape)
        d._altura_padrao = _px(760)               # tamanho PADRAO fixo: nao muda quando as credenciais extras ficam ocultas
        campos = {}
        self._cabecalho_dialogo(
            fr, "editar" if reg else "novo", "Editar item" if reg else "Novo item",
            "Apenas Conta / App é obrigatória")
        linha_acoes = ttk.Frame(fr)
        linha_acoes.pack(fill="x", pady=(0, 8))
        status = tk.BooleanVar(value=_item_ativo(reg) if reg else True)
        estilo_status = ttk.Style(d)
        estilo_status.configure("StatusAtiva.TButton", foreground=C["ok"], padding=(_px(10), _px(5)))
        estilo_status.configure("StatusInativa.TButton", foreground=C["fraco"], padding=(_px(10), _px(5)))
        estilo_status.configure("AjudaItem.TButton", foreground=C["fraco"], padding=(_px(2), _px(2)))
        bt_status = ttk.Button(linha_acoes, style="StatusAtiva.TButton")
        if reg:                                   # item NOVO nasce "em uso" sem botao; so a edicao permite marcar inativa
            bt_status.pack(side="right", padx=(8, 0))

        def atualizar_status():
            """Atualiza a etiqueta de estado sem alterar os demais dados do item."""
            ativa = status.get()
            bt_status.configure(text="Ativa" if ativa else "Desativada",
                                style="StatusAtiva.TButton" if ativa else "StatusInativa.TButton")

        bt_status.configure(command=lambda: (status.set(not status.get()), atualizar_status()))
        self._dica(bt_status, "Indica se você ainda usa esta conta. Marcar como desativada só muda o rótulo: "
                              "não apaga a senha nem bloqueia o acesso; o item continua salvo e pode ser reativado.")
        atualizar_status()
        bt_tour = ttk.Button(linha_acoes, text="?", style="AjudaItem.TButton")
        bt_tour.pack(side="right")
        self._dica(bt_tour, "Como preencher: um passeio guiado explicando cada campo do formulário.")

        # Conta / grupo / login
        topo = ttk.Frame(fr, style="Card.TFrame", padding=(_px(14), _px(12)))
        topo.pack(fill="x")
        topo.columnconfigure(0, weight=3)
        topo.columnconfigure(1, weight=2)
        ttk.Label(topo, text="IDENTIFICAÇÃO E ORGANIZAÇÃO", style="C.Campo.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Label(topo, text=ROTULOS["servico"].upper() + " *", style="C.Campo.TLabel").grid(
            row=1, column=0, sticky="w")
        ttk.Label(topo, text="GRUPO / CATEGORIA", style="C.Campo.TLabel").grid(
            row=1, column=1, sticky="w", padx=(12, 0))
        linha_servico = ttk.Frame(topo, style="C.TFrame")
        linha_servico.grid(row=2, column=0, sticky="ew", pady=(4, 12))
        linha_servico.columnconfigure(0, weight=1)
        ent = ttk.Entry(linha_servico, width=30, style="C.TEntry")
        ent.grid(row=0, column=0, sticky="ew")
        campos["servico"] = ent
        self._pista_entrada(ent, "Ex.: Instagram, banco ou aplicativo")
        prev_marca = ttk.Label(linha_servico, style="C.TLabel")
        prev_marca.grid(row=0, column=1, padx=(8, 0))
        lista_marcas = tk.Frame(topo, bg=C["sup"], highlightthickness=1,
                                highlightbackground=C["borda"])
        lista_marcas.grid(row=3, column=0, sticky="ew", pady=(0, 4))
        autocompletar = AutocompletarMarcas(ent, prev_marca, lista_marcas)
        NOVO_GRUPO = "＋ Criar novo grupo…"        # 1ª opção da lista: o usuário escolhe o próprio nome de grupo
        cg = ttk.Combobox(topo, width=20, values=[NOVO_GRUPO] + list(self._grupos_sugeridos()),
                          style="C.TCombobox")
        cg.grid(row=2, column=1, sticky="ew", padx=(12, 0), pady=(4, 12))
        dica_grupo = ttk.Label(topo, text="", style="C.Fraco.TLabel", wraplength=_px(220), justify="left")

        def escolheu_grupo(event=None):
            """Ao escolher '＋ Criar novo grupo…': limpa o campo e deixa digitar o nome que quiser."""
            if cg.get() == NOVO_GRUPO:
                cg.set("")
                cg.focus_set()
                dica_grupo.config(text="Digite o nome do seu grupo. Ele é criado ao salvar.")
                dica_grupo.grid(row=3, column=1, sticky="w", padx=(12, 0), pady=(0, 6))
        cg.bind("<<ComboboxSelected>>", escolheu_grupo)
        sugestao_grupo = ttk.Label(topo, text="", style="C.Fraco.TLabel", wraplength=_px(220), justify="left",
                                   cursor="hand2", foreground=C["prim_txt"])

        def atualizar_sugestao(event=None):
            """Recomenda um grupo pelo tipo da conta digitada. So aparece com o campo Grupo vazio; um clique aceita,
            e digitar o grupo por conta propria faz a sugestao sumir. Nada e preenchido sem o usuario aceitar."""
            try:
                recomendado = None
                if not cg.get().strip() and not dica_grupo.grid_info():
                    recomendado = self._nome_grupo_recomendado(campos["servico"].get())
                if recomendado:
                    sugestao_grupo.config(text=f"Sugestão: {recomendado}  (clique para usar)")
                    sugestao_grupo._valor = recomendado
                    sugestao_grupo.grid(row=3, column=1, sticky="w", padx=(12, 0), pady=(0, 6))
                else:
                    sugestao_grupo.grid_remove()
            except (tk.TclError, KeyError):
                pass

        ajustar_grupo_bancario = [None]            # preenchido no fim do formulario (ajustar_bancarios)

        def aceitar_sugestao(event=None):
            """Usa o grupo recomendado."""
            valor = getattr(sugestao_grupo, "_valor", "")
            if valor:
                cg.delete(0, "end")
                cg.insert(0, valor)
                getattr(cg, "_pista_atualizar", lambda: None)()
                if ajustar_grupo_bancario[0]:
                    ajustar_grupo_bancario[0]()
            sugestao_grupo.grid_remove()
        sugestao_grupo.bind("<Button-1>", aceitar_sugestao)
        cg.bind("<<ComboboxSelected>>", lambda e: atualizar_sugestao(), add="+")
        cg.bind("<KeyRelease>", atualizar_sugestao, add="+")
        cg.insert(0, (reg or {}).get("grupo", "") or (self.filtro_grupo.get()
                                                     if self.filtro_grupo.get() not in ("Todos", "(sem grupo)", "⚠ Atenção")
                                                     else ""))
        campos["grupo"] = cg
        campos["servico"].bind("<KeyRelease>", atualizar_sugestao, add="+")
        campos["servico"].bind("<FocusOut>", atualizar_sugestao, add="+")
        _escolher_marca = autocompletar.escolher

        def _escolher_marca_e_sugerir(indice):
            """Escolher a marca na lista tambem atualiza a recomendacao de grupo."""
            _escolher_marca(indice)
            atualizar_sugestao()
        autocompletar.escolher = _escolher_marca_e_sugerir
        atualizar_sugestao()
        ttk.Label(topo, text="LOGIN / E-MAIL / USUÁRIO", style="C.Campo.TLabel").grid(
            row=4, column=0, sticky="w")
        ttk.Label(topo, text="PESSOA (PERFIL)", style="C.Campo.TLabel").grid(
            row=4, column=1, sticky="w", padx=(12, 0))
        ent = ttk.Entry(topo, width=30, style="C.TEntry")
        ent.grid(row=5, column=0, sticky="ew", pady=(4, 0))
        campos["login"] = ent
        self._pista_entrada(ent, "Ex.: usuario@exemplo.com")
        NOVO_PESSOA = "＋ Criar novo perfil…"       # mesma ideia do grupo: 1ª opção da lista deixa claro que dá
                                                     # para criar um perfil novo (reclamação real do usuário: a
                                                     # lista de sugestões parecia fechada, sem jeito de adicionar)
        cp = ttk.Combobox(topo, width=20, values=[NOVO_PESSOA] + [self._nome_pessoa(x) for x in self._pessoas()],
                          style="C.TCombobox")
        cp.grid(row=5, column=1, sticky="ew", padx=(12, 0), pady=(4, 0))
        if reg:
            cp.insert(0, self._nome_pessoa(self._pessoa_de(reg)))
        else:
            fp = self.filtro_pessoa.get()
            cp.insert(0, self._nome_pessoa("" if fp == "*" else fp))

        def escolheu_pessoa(event=None):
            """Ao escolher '＋ Criar novo perfil…': limpa o campo e deixa digitar o nome que quiser (igual ao grupo)."""
            if cp.get() == NOVO_PESSOA:
                cp.set("")
                cp.focus_set()
        cp.bind("<<ComboboxSelected>>", escolheu_pessoa)
        self._dica(cp, "De quem é esta conta. Escolha da lista, ou '＋ Criar novo perfil…' / digite um nome novo.")
        self._pista_entrada(cg, "Ex.: Bancos, Redes sociais")
        self._pista_entrada(cp, "Ex.: Eu, família")
        if reg:
            campos["servico"].insert(0, reg.get("servico", ""))
            campos["login"].insert(0, reg.get("login", ""))
            autocompletar.atualizar_previsualizacao()
            for chave in ("servico", "login"):
                getattr(campos[chave], "_pista_atualizar", lambda: None)()

        # Credenciais secretas
        credenciais = ttk.Frame(fr, style="Card.TFrame", padding=(_px(14), _px(12)))
        credenciais.pack(fill="x", pady=(12, 0))
        cab_seg = ttk.Frame(credenciais, style="C.TFrame")
        cab_seg.pack(fill="x")
        ttk.Label(cab_seg, text="CREDENCIAIS SECRETAS", style="C.Campo.TLabel").pack(side="left")
        mostrar = tk.BooleanVar(value=False)
        ttk.Checkbutton(cab_seg, text="Mostrar", variable=mostrar, style="C.Switch.TCheckbutton",
                        command=lambda: alternar()).pack(side="right")
        cab_seg.pack_configure(pady=(0, 10))          # o seletor e o botao "+ Adicionar" ficam na linha logo abaixo (cab_add)
        CAMPOS_EXTRA = (("codigos", "Código de recuperação"), ("pin", "PIN"), ("senha_extra", "Senha extra"),
                        ("chave", "Chave / token"), ("numero_conta", "Número da conta"), ("agencia", "Agência"))
        tem = {k: tk.BooleanVar(value=bool(reg and (reg.get(k) or "").strip())) for k, _ in CAMPOS_EXTRA}
        rótulos_extra = {
            "codigos": "Códigos de recuperação",
            "senha_extra": "Senha extra",
            "pin": "PIN numérico",
            "chave": "Chave / token",
            "numero_conta": "Número da conta",
            "agencia": "Agência",
        }
        # o seletor e o botao ficam numa linha PROPRIA abaixo do titulo: na mesma linha de "CREDENCIAIS SECRETAS" e do
        # "Mostrar" nao sobra largura e o botao "+ Adicionar credencial" era cortado (63 px de 173 px pedidos)
        cab_add = ttk.Frame(credenciais, style="C.TFrame")
        cab_add.pack(fill="x", pady=(0, 10))
        cab_seg.pack_configure(pady=(0, 4))
        selecao_credencial = ttk.Combobox(
            cab_add, state="readonly", width=24,
            values=[rótulos_extra[k] for k, _ in CAMPOS_EXTRA if not tem[k].get()],
            style="C.TCombobox")

        def atualizar_seletor_credenciais():
            """Lista apenas as credenciais ainda não adicionadas ao formulário."""
            opcoes = [rótulos_extra[k] for k, _ in CAMPOS_EXTRA if not tem[k].get()]
            selecao_credencial.configure(values=opcoes)
            if opcoes:
                if selecao_credencial.get() not in opcoes:
                    selecao_credencial.set(opcoes[0])
                botao_adicionar.configure(state="normal")
            else:
                selecao_credencial.set("Todas adicionadas")
                botao_adicionar.configure(state="disabled")

        def adicionar_credencial():
            """Inclui no formulário a credencial selecionada."""
            escolhida = selecao_credencial.get()
            chave = next((k for k, rot in rótulos_extra.items() if rot == escolhida), None)
            if chave is not None:
                tem[chave].set(True)
                aplicar_campos()

        botao_adicionar = ttk.Button(cab_add, text="+ Adicionar credencial", style="Acao.TButton",
                                     command=adicionar_credencial)
        botao_adicionar.pack(side="right", padx=(8, 0))
        selecao_credencial.pack(side="right")
        grade = ttk.Frame(credenciais, style="S2.TFrame")
        grade.pack(fill="x")
        grade.columnconfigure(0, weight=1, uniform="s")
        grade.columnconfigure(1, weight=1, uniform="s")
        secretos = []
        grupos_campo = {k: [] for k in ("pin", "senha_extra", "chave", "numero_conta", "agencia")}   # widgets de
                                                                                            # cada campo extra
        dicas_item = PainelForca(credenciais, self, largura=_px(660), pref="C.", compacto=True)
        for i, chave in enumerate(("senha", "senha_extra", "pin", "chave", "numero_conta", "agencia")):
            if chave == "senha":                   # Senha Principal: caixa propria, na largura toda (como no modelo)
                col, lin, vao, px = 0, 0, 2, (0, 0)
            else:                                   # credenciais extras: abaixo, em 2 colunas
                j_ = i - 1
                col, lin, vao = j_ % 2, 3 + (j_ // 2) * 3, 1
                px = (0, 10) if col == 0 else (10, 0)
            cab_campo = ttk.Frame(grade, style="S2.TFrame")
            cab_campo.grid(row=lin, column=col, columnspan=vao, sticky="ew", padx=px)
            rot_c = ttk.Label(cab_campo, text=ROTULOS[chave].upper(), style="S2.Campo.TLabel")
            rot_c.pack(side="left")
            grupo_campo = []
            if chave != "senha":
                bt_remover = ttk.Button(cab_campo, text="×", style="Icone.TButton", width=2,
                                        command=lambda k=chave: (tem[k].set(False), aplicar_campos()))
                bt_remover.pack(side="right")
                grupo_campo.extend((cab_campo, bt_remover))
                grupos_campo[chave].extend((cab_campo, bt_remover))
            linha = ttk.Frame(grade, style="S2.TFrame")
            linha.grid(row=lin + 1, column=col, columnspan=vao, sticky="ew", padx=px, pady=(4, 0))
            if chave != "senha":
                grupos_campo[chave].append(linha)
            caixa, ent = self._linha_secreta(linha, 18, olho=False, pref="S2.")
            caixa.pack(side="left", fill="x", expand=True)
            if reg:
                ent.insert(0, reg.get(chave, ""))
                getattr(ent, "_pista_atualizar", lambda: None)()
            campos[chave] = ent
            secretos.append(ent)
            if reg:          # item novo: copiar o que acabou de digitar não serve; só a edição tem "Copiar"
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
                med = self._medidor(grade, ent, pin=(chave == "pin"), dicas_lbl=dicas_item,
                                    pref="S2.", titulo=ROTULOS[chave])
                med.grid(row=lin + 2, column=col, columnspan=vao, sticky="w", padx=px, pady=(6, 12))
                if chave != "senha":
                    grupos_campo[chave].append(med)
            else:
                ttk.Frame(grade, style="S2.TFrame", height=8).grid(row=lin + 2, column=col)
        dicas_item.pack(fill="x", pady=(6, 0))
        if senha_inicial and not reg:
            campos["senha"].insert(0, senha_inicial)
            getattr(campos["senha"], "_pista_atualizar", lambda: None)()
        for _k in ("senha", "senha_extra", "pin"):
            campos[_k].event_generate("<<AtualizarJa>>")      # painéis de força já prontos no 1º quadro

        extras = ttk.Frame(credenciais, style="S2.TFrame", padding=(_px(2), _px(8), _px(2), 0))
        ttk.Label(extras, text=ROTULOS["codigos"].upper(), style="S2.Campo.TLabel").pack(anchor="w", pady=(4, 4))
        extras_notas = ttk.Frame(fr, style="Card.TFrame", padding=(_px(14), _px(12)))
        extras_notas.pack(fill="x", pady=(12, 0))
        fc = ttk.Frame(extras, style="S2.TFrame")
        fc.pack(fill="x")
        codigos = self._texto_multilinha(fc, 8, mono=True)
        atualizar_pista_codigos = self._pista_texto(codigos, "Um código de recuperação por linha")
        barra_cod = ttk.Frame(fc, style="S2.TFrame")
        cont_cod = ttk.Label(barra_cod, text="", style="S2.Fraco.TLabel")

        def contar_codigos(event=None):
            """Mostra quantos códigos há na caixa (um por linha)."""
            n = len([x for x in codigos.get("1.0", "end").splitlines() if x.strip()])
            cont_cod.config(text=f"{n} código(s)  —  um por linha")

        def colar_varios():
            """Cola vários códigos de uma vez: separa por linha, vírgula ou ponto e vírgula, tira repetidos e
            limpa a área de transferência em seguida."""
            try:
                bruto = self.root.clipboard_get()
            except tk.TclError:
                messagebox.showinfo("Colar códigos", "Não há texto copiado. Copie os códigos (do site ou do PDF) "
                                    "e clique de novo.", parent=d)
                return
            novos = [x.strip() for x in re.split(r"[\r\n,;]+", bruto) if x.strip()]
            atuais = [x.strip() for x in codigos.get("1.0", "end").splitlines() if x.strip()]
            novos = [x for x in dict.fromkeys(novos) if x not in atuais]
            if not novos:
                messagebox.showinfo("Colar códigos", "Nenhum código novo no texto copiado.", parent=d)
                return
            if codigos.get("1.0", "end").strip():
                codigos.insert("end", "\n" if not codigos.get("1.0", "end").endswith("\n\n") else "")
            codigos.insert("end", "\n".join(novos))
            atualizar_pista_codigos()
            contar_codigos()
            try:
                self.root.clipboard_clear()
                if EH_WINDOWS:
                    limpar_clipboard_windows()
            except tk.TclError:
                pass
            cont_cod.config(text=f"+{len(novos)} código(s) colado(s); área de transferência limpa")

        ttk.Button(barra_cod, text="Colar vários códigos", style="Acao.TButton", command=colar_varios).pack(side="left")
        cont_cod.pack(side="left", padx=12)
        codigos.bind("<KeyRelease>", contar_codigos, add="+")
        contar_codigos()
        oculto = ttk.Label(fc, text="••••••   (oculto — ligue Mostrar)" if (reg or {}).get("codigos")
                           else "(vazio — ligue Mostrar para preencher)", style="S2.Fraco.TLabel")
        oculto.pack(anchor="w", pady=(2, 0))
        if reg:
            codigos.insert("1.0", reg.get("codigos", ""))
            atualizar_pista_codigos()

        timer_mostrar = {"t": None}

        def alternar():
            """Mostra ou oculta os campos secretos do formulário."""
            if timer_mostrar["t"]:
                try:
                    d.after_cancel(timer_mostrar["t"])
                except (tk.TclError, ValueError):
                    pass
                timer_mostrar["t"] = None
            s = "" if mostrar.get() else "•"
            for e in secretos:
                e.config(show=s)
            if mostrar.get():
                oculto.pack_forget()
                barra_cod.pack(fill="x", pady=(0, 6))
                codigos.pack(fill="x")
                atualizar_pista_codigos()
                timer_mostrar["t"] = self._depois_do_widget(
                    d, self.MOSTRAR_SENHA_MS, lambda: (mostrar.set(False), alternar()))   # volta a esconder
            else:
                codigos.pack_forget()
                barra_cod.pack_forget()
                oculto.pack(anchor="w", pady=(2, 0))
            self._recalcular_dialogo(d)

        ttk.Label(extras_notas, text="NOTAS / OBSERVAÇÕES", style="C.Campo.TLabel").pack(anchor="w", pady=(2, 4))
        notas = self._texto_multilinha(extras_notas, 2)
        notas.pack(fill="x")
        atualizar_pista_notas = self._pista_texto(notas, "Anotações importantes sobre esta conta…")
        if reg:
            notas.insert("1.0", reg.get("notas", ""))
            atualizar_pista_notas()

        def salvar():
            """Valida e grava o item (novo ou editado) numa transação e fecha o formulário."""
            dados = {k: _limpar_texto(e.get()).strip() if k in ("grupo", "servico", "login") else e.get()
                     for k, e in campos.items()}       # títulos sem controles/bidi (RLO forja nomes na lista)
            if dados.get("grupo", "").startswith("＋"):      # a opção "criar novo" nunca vira nome de grupo
                dados["grupo"] = ""
            dados["codigos"] = codigos.get("1.0", "end").strip("\n")
            dados["notas"] = notas.get("1.0", "end").rstrip("\n")
            dados["pessoa"] = _limpar_texto(self._valor_pessoa(cp.get())).strip()
            dados["ativo"] = status.get()
            if not dados["servico"]:
                erro_validacao.pack(side="left")
                campos["servico"].focus_set()
                return
            erro_validacao.pack_forget()
            if reg:
                rid = reg["id"]

                def mudar():
                    """Aplica os dados do formulário ao item (novo ou existente)."""
                    alvo = next(r for r in self.cofre.registros if r["id"] == rid)
                    alvo.update(dados)
                if not self._transacao(mudar):
                    return
            else:
                item = novo_item(**dados)
                if not self._transacao(lambda: self.cofre.registros.append(item)):
                    return
            self.atualizar_lista()
            if not reg:
                self.tree.selection_set(item["id"])
            d.destroy()

        ancora = ttk.Frame(fr, height=1)     # ponto de referência: campos extras entram antes dele
        ancora.pack(fill="x")
        extras_notas.pack(fill="x", before=ancora)
        ttk.Separator(rodape).pack(fill="x", pady=(0, 10))
        rod = ttk.Frame(rodape)
        rod.pack(fill="x")
        erro_validacao = ttk.Label(rod, text="Informe o nome da Conta / App para salvar.", foreground=C["perigo"])

        # ---- modo simples x completo (revelação progressiva) ----
        def aplicar_campos():
            """Atualiza a lista e a visibilidade das credenciais extras."""
            for k, grupo in grupos_campo.items():
                for w in grupo:
                    try:
                        w.grid() if tem[k].get() else w.grid_remove()
                    except tk.TclError:
                        pass
            atualizar_seletor_credenciais()
            extras.pack_forget()
            if tem["codigos"].get():
                extras.pack(fill="x")
            self._recalcular_dialogo(d)

        ttk.Button(rod, text="Salvar item", command=salvar, style="Primario.TButton",
                   image=imagem_icone(self.root, "ok", "#ffffff"), compound="left").pack(side="right")
        ttk.Button(rod, text="Cancelar", command=d.destroy).pack(side="right", padx=8)
        campos["servico"].focus_set()

        def passeio_formulario():
            """Passeio guiado do formulário de item: o que escrever em cada campo."""
            passos = [
                (lambda: campos["servico"], "Conta / App",
                 "Nome do site, app ou cartão (ex.: Banco Azul). É o único campo obrigatório."),
                (lambda: campos["grupo"], "Grupo (categoria)",
                 "Escolha uma sugestão (Banco, Compras, Redes sociais...) ou DIGITE um nome novo: o grupo é criado "
                 "sozinho. Serve para organizar a lista."),
                (lambda: campos["login"], "Login", "Usuário, e-mail ou número da conta."),
                (lambda: cp, "Pessoa (perfil)",
                 "De quem é esta conta: 'Eu' ou outro perfil (Pai, Mãe...). Digite um nome novo para criar o perfil."),
                (lambda: campos["senha"], "Senha",
                 "Digite ou use o botão de gerar para criar uma senha forte. Enquanto você digita, a barra mostra a força "
                 "e quanto tempo levaria para quebrar."),
                (lambda: campos["numero_conta"], "Número da conta / Agência",
                 "Dados bancários: ficam ocultos como senha e SEMPRE pedem a senha mestra de novo para ver, copiar "
                 "ou editar -- mesmo com a proteção extra desligada para o resto do cofre."),
                (lambda: fc, "Códigos de recuperação",
                 "Guarde aqui os códigos de reserva do site (vários, um por linha). Ligue 'Mostrar' e use 'Colar vários "
                 "códigos' para colar todos de uma vez."),
                (lambda: notas, "Notas", "Qualquer observação: perguntas de segurança, endereço, número do cartão..."),
                (lambda: rod, "Salvar",
                 "Clique em Salvar para guardar (tudo fica criptografado). A proteção extra -- pedir a senha mestra "
                 "de novo para ver ou copiar -- agora é um ajuste só, para o cofre todo: '⋯ → Segurança → Proteção "
                 "extra'."),
            ]
            TourGuiado(self, d, passos).iniciar()
        def passeio_com_tudo():
            """O passeio fala de todos os campos: abre o modo completo antes de começar."""
            for v_ in tem.values():
                v_.set(True)
            aplicar_campos()
            passeio_formulario()
        bt_tour.config(command=passeio_com_tudo)
        aplicar_campos()

        def ajustar_bancarios(event=None):
            """Grupo de banco/financas: mostra Numero da conta e Agencia (como no modelo). Sair do grupo nao apaga nada."""
            try:
                nome_g = chave_ordem_alfabetica(cg.get())
            except tk.TclError:
                return
            if "banc" in nome_g or "financ" in nome_g:
                mudou = False
                for k_ in ("numero_conta", "agencia"):
                    if not tem[k_].get():
                        tem[k_].set(True)
                        mudou = True
                if mudou:
                    aplicar_campos()
        for seq_ in ("<KeyRelease>", "<<ComboboxSelected>>", "<FocusOut>"):
            cg.bind(seq_, ajustar_bancarios, add="+")
        ajustar_grupo_bancario[0] = ajustar_bancarios
        d.bind("<Return>", lambda e: salvar() if e.widget.winfo_class() in ("TEntry", "Entry", "TCombobox") else None)
        d.bind("<Destroy>", lambda e: (self._tour.encerrar() if getattr(self, "_tour", None) and e.widget is d else None), add="+")


    # ---------- Senha mestra, chave de acesso e planilha-modelo ----------

    def _confirmar_senha_atual(self, titulo):
        """Pede a senha mestra de novo e confere (operações sensíveis)."""
        atual = self._pedir_senha(titulo, "Confirme a senha mestra atual:")
        if atual is None:
            return False
        self._ocupado(True)
        try:
            cof = self.cofre
            ok = cof is not None and self._com_espera(lambda: cof.confere_senha(atual), "Verificando a senha…")
            zerar_objeto(atual)
        except MemoryError:
            self._ocupado(False)
            messagebox.showerror("Memória insuficiente", "Faltou memória livre para verificar a senha (a blindagem Máxima usa 1 GB). Feche o navegador e outros programas e tente de novo.")
            return False
        self._ocupado(False)
        if not ok:
            messagebox.showerror("Erro", "Senha mestra incorreta.")
            return False
        return atual

    def trocar_senha(self):
        """Troca a senha mestra (e a chave dos dados), depois de pedir a senha atual."""
        if not self._confirmar_senha_atual("Trocar senha"):
            return
        chave_txt = None
        if self.cofre.modo == MODO_OU and self.cofre._kb is None:
            resp = self._pedir_senha("Trocar senha",
                                     "Para trocar a senha, o cofre também renova a chave interna dos dados e "
                                     "precisa refazer o cadeado da chave de acesso.\n\nDigite a sua chave de "
                                     "acesso atual para MANTER a mesma. Se não a tiver aqui, deixe em branco: "
                                     "será criada uma chave NOVA (a antiga deixa de valer).")
            if resp is None:
                return
            chave_txt = resp.strip() or None
        nova = self._pedir_senha("Trocar senha", f"Nova senha (mín. {MIN_SENHA} caracteres):", medidor=True)
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
        chave_nova = None
        try:
            cof = self.cofre
            chave_nova = self._com_espera(lambda: cof.trocar_senha(nova, chave_acesso=chave_txt),
                                          "Trocando a senha e recifrando…")
        except ChaveMalFormada as ex:
            self._ocupado(False)
            messagebox.showerror("Chave de acesso", f"{ex}\n\nNada foi alterado.")
            return
        except MemoryError:
            self._ocupado(False)
            messagebox.showerror("Memória insuficiente", "Faltou memória livre para trocar a senha. Feche "
                                 "outros programas e tente de novo. A senha antiga continua valendo.")
            return
        except OSError as ex:
            self._ocupado(False)
            messagebox.showerror("Erro", f"Não foi possível gravar o cofre:\n{texto_erro(ex)}")
            return
        self._ocupado(False)
        messagebox.showinfo("Pronto", "Senha mestra alterada e a chave interna dos dados foi RENOVADA: a "
                            "senha antiga não abre mais este cofre, nem com uma cópia antiga do arquivo "
                            "em mãos. " + (("ATENÇÃO: não consegui apagar estas cópias antigas, que ainda abrem com a "
                                            "senha velha: " + ", ".join(self.cofre.copias_nao_apagadas) + ". Apague-as à mão.\n\n")
                                           if getattr(self.cofre, "copias_nao_apagadas", None)
                                           else "As cópias automáticas antigas foram apagadas. ") +
                            "Backups SEUS, feitos antes, continuam abrindo com a senha antiga: refaça o backup.")
        if chave_nova:
            self.mostrar_chave_acesso(chave_nova, self.cofre.modo)

    def nova_chave(self):
        """Gera uma nova chave de acesso depois de confirmar e pedir a senha."""
        if not messagebox.askyesno("Nova chave de acesso",
                                   "Gerar uma nova chave de acesso?\n\nA chave atual (e arquivos .key "
                                   "antigos) deixarão de abrir este cofre, e a chave interna dos dados é "
                                   "renovada. Backups seus, feitos antes, continuam abrindo com a chave antiga.", perigoso=True):
            return
        senha = self._confirmar_senha_atual("Nova chave de acesso")
        if not senha:
            return
        self._ocupado(True)
        try:
            cof = self.cofre
            chave = self._com_espera(lambda: cof.gerar_nova_chave_acesso(senha), "Gerando a nova chave…")
        except MemoryError:
            self._ocupado(False)
            messagebox.showerror("Memória insuficiente", "Faltou memória livre. Feche outros programas e "
                                 "tente de novo. A chave antiga continua valendo.")
            return
        except (OSError, ChaveMalFormada, ValueError) as ex:
            self._ocupado(False)
            messagebox.showerror("Erro", f"Não foi possível gerar a nova chave:\n{texto_erro(ex)}")
            return
        self._ocupado(False)
        self.mostrar_chave_acesso(chave, self.cofre.modo)

    def adicionar_chave_acesso(self, novo_modo):
        """Cofre 'so senha': adiciona a chave de acesso depois de criado (tela Seguranca adicional)."""
        if self.cofre is None or self.cofre.modo != MODO_S:
            return
        nome = "senha E chave (dois fatores)" if novo_modo == MODO_E else "senha OU chave"
        if not messagebox.askyesno("Adicionar chave de acesso",
                                   f"Adicionar uma chave de acesso a este cofre ({nome})?\n\n"
                                   "Uma chave nova será mostrada UMA vez: guarde-a fora do pendrive. A chave interna "
                                   "dos dados é renovada e as cópias automáticas antigas são apagadas. Backups seus, "
                                   "feitos antes, continuam abrindo só com a senha."):
            return
        senha = self._confirmar_senha_atual("Adicionar chave de acesso")
        if not senha:
            return
        self._ocupado(True)
        try:
            cof = self.cofre
            chave = self._com_espera(lambda: cof.adicionar_chave_acesso(novo_modo, senha), "Adicionando a chave…")
        except MemoryError:
            self._ocupado(False)
            messagebox.showerror("Memória insuficiente", "Faltou memória livre. Feche outros programas e tente de "
                                 "novo. O cofre continua como estava.")
            return
        except (OSError, ChaveMalFormada, ValueError) as ex:
            self._ocupado(False)
            messagebox.showerror("Erro", f"Não foi possível adicionar a chave:\n{texto_erro(ex)}\n\n"
                                 "O cofre continua como estava.")
            return
        self._ocupado(False)
        self.mostrar_chave_acesso(chave, self.cofre.modo)
        try:
            self.tela_principal()            # refaz menus e indicadores (agora existe 'Nova chave de acesso')
        except tk.TclError:
            pass

    # ---------- importação de planilha ----------
    def modelo_planilha(self):
        """Salva a planilha modelo para importação."""
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
            try:
                c_ = self.cofre
                selo_ = (c_.sal_k, c_.nonce_k, c_.wrap_k)         # ata a planilha a ESTE cofre (selo de autenticidade)
            except AttributeError:
                selo_ = None
            criar_modelo_planilha(destino, selo_)
        except ImportError:
            messagebox.showerror("Erro", "Falta a biblioteca de Excel. Rode:  pip install openpyxl defusedxml")
            return
        except OSError as ex:
            messagebox.showerror("Erro", f"Não foi possível salvar:\n{texto_erro(ex)}")
            return
        messagebox.showinfo("Modelo criado",
                            "Abra o arquivo no Excel:\n\n"
                            "1) Leia a aba 'Leia-me' (1 minuto).\n"
                            "2) Preencha a aba 'Senhas': uma linha por conta. As linhas EXEMPLO mostram como usar "
                            "vários perfis (Eu, Pai, Mãe), grupos (Bancos, Compras...) e vários códigos de "
                            "recuperação. O cofre ignora as linhas EXEMPLO.\n"
                            "3) Salve, volte aqui e use  ⋯  >  Importar planilha.\n"
                            "4) Depois de importar, APAGUE a planilha: ela guarda as senhas sem criptografia.")

    def importar(self):
        """Lê uma planilha ou CSV e mostra a prévia da importação."""
        arq = filedialog.askopenfilename(title="Importar senhas de planilha",
                                         filetypes=[("Planilhas", "*.xlsx *.xlsm *.csv"),
                                                    ("Excel", "*.xlsx *.xlsm"), ("CSV", "*.csv")])
        if not arq:
            return
        self._ocupado(True)
        try:
            try:
                c_ = self.cofre
                selo_ = (c_.sal_k, c_.nonce_k, c_.wrap_k)
            except AttributeError:
                selo_ = None
            novos, avisos = ler_planilha(arq, selo=selo_, exigir_selo=IMPORTAR_SOMENTE_COM_SELO)
        except (ValueError, OSError) as ex:
            self._ocupado(False)
            messagebox.showerror("Importar planilha", texto_erro(ex))
            return
        self._ocupado(False)
        if not novos:
            messagebox.showinfo("Importar planilha", "Nenhuma conta encontrada para importar.\n\n"
                                "• Se você só abriu o modelo, falta preencher: as linhas EXEMPLO são ignoradas.\n"
                                "• A primeira linha precisa ter os títulos (Conta / App, Login, Senha...).\n"
                                "• Para ver o passo a passo, use  ⋯  >  Baixar modelo de planilha  e leia a aba "
                                "'Leia-me'.")
            return
        inserir, iguais, conflitos = classificar_importacao(self.cofre.registros, novos)
        self._previa_importacao(arq, inserir, iguais, conflitos, avisos)

    # ---------- Importação de planilha: prévia, avisos e conferência ----------

    def _previa_importacao(self, arq, inserir, iguais, conflitos, avisos):
        """Mostra a prévia da importação (novos, iguais e conflitos) e deixa escolher o que entra antes de gravar."""
        d = self._nova_janela("Conferir importação")
        self._modal(d)
        d.resizable(True, True)
        fr = ttk.Frame(d, padding=(26, 22, 26, 20))
        fr.pack(fill="both", expand=True)
        resumo = (f"Novas contas: {len(inserir)}    •    Já existem iguais (ignoradas): {len(iguais)}"
                  f"    •    Já existem com dados diferentes: {len(conflitos)}")
        self._cabecalho_dialogo(fr, "importar", "Conferir importação — " + os.path.basename(arq), resumo)
        for a in avisos:
            if a.startswith("🛡 OK"):                      # verificação de segurança que PASSOU: linha verde com ✓
                ttk.Label(fr, text="  " + a[len("🛡 OK"):].strip(), image=imagem_icone(self.root, "ok", CORES["ok"], 14),
                          compound="left", foreground=CORES["ok"], wraplength=_px(760)).pack(anchor="w")
                continue
            ttk.Label(fr, text="  " + a, image=imagem_icone(self.root, "alerta", CORES["alerta"], 14), compound="left",
                      foreground=CORES["alerta"], wraplength=_px(760)).pack(anchor="w")

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
            """Valor mascarado (•••) se 'mostrar senhas' estiver desligado."""
            return v if mostrar.get() else ("•" * min(len(v), 10) if v else "")

        def linha(situacao, r):
            """Monta uma linha da tabela de prévia."""
            outros = ", ".join(ROTULOS[c] for c in ("senha_extra", "pin", "chave", "codigos") if r.get(c))
            return (situacao, r.get("grupo", ""), r.get("servico", ""), r.get("login", ""),
                    oculto(r.get("senha", "")), outros, r.get("notas", "").replace("\n", " ")[:80])

        ordem = {"az": True}                              # padrão: ordem alfabética (A → Z)

        def preencher():
            """Preenche a tabela de prévia, em ordem alfabética pelo nome da conta (A → Z ou Z → A)."""
            tree.delete(*tree.get_children())
            linhas = [("Nova", r) for r in inserir] + [("Dados diferentes", r) for _, r in conflitos]
            linhas.sort(key=lambda x: chave_ordem_alfabetica(x[1].get("servico", "")), reverse=not ordem["az"])
            for situacao, r in linhas:
                tree.insert("", "end", values=linha(situacao, r))

        def alternar_ordem_previa():
            """Troca a ordem da prévia entre A → Z e Z → A."""
            ordem["az"] = not ordem["az"]
            bord.config(text="A → Z" if ordem["az"] else "Z → A")
            preencher()

        opc = ttk.Frame(fr)
        opc.pack(fill="x")
        bord = ttk.Button(opc, text="A → Z", style="Acao.TButton", width=7, command=alternar_ordem_previa)
        bord.pack(side="left", padx=(0, 12))
        preencher()
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
            """Grava o que foi marcado; se falhar, desfaz tudo."""
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
        """Depois de importar, oferece apagar a planilha original (que guarda as senhas em claro)."""
        texto = ("Importação concluída.\n\nA planilha original guarda as senhas SEM criptografia. "
                 "Deseja apagá-la com segurança agora? (o arquivo é sobrescrito com dados "
                 "aleatórios e excluído — não vai para a Lixeira)\n\n"
                 "Feche a planilha no Excel antes de confirmar.")
        if not messagebox.askyesno("Apagar planilha?", texto, perigoso=True):
            messagebox.showinfo("Lembrete", "Lembre de apagar a planilha e esvaziar a Lixeira quando "
                                "terminar de conferir.")
            return
        try:
            destruir_arquivo(arq)
        except OSError as ex:
            messagebox.showerror("Erro", f"Não foi possível apagar (o arquivo está aberto no Excel?).\n{texto_erro(ex)}")
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
        """Texto e cor do veredito de força conforme a nota."""
        if nota >= 3:
            return "Ótima senha!", CORES["ok"]
        if nota == 2:
            return "Hora de mudar de senha!", CORES["alerta"]
        return "Já passou da hora de trocar sua senha!", CORES["perigo"]

    @staticmethod
    def _pintar(texto_widget, senha, oculta=False):
        """Mostra a senha grande e colorida: letras claras, números azuis, símbolos rosa. oculta=True: só bolinhas."""
        texto_widget.config(state="normal")
        texto_widget.delete("1.0", "end")
        if oculta:
            texto_widget.insert("end", "•" * len(senha), ("let", "centro"))
            texto_widget.config(state="disabled")
            return
        for ch in senha:
            tag = "num" if ch.isdigit() else ("let" if ch.isalpha() else "sim")
            texto_widget.insert("end", ch, (tag, "centro"))
        texto_widget.config(state="disabled")

    # ---------- Gerador de senha (diálogo) e verificação de força em massa ----------

    def _novo_texto_senha(self, mestre, fundo=None):
        """Campo de senha somente leitura com fonte monoespaçada."""
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
            curto, resto = subtitulo, False
            if len(subtitulo) > 90:                      # subtítulo curto na tela; o texto inteiro abre no "?"
                corte = subtitulo.find(". ")
                curto = subtitulo[:corte + 1] if 0 < corte <= 90 else subtitulo[:87].rstrip() + "…"
                resto = True
            lin = ttk.Frame(tx)
            lin.pack(anchor="w", fill="x")
            ttk.Label(lin, text=curto, style="Suave.TLabel", wraplength=_px(440), justify="left").pack(side="left")
            if resto:
                self._ajuda(lin, titulo, subtitulo, CORES["fundo"]).pack(side="left", padx=(4, 0))
        return topo

    def dialogo_gerador(self, alvo=None, modo_inicial="aleatoria", mestre=None, senha_mestra=False, extra=None):
        """Gerador de senhas local (estilo 1Password) + verificador (estilo Kaspersky).
        Se 'alvo' for informado, o botão 'Usar esta senha' preenche o campo (e 'extra', se houver).
        Aberto sozinho (menu / Ctrl+G), o botão principal é 'Usar em um novo item': a senha não fica solta.
        Os botões ficam num rodapé fixo e os textos de análise
        (composição, tempo para quebrar) ficam escondidos até o clique em 'Ver detalhes'."""
        import math
        C = CORES
        minimo_chars = MIN_SENHA if senha_mestra else 8     # senha mestra: o gerador respeita o mesmo minimo da tela (14)
        d = self._nova_janela("Gerador de senhas", mestre)
        self._modal(d)
        rodape = ttk.Frame(d, padding=(_px(26), _px(10), _px(26), _px(16)))
        rodape.pack(side="bottom", fill="x")          # empacotado ANTES do corpo: fica sempre visível
        cartao = self._corpo_dialogo(d, (26, 22, 26, 8), rodape=rodape)
        self._cabecalho_dialogo(cartao, "gerar", "Gerador de senhas", "Gerado neste computador. Nada vai para a internet.")

        tipo = tk.StringVar(value=modo_inicial)
        seg = ttk.Frame(cartao, style="Card2.TFrame", padding=4)
        seg.pack(fill="x")
        for chave, texto, ic in (("aleatoria", "Aleatória", "gerar"), ("frase", "Fácil de lembrar", "pessoa"),
                                 ("pin", "PIN", "teclado")):
            if senha_mestra and chave == "pin":
                continue                       # um PIN (4 a 12 digitos) nunca chega ao minimo da senha mestra
            ttk.Radiobutton(seg, text=" " + texto, value=chave, variable=tipo, style="S2.Segmento.Toolbutton",
                            image=imagem_icone(self.root, ic, C["suave"], 16), compound="left",
                            command=lambda: montar_opcoes()).pack(side="left", expand=True, fill="x", padx=1)

        # Senha gerada (grande e colorida)
        caixa_fr = ttk.Frame(cartao, style="Card2.TFrame", padding=(12, 10))
        caixa_fr.pack(fill="x", pady=(16, 0))
        caixa = self._novo_texto_senha(caixa_fr)
        atual = {"s": "", "ver": False, "timer": None}
        olho_g = ttk.Button(caixa_fr, text="👁", image=imagem_icone(self.root, "ver", C["suave"], 18), compound="image",
                            style="Quadrado.TButton", takefocus=0)
        olho_g.pack(side="right", padx=(6, 0))
        caixa.pack(side="left", fill="x", expand=True)

        def alternar_olho():
            """Mostra ou esconde a senha gerada (nunca aparece sozinha; volta a esconder depois de 30 s)."""
            if atual["timer"]:
                try:
                    olho_g.after_cancel(atual["timer"])
                except tk.TclError:
                    pass
                atual["timer"] = None
            atual["ver"] = not atual["ver"]
            self._pintar(caixa, atual["s"], not atual["ver"])
            olho_g.config(image=imagem_icone(self.root, "ocultar" if atual["ver"] else "ver",
                                             C["prim_txt"] if atual["ver"] else C["suave"], 18))
            if atual["ver"]:
                atual["timer"] = self._depois_do_widget(olho_g, self.MOSTRAR_SENHA_MS,
                                                        lambda: alternar_olho() if atual["ver"] else None)
        olho_g.config(command=alternar_olho)
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
            """Atualiza o tamanho a partir do controle deslizante e gera de novo."""
            n = int(round(float(v)))
            if tamanho.get() == n and texto_tam.get() == str(n):
                return                          # o controle dispara várias vezes para o mesmo número: nada a refazer
            tamanho.set(n)
            texto_tam.set(str(n))
            gerar_depois()

        pendente = {"id": None}

        def gerar_depois():
            """Junta várias mudanças seguidas do controle deslizante numa geração só (evita travar ao arrastar)."""
            if pendente["id"] is not None:
                try:
                    d.after_cancel(pendente["id"])
                except tk.TclError:
                    pass
            pendente["id"] = d.after(30, executar_pendente)

        def executar_pendente():
            """Executa a geração agendada (se a janela ainda existe)."""
            pendente["id"] = None
            try:
                gerar()
            except tk.TclError:
                pass

        def da_caixa(event=None):
            """Atualiza o tamanho a partir da caixa numérica e gera de novo."""
            try:
                n = int(texto_tam.get())
            except ValueError:
                return                          # caixa vazia ou digitação incompleta: espera
            lo, hi = int(float(escala.cget("from"))), int(float(escala.cget("to")))
            if lo <= n <= hi and tamanho.get() != n:
                tamanho.set(n)
                gerar_depois()

        # A caixa numerica e empacotada PRIMEIRO (lado direito): assim ela sempre tem o seu espaco e o numero nunca
        # some; quem encolhe, se a janela for estreita, e a regua.
        escala = ttk.Scale(linha_tam, from_=minimo_chars, to=64, orient="horizontal", variable=tamanho, length=_px(160),
                           command=do_deslizante)
        caixa_tam = ttk.Spinbox(linha_tam, from_=minimo_chars, to=64, textvariable=texto_tam, width=5, command=da_caixa)
        caixa_tam.pack(side="right")
        escala.pack(side="left", padx=(4, 12), fill="x", expand=True)
        caixa_tam.bind("<KeyRelease>", da_caixa)
        caixa_tam.bind("<FocusOut>", lambda e: texto_tam.set(str(tamanho.get())))
        opc = ttk.Frame(cartao)
        opc.pack(fill="x", pady=(10, 0))
        numeros, simbolos = tk.BooleanVar(value=True), tk.BooleanVar(value=True)
        maiusc, num_fim = tk.BooleanVar(value=True), tk.BooleanVar(value=True)
        detalhes = {"aberto": False, "args": None}
        bt_det = ttk.Button(cartao, text="Ver detalhes da senha  ▸", style="Acao.TButton")
        bt_det.pack(anchor="w", pady=(12, 0))
        info = PainelForca(cartao, self, largura=_px(540))   # só aparece (e só é desenhado) depois do clique

        def desenhar_detalhes():
            """Desenha o painel de análise com os últimos valores gerados (só se estiver aberto)."""
            a = detalhes["args"]
            if not detalhes["aberto"] or a is None:
                return
            if a[0] == "pin":
                info._limpar()
                info._texto = "PIN aleatório."
                info._cartao()
                info._linha(info, "info", C["suave"], "A segurança de um PIN vem do limite de tentativas do banco "
                            "ou do aparelho (geralmente 3 erros bloqueiam).").pack_configure(pady=0)
            else:
                info.mostrar_gerada(*a[1:])

        def alternar_detalhes():
            """Abre ou fecha o painel de detalhes (composição, tempo para quebrar, indicação de uso)."""
            detalhes["aberto"] = not detalhes["aberto"]
            if detalhes["aberto"]:
                info.pack(fill="x", pady=(8, 0))
                bt_det.config(text="Esconder detalhes  ▾")
                desenhar_detalhes()
            else:
                info.pack_forget()
                bt_det.config(text="Ver detalhes da senha  ▸")
            self._recalcular_dialogo(d)
        bt_det.config(command=alternar_detalhes)
        if senha_mestra:
            av = ttk.Frame(cartao, style="Card2.TFrame", padding=(12, 10))
            av.pack(fill="x", pady=(12, 0))
            ttk.Label(av, text="  Será a senha mestra: anote em papel antes de usar.",
                      image=imagem_icone(self.root, "alerta", C["alerta"], 16), compound="left",
                      style="S2.TLabel", foreground=C["alerta"], wraplength=_px(400), justify="left").pack(side="left")
            self._ajuda(av, "Senha mestra", "ESTA SERÁ A SENHA MESTRA: decore ou anote em papel AGORA, antes de clicar em "
                        "'Usar esta senha'. Ela não será mostrada de novo e não há como recuperá-la.",
                        C["sup2"]).pack(side="right")

        def montar_opcoes():
            """Mostra as opções do gerador conforme o tipo escolhido (senha, frase, PIN)."""
            for w in opc.winfo_children():
                w.destroy()
            t = tipo.get()
            if t == "aleatoria":
                rot_tam.config(text="CARACTERES")
                escala.config(from_=minimo_chars, to=64)
                caixa_tam.config(from_=minimo_chars, to=64)
                tamanho.set(max(20, minimo_chars))
                texto_tam.set(str(max(20, minimo_chars)))
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
            """Gera uma nova senha/frase conforme as opções escolhidas e mostra a força."""
            t = tipo.get()
            try:
                n = int(round(float(tamanho.get())))
            except (tk.TclError, ValueError):
                return
            lim = {"aleatoria": (minimo_chars, 64), "frase": (3, 10), "pin": (4, 12)}[t]
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
            while senha_mestra and len(s) < MIN_SENHA:     # rede de seguranca: nunca entrega senha mestra curta
                s = gerar_frase(n + 1, maiusc.get(), num_fim.get()) if t == "frase" else gerar_senha(
                    MIN_SENHA, numeros.get(), simbolos.get())
            atual["s"] = s
            self._pintar(caixa, s, not atual["ver"])
            nota = 4 if bits >= 80 else 3 if bits >= 60 else 2 if bits >= 40 else 1
            if t == "pin":
                barra_lbl.config(image=self._barra_forca(3, 96))
                veredito.config(text=f"PIN aleatório de {n} dígitos", foreground=C["ok"])
                bits_lbl.config(text=f"{len(s)} dígitos")  # contagem sempre visível; bits só em "Ver detalhes"
                detalhes["args"] = ("pin",)
                desenhar_detalhes()
                return
            txt, cor = self._veredito(nota)
            barra_lbl.config(image=self._barra_forca(nota, 96))
            veredito.config(text=txt, foreground=cor)
            bits_lbl.config(text=f"{len(s)} caracteres")   # contagem sempre visível; "bits" só em "Ver detalhes"
            detalhes["args"] = ("normal", s, bits, nota, txt, uso)
            desenhar_detalhes()

        ttk.Separator(rodape).pack(fill="x", pady=(0, 10))
        botoes = ttk.Frame(rodape)
        botoes.pack(fill="x")
        msg = ttk.Label(rodape, text="", style="Suave.TLabel")

        def copiar():
            """Copia a senha gerada."""
            ok, texto = self._copiar_texto(atual["s"], "Senha")
            msg.config(text=texto)
            return ok

        def usar():
            """Devolve a senha gerada ao formulário que chamou o gerador.
            Fecha ESTE diálogo (gerador) ANTES de mexer no campo: o evento <<Atualizar>> recalcula a barra de
            força e pode recentralizar/redesenhar a janela do item por baixo, e fazer isso enquanto o gerador
            (modal, por cima) ainda estava na tela deixava um glitch visual (achado real 2026-11-13: tela
            ficava truncada ao escolher a senha)."""
            valor, atual["s"] = atual["s"], ""
            d.destroy()
            try:
                for campo in (alvo, extra):
                    if campo is not None:
                        campo.delete(0, "end")
                        campo.insert(0, valor)
                        campo.event_generate("<<Atualizar>>")
            except tk.TclError:
                pass

        def usar_em_novo_item():
            """Fecha o gerador e abre 'Novo item' com a senha gerada já preenchida no campo Senha."""
            senha = atual["s"]
            atual["s"] = ""
            d.destroy()
            self.root.after(30, lambda: self.dialogo_registro(None, senha_inicial=senha))

        if alvo is not None:
            ttk.Button(botoes, text="Usar esta senha", command=usar, style="Primario.TButton",
                       image=imagem_icone(self.root, "ok", "#ffffff"), compound="left").pack(side="right")
        else:
            ttk.Button(botoes, text="Usar em um novo item", command=usar_em_novo_item, style="Primario.TButton",
                       image=imagem_icone(self.root, "novo", "#ffffff"), compound="left").pack(side="right")
        bcg = ttk.Button(botoes, text=" Copiar", style="Acao.TButton",
                         image=imagem_icone(self.root, "copiar", C["texto"]), compound="left")
        bcg.config(command=lambda: copiar() and self._copiado(bcg))
        bcg.pack(side="right", padx=8)
        ttk.Button(botoes, text="Atualizar senha", command=gerar, style="Acao.TButton",
                   image=imagem_icone(self.root, "atualizar", C["texto"]), compound="left").pack(side="right", padx=8)
        msg.pack(fill="x", pady=(8, 0))

        # ---- verificador (estilo Kaspersky), só quando aberto sozinho ----
        if alvo is None:
            bt_ver = ttk.Button(cartao, text="Testar uma senha que eu já tenho  ▸", style="Acao.TButton")
            bt_ver.pack(anchor="w", pady=(10, 0))
            area_ver = ttk.Frame(cartao)                # escondida até o clique
            ttk.Label(area_ver, text="Verificado só neste computador.", style="Suave.TLabel").pack(anchor="w",
                                                                                                    pady=(10, 0))

            def alternar_verificador():
                """Mostra ou esconde a área de teste de uma senha digitada."""
                if area_ver.winfo_manager():
                    area_ver.pack_forget()
                    bt_ver.config(text="Testar uma senha que eu já tenho  ▸")
                else:
                    area_ver.pack(fill="x")
                    bt_ver.config(text="Esconder o teste de senha  ▾")
                    teste.focus_set()
            bt_ver.config(command=alternar_verificador)
            lin = ttk.Frame(area_ver)
            lin.pack(fill="x", pady=(8, 6))
            teste = self._campo_secreto(lin, 40)
            teste.pack(side="left", fill="x", expand=True)
            ver = tk.BooleanVar(value=False)
            ttk.Checkbutton(lin, text="Mostrar", variable=ver, style="Switch.TCheckbutton",
                            command=lambda: teste.config(show="" if ver.get() else "•")).pack(side="left", padx=(12, 0))
            lv2 = ttk.Frame(area_ver)
            lv2.pack(fill="x")
            b2 = ttk.Label(lv2)
            b2.pack(side="left")
            v2 = ttk.Label(lv2, text="", font="CofreForte")
            v2.pack(side="left", padx=(10, 0))
            i2 = PainelForca(area_ver, self, largura=_px(540))
            i2.pack(fill="x", pady=(6, 0))

            def testar(event=None):
                """Avalia a força de uma senha digitada no campo de teste."""
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

            ultimo_teste = {"v": None}

            def testar_se_mudou(event=None):
                """Reavalia só quando o texto do campo mudou."""
                if teste.get() != ultimo_teste["v"]:
                    ultimo_teste["v"] = teste.get()
                    testar()

            def vigiar_teste():
                """Acompanha o campo a cada 150 ms (colar com o mouse, teclado virtual...)."""
                try:
                    if not teste.winfo_exists():
                        return
                    testar_se_mudou()
                    teste.after(150, vigiar_teste)
                except tk.TclError:
                    pass

            for ev in ("<KeyRelease>", "<<Paste>>", "<<Cut>>", "<<Clear>>", "<ButtonRelease-1>"):
                teste.bind(ev, testar_se_mudou, add="+")
            teste.bind("<<Atualizar>>", testar, add="+")
            teste.after(150, vigiar_teste)

        montar_opcoes()
        self.root.wait_window(d)


    def verificar_senhas(self):
        """Mostra o resultado da auditoria das senhas do cofre."""
        achados = auditar_cofre(self.cofre.registros)
        d = self._nova_janela("Verificação das senhas")
        self._modal(d)
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
            """Abre o item escolhido na lista de achados."""
            sel = tree.selection()
            if sel:
                d.destroy()
                if self._liberar_protegido(mapa[sel[0]]):
                    self.dialogo_registro(mapa[sel[0]])

        tree.bind("<Double-1>", abrir)
        base = ttk.Frame(fr)
        base.pack(fill="x", pady=(14, 0))
        ttk.Button(base, text="Fechar", command=d.destroy, style="Primario.TButton").pack(side="right")
        ttk.Button(base, text="Checar vazamentos (online)…", command=lambda: self.checar_vazamentos(d)).pack(side="right", padx=(0, 8))

    # ---------- Checagem de vazamentos online e impressão ----------

    def checar_vazamentos(self, pai=None):
        """Confere se as senhas do cofre aparecem em vazamentos conhecidos (Have I Been Pwned, k-anonymity).
        Sai pela rede só o começo (5 caracteres) do SHA-1 de cada senha; a comparação final é feita aqui."""
        pai = pai or self.root
        if not messagebox.askyesno(
                "Checar vazamentos (online)",
                "Isto usa a internet.\n\nDe cada senha, só os 5 primeiros caracteres do SHA-1 dela (nunca a senha, "
                "nunca o SHA-1 inteiro) são enviados ao serviço Have I Been Pwned; ele devolve uma lista e a "
                "comparação final é feita neste computador.\n\nO serviço não recebe suas senhas, mas vê o seu "
                "endereço de internet e que você fez a consulta.\n\nContinuar?", parent=pai):
            return
        pedidos = []
        for r in self.cofre.registros:
            for campo in ("senha", "senha_extra"):
                v = r.get(campo)
                if v:
                    pre, suf = hibp_dividir(v)
                    pedidos.append(((r.get("servico", ""), ROTULOS[campo]), pre, suf))
        if not pedidos:
            messagebox.showinfo("Checar vazamentos", "Não há senhas no cofre para checar.", parent=pai)
            return
        estado = {"feito": 0, "total": len({p[1] for p in pedidos}), "achados": None, "erro": None, "cancelar": False}

        def trabalho():
            """Thread: consulta o serviço e guarda o resultado (nenhuma senha passa por aqui, só prefixo e sufixo)."""
            try:
                estado["achados"] = hibp_verificar(pedidos, ao_andar=lambda n: estado.__setitem__("feito", n),
                                                   cancelar=lambda: estado["cancelar"])
            except Exception as ex:
                estado["erro"] = ex
        d = self._nova_janela("Checar vazamentos", pai)
        self._modal(d)
        fr = ttk.Frame(d, padding=(26, 22, 26, 20))
        fr.pack(fill="both", expand=True)
        self._cabecalho_dialogo(fr, "verificar", "Checando vazamentos", "Consultando o serviço, aguarde…")
        info = ttk.Label(fr, text="", wraplength=_px(520))
        info.pack(anchor="w")
        corpo = ttk.Frame(fr)
        corpo.pack(fill="both", expand=True, pady=(8, 0))
        bt = ttk.Button(fr, text="Cancelar", command=lambda: (estado.__setitem__("cancelar", True), d.destroy()))
        bt.pack(anchor="e", pady=(14, 0))
        d.bind("<Destroy>", lambda e: estado.__setitem__("cancelar", True) if e.widget is d else None)
        th = threading.Thread(target=trabalho, daemon=True)
        th.start()

        def sondar():
            """Atualiza o andamento e, ao terminar, mostra o resultado."""
            if th.is_alive():
                info.config(text=f"Consultando… {estado['feito']} de {estado['total']}")
                self._depois_do_widget(d, 300, sondar)
                return
            for _, _, suf in pedidos:
                zerar_objeto(suf)
            bt.config(text="Fechar", command=d.destroy)
            if estado["erro"] is not None or estado["achados"] is None:
                info.config(text="Não foi possível consultar o serviço (sem internet, bloqueio de rede ou serviço fora do ar). "
                                 "Nada foi alterado.", foreground=CORES["alerta"])
                return
            achados = estado["achados"]
            if not achados:
                info.config(text="Nenhuma das senhas aparece nas listas de vazamento conhecidas. Isso não prova que "
                                 "sejam fortes: veja também a verificação de força e de repetidas.", foreground=CORES["ok"])
                return
            info.config(text=f"{len(achados)} senha(s) apareceram em vazamentos. Troque-as pelo gerador.",
                        foreground=CORES["perigo"])
            tv = ttk.Treeview(corpo, columns=("conta", "campo", "vezes"), show="headings", height=min(12, len(achados)))
            for col, txt, larg in (("conta", "Conta / App", 240), ("campo", "Campo", 110), ("vezes", "Vezes vazada", 110)):
                tv.heading(col, text=txt)
                tv.column(col, width=larg)
            for (serv, campo), n in achados:
                tv.insert("", "end", values=(serv, campo, f"{n:,}".replace(",", ".")))
            tv.pack(fill="both", expand=True)
        sondar()

    # ---------- impressão ----------
    # Únicos documentos que o cofre imprime: a cópia de emergência da chave de acesso e do código de recuperação.
    # Senhas, itens, backups e a senha mestra NUNCA são impressos (nenhuma outra tela chama esta função).
    TITULOS_IMPRESSAO = ("ARCA — CHAVE DE ACESSO", "ARCA — CÓDIGO DE RECUPERAÇÃO")
    AVISO_IMPRESSAO = ("Impressão bloqueada para senhas e credenciais. Liberada só para a cópia de emergência "
                       "da chave de acesso e do código de recuperação (pede a senha mestra).")

    def _imprimir(self, titulo, campos, mestre=None):
        """Imprime direto na impressora, sem criar arquivo. SÓ para a chave de acesso e o código de recuperação
        (título conferido) e SÓ depois de pedir a senha mestra. Avisa se a impressora gera arquivo."""
        janela = mestre or self.root
        if titulo not in self.TITULOS_IMPRESSAO:
            messagebox.showerror("Imprimir", self.AVISO_IMPRESSAO, parent=janela)
            return False
        if not self._confirmar_senha_atual("Imprimir cópia de emergência"):
            return False
        if not messagebox.askyesno(
                "Antes de imprimir",
                "O Windows guarda o que você imprime na fila de impressão (uma pasta no disco C:) até o "
                "fim do trabalho, e impressoras de rede mandam o conteúdo pela rede.\n\nImprima só em uma "
                "impressora USB sua, pegue a folha na hora e guarde-a em local seguro.\n\nContinuar?",
                parent=janela, perigoso=True):
            return False
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
                    f'"{nome}" cria um ARQUIVO (PDF/XPS/etc.) com a chave impressa SEM criptografia.\n\n'
                    "O recomendado é imprimir em uma impressora de verdade.\n\nContinuar mesmo assim?",
                    parent=janela, perigoso=True):
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

    # ---------- tarefas demoradas sem travar a janela ----------
    # ---------- Execução em segundo plano (operações demoradas sem travar a tela) ----------

    def _executar_salvamento(self, funcao):
        """Executor usado por `Cofre.salvar`: roda a gravação numa thread; o aviso 'Salvando…' só aparece se
        passar de 0,4 s (gravações rápidas não piscam nada na tela). Bloqueios automáticos esperam o fim.
        Em unidade removível (pendrive lento ou gasto) o aviso também pede para NÃO retirá-la durante a gravação."""
        self._salvando = True
        try:
            texto = "Salvando…"
            try:
                if unidade_removivel(getattr(self, "caminho", None) or getattr(self.cofre, "caminho", None)):
                    texto = "Salvando… não retire o pendrive"
            except OSError as ex:
                texto = "Salvando… não retire o pendrive"
                diag_registrar(DIAG_GRAVACAO, ex)
            return self._com_espera(funcao, texto, atraso=0.4)
        finally:
            self._salvando = False

    def _com_espera(self, funcao, texto="Verificando…", atraso=0.0):
        """Roda 'funcao' (Argon2: vários segundos) numa thread enquanto a janela continua respondendo ao
        Windows, com um aviso modal que bloqueia cliques repetidos. Devolve o resultado ou repassa o erro.
        Com 'atraso' > 0 o aviso nasce transparente (já bloqueando cliques) e só fica visível depois desse tempo."""
        resultado = {}
        t0 = time.monotonic()

        def alvo():
            """Roda a tarefa demorada e guarda o resultado ou o erro."""
            try:
                resultado["v"] = funcao()
            except BaseException as ex:
                resultado["e"] = ex

        j = None
        try:
            j = tk.Toplevel(self.root)
            j.overrideredirect(True)
            j.configure(bg=CORES["borda2"])
            q = tk.Frame(j, bg=CORES["fundo"], padx=26, pady=16)
            q.pack(padx=1, pady=1)
            tk.Label(q, text=texto, bg=CORES["fundo"], fg=CORES["texto"], font="CofreForte").pack()
            j.update_idletasks()
            x = self.root.winfo_rootx() + (self.root.winfo_width() - j.winfo_reqwidth()) // 2
            y = self.root.winfo_rooty() + (self.root.winfo_height() - j.winfo_reqheight()) // 3
            j.geometry(f"+{max(0, x)}+{max(0, y)}")
            proteger_contra_captura(j)
            if atraso > 0:
                try:
                    j.attributes("-alpha", 0.0)
                except tk.TclError:
                    pass
            _grab_seguro(j, 0.5)
        except tk.TclError:
            j = None
        th = threading.Thread(target=alvo, daemon=True)
        th.start()
        visivel = atraso <= 0
        try:
            while th.is_alive():
                if not visivel and j is not None and time.monotonic() - t0 >= atraso:
                    visivel = True
                    try:
                        j.attributes("-alpha", 1.0)
                    except tk.TclError:
                        pass
                try:
                    self.root.update()
                except tk.TclError:
                    break
                self._ultimo_tique = time.time()
                time.sleep(0.02)
            th.join()
        finally:
            if j is not None:
                try:
                    j.grab_release()
                    j.destroy()
                except tk.TclError:
                    pass
        if "e" in resultado:
            raise resultado["e"]
        return resultado.get("v")

    def _em_segundo_plano(self, funcao, ao_terminar):
        """Roda uma função numa thread e chama ao_terminar(resultado, erro) na thread da tela."""
        resultado = {}

        def alvo():
            """Corpo da thread: executa e guarda o resultado ou o erro."""
            try:
                resultado["v"] = funcao()
            except BaseException as ex:          # repassa qualquer erro para a janela tratar
                resultado["e"] = ex

        th = threading.Thread(target=alvo, daemon=True)
        th.start()

        def checar():
            """Verifica de tempos em tempos se a thread terminou."""
            if th.is_alive():
                self.root.after(100, checar)
            else:
                ao_terminar(resultado.get("v"), resultado.get("e"))

        self.root.after(100, checar)

    def _pedir_texto(self, titulo, texto, inicial=""):
        """Janela que pede um texto ao usuário e o devolve (None se cancelar)."""
        d = self._nova_janela(titulo)
        self._modal(d)
        res = {"v": None}
        fr = ttk.Frame(d, padding=(26, 22, 26, 20))
        fr.pack()
        self._cabecalho_dialogo(fr, "editar", titulo, texto)
        e = ttk.Entry(fr, width=40)
        e.insert(0, inicial)
        e.pack(fill="x")
        if not inicial:
            self._pista_entrada(e, "Digite aqui")

        def ok(event=None):
            """Confirma o texto digitado."""
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
        self._modal(d)
        ok = {"v": False}
        fr = ttk.Frame(d, padding=(26, 22, 26, 20))
        fr.pack(fill="both", expand=True)
        self._cabecalho_dialogo(fr, "chave", "Código de recuperação",
                                "Para emergências: substitui a chave FIDO se você perder todas.", "alerta")
        caixa_av = ttk.Frame(fr, style="Card2.TFrame", padding=(14, 12))
        caixa_av.pack(fill="x", pady=(0, 14))
        ttk.Label(caixa_av, style="S2.TLabel", text="Anote em PAPEL agora: ele aparece só esta vez.",
                  foreground=CORES["alerta"], justify="left", wraplength=_px(470)).pack(side="left", anchor="w")
        self._ajuda(caixa_av, "Código de recuperação",
                    "Use este código SOMENTE se perder TODAS as chaves FIDO. Ele substitui a chave FIDO (a senha mestra "
                    "e a chave de acesso continuam sendo exigidas).\n\n"
                    "• Anote em PAPEL e guarde em local seguro (gaveta trancada, cofre físico).\n"
                    "• NÃO guarde no celular, no computador, em foto ou na nuvem.\n"
                    "• Ele aparece só agora.", CORES["alerta"]).pack(side="right")
        partes = codigo.split("-")
        # Bloco a conferir SORTEADO (não sempre o último): se fosse sempre o mesmo lugar, dava para decorar só
        # aquele pedacinho sem realmente olhar o código inteiro, o que não prova que a pessoa anotou tudo certo
        # (sugestão do usuário, achado 2026-11-13). Fica destacado em VERMELHO no próprio código mostrado.
        alvo_i = secrets.SystemRandom().randrange(len(partes))
        bloco_alvo = partes[alvo_i]
        caixa = tk.Text(fr, height=2, width=42, font=(FONTES["CofreMonoG"].cget("family"), 16), relief="flat",
                        bd=0, wrap="char", exportselection=False, cursor="arrow", padx=6, pady=6,
                        highlightthickness=0, bg=CORES["sup2"], fg=CORES["texto"], insertbackground=CORES["sup2"],
                        selectbackground=CORES["sup2"], inactiveselectbackground=CORES["sup2"])
        caixa.tag_configure("normal", foreground=CORES["texto"], justify="center", spacing1=2)
        caixa.tag_configure("destaque", foreground=CORES["perigo"], justify="center", spacing1=2)
        for i, p in enumerate(partes):
            if i:
                caixa.insert("end", "-", "normal")
            caixa.insert("end", p, "destaque" if i == alvo_i else "normal")
        caixa.config(state="disabled")
        self._bloquear_copia(caixa)
        caixa.pack(fill="x")
        # O bloco sorteado nem sempre tem 4 caracteres: o código é 32 caracteres (dados) + 2 de verificação,
        # e 34 não é múltiplo de 4, então o bloco final sempre sobra com 2 (achado real 2026-11-13: o texto
        # antigo dizia sempre "4 caracteres" e o usuário digitava 4, mas às vezes o bloco de verdade tinha só 2
        # -> "sai errado"). Agora o rótulo mostra o tamanho de verdade do bloco destacado.
        ttk.Label(fr, text=f"Para confirmar que anotou, digite o bloco em VERMELHO "
                            f"({len(bloco_alvo)} caracteres):").pack(anchor="w", pady=(14, 4))
        conf = ttk.Entry(fr, width=10, font="CofreMono")
        conf.pack(anchor="w")
        self._pista_entrada(conf, f"Bloco ({len(bloco_alvo)} caracteres)")
        msg = ttk.Label(fr, text="", foreground=CORES["perigo"])
        msg.pack(anchor="w", pady=(4, 0))

        def confirmar(event=None):
            """Só libera depois de o usuário digitar o bloco em vermelho, para provar que anotou o código inteiro."""
            if conf.get().strip().upper() == bloco_alvo:
                ok["v"] = True
                d.destroy()
            else:
                msg.config(text="Não confere. Confira o que você anotou.")

        conf.bind("<Return>", confirmar)
        bt = ttk.Frame(fr)
        bt.pack(fill="x", pady=(14, 0))
        def imprimir_codigo():
            """Imprime SÓ o código de recuperação (cópia de emergência; pede a senha mestra)."""
            self._imprimir("ARCA — CÓDIGO DE RECUPERAÇÃO", [("Código de recuperação", codigo)], mestre=d)

        ttk.Button(bt, text="Imprimir só o código…", command=imprimir_codigo,
                   image=imagem_icone(self.root, "imprimir", CORES["texto"]), compound="left").pack(side="left")
        ttk.Label(fr, text="Impressão bloqueada para senhas; liberada só para esta cópia de emergência "
                  "(pede a senha mestra). Use uma impressora USB sua.", style="Suave.TLabel",
                  wraplength=_px(470), justify="left").pack(anchor="w", pady=(8, 0), before=bt)
        ttk.Button(bt, text="Já anotei — confirmar", command=confirmar, style="Primario.TButton").pack(side="right")
        ttk.Button(bt, text="Cancelar (não altera o cofre)", command=d.destroy).pack(side="right", padx=8)
        conf.focus_set()
        self.root.wait_window(d)
        return ok["v"]

    def tela_seguranca_adicional(self):
        """Tela central de 'Segurança adicional': o nível de proteção por inteiro, cada camada extra (ativa ou
        não) com uma explicação, e um botão de ação direta quando dá para ligar na hora. Reúne num só lugar o
        que antes ficava espalhado (achado do usuário 2026-11-13: no painel lateral, clicar num item que falta
        E NÃO TEM AÇÃO — hoje só a 'chave de acesso' quando não foi escolhida ao criar o cofre — não levava a
        lugar nenhum; e o menu "…" misturava itens gerais com itens de segurança sem nenhuma separação)."""
        C = CORES
        d = self._nova_janela("Segurança adicional")
        self._modal(d)
        fr = ttk.Frame(d, padding=(26, 22, 26, 20))
        fr.pack(fill="both", expand=True)
        self._cabecalho_dialogo(fr, "escudo", "Segurança adicional",
                                "O que cada camada extra faz, o quanto ela soma e como ligar.", "alerta")
        pts, nivel, itens_nivel = nivel_protecao(self.cofre.modo, self.cofre.m, self.cofre.fido, self.cofre.pc) \
            if self.cofre is not None else (0, "Básica", [])
        cor_nivel = C["perigo"] if pts < 40 else C["alerta"] if pts < 65 else C["ok"]
        faixa = ttk.Frame(fr)
        faixa.pack(fill="x", pady=(0, 4))
        barra = tk.Canvas(faixa, height=8, bg=C["sup2"], highlightthickness=0)
        barra.pack(fill="x")
        barra.bind("<Configure>", lambda e, b=barra: (b.delete("all"), b.create_rectangle(
            0, 0, int(e.width * pts / 100), 8, fill=cor_nivel, width=0)))
        ttk.Label(fr, text=f"Proteção: {nivel}  ({pts}/100)", foreground=cor_nivel, font="CofreForte").pack(
            anchor="w", pady=(6, 14))
        for rot, pt, ativo, acao in itens_nivel:
            lin = ttk.Frame(fr, style="Card2.TFrame", padding=(14, 12))
            lin.pack(fill="x", pady=(0, 10))
            topo = ttk.Frame(lin, style="Card2.TFrame")
            topo.pack(fill="x")
            ttk.Label(topo, image=imagem_icone(self.root, "ok" if ativo else "alerta",
                      C["ok"] if ativo else C["fraco"], 16), style="S2.TLabel").pack(side="left", anchor="n")
            ttk.Label(topo, text=rot, style="S2.TLabel", font="CofreForte", wraplength=_px(380),
                      justify="left").pack(side="left", padx=(8, 0), fill="x", expand=True)
            ttk.Label(topo, text="Ativo ✓" if ativo else f"+{pt} pontos", style="S2.TLabel",
                      foreground=C["ok"] if ativo else C["fraco"]).pack(side="right")
            if ativo:
                continue
            if acao:
                ttk.Button(lin, text="Ativar agora…", style="Acao.TButton",
                           command=(lambda a=acao: (d.destroy(),
                                    self.gerenciar_computadores() if a == "pc" else self.gerenciar_fido()))
                           ).pack(anchor="w", pady=(8, 0))
            elif "chave de acesso" in rot.lower():
                ttk.Label(lin, style="S2.Fraco.TLabel", justify="left", wraplength=_px(420),
                          text="Dá para adicionar agora, sem recriar o cofre e sem perder nada. Uma chave nova "
                               "aparece uma única vez: guarde-a fora do pendrive.").pack(anchor="w", pady=(8, 0))
                bt_chave = ttk.Frame(lin, style="Card2.TFrame")
                bt_chave.pack(anchor="w", pady=(8, 0))
                ttk.Button(bt_chave, text="Senha E chave (recomendado)…", style="Acao.TButton",
                           command=lambda: (d.destroy(), self.adicionar_chave_acesso(MODO_E))).pack(side="left")
                ttk.Button(bt_chave, text="Senha OU chave…", style="Acao.TButton",
                           command=lambda: (d.destroy(), self.adicionar_chave_acesso(MODO_OU))).pack(
                               side="left", padx=(8, 0))
        ttk.Button(fr, text="Fechar", command=d.destroy, style="Primario.TButton").pack(anchor="e", pady=(4, 0))

    # ---------- chaves FIDO ----------
    # ---------- FIDO2 e computadores autorizados ----------

    def gerenciar_fido(self):
        """Janela para cadastrar e remover chaves FIDO2 do cofre."""
        d = self._nova_janela("Chaves FIDO")
        self._modal(d)
        fr = ttk.Frame(d, padding=(26, 22, 26, 20))
        fr.pack(fill="both", expand=True)
        self._cabecalho_dialogo(fr, "chave", "Chaves FIDO",
                                "Chaves de segurança físicas (YubiKey, Feitian, Titan...) como proteção extra.")
        linha_estado = ttk.Frame(fr)
        linha_estado.pack(anchor="w", fill="x", pady=(4, 8))
        estado = ttk.Label(linha_estado, text="", wraplength=_px(500), justify="left")
        estado.pack(side="left")
        self._ajuda(linha_estado, "Chaves FIDO",
                    "Com FIDO ativo, o cofre só abre com a senha (e a chave de acesso, se o modo exigir) MAIS uma das "
                    "chaves físicas cadastradas, ou o código de recuperação em papel.\n\n"
                    "Cadastre sempre uma SEGUNDA chave (reserva).\n\n"
                    "Serve quase qualquer chave de segurança FIDO2: Yubico Security Key NFC, YubiKey 5, Feitian ePass "
                    "FIDO2... Chave nova vem sem PIN: o Windows pede para criar um no primeiro uso (ou em Configurações "
                    "> Contas > Opções de entrada > Chave de segurança > Gerenciar).").pack(side="left", padx=(6, 0))
        lista = ttk.Treeview(fr, columns=("nome",), show="headings", height=6, selectmode="browse")
        lista.heading("nome", text="Chaves cadastradas")
        lista.column("nome", width=520)
        lista.pack(fill="x")

        def atualizar():
            """Recarrega a lista de chaves FIDO cadastradas."""
            lista.delete(*lista.get_children())
            if self.cofre.fido:
                for i, ch in enumerate(self.cofre.fido["chaves"]):
                    lista.insert("", "end", iid=str(i), values=(ch["nome"],))
                n = len(self.cofre.fido["chaves"])
                estado.config(foreground=CORES["ok"], text=(
                    f"FIDO ativo: {n} chave(s)." + ("  ⚠ Cadastre uma reserva." if n == 1 else "")))
            else:
                estado.config(foreground=CORES["suave"], text="FIDO desativado.")
            for b in (b_rem, b_rec, b_des):
                b.config(state="normal" if self.cofre.fido else "disabled")
            self._atualizar_indicadores()

        def adicionar():
            """Cadastra uma chave FIDO nova (pede a senha mestra)."""
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
            """Termina o cadastro da chave FIDO (feito em segundo plano): atualiza a lista ou mostra o erro."""
            self._ocupado(False)
            if erro is not None:
                atualizar()
                messagebox.showerror("Chave FIDO", str(erro) if isinstance(erro, FidoErro)
                                     else f"Erro inesperado: {erro}", parent=d)
                return
            if self.cofre is None:              # o cofre foi bloqueado enquanto a chave era tocada
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
            """Remove a chave FIDO selecionada, depois de confirmar."""
            sel = lista.selection()
            if not sel:
                messagebox.showinfo("Chaves FIDO", "Selecione a chave a remover.", parent=d)
                return
            ch = self.cofre.fido["chaves"][int(sel[0])]
            if not messagebox.askyesno("Remover chave", f'Remover a chave "{ch["nome"]}" deste cofre?\n\n'
                                       "Ela deixará de abrir o cofre.", parent=d, perigoso=True):
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
                return
            atualizar()
            messagebox.showinfo("Chave removida", "Pronto. Lembre: backups e cópias antigas do cofre (.bak1 a .bak5, "
                                "backups externos) continuam abrindo com a chave removida. Se ela foi "
                                "perdida ou roubada, a senha mestra continua sendo o que protege o cofre — "
                                "troque-a e gere uma nova chave de acesso.", parent=d)

        def novo_codigo():
            """Gera um novo código de recuperação (o anterior deixa de valer)."""
            if not messagebox.askyesno("Novo código de recuperação", "Gerar um novo código de recuperação?\n\n"
                                       "O código antigo deixa de funcionar.", parent=d, perigoso=True):
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
            """Desativa a exigência de FIDO depois de confirmar."""
            if not messagebox.askyesno("Desativar FIDO", "Desativar a exigência de chave FIDO?\n\nO cofre volta "
                                       "a abrir só com a senha/chave de acesso. Todas as chaves FIDO e o código "
                                       "de recuperação deixam de valer.", parent=d, perigoso=True):
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

    def _perguntar_mais_computadores(self, parent=None):
        """Pergunta se há mais computadores a autorizar. SIM libera até MAX_PC; NÃO deixa só 1."""
        return bool(messagebox.askyesno(
            "Mais computadores?",
            "Você tem mais computadores para autorizar a abrir este cofre?\n\n"
            f"SIM: libera o 2º lugar (podem ser até {MAX_PC} computadores).\n"
            "NÃO: o cofre fica preso a 1 computador (este). Nenhum outro consegue abri-lo, "
            "a não ser com o código de recuperação.\n\n"
            "Você pode mudar essa resposta depois, em Computadores autorizados.", parent=parent or self.root))

    def _autorizar_primeiro_pc_na_criacao(self):
        """Logo após criar o cofre: autoriza ESTE computador, mostra o código de recuperação e pergunta
        se haverá mais computadores. Se algo falhar, o cofre continua válido (sem a exigência) e avisa."""
        if os.environ.get("COFRE_SEM_VERIFICACAO_INICIAL") == "1" or self.cofre is None or self.cofre.pc:
            return
        anterior = self.cofre.estado_pc()
        meta_antes = self.cofre.meta.get("pcs_multiplos")

        def desfazer():
            self.cofre.restaurar_pc(anterior)
            if meta_antes is None:
                self.cofre.meta.pop("pcs_multiplos", None)
            else:
                self.cofre.meta["pcs_multiplos"] = meta_antes

        nome = os.environ.get("COMPUTERNAME") or "Computador principal"
        try:
            try:
                codigo = self.cofre.pc_adicionar(nome, local=bool(EH_WINDOWS))
            except ValueError:
                self.cofre.restaurar_pc(anterior)
                codigo = self.cofre.pc_adicionar(nome, local=False)    # sem o reforço do Windows
            self.cofre.definir_pcs_multiplos(self._perguntar_mais_computadores())
        except ValueError as ex:
            desfazer()
            messagebox.showwarning("Computadores autorizados",
                                   f"Não foi possível autorizar este computador agora:\n{ex}\n\n"
                                   "Você pode fazer isso depois em Computadores autorizados.", parent=self.root)
            return
        if codigo and not self.mostrar_codigo_recuperacao(codigo):
            desfazer()
            messagebox.showinfo("Computadores autorizados", "Cancelado. O cofre ficou sem computador autorizado; "
                                "ative depois em Computadores autorizados.", parent=self.root)
            return
        if not self._salvar():
            desfazer()
            return
        messagebox.showinfo("Computadores autorizados",
                            f'Este computador ("{nome}") foi autorizado.\n\n' +
                            (f"Você pode autorizar até {MAX_PC} computadores." if self.cofre.pcs_multiplos()
                             else "O cofre está preso a 1 computador. Para liberar outros, mude a resposta em "
                                  "Computadores autorizados."), parent=self.root)

    def gerenciar_computadores(self):
        """Janela para autorizar computadores (fator extra: o cofre só abre neles, ou com o código de recuperação)."""
        d = self._nova_janela("Computadores autorizados")
        self._modal(d)
        fr = ttk.Frame(d, padding=(26, 22, 26, 20))
        fr.pack(fill="both", expand=True)
        self._cabecalho_dialogo(fr, "cadeado", "Computadores autorizados",
                                "Fator extra: além da senha (e da chave FIDO), o cofre exige um computador da lista.")
        linha_estado = ttk.Frame(fr)
        linha_estado.pack(anchor="w", fill="x", pady=(4, 8))
        estado = ttk.Label(linha_estado, text="", wraplength=_px(500), justify="left")
        estado.pack(side="left")
        self._ajuda(linha_estado, "Computadores autorizados",
                    "Com este fator ativo, o cofre só abre nos computadores da lista OU com o código de recuperação "
                    "em papel. Quem roubar o pendrive e descobrir a senha não consegue abrir em outro computador.\n\n"
                    "O computador é reconhecido pelo MachineGuid do Windows e pelo UUID da placa-mãe (não pelo disco "
                    "nem pela placa de rede, que mudam). Reinstalar o Windows ou trocar a placa-mãe muda isso: "
                    "autorize o computador de novo, usando o código de recuperação ou outro computador da lista.\n\n"
                    "Não é segredo contra quem já está no seu computador: é uma proteção contra pendrive roubado.\n\n"
                    "Guarde o código de recuperação em papel: sem ele, se todos os computadores da lista mudarem, "
                    "o cofre não abre.").pack(side="left", padx=(6, 0))
        lista = ttk.Treeview(fr, columns=("nome", "aqui"), show="headings", height=6, selectmode="browse")
        lista.heading("nome", text="Computadores autorizados")
        lista.heading("aqui", text="")
        lista.column("nome", width=350)
        lista.column("aqui", width=170, anchor="center")
        lista.pack(fill="x")

        def atualizar():
            """Recarrega a lista de computadores autorizados."""
            lista.delete(*lista.get_children())
            if self.cofre.pc:
                aqui = self.cofre.pc_id_deste()
                reforco = self.cofre.pc_nivel_deste() == "local"
                for i, m in enumerate(self.cofre.pc["maquinas"]):
                    lista.insert("", "end", iid=str(i), values=(
                        m["nome"], ("este computador" + (" ✓ reforçado" if reforco else "")) if m["id"] == aqui else ""))
                n = len(self.cofre.pc["maquinas"])
                estado.config(foreground=CORES["ok"], text=f"Ativo: {n} computador(es) autorizado(s).")
            else:
                estado.config(foreground=CORES["suave"], text="Desativado: o cofre abre em qualquer computador.")
            ja = bool(self.cofre.pc) and self.cofre.pc_id_deste() is not None
            b_aut.config(state="disabled" if ja else "normal")
            for b in (b_rem, b_rec, b_des):
                b.config(state="normal" if self.cofre.pc else "disabled")
            self._atualizar_indicadores()

        def autorizar():
            """Autoriza ESTE computador (o primeiro ativa a exigência e mostra o código de recuperação)."""
            if not self.cofre.pc and not messagebox.askyesno(
                    "Ativar computadores autorizados",
                    "Depois de ativar, o cofre só abrirá NESTE computador (e nos que você autorizar depois) ou com o "
                    "código de recuperação.\n\nVai aparecer um código de recuperação: GUARDE-O EM PAPEL.\n\nAtivar?",
                    parent=d, perigoso=True):
                return
            if self.cofre.pc and len(self.cofre.pc["maquinas"]) >= self.cofre.limite_pc() == 1:
                if not messagebox.askyesno("Limitado a 1 computador",
                                           "O cofre está preso a 1 computador.\n\nQuer liberar mais "
                                           f"computadores (até {MAX_PC})?", parent=d):
                    return
                if not self._confirmar_senha_atual("Liberar mais computadores"):
                    return
                self.cofre.definir_pcs_multiplos(True)
                if not self._salvar():
                    self.cofre.definir_pcs_multiplos(False)
                    return
                atualizar()
            elif not self._confirmar_senha_atual("Autorizar este computador"):
                return
            n = len(self.cofre.pc["maquinas"]) if self.cofre.pc else 0
            nome = self._pedir_texto("Nome do computador", "Dê um nome para identificar este computador:",
                                     os.environ.get("COMPUTERNAME") or ("Computador principal" if n == 0 else "Outro computador"))
            if nome is None:
                return
            local = EH_WINDOWS and messagebox.askyesno(
                "Reforço (recomendado)",
                "Guardar também um segredo protegido pelo Windows NESTE computador?\n\nSem ele, quem tiver o pendrive e "
                "a senha e souber o identificador deste computador poderia abrir. Com ele, só esta conta do Windows, "
                "neste computador, abre.\n\nSe o Windows for reinstalado ou a conta mudar, use o código de recuperação "
                "e autorize de novo.", parent=d)
            anterior = self.cofre.estado_pc()
            try:
                codigo = self.cofre.pc_adicionar(nome, local=bool(local))
            except ValueError as ex:
                self.cofre.restaurar_pc(anterior)
                messagebox.showerror("Computadores autorizados", str(ex), parent=d)
                return
            if codigo and not self.mostrar_codigo_recuperacao(codigo):
                self.cofre.restaurar_pc(anterior)
                messagebox.showinfo("Computadores autorizados", "Cancelado. O cofre não foi alterado.", parent=d)
                atualizar()
                return
            if not self._salvar():
                self.cofre.restaurar_pc(anterior)
                atualizar()
                return
            atualizar()
            extra = ("\n\nIMPORTANTE: backups feitos ANTES de hoje continuam abrindo em qualquer computador. "
                     "Faça um backup novo e guarde/apague os antigos com cuidado." if codigo else "")
            messagebox.showinfo("Computadores autorizados", f'Computador "{nome}" autorizado.' + extra, parent=d)

        def remover():
            """Tira o computador selecionado da lista, depois de confirmar."""
            sel = lista.selection()
            if not sel:
                messagebox.showinfo("Computadores autorizados", "Selecione o computador a remover.", parent=d)
                return
            m = self.cofre.pc["maquinas"][int(sel[0])]
            if not messagebox.askyesno("Remover computador", f'Remover "{m["nome"]}" da lista?\n\n'
                                       "Ele deixará de abrir o cofre (só com o código de recuperação).",
                                       parent=d, perigoso=True):
                return
            if not self._confirmar_senha_atual("Remover computador"):
                return
            anterior = self.cofre.estado_pc()
            try:
                self.cofre.pc_remover(m["id"])
            except ValueError as ex:
                messagebox.showerror("Computadores autorizados", str(ex), parent=d)
                return
            if not self._salvar():
                self.cofre.restaurar_pc(anterior)
            atualizar()

        def novo_codigo():
            """Gera um novo código de recuperação único (o anterior deixa de valer)."""
            if not messagebox.askyesno("Novo código de recuperação", "Gerar um novo código de recuperação?\n\n"
                                       "O código antigo deixa de funcionar.", parent=d, perigoso=True):
                return
            if not self._confirmar_senha_atual("Novo código de recuperação"):
                return
            anterior = self.cofre.estado_pc()
            codigo = self.cofre.novo_codigo_recuperacao()
            if not self.mostrar_codigo_recuperacao(codigo):
                self.cofre.restaurar_pc(anterior)
                return
            if not self._salvar():
                self.cofre.restaurar_pc(anterior)
            atualizar()

        def desativar():
            """Desliga a exigência de computador autorizado, depois de confirmar."""
            if not messagebox.askyesno("Desativar", "Desativar os computadores autorizados?\n\nO cofre volta a abrir "
                                       "em qualquer computador (continua pedindo a senha e a chave FIDO, se houver).",
                                       parent=d, perigoso=True):
                return
            if not self._confirmar_senha_atual("Desativar computadores autorizados"):
                return
            anterior = self.cofre.estado_pc()
            self.cofre.desativar_pc()
            if not self._salvar():
                self.cofre.restaurar_pc(anterior)
            atualizar()

        bt = ttk.Frame(fr)
        bt.pack(fill="x", pady=(14, 0))
        b_aut = ttk.Button(bt, text="Autorizar este computador", command=autorizar, style="Primario.TButton",
                           image=imagem_icone(self.root, "novo", "#ffffff"), compound="left")
        b_aut.pack(side="left")
        b_rem = ttk.Button(bt, text="Remover selecionado", command=remover)
        b_rem.pack(side="left", padx=8)
        b_rec = ttk.Button(bt, text="Novo código de recuperação", command=novo_codigo)
        b_rec.pack(side="left")
        def alternar_multiplos():
            """Muda a resposta 'tenho mais computadores': SIM libera até MAX_PC, NÃO limita a 1."""
            novo = not self.cofre.pcs_multiplos()
            if novo:
                if not messagebox.askyesno("Mais computadores", f"Liberar até {MAX_PC} computadores neste cofre?",
                                           parent=d):
                    return
            elif not messagebox.askyesno("Limitar a 1 computador", "Limitar o cofre a 1 computador?",
                                         parent=d, perigoso=True):
                return
            if not self._confirmar_senha_atual("Alterar limite de computadores"):
                return
            try:
                self.cofre.definir_pcs_multiplos(novo)
            except ValueError as ex:
                messagebox.showerror("Computadores autorizados", str(ex), parent=d)
                return
            if not self._salvar():
                self.cofre.meta["pcs_multiplos"] = not novo
            b_mult.config(text="Limitar a 1 computador" if self.cofre.pcs_multiplos() else "Liberar mais computadores")

        b_mult = ttk.Button(bt, text="Limitar a 1 computador" if self.cofre.pcs_multiplos() else "Liberar mais computadores",
                            command=alternar_multiplos)
        b_mult.pack(side="left", padx=8)
        b_des = ttk.Button(bt, text="Desativar", command=desativar, style="Perigo.TButton")
        b_des.pack(side="left", padx=8)
        ttk.Button(bt, text="Fechar", command=d.destroy).pack(side="right")
        atualizar()

    # ---------- Backup, bloqueio da tela e fechar o programa ----------

    def backup(self):
        """Salva uma cópia do cofre num arquivo escolhido (de preferência fora do disco do Windows).
        Antes de tudo pede a CHAVE DE ACESSO e a confere com o cofre (cofre 'só senha' não tem chave)."""
        if self.cofre is not None and self.cofre.modo != MODO_S:
            for tentativa in range(3):
                txt = self._pedir_senha("Backup do cofre", "Para fazer o backup, digite a sua CHAVE DE ACESSO "
                                        "(a de 8 grupos de 4 letras e números):")
                if txt is None:
                    return
                if self.cofre.confere_chave_acesso(txt):
                    zerar_objeto(txt)
                    break
                zerar_objeto(txt)
                messagebox.showerror("Backup do cofre", "Essa não é a chave de acesso deste cofre. "
                                     + ("Confira o papel/arquivo onde você a guardou." if tentativa < 2
                                        else "Backup cancelado: nada foi salvo."))
                if tentativa == 2:
                    return
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
            with open(self.caminho, "rb") as f:
                origem = f.read(LIMITE_COFRE + 1)
            _gravar_atomico(destino, origem)             # .tmp + conferência SHA-256 + troca atômica
            with open(destino, "rb") as f:
                copia = f.read(LIMITE_COFRE + 1)
            _ler_cabecalho(copia)                      # a cópia precisa ser um cofre legível
            if copia != origem:
                raise OSError("a cópia gravada não é idêntica ao original")
            messagebox.showinfo("Backup", "Backup salvo e conferido (o arquivo continua criptografado).\n\n"
                                f"Hash (SHA-256): {hashlib.sha256(copia).hexdigest()[:16]}\n"
                                "Anote-a se quiser comparar mais tarde.")
        except (OSError, ArquivoInvalido) as ex:
            diag_registrar(DIAG_BACKUP, ex)
            messagebox.showerror("Erro", f"Falha no backup (o arquivo de destino NÃO é confiável):\n{texto_erro(ex)}")

    def _limpar_residuos(self):
        """Ao bloquear: cancela timers e solta tudo o que ainda aponta para dados do cofre
        (lista de contas na tela, campos revelados, resumo do painel de detalhes)."""
        limpar_cache_auditoria()
        self.__dict__.pop("_cache_auditoria_lista", None)
        self.__dict__.pop("_cache_lista_ordenada", None)
        for nome in ("_detalhe_pendente", "_timer_aviso", "_timer_busca"):
            t = getattr(self, nome, None)
            if t:
                try:
                    self.root.after_cancel(t)
                except (tk.TclError, ValueError):
                    pass
            setattr(self, nome, None)
        for t in list(getattr(self, "_timers_revelar", {}).values()):
            try:
                self.root.after_cancel(t)
            except (OSError, AttributeError, ctypes.ArgumentError, TypeError):
                continue
        self._timers_revelar = {}
        self._revelados = set()
        self._detalhe_chave = None
        try:
            if hasattr(self, "tree"):
                self.tree._linhas = []
                self.tree._idx = {}
                self.tree._sel = None
                self.tree._assinatura = None
        except (AttributeError, tk.TclError):
            pass
        try:
            if hasattr(self, "busca"):
                self.busca.set("")                  # termo digitado na busca
        except (AttributeError, tk.TclError):
            pass
        try:
            if hasattr(self, "lateral_pessoas"):
                self.lateral_pessoas._itens = {}
                self.lateral_pessoas._ordem = []
                self.lateral_pessoas._entradas = []
                self.lateral_pessoas._indice = {}
                self.lateral_pessoas._assinatura = None
                self.lateral_pessoas._sel = None
            if hasattr(self, "lateral"):
                self.lateral._itens = {}
                self.lateral._ordem = []
                self.lateral._entradas = []
                self.lateral._indice = {}
                self.lateral._assinatura = None
                self.lateral._sel = None
        except (AttributeError, tk.TclError):
            pass
        for nome in ("tree", "lateral", "lateral_pessoas", "detalhe", "campo_busca", "busca"):
            try:
                delattr(self, nome)
            except AttributeError:
                pass

    def bloquear(self):
        """Bloqueia o cofre: apaga as chaves da memória, limpa a área de transferência e volta ao desbloqueio."""
        if getattr(self, "_salvando", False):          # nunca apaga as chaves no meio de uma gravação
            try:
                self.root.after(300, self.bloquear)
            except tk.TclError:
                pass
            return
        self._mostrar_conteudo()
        self._liberado_em = {}
        self._fechar_aviso_bloqueio()
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
        self._limpar_residuos()
        self.tela_desbloqueio()
        varrer_memoria_livre()              # sobrescreve restos de textos descartados (melhor esforço)

    def _ao_perigo(self):
        """Suspensão/hibernação, Win+L ou desligamento: apaga as chaves da memória AGORA (antes de o Windows
        gravar a RAM no disco)."""
        try:
            if self.cofre:                    # dentro do WndProc: SÓ apaga as chaves (rápido e sem Tk)
                self.cofre.fechar()
                self.cofre = None
                varrer_memoria_livre(2000)     # ~15 ms: restos de textos antes de o Windows gravar a RAM
            self.root.after_idle(self.bloquear)       # a troca de tela acontece fora do WndProc
        except (AttributeError, OSError, RuntimeError, tk.TclError, ValueError) as ex:
            diag_registrar(DIAG_INTERFACE, ex)

    def sair(self):
        """Fecha o programa (bloqueando antes), perguntando se ainda há tarefa em andamento."""
        if getattr(self, "_trabalhando", False) and not messagebox.askyesno(
                "Verificando a senha",
                "O cofre ainda está verificando a senha. Fechar agora GASTA uma tentativa.\n\nFechar mesmo assim?", perigoso=True):
            return
        try:
            if getattr(self, "_hook_energia", None) and self._hook_energia.get("desfazer"):
                self._hook_energia["desfazer"]()
        except (AttributeError, OSError, RuntimeError, ctypes.ArgumentError, TypeError) as ex:
            diag_registrar(DIAG_INTERFACE, ex)
        if self.cofre:
            self.cofre.fechar()
        self._limpar_clip(forcar=True)
        self._parar_monitor_espias()
        self._cancelar_todos_after()
        self.root.destroy()

    def _cancelar_todos_after(self):
        """Cancela TODOS os after() pendentes nesta janela antes de destruí-la (vigia periódica, timers de
        bloqueio por inatividade, limpeza de clipboard, passeio guiado, etc.). A lista do Tcl é global ao
        interpretador, mas cada widget guarda seus próprios comandos Python; usar root.after_cancel() em um timer
        criado por um widget deixa o comando registrado no dono errado e causa TclError durante destroy()."""
        try:
            for identificador in self.root.tk.call("after", "info"):
                try:
                    self.root.tk.call("after", "cancel", identificador)
                except (tk.TclError, ValueError):
                    pass
        except (AttributeError, tk.TclError):
            pass


# ----------------------------------------------------------------------------
# Decorador do modo consulta e ponto de entrada do programa (main)
# ----------------------------------------------------------------------------
def _so_com_escrita(metodo):
    """Decorador do MODO CONSULTA: se o cofre foi aberto somente para leitura, a ação que altera dados não abre
    formulário nenhum (para o usuário não digitar à toa): só explica e volta."""
    def interno(self, *a, **k):
        """Recusa a ação no modo consulta; fora dele, executa normalmente."""
        if self.cofre is not None and self.cofre.somente_leitura:
            if self.cofre.motivo_consulta == "em_uso":
                messagebox.showinfo("Modo consulta", "Este cofre está aberto em outra janela: aqui você só pode ver e "
                                    "copiar. Para adicionar, alterar ou apagar, use a outra janela (ou feche-a e abra "
                                    "o cofre de novo).")
            else:
                messagebox.showinfo("Modo consulta", "O pendrive está protegido contra gravação: nesta sessão você só "
                                    "pode ver e copiar. Para adicionar, alterar ou apagar, destrave o pendrive e abra "
                                    "o cofre de novo.")
            return None
        return metodo(self, *a, **k)
    interno.__name__ = metodo.__name__
    interno.__doc__ = metodo.__doc__
    return interno


for _nome in ("configurar_bloqueio", "configurar_protecao_extra", "_adicionar_pessoa", "_renomear_pessoa", "_remover_pessoa", "_grupo_para_pessoa",
              "_renomear_grupo", "excluir", "dialogo_registro", "trocar_senha", "importar", "gerenciar_fido", "gerenciar_computadores", "nova_chave",
              "configurar_tentativas"):
    setattr(App, _nome, _so_com_escrita(getattr(App, _nome)))


def main():
    """Ponto de entrada: confere o ambiente, endurece o processo e abre a janela do programa."""
    if tk is None:
        _aviso_fatal(_NOME_APP, "Tkinter não encontrado.\n\nInstale o Python oficial de python.org "
                     "(ele já vem com Tkinter).")
        sys.exit(1)
    caminho = sys.argv[1] if len(sys.argv) > 1 else os.path.join(pasta_base(), ARQUIVO_PADRAO)
    for velho in ("erro_cofre.log", "erro_cofre.log.1"):       # versões antigas gravavam o erro em texto puro
        try:
            _destruir_um(os.path.join(pasta_base(), velho))
        except OSError:
            pass
    exe_proprio = sys.argv[0] if ocultacao_ativa() else None
    if ocultacao_ativa():
        revelar_apoio(caminho, exe_proprio)            # liberados para gravar; voltam a ficar escondidos ao sair
    blindar_processo()
    if EH_WINDOWS:
        try:                                          # nitidez em telas com 125%, 150%...
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError, ctypes.ArgumentError, TypeError):
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except (AttributeError, OSError, ctypes.ArgumentError, TypeError):
                pass
    root = tk.Tk()
    root.withdraw()                                   # só aparece quando a primeira tela estiver pronta
    em_uso = not instancia_unica(caminho)
    if ocultacao_ativa() and not em_uso:                # só o dono da trava esconde (a janela de consulta não)
        atexit.register(ocultar_apoio, caminho, exe_proprio)   # registrado ANTES do TEMP privado: roda DEPOIS da limpeza dele
        apoio_ativar(caminho, exe_proprio)             # esconde o cofre e as cópias JÁ (só aparecem no instante de gravar)
    if not em_uso:
        isolar_temporarios()                           # TEMP privado no pendrive (some ao sair); só o dono da trava
    aviso_fs = aviso_sistema_de_arquivos(sistema_de_arquivos(caminho))
    if aviso_fs and politica_exigir_ntfs():            # política opcional: recusa abrir em FAT/exFAT
        root.withdraw()
        messagebox.showerror("Pendrive não aceito",
                             "Este cofre está configurado para abrir SOMENTE em pendrive NTFS (ou ReFS), e este não é.\n\n"
                             f"{aviso_fs}\n\nO arquivo NÃO foi alterado. Formate o pendrive em NTFS (copie o cofre antes) ou "
                             f"apague o arquivo {NOME_MARCADOR_NTFS} da pasta do programa para voltar ao modo só-alerta.")
        root.destroy()
        sys.exit(6)
    if em_uso and not os.path.exists(caminho):         # outra janela está CRIANDO este cofre agora: nada para ler
        root.withdraw()
        messagebox.showerror("Cofre já aberto", "Este cofre está sendo criado em outra janela. Termine lá e abra de novo.")
        root.destroy()
        sys.exit(5)
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
    try:
        nomes = processos_abertos()
    except OSError:
        root.withdraw()
        messagebox.showerror("Verificação de segurança indisponível",
                             "Não foi possível verificar os programas abertos. O cofre não será iniciado.")
        root.destroy()
        sys.exit(7)
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
    def erro_interno(tipo, valor, tb):
        """Registra um erro inesperado em arquivo (sem segredos) e avisa o usuário."""
        diag_registrar(DIAG_INTERFACE, valor, tb)
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
                                     "cofre não foram alterados por ela.\n\nReferência do erro (sem senhas): "
                                     f"{diag_referencia(valor, tb)}\n\nO detalhe também ficou guardado, cifrado: "
                                     "menu ⋯ › Diagnóstico › Copiar relatório.")
        except (AttributeError, OSError, RuntimeError, tk.TclError):
            _aviso_fatal("Algo deu errado", "A ação falhou e não foi possível exibir os detalhes.")
    root.report_callback_exception = erro_interno
    App(root, caminho, em_uso=em_uso)
    revelar_janela(root)                           # primeira tela já montada: aparece de uma vez
    if aviso_fs and not aviso_ja_visto(aviso_fs):  # aviso inicial: aparece UMA vez (depois fica só a linha curta na tela)
        def _aviso_fs_unico():
            """Mostra o alerta do pendrive sem permissões e lembra que já foi visto."""
            marcar_aviso_visto(aviso_fs)
            messagebox.showwarning("Pendrive sem permissões de arquivo", aviso_fs)
        root.after(100, _aviso_fs_unico)
    if em_uso:
        root.after(200, lambda: messagebox.showinfo(
            "Cofre já aberto em outra janela",
            "Esta janela abre em MODO CONSULTA: dá para ver e copiar, mas nada é salvo e as tentativas de senha "
            "não são contadas."))
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        diag_registrar(DIAG_NAO_TRATADO, sys.exc_info()[1], sys.exc_info()[2])
        _aviso_fatal(_NOME_APP, "O cofre encontrou um erro e fechou.\n\nReferência do erro (sem senhas): "
                     f"{diag_referencia(sys.exc_info()[1], sys.exc_info()[2])}\n\nO detalhe ficou guardado, cifrado: "
                     "abra o cofre de novo e veja em ⋯ › Diagnóstico. "
                     "Seus dados no cofre.dat não foram alterados.")
        sys.exit(1)
