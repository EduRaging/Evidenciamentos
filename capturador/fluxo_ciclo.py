"""Do teste capturado ao ciclo com roteiro: cria o ciclo só com as telas e monta o pedido ao Claude.

Sem interface: o app (e os testes) chamam estas funções. O usuário só escolhe as telas de referência;
nome, objetivo, escopo e critérios ficam por conta da IA, a menos que ele queira ajustar.
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from . import ciclos, metadados
from .ciclos import Ciclo
from .dialogo_prompt import ler_testes
from .metadados import PastaTeste
from .prompt_ciclo import montar_prompt_roteiro


def criar_a_partir_de_testes(base: Path | str, pastas: Sequence[Path | str],
                             parametros: dict | None = None) -> tuple[Ciclo, list[tuple[str, str]]]:
    """Cria o ciclo tendo os testes `pastas` como telas de referência.

    Devolve (ciclo, ignorados): testes sem imagens ou inválidos ficam de fora e voltam em `ignorados`.
    `parametros` (opcional) traz o que o usuário quis ajustar; o nome, se faltar, vem dos testes.
    Levanta ValueError se nenhum teste servir ou se os parâmetros não forem válidos.
    """
    testes, ignorados = ler_testes(pastas)
    if not testes:
        raise ValueError("Nenhum dos testes escolhidos tem imagens de evidência para servir de referência.")
    dados = dict(parametros or {})
    dados["nome"] = (dados.get("nome") or "").strip() or ciclos.nome_automatico([t.nome_teste for t in testes])
    dados["testes_base"] = [t.pasta.name for t in testes]
    return ciclos.criar_ciclo(base, dados), ignorados


def testes_de_referencia(ciclo: Ciclo, base: Path | str) -> tuple[list[PastaTeste], list[str]]:
    """As telas de referência do ciclo que ainda existem, e os nomes das que sumiram (arquivadas ou apagadas)."""
    base = Path(base)
    achados: list[PastaTeste] = []
    ausentes: list[str] = []
    for nome in ciclo.testes_base:
        pasta = base / nome
        try:
            if nome.startswith(("_", ".")) or pasta.parent != base or not pasta.is_dir():
                raise ValueError("fora do lugar")
            teste = metadados.ler(pasta)
            if not teste.evidencias:
                raise ValueError("sem imagens")
            achados.append(teste)
        except ValueError:
            ausentes.append(nome)
    return achados, ausentes


def montar_pedido(ciclo: Ciclo, base: Path | str) -> str:
    """O texto que o app entrega ao Claude para ele montar o roteiro (as telas são lidas pela extensão)."""
    testes, ausentes = testes_de_referencia(ciclo, base)
    return montar_prompt_roteiro(ciclo, testes, ausentes)


def situacao(ciclo: Ciclo) -> tuple[str, int]:
    """("sem roteiro", 0) ou ("roteiro pronto", n casos) para a lista de ciclos."""
    roteiro = ciclos.ler_roteiro_mais_recente(ciclo.pasta)
    return ("roteiro pronto", len(roteiro.casos)) if roteiro else ("sem roteiro", 0)
