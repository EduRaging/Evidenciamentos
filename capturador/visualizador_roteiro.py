"""Janela do roteiro de testes de um ciclo: os casos com seus passos e a definição do ciclo (só leitura)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from . import ciclos, estilo
from .ciclos import Caso, Ciclo, Roteiro

_ORIGEM = {"IA": "  (proposto pela IA)", "padrão": "  (padrão do CTFL)", "usuário": "", "": ""}


def trechos_do_caso(caso: Caso) -> list[tuple[str, str]]:
    """O caso como lista de (texto, estilo) para o campo de detalhe. Estilos: titulo, rotulo, alerta, normal."""
    saida: list[tuple[str, str]] = [(f"{caso.id} — {caso.titulo}\n", "titulo"),
                                    (f"Prioridade {caso.prioridade}  ·  {caso.tecnica}  ·  {caso.tipo}\n", "suave")]
    if caso.a_confirmar:
        saida.append(("Resultado esperado a confirmar: a IA não viu a regra nas telas.\n", "alerta"))
    saida += [("\nObjetivo\n", "rotulo"), (caso.objetivo + "\n", "normal")]
    for rotulo, itens in (("Pré-condições", caso.pre_condicoes), ("Dados de teste", caso.dados_de_teste)):
        if itens:
            saida += [(f"\n{rotulo}\n", "rotulo")] + [(f"•  {i}\n", "normal") for i in itens]
    saida.append(("\nPassos\n", "rotulo"))
    for n, passo in enumerate(caso.passos, 1):
        saida += [(f"{n}.  {passo.acao}\n", "normal"), (f"     Esperado: {passo.resultado_esperado}\n", "suave")]
    for rotulo, itens in (("Pós-condições", caso.pos_condicoes), ("Rastreio", caso.rastreio)):
        if itens:
            saida += [(f"\n{rotulo}\n", "rotulo")] + [(f"•  {i}\n", "normal") for i in itens]
    if caso.evidencias_base:
        saida += [("\nTelas de referência\n", "rotulo")] + [
            (f"•  {e['teste']} (evidência {e['numero']})\n", "normal") for e in caso.evidencias_base]
    return saida


def trechos_do_ciclo(ciclo: Ciclo, roteiro: Roteiro) -> list[tuple[str, str]]:
    """A definição do ciclo (o que o usuário preencheu, o que a IA propôs e o padrão) em trechos."""
    ef = ciclos.definicao_efetiva(ciclo, roteiro)
    origem = ef["origem"]
    saida: list[tuple[str, str]] = [(f"{ciclo.nome}\n", "titulo"),
                                    (f"{ciclo.tipo}  ·  {ef['sistema'] or 'sistema não informado'}"
                                     f"{'  ·  versão ' + ciclo.versao_sistema if ciclo.versao_sistema else ''}"
                                     f"{'  ·  ' + ef['ambiente'] if ef['ambiente'] else ''}\n", "suave")]

    def bloco(rotulo: str, chave: str, lista: bool) -> None:
        valor = ef[chave]
        if not valor:
            return
        saida.append((f"\n{rotulo}{_ORIGEM[origem[chave]]}\n", "rotulo"))
        saida.extend([(f"•  {i}\n", "normal") for i in valor] if lista else [(valor + "\n", "normal")])

    bloco("Objetivo", "objetivo", False)
    bloco("Escopo", "escopo", True)
    bloco("Fora do escopo", "fora_do_escopo", False)
    bloco("Riscos", "riscos", False)
    bloco("Critérios de entrada", "criterios_entrada", True)
    bloco("Critérios de saída", "criterios_saida", True)
    if roteiro.observacoes:
        saida += [("\nDúvidas e hipóteses a confirmar\n", "rotulo")] + [(f"•  {o}\n", "normal") for o in roteiro.observacoes]
    return saida


def _escrever(campo: tk.Text, trechos: list[tuple[str, str]]) -> None:
    campo.configure(state="normal")
    campo.delete("1.0", "end")
    for texto, estilo_ in trechos:
        campo.insert("end", texto, estilo_)
    campo.configure(state="disabled")


def _campo_somente_leitura(pai: tk.Misc, altura: int) -> tk.Text:
    campo = tk.Text(pai, height=altura, wrap="word", font=(estilo.FAMILIA, 10), relief="solid", borderwidth=1,
                    state="disabled", padx=10, pady=8)
    campo.tag_configure("titulo", font=(estilo.FAMILIA, 12, "bold"))
    campo.tag_configure("rotulo", font=(estilo.FAMILIA, 10, "bold"))
    campo.tag_configure("suave", foreground=estilo.COR_SUAVE)
    campo.tag_configure("alerta", foreground=estilo.COR_ALERTA)
    return campo


def abrir_visualizador(pai: tk.Misc, ciclo: Ciclo, ao_gerar_de_novo: Callable[[], None] | None = None,
                       ao_salvar_pdf: Callable[[], None] | None = None) -> None:
    """Mostra o roteiro mais recente do ciclo. ValueError se ele ainda não tem roteiro."""
    roteiro = ciclos.ler_roteiro_mais_recente(ciclo.pasta)
    if roteiro is None:
        raise ValueError("Este ciclo ainda não tem roteiro. Gere o roteiro com o Claude primeiro.")

    janela = tk.Toplevel(pai)
    janela.title(f"Roteiro — {ciclo.nome}")
    janela.geometry("820x640")
    janela.minsize(680, 520)
    janela.transient(pai)
    quadro = ttk.Frame(janela, padding=(18, 16, 18, 12))
    quadro.pack(fill="both", expand=True)

    prioridades = {p: sum(1 for c in roteiro.casos if c.prioridade == p) for p in ciclos.PRIORIDADES}
    resumo = "  ·  ".join(f"{n} {p}" for p, n in prioridades.items() if n)
    ttk.Label(quadro, text=ciclo.nome, style="Titulo.TLabel", wraplength=760, justify="left").pack(anchor="w")
    ttk.Label(quadro, text=f"{len(roteiro.casos)} casos ({resumo})  ·  roteiro nº {roteiro.numero}  ·  rascunho da IA: "
                           "revise antes de executar", style="Suave.TLabel", wraplength=760,
              justify="left").pack(anchor="w", pady=(2, 8))

    rodape = ttk.Frame(quadro)
    rodape.pack(fill="x", side="bottom", pady=(10, 0))
    if ao_salvar_pdf:
        estilo.botao_primario(rodape, "Salvar o roteiro em PDF", ao_salvar_pdf).pack(side="left")
    if ao_gerar_de_novo:
        ttk.Button(rodape, text="Gerar de novo com o Claude", command=ao_gerar_de_novo).pack(side="left", padx=(10, 0))
    ttk.Button(rodape, text="Fechar", command=janela.destroy).pack(side="right")

    abas = ttk.Notebook(quadro)
    abas.pack(fill="both", expand=True)
    aba_casos = ttk.Frame(abas, padding=(0, 8, 0, 0))
    aba_ciclo = ttk.Frame(abas, padding=(0, 8, 0, 0))
    abas.add(aba_casos, text="  Casos  ")
    abas.add(aba_ciclo, text="  Ciclo e critérios  ")

    divisao = ttk.PanedWindow(aba_casos, orient="vertical")
    divisao.pack(fill="both", expand=True)
    topo = ttk.Frame(divisao)
    arvore = ttk.Treeview(topo, columns=("id", "titulo", "prioridade", "tecnica", "passos"), show="headings",
                          selectmode="browse", height=8, style="Tabela.Treeview")
    for coluna, titulo, largura, ancora, estica in (
            ("id", "ID", 56, "w", False), ("titulo", "Caso", 260, "w", True), ("prioridade", "Prioridade", 92, "center", False),
            ("tecnica", "Técnica", 200, "w", False), ("passos", "Passos", 60, "center", False)):
        arvore.heading(coluna, text=titulo)
        arvore.column(coluna, width=largura, anchor=ancora, stretch=estica)
    barra = ttk.Scrollbar(topo, orient="vertical", command=arvore.yview)
    arvore.configure(yscrollcommand=barra.set)
    arvore.pack(side="left", fill="both", expand=True)
    barra.pack(side="right", fill="y")
    for i, c in enumerate(roteiro.casos):
        arvore.insert("", "end", iid=str(i), values=(c.id, c.titulo, c.prioridade, c.tecnica, len(c.passos)))
    baixo = ttk.Frame(divisao)
    detalhe = _campo_somente_leitura(baixo, 12)
    barra_detalhe = ttk.Scrollbar(baixo, orient="vertical", command=detalhe.yview)
    detalhe.configure(yscrollcommand=barra_detalhe.set)
    detalhe.pack(side="left", fill="both", expand=True)
    barra_detalhe.pack(side="right", fill="y")
    divisao.add(topo, weight=1)
    divisao.add(baixo, weight=2)

    def mostrar_caso(*_args) -> None:
        marcado = arvore.selection()
        if marcado:
            _escrever(detalhe, trechos_do_caso(roteiro.casos[int(marcado[0])]))

    arvore.bind("<<TreeviewSelect>>", mostrar_caso)
    arvore.selection_set("0")

    texto_ciclo = _campo_somente_leitura(aba_ciclo, 12)
    barra_ciclo = ttk.Scrollbar(aba_ciclo, orient="vertical", command=texto_ciclo.yview)
    texto_ciclo.configure(yscrollcommand=barra_ciclo.set)
    texto_ciclo.pack(side="left", fill="both", expand=True)
    barra_ciclo.pack(side="right", fill="y")
    _escrever(texto_ciclo, trechos_do_ciclo(ciclo, roteiro))

    janela.focus_force()
