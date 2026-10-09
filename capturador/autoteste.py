"""Autoteste do ambiente: valida, no próprio .exe, o que costuma quebrar ao empacotar.

Uso:  CapturadorEvidencias.exe --autoteste resultado.txt
O .exe não tem console, então o relatório vai para o arquivo informado.
Código de saída: 0 = tudo certo, 1 = alguma verificação falhou.
"""
from __future__ import annotations

import re
import tempfile
import tkinter as tk
import traceback
from pathlib import Path

from PIL import Image, ImageTk

from . import __version__, atalhos, captura, recursos
from .pdf_relatorio import _registrar_fontes
from .sessao import Sessao


def _captura_da_tela() -> str:
    imagem, retangulo = captura.capturar_monitor()
    esperado = (retangulo[2] - retangulo[0], retangulo[3] - retangulo[1])
    if imagem.size != esperado:
        raise AssertionError(f"imagem {imagem.size} difere do monitor {esperado}")
    return f"{imagem.size[0]}x{imagem.size[1]}"


def _tk_com_imagem() -> str:
    raiz = tk.Tk()
    try:
        raiz.withdraw()
        ImageTk.PhotoImage(Image.new("RGB", (40, 30), "red"), master=raiz)
        icone = recursos.caminho("assets/icone.ico")
        if not icone.exists():
            raise FileNotFoundError(f"ícone ausente: {icone.name}")
        raiz.iconbitmap(default=str(icone))
    finally:
        raiz.destroy()
    return "Tk, ImageTk e ícone carregados"


def _atalhos_globais() -> str:
    gerenciador = atalhos.GerenciadorAtalhos(lambda _nome: None)
    try:
        erros = gerenciador.registrar({"teste": "ctrl+alt+shift+f20"})
    finally:
        gerenciador.parar()
    if erros:
        raise RuntimeError(erros)
    return "registro e remoção de atalho global"


def _sessao_e_pdf() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        sessao = Sessao(tmp / "em_andamento")
        imagem, _ = captura.capturar_monitor()
        sessao.adicionar(imagem, "tela")
        sessao.adicionar(imagem.crop((0, 0, 300, 200)), "recorte")
        pasta = sessao.finalizar("Autoteste de acentuação", "Autoteste", tmp / "base")
        pdfs = list(pasta.glob("*.pdf"))
        if len(pdfs) != 1:
            raise AssertionError(f"esperava 1 PDF, achou {len(pdfs)}")
        dados = pdfs[0].read_bytes()
        paginas = len(re.findall(rb"/Type /Page\b", dados))
        if not dados.startswith(b"%PDF") or paginas != 3:
            raise AssertionError(f"PDF inválido (páginas={paginas})")
    return f"pasta + PDF de {paginas} páginas, fonte {_registrar_fontes()[0]}"


VERIFICACOES = (
    ("captura da tela", _captura_da_tela),
    ("interface Tk e imagens", _tk_com_imagem),
    ("atalhos globais", _atalhos_globais),
    ("sessão, pasta e PDF", _sessao_e_pdf),
)


def executar(arquivo_resultado: str) -> int:
    captura.ativar_dpi()
    linhas = [f"Capturador de Evidências {__version__}"]
    tudo_ok = True
    for nome, verificacao in VERIFICACOES:
        try:
            linhas.append(f"OK     {nome}: {verificacao()}")
        except Exception:  # noqa: BLE001 - o objetivo é relatar qualquer falha
            tudo_ok = False
            linhas.append(f"FALHA  {nome}:\n{traceback.format_exc()}")
    linhas.append("RESULTADO: " + ("APROVADO" if tudo_ok else "REPROVADO"))
    Path(arquivo_resultado).write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return 0 if tudo_ok else 1
