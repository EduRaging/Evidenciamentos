"""Confere, no Claude desktop, se a extensão do Capturador está pronta para ler um teste.

Lê só dois arquivos pequenos que o Claude desktop mantém em %APPDATA%\\Claude (formato não
documentado, observado na versão instalada): o aviso é apenas uma ajuda. Qualquer dúvida (arquivo
ausente, formato diferente) significa "não sei" e não gera aviso nenhum.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ID_EXTENSAO = "local.mcpb.eduraging.capturador-evidencias"


def _pasta_do_claude() -> Path | None:
    appdata = os.environ.get("APPDATA")
    return Path(appdata) / "Claude" if appdata else None


def _json(caminho: Path) -> dict | None:
    try:
        if caminho.stat().st_size > 100_000:
            return None
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return dados if isinstance(dados, dict) else None


def _mesma_pasta(a: str, b: Path) -> bool:
    try:
        return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(str(b)))
    except (TypeError, ValueError):
        return False


def avisos(pasta_do_teste: Path, pasta_do_claude: Path | None = None) -> list[str]:
    """Problemas que impediriam o Claude de ler `pasta_do_teste` pela extensão (lista vazia = sem aviso)."""
    base = pasta_do_claude or _pasta_do_claude()
    if base is None or not (base / "Claude Extensions").is_dir():
        return []  # Claude desktop não encontrado: nada a afirmar
    if not (base / "Claude Extensions" / ID_EXTENSAO / "manifest.json").is_file():
        return ["A extensão do Capturador não está instalada no Claude desktop: ele não vai conseguir ler as "
                "evidências. Instale o arquivo CapturadorEvidencias.mcpb ou desmarque esta caixa."]
    ajustes = _json(base / "Claude Extensions Settings" / f"{ID_EXTENSAO}.json")
    if ajustes is None:
        return []
    problemas = []
    if ajustes.get("isEnabled") is False:
        problemas.append("A extensão está instalada, mas DESATIVADA no Claude desktop: ligue-a em "
                         "Configurações > Extensões, senão o Claude não terá as ferramentas.")
    configuracao = ajustes.get("userConfig")
    configurada = configuracao.get("pasta_base") if isinstance(configuracao, dict) else None
    if isinstance(configurada, str) and configurada and not _mesma_pasta(configurada, pasta_do_teste.parent):
        problemas.append(f'A extensão lê a pasta "{configurada}", mas este teste está em "{pasta_do_teste.parent}": '
                         "o Claude não vai achá-lo. Escolha um teste daquela pasta (Trocar…) ou mude a pasta "
                         "da extensão no Claude.")
    return problemas
