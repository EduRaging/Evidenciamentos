"""Janela "Preparar prompt para IA": monta o texto, mostra a prévia, envia ao Claude ou copia."""
from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Sequence

from . import claude_desktop, extensao_claude, metadados
from .prompt_ia import MAX_TESTES, SAIDAS, Formulario, montar_prompt, montar_prompt_varios

ARQUIVO_PROMPT = "Prompt para IA.txt"
AVISO = ("Antes de enviar ou anexar, confira se as evidências não têm dados pessoais ou sensíveis e se a "
         "ferramenta de IA que o senhor vai usar é aprovada pela empresa.")


def _campo_texto(pai: tk.Misc, linhas: int) -> tk.Text:
    texto = tk.Text(pai, height=linhas, wrap="word", font=("Segoe UI", 9), undo=True,
                    relief="solid", borderwidth=1)
    texto.bind("<Tab>", lambda _e: (texto.tk_focusNext().focus_set(), "break")[1])
    return texto


def ler_testes(pastas: Sequence[Path | str]) -> tuple[list[metadados.PastaTeste], list[tuple[str, str]]]:
    """Lê os testes de `pastas` (sem repetir). Devolve (testes lidos, [(nome da pasta, motivo) ignorados])."""
    testes, ignorados, vistas = [], [], set()
    for pasta in pastas:
        chave = os.path.normcase(os.path.normpath(str(pasta)))
        if chave in vistas:
            continue
        vistas.add(chave)
        try:
            teste = metadados.ler(pasta)
        except ValueError as exc:
            ignorados.append((Path(pasta).name, str(exc)))
            continue
        if not teste.evidencias:  # só PDF/outros arquivos: não há imagens para o Claude analisar
            ignorados.append((Path(pasta).name, "sem imagens de evidência"))
            continue
        testes.append(teste)
    return testes, ignorados


def _resumo_dos_testes(testes: list[metadados.PastaTeste]) -> str:
    nomes = "; ".join(t.nome_teste for t in testes)
    if len(nomes) > 90:
        nomes = nomes[:87].rstrip() + "…"
    return f"{len(testes)} testes: {nomes}  ({sum(len(t.evidencias) for t in testes)} evidências)"


def abrir_dialogo_prompt(pai: tk.Misc, pasta: Path | Sequence[Path], pasta_base: str) -> Path:
    """Abre a janela para o teste em `pasta` (ou para VÁRIOS testes, se for uma lista).

    Devolve a pasta que ficou selecionada (a do primeiro, no modo de vários testes).
    Levanta ValueError (antes de abrir a janela) se uma pasta não for de um teste ou se forem testes demais.
    Com vários testes só existe o modo "Claude com a extensão": ele lê as pastas e salva um PDF por teste.
    """
    pastas = [Path(pasta)] if isinstance(pasta, (str, Path)) else [Path(p) for p in pasta]
    if not pastas:
        raise ValueError("Nenhum teste selecionado.")
    if len(pastas) > MAX_TESTES:
        raise ValueError(f"Selecione no máximo {MAX_TESTES} testes por vez (foram {len(pastas)}).")
    testes = [metadados.ler(p) for p in pastas]
    multiplo = len(testes) > 1
    estado = {"teste": testes[0], "testes": testes, "agendado": None}

    janela = tk.Toplevel(pai)
    janela.title("Preparar prompt para IA" + (f" — {len(testes)} testes" if multiplo else ""))
    janela.geometry("780x760")
    janela.minsize(700, 700)
    janela.transient(pai)

    quadro = ttk.Frame(janela, padding=14)
    quadro.pack(fill="both", expand=True)
    quadro.columnconfigure(1, weight=1)

    var_titulo = tk.StringVar()
    var_ambiente = tk.StringVar()
    var_saida = tk.StringVar(value="ambos")
    var_pdf = tk.BooleanVar(value=True)
    var_sugerir = tk.BooleanVar(value=True)
    var_extensao = tk.BooleanVar(value=True)
    var_aviso_extensao = tk.StringVar()
    var_status = tk.StringVar()

    # --- teste escolhido
    ttk.Label(quadro, text="Testes" if multiplo else "Teste").grid(row=0, column=0, sticky="nw")
    ttk.Label(quadro, textvariable=var_titulo, font=("Segoe UI", 10, "bold"), wraplength=470,
              justify="left").grid(row=0, column=1, sticky="w", padx=8)
    botao_trocar = ttk.Button(quadro, text="Trocar…", state="disabled" if multiplo else "normal")
    botao_trocar.grid(row=0, column=2, sticky="n")

    # --- formulário
    de_todos = "\n(de todos os testes)" if multiplo else ""
    ttk.Label(quadro, text="Sistema / ambiente" + de_todos).grid(row=1, column=0, sticky="w", pady=(10, 0))
    ttk.Entry(quadro, textvariable=var_ambiente).grid(row=1, column=1, columnspan=2, sticky="ew",
                                                      padx=8, pady=(10, 0))

    campos = {}
    for linha, (chave, rotulo, altura) in enumerate((
            ("objetivo", "Objetivo do teste" + de_todos, 3),
            ("criterios", "Critérios de aceite /\nresultado esperado" + de_todos, 3),
            ("observacoes", "Observações" + de_todos, 2)), start=2):
        ttk.Label(quadro, text=rotulo).grid(row=linha, column=0, sticky="nw", pady=(8, 0))
        campos[chave] = _campo_texto(quadro, altura)
        campos[chave].grid(row=linha, column=1, columnspan=2, sticky="ew", padx=8, pady=(8, 0))

    ttk.Label(quadro, text="O que a IA deve gerar").grid(row=5, column=0, sticky="nw", pady=(10, 0))
    opcoes = ttk.Frame(quadro)
    opcoes.grid(row=5, column=1, columnspan=2, sticky="w", padx=8, pady=(10, 0))
    linha_saida = ttk.Frame(opcoes)
    linha_saida.pack(anchor="w")
    for chave, rotulo in SAIDAS.items():
        ttk.Radiobutton(linha_saida, text=rotulo, value=chave, variable=var_saida).pack(
            side="left", padx=(0, 14))
    ttk.Checkbutton(linha_saida, text="Pedir a entrega em PDF", variable=var_pdf).pack(
        side="left", padx=(10, 0))
    ttk.Checkbutton(opcoes, text="Sugerir casos de teste adicionais (técnicas ISTQB/BSTQB)",
                    variable=var_sugerir).pack(anchor="w", pady=(4, 0))
    chk_extensao = ttk.Checkbutton(
        opcoes, variable=var_extensao, text="Claude com a extensão instalada (ele lê as evidências direto da pasta)"
        + (" — necessário com vários testes" if multiplo else ""))
    chk_extensao.pack(anchor="w", pady=(4, 0))
    if multiplo:
        var_extensao.set(True)
        chk_extensao.state(["disabled"])  # com anexos não dá para misturar testes: só a extensão lê as pastas

    # --- prévia
    ttk.Label(quadro, text="Prévia do prompt (é isto que será enviado ou copiado)").grid(
        row=6, column=0, columnspan=3, sticky="w", pady=(14, 2))
    moldura = ttk.Frame(quadro)
    moldura.grid(row=7, column=0, columnspan=3, sticky="nsew")
    quadro.rowconfigure(7, weight=1)
    previa = tk.Text(moldura, height=5, wrap="word", font=("Consolas", 9), state="disabled",
                     background="#f5f5f5", relief="solid", borderwidth=1)
    barra = ttk.Scrollbar(moldura, orient="vertical", command=previa.yview)
    previa.configure(yscrollcommand=barra.set)
    previa.pack(side="left", fill="both", expand=True)
    barra.pack(side="right", fill="y")

    ttk.Label(quadro, textvariable=var_aviso_extensao, foreground="#b00020", wraplength=700,
              justify="left").grid(row=8, column=0, columnspan=3, sticky="w", pady=(8, 0))
    ttk.Label(quadro, text=AVISO, foreground="#8a4b00", wraplength=700, justify="left").grid(
        row=9, column=0, columnspan=3, sticky="w", pady=(8, 0))

    # --- botões
    rodape = ttk.Frame(quadro)
    rodape.grid(row=10, column=0, columnspan=3, sticky="ew", pady=(10, 0))
    botao_enviar = ttk.Button(rodape, text="Enviar ao Claude")
    botao_enviar.pack(side="left", ipady=4, ipadx=8)
    botao_copiar = ttk.Button(rodape, text="Copiar prompt")
    botao_copiar.pack(side="left", padx=8)
    botao_pasta = ttk.Button(rodape, text="Abrir pasta dos testes" if multiplo else "Abrir pasta do teste")
    botao_pasta.pack(side="left")
    ttk.Button(rodape, text="Fechar", command=janela.destroy).pack(side="right")
    ttk.Label(quadro, textvariable=var_status, foreground="#1b5e20", wraplength=700,
              justify="left").grid(row=11, column=0, columnspan=3, sticky="w", pady=(8, 0))

    # --- lógica
    def formulario() -> Formulario:
        return Formulario(
            ambiente=var_ambiente.get(),
            objetivo=campos["objetivo"].get("1.0", "end"),
            criterios=campos["criterios"].get("1.0", "end"),
            observacoes=campos["observacoes"].get("1.0", "end"),
            saida=var_saida.get(),
            entregar_pdf=var_pdf.get(),
            sugerir_casos=var_sugerir.get(),
            via_mcp=var_extensao.get(),
        )

    def prompt_atual() -> str:
        if multiplo:
            return montar_prompt_varios(estado["testes"], formulario())
        return montar_prompt(estado["teste"], formulario())

    def problemas_da_extensao() -> list[str]:
        """O que impediria o Claude de ler o(s) teste(s) pela extensão (vazio se a caixa está desmarcada)."""
        if not var_extensao.get():
            return []
        achados: list[str] = []
        for teste in estado["testes"]:
            achados.extend(extensao_claude.avisos(teste.pasta))
        return list(dict.fromkeys(achados))  # o mesmo aviso não se repete para cada teste

    def atualizar_aviso_extensao(*_args) -> None:
        var_aviso_extensao.set("\n".join(f"⚠ {p}" for p in problemas_da_extensao()))

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
        var_titulo.set(_resumo_dos_testes(estado["testes"]) if multiplo
                       else f"{teste.nome_teste}  ({len(teste.evidencias)} evidências)")

    def agendar(*_args) -> None:
        if estado["agendado"]:
            janela.after_cancel(estado["agendado"])
        estado["agendado"] = janela.after(250, atualizar_previa)

    def guardar_copia(texto: str) -> str:
        """Põe o texto na área de transferência e salva um .txt na pasta do teste; devolve o aviso."""
        janela.clipboard_clear()
        janela.clipboard_append(texto)
        janela.update()
        if multiplo:
            return ""  # o texto vale para vários testes: não há uma pasta só onde guardá-lo
        destino = estado["teste"].pasta / ARQUIVO_PROMPT
        try:
            destino.write_text(texto, encoding="utf-8-sig")  # BOM: o Bloco de Notas acerta os acentos
            return f' Também salvo na pasta do teste como "{ARQUIVO_PROMPT}".'
        except OSError:
            return ""

    def a_anexar() -> str:
        """O que falta anexar à mão: nada, se o Claude lê as evidências pela extensão."""
        if var_extensao.get():
            return ""
        return f" Anexe: {estado['teste'].pdf or 'as imagens das evidências'}."

    def copiar() -> None:
        salvo = guardar_copia(prompt_atual())
        var_status.set(f"Prompt copiado! Cole na IA.{a_anexar()}{salvo}")

    def enviar() -> None:
        problemas = problemas_da_extensao()
        atualizar_aviso_extensao()
        if problemas and not messagebox.askyesno(
                "A extensão não está pronta",
                "\n\n".join(problemas) + "\n\nEnviar ao Claude mesmo assim? (Ele provavelmente dirá que não "
                "consegue ler as evidências.)", icon="warning", default="no", parent=janela):
            return
        texto = prompt_atual()
        var_status.set("Abrindo o Claude…")
        janela.update_idletasks()
        resultado = claude_desktop.abrir_conversa(texto)
        if resultado == claude_desktop.PREENCHIDO:
            pedidos = (f" Ele pode pedir permissão para gravar cada um dos {len(estado['testes'])} PDFs."
                       if multiplo and var_pdf.get() else "")
            var_status.set("O Claude abriu com o prompt preenchido. Confira e aperte Enter para enviar: "
                           f"nada sai do computador antes disso.{a_anexar()}{pedidos}")
            return
        salvo = guardar_copia(texto)  # o link não deu certo: o prompt segue pela área de transferência
        if resultado == claude_desktop.VAZIA:
            var_status.set("O prompt é grande demais para ir no link. O Claude abriu em branco e o prompt "
                           f"está copiado: cole com Ctrl+V.{a_anexar()}{salvo}")
        else:
            var_status.set("Não consegui abrir o Claude desktop (não está instalado ou não iniciou). O prompt "
                           f"foi copiado: abra o Claude e cole com Ctrl+V.{a_anexar()}{salvo}")

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
        atualizar_aviso_extensao()

    botao_trocar.configure(command=trocar)
    botao_enviar.configure(command=enviar)
    botao_copiar.configure(command=copiar)
    botao_pasta.configure(command=lambda: os.startfile(
        estado["teste"].pasta.parent if multiplo else estado["teste"].pasta))
    var_ambiente.trace_add("write", agendar)
    var_saida.trace_add("write", agendar)
    var_pdf.trace_add("write", agendar)
    var_sugerir.trace_add("write", agendar)
    var_extensao.trace_add("write", agendar)
    var_extensao.trace_add("write", atualizar_aviso_extensao)
    for campo in campos.values():
        campo.bind("<KeyRelease>", agendar)

    atualizar_previa()
    atualizar_aviso_extensao()
    janela.update_idletasks()
    janela.focus_force()
    pai.wait_window(janela)
    return estado["teste"].pasta
