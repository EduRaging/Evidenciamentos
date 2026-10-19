"""Janela "Novo ciclo de testes": o usuário só escolhe as telas; o resto é opcional e a IA completa."""
from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Sequence

from . import ciclos, estilo, fluxo_ciclo, registro_pdfs
from .ciclos import Ciclo


def _linhas(campo: tk.Text) -> list[str]:
    return [linha.strip() for linha in campo.get("1.0", "end").splitlines() if linha.strip()]


def _campo(pai: tk.Misc, linhas: int) -> tk.Text:
    texto = tk.Text(pai, height=linhas, width=30, wrap="word", font=(estilo.FAMILIA, 10), undo=True, relief="solid",
                    borderwidth=1)
    texto.bind("<Tab>", lambda _e: (texto.tk_focusNext().focus_set(), "break")[1])
    return texto


def abrir_ajustes(pai: tk.Misc, atuais: dict, testador: str = "") -> dict | None:
    """Janela dos parâmetros opcionais do ciclo. Devolve o que o usuário preencheu (só o que preencheu) ou None.

    Tudo é opcional: o que ficar em branco a IA propõe a partir das telas.
    """
    resultado: dict = {"valor": None}
    janela = tk.Toplevel(pai)
    janela.title("Parâmetros do ciclo")
    janela.transient(pai)
    janela.grab_set()
    quadro = ttk.Frame(janela, padding=(20, 18, 20, 16))
    quadro.pack(fill="both", expand=True)
    ttk.Label(quadro, text="Parâmetros do ciclo", style="Titulo.TLabel").pack(anchor="w")
    ttk.Label(quadro, text="Tudo é opcional: o que ficar em branco o Claude propõe a partir das telas.",
              style="Suave.TLabel").pack(anchor="w", pady=(2, 10))

    grade = ttk.Frame(quadro)
    grade.pack(fill="x")
    grade.columnconfigure((1, 3), weight=1)
    var = {k: tk.StringVar(value=str(atuais.get(k, ""))) for k in
           ("sistema", "versao_sistema", "ambiente", "testador", "inicio", "fim", "observacoes")}
    if not var["testador"].get():
        var["testador"].set(testador)
    var_tipo = tk.StringVar(value=atuais.get("tipo") or ciclos.TIPOS_DE_RODADA[0])
    combo = ttk.Combobox(grade, textvariable=var_tipo, values=ciclos.TIPOS_DE_RODADA, state="readonly", width=20)
    pares = [("Tipo de rodada", combo, "Sistema", ttk.Entry(grade, textvariable=var["sistema"], width=20)),
             ("Versão", ttk.Entry(grade, textvariable=var["versao_sistema"], width=20), "Ambiente",
              ttk.Entry(grade, textvariable=var["ambiente"], width=20)),
             ("Testador", ttk.Entry(grade, textvariable=var["testador"], width=20), "Início (AAAA-MM-DD)",
              ttk.Entry(grade, textvariable=var["inicio"], width=20)),
             ("Fim (AAAA-MM-DD)", ttk.Entry(grade, textvariable=var["fim"], width=20), "", None)]
    for i, (rotulo1, widget1, rotulo2, widget2) in enumerate(pares):
        ttk.Label(grade, text=rotulo1).grid(row=i, column=0, sticky="w", pady=3)
        widget1.grid(row=i, column=1, sticky="ew", padx=(8, 14), pady=3)
        if widget2 is not None:
            ttk.Label(grade, text=rotulo2).grid(row=i, column=2, sticky="w", pady=3)
            widget2.grid(row=i, column=3, sticky="ew", padx=(8, 0), pady=3)

    blocos = ttk.Frame(quadro)
    blocos.pack(fill="x", pady=(6, 0))
    blocos.columnconfigure((0, 1), weight=1)
    objetivo, escopo = _campo(blocos, 2), _campo(blocos, 2)
    entrada, saida = _campo(blocos, 3), _campo(blocos, 3)
    objetivo.insert("1.0", atuais.get("objetivo", ""))
    escopo.insert("1.0", "\n".join(atuais.get("escopo", []) or []))
    entrada.insert("1.0", "\n".join(atuais.get("criterios_entrada", []) or []))
    saida.insert("1.0", "\n".join(atuais.get("criterios_saida", []) or []))
    # (rótulo, campo, linha do rótulo, coluna, colunas ocupadas): objetivo e escopo ocupam a largura toda; os
    # critérios de entrada e de saída ficam lado a lado, para a janela não passar da altura de uma tela
    for rotulo, campo, linha, coluna, abrange in (
            ("Objetivo", objetivo, 0, 0, 2), ("Escopo (um item por linha)", escopo, 2, 0, 2),
            ("Critérios de entrada (um por linha)", entrada, 4, 0, 1), ("Critérios de saída (um por linha)", saida, 4, 1, 1)):
        ttk.Label(blocos, text=rotulo, style="Suave.TLabel").grid(row=linha, column=coluna, columnspan=abrange,
                                                                  sticky="w", pady=(8, 0))
        campo.grid(row=linha + 1, column=coluna, columnspan=abrange, sticky="ew", padx=(0, 10) if abrange == 1 and coluna == 0 else 0)
    ttk.Label(blocos, text="Observações", style="Suave.TLabel").grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))
    ttk.Entry(blocos, textvariable=var["observacoes"]).grid(row=7, column=0, columnspan=2, sticky="ew")

    def aplicar() -> None:
        dados: dict = {"tipo": var_tipo.get(), **{k: v.get().strip() for k, v in var.items()},
                       "objetivo": " ".join(_linhas(objetivo)), "escopo": _linhas(escopo)}
        if _linhas(entrada):
            dados["criterios_entrada"] = _linhas(entrada)
        if _linhas(saida):
            dados["criterios_saida"] = _linhas(saida)
        try:  # valida já, para o erro aparecer aqui e não só na hora de criar
            ciclos.validar_parametros({**dados, "nome": "x", "testes_base": ["x"]})
        except ValueError as exc:
            messagebox.showwarning("Parâmetros inválidos", str(exc), parent=janela)
            return
        resultado["valor"] = {k: v for k, v in dados.items() if v not in ("", [], None)}
        janela.destroy()

    rodape = ttk.Frame(quadro)
    rodape.pack(fill="x", pady=(14, 0))
    estilo.botao_primario(rodape, "Aplicar", aplicar).pack(side="left")
    ttk.Button(rodape, text="Cancelar", command=janela.destroy).pack(side="right")
    janela.update_idletasks()
    janela.focus_force()
    pai.wait_window(janela)
    return resultado["valor"]


def abrir_dialogo_ciclo(pai: tk.Misc, base: Path | str, pre_selecionadas: Sequence[Path | str] = (),
                        testador: str = "") -> tuple[Ciclo, list[tuple[str, str]]] | None:
    """Abre a janela e devolve (ciclo criado, testes ignorados), ou None se o usuário cancelar.

    `pre_selecionadas` são as telas já escolhidas (por exemplo, o teste que acabou de ser finalizado).
    """
    testes = registro_pdfs.agrupar_por_teste(registro_pdfs.listar_pdfs(base))
    if not testes:
        messagebox.showinfo("Novo ciclo de testes", "Ainda não há testes finalizados para servir de referência. "
                            "Capture e finalize um teste primeiro.", parent=pai)
        return None
    marcadas = {os.path.normcase(os.path.normpath(str(p))) for p in pre_selecionadas}
    resultado: dict = {"valor": None, "nome_editado": False, "ajustes": {}}

    janela = tk.Toplevel(pai)
    janela.title("Novo ciclo de testes")
    janela.minsize(620, 1)
    janela.transient(pai)
    quadro = ttk.Frame(janela, padding=(20, 18, 20, 16))
    quadro.pack(fill="both", expand=True)

    ttk.Label(quadro, text="Novo ciclo de testes", style="Titulo.TLabel").pack(anchor="w")
    ttk.Label(quadro, text="O Claude monta o roteiro a partir das telas que o senhor capturou. Escolha as telas de "
                           "referência; o resto ele propõe.", style="Suave.TLabel", wraplength=560,
              justify="left").pack(anchor="w", pady=(4, 10))

    # --- telas de referência
    moldura = ttk.Frame(quadro)
    moldura.pack(fill="x")
    arvore = ttk.Treeview(moldura, columns=("data", "teste", "evidencias"), show="headings", selectmode="extended",
                          height=6, style="Tabela.Treeview")
    for coluna, titulo, largura, ancora, estica in (("data", "Data", 70, "w", False), ("teste", "Teste", 360, "w", True),
                                                    ("evidencias", "Telas", 60, "center", False)):
        arvore.heading(coluna, text=titulo)
        arvore.column(coluna, width=largura, anchor=ancora, stretch=estica)
    barra = ttk.Scrollbar(moldura, orient="vertical", command=arvore.yview)
    arvore.configure(yscrollcommand=barra.set)
    arvore.pack(side="left", fill="x", expand=True)
    barra.pack(side="right", fill="y")
    por_iid: dict[str, registro_pdfs.TesteRegistrado] = {}
    for i, t in enumerate(testes):
        iid = str(i)
        por_iid[iid] = t
        arvore.insert("", "end", iid=iid, values=(t.momento.strftime("%d/%m"), t.teste, "✓" if t.evidencias else "—"))
        if os.path.normcase(os.path.normpath(str(t.pasta))) in marcadas:
            arvore.selection_add(iid)
    var_contagem = tk.StringVar()
    ttk.Label(quadro, textvariable=var_contagem, style="Suave.TLabel").pack(anchor="w", pady=(4, 0))

    # --- nome (automático, editável)
    ttk.Label(quadro, text="Nome do ciclo", style="Suave.TLabel").pack(anchor="w", pady=(12, 0))
    var_nome = tk.StringVar()
    entrada_nome = ttk.Entry(quadro, textvariable=var_nome, font=(estilo.FAMILIA, 11))
    entrada_nome.pack(fill="x", ipady=3)
    entrada_nome.bind("<Key>", lambda _e: resultado.update(nome_editado=True))

    # --- os ajustes opcionais ficam numa janela à parte (esta precisa caber numa tela de 768 px)
    botao_ajustes = ttk.Button(quadro, style="Link.Toolbutton")
    botao_ajustes.pack(anchor="w", pady=(12, 0))

    def rotulo_dos_ajustes() -> None:
        botao_ajustes.configure(text="Parâmetros ajustados ✓ (editar…)" if resultado["ajustes"]
                                else "Ajustar parâmetros do ciclo (opcional)…")

    def ajustar() -> None:
        novos = abrir_ajustes(janela, resultado["ajustes"], testador)
        if novos is not None:
            resultado["ajustes"] = novos
            rotulo_dos_ajustes()

    botao_ajustes.configure(command=ajustar)
    rotulo_dos_ajustes()

    # --- ações
    rodape = ttk.Frame(quadro)
    rodape.pack(fill="x", pady=(16, 0))
    botao_criar = estilo.botao_primario(rodape, "Criar e gerar o roteiro", None)
    botao_criar.pack(side="left")
    ttk.Button(rodape, text="Cancelar", command=janela.destroy).pack(side="right")

    def selecionadas() -> list[registro_pdfs.TesteRegistrado]:
        return [por_iid[i] for i in arvore.selection() if i in por_iid]

    def ao_selecionar(*_args) -> None:
        escolhidas = selecionadas()
        n = len(escolhidas)
        var_contagem.set(f"{n} {'tela escolhida' if n == 1 else 'telas escolhidas'} (no máximo {ciclos.MAX_TESTES_BASE})"
                         if n else "Escolha ao menos um teste (Ctrl ou Shift escolhem vários).")
        estilo.ativar(botao_criar, 1 <= n <= ciclos.MAX_TESTES_BASE)
        if not resultado["nome_editado"]:
            var_nome.set(ciclos.nome_automatico([t.teste for t in escolhidas]) if escolhidas else "")

    def criar() -> None:
        parametros = {**resultado["ajustes"], "nome": var_nome.get()}
        try:
            resultado["valor"] = fluxo_ciclo.criar_a_partir_de_testes(base, [t.pasta for t in selecionadas()], parametros)
        except (ValueError, OSError) as exc:
            messagebox.showwarning("Não foi possível criar o ciclo", str(exc), parent=janela)
            return
        janela.destroy()

    botao_criar.configure(command=criar)
    arvore.bind("<<TreeviewSelect>>", ao_selecionar)
    ao_selecionar()
    janela.update_idletasks()
    janela.geometry("")
    janela.focus_force()
    pai.wait_window(janela)
    return resultado["valor"]
