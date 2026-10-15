"""Abertura segura das imagens de evidência (que podem ter sido trocadas ou adulteradas)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

LIMITE_PIXELS = 40_000_000  # 40 milhões de pixels: uma tela 8K tem cerca de 33 milhões


def abrir_png(caminho: Path | str) -> Image.Image:
    """Abre o arquivo SÓ como PNG e recusa imagens enormes antes de decodificar os pixels.

    O Pillow identifica o formato pelo CONTEÚDO, não pela extensão, e aceita dezenas de formatos
    (até EMF/WMF, que vão para o GDI do Windows, e EPS, que chama o Ghostscript). Um arquivo
    `01_tela.png` com outro conteúdo não pode chegar a esses leitores. ValueError se não servir.
    """
    try:
        imagem = Image.open(caminho, formats=["PNG"])
    except (OSError, Image.DecompressionBombError) as exc:  # UnidentifiedImageError é um OSError
        raise ValueError("O arquivo da evidência não é um PNG válido ou é grande demais.") from exc
    if imagem.width * imagem.height > LIMITE_PIXELS:
        imagem.close()
        raise ValueError("A imagem da evidência é grande demais "
                         f"(o limite é de {LIMITE_PIXELS // 1_000_000} milhões de pixels).")
    return imagem
