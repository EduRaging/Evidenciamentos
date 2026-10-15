"""Registro dos PDFs gerados (evidências e relatórios) nas pastas de teste."""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PREFIXO_EVIDENCIAS = "Evidencias - "  # PDF gerado pelo app ao finalizar; os demais são relatórios da IA
TIPO_EVIDENCIAS = "Evidências"
TIPO_RELATORIO = "Relatório"
_PREFIXO_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{4} - ")


@dataclass(frozen=True)
class RegistroPdf:
    caminho: Path
    teste: str  # nome do teste (a pasta sem o prefixo de data)
    pasta_teste: str  # nome completo da pasta do teste
    tipo: str  # TIPO_EVIDENCIAS ou TIPO_RELATORIO
    momento: datetime  # última modificação do arquivo
    tamanho: int  # bytes


def listar_pdfs(base: Path | str, limite: int = 300) -> list[RegistroPdf]:
    """PDFs dentro das pastas de teste de `base`, do mais recente para o mais antigo.

    Só olha um nível de subpastas (cada teste é uma pasta) e ignora pastas de trabalho (_ e .).
    """
    base = Path(base)
    if not base.is_dir():
        return []
    achados: list[RegistroPdf] = []
    try:
        testes = list(os.scandir(base))
    except OSError:
        return []
    for pasta in testes:
        try:
            if not pasta.is_dir(follow_symlinks=False) or pasta.name.startswith(("_", ".")):
                continue
            nome = _PREFIXO_DATA.sub("", pasta.name)
            with os.scandir(pasta.path) as arquivos:
                for arquivo in arquivos:
                    if not (arquivo.is_file(follow_symlinks=False) and arquivo.name.lower().endswith(".pdf")):
                        continue
                    info = arquivo.stat()
                    tipo = TIPO_EVIDENCIAS if arquivo.name.startswith(PREFIXO_EVIDENCIAS) else TIPO_RELATORIO
                    achados.append(RegistroPdf(Path(arquivo.path), nome, pasta.name, tipo,
                                               datetime.fromtimestamp(info.st_mtime), info.st_size))
        except OSError:
            continue  # pasta sumiu ou sem permissão: segue com as outras
    achados.sort(key=lambda r: r.momento, reverse=True)
    return achados[:max(1, limite)]


def _normalizar(texto: str) -> str:
    """Minúsculas e sem acentos, para o filtro achar 'relatorio' em 'Relatório'."""
    base = unicodedata.normalize("NFD", texto.casefold())
    return "".join(c for c in base if unicodedata.category(c) != "Mn")


def filtrar(registros: list[RegistroPdf], texto: str) -> list[RegistroPdf]:
    """Mantém os registros em que TODAS as palavras do filtro aparecem (teste, tipo ou arquivo)."""
    palavras = _normalizar(texto).split()
    if not palavras:
        return list(registros)
    resultado = []
    for r in registros:
        alvo = _normalizar(f"{r.teste} {r.tipo} {r.caminho.name}")
        if all(p in alvo for p in palavras):
            resultado.append(r)
    return resultado


def formatar_tamanho(bytes_: int) -> str:
    if bytes_ < 1024 * 1024:
        return f"{max(1, round(bytes_ / 1024))} KB"
    return f"{bytes_ / 1024 / 1024:.1f} MB".replace(".", ",")
