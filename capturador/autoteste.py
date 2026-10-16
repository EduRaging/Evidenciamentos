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

from . import (__version__, arquivamento, atalhos, captura, claude_desktop, dialogo_prompt, estilo, metadados,
               miniaturas, painel_pdfs, recursos, registro_pdfs, winutil)
from .pdf_relatorio import _registrar_fontes
from .prompt_ia import Formulario, montar_prompt
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
        if not winutil.definir_icone(raiz, icone):
            raise RuntimeError("não consegui declarar o ícone da janela ao Windows")
    finally:
        raiz.destroy()
    return "Tk, ImageTk e ícone (janela e barra de tarefas) carregados"


def _identidade_do_app() -> str:
    if not winutil.definir_identidade_do_app():
        raise RuntimeError("não consegui definir a identidade do app na barra de tarefas")
    return "AppUserModelID definido"


def _atalhos_globais() -> str:
    gerenciador = atalhos.GerenciadorAtalhos(lambda _nome: None)
    try:
        erros = gerenciador.registrar({"teste": "ctrl+alt+shift+f20"})
    finally:
        gerenciador.parar()
    if erros:
        raise RuntimeError(erros)
    return "registro e remoção de atalho global"


def _finalizar_exemplo(tmp: Path) -> Path:
    sessao = Sessao(tmp / "em_andamento")
    imagem, _ = captura.capturar_monitor()
    sessao.adicionar(imagem, "tela")
    sessao.adicionar(imagem.crop((0, 0, 300, 200)), "recorte")
    return sessao.finalizar("Autoteste de acentuação", "Autoteste", tmp / "base")


def _prompt_ia() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        pasta = _finalizar_exemplo(Path(tmp))
        teste = metadados.ler(pasta)
        prompt = montar_prompt(teste, Formulario(objetivo="Autoteste"))
        for esperado in (teste.pdf, "Evidências anexadas (2)", "Autoteste de acentuação",
                         "arquivo PDF para eu baixar", "Partição de equivalência",
                         "sugeridos (não executados)"):
            if not esperado or esperado not in prompt:
                raise AssertionError(f"prompt sem {esperado!r}")
        if not callable(dialogo_prompt.abrir_dialogo_prompt):
            raise AssertionError("janela do prompt indisponível")
    return f"prompt de {len(prompt)} caracteres com PDF e evidências"


def _envio_ao_claude() -> str:
    """Monta o link do prompt completo e procura o Claude desktop (sem abri-lo)."""
    with tempfile.TemporaryDirectory() as tmp:
        teste = metadados.ler(_finalizar_exemplo(Path(tmp)))
        prompt = montar_prompt(teste, Formulario(via_mcp=True))
    if len(prompt) > claude_desktop.LIMITE_PROMPT:
        raise AssertionError(f"prompt de {len(prompt)} caracteres passa do limite do link")
    link = claude_desktop.montar_link(prompt)
    comando = claude_desktop.comando_para_abrir(link)
    if comando is None:
        return "link montado; Claude desktop não encontrado (o app copia o prompt para colar)"
    return f"link de {len(link)} caracteres pronto para o {Path(comando[0]).name} registrado"


def _miniaturas_e_arquivamento() -> str:
    """Miniaturas da lista, um item por teste e arquivar sem apagar (o que a janela nova usa)."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "base"
        pasta = _finalizar_exemplo(Path(tmp))
        raiz = tk.Tk()
        raiz.withdraw()
        try:
            png = next(pasta.glob("*.png"))
            foto = miniaturas.obter(png)
            if foto is None or (foto.width(), foto.height()) != miniaturas.TAMANHO:
                raise AssertionError("a miniatura não saiu no tamanho esperado")
            estilo.aplicar(raiz)
            botao = estilo.botao_primario(raiz, "Teste", lambda: None)
            estilo.ativar(botao, False)
        finally:
            raiz.destroy()
        testes = registro_pdfs.agrupar_por_teste(registro_pdfs.listar_pdfs(pasta.parent))
        if len(testes) != 1 or testes[0].evidencias is None or testes[0].principal is None:
            raise AssertionError(f"agrupamento inesperado: {testes}")
        destino = arquivamento.arquivar(pasta, pasta.parent)
        if pasta.exists() or not (destino / png.name).exists() or registro_pdfs.listar_pdfs(pasta.parent):
            raise AssertionError("o arquivamento não moveu a pasta inteira")
    return "miniatura, estilo, um item por teste e arquivar sem apagar"


def _registro_de_pdfs() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "base"
        pasta = _finalizar_exemplo(Path(tmp))
        (pasta.parent / ".keep").write_text("", encoding="utf-8")  # arquivo solto na base: deve ser ignorado
        itens = registro_pdfs.listar_pdfs(pasta.parent)
        if len(itens) != 1 or itens[0].tipo != registro_pdfs.TIPO_EVIDENCIAS:
            raise AssertionError(f"registro inesperado: {itens}")
        if not painel_pdfs.PainelPdfs or len(winutil.montar_dropfiles([itens[0].caminho])) <= 20:
            raise AssertionError("painel ou área de transferência indisponível")
    return "registro de PDFs, painel e formato de arquivo copiado"


def _sessao_e_pdf() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pasta = _finalizar_exemplo(tmp)
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
    ("identidade na barra de tarefas", _identidade_do_app),
    ("atalhos globais", _atalhos_globais),
    ("sessão, pasta e PDF", _sessao_e_pdf),
    ("prompt para IA", _prompt_ia),
    ("envio ao Claude desktop", _envio_ao_claude),
    ("registro de PDFs", _registro_de_pdfs),
    ("miniaturas e arquivamento", _miniaturas_e_arquivamento),
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
