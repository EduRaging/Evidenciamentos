"""Atalhos globais de teclado (RegisterHotKey) e conversão de/para texto.

Os atalhos são guardados como texto, ex.: "ctrl+shift+f9".
"""
from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from typing import Callable

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012

_MODIFICADORES = {"ctrl": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT}
_TECLAS_NOMEADAS = {
    "print": 0x2C, "pause": 0x13, "scrolllock": 0x91, "insert": 0x2D, "delete": 0x2E,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "space": 0x20,
}
_NOME_POR_VK = {vk: nome for nome, vk in _TECLAS_NOMEADAS.items()}
# Teclas que dispensam modificador (não digitam nada sozinhas)
_SEM_MODIFICADOR = {"print", "pause", "scrolllock"}
# Códigos virtuais de Shift/Ctrl/Alt/Win: pressioná-los sozinhos não forma atalho
_VK_MODIFICADORES = {16, 17, 18, 91, 92, 160, 161, 162, 163, 164, 165}

# Tk no Windows: bits de event.state
_TK_SHIFT, _TK_CONTROL, _TK_ALT = 0x1, 0x4, 0x20000


def _vk_da_tecla(nome: str) -> int | None:
    if len(nome) == 1 and nome.isascii() and nome.isalnum():
        return ord(nome.upper())
    if nome.startswith("f") and nome[1:].isdigit() and 1 <= int(nome[1:]) <= 24:
        return 0x6F + int(nome[1:])
    return _TECLAS_NOMEADAS.get(nome)


def _nome_do_vk(vk: int) -> str | None:
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk).lower()
    if 0x70 <= vk <= 0x87:
        return f"f{vk - 0x6F}"
    return _NOME_POR_VK.get(vk)


def interpretar(atalho: str) -> tuple[int, int]:
    """'ctrl+shift+f9' -> (modificadores, código virtual). ValueError se inválido."""
    partes = [p.strip().lower() for p in atalho.split("+") if p.strip()]
    if not partes:
        raise ValueError("Atalho vazio.")
    *mods, tecla = partes
    vk = _vk_da_tecla(tecla)
    if vk is None:
        raise ValueError(f"Tecla não suportada: {tecla!r}.")
    flags = 0
    for m in mods:
        if m not in _MODIFICADORES:
            raise ValueError(f"Modificador inválido: {m!r}.")
        flags |= _MODIFICADORES[m]
    eh_funcao = tecla.startswith("f") and tecla[1:].isdigit()
    if not flags and not eh_funcao and tecla not in _SEM_MODIFICADOR:
        raise ValueError("Use ao menos Ctrl, Alt ou Shift junto com a tecla.")
    return flags, vk


def formatar(atalho: str) -> str:
    """'ctrl+shift+f9' -> 'Ctrl+Shift+F9'."""
    return "+".join(p.strip().capitalize() if len(p.strip()) > 1 else p.strip().upper()
                    for p in atalho.split("+") if p.strip())


def atalho_do_evento(state: int, keycode: int) -> str | None:
    """Converte um evento de teclado do Tk em texto de atalho.

    Retorna None se foi só um modificador (continua aguardando) e levanta
    ValueError se a combinação não puder ser usada.
    """
    if keycode in _VK_MODIFICADORES:
        return None
    tecla = _nome_do_vk(keycode)
    if tecla is None:
        raise ValueError("Essa tecla não pode ser usada como atalho.")
    partes = []
    if state & _TK_CONTROL:
        partes.append("ctrl")
    if state & _TK_ALT:
        partes.append("alt")
    if state & _TK_SHIFT:
        partes.append("shift")
    texto = "+".join([*partes, tecla])
    interpretar(texto)  # valida a regra do modificador
    return texto


user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = ctypes.c_int
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                wintypes.UINT, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


class GerenciadorAtalhos:
    """Registra atalhos globais numa thread própria e avisa por callback.

    O callback roda NA THREAD dos atalhos: quem recebe deve só enfileirar o
    evento e tratar na thread da interface (o Tk não é thread-safe).
    """

    def __init__(self, ao_disparar: Callable[[str], None]) -> None:
        self._ao_disparar = ao_disparar
        self._thread: threading.Thread | None = None
        self._id_thread = 0

    def registrar(self, atalhos: dict[str, str]) -> dict[str, str]:
        """Registra {nome: atalho}. Devolve {nome: motivo} dos que falharam."""
        self.parar()
        erros: dict[str, str] = {}
        pronto = threading.Event()

        def laco() -> None:
            msg = wintypes.MSG()
            user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # cria a fila de mensagens
            self._id_thread = kernel32.GetCurrentThreadId()
            ativos: dict[int, str] = {}
            for i, (nome, texto) in enumerate(atalhos.items(), start=1):
                try:
                    mods, vk = interpretar(texto)
                except ValueError as exc:
                    erros[nome] = str(exc)
                    continue
                if user32.RegisterHotKey(None, i, mods | MOD_NOREPEAT, vk):
                    ativos[i] = nome
                else:
                    erros[nome] = f"{formatar(texto)} já está em uso por outro programa."
            pronto.set()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam in ativos:
                    self._ao_disparar(ativos[msg.wParam])
            for i in ativos:
                user32.UnregisterHotKey(None, i)

        self._thread = threading.Thread(target=laco, name="atalhos-globais", daemon=True)
        self._thread.start()
        pronto.wait(timeout=3)
        return erros

    def parar(self) -> None:
        if self._thread and self._thread.is_alive():
            user32.PostThreadMessageW(self._id_thread, WM_QUIT, 0, 0)
            self._thread.join(timeout=2)
        self._thread = None
