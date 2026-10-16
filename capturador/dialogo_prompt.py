"""Janela "Enviar ao Claude": o essencial à vista (um botão); opções, detalhes e prévia ficam recolhidos."""
from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Sequence

from . import claude_desktop, estilo, extensao_claude, metadados
from .prompt_ia import MAX_TESTES, SAIDAS, Formulario, montar_prompt, montar_prompt_varios

ARQUIVO_PROMPT = "Prompt para IA.txt"
AVISO = ("Antes de enviar, confira se as evidências não têm dados pessoais ou sensíveis e se a ferramenta "
         "de IA é aprovada pela empresa.")
_RESUMO_DA_SAIDA = {"casos": "Casos de teste", "relatorio": "Relatório de execução",
                    "ambos": "Casos de teste e relatório"}


def _campo_texto(pai: tk.Misc, linhas: int) -> tk.Text:
    texto = tk.Text(pai, height=linhas, wrap="word", font=(estilo.FAMILIA, 10), undo=True,
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
    janela.title("Enviar ao Claude" + (f" — {len(testes)} testes" if multiplo else ""))
    janela.minsize(600, 1)
    janela.transient(pai)

    quadro = ttk.Frame(janela, padding=(20, 18, 20, 14))
    quadro.pack(fill="both", expand=True)

    var_titulo = tk.StringVar()
    var_resumo = tk.StringVar()
    var_ambiente = tk.StringVar()
    var_saida = tk.StringVar(value="ambos")
    var_pdf = tk.BooleanVar(value=True)
    var_sugerir = tk.BooleanVar(value=True)
    var_automacao = tk.BooleanVar(value=False)
    var_extensao = tk.BooleanVar(value=True)
    var_aviso_extensao = tk.StringVar()
    var_status = tk.StringVar()

    def reajustar() -> None:
        """Seções recolhidas mudam o tamanho: deixa o Tk recalcular a altura da janela."""
        janela.update_idletasks()
        janela.geometry("")

    secoes: list = []  # (fechar, está_aberta) de cada seção: abrir uma fecha as outras, e a janela não passa de uma tela

    def secao_recolhivel(pai_: tk.Misc, rotulo_fechada: str, rotulo_aberta: str, ao_alternar=None):
        """Devolve (botão que alterna, quadro do conteúdo, função de alternar); o conteúdo começa oculto."""
        conteudo = ttk.Frame(pai_)
        botao = ttk.Button(pai_, text=rotulo_fechada, style="Link.Toolbutton")

        def fechar() -> None:
            conteudo.pack_forget()
            botao.configure(text=rotulo_fechada)
            if ao_alternar:
                ao_alternar()

        def alternar() -> None:
            if conteudo.winfo_manager():
                fechar()
            else:
                for outra_fechar, outra_aberta in secoes:
                    if outra_aberta():
                        outra_fechar()
                conteudo.pack(fill="both", expand=True, pady=(6, 0), after=botao)
                botao.configure(text=rotulo_aberta)
                if ao_alternar:
                    ao_alternar()
            reajustar()

        botao.configure(command=alternar)
        secoes.append((fechar, lambda: bool(conteudo.winfo_manager())))
        return botao, conteudo, alternar

    # --- 1. qual teste (ou quais)
    cabeca = ttk.Frame(quadro)
    cabeca.pack(fill="x")
    ttk.Label(cabeca, textvariable=var_titulo, style="Titulo.TLabel", wraplength=470, justify="left").pack(
        side="left", fill="x", expand=True)
    botao_trocar = None
    if not multiplo:
        botao_trocar = ttk.Button(cabeca, text="Trocar…")
        botao_trocar.pack(side="right", anchor="n")

    # --- 2. o que o Claude vai gerar: uma linha-resumo; o detalhe fica recolhido
    ttk.Label(quadro, text="O Claude vai gerar", style="Secao.TLabel").pack(anchor="w", pady=(16, 0))
    linha_resumo = ttk.Frame(quadro)
    linha_resumo.pack(fill="x")
    ttk.Label(linha_resumo, textvariable=var_resumo, wraplength=540, justify="left").pack(side="left", fill="x",
                                                                                          expand=True)
    sec_opcoes = ttk.Frame(quadro)
    sec_opcoes.pack(fill="x")
    botao_opcoes, opcoes, _ = secao_recolhivel(sec_opcoes, "Alterar ▾", "Ocultar ▴")
    botao_opcoes.pack(anchor="w")
    linha_saida = ttk.Frame(opcoes)
    linha_saida.pack(anchor="w")
    for chave, rotulo in SAIDAS.items():
        ttk.Radiobutton(linha_saida, text=rotulo, value=chave, variable=var_saida).pack(side="left", padx=(0, 14))
    ttk.Checkbutton(opcoes, text="Pedir a entrega em PDF", variable=var_pdf).pack(anchor="w", pady=(4, 0))
    ttk.Checkbutton(opcoes, text="Sugerir casos de teste adicionais (técnicas ISTQB/BSTQB)",
                    variable=var_sugerir).pack(anchor="w", pady=(2, 0))
    ttk.Checkbutton(opcoes, text="Avaliar o que é automatizável e gerar código Playwright (Python)",
                    variable=var_automacao).pack(anchor="w", pady=(2, 0))
    chk_extensao = ttk.Checkbutton(
        opcoes, variable=var_extensao, text="Claude com a extensão instalada (ele lê as evidências direto da pasta)"
        + (" — necessário com vários testes" if multiplo else ""))
    chk_extensao.pack(anchor="w", pady=(2, 0))
    if multiplo:
        var_extensao.set(True)
        chk_extensao.state(["disabled"])  # com anexos não dá para misturar testes: só a extensão lê as pastas

    # --- 3. detalhes do teste (opcional)
    de_todos = " (valem para todos os testes)" if multiplo else ""
    sec_detalhes = ttk.Frame(quadro)
    sec_detalhes.pack(fill="x", pady=(10, 0))
    botao_detalhes, detalhes, _ = secao_recolhivel(sec_detalhes, "Adicionar detalhes do teste ▾",
                                                   "Ocultar detalhes ▴",
                                                   lambda: atualizar_indicador_detalhes())
    botao_detalhes.pack(anchor="w")
    detalhes.columnconfigure(1, weight=1)
    ttk.Label(detalhes, text="Sistema / ambiente").grid(row=0, column=0, sticky="w", pady=(0, 6))
    ttk.Entry(detalhes, textvariable=var_ambiente).grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=(0, 6))
    campos = {}
    for linha, (chave, rotulo, altura) in enumerate((
            ("objetivo", "Objetivo", 2), ("criterios", "Critérios de aceite", 2),
            ("observacoes", "Observações", 2)), start=1):
        ttk.Label(detalhes, text=rotulo).grid(row=linha, column=0, sticky="nw", pady=(0, 6))
        campos[chave] = _campo_texto(detalhes, altura)
        campos[chave].grid(row=linha, column=1, sticky="ew", padx=(10, 0), pady=(0, 6))
    if multiplo:
        ttk.Label(detalhes, text="Os detalhes" + de_todos + ".", style="Suave.TLabel").grid(
            row=4, column=0, columnspan=2, sticky="w")

    # --- 4. avisos (só aparecem quando há algo a avisar)
    aviso_extensao = ttk.Label(quadro, textvariable=var_aviso_extensao, style="Alerta.TLabel", wraplength=560,
                               justify="left")

    # --- 5. ação principal, ação secundária e a prévia recolhida
    rodape = ttk.Frame(quadro)
    rodape.pack(fill="x", pady=(14, 0))
    botao_enviar = estilo.botao_primario(rodape, "Enviar ao Claude", None)
    botao_enviar.pack(side="left")
    botao_copiar = ttk.Button(rodape, text="Copiar prompt")
    botao_copiar.pack(side="left", padx=(10, 0))
    ttk.Button(rodape, text="Fechar", command=janela.destroy).pack(side="right")
    sec_previa = ttk.Frame(quadro)
    sec_previa.pack(fill="x", pady=(8, 0))
    botao_previa, moldura_previa, _ = secao_recolhivel(sec_previa, "Ver o texto que será enviado ▾",
                                                       "Ocultar o texto ▴")
    botao_previa.pack(anchor="w")
    previa = tk.Text(moldura_previa, height=8, wrap="word", font=("Consolas", 9), state="disabled",
                     background="#f5f5f5", relief="solid", borderwidth=1)
    barra = ttk.Scrollbar(moldura_previa, orient="vertical", command=previa.yview)
    previa.configure(yscrollcommand=barra.set)
    previa.pack(side="left", fill="both", expand=True)
    barra.pack(side="right", fill="y")

    ttk.Label(quadro, textvariable=var_status, style="Ok.TLabel", wraplength=560, justify="left").pack(
        anchor="w", pady=(10, 0))
    ttk.Label(quadro, text=AVISO, style="Suave.TLabel", wraplength=560, justify="left").pack(anchor="w", pady=(8, 0))

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
            automacao=var_automacao.get(),
            via_mcp=var_extensao.get(),
        )

    def prompt_atual() -> str:
        if multiplo:
            return montar_prompt_varios(estado["testes"], formulario())
        return montar_prompt(estado["teste"], formulario())

    def atualizar_resumo(*_args) -> None:
        partes = [_RESUMO_DA_SAIDA.get(var_saida.get(), _RESUMO_DA_SAIDA["ambos"])]
        if var_pdf.get():
            partes.append("entrega em PDF")
        if var_sugerir.get():
            partes.append("casos sugeridos")
        if var_automacao.get():
            partes.append("avaliação de automação")
        partes.append("lendo pela extensão" if var_extensao.get() else "com anexos")
        var_resumo.set(" · ".join(partes))

    def atualizar_indicador_detalhes(*_args) -> None:
        preenchido = bool(var_ambiente.get().strip() or any(c.get("1.0", "end").strip() for c in campos.values()))
        aberto = bool(detalhes.winfo_manager())
        if aberto:
            botao_detalhes.configure(text="Ocultar detalhes ▴")
        else:
            botao_detalhes.configure(text="Detalhes do teste: preenchidos (editar) ▾" if preenchido
                                     else "Adicionar detalhes do teste ▾")

    def problemas_da_extensao() -> list[str]:
        """O que impediria o Claude de ler o(s) teste(s) pela extensão (vazio se a caixa está desmarcada)."""
        if not var_extensao.get():
            return []
        achados: list[str] = []
        for teste in estado["testes"]:
            achados.extend(extensao_claude.avisos(teste.pasta))
        return list(dict.fromkeys(achados))  # o mesmo aviso não se repete para cada teste

    def atualizar_aviso_extensao(*_args) -> None:
        texto = "\n".join(f"⚠ {p}" for p in problemas_da_extensao())
        var_aviso_extensao.set(texto)
        if texto and not aviso_extensao.winfo_manager():
            aviso_extensao.pack(anchor="w", pady=(10, 0), before=rodape)
        elif not texto and aviso_extensao.winfo_manager():
            aviso_extensao.pack_forget()
        reajustar()

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
        atualizar_indicador_detalhes()

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
            gravacoes = len(estado["testes"]) * (2 if var_sugerir.get() else 1)  # relatório + sugestões
            pedidos = (f" Ele pode pedir permissão para gravar cada um dos {gravacoes} PDFs."
                       if var_pdf.get() and (multiplo or var_sugerir.get()) else "")
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
            estado["teste"] = estado["testes"][0] = metadados.ler(escolhida)
        except ValueError as exc:
            messagebox.showwarning("Pasta inválida", str(exc), parent=janela)
            return
        var_status.set("")
        atualizar_previa()
        atualizar_aviso_extensao()

    if botao_trocar is not None:
        botao_trocar.configure(command=trocar)
    botao_enviar.configure(command=enviar)
    botao_copiar.configure(command=copiar)
    for variavel in (var_saida, var_pdf, var_sugerir, var_automacao, var_extensao):
        variavel.trace_add("write", agendar)
        variavel.trace_add("write", atualizar_resumo)
    var_ambiente.trace_add("write", agendar)
    var_extensao.trace_add("write", atualizar_aviso_extensao)
    for campo in campos.values():
        campo.bind("<KeyRelease>", agendar)

    atualizar_resumo()
    atualizar_previa()
    atualizar_aviso_extensao()
    reajustar()
    janela.focus_force()
    pai.wait_window(janela)
    return estado["teste"].pasta
