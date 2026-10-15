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
    except (OSError, ValueError, KeyError, TypeError, OverflowError, RecursionError):
        # JSON ausente, corrompido ou hostil (número gigante, aninhamento extremo...): lê pelos arquivos
        return _varrer(pasta)


LIMITE_JSON_BYTES = 1_000_000  # um evidencias.json legítimo tem poucos KB
MAX_EVIDENCIAS = 200
_CONTROLE = re.compile(r"[\x00-\x1f\x7f​-‏‪-‮⁦-⁩]")


def _texto_seguro(valor, limite: int = 200) -> str:
    """Texto de uma linha só, sem caracteres de controle nem de direção (o JSON pode ter sido
    adulterado e estes campos vão parar dentro do prompt da IA), e com tamanho limitado."""
    return re.sub(r"\s+", " ", _CONTROLE.sub(" ", str(valor))).strip()[:limite]


def _nome_simples(nome: str) -> str:
    """Só o nome de um arquivo, nunca um caminho: o JSON pode ter sido adulterado."""
    if not nome or nome in (".", "..") or Path(nome).name != nome or any(c in nome for c in '/\\:\x00'):
        raise ValueError(f"Nome de arquivo inválido em {ARQUIVO}: {nome!r}")
    return nome


def _ler_json(pasta: Path) -> PastaTeste:
    arquivo = pasta / ARQUIVO
    if arquivo.stat().st_size > LIMITE_JSON_BYTES:
        raise ValueError(f"{ARQUIVO} grande demais")
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    brutas = dados["evidencias"]
    if not isinstance(brutas, list) or len(brutas) > MAX_EVIDENCIAS:
        raise ValueError(f"Lista de evidências inválida em {ARQUIVO}")
    evidencias = [
        EvidenciaInfo(
            numero=int(e["numero"]),
            arquivo=_nome_simples(str(e["arquivo"])),
            rotulo=_texto_seguro(e["rotulo"]),
            # sem fuso: datas com e sem fuso misturadas não podem ser comparadas (TypeError)
            momento=datetime.fromisoformat(e["hora"]).replace(tzinfo=None) if e.get("hora") else None,
        )
        for e in brutas
    ]
    pdf = dados.get("pdf")
    return PastaTeste(pasta, _texto_seguro(dados["nome_teste"]), _texto_seguro(dados.get("testador", "")),
                      _nome_simples(str(pdf)) if pdf else None, evidencias)


def _varrer(pasta: Path) -> PastaTeste:
    evidencias = []
    try:
        arquivos = sorted(pasta.iterdir())
        pdfs = sorted(p.name for p in pasta.glob("*.pdf"))
    except OSError as exc:  # sem permissão, pasta sumiu...
        raise ValueError("Não consegui ler esta pasta.") from exc
    for arquivo in arquivos:
        achado = _PNG.match(arquivo.name)
        if achado and len(evidencias) < MAX_EVIDENCIAS:
            tipo = achado.group(2).lower()
            evidencias.append(EvidenciaInfo(int(achado.group(1)), arquivo.name,
                                            _ROTULOS.get(tipo, tipo)))
    if not evidencias and not pdfs:
        raise ValueError("Esta pasta não parece ser de um teste do Capturador "
                         "(não encontrei os PNGs numerados nem o PDF).")
    nome = _texto_seguro(_PREFIXO_DATA.sub("", pasta.name))
    return PastaTeste(pasta, nome, "", pdfs[0] if pdfs else None, evidencias)
