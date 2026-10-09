"""Pequenos recursos do Windows usados pela interface."""
from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE

GA_ROOT = 2
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WDA_EXCLUDEFROMCAPTURE = 0x11  # Windows 10 2004+
ERROR_ALREADY_EXISTS = 183

_mutex = None  # mantém o handle vivo enquanto o processo existir


def _hwnd(janela) -> int:
    janela.update_idletasks()
    return user32.GetAncestor(janela.winfo_id(), GA_ROOT)


def excluir_da_captura(janela) -> bool:
    """Faz a janela do app não aparecer nos prints (a tela por baixo é capturada)."""
    return bool(user32.SetWindowDisplayAffinity(_hwnd(janela), WDA_EXCLUDEFROMCAPTURE))


def nao_ativar(janela) -> None:
    """Janela que aparece sem roubar o foco (não fecha menus abertos no sistema testado)."""
    hwnd = _hwnd(janela)
    estilo = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, estilo | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)


def instancia_unica() -> bool:
    """True se esta é a única instância do app em execução."""
    global _mutex
    _mutex = kernel32.CreateMutexW(None, False, "Local\\CapturadorEvidencias")
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS
