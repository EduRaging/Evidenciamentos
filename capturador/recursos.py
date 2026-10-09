"""Acesso a arquivos de recursos (ícone), tanto no código-fonte quanto no .exe empacotado."""
from __future__ import annotations

import sys
from pathlib import Path


def caminho(relativo: str) -> Path:
    """Caminho de um recurso. No .exe (PyInstaller) os dados ficam em sys._MEIPASS."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relativo
