"""Registro dos PDFs gerados (evidências e relatórios) nas pastas de teste."""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PREFIXO_EVIDENCIAS = "Evidencias - "  # PDF gerado pelo app ao finalizar; os demais são da IA
PREFIXO_SUGESTOES = "sugestoes de casos"  # PDF de sugestões da IA (comparado sem acento nem maiúsculas)
TIPO_EVIDENCIAS = "Evidências"
TIPO_RELATORIO = "Relatório"
TIPO_SUGESTOES = "Sugestões"
_PREFIXO_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{4} - ")


def tipo_do_pdf(nome_do_arquivo: str) -> str:
    """Evidências (o do app), Sugestões (a IA, pelo começo do título) ou Relatório (os demais)."""
    if nome_do_arquivo.startswith(PREFIXO_EVIDENCIAS):
        return TIPO_EVIDENCIAS
    if _normalizar(nome_do_arquivo).startswith(PREFIXO_SUGESTOES):
        return TIPO_SUGESTOES
    return TIPO_RELATORIO


@dataclass(frozen=True)
class RegistroPdf:
    caminho: Path
    teste: str  # nome do teste (a pasta sem o prefixo de data)
    pasta_teste: str  # nome completo da pasta do teste
    tipo: str  # TIPO_EVIDENCIAS, TIPO_RELATORIO ou TIPO_SUGESTOES
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
                    achados.append(RegistroPdf(Path(arquivo.path), nome, pasta.name, tipo_do_pdf(arquivo.name),
                                               datetime.fromtimestamp(info.st_mtime), info.st_size))
        except OSError:
            continue  # pasta sumiu ou sem permissão: segue com as outras
    achados.sort(key=lambda r: r.momento, reverse=True)
    return achados[:max(1, limite)]


@dataclass(frozen=True)
class TesteRegistrado:
    """Um teste (uma pasta) com os PDFs dele: evidências, relatórios e sugestões."""
    pasta: Path
    teste: str  # nome do teste (a pasta sem o prefixo de data)
    pasta_nome: str
    momento: datetime  # quando o teste foi feito (prefixo da pasta; senão, o PDF mais antigo)
    evidencias: RegistroPdf | None  # o "Evidencias - ….pdf" gerado pelo app
    relatorios: tuple[RegistroPdf, ...]  # do mais recente para o mais antigo
    sugestoes: tuple[RegistroPdf, ...] = ()  # "Sugestões de casos de teste - ….pdf", do mais recente

    @property
    def principal(self) -> RegistroPdf | None:
        """O PDF que as ações abrem por padrão: o relatório mais recente, ou o de evidências."""
        return self.relatorios[0] if self.relatorios else self.evidencias

    @property
    def pdfs(self) -> list[RegistroPdf]:
        """Todos, na ordem em que o teste os produz: evidências, relatórios e sugestões."""
        return ([self.evidencias] if self.evidencias else []) + list(self.relatorios) + list(self.sugestoes)


def _momento_da_pasta(nome: str) -> datetime | None:
    try:
        return datetime.strptime(nome[:15], "%Y-%m-%d_%H%M")
    except ValueError:
        return None


def agrupar_por_teste(registros: list[RegistroPdf]) -> list[TesteRegistrado]:
    """Junta os PDFs por pasta de teste, um item por teste, do mais recente para o mais antigo."""
    por_pasta: dict[Path, list[RegistroPdf]] = {}
    for r in registros:
        por_pasta.setdefault(r.caminho.parent, []).append(r)
    com_chave = []
    for pasta, itens in por_pasta.items():
        evidencias = sorted((i for i in itens if i.tipo == TIPO_EVIDENCIAS), key=lambda i: i.momento, reverse=True)
        relatorios = sorted((i for i in itens if i.tipo == TIPO_RELATORIO), key=lambda i: i.momento, reverse=True)
        sugestoes = sorted((i for i in itens if i.tipo == TIPO_SUGESTOES), key=lambda i: i.momento, reverse=True)
        mais_antigo = min(i.momento for i in itens)  # o PDF mais antigo é o do dia do teste, não o relatório
        momento = _momento_da_pasta(pasta.name) or mais_antigo
        teste = TesteRegistrado(pasta, itens[0].teste, pasta.name, momento,
                                evidencias[0] if evidencias else None, tuple(relatorios), tuple(sugestoes))
        com_chave.append(((momento, mais_antigo), teste))  # a pasta só tem minutos: o PDF desempata
    com_chave.sort(key=lambda par: par[0], reverse=True)
    return [teste for _, teste in com_chave]


def filtrar_testes(testes: list[TesteRegistrado], texto: str) -> list[TesteRegistrado]:
    """Mantém os testes em que TODAS as palavras aparecem no nome do teste ou nos nomes dos PDFs."""
    palavras = _normalizar(texto).split()
    if not palavras:
        return list(testes)
    resultado = []
    for t in testes:
        alvo = _normalizar(" ".join([t.teste, t.pasta_nome] + [p.caminho.name for p in t.pdfs]))
        if all(p in alvo for p in palavras):
            resultado.append(t)
    return resultado


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
