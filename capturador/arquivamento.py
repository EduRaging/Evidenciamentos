"""Arquivar testes antigos: tira a pasta da lista sem apagar nada (é só mover de volta para desfazer)."""
from __future__ import annotations

import os
from pathlib import Path

NOME_PASTA_ARQUIVO = "_arquivo"  # o registro e o servidor MCP ignoram pastas que começam com "_"


def pasta_de_arquivo(base: Path | str) -> Path:
    return Path(base) / NOME_PASTA_ARQUIVO


def _e_atalho(caminho: Path) -> bool:
    return os.path.islink(caminho) or os.path.isjunction(caminho)


def arquivar(pasta: Path | str, base: Path | str) -> Path:
    """Move a pasta de um teste de `base` para `base\\_arquivo` e devolve o novo caminho.

    Só aceita pastas que estejam DIRETAMENTE em `base`, não sejam atalhos/junções e não sejam pastas
    de trabalho (_ ou .). Um nome repetido no arquivo ganha " (2)", " (3)"…; nada é sobrescrito.
    Levanta ValueError para pastas que não podem ser arquivadas e OSError se o Windows recusar o
    movimento (por exemplo, um PDF do teste aberto num leitor).
    """
    pasta, base = Path(pasta), Path(base)
    if not pasta.is_dir() or _e_atalho(pasta):
        raise ValueError("A pasta do teste não existe mais ou é um atalho.")
    if pasta.parent.resolve() != base.resolve():
        raise ValueError("Só é possível arquivar testes que estão diretamente na pasta de evidências.")
    if pasta.name.startswith(("_", ".")):
        raise ValueError("Esta pasta é de trabalho do app e não pode ser arquivada.")
    arquivo = pasta_de_arquivo(base)
    if arquivo.exists() and (not arquivo.is_dir() or _e_atalho(arquivo)):
        raise ValueError(f'"{NOME_PASTA_ARQUIVO}" na pasta de evidências não é uma pasta comum.')
    arquivo.mkdir(exist_ok=True)
    destino = arquivo / pasta.name
    n = 2
    while destino.exists():
        destino = arquivo / f"{pasta.name} ({n})"
        n += 1
    pasta.rename(destino)  # mesma unidade: movimento atômico; falha (PermissionError) se algo estiver aberto
    return destino
