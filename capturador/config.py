"""Configuração persistente do Capturador de Evidências (JSON em %APPDATA%)."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

NOME_APP = "CapturadorEvidencias"


def pasta_config() -> Path:
    """Pasta de dados do app. CAPTURADOR_CONFIG_DIR permite redirecionar (testes)."""
    pasta = os.environ.get("CAPTURADOR_CONFIG_DIR")
    if pasta:
        return Path(pasta)
    return Path(os.environ.get("APPDATA", str(Path.home()))) / NOME_APP


@dataclass
class Config:
    pasta_base: str = ""
    atalho_tela: str = "ctrl+shift+f9"
    atalho_recorte: str = "ctrl+shift+f8"
    atalho_janela: str = "ctrl+shift+f7"
    testador: str = ""

    def __post_init__(self) -> None:
        if not self.pasta_base:
            self.pasta_base = str(Path.home() / "Documents" / "Evidencias")


def carregar() -> Config:
    arquivo = pasta_config() / "config.json"
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Config()
    validos = {f.name for f in fields(Config)}
    return Config(**{k: v for k, v in dados.items() if k in validos and isinstance(v, str)})


def salvar(cfg: Config) -> None:
    pasta = pasta_config()
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "config.json").write_text(
        json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8"
    )
