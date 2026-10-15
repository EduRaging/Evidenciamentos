"""Servidor MCP (protótipo): deixa uma IA ler as evidências dos testes e salvar o relatório em PDF.

Roda por stdio, iniciado pelo cliente (Claude Desktop, Claude Code...). Nunca escreva na saída
padrão: ela é o canal do protocolo.

Segurança: toda ferramenta recebe só o NOME da pasta do teste, sempre resolvido dentro da pasta
de evidências do app; nada fora dela é lido ou escrito, e nenhum arquivo é sobrescrito.
"""
from __future__ import annotations

import io
import os
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from PIL import Image as PILImage

from . import config, metadados
from .metadados import PastaTeste
from .prompt_ia import SAIDAS, Formulario, montar_prompt
from .relatorio_md import EvidenciaPdf, gerar_pdf_de_markdown
from .sessao import nome_seguro

LADO_MAXIMO = 1568  # px; acima disso a IA reduz a imagem de qualquer jeito e o custo só sobe
MAX_MARKDOWN = 200_000
MAX_TITULO = 150
AVISO_IA = "Rascunho gerado por IA a partir das evidências. Revisão do testador necessária."

INSTRUCOES = (
    "Evidências de testes manuais capturadas pelo Capturador de Evidências. Fluxo: `listar_testes` "
    "para achar o teste; `obter_teste` para ver as evidências; `ver_evidencia` para olhar cada imagem; "
    "`salvar_relatorio_pdf` para gravar o relatório (Markdown) em PDF na pasta do teste. O prompt "
    "`analisar_teste` já traz as instruções completas. Baseie-se só no que as imagens mostram."
)

mcp = MCPServer("capturador-evidencias", instructions=INSTRUCOES, log_level="WARNING")


def _erros_previstos(funcao):
    """Faz as validações (ValueError) chegarem à IA com a mensagem, para ela se corrigir.

    Qualquer outra exceção continua virando um erro genérico no cliente, de propósito: não
    expõe detalhes internos nem caminhos da máquina.
    """
    @wraps(funcao)
    def interna(*args, **kwargs):
        try:
            return funcao(*args, **kwargs)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
    return interna


def _base() -> Path:
    return Path(os.environ.get("CAPTURADOR_PASTA_BASE") or config.carregar().pasta_base)


def _resolver_teste(teste: str) -> PastaTeste:
    """Pasta do teste pelo nome, confinada à pasta de evidências. ValueError se inválida."""
    nome = (teste or "").strip()
    if not nome or nome in (".", "..") or any(c in nome for c in '/\\:\x00'):
        raise ValueError("Informe só o nome da pasta do teste, como aparece em `listar_testes`.")
    base = _base().resolve()
    pasta = (base / nome).resolve()
    if pasta.parent != base or not pasta.is_dir():
        raise ValueError(f"Teste não encontrado: {nome!r}. Use `listar_testes` para ver os disponíveis.")
    return metadados.ler(pasta)


def _evidencia(dados: PastaTeste, numero: int) -> metadados.EvidenciaInfo:
    for ev in dados.evidencias:
        if ev.numero == numero:
            return ev
    raise ValueError(f"Evidência {numero} não existe; este teste tem de 1 a {len(dados.evidencias)}.")


def _arquivo_unico(pasta: Path, base: str, extensao: str) -> Path:
    for n in range(1, 100):
        candidato = pasta / f"{base}{'' if n == 1 else f' ({n})'}{extensao}"
        if not candidato.exists():
            return candidato
    raise OSError("Há arquivos demais com esse nome na pasta do teste.")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
@_erros_previstos
def listar_testes(limite: int = 20) -> list[dict[str, Any]]:
    """Lista os testes finalizados mais recentes. Use o campo `teste` nas outras ferramentas."""
    base = _base()
    achados = []
    if base.is_dir():
        for pasta in base.iterdir():
            if not pasta.is_dir() or pasta.name.startswith(("_", ".")):
                continue
            try:
                dados = metadados.ler(pasta)
            except ValueError:
                continue
            achados.append((pasta.stat().st_mtime, {
                "teste": pasta.name,
                "nome_teste": dados.nome_teste,
                "evidencias": len(dados.evidencias),
                "pdf": dados.pdf,
                "data": datetime.fromtimestamp(pasta.stat().st_mtime).isoformat(timespec="minutes"),
            }))
    achados.sort(key=lambda par: par[0], reverse=True)
    return [item for _, item in achados[:max(1, min(limite, 100))]]


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
@_erros_previstos
def obter_teste(teste: str) -> dict[str, Any]:
    """Dados de um teste: nome, testador e a lista numerada de evidências (tipo e hora)."""
    dados = _resolver_teste(teste)
    return {
        "teste": dados.pasta.name,
        "nome_teste": dados.nome_teste,
        "testador": dados.testador or None,
        "pdf": dados.pdf,
        "evidencias": [
            {"numero": e.numero, "tipo": e.rotulo, "arquivo": e.arquivo,
             "hora": e.momento.isoformat(timespec="seconds") if e.momento else None}
            for e in dados.evidencias
        ],
    }


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
@_erros_previstos
def ver_evidencia(teste: str, numero: int) -> Image:
    """Devolve a imagem da evidência `numero` (1 a N) para você olhar."""
    dados = _resolver_teste(teste)
    ev = _evidencia(dados, numero)
    caminho = (dados.pasta / ev.arquivo).resolve()
    if caminho.parent != dados.pasta.resolve() or not caminho.is_file():
        raise ValueError(f"O arquivo da evidência {numero} não foi encontrado na pasta do teste.")
    with PILImage.open(caminho) as img:
        img = img.convert("RGB")
        img.thumbnail((LADO_MAXIMO, LADO_MAXIMO), PILImage.Resampling.LANCZOS)
        saida = io.BytesIO()
        img.save(saida, "PNG", optimize=True)
    return Image(data=saida.getvalue(), format="png")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                      idempotentHint=False, openWorldHint=False))
@_erros_previstos
def salvar_relatorio_pdf(teste: str, titulo: str, conteudo_markdown: str,
                         incluir_evidencias: bool = True) -> dict[str, Any]:
    """Grava o relatório (Markdown) em PDF na pasta do teste, com as imagens ao final.

    Suporta títulos (#), listas, tabelas com barras verticais, **negrito** e *itálico*.
    Nunca sobrescreve: se o nome já existe, cria outro com (2), (3)...
    """
    dados = _resolver_teste(teste)
    titulo = (titulo or "").strip()
    if not titulo or len(titulo) > MAX_TITULO:
        raise ValueError(f"O título é obrigatório e deve ter até {MAX_TITULO} caracteres.")
    if not (conteudo_markdown or "").strip() or len(conteudo_markdown) > MAX_MARKDOWN:
        raise ValueError(f"O conteúdo é obrigatório e deve ter até {MAX_MARKDOWN} caracteres.")

    pdf = _arquivo_unico(dados.pasta, nome_seguro(titulo), ".pdf")
    evidencias = []
    if incluir_evidencias:
        for ev in dados.evidencias:
            caminho = dados.pasta / ev.arquivo
            if caminho.is_file():
                evidencias.append(EvidenciaPdf(caminho, ev.rotulo, ev.numero, ev.momento))
    subtitulo = (f"Teste: {dados.nome_teste} · gerado em {datetime.now():%d/%m/%Y %H:%M} · {AVISO_IA}")
    paginas = gerar_pdf_de_markdown(pdf, titulo, conteudo_markdown, subtitulo, evidencias)
    markdown = pdf.with_suffix(".md")
    markdown.write_text(conteudo_markdown, encoding="utf-8")
    return {"teste": dados.pasta.name, "pdf": pdf.name, "markdown": markdown.name, "paginas": paginas,
            "evidencias_anexadas": len(evidencias), "pasta": str(dados.pasta)}


@mcp.prompt(title="Analisar teste e gerar o relatório em PDF")
def analisar_teste(teste: str, ambiente: str = "", objetivo: str = "", criterios: str = "",
                   observacoes: str = "", saida: str = "ambos", sugerir_casos: bool = True) -> str:
    """Instruções completas para analisar as evidências de um teste e entregar o PDF."""
    if saida not in SAIDAS:
        raise ValueError(f"`saida` deve ser uma de: {', '.join(SAIDAS)}.")
    return montar_prompt(_resolver_teste(teste), Formulario(
        ambiente=ambiente, objetivo=objetivo, criterios=criterios, observacoes=observacoes,
        saida=saida, entregar_pdf=True, via_mcp=True, sugerir_casos=sugerir_casos))


def executar() -> None:
    mcp.run()  # stdio
