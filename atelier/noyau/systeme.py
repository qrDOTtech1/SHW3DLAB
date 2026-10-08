"""Mesures systeme sans dependance (Windows : ctypes) : RAM totale / utilisee, memoire du serveur."""
from __future__ import annotations

import ctypes
import os


class _MEM(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


class _PMC(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong), ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t)]


def ram() -> dict:
    """{'total_go', 'utilise_go', 'pct', 'processus_mo'} (processus = ce programme)."""
    out = {"total_go": 0.0, "utilise_go": 0.0, "pct": 0, "processus_mo": 0}
    if os.name != "nt":
        return out
    m = _MEM(); m.dwLength = ctypes.sizeof(_MEM)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
        out.update(total_go=round(m.ullTotalPhys / 2 ** 30, 1), utilise_go=round((m.ullTotalPhys - m.ullAvailPhys) / 2 ** 30, 1),
                   pct=int(m.dwMemoryLoad))
    try:
        pmc = _PMC(); pmc.cb = ctypes.sizeof(_PMC)
        ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        h = ctypes.windll.kernel32.GetCurrentProcess()
        if ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb):
            out["processus_mo"] = int(pmc.WorkingSetSize / 2 ** 20)
    except Exception:
        pass
    return out
