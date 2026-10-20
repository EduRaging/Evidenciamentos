"""Janela principal do Capturador de Evidências."""
from __future__ import annotations

import logging
import os
import queue
import threading
import time
import tkinter as tk
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from . import (atalhos, captura, ciclos, claude_desktop, config, estilo, extensao_claude, fluxo_ciclo, ia_local,
               miniaturas, recursos, roteiro_md, winutil)
from .aviso import mostrar_aviso
from .dialogo_ciclo import abrir_dialogo_ciclo
from .dialogo_prompt import abrir_dialogo_prompt, ler_testes
from .dialogos import abrir_configuracoes
from .painel_ciclos import PainelCiclos
from .painel_pdfs import PainelPdfs
from .prompt_ia import MAX_TESTES
from .sessao import ROTULOS, Sessao
from .visualizador_roteiro import abrir_visualizador

log = logging.getLogger(__name__)


class App:
    def __init__(self) -> None:
        self.cfg = config.carregar()
        self.sessao = Sessao(config.pasta_config() / "em_andamento")
        self._fila: queue.Queue[str] = queue.Queue()
        self._ocupado = False
        self._gerando: dict[Path, ia_local.Controle] = {}  # roteiros que o Claude está montando agora
        self._lote: dict | None = None  # relatórios que o Claude está montando agora (um lote por vez)
        self._andamento: dict = {}  # o que mostrar na linha de status, com o tempo, enquanto o Claude trabalha
        self._fila_ia: queue.Queue = queue.Queue()  # resultados das gerações (vêm de outra thread)
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
        self.raiz.after(500, self._processar_fila_ia)
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
        self.painel_pdfs = PainelPdfs(self.abas, lambda: self.cfg.pasta_base, self._gerar_relatorios,
                                      self._criar_ciclo_automatico, self._analisar_varios_manual,
                                      self._cancelar_relatorios)
        self.abas.add(self.painel_pdfs, text="  Meus testes  ")
        self.painel_ciclos = PainelCiclos(self.abas, lambda: self.cfg.pasta_base, self._novo_ciclo, self._gerar_roteiro,
                                          self._ver_roteiro, self._salvar_pdf_roteiro, self._gerar_roteiro_manual,
                                          self._cancelar_geracao, self._revogar_autorizacao)
        self.abas.add(self.painel_ciclos, text="  Ciclos  ")
        self.abas.bind("<<NotebookTabChanged>>", lambda _e: (self.painel_pdfs.atualizar(), self.painel_ciclos.atualizar()))

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
        """Aviso de teste finalizado com os próximos passos (criar o ciclo, gerar o relatório ou abrir a pasta)."""
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

        estilo.botao_primario(botoes, "Criar ciclo de testes", lambda: fechar("ciclo")).pack(side="left")
        ttk.Button(botoes, text="Gerar relatório", command=lambda: fechar("relatorio")).pack(side="left", padx=(10, 0))
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
        elif acao == "relatorio":
            self._gerar_relatorios([pasta])
        elif acao == "ciclo":
            self._criar_ciclo_automatico([pasta])

    def _analisar_varios_manual(self, pastas: list[Path]) -> None:
        """Plano B: abre a janela do prompt (e o Claude desktop) para os testes escolhidos em Meus testes."""
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
            usada = abrir_dialogo_prompt(self.raiz, [t.pasta for t in testes], self.cfg.pasta_base)
        except ValueError as exc:
            messagebox.showwarning("Não foi possível preparar o envio", str(exc), parent=self.raiz)
            return
        self._lembrar_pasta(usada)

    # --- ciclos de teste ----------------------------------------------
    def _criar_ciclo_automatico(self, pastas: list[Path]) -> None:
        """Cria o ciclo só com as telas (nome, objetivo, escopo e critérios ficam por conta do Claude) e já pede o roteiro."""
        try:
            ciclo, ignorados = fluxo_ciclo.criar_a_partir_de_testes(self.cfg.pasta_base, pastas)
        except (ValueError, OSError) as exc:
            messagebox.showwarning("Não foi possível criar o ciclo", str(exc), parent=self.raiz)
            return
        self._ciclo_criado(ciclo, ignorados)

    def _novo_ciclo(self) -> None:
        """Abre a janela de novo ciclo (para escolher várias telas ou ajustar parâmetros) e pede o roteiro."""
        resultado = abrir_dialogo_ciclo(self.raiz, self.cfg.pasta_base, (), self.cfg.testador)
        if resultado is not None:
            self._ciclo_criado(*resultado)

    def _ciclo_criado(self, ciclo, ignorados: list[tuple[str, str]]) -> None:
        if ignorados:
            lista = "\n".join(f"• {nome}" for nome, _motivo in ignorados)
            messagebox.showinfo("Testes ignorados", "Estes testes não têm imagens para servir de referência e ficaram "
                                f"de fora do ciclo:\n\n{lista}", parent=self.raiz)
        self.abas.select(self.painel_ciclos)
        self.painel_ciclos.selecionar(ciclo.pasta)
        self._gerar_roteiro(ciclo)

    def _acompanhar(self, chave, texto: str, status) -> None:
        """Mostra `texto` na linha de status com o tempo decorrido, de segundo em segundo, até `chave` sair de `_andamento`.

        Sem isso o app fica mudo por um ou dois minutos e parece travado.
        """
        self._andamento[chave] = texto
        inicio = time.monotonic()

        def tique() -> None:
            if chave not in self._andamento:
                return
            segundos = int(time.monotonic() - inicio)
            status(f"{self._andamento[chave]}  ·  {segundos // 60}:{segundos % 60:02d}")
            self.raiz.after(1000, tique)

        tique()

    def _pronto_para_ia(self, status, telas: int, o_que: str, retomar) -> Path | None:
        """Confere o Claude Code, a autorização e o login. Devolve o executável, ou None (com a explicação em `status`).

        `retomar` refaz o pedido do usuário: se faltar o login, o app o oferece e, quando termina, continua sozinho.
        """
        exe = ia_local.localizar_claude()
        if exe is None:
            status("Não achei o Claude Code neste computador (ele vem junto com o Claude desktop: abra o Claude desktop "
                   "uma vez e tente de novo). Em Mais ▾ há o pedido manual no Claude desktop.")
            return None
        if not self._autorizou_envio(telas, o_que):
            status("Não enviado: sem a autorização para mandar as telas ao Claude. Em Mais ▾ há o pedido manual "
                   "no Claude desktop.")
            return None
        if not ia_local.esta_logado(exe):
            self._oferecer_login(exe, status, retomar)
            return None
        return exe

    def _gerar_roteiro(self, ciclo) -> None:
        """Gera o roteiro SOZINHO: o app chama o Claude Code deste computador, valida o que volta e grava."""
        painel = self.painel_ciclos
        if ciclo.pasta in self._gerando:
            painel.var_status.set("O roteiro deste ciclo já está sendo gerado.")
            return
        testes, _ = fluxo_ciclo.testes_de_referencia(ciclo, self.cfg.pasta_base)
        telas = min(ia_local.MAX_IMAGENS, sum(len(t.evidencias) for t in testes))
        exe = self._pronto_para_ia(painel.var_status.set, telas, "os dados do ciclo (nome, objetivo, escopo)",
                                   lambda: self._gerar_roteiro(ciclo))
        if exe is None:
            return
        controle = ia_local.Controle()
        self._gerando[ciclo.pasta] = controle
        painel.marcar_gerando(ciclo.pasta, True)
        self._acompanhar(ciclo.pasta, f"O Claude está montando o roteiro de “{ciclo.nome}”… o app continua livre "
                         "para capturar", painel.var_status.set)
        base = self.cfg.pasta_base

        def trabalho() -> None:  # thread: nada de Tk aqui, só devolve o resultado pela fila
            try:
                _, casos = ia_local.gerar_roteiro(ciclo, base, exe, controle)
                self._fila_ia.put(("roteiro", "ok", ciclo, casos, ""))
            except ia_local.Cancelado:
                self._fila_ia.put(("roteiro", "cancelado", ciclo, 0, ""))
            except ia_local.NaoLogado as exc:
                self._fila_ia.put(("roteiro", "nao_logado", ciclo, 0, str(exc)))
            except ia_local.ErroIA as exc:
                self._fila_ia.put(("roteiro", "erro", ciclo, 0, str(exc)))
            except Exception as exc:  # noqa: BLE001 - qualquer falha precisa chegar ao usuário, não morrer na thread
                log.exception("Falha inesperada ao gerar o roteiro")
                self._fila_ia.put(("roteiro", "erro", ciclo, 0, f"Falha inesperada: {exc}"))

        threading.Thread(target=trabalho, daemon=True, name="gerar-roteiro").start()

    # --- relatório de execução: o app chama o Claude sozinho e grava o PDF na pasta do teste
    def _status_relatorio(self, texto: str) -> None:
        self.painel_pdfs.mensagem(texto)
        self._status(texto)

    def _gerar_relatorios(self, pastas: list[Path]) -> None:
        """Gera SOZINHO o relatório em PDF de cada teste, um de cada vez; o usuário só vê o andamento e o resultado."""
        if self._lote is not None:
            self._status_relatorio("Já há relatórios sendo gerados.")
            return
        if len(pastas) > MAX_TESTES:
            messagebox.showwarning("Testes demais", f"Selecione no máximo {MAX_TESTES} testes por vez "
                                   f"(foram {len(pastas)}).", parent=self.raiz)
            return
        testes, ignorados = ler_testes(pastas)
        if ignorados:
            lista = "\n".join(f"• {nome}" for nome, _motivo in ignorados)
            messagebox.showinfo(
                "Testes ignorados",
                "Estes testes não têm imagens de evidência que o Claude possa analisar (ou o registro "
                f"evidencias.json está inválido), então ficaram de fora:\n\n{lista}", parent=self.raiz)
        if not testes:
            return
        telas = min(ia_local.MAX_IMAGENS, sum(len(t.evidencias) for t in testes))
        exe = self._pronto_para_ia(self._status_relatorio, telas, "o nome, o testador e as datas dos testes",
                                   lambda: self._gerar_relatorios(pastas))
        if exe is None:
            return
        controle = ia_local.Controle()
        self._lote = {"controle": controle, "pendentes": {t.pasta for t in testes}, "prontos": 0, "falhas": [],
                      "nao_logado": False, "total": len(testes)}
        self.painel_pdfs.marcar_gerando(self._lote["pendentes"])
        self._acompanhar("relatorios", f"O Claude está analisando {'o teste' if len(testes) == 1 else f'{len(testes)} testes'}…"
                         " o app continua livre para capturar", self._status_relatorio)
        base = self.cfg.pasta_base

        def trabalho() -> None:  # thread: nada de Tk aqui, só devolve o resultado pela fila
            for i, teste in enumerate(testes, 1):
                if controle.cancelado:
                    break
                self._fila_ia.put(("relatorio", "andamento", teste, i, ""))
                try:
                    dados = ia_local.gerar_relatorio(teste.pasta, base, exe, controle)
                    self._fila_ia.put(("relatorio", "ok", teste, dados, ""))
                except ia_local.Cancelado:
                    break
                except ia_local.NaoLogado as exc:
                    # o login caiu no meio: volta com este teste e os que faltavam
                    self._fila_ia.put(("relatorio", "nao_logado", teste, [t.pasta for t in testes[i - 1:]], str(exc)))
                    break
                except ia_local.ErroIA as exc:
                    self._fila_ia.put(("relatorio", "erro", teste, None, str(exc)))
                except Exception as exc:  # noqa: BLE001 - qualquer falha precisa chegar ao usuário, não morrer na thread
                    log.exception("Falha inesperada ao gerar o relatório")
                    self._fila_ia.put(("relatorio", "erro", teste, None, f"Falha inesperada: {exc}"))
            self._fila_ia.put(("relatorio", "fim", None, None, ""))

        threading.Thread(target=trabalho, daemon=True, name="gerar-relatorio").start()

    def _cancelar_relatorios(self) -> None:
        if self._lote is not None:
            self._lote["controle"].cancelar()
            self._andamento["relatorios"] = "Cancelando a geração do relatório…"
            self._status_relatorio("Cancelando a geração do relatório…")

    def _autorizou_envio(self, telas: int, o_que: str) -> bool:
        """Pede (uma vez) a autorização de enviar as telas ao Claude; a resposta fica salva."""
        if self.cfg.autorizou_envio_ia:
            return True
        if not messagebox.askyesno(
                "Enviar as telas ao Claude?",
                "Para montar o roteiro e o relatório sozinho, o app vai enviar ao Claude, pela sua conta no Claude Code "
                f"deste computador:\n\n• as telas dos testes ({telas} imagens, reduzidas)\n• {o_que}\n\n"
                "Elas saem do computador. Confirme que as telas não têm dados pessoais ou sensíveis e que o uso do "
                "Claude é aprovado pela empresa.\n\nA autorização fica salva (vale para os roteiros e para os "
                "relatórios); dá para revogá-la em Mais ▾ na aba Ciclos.\n\nAutorizar?",
                icon="warning", default="no", parent=self.raiz):
            return False
        self.cfg = replace(self.cfg, autorizou_envio_ia=datetime.now().isoformat(timespec="seconds"))
        config.salvar(self.cfg)
        return True

    def _revogar_autorizacao(self) -> None:
        self.cfg = replace(self.cfg, autorizou_envio_ia="")
        config.salvar(self.cfg)
        self.painel_ciclos.var_status.set("Autorização revogada: da próxima vez o app volta a perguntar antes de enviar telas.")

    def _oferecer_login(self, exe, status, retomar=None) -> None:
        """Oferece conectar ao Claude; quando o login termina, o app confere a conta e continua o pedido sozinho."""
        if messagebox.askyesno(
                "Conectar ao Claude",
                "Para gerar o roteiro e o relatório sozinho o app usa o Claude Code instalado neste computador, que "
                "ainda não está conectado à sua conta do Claude.\n\nConectar agora? Abre uma janela e o navegador para "
                "o senhor entrar (é uma vez só).", parent=self.raiz):
            try:
                processo = ia_local.abrir_login(exe)
            except OSError as exc:
                messagebox.showerror("Não foi possível abrir o login", str(exc), parent=self.raiz)
                return
            status("Termine o login no navegador (use a conta da empresa); o app continua sozinho quando terminar.")

            def esperar() -> None:  # thread: só espera e devolve o resultado pela fila
                self._fila_ia.put(("login", "", retomar, (status, ia_local.esperar_login(processo, exe)), ""))

            threading.Thread(target=esperar, daemon=True, name="esperar-login").start()
        else:
            status("Sem a conexão a geração automática não funciona. Em Mais ▾ há o pedido manual no Claude desktop.")

    def _processar_fila_ia(self) -> None:
        self.raiz.after(500, self._processar_fila_ia)
        try:
            while True:
                tipo, resultado, objeto, valor, mensagem = self._fila_ia.get_nowait()
                if tipo == "roteiro":
                    self._resultado_roteiro(resultado, objeto, valor, mensagem)
                elif tipo == "login":
                    self._resultado_login(objeto, *valor)
                else:
                    self._resultado_relatorio(resultado, objeto, valor, mensagem)
        except queue.Empty:
            pass

    def _avisar_pronto(self, texto: str) -> None:
        try:
            mostrar_aviso(self.raiz, texto, (0, 0, self.raiz.winfo_screenwidth(), self.raiz.winfo_screenheight()))
        except tk.TclError:
            pass

    def _resultado_login(self, retomar, status, conta: dict) -> None:
        """O login terminou: mostra em que conta ficou e continua o que o usuário tinha pedido."""
        if not conta:
            status("Não consegui confirmar a conexão ao Claude. Peça de novo para tentar outra vez.")
            return
        quem = conta.get("email") or "a sua conta"
        status(f"Conectado ao Claude como {quem}. Continuando…")
        if retomar is not None:
            retomar()

    def _resultado_roteiro(self, resultado: str, ciclo, casos: int, mensagem: str) -> None:
        self._gerando.pop(ciclo.pasta, None)
        self._andamento.pop(ciclo.pasta, None)
        self.painel_ciclos.marcar_gerando(ciclo.pasta, False)
        painel = self.painel_ciclos
        if resultado == "ok":
            painel.var_status.set(f"Roteiro pronto: {casos} {'caso' if casos == 1 else 'casos'} em “{ciclo.nome}”.")
            self._avisar_pronto(f"Roteiro pronto: {casos} casos")
        elif resultado == "cancelado":
            painel.var_status.set("Geração do roteiro cancelada.")
        elif resultado == "nao_logado":
            exe = ia_local.localizar_claude()
            if exe is not None:
                self._oferecer_login(exe, painel.var_status.set, lambda: self._gerar_roteiro(ciclo))
        else:
            painel.var_status.set("Não foi possível gerar o roteiro.")
            messagebox.showwarning(
                "Não foi possível gerar o roteiro", f"{mensagem}\n\nO senhor pode tentar de novo ou pedir o "
                "roteiro no Claude desktop (Mais ▾ na aba Ciclos).", parent=self.raiz)

    def _resultado_relatorio(self, resultado: str, teste, valor, mensagem: str) -> None:
        lote = self._lote
        if lote is None:
            return
        if resultado == "andamento":
            if lote["total"] > 1 and "relatorios" in self._andamento and not lote["controle"].cancelado:
                self._andamento["relatorios"] = f"O Claude está analisando o teste {valor} de {lote['total']}: {teste.nome_teste}…"
            return
        if resultado in ("ok", "erro", "nao_logado"):
            lote["pendentes"].discard(teste.pasta)
            self.painel_pdfs.marcar_gerando(lote["pendentes"])
            if resultado == "ok":
                lote["prontos"] += 1
                self.painel_pdfs.atualizar()
            elif resultado == "nao_logado":
                lote["nao_logado"] = valor  # as pastas que ainda faltam, para retomar depois do login
            else:
                lote["falhas"].append((teste.nome_teste, mensagem))
            return
        # "fim": a thread terminou (acabou, foi cancelada ou parou por falta de login)
        self._lote = None
        self._andamento.pop("relatorios", None)
        self.painel_pdfs.marcar_gerando(frozenset())
        self.painel_pdfs.atualizar()
        prontos, falhas = lote["prontos"], lote["falhas"]
        cancelado = lote["controle"].cancelado
        if lote["nao_logado"]:
            exe = ia_local.localizar_claude()
            if exe is not None:
                faltam = lote["nao_logado"]
                self._oferecer_login(exe, self._status_relatorio, lambda: self._gerar_relatorios(faltam))
            return
        if prontos:
            self._status_relatorio(f"{prontos} {'relatório pronto' if prontos == 1 else 'relatórios prontos'} em "
                                   "Meus testes." + (" Cancelado antes de terminar os demais." if cancelado else ""))
            self._avisar_pronto("Relatório pronto" if prontos == 1 else f"{prontos} relatórios prontos")
        elif cancelado:
            self._status_relatorio("Geração do relatório cancelada.")
        if falhas:
            if not prontos and not cancelado:
                self._status_relatorio("Não foi possível gerar o relatório.")
            detalhe = "\n".join(f"• {nome}: {motivo}" for nome, motivo in falhas)
            messagebox.showwarning(
                "Não foi possível gerar o relatório",
                f"{detalhe}\n\nO senhor pode tentar de novo ou pedir a análise no Claude desktop (Mais ▾ em Meus testes).",
                parent=self.raiz)

    def _cancelar_geracao(self, ciclo) -> None:
        controle = self._gerando.get(ciclo.pasta)
        if controle is not None:
            controle.cancelar()
            self._andamento[ciclo.pasta] = "Cancelando a geração do roteiro…"
            self.painel_ciclos.var_status.set("Cancelando a geração do roteiro…")

    def _gerar_roteiro_manual(self, ciclo) -> None:
        """Plano B, só por escolha do usuário (Mais ▾): abre o Claude desktop com o pedido do roteiro preenchido."""
        painel = self.painel_ciclos
        problemas = extensao_claude.avisos(ciclo.pasta.parent, exigir_ferramenta="salvar_casos")
        if problemas and not messagebox.askyesno(
                "A extensão não está pronta", "\n\n".join(problemas) + "\n\nPedir o roteiro ao Claude mesmo assim? "
                "(Ele provavelmente não conseguirá gravar os casos.)", icon="warning", default="no", parent=self.raiz):
            painel.var_status.set("Roteiro não pedido: ajuste a extensão e use “Gerar roteiro com o Claude”.")
            return
        try:
            pedido = fluxo_ciclo.montar_pedido(ciclo, self.cfg.pasta_base)
        except ValueError as exc:
            messagebox.showwarning("Não foi possível montar o pedido", str(exc), parent=self.raiz)
            return
        painel.var_status.set("Abrindo o Claude…")
        self.raiz.update_idletasks()
        resultado = claude_desktop.abrir_conversa(pedido)
        if resultado == claude_desktop.PREENCHIDO:
            painel.var_status.set("O Claude abriu com o pedido do roteiro preenchido: aperte Enter. Quando ele terminar, "
                                  "os casos aparecem aqui sozinhos (confira o status em “Roteiro”).")
            return
        self.raiz.clipboard_clear()
        self.raiz.clipboard_append(pedido)
        self.raiz.update()
        painel.var_status.set(
            "O pedido é grande demais para ir no link: o Claude abriu em branco e o texto está copiado, cole com Ctrl+V."
            if resultado == claude_desktop.VAZIA else
            "Não consegui abrir o Claude desktop. O pedido foi copiado: abra o Claude e cole com Ctrl+V.")

    def _ver_roteiro(self, ciclo) -> None:
        try:
            abrir_visualizador(self.raiz, ciclo, lambda: self._gerar_roteiro(ciclo), lambda: self._salvar_pdf_roteiro(ciclo))
        except ValueError as exc:
            messagebox.showinfo("Roteiro", str(exc), parent=self.raiz)

    def _salvar_pdf_roteiro(self, ciclo) -> None:
        roteiro = ciclos.ler_roteiro_mais_recente(ciclo.pasta)
        if roteiro is None:
            messagebox.showinfo("Roteiro", "Este ciclo ainda não tem roteiro.", parent=self.raiz)
            return
        try:
            caminho = roteiro_md.gerar_pdf_do_roteiro(ciclo, roteiro)
            os.startfile(caminho)
        except Exception as exc:  # noqa: BLE001 - qualquer falha de geração deve aparecer ao usuário
            log.exception("Falha ao gerar o PDF do roteiro")
            messagebox.showerror("Erro ao gerar o PDF do roteiro", str(exc), parent=self.raiz)
            return
        self.painel_ciclos.var_status.set(f"PDF do roteiro salvo em: {caminho}")

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
        if self._gerando or self._lote is not None:
            if not messagebox.askyesno("Sair", "O Claude está trabalhando num roteiro ou relatório agora. Sair cancela a "
                                       "geração. Sair mesmo assim?", icon="warning", default="no", parent=self.raiz):
                return
            for controle in self._gerando.values():
                controle.cancelar()
            if self._lote is not None:
                self._lote["controle"].cancelar()
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
