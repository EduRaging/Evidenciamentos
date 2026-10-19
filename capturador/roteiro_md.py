"""Roteiro de testes do ciclo em Markdown e em PDF (gerado pelo app a partir do JSON, não pela IA)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .ciclos import Caso, Ciclo, Roteiro, definicao_efetiva
from .relatorio_md import gerar_pdf_de_markdown
from .sessao import nome_seguro

_ORIGEM = {"IA": " *(proposto pela IA)*", "padrão": " *(padrão do CTFL)*", "usuário": "", "": ""}


def _c(texto) -> str:
    """Texto para uma célula de tabela: a barra vertical separa colunas e não pode aparecer no texto."""
    return str(texto).replace("|", "/").replace("\n", " ").strip()


def _lista(itens) -> str:
    return "\n".join(f"- {i}" for i in itens) if itens else "- (nenhum)"


def _periodo(ciclo: Ciclo) -> str:
    if ciclo.inicio and ciclo.fim:
        return f"{ciclo.inicio} a {ciclo.fim}"
    return ciclo.inicio or ciclo.fim or "não informado"


def _caso(c: Caso) -> str:
    linhas = [f"### {c.id} — {c.titulo}",
              f"**Prioridade:** {c.prioridade} · **Técnica:** {c.tecnica} · **Tipo:** {c.tipo}"
              + (" · **Resultado esperado a confirmar**" if c.a_confirmar else ""),
              f"**Objetivo:** {c.objetivo}"]
    if c.pre_condicoes:
        linhas += ["**Pré-condições:**", _lista(c.pre_condicoes)]
    if c.dados_de_teste:
        linhas += ["**Dados de teste:**", _lista(c.dados_de_teste)]
    linhas += ["| # | Ação | Resultado esperado |", "|---|---|---|"]
    linhas += [f"| {i} | {_c(p.acao)} | {_c(p.resultado_esperado)} |" for i, p in enumerate(c.passos, 1)]
    if c.pos_condicoes:
        linhas += ["**Pós-condições:**", _lista(c.pos_condicoes)]
    if c.rastreio:
        linhas.append("**Rastreio:** " + "; ".join(c.rastreio))
    if c.evidencias_base:
        linhas.append("**Evidências de referência:** " + "; ".join(
            f"{e['teste']} (evidência {e['numero']})" for e in c.evidencias_base))
    return "\n".join(linhas)


def roteiro_para_markdown(ciclo: Ciclo, roteiro: Roteiro) -> str:
    """O roteiro inteiro em Markdown: ciclo, critérios, resumo dos casos e cada caso com seus passos."""
    ef = definicao_efetiva(ciclo, roteiro)
    origem = ef["origem"]
    prioridades: dict[str, int] = {}
    for c in roteiro.casos:
        prioridades[c.prioridade] = prioridades.get(c.prioridade, 0) + 1
    resumo_prioridades = ", ".join(f"{prioridades[p]} {p}" for p in ("Alta", "Média", "Baixa") if p in prioridades)
    partes = [
        "## Ciclo",
        "| Campo | Valor |\n|---|---|\n"
        f"| Rodada | {_c(ciclo.nome)} |\n| Tipo | {_c(ciclo.tipo)} |\n"
        f"| Sistema | {_c(ef['sistema'] or 'não informado')} |\n| Versão | {_c(ciclo.versao_sistema or 'não informada')} |\n"
        f"| Ambiente | {_c(ef['ambiente'] or 'não informado')} |\n| Período | {_c(_periodo(ciclo))} |\n"
        f"| Testador | {_c(ciclo.testador or 'não informado')} |\n| Casos | {len(roteiro.casos)} ({resumo_prioridades}) |",
        f"**Objetivo:**{_ORIGEM[origem['objetivo']]} {ef['objetivo'] or 'não informado'}",
        f"**Escopo:**{_ORIGEM[origem['escopo']]}\n{_lista(ef['escopo'])}",
    ]
    if ef["fora_do_escopo"]:
        partes.append(f"**Fora do escopo:**{_ORIGEM[origem['fora_do_escopo']]} {ef['fora_do_escopo']}")
    if ef["riscos"]:
        partes.append(f"**Riscos:**{_ORIGEM[origem['riscos']]} {ef['riscos']}")
    partes += [f"## Critérios de entrada{_ORIGEM[origem['criterios_entrada']]}", _lista(ef["criterios_entrada"]),
               f"## Critérios de saída{_ORIGEM[origem['criterios_saida']]}", _lista(ef["criterios_saida"]),
               "## Resumo dos casos",
               "| ID | Caso | Técnica | Prioridade | Passos |\n|---|---|---|---|---|\n"
               + "\n".join(f"| {c.id} | {_c(c.titulo)} | {_c(c.tecnica)} | {c.prioridade} | {len(c.passos)} |"
                           for c in roteiro.casos),
               "## Casos de teste", *[_caso(c) for c in roteiro.casos]]
    if roteiro.observacoes:
        partes += ["## Dúvidas e hipóteses a confirmar", _lista(roteiro.observacoes)]
    return "\n\n".join(partes) + "\n"


def gerar_pdf_do_roteiro(ciclo: Ciclo, roteiro: Roteiro, agora: datetime | None = None) -> Path:
    """Grava `Roteiro de testes - <ciclo>.pdf` na pasta do ciclo (nunca sobrescreve: (2), (3)…). Devolve o caminho."""
    titulo = f"Roteiro de testes - {ciclo.nome}"
    base = nome_seguro(titulo)
    markdown = roteiro_para_markdown(ciclo, roteiro)
    subtitulo = (f"Ciclo: {ciclo.nome} · roteiro nº {roteiro.numero} · gerado em "
                 f"{(agora or datetime.now()):%d/%m/%Y %H:%M} · Rascunho gerado por IA: revisão do testador necessária.")
    for n in range(1, 100):
        destino = ciclo.pasta / (f"{base}.pdf" if n == 1 else f"{base} ({n}).pdf")
        try:
            arquivo = destino.open("xb")
        except FileExistsError:
            continue
        try:
            with arquivo:
                gerar_pdf_de_markdown(arquivo, titulo, markdown, subtitulo, [])
        except BaseException:
            destino.unlink(missing_ok=True)
            raise
        return destino
    raise ValueError("Há arquivos demais com esse nome na pasta do ciclo.")
