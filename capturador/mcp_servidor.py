"""Servidor MCP (protótipo): deixa uma IA ler as evidências dos testes e salvar o relatório em PDF.

Roda por stdio, iniciado pelo cliente (Claude Desktop, Claude Code...). Nunca escreva na saída
padrão: ela é o canal do protocolo.

Segurança: toda ferramenta recebe só o NOME da pasta do teste, sempre resolvido dentro da pasta
de evidências do app; nada fora dela é lido ou escrito, e nenhum arquivo é sobrescrito.
"""
from __future__ import annotations

import os
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import ciclos, gravacao, metadados
from .imagens import reduzir_para_ia
from .metadados import PastaTeste
from .prompt_ciclo import montar_prompt_roteiro
from .prompt_ia import SAIDAS, Formulario, montar_prompt

LADO_MAXIMO = 1568  # px; acima disso a IA reduz a imagem de qualquer jeito e o custo só sobe
MAX_MARKDOWN = gravacao.MAX_MARKDOWN
MAX_TITULO = gravacao.MAX_TITULO
MAX_PDFS_POR_TESTE = gravacao.MAX_PDFS_POR_TESTE  # a gravação do PDF vive em gravacao.py, igual para o app
MAX_ROTEIROS_POR_CICLO = 30  # idem para os roteiros (cada geração nova cria o próximo número)
_trava_gravacao = gravacao.trava_gravacao  # o SDK roda as ferramentas em threads; a gravação é uma por vez
AVISO_IA = gravacao.AVISO_IA

INSTRUCOES = (
    "Evidências de testes manuais capturadas pelo Capturador de Evidências. Fluxo: `listar_testes` "
    "para achar o teste; `obter_teste` para ver as evidências; `ver_evidencia` para olhar cada imagem; "
    "`salvar_relatorio_pdf` para gravar o relatório (Markdown) em PDF na pasta do teste. O prompt "
    "`analisar_teste` já traz as instruções completas. Para montar o roteiro de testes de um ciclo, o prompt "
    "`gerar_roteiro` traz as instruções e a ferramenta `salvar_casos` grava os casos. "
    "Baseie-se só no que as imagens mostram. "
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


_e_atalho = gravacao.e_atalho


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


_caminho_da_evidencia = gravacao.caminho_da_evidencia


def _evidencia(dados: PastaTeste, numero: int) -> metadados.EvidenciaInfo:
    for ev in dados.evidencias:
        if ev.numero == numero:
            return ev
    raise ValueError(f"Evidência {numero} não existe; este teste tem de 1 a {len(dados.evidencias)}.")


_nome_unico = gravacao.nome_unico


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
    # só PNG e com limite de pixels; acima de ~700 KB o Claude desktop recusa a imagem, então vira JPEG (imagens.py)
    imagem, formato = reduzir_para_ia(caminho, LADO_MAXIMO)
    return Image(data=imagem, format=formato)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                      idempotentHint=False, openWorldHint=False))
@_erros_previstos
def salvar_relatorio_pdf(teste: str, titulo: str, conteudo_markdown: str,
                         incluir_evidencias: bool = True) -> dict[str, Any]:
    """Grava o relatório (Markdown) em PDF na pasta do teste, com as imagens ao final.

    Suporta títulos (#), listas, tabelas com barras verticais, **negrito** e *itálico*.
    Nunca sobrescreve: se o nome já existe, cria outro com (2), (3)...
    """
    # `pasta` e os caminhos completos vão para a IA de propósito: o usuário precisa saber ONDE o arquivo
    # foi parar. É a pasta que ele mesmo configurou, a mesma que a IA já está lendo.
    return gravacao.gravar_relatorio_pdf(_resolver_teste(teste), titulo, conteudo_markdown, incluir_evidencias,
                                         max_pdfs=MAX_PDFS_POR_TESTE)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                      idempotentHint=False, openWorldHint=False))
@_erros_previstos
def salvar_casos(ciclo: str, casos: list[dict[str, Any]], ciclo_sugerido: dict[str, Any] | None = None,
                 observacoes: list[str] | None = None) -> dict[str, Any]:
    """Grava o roteiro de testes (os casos) de um ciclo, para o app mostrá-lo ao testador.

    `ciclo` é o nome da pasta do ciclo. Cada caso: id (CT-01), titulo, objetivo, tecnica, prioridade
    (Alta, Média ou Baixa), passos [{acao, resultado_esperado}] e, opcionalmente, tipo, pre_condicoes,
    dados_de_teste, pos_condicoes, rastreio, evidencias_base [{teste, numero}] e a_confirmar.
    `ciclo_sugerido` propõe objetivo, escopo, riscos e critérios de entrada e saída. Tudo é validado e,
    se algo não servir, a mensagem diz o que corrigir. Nunca sobrescreve: cada chamada cria o próximo
    arquivo roteiro-NNN.json na pasta do ciclo.
    """
    pasta = ciclos.resolver_ciclo(_base(), ciclo)
    ciclos.ler_ciclo(pasta)  # só se grava em pasta que seja mesmo um ciclo criado pelo app
    validados = ciclos.validar_casos(casos)
    with _trava_gravacao:
        if ciclos.contar_roteiros(pasta) >= MAX_ROTEIROS_POR_CICLO:
            raise ValueError(f"Este ciclo já tem {MAX_ROTEIROS_POR_CICLO} roteiros; apague os que não servem mais.")
        arquivo = ciclos.gravar_roteiro(pasta, validados, observacoes, ciclo_sugerido=ciclo_sugerido)
    por_prioridade: dict[str, int] = {}
    for c in validados:
        por_prioridade[c.prioridade] = por_prioridade.get(c.prioridade, 0) + 1
    # a pasta e o caminho vão para a IA de propósito, como no relatório: é a pasta que o usuário configurou
    return {"ciclo": pasta.name, "arquivo": arquivo.name, "casos": len(validados), "por_prioridade": por_prioridade,
            "pasta": str(pasta), "caminho": str(arquivo)}


@mcp.prompt(title="Gerar o roteiro de testes de um ciclo")
def gerar_roteiro(ciclo: str) -> str:
    """Instruções completas para montar o roteiro de testes de um ciclo a partir das telas de referência."""
    pasta = ciclos.resolver_ciclo(_base(), ciclo)
    dados = ciclos.ler_ciclo(pasta)
    testes, ausentes = [], []
    for nome in dados.testes_base:
        try:
            testes.append(_resolver_teste(nome))
        except ValueError:
            ausentes.append(nome)
    return montar_prompt_roteiro(dados, testes, ausentes)


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
