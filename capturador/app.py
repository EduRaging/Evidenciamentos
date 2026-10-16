"""Janela principal do Capturador de Evidências."""
from __future__ import annotations

import logging
import os
import queue
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import atalhos, captura, config, estilo, miniaturas, recursos, winutil
from .aviso import mostrar_aviso
from .dialogo_prompt import abrir_dialogo_prompt, ler_testes
from .dialogos import abrir_configuracoes
from .painel_pdfs import PainelPdfs
from .sessao import ROTULOS, Sessao

log = logging.getLogger(__name__)


class App:
    def __init__(self) -> None:
        self.cfg = config.carregar()
        self.sessao = Sessao(config.pasta_config() / "em_andamento")
        self._fila: queue.Queue[str] = queue.Queue()
        self._ocupado = False
        self.atalhos = atalhos.GerenciadorAtalhos(self._fila.put)

        self.raiz = tk.Tk()
        self.raiz.report_callback_exception = self._erro_inesperado
        try:
            self.raiz.iconbitmap(default=str(recursos.caminho("assets/icone.ico")))
        except tk.TclError:
            log.warning("Ícone não encontrado; seguindo sem ele.")
        self._montar()
        self.raiz.update()
        if not winutil.definir_icone(self.raiz, recursos.caminho("assets/icone.ico")):
            log.warning("Não consegui definir o ícone da janela na barra de tarefas.")
        winutil.excluir_da_captura(self.raiz)  # a janela do app não sai nos prints

        self.var_nome.set(self.sessao.nome_teste)
        self._recarregar_lista()
        if self.sessao.evidencias:
            self._status(f"Sessão anterior retomada: {len(self.sessao.evidencias)} evidência(s).")
        self.raiz.after(50, self._processar_fila)
        self.raiz.after(300, self._registrar_atalhos)

    # --- interface ----------------------------------------------------
    def _montar(self) -> None:
        r = self.raiz
        estilo.aplicar(r)
        r.title("Capturador de Evidências")
        r.geometry("540x680")
        r.minsize(500, 600)
        r.protocol("WM_DELETE_WINDOW", self._ao_fechar)

        self.abas = ttk.Notebook(r)
        self.abas.pack(fill="both", expand=True)
        quadro = ttk.Frame(self.abas, padding=(18, 16, 18, 12))
        self.abas.add(quadro, text="  Capturar  ")
        self.painel_pdfs = PainelPdfs(self.abas, lambda: self.cfg.pasta_base, self._analisar_varios)
        self.abas.add(self.painel_pdfs, text="  Meus testes  ")
        self.abas.bind("<<NotebookTabChanged>>", lambda _e: self.painel_pdfs.atualizar())

        # --- nome do teste e os dois botões de captura
        ttk.Label(quadro, text="Nome do teste", style="Suave.TLabel").pack(anchor="w")
        self.var_nome = tk.StringVar()
        ttk.Entry(quadro, textvariable=self.var_nome, font=(estilo.FAMILIA, 11)).pack(fill="x", pady=(2, 14), ipady=3)

        botoes = ttk.Frame(quadro)
        botoes.pack(fill="x")
        botoes.columnconfigure((0, 1), weight=1, uniform="capturar")
        self.btn_tela = ttk.Button(botoes, command=self.capturar_tela)
        self.btn_tela.grid(row=0, column=0, sticky="ew", padx=(0, 5), ipady=7)
        self.btn_recorte = ttk.Button(botoes, command=self.capturar_recorte)
        self.btn_recorte.grid(row=0, column=1, sticky="ew", padx=(5, 0), ipady=7)

        # --- evidências da sessão: miniaturas (ou um convite, enquanto não há nenhuma)
        self.var_contador = tk.StringVar()
        ttk.Label(quadro, textvariable=self.var_contador, style="Secao.TLabel").pack(anchor="w", pady=(18, 4))
        self._area_lista = ttk.Frame(quadro)
        self._moldura_lista = ttk.Frame(self._area_lista)
        self.lista = ttk.Treeview(self._moldura_lista, show="tree", selectmode="browse", style="Evid.Treeview")
        self.lista.column("#0", width=300, stretch=True)
        barra = ttk.Scrollbar(self._moldura_lista, orient="vertical", command=self.lista.yview)
        self.lista.configure(yscrollcommand=barra.set)
        self.lista.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self._vazio = ttk.Label(self._area_lista, style="Suave.TLabel", justify="center", anchor="center",
                                relief="groove", padding=20, wraplength=400)
        self._dica = ttk.Label(quadro, text="Duplo clique abre a imagem · Delete remove a selecionada",
                               style="Suave.TLabel")
        self._miniaturas: list = []  # referências: o Tk descarta a imagem se ninguém a segurar
        self.lista.bind("<Double-1>", lambda _e: self._abrir_selecionada())
        self.lista.bind("<Return>", lambda _e: self._abrir_selecionada())
        self.lista.bind("<Delete>", lambda _e: self._remover_selecionada())
        self.lista.bind("<Button-3>", self._menu_da_evidencia)
        self.menu_evidencia = tk.Menu(self.raiz, tearoff=False)
        self.menu_evidencia.add_command(label="Abrir imagem", command=self._abrir_selecionada)
        self.menu_evidencia.add_command(label="Remover do teste", command=self._remover_selecionada)

        # --- ação principal e o que é secundário
        rodape = ttk.Frame(quadro)
        rodape.pack(fill="x", side="bottom", pady=(10, 0))
        self.btn_finalizar = estilo.botao_primario(rodape, "Finalizar teste", self.finalizar)
        self.btn_finalizar.pack(side="left")
        ttk.Button(rodape, text="Descartar", style="Link.Toolbutton", command=self._descartar).pack(side="left", padx=10)
        ttk.Button(rodape, text="Configurações", style="Link.Toolbutton", command=self._configuracoes).pack(side="right")

        self.var_status = tk.StringVar()
        ttk.Label(quadro, textvariable=self.var_status, style="Suave.TLabel", wraplength=480).pack(
            anchor="w", side="bottom", pady=(8, 0))
        self._dica.pack(anchor="w", side="bottom", pady=(6, 0))
        # a lista é empacotada por último: o que está embaixo reserva o seu espaço antes dela
        self._area_lista.pack(fill="both", expand=True)
        self._atualizar_rotulos()

    def _atualizar_rotulos(self) -> None:
        self.btn_tela.configure(text=f"Tela inteira\n{atalhos.formatar(self.cfg.atalho_tela)}")
        self.btn_recorte.configure(text=f"Recortar área\n{atalhos.formatar(self.cfg.atalho_recorte)}")

    def _status(self, texto: str) -> None:
        self.var_status.set(texto)

    def _recarregar_lista(self) -> None:
        self.lista.delete(*self.lista.get_children())
        self._miniaturas = []
        total = len(self.sessao.evidencias)
        for i, ev in enumerate(self.sessao.evidencias, start=1):
            foto = miniaturas.obter(self.sessao.caminho(ev))
            if foto is not None:
                self._miniaturas.append(foto)
            self.lista.insert("", "end", iid=str(i - 1), image=foto or "",
                              text=f"  {i}   {ROTULOS.get(ev.tipo, ev.tipo)}  ·  {ev.momento.strftime('%H:%M:%S')}")
        self._dica.configure(text="Duplo clique abre a imagem · Delete remove a selecionada" if total else "")
        if total:
            self._vazio.pack_forget()
            self._moldura_lista.pack(fill="both", expand=True)
            self.lista.see(str(total - 1))
            self.var_contador.set(f"{total} {'evidência' if total == 1 else 'evidências'}")
        else:
            self._moldura_lista.pack_forget()
            self._vazio.configure(text="Nenhuma evidência ainda.\n\nCapture com os botões acima ou com os atalhos "
                                       f"({atalhos.formatar(self.cfg.atalho_tela)} para a tela inteira).")
            self._vazio.pack(fill="both", expand=True)
            self.var_contador.set("Evidências")
        estilo.ativar(self.btn_finalizar, bool(total))
        self.btn_finalizar.configure(text=f"Finalizar teste  ·  {total}" if total else "Finalizar teste")

    def _menu_da_evidencia(self, evento) -> None:
        iid = self.lista.identify_row(evento.y)
        if iid:
            self.lista.selection_set(iid)
            self.menu_evidencia.tk_popup(evento.x_root, evento.y_root)

    def _selecionada(self) -> int | None:
        marcado = self.lista.selection()
        return int(marcado[0]) if marcado else None

    def _abrir_selecionada(self) -> None:
        posicao = self._selecionada()
        if posicao is not None:
            os.startfile(self.sessao.caminho(self.sessao.evidencias[posicao]))

    def _remover_selecionada(self) -> None:
        posicao = self._selecionada()
        if posicao is None:
            self._status("Selecione uma evidência na lista para remover.")
            return
        self.sessao.remover(posicao)
        self._recarregar_lista()
        self._status("Evidência removida.")

    # --- atalhos e capturas ------------------------------------------
    def _registrar_atalhos(self) -> None:
        erros = self.atalhos.registrar({
            "tela": self.cfg.atalho_tela,
            "recorte": self.cfg.atalho_recorte,
            "janela": self.cfg.atalho_janela,
        })
        if erros:
            messagebox.showwarning("Atalhos indisponíveis", "\n".join(erros.values())
                                   + "\n\nEscolha outro em Configurações.", parent=self.raiz)

    def _processar_fila(self) -> None:
        self.raiz.after(50, self._processar_fila)  # reagenda antes: segue vivo durante o recorte
        try:
            while True:
                nome = self._fila.get_nowait()
                if self._ocupado:
                    continue  # atalho apertado no meio de outra captura
                if nome == "tela":
                    self.capturar_tela()
                elif nome == "recorte":
                    self.capturar_recorte()
                elif nome == "janela":
                    self._alternar_janela()
        except queue.Empty:
            pass

    def _alternar_janela(self) -> None:
        if self.raiz.state() == "normal":
            self.raiz.iconify()
        else:
            self.raiz.deiconify()
            self.raiz.lift()
            self.raiz.focus_force()

    def _capturar(self, tipo: str) -> None:
        if self._ocupado:
            return
        self._ocupado = True
        try:
            imagem, monitor = captura.capturar_monitor()  # primeiro, para congelar o estado atual
            if tipo == "recorte":
                imagem = captura.selecionar_recorte(self.raiz, imagem, monitor)
                if imagem is None:
                    return
            self.sessao.nome_teste = self.var_nome.get().strip()
            self.sessao.adicionar(imagem, tipo)
            self._recarregar_lista()
            total = len(self.sessao.evidencias)
            self._status(f"{ROTULOS[tipo]} capturada ({total} no total).")
            mostrar_aviso(self.raiz, f"Evidência {total} capturada · {ROTULOS[tipo].lower()}", monitor)
        except Exception as exc:  # noqa: BLE001 - qualquer falha deve aparecer ao usuário
            log.exception("Falha ao capturar")
            messagebox.showerror("Erro ao capturar", str(exc), parent=self.raiz)
        finally:
            self._ocupado = False

    def capturar_tela(self) -> None:
        self._capturar("tela")

    def capturar_recorte(self) -> None:
        self._capturar("recorte")

    # --- fechamento do teste -----------------------------------------
    def finalizar(self) -> bool:
        """Cria a pasta + PDF. True se concluiu."""
        if not self.sessao.evidencias:
            messagebox.showinfo("Sem evidências", "Capture ao menos uma tela antes de finalizar.",
                                parent=self.raiz)
            return False
        nome = self.var_nome.get().strip()
        if not nome:
            nome = (simpledialog.askstring(
                "Nome do teste", "Informe o nome do teste (será o nome da pasta):",
                parent=self.raiz) or "").strip()
            if not nome:
                return False
            self.var_nome.set(nome)
        self._status("Gerando PDF…")
        self.raiz.update_idletasks()
        try:
            pasta = self.sessao.finalizar(nome, self.cfg.testador, self.cfg.pasta_base)
        except Exception as exc:  # noqa: BLE001
            log.exception("Falha ao finalizar")
            messagebox.showerror("Erro ao gerar o PDF", str(exc), parent=self.raiz)
            self._status("Falha ao gerar o PDF. As capturas continuam guardadas.")
            return False
        self.var_nome.set("")
        self._recarregar_lista()
        self._lembrar_pasta(pasta)
        self.painel_pdfs.atualizar()
        self._status(f"Pasta criada: {pasta}")
        self._dialogo_concluido(pasta)
        return True

    def _lembrar_pasta(self, pasta: Path) -> None:
        self.cfg = replace(self.cfg, ultima_pasta=str(pasta))
        config.salvar(self.cfg)

    def _dialogo_concluido(self, pasta: Path) -> None:
        """Aviso de teste finalizado com os próximos passos (abrir a pasta ou preparar o prompt)."""
        janela = tk.Toplevel(self.raiz)
        janela.title("Teste finalizado")
        janela.transient(self.raiz)
        janela.resizable(False, False)
        corpo = ttk.Frame(janela, padding=(22, 20, 22, 6))
        corpo.pack(fill="x")
        ttk.Label(corpo, text="✓  Teste finalizado", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(corpo, text=pasta.name, wraplength=440, justify="left").pack(anchor="w", pady=(8, 0))
        ttk.Label(corpo, text=f"As evidências e o PDF estão em {pasta.parent}", style="Suave.TLabel",
                  wraplength=440, justify="left").pack(anchor="w", pady=(2, 0))
        botoes = ttk.Frame(janela, padding=(22, 14, 22, 20))
        botoes.pack(fill="x")
        escolha: list[str] = []

        def fechar(acao: str = "") -> None:
            escolha.append(acao)
            janela.destroy()

        estilo.botao_primario(botoes, "Enviar ao Claude…", lambda: fechar("prompt")).pack(side="left")
        ttk.Button(botoes, text="Abrir pasta", command=lambda: fechar("pasta")).pack(side="left", padx=(10, 0))
        ttk.Button(botoes, text="Fechar", command=fechar).pack(side="right")
        janela.protocol("WM_DELETE_WINDOW", fechar)
        janela.update_idletasks()
        janela.grab_set()
        janela.focus_force()
        self.raiz.wait_window(janela)
        acao = escolha[0] if escolha else ""
        if acao == "pasta":
            os.startfile(pasta)
        elif acao == "prompt":
            self._preparar_prompt(pasta)

    def _preparar_prompt(self, pasta: Path | None = None) -> None:
        """Abre a janela do prompt de IA para `pasta` (padrão: o último teste finalizado)."""
        if pasta is None:
            ultima = Path(self.cfg.ultima_pasta) if self.cfg.ultima_pasta else None
            if ultima and ultima.is_dir():
                pasta = ultima
            else:
                base = Path(self.cfg.pasta_base)
                escolhida = filedialog.askdirectory(
                    parent=self.raiz, initialdir=str(base) if base.is_dir() else None,
                    title="Escolha a pasta do teste")
                if not escolhida:
                    return
                pasta = Path(escolhida)
        try:
            usada = abrir_dialogo_prompt(self.raiz, pasta, self.cfg.pasta_base)
        except ValueError as exc:
            messagebox.showwarning("Pasta inválida", str(exc), parent=self.raiz)
            return
        self._lembrar_pasta(usada)

    def _analisar_varios(self, pastas: list[Path]) -> None:
        """Abre a janela do prompt para os testes escolhidos na aba "PDFs gerados"."""
        testes, ignorados = ler_testes(pastas)
        if ignorados:
            lista = "\n".join(f"• {nome}" for nome, _motivo in ignorados)
            messagebox.showinfo(
                "Testes ignorados",
                "Estes testes não têm imagens de evidência que o Claude possa analisar (ou o registro "
                f"evidencias.json está inválido), então ficaram de fora:\n\n{lista}", parent=self.raiz)
        if not testes:
            return
        try:
            abrir_dialogo_prompt(self.raiz, [t.pasta for t in testes], self.cfg.pasta_base)
        except ValueError as exc:
            messagebox.showwarning("Não foi possível preparar o envio", str(exc), parent=self.raiz)

    def _descartar(self) -> None:
        if not self.sessao.evidencias:
            self.var_nome.set("")
            return
        if messagebox.askyesno("Descartar tudo",
                               f"Apagar as {len(self.sessao.evidencias)} evidência(s) desta sessão?\n"
                               "Isso não pode ser desfeito.", icon="warning", parent=self.raiz):
            self.sessao.descartar()
            self.var_nome.set("")
            self._recarregar_lista()
            self._status("Sessão descartada.")

    def _configuracoes(self) -> None:
        self.atalhos.parar()  # evita que os atalhos atuais disparem enquanto se escolhe outro
        try:
            nova = abrir_configuracoes(self.raiz, self.cfg)
            if nova:
                self.cfg = nova
                config.salvar(nova)
                self._atualizar_rotulos()
        finally:
            self._registrar_atalhos()

    def _ao_fechar(self) -> None:
        if self.sessao.evidencias:
            resposta = messagebox.askyesnocancel(
                "Sair",
                f"Há {len(self.sessao.evidencias)} evidência(s) ainda não finalizadas.\n\n"
                "Sim: gerar o PDF agora e sair.\n"
                "Não: sair e continuar da próxima vez.\n"
                "Cancelar: voltar.", parent=self.raiz)
            if resposta is None:
                return
            if resposta and not self.finalizar():
                return
            self.sessao.nome_teste = self.var_nome.get().strip()
            if self.sessao.evidencias:
                self.sessao.salvar()
        self.atalhos.parar()
        self.raiz.destroy()

    def _erro_inesperado(self, tipo, valor, rastro) -> None:
        log.error("Erro inesperado na interface", exc_info=(tipo, valor, rastro))
        messagebox.showerror("Erro inesperado", f"{tipo.__name__}: {valor}", parent=self.raiz)

    def rodar(self) -> None:
        self.raiz.mainloop()


def _configurar_log() -> None:
    pasta = config.pasta_config()
    pasta.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=pasta / "capturador.log", level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def executar() -> None:
    _configurar_log()
    captura.ativar_dpi()
    winutil.definir_identidade_do_app()  # antes de qualquer janela: ícone próprio na barra de tarefas
    if not winutil.instancia_unica():
        aviso = tk.Tk()
        aviso.withdraw()
        messagebox.showinfo("Capturador de Evidências",
                            "O Capturador já está em execução (procure na barra de tarefas).")
        return
    App().rodar()
