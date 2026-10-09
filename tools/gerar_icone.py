"""Gera assets/icone.ico (moldura de recorte com lente). Uso: python tools/gerar_icone.py"""
from pathlib import Path

from PIL import Image, ImageDraw

TAMANHOS = [16, 24, 32, 48, 64, 128, 256]
BASE = 1024  # desenha grande e reduz, para as bordas ficarem suaves


def desenhar() -> Image.Image:
    imagem = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    d = ImageDraw.Draw(imagem)
    d.rounded_rectangle((32, 32, BASE - 32, BASE - 32), radius=200, fill=(30, 64, 120, 255))

    # quatro cantoneiras brancas: a "moldura" do recorte
    margem, braco, espessura = 210, 230, 70
    esq, topo, dir_, base = margem, margem, BASE - margem, BASE - margem
    branco = (255, 255, 255, 255)
    for x, y, sx, sy in ((esq, topo, 1, 1), (dir_, topo, -1, 1), (esq, base, 1, -1), (dir_, base, -1, -1)):
        d.rectangle(sorted_box(x, y, x + sx * braco, y + sy * espessura), fill=branco)
        d.rectangle(sorted_box(x, y, x + sx * espessura, y + sy * braco), fill=branco)

    # lente no centro
    centro, raio = BASE // 2, 120
    d.ellipse((centro - raio, centro - raio, centro + raio, centro + raio), fill=(56, 189, 248, 255))
    return imagem


def sorted_box(x0: int, y0: int, x1: int, y1: int) -> tuple[int, int, int, int]:
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


if __name__ == "__main__":
    destino = Path(__file__).resolve().parent.parent / "assets" / "icone.ico"
    destino.parent.mkdir(exist_ok=True)
    desenhar().save(destino, sizes=[(t, t) for t in TAMANHOS])
    print("icone gerado:", destino.name)
