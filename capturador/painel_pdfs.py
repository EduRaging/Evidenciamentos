"""Aba "PDFs gerados": registro dos PDFs (evidências e relatórios) com ações para abrir, encaminhar
e baixar."""
from __future__ import annotations

import os
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable
from urllib.parse import quote

from . import registro_pdfs, winutil
from .registro_pdfs import RegistroPdf

INTERVALO_ATUALIZACAO_MS = 6000  # relatórios gerados por fora (ex.: pela IA) aparecem sozinhos


class PainelPdfs(ttk.Frame):
    def __init__(self, pai: tk.Misc, obter_base: Callable[[], str],
                 ao_enviar_ao_claude: Callable[[list[Path]], None] | None = None) -> None:
        """`ao_enviar_ao_claude` recebe as pastas (sem repetir) dos testes cujos PDFs estão selecionados."""
        super().__init__(pai, padding=14)
        self._obter_base = obter_base
        self._ao_enviar_ao_claude = ao_enviar_ao_claude
        self._registros: list[RegistroPdf] = []
        self._por_iid: dict[str, RegistroPdf] = {}
        self._assinatura: tuple | None = None
        self._montar()
        self.after(150, self.atualizar)
        self.after(INTERVALO_ATUALIZACAO_MS, self._tique)

    # --- interface ----------------------------------------------------
    def _montar(self) -> None:
        topo = ttk.Frame(self)
        topo.pack(fill="x")
        ttk.Label(topo, text="Filtrar").pack(side="left")
        self.var_filtro = tk.StringVar()
        ttk.Entry(topo, textvariable=self.var_filtro).pack(side="left", fill="x", expand=True, padx=6)
        self.var_filtro.trace_add("write", lambda *_: self._mostrar())
        ttk.Button(topo, text="Atualizar", command=self.atualizar).pack(side="left")

        self.var_pasta = tk.StringVar()
        ttk.Label(self, textvariable=self.var_pasta, foreground="#666", wraplength=470,
                  justify="left").pack(anchor="w", pady=(6, 4))

        corpo = ttk.Frame(self)
        corpo.pack(fill="both", expand=True)
        self.arvore = ttk.Treeview(corpo, columns=("data", "teste", "tipo", "tamanho"), show="headings",
                                   selectmode="extended", height=10)  # Ctrl/Shift: vários PDFs para o Claude
        for coluna, titulo, largura, ancora in (("data", "Data", 112, "w"), ("teste", "Teste", 190, "w"),
                                                ("tipo", "Tipo", 78, "w"), ("tamanho", "Tamanho", 66, "e")):
            self.arvore.heading(coluna, text=titulo)
            self.arvore.column(coluna, width=largura, anchor=ancora)
        barra = ttk.Scrollbar(corpo, orient="vertical", command=self.arvore.yview)
        self.arvore.configure(yscrollcommand=barra.set)
        self.arvore.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self.arvore.bind("<<TreeviewSelect>>", lambda _e: self._atualizar_botoes())
        self.arvore.bind("<Double-1>", lambda _e: self.abrir())
        self.arvore.bind("<Return>", lambda _e: self.abrir())
        self.arvore.bind("<Button-3>", self._menu_de_contexto)

        acoes = ttk.Frame(self)
        acoes.pack(fill="x", pady=(8, 0))
        acoes.columnconfigure((0, 1, 2), weight=1, uniform="acao")
        self._acoes = [
            ("Abrir (ler)", self.abrir), ("Mostrar na pasta", self.mostrar_na_pasta),
            ("Copiar caminho", self.copiar_caminho), ("Copiar arquivo", self.copiar_arquivo),
            ("Salvar cópia…", self.salvar_copia), ("Enviar por e-mail…", self.enviar_por_email),
        ]
        self._botoes: list[ttk.Button] = []
        for i, (rotulo, comando) in enumerate(self._acoes):
            botao = ttk.Button(acoes, text=rotulo, command=comando)
            botao.grid(row=i // 3, column=i % 3, sticky="ew", padx=2, pady=2)
            self._botoes.append(botao)
        self.botao_claude = ttk.Button(acoes, command=self.enviar_ao_claude)
        self.botao_claude.grid(row=2, column=0, columnspan=3, sticky="ew", padx=2, pady=(6, 2), ipady=3)

        self.var_status = tk.StringVar()
        ttk.Label(self, textvariable=self.var_status, foreground="#1b5e20", wraplength=470,
                  justify="left").pack(anchor="w", pady=(8, 0))

        self.menu = tk.Menu(self, tearoff=False)
        for rotulo, comando in self._acoes:
            self.menu.add_command(label=rotulo, command=comando)
        self.menu.add_separator()
        self.menu.add_command(command=self.enviar_ao_claude)
        self._atualizar_botoes()

    # --- dados --------------------------------------------------------
    def atualizar(self) -> None:
        base = self._obter_base()
        self._registros = registro_pdfs.listar_pdfs(base)
        existe = Path(base).is_dir()
        self.var_pasta.set(f"Pasta: {base}" if existe else f"A pasta de evidências ainda não existe: {base}")
        self._mostrar()

    def _tique(self) -> None:
        self.after(INTERVALO_ATUALIZACAO_MS, self._tique)
        if self.winfo_ismapped():  # só varre a pasta enquanto a aba está à vista
            self.atualizar()

    def _mostrar(self) -> None:
        visiveis = registro_pdfs.filtrar(self._registros, self.var_filtro.get())
        assinatura = tuple((r.caminho, r.momento, r.tamanho) for r in visiveis)
        if assinatura == self._assinatura:
            return  # nada mudou: a atualização automática não derruba a seleção nem a rolagem
        self._assinatura = assinatura
        anteriores = {r.caminho for r in self._selecionados()}
        self.arvore.delete(*self.arvore.get_children())
        self._por_iid = {}
        for i, r in enumerate(visiveis):
            iid = str(i)
            self._por_iid[iid] = r
            self.arvore.insert("", "end", iid=iid, values=(
                r.momento.strftime("%d/%m/%Y %H:%M"), r.teste, r.tipo, registro_pdfs.formatar_tamanho(r.tamanho)))
            if r.caminho in anteriores:
                self.arvore.selection_add(iid)
        total, mostrados = len(self._registros), len(visiveis)
        if not total:
            self.var_status.set("Nenhum PDF ainda. Finalize um teste para gerar o primeiro.")
        elif mostrados != total:
            self.var_status.set(f"Mostrando {mostrados} de {total} PDFs.")
        elif not self.var_status.get().startswith(("Arquivo", "Caminho", "Cópia", "E-mail")):
            self.var_status.set(f"{total} PDF(s). Dois cliques abrem; Ctrl ou Shift escolhem vários para o Claude.")
        self._atualizar_botoes()

    def _selecionados(self) -> list[RegistroPdf]:
        return [self._por_iid[i] for i in self.arvore.selection() if i in self._por_iid]

    def _selecionado(self) -> RegistroPdf | None:
        """O PDF selecionado, se for exatamente um: as ações de arquivo não valem para vários de uma vez."""
        marcados = self._selecionados()
        return marcados[0] if len(marcados) == 1 else None

    def _pastas_selecionadas(self) -> list[Path]:
        """Pasta de cada teste cujos PDFs estão selecionados (um teste com 2 PDFs conta uma vez só)."""
        vistas: dict[Path, None] = {}
        for r in self._selecionados():
            vistas.setdefault(r.caminho.parent, None)
        return list(vistas)

    def _rotulo_do_claude(self) -> str:
        n = len(self._pastas_selecionadas())
        if n <= 1:
            return "Enviar ao Claude para analisar…"
        return f"Enviar ao Claude para analisar {n} testes…"

    def _atualizar_botoes(self) -> None:
        um = ["!disabled"] if self._selecionado() else ["disabled"]
        for botao in self._botoes:
            botao.state(um)
        texto = self._rotulo_do_claude()
        ligado = bool(self._selecionados()) and self._ao_enviar_ao_claude is not None
        self.botao_claude.configure(text=texto)
        self.botao_claude.state(["!disabled"] if ligado else ["disabled"])
        for i in range(len(self._acoes)):
            self.menu.entryconfigure(i, state="normal" if self._selecionado() else "disabled")
        self.menu.entryconfigure(len(self._acoes) + 1, label=texto, state="normal" if ligado else "disabled")

    def _menu_de_contexto(self, evento) -> None:
        iid = self.arvore.identify_row(evento.y)
        if iid:
            if iid not in self.arvore.selection():
                self.arvore.selection_set(iid)  # clicar fora da seleção troca; dentro dela, mantém os vários
            self._atualizar_botoes()
            self.menu.tk_popup(evento.x_root, evento.y_root)

    # --- ações --------------------------------------------------------
    def enviar_ao_claude(self) -> None:
        """Entrega ao app as pastas dos testes selecionados, para montar o prompt e abrir o Claude."""
        pastas = self._pastas_selecionadas()
        if not pastas or self._ao_enviar_ao_claude is None:
            return
        self._ao_enviar_ao_claude(pastas)

    def _com_arquivo(self, acao: Callable[[RegistroPdf], None]) -> None:
        registro = self._selecionado()
        if registro is None:
            return
        if not registro.caminho.is_file():
            messagebox.showwarning("Arquivo não encontrado",
                                   "Este PDF não está mais na pasta (foi movido ou apagado).", parent=self)
            self.atualizar()
            return
        try:
            acao(registro)
        except OSError as exc:
            messagebox.showerror("Não foi possível concluir", str(exc), parent=self)

    def abrir(self) -> None:
        self._com_arquivo(lambda r: os.startfile(r.caminho))

    def mostrar_na_pasta(self) -> None:
        self._com_arquivo(lambda r: winutil.revelar_no_explorador(r.caminho))

    def copiar_caminho(self) -> None:
        def acao(r: RegistroPdf) -> None:
            self.clipboard_clear()
            self.clipboard_append(str(r.caminho))
            self.update()
            self.var_status.set("Caminho copiado.")

        self._com_arquivo(acao)

    def copiar_arquivo(self) -> None:
        def acao(r: RegistroPdf) -> None:
            winutil.copiar_arquivos_para_area_de_transferencia([r.caminho])
            self.var_status.set("Arquivo copiado: cole (Ctrl+V) num e-mail, no Teams ou numa pasta.")

        self._com_arquivo(acao)

    def salvar_copia(self) -> None:
        def acao(r: RegistroPdf) -> None:
            destino = filedialog.asksaveasfilename(
                parent=self, title="Salvar cópia do PDF", initialfile=r.caminho.name,
                defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
            if not destino:
                return
            if Path(destino).resolve() == r.caminho.resolve():
                self.var_status.set("Cópia não feita: o destino é o próprio arquivo.")
                return
            shutil.copy2(r.caminho, destino)
            self.var_status.set(f"Cópia salva em: {destino}")

        self._com_arquivo(acao)

    def enviar_por_email(self) -> None:
        """Abre um e-mail novo e deixa o PDF na área de transferência para colar (Ctrl+V) como anexo.

        O padrão mailto: não permite anexar arquivos; colar é o jeito que funciona em qualquer cliente.
        """
        def acao(r: RegistroPdf) -> None:
            winutil.copiar_arquivos_para_area_de_transferencia([r.caminho])
            assunto = quote(f"{r.tipo}: {r.teste}")
            corpo = quote(f"Segue o PDF “{r.caminho.name}”.\n\n(Cole o arquivo aqui com Ctrl+V para anexar.)")
            os.startfile(f"mailto:?subject={assunto}&body={corpo}")
            self.var_status.set("E-mail aberto. O PDF está copiado: cole (Ctrl+V) na mensagem para anexar.")

        self._com_arquivo(acao)
