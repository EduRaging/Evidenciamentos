"""Aba "Meus testes": um item por teste, com abrir, gerar o relatório, compartilhar e arquivar."""
from __future__ import annotations

import os
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable
from urllib.parse import quote

from . import arquivamento, estilo, registro_pdfs, winutil
from .registro_pdfs import RegistroPdf, TesteRegistrado

INTERVALO_ATUALIZACAO_MS = 6000  # relatórios gerados por fora (ex.: pela IA) aparecem sozinhos
SIM, NAO = "✓", "—"


def _rotulo_do_pdf(teste: TesteRegistrado, pdf: RegistroPdf) -> str:
    if pdf is teste.evidencias:
        return "Evidências"
    grupo = teste.sugestoes if pdf in teste.sugestoes else teste.relatorios
    nome = "Sugestões" if pdf in teste.sugestoes else "Relatório"
    return nome if len(grupo) == 1 else f"{nome} de {pdf.momento:%d/%m %H:%M}"


def _marca(itens: tuple) -> str:
    """✓ (ou "✓ 2" quando há mais de um) ou — para a tabela."""
    if not itens:
        return NAO
    return SIM if len(itens) == 1 else f"{SIM} {len(itens)}"


class PainelPdfs(ttk.Frame):
    def __init__(self, pai: tk.Misc, obter_base: Callable[[], str],
                 ao_gerar_relatorio: Callable[[list[Path]], None] | None = None,
                 ao_criar_ciclo: Callable[[list[Path]], None] | None = None,
                 ao_enviar_manual: Callable[[list[Path]], None] | None = None,
                 ao_cancelar_relatorio: Callable[[], None] | None = None) -> None:
        """Os callbacks com lista recebem as pastas (sem repetir) dos testes selecionados.

        `ao_gerar_relatorio` é o caminho normal (o app chama o Claude sozinho); `ao_enviar_manual` abre o Claude desktop
        com o pedido, só como plano B, no menu Mais.
        """
        super().__init__(pai, padding=(18, 16, 18, 12))
        self._obter_base = obter_base
        self._ao_gerar_relatorio = ao_gerar_relatorio
        self._ao_criar_ciclo = ao_criar_ciclo
        self._ao_enviar_manual = ao_enviar_manual
        self._ao_cancelar_relatorio = ao_cancelar_relatorio
        self._gerando: set[Path] = set()  # testes cujo relatório o Claude está montando agora
        self._mensagem = ""  # último aviso do app (andamento do relatório): a atualização automática não o apaga
        self._testes: list[TesteRegistrado] = []
        self._por_iid: dict[str, TesteRegistrado] = {}
        self._assinatura: tuple | None = None
        self._montar()
        self.after(150, self.atualizar)
        self.after(INTERVALO_ATUALIZACAO_MS, self._tique)

    # --- interface ----------------------------------------------------
    def _montar(self) -> None:
        topo = ttk.Frame(self)
        topo.pack(fill="x")
        self.var_filtro = tk.StringVar()
        entrada = ttk.Entry(topo, textvariable=self.var_filtro, font=(estilo.FAMILIA, 11))
        entrada.pack(side="left", fill="x", expand=True, ipady=3)
        ttk.Button(topo, text="↻", width=3, command=self.atualizar).pack(side="left", padx=(6, 0))
        self.var_filtro.trace_add("write", lambda *_: self._mostrar())
        ttk.Label(self, text="Buscar por nome do teste", style="Suave.TLabel").pack(anchor="w", pady=(2, 8))

        # rodapé primeiro (reserva o espaço); a lista, que cresce, é empacotada por último
        rodape = ttk.Frame(self)
        rodape.pack(fill="x", side="bottom", pady=(10, 0))
        self.botao_relatorio = estilo.botao_primario(rodape, "Gerar relatório", self.gerar_relatorio)
        self.botao_relatorio.pack(side="left")
        self.botao_mais = ttk.Button(rodape, text="Mais ▾", command=self._abrir_menu_mais)
        self.botao_mais.pack(side="right")
        self.botao_abrir = ttk.Button(rodape, text="Abrir PDF", command=self.abrir)
        self.botao_abrir.pack(side="right", padx=(0, 6))
        self.var_status = tk.StringVar()
        ttk.Label(self, textvariable=self.var_status, style="Suave.TLabel", wraplength=480,
                  justify="left").pack(anchor="w", side="bottom", pady=(8, 0))
        ttk.Label(self, text="Evid. = evidências · Relat. = relatório · Sug. = sugestões de casos"
                  "\nCtrl ou Shift escolhem vários testes", style="Suave.TLabel", wraplength=490,
                  justify="left").pack(anchor="w", side="bottom", pady=(6, 0))

        corpo = ttk.Frame(self)
        corpo.pack(fill="both", expand=True)
        self._moldura = ttk.Frame(corpo)
        self.arvore = ttk.Treeview(self._moldura, columns=("data", "teste", "evidencias", "relatorio", "sugestoes"),
                                   show="headings", selectmode="extended", style="Tabela.Treeview")
        for coluna, titulo, largura, ancora, estica in (
                ("data", "Data", 58, "w", False), ("teste", "Teste", 200, "w", True),
                ("evidencias", "Evid.", 56, "center", False), ("relatorio", "Relat.", 58, "center", False),
                ("sugestoes", "Sug.", 52, "center", False)):
            self.arvore.heading(coluna, text=titulo)
            self.arvore.column(coluna, width=largura, anchor=ancora, stretch=estica)
        barra = ttk.Scrollbar(self._moldura, orient="vertical", command=self.arvore.yview)
        self.arvore.configure(yscrollcommand=barra.set)
        self.arvore.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self._vazio = ttk.Label(corpo, style="Suave.TLabel", justify="center", anchor="center", relief="groove",
                                padding=20, wraplength=400)
        self.arvore.bind("<<TreeviewSelect>>", lambda _e: self._atualizar_botoes())
        self.arvore.bind("<Double-1>", lambda _e: self.abrir())
        self.arvore.bind("<Return>", lambda _e: self.abrir())
        self.arvore.bind("<Button-3>", self._menu_de_contexto)
        self._corpo = corpo
        self._atualizar_botoes()

    # --- dados --------------------------------------------------------
    def atualizar(self) -> None:
        base = self._obter_base()
        self._testes = registro_pdfs.agrupar_por_teste(registro_pdfs.listar_pdfs(base))
        self._base_existe = Path(base).is_dir()
        self._mostrar()

    def _tique(self) -> None:
        self.after(INTERVALO_ATUALIZACAO_MS, self._tique)
        if self.winfo_ismapped():  # só varre a pasta enquanto a aba está à vista
            self.atualizar()

    def mensagem(self, texto: str) -> None:
        """Mostra um aviso do app na linha de status (o resumo da lista só volta quando outro aviso o substituir)."""
        self._mensagem = texto
        self.var_status.set(texto)

    def marcar_gerando(self, pastas: set[Path] | frozenset[Path]) -> None:
        """Mostra "…" na coluna do relatório dos testes que o Claude está analisando (vazio = nenhum)."""
        self._gerando = set(pastas)
        self._assinatura = None
        self._mostrar()

    def _mostrar(self) -> None:
        visiveis = registro_pdfs.filtrar_testes(self._testes, self.var_filtro.get())
        assinatura = (self.var_filtro.get().strip(), frozenset(self._gerando), tuple(
            (t.pasta, tuple((p.caminho, p.momento, p.tamanho) for p in t.pdfs)) for t in visiveis))
        if assinatura == self._assinatura:
            return  # nada mudou: a atualização automática não derruba a seleção nem a rolagem
        self._assinatura = assinatura
        anteriores = {t.pasta for t in self._selecionados()}
        self.arvore.delete(*self.arvore.get_children())
        self._por_iid = {}
        for i, t in enumerate(visiveis):
            iid = str(i)
            self._por_iid[iid] = t
            self.arvore.insert("", "end", iid=iid, values=(
                t.momento.strftime("%d/%m"), t.teste, SIM if t.evidencias else NAO,
                "…" if t.pasta in self._gerando else _marca(t.relatorios), _marca(t.sugestoes)))
            if t.pasta in anteriores:
                self.arvore.selection_add(iid)
        total, mostrados = len(self._testes), len(visiveis)
        if mostrados:
            self._vazio.pack_forget()
            self._moldura.pack(fill="both", expand=True)
        else:
            self._moldura.pack_forget()
            if not total:
                texto = ("A pasta de evidências ainda não existe." if not getattr(self, "_base_existe", True)
                         else "Nenhum teste ainda.\n\nFinalize um teste na aba Capturar para ele aparecer aqui.")
            else:
                texto = f"Nenhum teste encontrado para “{self.var_filtro.get().strip()}”."
            self._vazio.configure(text=texto)
            self._vazio.pack(fill="both", expand=True)
        if not (self.var_status.get().startswith(("Arquivo", "Caminho", "Cópia", "E-mail", "Arquivado", "Abrindo"))
                or self.var_status.get() == self._mensagem):
            self.var_status.set(self._resumo(total, mostrados))
        self._atualizar_botoes()

    def _resumo(self, total: int, mostrados: int) -> str:
        if not total:
            return ""
        base = Path(self._obter_base()).name
        quantos = f"{total} {'teste' if total == 1 else 'testes'}"
        if mostrados != total:
            quantos = f"{mostrados} de {quantos}"
        return f"{quantos} em “{base}”"

    def _selecionados(self) -> list[TesteRegistrado]:
        return [self._por_iid[i] for i in self.arvore.selection() if i in self._por_iid]

    def _selecionado(self) -> TesteRegistrado | None:
        """O teste selecionado, se for exatamente um: as ações de arquivo não valem para vários de uma vez."""
        marcados = self._selecionados()
        return marcados[0] if len(marcados) == 1 else None

    def _pastas_selecionadas(self) -> list[Path]:
        return [t.pasta for t in self._selecionados()]

    def _atualizar_botoes(self) -> None:
        marcados = self._selecionados()
        um = self._selecionado()
        n = len(marcados)
        if self._gerando:  # enquanto o Claude trabalha, o botão principal passa a cancelar
            estilo.ativar(self.botao_relatorio, self._ao_cancelar_relatorio is not None)
            self.botao_relatorio.configure(text="Cancelar relatório")
        else:
            estilo.ativar(self.botao_relatorio, bool(marcados) and self._ao_gerar_relatorio is not None)
            self.botao_relatorio.configure(text="Gerar relatório" if n <= 1 else f"Gerar relatório  ·  {n} testes")
        self.botao_abrir.state(["!disabled"] if um and um.principal else ["disabled"])
        self.botao_mais.state(["!disabled"] if marcados else ["disabled"])

    # --- menu ---------------------------------------------------------
    def _menu_para_selecao(self) -> tk.Menu:
        """Monta o menu de ações do que está selecionado (muda conforme o teste e seus PDFs)."""
        menu = tk.Menu(self, tearoff=False)
        marcados = self._selecionados()
        um = self._selecionado()
        if self._ao_gerar_relatorio is not None and marcados:
            menu.add_command(label="Gerar relatório" if len(marcados) == 1 else f"Gerar relatório de {len(marcados)} testes",
                             command=self.gerar_relatorio, state="disabled" if self._gerando else "normal")
            if self._ao_criar_ciclo is not None:
                menu.add_command(label="Criar ciclo de testes com " + ("este teste…" if len(marcados) == 1 else "estes testes…"),
                                 command=self.criar_ciclo)
            if self._ao_enviar_manual is not None:
                menu.add_command(label="Pedir a análise no Claude desktop (manual)…", command=self.enviar_manual)
            menu.add_separator()
        if um is not None:
            if len(um.pdfs) == 1:
                self._itens_do_pdf(menu, um.pdfs[0])
            else:
                for pdf in um.pdfs:
                    sub = tk.Menu(menu, tearoff=False)
                    self._itens_do_pdf(sub, pdf)
                    menu.add_cascade(label=_rotulo_do_pdf(um, pdf), menu=sub)
            menu.add_command(label="Mostrar a pasta do teste", command=lambda: self._acao_pasta(um))
            menu.add_separator()
        if marcados:
            menu.add_command(label="Arquivar teste…" if len(marcados) == 1 else f"Arquivar {len(marcados)} testes…",
                             command=self.arquivar)
        menu.add_command(label="Abrir a pasta dos arquivados", command=self.abrir_pasta_dos_arquivados)
        return menu

    def _itens_do_pdf(self, menu: tk.Menu, pdf: RegistroPdf) -> None:
        for rotulo, acao in (("Abrir", self._abrir_pdf), ("Copiar arquivo (para colar no e-mail ou Teams)", self._copiar_arquivo),
                             ("Salvar cópia…", self._salvar_copia), ("Enviar por e-mail…", self._enviar_por_email),
                             ("Copiar caminho", self._copiar_caminho)):
            menu.add_command(label=rotulo, command=lambda a=acao: self._com_arquivo(pdf, a))

    def _abrir_menu_mais(self) -> None:
        menu = self._menu_para_selecao()
        x = self.botao_mais.winfo_rootx()
        y = self.botao_mais.winfo_rooty() + self.botao_mais.winfo_height()
        menu.tk_popup(x, y)

    def _menu_de_contexto(self, evento) -> None:
        iid = self.arvore.identify_row(evento.y)
        if iid:
            if iid not in self.arvore.selection():
                self.arvore.selection_set(iid)  # clicar fora da seleção troca; dentro dela, mantém os vários
            self._atualizar_botoes()
            self._menu_para_selecao().tk_popup(evento.x_root, evento.y_root)

    # --- ações --------------------------------------------------------
    def gerar_relatorio(self) -> None:
        """Entrega ao app as pastas dos testes selecionados, para o Claude montar o relatório sozinho (ou cancela, se já está gerando)."""
        if self._gerando:
            if self._ao_cancelar_relatorio is not None:
                self._ao_cancelar_relatorio()
            return
        pastas = self._pastas_selecionadas()
        if pastas and self._ao_gerar_relatorio is not None:
            self._ao_gerar_relatorio(pastas)

    def enviar_manual(self) -> None:
        """Plano B: abre o Claude desktop com o pedido de análise preenchido para os testes selecionados."""
        pastas = self._pastas_selecionadas()
        if pastas and self._ao_enviar_manual is not None:
            self._ao_enviar_manual(pastas)

    def criar_ciclo(self) -> None:
        """Cria um ciclo de testes tendo os testes selecionados como telas de referência."""
        pastas = self._pastas_selecionadas()
        if pastas and self._ao_criar_ciclo is not None:
            self._ao_criar_ciclo(pastas)

    def _com_arquivo(self, pdf: RegistroPdf | None, acao: Callable[[RegistroPdf], None]) -> None:
        if pdf is None:
            return
        if not pdf.caminho.is_file():
            messagebox.showwarning("Arquivo não encontrado",
                                   "Este PDF não está mais na pasta (foi movido ou apagado).", parent=self)
            self.atualizar()
            return
        try:
            acao(pdf)
        except OSError as exc:
            messagebox.showerror("Não foi possível concluir", str(exc), parent=self)

    def _principal(self) -> RegistroPdf | None:
        teste = self._selecionado()
        return teste.principal if teste else None

    def _abrir_pdf(self, r: RegistroPdf) -> None:
        os.startfile(r.caminho)

    def _copiar_caminho(self, r: RegistroPdf) -> None:
        self.clipboard_clear()
        self.clipboard_append(str(r.caminho))
        self.update()
        self.var_status.set("Caminho copiado.")

    def _copiar_arquivo(self, r: RegistroPdf) -> None:
        winutil.copiar_arquivos_para_area_de_transferencia([r.caminho])
        self.var_status.set("Arquivo copiado: cole (Ctrl+V) num e-mail, no Teams ou numa pasta.")

    def _salvar_copia(self, r: RegistroPdf) -> None:
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

    def _enviar_por_email(self, r: RegistroPdf) -> None:
        """Abre um e-mail novo e deixa o PDF na área de transferência para colar (Ctrl+V) como anexo.

        O padrão mailto: não permite anexar arquivos; colar é o jeito que funciona em qualquer cliente.
        """
        winutil.copiar_arquivos_para_area_de_transferencia([r.caminho])
        assunto = quote(f"{r.tipo}: {r.teste}")
        corpo = quote(f"Segue o PDF “{r.caminho.name}”.\n\n(Cole o arquivo aqui com Ctrl+V para anexar.)")
        os.startfile(f"mailto:?subject={assunto}&body={corpo}")
        self.var_status.set("E-mail aberto. O PDF está copiado: cole (Ctrl+V) na mensagem para anexar.")

    def _acao_pasta(self, teste: TesteRegistrado) -> None:
        alvo = teste.principal.caminho if teste.principal else teste.pasta
        if not teste.pasta.is_dir():
            messagebox.showwarning("Pasta não encontrada", "A pasta deste teste não existe mais.", parent=self)
            self.atualizar()
            return
        winutil.revelar_no_explorador(alvo)

    # atalhos para o PDF principal do teste selecionado (relatório mais recente, ou o de evidências)
    def abrir(self) -> None:
        self._com_arquivo(self._principal(), self._abrir_pdf)

    def mostrar_na_pasta(self) -> None:
        teste = self._selecionado()
        if teste:
            self._acao_pasta(teste)

    def copiar_caminho(self) -> None:
        self._com_arquivo(self._principal(), self._copiar_caminho)

    def copiar_arquivo(self) -> None:
        self._com_arquivo(self._principal(), self._copiar_arquivo)

    def salvar_copia(self) -> None:
        self._com_arquivo(self._principal(), self._salvar_copia)

    def enviar_por_email(self) -> None:
        self._com_arquivo(self._principal(), self._enviar_por_email)

    # --- arquivar -----------------------------------------------------
    def arquivar(self) -> None:
        """Move os testes selecionados para a pasta _arquivo (não apaga nada; desfaz-se movendo de volta)."""
        marcados = self._selecionados()
        if not marcados:
            return
        base = self._obter_base()
        nomes = "\n".join(f"• {t.teste}" for t in marcados[:8]) + (f"\n… e mais {len(marcados) - 8}" if len(marcados) > 8 else "")
        if not messagebox.askyesno(
                "Arquivar", f"Arquivar {'este teste' if len(marcados) == 1 else f'estes {len(marcados)} testes'}?\n\n"
                f"{nomes}\n\nEles saem desta lista e do alcance do Claude, mas nada é apagado: ficam na pasta "
                f"“{arquivamento.NOME_PASTA_ARQUIVO}” dentro da pasta de evidências, e dá para movê-los de volta.",
                parent=self):
            return
        feitos, falhas = 0, []
        for teste in marcados:
            try:
                arquivamento.arquivar(teste.pasta, base)
                feitos += 1
            except (ValueError, OSError) as exc:
                falhas.append(f"{teste.teste}: {exc}")
        self._assinatura = None
        self.atualizar()
        if falhas:
            messagebox.showwarning(
                "Alguns testes não foram arquivados",
                "\n\n".join(falhas) + "\n\nSe um PDF ou uma imagem do teste estiver aberta em outro programa, "
                "feche-a e tente de novo.", parent=self)
        if feitos:
            self.var_status.set(f"Arquivado{'s' if feitos > 1 else ''}: {feitos} "
                                f"{'teste' if feitos == 1 else 'testes'} (pasta “{arquivamento.NOME_PASTA_ARQUIVO}”).")

    def abrir_pasta_dos_arquivados(self) -> None:
        pasta = arquivamento.pasta_de_arquivo(self._obter_base())
        if pasta.is_dir():
            os.startfile(pasta)
        else:
            self.var_status.set("Ainda não há testes arquivados.")
