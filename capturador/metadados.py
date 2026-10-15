"""Dados de uma pasta de teste já finalizada (usados para preparar o prompt de IA).

Cada teste finalizado ganha um `evidencias.json`. Pastas antigas, sem o arquivo, são lidas
varrendo os PNGs e o PDF.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ARQUIVO = "evidencias.json"

_ROTULOS = {"tela": "Tela inteira", "recorte": "Recorte"}
_PREFIXO_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{4} - ")
_PNG = re.compile(r"^(\d+)_(tela|recorte)\.png$", re.IGNORECASE)


@dataclass
class EvidenciaInfo:
    numero: int
    arquivo: str
    rotulo: str
    momento: datetime | None = None


@dataclass
class PastaTeste:
    pasta: Path
    nome_teste: str
    testador: str = ""
    pdf: str | None = None
    evidencias: list[EvidenciaInfo] = field(default_factory=list)


def gravar(pasta: Path, nome_teste: str, testador: str, pdf: str,
           evidencias: list[EvidenciaInfo]) -> None:
    dados = {
        "versao": 1,
        "nome_teste": nome_teste,
        "testador": testador,
        "pdf": pdf,
        "evidencias": [
            {
                "numero": e.numero,
                "arquivo": e.arquivo,
                "rotulo": e.rotulo,
                "hora": e.momento.isoformat(timespec="seconds") if e.momento else None,
            }
            for e in evidencias
        ],
    }
    (Path(pasta) / ARQUIVO).write_text(json.dumps(dados, ensure_ascii=False, indent=2),
                                       encoding="utf-8")


def ler(pasta: Path | str) -> PastaTeste:
    """Lê a pasta de um teste. ValueError se ela não parecer ser de um teste do Capturador."""
    pasta = Path(pasta)
    if not pasta.is_dir():
        raise ValueError("A pasta informada não existe.")
    try:
        return _ler_json(pasta)
    except (OSError, ValueError, KeyError, TypeError):
        return _varrer(pasta)


def _ler_json(pasta: Path) -> PastaTeste:
    dados = json.loads((pasta / ARQUIVO).read_text(encoding="utf-8"))
    evidencias = [
        EvidenciaInfo(
            numero=int(e["numero"]),
            arquivo=str(e["arquivo"]),
            rotulo=str(e["rotulo"]),
            momento=datetime.fromisoformat(e["hora"]) if e.get("hora") else None,
        )
        for e in dados["evidencias"]
    ]
    return PastaTeste(pasta, str(dados["nome_teste"]), str(dados.get("testador", "")),
                      dados.get("pdf"), evidencias)


def _varrer(pasta: Path) -> PastaTeste:
    evidencias = []
    for arquivo in sorted(pasta.iterdir()):
        achado = _PNG.match(arquivo.name)
        if achado:
            tipo = achado.group(2).lower()
            evidencias.append(EvidenciaInfo(int(achado.group(1)), arquivo.name,
                                            _ROTULOS.get(tipo, tipo)))
    pdfs = sorted(p.name for p in pasta.glob("*.pdf"))
    if not evidencias and not pdfs:
        raise ValueError("Esta pasta não parece ser de um teste do Capturador "
                         "(não encontrei os PNGs numerados nem o PDF).")
    nome = _PREFIXO_DATA.sub("", pasta.name)
    return PastaTeste(pasta, nome, "", pdfs[0] if pdfs else None, evidencias)
