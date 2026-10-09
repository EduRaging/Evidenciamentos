"""Janela principal do Capturador de Evidências."""
from __future__ import annotations

import logging
import os
import queue
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from . import atalhos, captura, config, winutil
from .aviso import mostrar_aviso
from .dialogos import abrir_configuracoes
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
        self._montar()
        self.raiz.update()
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
        r.title("Capturador de Evidências")
        r.geometry("500x560")
        r.minsize(440, 480)
        r.protocol("WM_DELETE_WINDOW", self._ao_fechar)

        quadro = ttk.Frame(r, padding=14)
        quadro.pack(fill="both", expand=True)

        ttk.Label(quadro, text="Nome do teste").pack(anchor="w")
        self.var_nome = tk.StringVar()
        ttk.Entry(quadro, textvariable=self.var_nome).pack(fill="x", pady=(2, 12))

        botoes = ttk.Frame(quadro)
        botoes.pack(fill="x")
        botoes.columnconfigure((0, 1), weight=1, uniform="capturar")
        self.btn_tela = ttk.Button(botoes, command=self.capturar_tela)
        self.btn_tela.grid(row=0, column=0, sticky="ew", padx=(0, 4), ipady=6)
        self.btn_recorte = ttk.Button(botoes, command=self.capturar_recorte)
        self.btn_recorte.grid(row=0, column=1, sticky="ew", padx=(4, 0), ipady=6)

        ttk.Label(quadro, text="Evidências desta sessão").pack(anchor="w", pady=(14, 2))
        lista = ttk.Frame(quadro)
        lista.pack(fill="both", expand=True)
        self.lista = ttk.Treeview(lista, columns=("n", "tipo", "hora"), show="headings",
                                  selectmode="browse", height=8)
        for coluna, titulo, largura in (("n", "#", 40), ("tipo", "Tipo", 150), ("hora", "Hora", 120)):
            self.lista.heading(coluna, text=titulo)
            self.lista.column(coluna, width=largura, anchor="w" if coluna != "n" else "center")
        barra = ttk.Scrollbar(lista, orient="vertical", command=self.lista.yview)
        self.lista.configure(yscrollcommand=barra.set)
        self.lista.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self.lista.bind("<Double-1>", lambda _e: self._abrir_selecionada())

        acoes = ttk.Frame(quadro)
        acoes.pack(fill="x", pady=(6, 0))
        ttk.Button(acoes, text="Abrir imagem", command=self._abrir_selecionada).pack(side="left")
        ttk.Button(acoes, text="Remover selecionada", command=self._remover_selecionada).pack(
            side="left", padx=6)

        ttk.Separator(quadro).pack(fill="x", pady=12)
        rodape = ttk.Frame(quadro)
        rodape.pack(fill="x")
        ttk.Button(rodape, text="Finalizar e gerar PDF", command=self.finalizar).pack(
            side="left", ipady=4, ipadx=6)
        ttk.Button(rodape, text="Descartar tudo", command=self._descartar).pack(side="left", padx=6)
        ttk.Button(rodape, text="Configurações…", command=self._configuracoes).pack(side="right")

        self.var_status = tk.StringVar()
        ttk.Label(quadro, textvariable=self.var_status, foreground="#555", wraplength=460).pack(
            anchor="w", pady=(10, 0))
        self._atualizar_rotulos()

    def _atualizar_rotulos(self) -> None:
        self.btn_tela.configure(text=f"Tela inteira\n{atalhos.formatar(self.cfg.atalho_tela)}")
        self.btn_recorte.configure(text=f"Recortar área\n{atalhos.formatar(self.cfg.atalho_recorte)}")

    def _status(self, texto: str) -> None:
        self.var_status.set(texto)

    def _recarregar_lista(self) -> None:
        self.lista.delete(*self.lista.get_children())
        for i, ev in enumerate(self.sessao.evidencias, start=1):
            self.lista.insert("", "end", iid=str(i - 1),
                              values=(i, ROTULOS.get(ev.tipo, ev.tipo), ev.momento.strftime("%H:%M:%S")))
        if self.sessao.evidencias:
            self.lista.see(str(len(self.sessao.evidencias) - 1))

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
        self._status(f"Pasta criada: {pasta}")
        if messagebox.askyesno("Teste finalizado",
                               f"Evidências e PDF salvos em:\n{pasta}\n\nAbrir a pasta agora?",
                               parent=self.raiz):
            os.startfile(pasta)
        return True

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
    if not winutil.instancia_unica():
        aviso = tk.Tk()
        aviso.withdraw()
        messagebox.showinfo("Capturador de Evidências",
                            "O Capturador já está em execução (procure na barra de tarefas).")
        return
    App().rodar()
