"""Miniaturas das evidências para a lista da janela (cache em memória)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageTk

from .imagens import abrir_png

TAMANHO = (92, 56)
_FUNDO = (232, 234, 238)
_LIMITE_CACHE = 200
_cache: dict[tuple[str, int], ImageTk.PhotoImage] = {}


def obter(caminho: Path | str) -> ImageTk.PhotoImage | None:
    """Miniatura do PNG (centralizada num quadro de tamanho fixo), ou None se não der para abrir.

    O cache é por caminho e data de modificação; as imagens abertas são PNGs de verdade e limitadas
    em pixels (as mesmas regras de segurança do resto do app).
    """
    caminho = Path(caminho)
    try:
        chave = (str(caminho), caminho.stat().st_mtime_ns)
    except OSError:
        return None
    if chave in _cache:
        return _cache[chave]
    try:
        with abrir_png(caminho) as original:
            miniatura = original.convert("RGB")
    except (OSError, ValueError):
        return None
    miniatura.thumbnail(TAMANHO, Image.Resampling.LANCZOS)
    quadro = Image.new("RGB", TAMANHO, _FUNDO)
    quadro.paste(miniatura, ((TAMANHO[0] - miniatura.width) // 2, (TAMANHO[1] - miniatura.height) // 2))
    foto = ImageTk.PhotoImage(quadro)
    if len(_cache) >= _LIMITE_CACHE:
        _cache.pop(next(iter(_cache)))  # descarta a mais antiga
    _cache[chave] = foto
    return foto
