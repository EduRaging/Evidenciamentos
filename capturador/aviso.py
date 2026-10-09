"""Aviso rápido no canto da tela ("Evidência 3 capturada"), sem roubar o foco."""
from __future__ import annotations

import tkinter as tk

from . import winutil


def mostrar_aviso(raiz: tk.Misc, texto: str, monitor: tuple[int, int, int, int],
                  duracao_ms: int = 1600) -> None:
    aviso = tk.Toplevel(raiz)
    aviso.withdraw()
    aviso.overrideredirect(True)
    aviso.attributes("-topmost", True)
    tk.Label(aviso, text=texto, bg="#1f2933", fg="white", padx=16, pady=10,
             font=("Segoe UI", 10)).pack()
    aviso.update_idletasks()
    _, _, direita, base = monitor
    x = direita - aviso.winfo_reqwidth() - 24
    y = base - aviso.winfo_reqheight() - 64  # acima da barra de tarefas
    aviso.geometry(f"+{x}+{y}")
    winutil.nao_ativar(aviso)
    winutil.excluir_da_captura(aviso)
    aviso.deiconify()
    aviso.after(duracao_ms, aviso.destroy)
