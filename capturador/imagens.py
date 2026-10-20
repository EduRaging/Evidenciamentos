"""Abertura segura das imagens de evidência (que podem ter sido trocadas ou adulteradas)."""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

LIMITE_PIXELS = 40_000_000  # 40 milhões de pixels: uma tela 8K tem cerca de 33 milhões
# O Claude desktop recusa imagem acima de 1 MB no resultado de uma ferramenta, e o base64 incha o arquivo em 1/3:
# 700 KB de imagem viram uns 930 KB no protocolo, com folga.
LIMITE_BYTES_IA = 700_000


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


def _codificar(imagem: Image.Image, formato: str, **opcoes) -> bytes:
    saida = io.BytesIO()
    imagem.save(saida, formato, **opcoes)
    return saida.getvalue()


def reduzir_para_ia(caminho: Path | str, lado_maximo: int = 1568,
                    limite_bytes: int = LIMITE_BYTES_IA) -> tuple[bytes, str]:
    """A evidência pronta para a IA olhar: no máximo `lado_maximo` px e no máximo `limite_bytes`.

    Devolve (bytes, "png" ou "jpeg"). PNG sempre que couber (sem perda, o melhor para texto de tela); se uma tela
    com fotos ou degradês passar do limite, vira JPEG (qualidade 85, depois 70) e, se ainda for preciso, encolhe
    20% por vez. ValueError se o arquivo não for um PNG válido ou nem assim couber.
    """
    with abrir_png(caminho) as original:  # só PNG e com limite de pixels
        original.thumbnail((lado_maximo, lado_maximo), Image.Resampling.LANCZOS)
        atual = original.convert("RGB")  # converte DEPOIS de reduzir: poupa memória
    dados = _codificar(atual, "PNG", optimize=True)
    if len(dados) <= limite_bytes:
        return dados, "png"
    for _ in range(8):
        for qualidade in (85, 70):
            dados = _codificar(atual, "JPEG", quality=qualidade, optimize=True)
            if len(dados) <= limite_bytes:
                return dados, "jpeg"
        atual = atual.resize((max(1, int(atual.width * 0.8)), max(1, int(atual.height * 0.8))), Image.Resampling.LANCZOS)
    raise ValueError("Não consegui reduzir a imagem da evidência para o tamanho que a IA aceita.")
