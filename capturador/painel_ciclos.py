"""Aba "Ciclos": as rodadas de teste, com o roteiro que o Claude montou a partir das telas."""
from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable

from . import ciclos, estilo, fluxo_ciclo, winutil
from .ciclos import Ciclo

INTERVALO_ATUALIZACAO_MS = 6000  # o roteiro que o Claude grava aparece sozinho


def _assinatura_dos_roteiros(ciclo: Ciclo) -> tuple:
    """Nome, data e tamanho dos roteiros do ciclo: se não mudou, não precisa ler os JSONs de novo."""
    itens = []
    try:
        with os.scandir(ciclo.pasta) as it:
            for e in it:
                if e.name.lower().startswith("roteiro-") and e.name.lower().endswith(".json"):
                    info = e.stat()
                    itens.append((e.name, info.st_mtime_ns, info.st_size))
    except OSError:
        pass
    return tuple(sorted(itens))


class PainelCiclos(ttk.Frame):
    def __init__(self, pai: tk.Misc, obter_base: Callable[[], str], ao_novo: Callable[[], None],
                 ao_gerar: Callable[[Ciclo], None], ao_ver: Callable[[Ciclo], None],
                 ao_salvar_pdf: Callable[[Ciclo], None], ao_gerar_manual: Callable[[Ciclo], None] | None = None,
                 ao_cancelar: Callable[[Ciclo], None] | None = None,
                 ao_revogar: Callable[[], None] | None = None) -> None:
        super().__init__(pai, padding=(18, 16, 18, 12))
        self._obter_base = obter_base
        self._ao_novo, self._ao_gerar, self._ao_ver, self._ao_salvar_pdf = ao_novo, ao_gerar, ao_ver, ao_salvar_pdf
        self._ao_gerar_manual, self._ao_cancelar, self._ao_revogar = ao_gerar_manual, ao_cancelar, ao_revogar
        self._gerando: set[Path] = set()  # ciclos cujo roteiro o Claude está montando agora
        self._ciclos: list[Ciclo] = []
        self._por_iid: dict[str, Ciclo] = {}
        self._situacao: dict[Path, tuple[tuple, int]] = {}  # pasta -> (assinatura dos roteiros, nº de casos)
        self._assinatura: tuple | None = None
        self._montar()
        self.after(150, self.atualizar)
        self.after(INTERVALO_ATUALIZACAO_MS, self._tique)

    def _montar(self) -> None:
        rodape = ttk.Frame(self)
        rodape.pack(fill="x", side="bottom", pady=(10, 0))
        self.botao_principal = estilo.botao_primario(rodape, "Ver roteiro", self._acao_principal)
        self.botao_principal.pack(side="left")
        ttk.Button(rodape, text="+ Novo ciclo", command=self._ao_novo).pack(side="left", padx=(10, 0))
        self.botao_mais = ttk.Button(rodape, text="Mais ▾", command=self._abrir_menu_mais)
        self.botao_mais.pack(side="right")
        self.var_status = tk.StringVar()
        ttk.Label(self, textvariable=self.var_status, style="Suave.TLabel", wraplength=480, justify="left").pack(
            anchor="w", side="bottom", pady=(8, 0))
        ttk.Label(self, text="Um ciclo é uma rodada de testes. Escolha as telas capturadas e o Claude monta o roteiro.",
                  style="Suave.TLabel", wraplength=490, justify="left").pack(anchor="w", side="bottom", pady=(6, 0))

        corpo = ttk.Frame(self)
        corpo.pack(fill="both", expand=True)
        self._moldura = ttk.Frame(corpo)
        self.arvore = ttk.Treeview(self._moldura, columns=("data", "ciclo", "tipo", "situacao"), show="headings",
                                   selectmode="browse", style="Tabela.Treeview")
        for coluna, titulo, largura, ancora, estica in (
                ("data", "Data", 58, "w", False), ("ciclo", "Ciclo", 200, "w", True),
                ("tipo", "Tipo", 100, "w", False), ("situacao", "Roteiro", 110, "w", False)):
            self.arvore.heading(coluna, text=titulo)
            self.arvore.column(coluna, width=largura, anchor=ancora, stretch=estica)
        barra = ttk.Scrollbar(self._moldura, orient="vertical", command=self.arvore.yview)
        self.arvore.configure(yscrollcommand=barra.set)
        self.arvore.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self._vazio = ttk.Label(corpo, style="Suave.TLabel", justify="center", anchor="center", relief="groove",
                                padding=20, wraplength=400,
                                text="Nenhum ciclo ainda.\n\nCrie um com “+ Novo ciclo”, ou ao finalizar um teste.")
        self.arvore.bind("<<TreeviewSelect>>", lambda _e: self._atualizar_botoes())
        self.arvore.bind("<Double-1>", lambda _e: self._acao_principal())
        self.arvore.bind("<Return>", lambda _e: self._acao_principal())
        self._atualizar_botoes()

    # --- dados --------------------------------------------------------
    def atualizar(self) -> None:
        self._ciclos = ciclos.listar_ciclos(self._obter_base())
        vivos = {c.pasta for c in self._ciclos}
        self._situacao = {p: v for p, v in self._situacao.items() if p in vivos}
        self._mostrar()

    def _tique(self) -> None:
        self.after(INTERVALO_ATUALIZACAO_MS, self._tique)
        if self.winfo_ismapped():
            self.atualizar()

    def marcar_gerando(self, pasta: Path, ativo: bool) -> None:
        """Mostra (ou tira) "gerando…" no ciclo cujo roteiro o Claude está montando."""
        (self._gerando.add if ativo else self._gerando.discard)(pasta)
        self._assinatura = None
        self._mostrar()

    def _casos(self, ciclo: Ciclo) -> int:
        assinatura = _assinatura_dos_roteiros(ciclo)
        guardado = self._situacao.get(ciclo.pasta)
        if guardado and guardado[0] == assinatura:
            return guardado[1]
        _, n = fluxo_ciclo.situacao(ciclo)
        self._situacao[ciclo.pasta] = (assinatura, n)
        return n

    def _mostrar(self) -> None:
        linhas = [(c, self._casos(c)) for c in self._ciclos]
        assinatura = (tuple((c.pasta, n) for c, n in linhas), frozenset(self._gerando))
        if assinatura == self._assinatura:
            return
        self._assinatura = assinatura
        anterior = self._selecionado()
        self.arvore.delete(*self.arvore.get_children())
        self._por_iid = {}
        for i, (c, n) in enumerate(linhas):
            iid = str(i)
            self._por_iid[iid] = c
            data = c.criado_em[8:10] + "/" + c.criado_em[5:7] if len(c.criado_em) >= 10 else ""
            self.arvore.insert("", "end", iid=iid, values=(data, c.nome, c.tipo, "gerando…" if c.pasta in self._gerando else (f"{n} casos" if n else "aguardando")))
            if anterior and c.pasta == anterior.pasta:
                self.arvore.selection_set(iid)
        if linhas:
            self._vazio.pack_forget()
            self._moldura.pack(fill="both", expand=True)
        else:
            self._moldura.pack_forget()
            self._vazio.pack(fill="both", expand=True)
        total = len(linhas)
        self.var_status.set(f"{total} {'ciclo' if total == 1 else 'ciclos'}" if total else "")
        self._atualizar_botoes()

    def _selecionado(self) -> Ciclo | None:
        marcado = self.arvore.selection()
        return self._por_iid.get(marcado[0]) if marcado else None

    def _tem_roteiro(self, ciclo: Ciclo) -> bool:
        return self._casos(ciclo) > 0

    def _atualizar_botoes(self) -> None:
        ciclo = self._selecionado()
        if ciclo is None:
            self.botao_principal.configure(text="Ver roteiro")
            estilo.ativar(self.botao_principal, False)
        elif ciclo.pasta in self._gerando:
            self.botao_principal.configure(text="Gerando o roteiro…")
            estilo.ativar(self.botao_principal, False)
        elif self._tem_roteiro(ciclo):
            self.botao_principal.configure(text="Ver roteiro")
            estilo.ativar(self.botao_principal, True)
        else:
            self.botao_principal.configure(text="Gerar roteiro com o Claude")
            estilo.ativar(self.botao_principal, True)
        self.botao_mais.state(["!disabled"] if ciclo else ["disabled"])

    # --- ações --------------------------------------------------------
    def _acao_principal(self) -> None:
        ciclo = self._selecionado()
        if ciclo is None:
            return
        (self._ao_ver if self._tem_roteiro(ciclo) else self._ao_gerar)(ciclo)

    def _abrir_menu_mais(self) -> None:
        ciclo = self._selecionado()
        if ciclo is None:
            return
        gerando = ciclo.pasta in self._gerando
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Gerar o roteiro de novo (automático)", command=lambda: self._ao_gerar(ciclo),
                         state="disabled" if gerando else "normal")
        if self._ao_gerar_manual is not None:
            menu.add_command(label="Pedir o roteiro no Claude desktop (manual)", command=lambda: self._ao_gerar_manual(ciclo),
                             state="disabled" if gerando else "normal")
        if self._ao_cancelar is not None:
            menu.add_command(label="Cancelar a geração do roteiro", command=lambda: self._ao_cancelar(ciclo),
                             state="normal" if gerando else "disabled")
        menu.add_separator()
        menu.add_command(label="Salvar o roteiro em PDF", command=lambda: self._ao_salvar_pdf(ciclo),
                         state="normal" if self._tem_roteiro(ciclo) else "disabled")
        menu.add_command(label="Mostrar a pasta do ciclo", command=lambda: winutil.revelar_no_explorador(ciclo.pasta))
        if self._ao_revogar is not None:
            menu.add_separator()
            menu.add_command(label="Revogar a autorização de enviar telas ao Claude", command=self._ao_revogar)
        menu.tk_popup(self.botao_mais.winfo_rootx(), self.botao_mais.winfo_rooty() + self.botao_mais.winfo_height())

    def selecionar(self, pasta: Path) -> None:
        """Marca o ciclo da pasta (por exemplo, o que acabou de ser criado)."""
        self._assinatura = None
        self.atualizar()
        for iid, c in self._por_iid.items():
            if c.pasta == pasta:
                self.arvore.selection_set(iid)
                self.arvore.see(iid)
                break
