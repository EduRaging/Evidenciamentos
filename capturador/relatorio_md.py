"""Converte o relatório escrito pela IA (Markdown) em PDF, com as evidências em anexo.

Suporta o subconjunto que um relatório de testes usa: títulos (#, ##, ###), parágrafos,
listas (- e 1.), tabelas com barras verticais, **negrito**, *itálico*, `código` e linha (---).
Todo texto é escapado: nada do conteúdo vira marcação do PDF.
"""
from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (HRFlowable, Image, KeepTogether, ListFlowable, ListItem, PageBreak,
                                Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

MARGEM = 18 * mm
LARGURA_UTIL = A4[0] - 2 * MARGEM
ALTURA_MAX_IMAGEM = 105 * mm  # duas evidências cabem por página
AZUL = colors.HexColor("#1e4078")
CINZA = colors.HexColor("#555555")


@dataclass
class EvidenciaPdf:
    caminho: Path
    rotulo: str
    numero: int
    momento: datetime | None = None


def _fontes() -> tuple[str, str, str]:
    """(normal, negrito, itálico); Segoe UI se existir, senão Helvetica embutida."""
    pasta = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    normal, negrito = pasta / "segoeui.ttf", pasta / "segoeuib.ttf"
    if not (normal.exists() and negrito.exists()):
        return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
    pdfmetrics.registerFont(TTFont("SegoeUI", str(normal)))
    pdfmetrics.registerFont(TTFont("SegoeUI-Bold", str(negrito)))
    italico, negrito_italico = pasta / "segoeuii.ttf", pasta / "segoeuiz.ttf"
    if italico.exists() and negrito_italico.exists():
        pdfmetrics.registerFont(TTFont("SegoeUI-Italic", str(italico)))
        pdfmetrics.registerFont(TTFont("SegoeUI-BoldItalic", str(negrito_italico)))
        familia = ("SegoeUI-Italic", "SegoeUI-BoldItalic")
    else:
        familia = ("SegoeUI", "SegoeUI-Bold")
    pdfmetrics.registerFontFamily("SegoeUI", normal="SegoeUI", bold="SegoeUI-Bold",
                                  italic=familia[0], boldItalic=familia[1])
    return "SegoeUI", "SegoeUI-Bold", familia[0]


def _estilos() -> dict[str, ParagraphStyle]:
    normal, negrito, _ = _fontes()
    base = ParagraphStyle("corpo", fontName=normal, fontSize=9.5, leading=13.5, alignment=TA_LEFT,
                          spaceAfter=5)
    return {
        "corpo": base,
        "titulo": ParagraphStyle("titulo", parent=base, fontName=negrito, fontSize=20, leading=25,
                                 textColor=AZUL, spaceAfter=4),
        "subtitulo": ParagraphStyle("subtitulo", parent=base, fontSize=9, textColor=CINZA, spaceAfter=10),
        "h1": ParagraphStyle("h1", parent=base, fontName=negrito, fontSize=14.5, leading=19,
                             textColor=AZUL, spaceBefore=12, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=base, fontName=negrito, fontSize=12, leading=16,
                             spaceBefore=10, spaceAfter=4),
        "h3": ParagraphStyle("h3", parent=base, fontName=negrito, fontSize=10.5, leading=14,
                             spaceBefore=8, spaceAfter=3),
        "celula": ParagraphStyle("celula", parent=base, fontSize=8.3, leading=10.8, spaceAfter=0),
        "celula_cab": ParagraphStyle("celula_cab", parent=base, fontName=negrito, fontSize=8.3,
                                     leading=10.8, spaceAfter=0, textColor=colors.white),
        "legenda": ParagraphStyle("legenda", parent=base, fontName=negrito, fontSize=9.5, spaceAfter=3),
    }


def _inline(texto: str) -> str:
    """Escapa o texto e converte a marcação inline segura (negrito, itálico, código, <br>)."""
    t = html.escape(texto, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])", r"<i>\1</i>", t)
    t = re.sub(r"`(.+?)`", r'<font face="Courier">\1</font>', t)
    return re.sub(r"&lt;br\s*/?&gt;", "<br/>", t, flags=re.IGNORECASE)


_LINHA_TABELA = re.compile(r"^\s*\|.*\|\s*$")
_SEPARADOR = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_ITEM = re.compile(r"^\s*([-*+]|\d+[.)])\s+(.*)$")


def _celulas(linha: str) -> list[str]:
    linha = linha.strip()
    if linha.startswith("|"):
        linha = linha[1:]
    if linha.endswith("|"):
        linha = linha[:-1]
    return [c.strip() for c in linha.split("|")]


def _tabela(linhas: list[str], est: dict[str, ParagraphStyle]) -> Table:
    corpo = [_celulas(l) for i, l in enumerate(linhas) if i != 1]  # linha 1 é o separador
    colunas = max(len(l) for l in corpo)
    corpo = [l + [""] * (colunas - len(l)) for l in corpo]
    dados = [[Paragraph(_inline(c), est["celula_cab" if i == 0 else "celula"]) for c in l]
             for i, l in enumerate(corpo)]
    # cada coluna tem no mínimo a largura da sua maior palavra (nada de "CT-0/1"); o resto da
    # largura útil é dividido na proporção do tamanho do conteúdo
    minimos = []
    for c in range(colunas):
        maior_palavra = max((len(p) for l in corpo for p in re.split(r"\s+", l[c]) if p), default=3)
        minimos.append(min(maior_palavra * 4.9 + 10, LARGURA_UTIL * 0.3))
    if sum(minimos) > LARGURA_UTIL:
        minimos = [m * LARGURA_UTIL / sum(minimos) for m in minimos]
    pesos = [min(max(max(len(l[c]) for l in corpo), 6), 60) for c in range(colunas)]
    sobra = LARGURA_UTIL - sum(minimos)
    larguras = [m + sobra * p / sum(pesos) for m, p in zip(minimos, pesos)]
    tabela = Table(dados, colWidths=larguras, repeatRows=1)
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b8b8b8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f6fa")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return tabela


def _blocos(markdown: str, est: dict[str, ParagraphStyle]) -> list:
    saida: list = []
    paragrafo: list[str] = []
    itens: list[str] = []
    numerada = False
    linhas = markdown.replace("\r\n", "\n").split("\n")

    def fechar_paragrafo():
        if paragrafo:
            saida.append(Paragraph(_inline(" ".join(paragrafo)), est["corpo"]))
            paragrafo.clear()

    def fechar_lista():
        nonlocal numerada
        if itens:
            saida.append(ListFlowable(
                [ListItem(Paragraph(_inline(i), est["corpo"]), leftIndent=14) for i in itens],
                bulletType="1" if numerada else "bullet", bulletFormat="%s." if numerada else None,
                bulletFontSize=8.5, leftIndent=16))
            itens.clear()
        numerada = False

    i = 0
    while i < len(linhas):
        linha = linhas[i]
        if not linha.strip():
            fechar_paragrafo()
            fechar_lista()
        elif re.match(r"^\s*(-{3,}|\*{3,})\s*$", linha):
            fechar_paragrafo()
            fechar_lista()
            saida.append(HRFlowable(width="100%", color=colors.HexColor("#c8c8c8"), spaceBefore=4,
                                    spaceAfter=6))
        elif (achado := re.match(r"^(#{1,3})\s+(.*?)\s*#*\s*$", linha)):
            fechar_paragrafo()
            fechar_lista()
            saida.append(Paragraph(_inline(achado.group(2)), est[f"h{len(achado.group(1))}"]))
        elif _LINHA_TABELA.match(linha) and i + 1 < len(linhas) and _SEPARADOR.match(linhas[i + 1]):
            fechar_paragrafo()
            fechar_lista()
            bloco = []
            while i < len(linhas) and _LINHA_TABELA.match(linhas[i]):
                bloco.append(linhas[i])
                i += 1
            saida.append(_tabela(bloco, est))
            saida.append(Spacer(1, 6))
            continue
        elif (item := _ITEM.match(linha)):
            fechar_paragrafo()
            eh_numerada = item.group(1)[0].isdigit()
            if itens and eh_numerada != numerada:
                fechar_lista()
            numerada = eh_numerada
            itens.append(item.group(2))
        else:
            fechar_lista()
            paragrafo.append(linha.strip())
        i += 1
    fechar_paragrafo()
    fechar_lista()
    return saida


def _anexo_evidencias(evidencias: list[EvidenciaPdf], est: dict[str, ParagraphStyle]) -> list:
    blocos: list = [PageBreak(), Paragraph("Evidências", est["h1"])]
    for ev in evidencias:
        with PILImage.open(ev.caminho) as img:
            largura, altura = img.size
        escala = min(LARGURA_UTIL / largura, ALTURA_MAX_IMAGEM / altura, 1.0)
        hora = f" — {ev.momento:%d/%m/%Y %H:%M:%S}" if ev.momento else ""
        legenda = Paragraph(_inline(f"Evidência {ev.numero} — {ev.rotulo}{hora}"), est["legenda"])
        imagem = Image(str(ev.caminho), width=largura * escala, height=altura * escala, hAlign="LEFT")
        imagem.hAlign = "LEFT"
        blocos.append(KeepTogether([legenda, imagem, Spacer(1, 10)]))
    return blocos


def gerar_pdf_de_markdown(destino: Path, titulo: str, markdown: str, subtitulo: str = "",
                          evidencias: list[EvidenciaPdf] | None = None) -> int:
    """Gera o PDF e devolve o número de páginas."""
    est = _estilos()
    normal = est["corpo"].fontName

    def rodape(canvas, doc):
        canvas.saveState()
        canvas.setFont(normal, 8)
        canvas.setFillColor(CINZA)
        canvas.drawCentredString(A4[0] / 2, 10 * mm, f"Página {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(destino), pagesize=A4, leftMargin=MARGEM, rightMargin=MARGEM,
                            topMargin=MARGEM, bottomMargin=16 * mm, title=titulo,
                            author="Capturador de Evidências")
    historia = [Paragraph(_inline(titulo), est["titulo"])]
    if subtitulo:
        historia.append(Paragraph(_inline(subtitulo), est["subtitulo"]))
    historia.append(HRFlowable(width="100%", color=AZUL, thickness=1.2, spaceAfter=8))
    historia += _blocos(markdown, est)
    if evidencias:
        historia += _anexo_evidencias(evidencias, est)
    doc.build(historia, onFirstPage=rodape, onLaterPages=rodape)
    return doc.page
