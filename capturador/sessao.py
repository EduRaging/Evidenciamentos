"""Sessão de captura: guarda as evidências em andamento e fecha o teste numa pasta."""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image

from .pdf_relatorio import ItemPdf, gerar_pdf

ROTULOS = {"tela": "Tela inteira", "recorte": "Recorte"}

_CARACTERES_INVALIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_RESERVADOS = {"CON", "PRN", "AUX", "NUL",
               *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def nome_seguro(texto: str, limite: int = 80) -> str:
    """Transforma o nome do teste em nome de pasta/arquivo válido no Windows."""
    nome = _CARACTERES_INVALIDOS.sub("-", texto)
    nome = re.sub(r"\s+", " ", nome).strip(" .-")[:limite].strip(" .-")
    if not nome:
        return "teste"
    if nome.upper() in _RESERVADOS:
        return f"_{nome}"
    return nome


def _criar_pasta_unica(base: Path, nome: str) -> Path:
    for n in range(1, 1000):
        destino = base / (nome if n == 1 else f"{nome} ({n})")
        try:
            destino.mkdir()
            return destino
        except FileExistsError:
            continue
    raise OSError(f"Não foi possível criar uma pasta única para {nome!r}.")


@dataclass
class Evidencia:
    arquivo: str  # nome do PNG dentro da pasta de trabalho
    tipo: str  # "tela" | "recorte"
    hora: str  # ISO 8601

    @property
    def momento(self) -> datetime:
        return datetime.fromisoformat(self.hora)


class Sessao:
    """Evidências ainda não finalizadas, gravadas em disco (sobrevivem a fechar o app)."""

    def __init__(self, pasta_trabalho: Path) -> None:
        self.pasta = Path(pasta_trabalho)
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.nome_teste = ""
        self.evidencias: list[Evidencia] = []
        self._carregar()

    # --- persistência -------------------------------------------------
    @property
    def _indice(self) -> Path:
        return self.pasta / "sessao.json"

    def _carregar(self) -> None:
        try:
            dados = json.loads(self._indice.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.nome_teste = str(dados.get("nome_teste", ""))
        for item in dados.get("evidencias", []):
            ev = Evidencia(item["arquivo"], item["tipo"], item["hora"])
            if (self.pasta / ev.arquivo).exists():
                self.evidencias.append(ev)

    def salvar(self) -> None:
        dados = {"nome_teste": self.nome_teste, "evidencias": [asdict(e) for e in self.evidencias]}
        self._indice.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- operações ----------------------------------------------------
    def caminho(self, ev: Evidencia) -> Path:
        return self.pasta / ev.arquivo

    def adicionar(self, imagem: Image.Image, tipo: str) -> Evidencia:
        numero = max((int(Path(e.arquivo).stem) for e in self.evidencias), default=0) + 1
        ev = Evidencia(f"{numero:03d}.png", tipo, datetime.now().isoformat(timespec="seconds"))
        imagem.save(self.caminho(ev), "PNG", compress_level=3)
        self.evidencias.append(ev)
        self.salvar()
        return ev

    def remover(self, posicao: int) -> None:
        ev = self.evidencias.pop(posicao)
        self.caminho(ev).unlink(missing_ok=True)
        self.salvar()

    def descartar(self) -> None:
        for ev in self.evidencias:
            self.caminho(ev).unlink(missing_ok=True)
        self._indice.unlink(missing_ok=True)
        self.evidencias.clear()
        self.nome_teste = ""

    def finalizar(self, nome_teste: str, testador: str, pasta_base: Path | str) -> Path:
        """Cria a pasta do teste, copia as imagens, gera o PDF e limpa a sessão."""
        if not self.evidencias:
            raise ValueError("Nenhuma evidência capturada.")
        base = Path(pasta_base)
        base.mkdir(parents=True, exist_ok=True)
        nome = nome_seguro(nome_teste)
        destino = _criar_pasta_unica(base, f"{datetime.now():%Y-%m-%d_%H%M} - {nome}")
        try:
            digitos = max(2, len(str(len(self.evidencias))))
            itens = []
            for i, ev in enumerate(self.evidencias, start=1):
                final = destino / f"{i:0{digitos}d}_{ev.tipo}.png"
                shutil.copy2(self.caminho(ev), final)
                itens.append(ItemPdf(final, ROTULOS.get(ev.tipo, ev.tipo), ev.momento))
            gerar_pdf(destino / f"Evidencias - {nome}.pdf", nome_teste.strip(), testador.strip(), itens)
        except Exception:
            shutil.rmtree(destino, ignore_errors=True)  # só a pasta que acabamos de criar
            raise
        self.descartar()
        return destino
