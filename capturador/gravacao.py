"""Grava o relatório (Markdown) em PDF na pasta de um teste, com as imagens ao final.

Usado pelo servidor MCP (a IA grava pelo Claude desktop) e pelo app (relatório automático): nenhum dos dois
confia no que a IA devolve para decidir ONDE gravar, e nenhum arquivo é sobrescrito.
"""
from __future__ import annotations

import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from . import metadados
from .metadados import PastaTeste
from .relatorio_md import EvidenciaPdf, gerar_pdf_de_markdown
from .sessao import nome_seguro

MAX_MARKDOWN = 200_000
MAX_TITULO = 150
MAX_PDFS_POR_TESTE = 100  # teto de gravação: títulos diferentes criam arquivos novos sem limite
AVISO_IA = "Rascunho gerado por IA a partir das evidências. Revisão do testador necessária."
trava_gravacao = threading.Lock()  # uma gravação por vez (o servidor MCP roda as ferramentas em threads)


def e_atalho(caminho: Path) -> bool:
    """Link simbólico ou junction: pasta/arquivo que na verdade aponta para outro lugar."""
    return caminho.is_symlink() or os.path.isjunction(caminho)


def caminho_da_evidencia(dados: PastaTeste, ev: metadados.EvidenciaInfo) -> Path | None:
    """Arquivo da evidência, só se estiver realmente DENTRO da pasta do teste.

    Compara com a pasta JÁ validada (não a recalcula): se ela virar um atalho entre a validação e o
    uso, o `resolve()` seguiria o atalho e as duas pontas apontariam para fora, passando na checagem.
    """
    if e_atalho(dados.pasta):
        return None
    candidato = dados.pasta / ev.arquivo
    if e_atalho(candidato):
        return None
    caminho = candidato.resolve()
    if caminho.parent != dados.pasta or not caminho.is_file():
        return None
    return caminho


def nome_unico(pasta: Path, nome: str) -> str:
    """Nome-base livre para o par .pdf/.md: nenhum dos dois pode existir (nunca sobrescreve)."""
    for n in range(1, 100):
        candidato = nome if n == 1 else f"{nome} ({n})"
        if not (pasta / f"{candidato}.pdf").exists() and not (pasta / f"{candidato}.md").exists():
            return candidato
    raise ValueError("Há arquivos demais com esse nome na pasta do teste; use outro título.")


def gravar_relatorio_pdf(dados: PastaTeste, titulo: str, conteudo_markdown: str, incluir_evidencias: bool = True,
                         max_pdfs: int | None = None) -> dict[str, Any]:
    """Grava `<título>.pdf` e `<título>.md` na pasta do teste `dados` e devolve os dados do que foi gerado.

    `dados` já tem de ter sido validado por quem chama: pasta dentro da pasta de evidências, sem atalhos e já
    RESOLVIDA (`Path.resolve()`), senão as imagens não passam na conferência de caminho e ficam fora do PDF.
    Levanta ValueError, com mensagem para o usuário, se algo não servir. Nunca sobrescreve: (2), (3)…
    """
    titulo = (titulo or "").strip()
    if not titulo or len(titulo) > MAX_TITULO:
        raise ValueError(f"O título é obrigatório e deve ter até {MAX_TITULO} caracteres.")
    if not (conteudo_markdown or "").strip() or len(conteudo_markdown) > MAX_MARKDOWN:
        raise ValueError(f"O conteúdo é obrigatório e deve ter até {MAX_MARKDOWN} caracteres.")
    if not dados.evidencias:
        # a leitura de pastas antigas aceita qualquer pasta com um PDF; para GRAVAR exigimos que seja
        # mesmo um teste deste app, senão uma base apontada para uma pasta ampla receberia arquivos
        raise ValueError("Esta pasta não tem evidências numeradas deste app; por segurança nada é gravado nela.")
    limite = MAX_PDFS_POR_TESTE if max_pdfs is None else max_pdfs

    with trava_gravacao:
        if len(list(dados.pasta.glob("*.pdf"))) >= limite:
            raise ValueError(f"Esta pasta já tem {limite} PDFs; apague os que não servem mais.")
        nome = nome_unico(dados.pasta, nome_seguro(titulo))
        pdf, markdown = dados.pasta / f"{nome}.pdf", dados.pasta / f"{nome}.md"
        # Os dois arquivos são criados em modo EXCLUSIVO ("x"): se o nome existir (inclusive como link
        # físico para um arquivo de fora), a criação falha em vez de sobrescrever.
        # O Markdown vai primeiro: é barato e guarda o trabalho da IA mesmo que o PDF falhe ou demore.
        try:
            with markdown.open("x", encoding="utf-8") as f:
                f.write(conteudo_markdown)
            arquivo_pdf = pdf.open("xb")
        except FileExistsError as exc:
            raise ValueError("Já existe um arquivo com esse nome na pasta do teste; tente de novo.") from exc
        evidencias = []
        if incluir_evidencias:
            for ev in dados.evidencias:
                caminho = caminho_da_evidencia(dados, ev)
                if caminho is not None:
                    evidencias.append(EvidenciaPdf(caminho, ev.rotulo, ev.numero, ev.momento))
        subtitulo = f"Teste: {dados.nome_teste} · gerado em {datetime.now():%d/%m/%Y %H:%M} · {AVISO_IA}"
        try:
            with arquivo_pdf:
                paginas = gerar_pdf_de_markdown(arquivo_pdf, titulo, conteudo_markdown, subtitulo, evidencias)
        except BaseException:
            pdf.unlink(missing_ok=True)  # só o PDF que acabamos de criar; o .md fica com o trabalho da IA
            raise
    return {"teste": dados.pasta.name, "pdf": pdf.name, "markdown": markdown.name, "paginas": paginas,
            "evidencias_anexadas": len(evidencias), "pasta": str(dados.pasta),
            "caminho_pdf": str(pdf), "caminho_markdown": str(markdown)}
