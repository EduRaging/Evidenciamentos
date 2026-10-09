"""Diálogos: captura de uma combinação de teclas e janela de configurações."""
from __future__ import annotations

import tkinter as tk
from dataclasses import replace
from tkinter import filedialog, messagebox, ttk

from . import atalhos
from .config import Config

NOMES_ATALHOS = {
    "atalho_tela": "Capturar tela inteira",
    "atalho_recorte": "Recortar uma área",
    "atalho_janela": "Mostrar / ocultar esta janela",
}


def pedir_atalho(pai: tk.Misc, titulo: str) -> str | None:
    """Pede para o usuário pressionar a nova combinação. None se cancelou."""
    janela = tk.Toplevel(pai)
    janela.title(titulo)
    janela.transient(pai)
    janela.resizable(False, False)
    ttk.Label(janela, justify="center", padding=(24, 20, 24, 6),
              text="Pressione a combinação desejada\n(ex.: Ctrl+Shift+F9).  Esc cancela.").pack()
    mensagem = tk.StringVar()
    ttk.Label(janela, textvariable=mensagem, foreground="#b00020", padding=(24, 0, 24, 16)).pack()
    resultado: list[str] = []

    def ao_pressionar(evento) -> str:
        if evento.keysym == "Escape":
            janela.destroy()
            return "break"
        try:
            atalho = atalhos.atalho_do_evento(evento.state, evento.keycode)
        except ValueError as exc:
            mensagem.set(str(exc))
            return "break"
        if atalho is not None:
            resultado.append(atalho)
            janela.destroy()
        return "break"

    janela.bind("<KeyPress>", ao_pressionar)
    janela.update_idletasks()
    janela.grab_set()
    janela.focus_force()
    pai.wait_window(janela)
    return resultado[0] if resultado else None


def abrir_configuracoes(pai: tk.Misc, cfg: Config) -> Config | None:
    """Janela modal de configurações. Devolve a nova Config ou None se cancelou."""
    janela = tk.Toplevel(pai)
    janela.title("Configurações")
    janela.transient(pai)
    janela.resizable(False, False)
    quadro = ttk.Frame(janela, padding=16)
    quadro.pack(fill="both", expand=True)
    quadro.columnconfigure(1, weight=1)

    var_pasta = tk.StringVar(value=cfg.pasta_base)
    var_testador = tk.StringVar(value=cfg.testador)
    atuais = {chave: getattr(cfg, chave) for chave in NOMES_ATALHOS}
    var_atalhos = {chave: tk.StringVar(value=atalhos.formatar(valor)) for chave, valor in atuais.items()}

    ttk.Label(quadro, text="Pasta das evidências").grid(row=0, column=0, sticky="w", pady=4)
    ttk.Entry(quadro, textvariable=var_pasta, width=42).grid(row=0, column=1, sticky="ew", padx=8)

    def procurar() -> None:
        escolhida = filedialog.askdirectory(parent=janela, initialdir=var_pasta.get() or None,
                                            title="Pasta onde os testes serão salvos")
        if escolhida:
            var_pasta.set(escolhida.replace("/", "\\"))

    ttk.Button(quadro, text="Procurar…", command=procurar).grid(row=0, column=2)

    ttk.Label(quadro, text="Testador (opcional)").grid(row=1, column=0, sticky="w", pady=4)
    ttk.Entry(quadro, textvariable=var_testador).grid(row=1, column=1, columnspan=2, sticky="ew", padx=8)
    ttk.Label(quadro, text="Aparece na capa do PDF.", foreground="#666").grid(
        row=2, column=1, columnspan=2, sticky="w", padx=8)

    moldura = ttk.LabelFrame(quadro, text="Atalhos globais", padding=10)
    moldura.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(14, 8))
    moldura.columnconfigure(1, weight=1)

    def alterar(chave: str) -> None:
        novo = pedir_atalho(janela, NOMES_ATALHOS[chave])
        if novo:
            atuais[chave] = novo
            var_atalhos[chave].set(atalhos.formatar(novo))

    for linha, (chave, nome) in enumerate(NOMES_ATALHOS.items()):
        ttk.Label(moldura, text=nome).grid(row=linha, column=0, sticky="w", pady=3)
        ttk.Label(moldura, textvariable=var_atalhos[chave], font=("Segoe UI", 10, "bold")).grid(
            row=linha, column=1, sticky="w", padx=12)
        ttk.Button(moldura, text="Alterar…", command=lambda c=chave: alterar(c)).grid(row=linha, column=2)

    resultado: list[Config] = []

    def salvar() -> None:
        if len(set(atuais.values())) != len(atuais):
            messagebox.showwarning("Atalhos repetidos", "Cada ação precisa de um atalho diferente.",
                                   parent=janela)
            return
        pasta = var_pasta.get().strip()
        if not pasta:
            messagebox.showwarning("Pasta", "Informe a pasta das evidências.", parent=janela)
            return
        resultado.append(replace(cfg, pasta_base=pasta, testador=var_testador.get().strip(), **atuais))
        janela.destroy()

    botoes = ttk.Frame(quadro)
    botoes.grid(row=4, column=0, columnspan=3, sticky="e", pady=(8, 0))
    ttk.Button(botoes, text="Salvar", command=salvar).pack(side="left", padx=4)
    ttk.Button(botoes, text="Cancelar", command=janela.destroy).pack(side="left")

    janela.update_idletasks()
    janela.grab_set()
    pai.wait_window(janela)
    return resultado[0] if resultado else None
