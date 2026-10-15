"""Janela "Preparar prompt para IA": monta o texto, mostra a prévia e copia para a área de transferência."""
from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import metadados
from .prompt_ia import SAIDAS, Formulario, montar_prompt

ARQUIVO_PROMPT = "Prompt para IA.txt"
AVISO = ("Antes de anexar, confira se as evidências não têm dados pessoais ou sensíveis e se a "
         "ferramenta de IA que o senhor vai usar é aprovada pela empresa.")


def _campo_texto(pai: tk.Misc, linhas: int) -> tk.Text:
    texto = tk.Text(pai, height=linhas, wrap="word", font=("Segoe UI", 9), undo=True,
                    relief="solid", borderwidth=1)
    texto.bind("<Tab>", lambda _e: (texto.tk_focusNext().focus_set(), "break")[1])
    return texto


def abrir_dialogo_prompt(pai: tk.Misc, pasta: Path, pasta_base: str) -> Path:
    """Abre a janela para o teste em `pasta`. Devolve a pasta que ficou selecionada.

    Levanta ValueError (antes de abrir a janela) se a pasta não for de um teste.
    """
    estado = {"teste": metadados.ler(pasta), "agendado": None}

    janela = tk.Toplevel(pai)
    janela.title("Preparar prompt para IA")
    janela.geometry("780x760")
    janela.minsize(700, 620)
    janela.transient(pai)

    quadro = ttk.Frame(janela, padding=14)
    quadro.pack(fill="both", expand=True)
    quadro.columnconfigure(1, weight=1)

    var_titulo = tk.StringVar()
    var_ambiente = tk.StringVar()
    var_saida = tk.StringVar(value="ambos")
    var_pdf = tk.BooleanVar(value=True)
    var_status = tk.StringVar()

    # --- teste escolhido
    ttk.Label(quadro, text="Teste").grid(row=0, column=0, sticky="w")
    ttk.Label(quadro, textvariable=var_titulo, font=("Segoe UI", 10, "bold")).grid(
        row=0, column=1, sticky="w", padx=8)
    botao_trocar = ttk.Button(quadro, text="Trocar…")
    botao_trocar.grid(row=0, column=2)

    # --- formulário
    ttk.Label(quadro, text="Sistema / ambiente").grid(row=1, column=0, sticky="w", pady=(10, 0))
    ttk.Entry(quadro, textvariable=var_ambiente).grid(row=1, column=1, columnspan=2, sticky="ew",
                                                      padx=8, pady=(10, 0))

    campos = {}
    for linha, (chave, rotulo, altura) in enumerate((
            ("objetivo", "Objetivo do teste", 3),
            ("criterios", "Critérios de aceite /\nresultado esperado", 3),
            ("observacoes", "Observações", 2)), start=2):
        ttk.Label(quadro, text=rotulo).grid(row=linha, column=0, sticky="nw", pady=(8, 0))
        campos[chave] = _campo_texto(quadro, altura)
        campos[chave].grid(row=linha, column=1, columnspan=2, sticky="ew", padx=8, pady=(8, 0))

    ttk.Label(quadro, text="O que a IA deve gerar").grid(row=5, column=0, sticky="w", pady=(10, 0))
    opcoes = ttk.Frame(quadro)
    opcoes.grid(row=5, column=1, columnspan=2, sticky="w", padx=8, pady=(10, 0))
    for chave, rotulo in SAIDAS.items():
        ttk.Radiobutton(opcoes, text=rotulo, value=chave, variable=var_saida).pack(side="left", padx=(0, 14))
    ttk.Checkbutton(opcoes, text="Pedir a entrega em PDF", variable=var_pdf).pack(side="left", padx=(10, 0))

    # --- prévia
    ttk.Label(quadro, text="Prévia do prompt (é isto que será copiado)").grid(
        row=6, column=0, columnspan=3, sticky="w", pady=(14, 2))
    moldura = ttk.Frame(quadro)
    moldura.grid(row=7, column=0, columnspan=3, sticky="nsew")
    quadro.rowconfigure(7, weight=1)
    previa = tk.Text(moldura, height=10, wrap="word", font=("Consolas", 9), state="disabled",
                     background="#f5f5f5", relief="solid", borderwidth=1)
    barra = ttk.Scrollbar(moldura, orient="vertical", command=previa.yview)
    previa.configure(yscrollcommand=barra.set)
    previa.pack(side="left", fill="both", expand=True)
    barra.pack(side="right", fill="y")

    ttk.Label(quadro, text=AVISO, foreground="#8a4b00", wraplength=700, justify="left").grid(
        row=8, column=0, columnspan=3, sticky="w", pady=(10, 0))

    # --- botões
    rodape = ttk.Frame(quadro)
    rodape.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(10, 0))
    botao_copiar = ttk.Button(rodape, text="Copiar prompt")
    botao_copiar.pack(side="left", ipady=4, ipadx=8)
    botao_pasta = ttk.Button(rodape, text="Abrir pasta do teste")
    botao_pasta.pack(side="left", padx=8)
    ttk.Button(rodape, text="Fechar", command=janela.destroy).pack(side="right")
    ttk.Label(quadro, textvariable=var_status, foreground="#1b5e20", wraplength=700,
              justify="left").grid(row=10, column=0, columnspan=3, sticky="w", pady=(8, 0))

    # --- lógica
    def formulario() -> Formulario:
        return Formulario(
            ambiente=var_ambiente.get(),
            objetivo=campos["objetivo"].get("1.0", "end"),
            criterios=campos["criterios"].get("1.0", "end"),
            observacoes=campos["observacoes"].get("1.0", "end"),
            saida=var_saida.get(),
            entregar_pdf=var_pdf.get(),
        )

    def prompt_atual() -> str:
        return montar_prompt(estado["teste"], formulario())

    def atualizar_previa(*_args) -> None:
        estado["agendado"] = None
        try:
            previa.configure(state="normal")
            previa.delete("1.0", "end")
            previa.insert("1.0", prompt_atual())
            previa.configure(state="disabled")
        except tk.TclError:
            return  # janela fechada enquanto a atualização estava agendada
        teste = estado["teste"]
        var_titulo.set(f"{teste.nome_teste}  ({len(teste.evidencias)} evidências)")

    def agendar(*_args) -> None:
        if estado["agendado"]:
            janela.after_cancel(estado["agendado"])
        estado["agendado"] = janela.after(250, atualizar_previa)

    def copiar() -> None:
        texto = prompt_atual()
        janela.clipboard_clear()
        janela.clipboard_append(texto)
        janela.update()
        destino = estado["teste"].pasta / ARQUIVO_PROMPT
        try:
            destino.write_text(texto, encoding="utf-8-sig")  # BOM: o Bloco de Notas acerta os acentos
            salvo = f' Também salvo na pasta do teste como "{ARQUIVO_PROMPT}".'
        except OSError:
            salvo = ""
        anexo = estado["teste"].pdf or "as imagens das evidências"
        var_status.set(f"Prompt copiado! Cole na IA e anexe: {anexo}.{salvo}")

    def trocar() -> None:
        escolhida = filedialog.askdirectory(parent=janela, initialdir=pasta_base or None,
                                            title="Escolha a pasta do teste")
        if not escolhida:
            return
        try:
            estado["teste"] = metadados.ler(escolhida)
        except ValueError as exc:
            messagebox.showwarning("Pasta inválida", str(exc), parent=janela)
            return
        var_status.set("")
        atualizar_previa()

    botao_trocar.configure(command=trocar)
    botao_copiar.configure(command=copiar)
    botao_pasta.configure(command=lambda: os.startfile(estado["teste"].pasta))
    var_ambiente.trace_add("write", agendar)
    var_saida.trace_add("write", agendar)
    var_pdf.trace_add("write", agendar)
    for campo in campos.values():
        campo.bind("<KeyRelease>", agendar)

    atualizar_previa()
    janela.update_idletasks()
    janela.focus_force()
    pai.wait_window(janela)
    return estado["teste"].pasta
