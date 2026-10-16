"""Aparência comum do app: fontes, cores e o botão principal (uma ação de destaque por tela)."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

COR_PRIMARIA = "#1f5fbf"
COR_PRIMARIA_ESCURA = "#184c98"
COR_PRIMARIA_DESATIVADA = "#a9bddc"
COR_SUAVE = "#5f6b7a"
COR_ALERTA = "#b00020"
COR_OK = "#1b5e20"
FAMILIA = "Segoe UI"


def aplicar(raiz: tk.Misc) -> ttk.Style:
    """Ajusta as fontes e os estilos nomeados usados nas telas."""
    for nome in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
        try:
            tkfont.nametofont(nome).configure(family=FAMILIA, size=10)
        except tk.TclError:
            pass
    estilo = ttk.Style(raiz)
    estilo.configure("Suave.TLabel", foreground=COR_SUAVE)
    estilo.configure("Titulo.TLabel", font=(FAMILIA, 13, "bold"))
    estilo.configure("Secao.TLabel", font=(FAMILIA, 10, "bold"))
    estilo.configure("Link.Toolbutton", foreground=COR_PRIMARIA)  # texto azul: parece clicável
    estilo.configure("Alerta.TLabel", foreground=COR_ALERTA)
    estilo.configure("Ok.TLabel", foreground=COR_OK)
    estilo.configure("Evid.Treeview", rowheight=62)  # lista com miniaturas
    estilo.configure("Tabela.Treeview", rowheight=30)
    return estilo


def botao_primario(pai: tk.Misc, texto: str, comando, **opcoes) -> tk.Button:
    """Botão azul de destaque: a ação principal da tela (só um por tela)."""
    botao = tk.Button(
        pai, text=texto, command=comando, font=(FAMILIA, 10, "bold"), fg="white", bg=COR_PRIMARIA,
        activebackground=COR_PRIMARIA_ESCURA, activeforeground="white", disabledforeground="white",
        relief="flat", bd=0, padx=20, pady=9, cursor="hand2", highlightthickness=2,
        highlightbackground=pai.winfo_toplevel().cget("background") if hasattr(pai, "winfo_toplevel") else "white",
        highlightcolor="#7fb0ff", **opcoes)
    botao.bind("<Enter>", lambda _e: botao.configure(bg=COR_PRIMARIA_ESCURA) if _ativo(botao) else None)
    botao.bind("<Leave>", lambda _e: botao.configure(bg=COR_PRIMARIA) if _ativo(botao) else None)
    return botao


def _ativo(botao: tk.Button) -> bool:
    return str(botao.cget("state")) != "disabled"


def ativar(botao: tk.Button, ativo: bool) -> None:
    """Liga/desliga um botão primário (desligado fica azul claro e não responde)."""
    botao.configure(state="normal" if ativo else "disabled", bg=COR_PRIMARIA if ativo else COR_PRIMARIA_DESATIVADA,
                    cursor="hand2" if ativo else "arrow")
