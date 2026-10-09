"""Captura da tela (monitor sob o cursor) e seleção de recorte."""
from __future__ import annotations

import ctypes
import tkinter as tk
from ctypes import wintypes

from PIL import Image, ImageEnhance, ImageGrab, ImageTk

Retangulo = tuple[int, int, int, int]  # esquerda, topo, direita, base (coords do desktop virtual)

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
user32.MonitorFromPoint.restype = wintypes.HANDLE
user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
user32.GetMonitorInfoW.restype = wintypes.BOOL

MONITOR_DEFAULTTONEAREST = 2
TAMANHO_MINIMO_RECORTE = 4  # px; cliques sem arrasto não viram recorte


class _InfoMonitor(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def ativar_dpi() -> None:
    """Coordenadas em pixels reais. Chamar ANTES de criar a janela Tk."""
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()


def retangulo_do_monitor_do_cursor() -> Retangulo:
    ponto = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(ponto))
    monitor = user32.MonitorFromPoint(ponto, MONITOR_DEFAULTTONEAREST)
    info = _InfoMonitor()
    info.cbSize = ctypes.sizeof(_InfoMonitor)
    user32.GetMonitorInfoW(monitor, ctypes.byref(info))
    r = info.rcMonitor
    return r.left, r.top, r.right, r.bottom


def capturar_monitor() -> tuple[Image.Image, Retangulo]:
    """Print do monitor onde está o cursor. Devolve (imagem, retângulo do monitor)."""
    retangulo = retangulo_do_monitor_do_cursor()
    # layered=True inclui tooltips/menus translúcidos; bbox em coords do desktop virtual
    imagem = ImageGrab.grab(bbox=retangulo, include_layered_windows=True, all_screens=True)
    return imagem, retangulo


def selecionar_recorte(raiz: tk.Misc, imagem: Image.Image, retangulo: Retangulo) -> Image.Image | None:
    """Mostra o print congelado, escurecido, sobre o monitor e deixa arrastar a área.

    Devolve o recorte ou None se cancelado (Esc ou botão direito).
    """
    largura, altura = imagem.size
    escura = ImageEnhance.Brightness(imagem).enhance(0.45)

    topo = tk.Toplevel(raiz)
    topo.overrideredirect(True)
    topo.attributes("-topmost", True)
    topo.geometry(f"{largura}x{altura}+{retangulo[0]}+{retangulo[1]}")
    tela = tk.Canvas(topo, width=largura, height=altura, highlightthickness=0,
                     cursor="crosshair", bg="black")
    tela.pack()
    foto_escura = ImageTk.PhotoImage(escura)
    tela.create_image(0, 0, anchor="nw", image=foto_escura)

    dica = tela.create_text(largura // 2, 28, fill="white", font=("Segoe UI", 11),
                            text="Arraste para selecionar a área  •  Esc ou botão direito cancela")
    x0, y0, x1, y1 = tela.bbox(dica)
    fundo_dica = tela.create_rectangle(x0 - 12, y0 - 6, x1 + 12, y1 + 6, fill="#1f2933", outline="")
    tela.tag_lower(fundo_dica, dica)

    estado: dict = {"inicio": None, "caixa": None, "resultado": None, "foto": None}

    def calcular_caixa(evento) -> tuple[int, int, int, int]:
        ax, ay = estado["inicio"]
        bx = min(max(evento.x, 0), largura)
        by = min(max(evento.y, 0), altura)
        return min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)

    def desenhar(caixa) -> None:
        tela.delete("selecao")
        esq, cima, dir_, baixo = caixa
        if dir_ - esq < 1 or baixo - cima < 1:
            return
        estado["foto"] = ImageTk.PhotoImage(imagem.crop(caixa))  # trecho em brilho normal
        tela.create_image(esq, cima, anchor="nw", image=estado["foto"], tags="selecao")
        tela.create_rectangle(esq, cima, dir_, baixo, outline="#38bdf8", width=2, tags="selecao")
        rotulo = tela.create_text(esq + 4, max(cima - 14, 10), anchor="w", fill="white",
                                  font=("Segoe UI", 9, "bold"),
                                  text=f"{dir_ - esq} × {baixo - cima}", tags="selecao")
        fx0, fy0, fx1, fy1 = tela.bbox(rotulo)
        fundo = tela.create_rectangle(fx0 - 4, fy0 - 2, fx1 + 4, fy1 + 2, fill="#0c4a6e",
                                      outline="", tags="selecao")
        tela.tag_lower(fundo, rotulo)

    def ao_pressionar(evento) -> None:
        estado["inicio"] = (min(max(evento.x, 0), largura), min(max(evento.y, 0), altura))

    def ao_arrastar(evento) -> None:
        if estado["inicio"]:
            estado["caixa"] = calcular_caixa(evento)
            desenhar(estado["caixa"])

    def ao_soltar(evento) -> None:
        if not estado["inicio"]:
            return
        esq, cima, dir_, baixo = calcular_caixa(evento)
        estado["inicio"] = None
        if dir_ - esq < TAMANHO_MINIMO_RECORTE or baixo - cima < TAMANHO_MINIMO_RECORTE:
            tela.delete("selecao")
            return
        estado["resultado"] = (esq, cima, dir_, baixo)
        topo.destroy()

    def cancelar(_evento=None) -> None:
        topo.destroy()

    tela.bind("<ButtonPress-1>", ao_pressionar)
    tela.bind("<B1-Motion>", ao_arrastar)
    tela.bind("<ButtonRelease-1>", ao_soltar)
    tela.bind("<ButtonPress-3>", cancelar)
    topo.bind("<Escape>", cancelar)

    topo.update_idletasks()
    topo.lift()
    topo.focus_force()
    raiz.wait_window(topo)

    caixa = estado["resultado"]
    return imagem.crop(caixa) if caixa else None
