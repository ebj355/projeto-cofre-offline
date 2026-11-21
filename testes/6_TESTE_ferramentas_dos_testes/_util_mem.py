# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Auxiliar dos testes (não é um teste): pico de memória do processo em KB, no Linux (resource) e no Windows (psapi)."""


def pico_kb():
    """Maior uso de memória residente do processo até agora, em KB. Linux/macOS: resource.ru_maxrss; Windows:
    PeakWorkingSetSize (o módulo `resource` não existe no Windows)."""
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except ImportError:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            """PROCESS_MEMORY_COUNTERS do Windows."""
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        pmc = PMC()
        pmc.cb = ctypes.sizeof(pmc)
        k = ctypes.WinDLL("kernel32")
        p = ctypes.WinDLL("psapi")
        k.GetCurrentProcess.restype = wintypes.HANDLE
        p.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        p.GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
        return pmc.PeakWorkingSetSize // 1024
