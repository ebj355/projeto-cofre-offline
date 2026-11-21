# -*- coding: utf-8 -*-
"""
Smoke visual do CofreSenhas.exe COMPILADO (so Windows).

Abre o .exe apontando para um cofre temporario (o seu cofre real NAO e tocado), mede quanto demora ate a janela
principal aparecer e confere: o processo continua vivo, a janela existe e e visivel, tem tamanho razoavel, cabe
na area util do monitor, e o DPI da janela. Depois fecha pelo botao X (WM_CLOSE) e confere a saida limpa.

Se o programa recusar abrir (depurador, ferramenta espia, acesso remoto...), o codigo de saida e traduzido.

Uso:  python teste_exe_visual_smoke_windows.py [caminho\\CofreSenhas.exe]
"""
import os
import sys
import time
import ctypes
import tempfile
import shutil
import subprocess
from ctypes import wintypes

AQUI = os.path.dirname(os.path.abspath(__file__))
CODIGOS = {1: "erro fatal inesperado", 2: "depurador detectado", 3: "acesso remoto recusado pelo usuario",
           4: "ferramenta espia aberta", 5: "cofre sendo criado em outra janela", 6: "pendrive sem NTFS (politica)",
           7: "verificacao de seguranca indisponivel"}


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]


def pids_do_processo(pid, executavel):
    """Inclui os filhos do bootstrap onefile, que podem ser donos da janela real."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32))
    k32.Process32FirstW.restype = wintypes.BOOL
    k32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32))
    k32.Process32NextW.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    k32.CloseHandle.restype = wintypes.BOOL
    snapshot = k32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        processos = {}
        entrada = PROCESSENTRY32()
        entrada.dwSize = ctypes.sizeof(entrada)
        if k32.Process32FirstW(snapshot, ctypes.byref(entrada)):
            while True:
                processos[int(entrada.th32ProcessID)] = (
                    int(entrada.th32ParentProcessID), entrada.szExeFile.casefold())
                if not k32.Process32NextW(snapshot, ctypes.byref(entrada)):
                    break
    finally:
        k32.CloseHandle(snapshot)

    nome = os.path.basename(executavel).casefold()
    ids = {int(pid)}
    mudou = True
    while mudou:
        mudou = False
        for filho, (pai, nome_filho) in processos.items():
            if pai in ids and filho not in ids and nome_filho == nome:
                ids.add(filho)
                mudou = True
    return ids


def terminar_pid(pid):
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
    k32.TerminateProcess.restype = wintypes.BOOL
    k32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    k32.WaitForSingleObject.restype = wintypes.DWORD
    k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    k32.CloseHandle.restype = wintypes.BOOL
    handle = k32.OpenProcess(0x0001 | 0x00100000, False, int(pid))
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not k32.TerminateProcess(handle, 1) and k32.WaitForSingleObject(handle, 0) == 0x00000102:
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        k32.CloseHandle(handle)


def achar_exe():
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        return sys.argv[1]
    pasta = AQUI
    for _ in range(5):
        for sub in ("", "CofreSenhas"):
            p = os.path.join(pasta, sub, "CofreSenhas.exe")
            if os.path.isfile(p):
                return p
        pasta = os.path.dirname(pasta)
    return None


def janelas_do_processo(pids):
    u32 = ctypes.windll.user32
    achadas = []
    ENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _):
        p = wintypes.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value in pids and u32.IsWindowVisible(hwnd):
            n = u32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            u32.GetWindowTextW(hwnd, buf, n + 1)
            r = wintypes.RECT()
            u32.GetWindowRect(hwnd, ctypes.byref(r))
            achadas.append((hwnd, buf.value, r))
        return True
    u32.EnumWindows(ENUM(cb), 0)
    return achadas


def pid_da_janela(hwnd):
    pid = wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def main():
    if sys.platform != "win32":
        print("[PULADO] este teste so vale no Windows.")
        return 0
    exe = achar_exe()
    if not exe:
        print("[PULADO] CofreSenhas.exe nao encontrado. Compile primeiro ou passe o caminho como argumento.")
        return 9
    falhas = 0
    u32 = ctypes.windll.user32
    tmp = tempfile.mkdtemp(prefix="exe_visual_")
    caminho = os.path.join(tmp, "cofre.dat")
    # Keep the vault nonexistent: the close failure was reproduced on the first-use screen, not with an existing vault.
    ambiente = dict(os.environ, COFRE_GUI_TESTS_BACKGROUND="1")
    try:
        inicio = time.perf_counter()
        proc = subprocess.Popen([exe, caminho], cwd=os.path.dirname(exe), env=ambiente)
    except PermissionError as ex:
        shutil.rmtree(tmp, ignore_errors=True)
        if getattr(ex, "winerror", None) == 5:
            print("[PULADO] Windows ou uma politica de seguranca negou a inicializacao (WinError 5); nenhum bloqueio foi contornado.")
            return 9
        raise
    try:
        principal = None
        fim = time.time() + 90
        while time.time() < fim:
            if proc.poll() is not None:
                break
            pids = pids_do_processo(proc.pid, exe)
            js = [j for j in janelas_do_processo(pids) if (j[2].right - j[2].left) > 300]
            if js:
                principal = max(js, key=lambda j: (j[2].right - j[2].left) * (j[2].bottom - j[2].top))
                print(f"[INFO] tempo até a janela aparecer: {time.perf_counter() - inicio:.2f} s")
                time.sleep(2.0)                       # deixa a tela terminar de montar
                break
            time.sleep(0.5)
        if principal is None:
            cod = proc.poll()
            motivo = CODIGOS.get(cod, "sem janela em 40 s") if cod is not None else "sem janela em 40 s"
            print(f"[FALHOU] o .exe nao mostrou a janela principal: {motivo} (codigo {cod}; "
                  f"{time.perf_counter() - inicio:.1f} s aguardados)")
            return 1
        hwnd, titulo, r = principal
        largura, altura = r.right - r.left, r.bottom - r.top
        print(f"[OK] janela encontrada: '{titulo}' {largura}x{altura}; PIDs: {sorted(pids)}")
        u32.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
        u32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        estilo = u32.GetWindowLongPtrW(hwnd, -20)
        if estilo & 0x08000000:
            print("[OK] janela de teste está em segundo plano e não ativa")
        else:
            print("[FALHOU] a janela de teste não recebeu WS_EX_NOACTIVATE")
            falhas += 1
        foreground = u32.GetForegroundWindow()
        if foreground and pid_da_janela(foreground) in pids:
            print("[FALHOU] o Cofre tomou o foco do aplicativo do usuário")
            falhas += 1
        else:
            print("[OK] o aplicativo do usuário manteve o foco")
        if proc.poll() is not None:
            print(f"[FALHOU] o programa fechou sozinho logo depois de abrir (codigo {proc.returncode})")
            falhas += 1
        if largura < 700 or altura < 450:
            print(f"[FALHOU] janela pequena demais ({largura}x{altura})")
            falhas += 1
        try:
            dpi = u32.GetDpiForWindow(hwnd)
            print(f"[OK] DPI da janela: {dpi} ({dpi * 100 // 96}%)")
        except (AttributeError, OSError):
            print("[ALERTA] nao consegui ler o DPI da janela")
        mon = u32.MonitorFromWindow(hwnd, 2)
        class MI(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
        mi = MI()
        mi.cbSize = ctypes.sizeof(MI)
        if u32.GetMonitorInfoW(mon, ctypes.byref(mi)):
            w = mi.rcWork
            if r.left < w.left - 8 or r.top < w.top - 8 or r.right > w.right + 8 or r.bottom > w.bottom + 8:
                print(f"[FALHOU] a janela passa da area util do monitor (janela {r.left},{r.top},{r.right},{r.bottom}"
                      f" / area {w.left},{w.top},{w.right},{w.bottom})")
                falhas += 1
            else:
                print("[OK] a janela cabe na area util do monitor")
        u32.PostMessageW(hwnd, 0x0010, 0, 0)          # WM_CLOSE
        try:
            proc.wait(timeout=15)
            filhos_ativos = pids_do_processo(proc.pid, exe) - {proc.pid}
            if filhos_ativos:
                print(f"[FALHOU] processos-filho ainda ativos depois do fechamento: {sorted(filhos_ativos)}")
                falhas += 1
            else:
                print(f"[OK] fechou pelo X (codigo de saida {proc.returncode})")
        except subprocess.TimeoutExpired:
            print("[FALHOU] o programa nao fechou em 15 s depois do pedido de fechar")
            abertas = janelas_do_processo(pids_do_processo(proc.pid, exe))
            if abertas:
                print("[INFO] janelas ainda abertas: " +
                      ", ".join(f"{titulo!r} (HWND {hwnd})" for hwnd, titulo, _ in abertas))
            falhas += 1
        return 1 if falhas else 0
    finally:
        filhos = pids_do_processo(proc.pid, exe) - {proc.pid}
        for pid_filho in filhos:
            terminar_pid(pid_filho)
        if proc.poll() is None:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    rc = main()
    if rc == 9:
        print("[PULADO] smoke visual do .exe; confira o motivo registrado acima.")
    elif rc == 0:
        print("[OK] smoke visual do .exe concluido.")
    else:
        print("[FALHOU] smoke visual do .exe com problemas.")
    sys.exit(rc)
