"""Geração do PDF de evidências: capa + uma evidência por página."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

MARGEM = 36
ESCALA_MAXIMA = 1.0  # pt por pixel; evita ampliar recortes pequenos até ficarem borrados
CINZA = (0.35, 0.35, 0.35)


@dataclass
class ItemPdf:
    caminho: Path
    rotulo: str
    momento: datetime


def _registrar_fontes() -> tuple[str, str]:
    """Segoe UI (cobre mais caracteres) se existir; senão Helvetica embutida."""
    pasta = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    normal, negrito = pasta / "segoeui.ttf", pasta / "segoeuib.ttf"
    if normal.exists() and negrito.exists():
        pdfmetrics.registerFont(TTFont("SegoeUI", str(normal)))
        pdfmetrics.registerFont(TTFont("SegoeUI-Bold", str(negrito)))
        return "SegoeUI", "SegoeUI-Bold"
    return "Helvetica", "Helvetica-Bold"


def _cortar(texto: str, fonte: str, tamanho: float, largura: float) -> str:
    if pdfmetrics.stringWidth(texto, fonte, tamanho) <= largura:
        return texto
    while texto and pdfmetrics.stringWidth(texto + "…", fonte, tamanho) > largura:
        texto = texto[:-1]
    return texto + "…"


def _rodape(c: canvas.Canvas, fonte: str, largura: float, pagina: int, total: int) -> None:
    c.setFont(fonte, 8)
    c.setFillColorRGB(*CINZA)
    c.drawCentredString(largura / 2, MARGEM / 2, f"Página {pagina} de {total}")


def _capa(c: canvas.Canvas, fontes: tuple[str, str], nome_teste: str, testador: str,
          itens: list[ItemPdf], total_paginas: int) -> None:
    normal, negrito = fontes
    largura, altura = A4
    area = largura - 2 * MARGEM * 1.5
    x = MARGEM * 1.5

    c.setFillColorRGB(*CINZA)
    c.setFont(negrito, 12)
    c.drawString(x, altura - 140, "EVIDÊNCIAS DE TESTE")

    c.setFillColorRGB(0.1, 0.1, 0.1)
    y = altura - 180
    for linha in simpleSplit(nome_teste, negrito, 26, area):
        c.setFont(negrito, 26)
        c.drawString(x, y, linha)
        y -= 32

    c.setStrokeColorRGB(0.75, 0.75, 0.75)
    c.line(x, y - 8, largura - x, y - 8)
    y -= 40

    detalhes = [("Gerado em", datetime.now().strftime("%d/%m/%Y %H:%M"))]
    if testador:
        detalhes.append(("Testador", testador))
    detalhes.append(("Evidências", str(len(itens))))
    if itens:
        detalhes.append(("Primeira captura", itens[0].momento.strftime("%d/%m/%Y %H:%M:%S")))
        detalhes.append(("Última captura", itens[-1].momento.strftime("%d/%m/%Y %H:%M:%S")))
    for chave, valor in detalhes:
        c.setFillColorRGB(*CINZA)
        c.setFont(normal, 10)
        c.drawString(x, y, chave)
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.setFont(negrito, 11)
        c.drawString(x + 130, y, _cortar(valor, negrito, 11, area - 130))
        y -= 22
    _rodape(c, normal, largura, 1, total_paginas)


def _pagina_evidencia(c: canvas.Canvas, fontes: tuple[str, str], nome_teste: str, item: ItemPdf,
                      numero: int, total_itens: int, pagina: int, total_paginas: int) -> None:
    normal, negrito = fontes
    imagem = ImageReader(str(item.caminho))
    larg_img, alt_img = imagem.getSize()
    tamanho = landscape(A4) if larg_img >= alt_img else A4
    c.setPageSize(tamanho)
    largura, altura = tamanho

    # Cabeçalho
    contador = f"Evidência {numero} de {total_itens}"
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont(negrito, 11)
    largura_contador = pdfmetrics.stringWidth(contador, negrito, 11)
    c.drawString(MARGEM, altura - MARGEM - 8,
                 _cortar(nome_teste, negrito, 11, largura - 2 * MARGEM - largura_contador - 16))
    c.drawRightString(largura - MARGEM, altura - MARGEM - 8, contador)
    c.setFillColorRGB(*CINZA)
    c.setFont(normal, 9)
    c.drawString(MARGEM, altura - MARGEM - 24,
                 f"{item.rotulo}  •  {item.momento.strftime('%d/%m/%Y %H:%M:%S')}")
    c.setStrokeColorRGB(0.8, 0.8, 0.8)
    c.line(MARGEM, altura - MARGEM - 32, largura - MARGEM, altura - MARGEM - 32)

    # Imagem: cabe na área útil, centralizada na horizontal e colada no topo
    topo_area = altura - MARGEM - 44
    base_area = MARGEM + 20
    escala = min((largura - 2 * MARGEM) / larg_img, (topo_area - base_area) / alt_img, ESCALA_MAXIMA)
    w, h = larg_img * escala, alt_img * escala
    x, y = (largura - w) / 2, topo_area - h
    c.drawImage(imagem, x, y, w, h)
    c.setStrokeColorRGB(0.7, 0.7, 0.7)
    c.setLineWidth(0.5)
    c.rect(x, y, w, h, stroke=1, fill=0)

    _rodape(c, normal, largura, pagina, total_paginas)


def gerar_pdf(destino: Path, nome_teste: str, testador: str, itens: list[ItemPdf]) -> None:
    fontes = _registrar_fontes()
    total_paginas = 1 + len(itens)
    c = canvas.Canvas(str(destino), pagesize=A4)
    c.setTitle(f"Evidências - {nome_teste}")
    c.setCreator("Capturador de Evidências")
    if testador:
        c.setAuthor(testador)

    _capa(c, fontes, nome_teste, testador, itens, total_paginas)
    c.showPage()
    for numero, item in enumerate(itens, start=1):
        _pagina_evidencia(c, fontes, nome_teste, item, numero, len(itens), numero + 1, total_paginas)
        c.showPage()
    c.save()
