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

from . import metadados
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
    "`analisar_teste` já traz as instruções completas. Baseie-se só no que as imagens mostram. "
    "Sempre diga ao usuário QUAL pasta está lendo (campo `pasta_base` de `listar_testes`) e, ao salvar, "
    "o CAMINHO COMPLETO do arquivo gerado."
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
    """Pasta de evidências, SEMPRE explícita (variável CAPTURADOR_PASTA_BASE).

    Sem ela o servidor se recusa a trabalhar. Cair numa pasta padrão do app já expôs evidências
    REAIS quando a configuração da extensão não chegou ao processo ("falha aberta").
    """
    valor = (os.environ.get("CAPTURADOR_PASTA_BASE") or "").strip()
    if not valor or valor.startswith("${"):  # ausente, vazia ou não substituída pelo host
        raise ValueError(
            "A pasta das evidências não está configurada nesta extensão. No Claude desktop, abra "
            "Configurações > Extensões > capturador-evidencias, escolha a pasta e reinicie o Claude.")
    base = Path(valor)
    if not base.is_dir():
        raise ValueError(f"A pasta das evidências configurada não existe: {valor}")
    return base


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


def _caminho_da_evidencia(dados: PastaTeste, ev: metadados.EvidenciaInfo) -> Path | None:
    """Arquivo da evidência, só se estiver realmente DENTRO da pasta do teste.

    O .resolve() segue atalhos/links simbólicos: um link para fora da pasta é recusado.
    """
    caminho = (dados.pasta / ev.arquivo).resolve()
    if caminho.parent != dados.pasta.resolve() or not caminho.is_file():
        return None
    return caminho


def _evidencia(dados: PastaTeste, numero: int) -> metadados.EvidenciaInfo:
    for ev in dados.evidencias:
        if ev.numero == numero:
            return ev
    raise ValueError(f"Evidência {numero} não existe; este teste tem de 1 a {len(dados.evidencias)}.")


def _nome_unico(pasta: Path, nome: str) -> str:
    """Nome-base livre para o par .pdf/.md: nenhum dos dois pode existir (nunca sobrescreve)."""
    for n in range(1, 100):
        candidato = nome if n == 1 else f"{nome} ({n})"
        if not (pasta / f"{candidato}.pdf").exists() and not (pasta / f"{candidato}.md").exists():
            return candidato
    raise ValueError("Há arquivos demais com esse nome na pasta do teste; use outro título.")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
@_erros_previstos
def listar_testes(limite: int = 20) -> dict[str, Any]:
    """Lista os testes finalizados mais recentes e informa QUAL pasta de evidências está sendo lida.

    Use o campo `teste` de cada item nas outras ferramentas e diga ao usuário o `pasta_base`.
    """
    base = _base()
    achados = []
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
    return {"pasta_base": str(base), "testes": [item for _, item in achados[:max(1, min(limite, 100))]]}


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
    caminho = _caminho_da_evidencia(dados, ev)
    if caminho is None:
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

    nome = _nome_unico(dados.pasta, nome_seguro(titulo))
    pdf, markdown = dados.pasta / f"{nome}.pdf", dados.pasta / f"{nome}.md"
    # O Markdown vai primeiro: é barato e guarda o trabalho da IA mesmo que o PDF falhe ou demore.
    # Modo "x": falha em vez de sobrescrever se o arquivo aparecer entre a checagem e a gravação.
    try:
        with markdown.open("x", encoding="utf-8") as f:
            f.write(conteudo_markdown)
    except FileExistsError as exc:
        raise ValueError("Já existe um arquivo com esse nome na pasta do teste; tente de novo.") from exc
    evidencias = []
    if incluir_evidencias:
        for ev in dados.evidencias:
            caminho = _caminho_da_evidencia(dados, ev)
            if caminho is not None:
                evidencias.append(EvidenciaPdf(caminho, ev.rotulo, ev.numero, ev.momento))
    subtitulo = (f"Teste: {dados.nome_teste} · gerado em {datetime.now():%d/%m/%Y %H:%M} · {AVISO_IA}")
    paginas = gerar_pdf_de_markdown(pdf, titulo, conteudo_markdown, subtitulo, evidencias)
    return {"teste": dados.pasta.name, "pdf": pdf.name, "markdown": markdown.name, "paginas": paginas,
            "evidencias_anexadas": len(evidencias), "pasta": str(dados.pasta),
            "caminho_pdf": str(pdf), "caminho_markdown": str(markdown)}


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
