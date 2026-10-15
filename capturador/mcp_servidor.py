"""Servidor MCP (protótipo): deixa uma IA ler as evidências dos testes e salvar o relatório em PDF.

Roda por stdio, iniciado pelo cliente (Claude Desktop, Claude Code...). Nunca escreva na saída
padrão: ela é o canal do protocolo.

Segurança: toda ferramenta recebe só o NOME da pasta do teste, sempre resolvido dentro da pasta
de evidências do app; nada fora dela é lido ou escrito, e nenhum arquivo é sobrescrito.
"""
from __future__ import annotations

import io
import os
import threading
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from PIL import Image as PILImage

from . import metadados
from .imagens import abrir_png
from .metadados import PastaTeste
from .prompt_ia import SAIDAS, Formulario, montar_prompt
from .relatorio_md import EvidenciaPdf, gerar_pdf_de_markdown
from .sessao import nome_seguro

LADO_MAXIMO = 1568  # px; acima disso a IA reduz a imagem de qualquer jeito e o custo só sobe
MAX_MARKDOWN = 200_000
MAX_TITULO = 150
MAX_PDFS_POR_TESTE = 100  # teto de gravação: títulos diferentes criam arquivos novos sem limite
_trava_gravacao = threading.Lock()  # o SDK roda as ferramentas em threads; a gravação é uma por vez
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
    expõe detalhes internos. (Os caminhos que as ferramentas devolvem de propósito, como o do
    arquivo gerado, são da pasta que o próprio usuário configurou.)
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


def _e_atalho(caminho: Path) -> bool:
    """Link simbólico ou junction: pasta/arquivo que na verdade aponta para outro lugar."""
    return caminho.is_symlink() or os.path.isjunction(caminho)


def _resolver_teste(teste: str) -> PastaTeste:
    """Pasta do teste pelo nome, confinada à pasta de evidências. ValueError se inválida."""
    nome = (teste or "").strip()
    if (not nome or nome in (".", "..") or nome.startswith(("_", "."))  # pastas de trabalho/ocultas
            or any(c in nome for c in '/\\:\x00')):
        raise ValueError("Informe só o nome da pasta do teste, como aparece em `listar_testes`.")
    base = _base().resolve()
    candidata = base / nome
    nao_encontrado = ValueError(f"Teste não encontrado: {nome!r}. Use `listar_testes` para ver os disponíveis.")
    if _e_atalho(candidata):  # um atalho para fora da pasta de evidências nunca é um teste
        raise nao_encontrado
    pasta = candidata.resolve()
    if pasta.parent != base or not pasta.is_dir():
        raise nao_encontrado
    return metadados.ler(pasta)


def _caminho_da_evidencia(dados: PastaTeste, ev: metadados.EvidenciaInfo) -> Path | None:
    """Arquivo da evidência, só se estiver realmente DENTRO da pasta do teste.

    Compara com a pasta JÁ validada (não a recalcula): se ela virar um atalho entre a validação e o
    uso, o `resolve()` seguiria o atalho e as duas pontas apontariam para fora, passando na checagem.
    """
    if _e_atalho(dados.pasta):
        return None
    candidato = dados.pasta / ev.arquivo
    if _e_atalho(candidato):
        return None
    caminho = candidato.resolve()
    if caminho.parent != dados.pasta or not caminho.is_file():
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
        try:
            if not pasta.is_dir() or pasta.name.startswith(("_", ".")) or _e_atalho(pasta):
                continue
            dados = metadados.ler(pasta)
            modificada = pasta.stat().st_mtime
            achados.append((modificada, {
                "teste": pasta.name,
                "nome_teste": dados.nome_teste,
                "evidencias": len(dados.evidencias),
                "pdf": dados.pdf,
                "data": datetime.fromtimestamp(modificada).isoformat(timespec="minutes"),
            }))
        except Exception:  # noqa: BLE001 - uma pasta ruim (sem permissão, JSON malicioso) não pode
            continue  # derrubar a listagem de todos os testes
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
    with abrir_png(caminho) as original:  # só PNG e com limite de pixels (ver imagens.py)
        original.thumbnail((LADO_MAXIMO, LADO_MAXIMO), PILImage.Resampling.LANCZOS)
        reduzida = original.convert("RGB")  # converte DEPOIS de reduzir: poupa memória
    saida = io.BytesIO()
    reduzida.save(saida, "PNG", optimize=True)
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

    if not dados.evidencias:
        # a leitura de pastas antigas aceita qualquer pasta com um PDF; para GRAVAR exigimos que seja
        # mesmo um teste deste app, senão uma base apontada para uma pasta ampla receberia arquivos
        raise ValueError("Esta pasta não tem evidências numeradas deste app; por segurança nada é gravado nela.")

    with _trava_gravacao:  # o SDK roda as ferramentas em threads: uma gravação por vez
        if len(list(dados.pasta.glob("*.pdf"))) >= MAX_PDFS_POR_TESTE:
            raise ValueError(f"Esta pasta já tem {MAX_PDFS_POR_TESTE} PDFs; apague os que não servem mais.")
        nome = _nome_unico(dados.pasta, nome_seguro(titulo))
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
                caminho = _caminho_da_evidencia(dados, ev)
                if caminho is not None:
                    evidencias.append(EvidenciaPdf(caminho, ev.rotulo, ev.numero, ev.momento))
        subtitulo = f"Teste: {dados.nome_teste} · gerado em {datetime.now():%d/%m/%Y %H:%M} · {AVISO_IA}"
        try:
            with arquivo_pdf:
                paginas = gerar_pdf_de_markdown(arquivo_pdf, titulo, conteudo_markdown, subtitulo, evidencias)
        except BaseException:
            pdf.unlink(missing_ok=True)  # só o PDF que acabamos de criar; o .md fica com o trabalho da IA
            raise
    # `pasta` e os caminhos completos vão para a IA de propósito: o usuário precisa saber ONDE o arquivo
    # foi parar. É a pasta que ele mesmo configurou, a mesma que a IA já está lendo.
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
