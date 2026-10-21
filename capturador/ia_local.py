"""O app chama o Claude Code deste computador, sozinho, para montar o roteiro e o relatório (sem chave de API).

O Claude Code roda em modo NÃO interativo e RESTRITO: SEM ferramenta nenhuma (nem Read), numa pasta temporária
vazia, sem MCP, sem skills, sem ler as configurações do usuário, e tudo o que pediria permissão é negado. As
telas vão REDUZIDAS e dentro do próprio pedido (na memória: nenhuma cópia vai para o disco), e a IA só devolve um
JSON: quem valida e grava o roteiro ou o relatório é o app. Com as imagens no pedido o Claude responde numa única
volta, em vez de abrir uma imagem por vez (40 telas: 29 s contra 75 s). Usa o login do Claude Code do próprio
usuário (`claude auth login`, uma vez).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

from . import ciclos, fluxo_ciclo, gravacao, metadados
from .ciclos import Ciclo
from .imagens import reduzir_evidencia
from .metadados import PastaTeste
from .prompt_ciclo import montar_prompt_roteiro_local
from .prompt_ia import (STATUS_SUGERIDOS, ParteRelatorio, montar_prompt_relatorio_local,
                        montar_prompt_relatorio_unir)

log = logging.getLogger(__name__)

LADO_MAXIMO = 1568  # px, como na extensão: acima disso a IA reduz de qualquer jeito e só custa mais
MAX_IMAGENS = 40  # por pedido; no roteiro, com vários testes, cada um entra com algumas telas espaçadas.
# No relatório nenhuma tela fica de fora: um teste maior que isto é analisado em partes (`dividir_em_partes`).
MAX_PARALELO = 3  # partes do relatório que o Claude analisa ao mesmo tempo (cada uma é um processo à parte)
MIN_POR_TESTE = 3
LIMITE_IMAGEM_BYTES = 400_000  # por tela dentro do pedido
LIMITE_TOTAL_BYTES = 16_000_000  # soma das telas (o pedido todo aceita ~32 MB, e o base64 incha 1/3)
TEMPO_LIMITE_S = 25 * 60
ORCAMENTO_USD = 10.0
SEM_JANELA = 0x08000000  # CREATE_NO_WINDOW
NOVO_CONSOLE = 0x00000010  # CREATE_NEW_CONSOLE


class ErroIA(Exception):
    """Falha ao gerar o roteiro ou o relatório; a mensagem já é para o usuário."""


class NaoLogado(ErroIA):
    """O Claude Code deste computador ainda não está conectado a uma conta."""


class Cancelado(ErroIA):
    """O usuário cancelou a geração."""


# --- achar o Claude Code e o login ---------------------------------------------------------------
def _versao(pasta: Path) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", pasta.name)) or (0,)


def localizar_claude(raizes: list[Path] | None = None) -> Path | None:
    """O claude.exe mais novo que o app do Claude desktop instalou (…\\claude-code\\<versão>\\<id>\\claude.exe)."""
    if raizes is None:
        appdata = os.environ.get("APPDATA")
        raizes = [Path(appdata) / "Claude" / "claude-code"] if appdata else []
    candidatos = []
    for raiz in raizes:
        try:
            candidatos += [p for p in raiz.glob("*/*/claude.exe") if p.is_file()]
        except OSError:
            continue
    if candidatos:
        return max(candidatos, key=lambda p: (_versao(p.parent.parent), p.stat().st_mtime))
    achado = shutil.which("claude")
    return Path(achado) if achado else None


def situacao_login(exe: Path, executar: Callable = subprocess.run) -> dict:
    """O que `claude auth status` informa (conta, e-mail, organização), ou {} se não há conta ou algo deu errado."""
    try:
        r = executar([str(exe), "auth", "status"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
                     creationflags=SEM_JANELA)
        dados = json.loads(r.stdout)
    except (OSError, ValueError, subprocess.SubprocessError, AttributeError):
        return {}
    return dados if isinstance(dados, dict) and dados.get("loggedIn") else {}


def esta_logado(exe: Path, executar: Callable = subprocess.run) -> bool:
    """`claude auth status` diz se há uma conta conectada. Qualquer dúvida conta como "não"."""
    return bool(situacao_login(exe, executar))


def abrir_login(exe: Path, abrir: Callable = subprocess.Popen):
    """Abre o login do Claude Code numa janela de console VISÍVEL (o navegador abre para o usuário entrar).

    Devolve o processo, para o app saber quando o login terminou (`esperar_login`).
    """
    return abrir([str(exe), "auth", "login", "--claudeai"], creationflags=NOVO_CONSOLE)


def esperar_login(processo, exe: Path, tempo_limite: float = 600, verificar: Callable = situacao_login,
                  dormir: Callable = time.sleep, agora: Callable = time.monotonic) -> dict:
    """Espera o processo do login terminar e devolve a situação da conta ({} se não ficou conectado a tempo).

    Só consulta a conta depois que a janela do login fecha; mesmo então tenta mais duas vezes, porque a conta pode
    levar um instante para aparecer. Roda numa thread: nunca chame na interface.
    """
    limite = agora() + tempo_limite
    while agora() < limite:
        if processo.poll() is not None:
            for _ in range(3):
                conta = verificar(exe)
                if conta:
                    return conta
                dormir(2)
            return {}
        dormir(1)
    return {}


# --- as telas viram imagens reduzidas, em memória, dentro do próprio pedido ----------------------
def _espacadas(itens: list, quantas: int) -> list:
    """`quantas` itens bem distribuídos entre o primeiro e o último (ou todos, se forem poucos)."""
    if len(itens) <= quantas:
        return list(itens)
    if quantas <= 1:
        return [itens[0]]
    indices = sorted({round(k * (len(itens) - 1) / (quantas - 1)) for k in range(quantas)})
    return [itens[i] for i in indices]


def _e_atalho(caminho: Path) -> bool:
    return os.path.islink(caminho) or os.path.isjunction(caminho)


@dataclass
class Tela:
    """Uma evidência reduzida, pronta para ir dentro do pedido ao Claude."""
    teste: str  # nome da pasta do teste
    numero: int
    dados: bytes
    formato: str  # "png" ou "jpeg"
    rotulo: str  # o texto que antecede a imagem no pedido


def preparar_telas(testes: list[PastaTeste], max_imagens: int = MAX_IMAGENS) -> list[Tela]:
    """As telas dos testes, reduzidas e na memória (nada é copiado para o disco), na ordem dos testes.

    Só PNGs de verdade e dentro da pasta do teste (nada de atalhos). Com vários testes, cada um entra com algumas
    telas espaçadas. O tamanho de cada imagem respeita um teto, e o total cabe no limite de ~32 MB de um pedido.
    """
    por_teste = max(MIN_POR_TESTE, max_imagens // max(1, len(testes)))
    escolhidas = []
    for teste in testes:
        if _e_atalho(teste.pasta):
            continue
        escolhidas += [(teste, ev) for ev in _espacadas(teste.evidencias, por_teste)]
    limite = min(LIMITE_IMAGEM_BYTES, LIMITE_TOTAL_BYTES // max(1, len(escolhidas)))
    telas: list[Tela] = []
    for teste, ev in escolhidas:
        origem = teste.pasta / ev.arquivo
        try:
            if _e_atalho(origem) or origem.resolve().parent != teste.pasta.resolve():
                continue
            dados, formato = reduzir_evidencia(origem, LADO_MAXIMO, limite)  # PNG; JPEG se o PNG ficar pesado
        except (OSError, ValueError):
            continue
        rotulo = f"Evidência {ev.numero}:" if len(testes) == 1 else f'Teste "{teste.pasta.name}", evidência {ev.numero}:'
        telas.append(Tela(teste.pasta.name, ev.numero, dados, formato, rotulo))
    return telas


def resumo_das_telas(telas: list[Tela]) -> dict[str, list[int]]:
    """Nome do teste -> números das evidências enviadas (o que o prompt do roteiro lista)."""
    resumo: dict[str, list[int]] = {}
    for tela in telas:
        resumo.setdefault(tela.teste, []).append(tela.numero)
    return resumo


def montar_mensagem(prompt: str, telas: list[Tela]) -> str:
    """A mensagem de entrada do Claude Code (stream-json): o texto do pedido e, depois, cada tela com o seu rótulo."""
    partes: list[dict] = [{"type": "text", "text": prompt}]
    for tela in telas:
        partes.append({"type": "text", "text": tela.rotulo})
        partes.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/jpeg" if tela.formato == "jpeg" else "image/png",
            "data": base64.b64encode(tela.dados).decode("ascii")}})
    return json.dumps({"type": "user", "message": {"role": "user", "content": partes}}, ensure_ascii=False) + "\n"


# --- o pedido e a resposta -----------------------------------------------------------------------
def _lista(itens_tipo: dict) -> dict:
    return {"type": "array", "items": itens_tipo}


_TEXTO = {"type": "string"}
ESQUEMA_ROTEIRO = {
    "type": "object",
    "properties": {
        "casos": {"type": "array", "minItems": 1, "maxItems": ciclos.MAX_CASOS, "items": {
            "type": "object",
            "properties": {
                "id": _TEXTO, "titulo": _TEXTO, "objetivo": _TEXTO, "tecnica": _TEXTO,
                "prioridade": {"type": "string", "enum": list(ciclos.PRIORIDADES)}, "tipo": _TEXTO,
                "pre_condicoes": _lista(_TEXTO), "dados_de_teste": _lista(_TEXTO), "pos_condicoes": _lista(_TEXTO),
                "rastreio": _lista(_TEXTO),
                "passos": {"type": "array", "minItems": 1, "maxItems": ciclos.MAX_PASSOS, "items": {
                    "type": "object", "properties": {"acao": _TEXTO, "resultado_esperado": _TEXTO},
                    "required": ["acao", "resultado_esperado"]}},
                "evidencias_base": _lista({"type": "object", "properties": {"teste": _TEXTO, "numero": {"type": "integer"}},
                                           "required": ["teste", "numero"]}),
                "a_confirmar": {"type": "boolean"}},
            "required": ["id", "titulo", "objetivo", "tecnica", "prioridade", "passos"]}},
        "ciclo_sugerido": {"type": "object", "properties": {
            "objetivo": _TEXTO, "escopo": _lista(_TEXTO), "fora_do_escopo": _TEXTO, "riscos": _TEXTO, "sistema": _TEXTO,
            "criterios_entrada": _lista(_TEXTO), "criterios_saida": _lista(_TEXTO)}},
        "observacoes": _lista(_TEXTO)},
    "required": ["casos"],
}


ESQUEMA_RELATORIO = {
    "type": "object",
    "properties": {"status_sugerido": {"type": "string", "enum": list(STATUS_SUGERIDOS)}, "resumo": _TEXTO,
                   "relatorio_markdown": _TEXTO},
    "required": ["status_sugerido", "relatorio_markdown"],
}


def montar_comando(exe: Path, orcamento: float = ORCAMENTO_USD, esquema: dict | None = None) -> list[str]:
    """A linha de comando do Claude Code: não interativo, SEM ferramentas, restrito, sem MCP nem skills, sem sessão salva.

    O pedido (texto e imagens) entra pela entrada padrão em `stream-json`, que é o único formato de entrada que aceita imagens.
    """
    esquema = ESQUEMA_ROTEIRO if esquema is None else esquema
    return [str(exe), "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
            "--json-schema", json.dumps(esquema, ensure_ascii=False),
            "--tools", "", "--permission-mode", "dontAsk", "--permission-prompts", "none",
            "--restricted", "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence",
            "--max-budget-usd", f"{orcamento:g}"]


def _json_do_texto(texto: str):
    """O JSON dentro de um texto que pode vir cercado por ``` ou por frases soltas."""
    limpo = texto.strip()
    limpo = re.sub(r"^```(?:json)?\s*|\s*```$", "", limpo, flags=re.IGNORECASE)
    try:
        return json.loads(limpo)
    except ValueError:
        inicio, fim = limpo.find("{"), limpo.rfind("}")
        if 0 <= inicio < fim:
            return json.loads(limpo[inicio:fim + 1])
        raise


def _evento_final(saida: str) -> dict:
    """O evento `result` da saída `stream-json` (uma linha JSON por evento) ou, se for um JSON só, ele mesmo."""
    for linha in reversed(saida.strip().splitlines()):
        linha = linha.strip()
        if linha.startswith("{"):
            try:
                evento = json.loads(linha)
            except ValueError:
                continue
            if isinstance(evento, dict) and evento.get("type") == "result":
                return evento
    dados = json.loads(saida)
    if not isinstance(dados, dict):
        raise ValueError("resposta inesperada")
    return dados


def extrair_resposta(saida: str) -> dict:
    """O objeto (roteiro ou relatório) dentro da saída do Claude Code. ErroIA/NaoLogado se não houver."""
    try:
        dados = _evento_final(saida)
    except (ValueError, TypeError) as exc:
        raise ErroIA("O Claude Code devolveu uma resposta que o app não entendeu.") from exc
    texto = str(dados.get("result") or "")
    if dados.get("is_error"):
        if "not logged in" in texto.lower() or "/login" in texto.lower():
            raise NaoLogado("O Claude Code deste computador ainda não está conectado à sua conta.")
        raise ErroIA(f"O Claude Code recusou o pedido: {texto[:300] or 'sem detalhes'}")
    estruturado = dados.get("structured_output")
    if isinstance(estruturado, dict):
        return estruturado
    try:
        achado = _json_do_texto(texto)
    except (ValueError, TypeError) as exc:
        raise ErroIA("A resposta do Claude não veio no formato esperado; tente de novo.") from exc
    if not isinstance(achado, dict):
        raise ErroIA("A resposta do Claude não veio no formato esperado; tente de novo.")
    return achado


@dataclass
class Controle:
    """Deixa outra thread cancelar uma geração em andamento.

    Uma geração pode ter várias chamadas ao Claude ao mesmo tempo (as partes do relatório): cada uma recebe um controle
    filho (`derivar`). Cancelar o pai cancela todos os filhos; cancelar um filho cancela só ele.
    """
    processo: object | None = None
    cancelado: bool = False
    filhos: list = field(default_factory=list, repr=False, compare=False)
    _trava: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def derivar(self) -> "Controle":
        """Um controle para uma chamada que roda junto com outras; já nasce cancelado se o pai foi cancelado."""
        filho = Controle()
        with self._trava:
            filho.cancelado = self.cancelado
            self.filhos.append(filho)
        return filho

    def cancelar(self) -> None:
        with self._trava:
            self.cancelado = True
            filhos = list(self.filhos)
        for filho in filhos:
            filho.cancelar()
        processo = self.processo
        if processo is not None:
            try:
                processo.terminate()
            except OSError:
                pass


def executar(exe: Path, entrada: str, pasta_de_trabalho: Path, controle: Controle | None = None,
             abrir_processo: Callable = subprocess.Popen, tempo_limite: float = TEMPO_LIMITE_S,
             esquema: dict | None = None) -> dict:
    """Roda o Claude Code com a `entrada` (pela entrada padrão) na pasta de trabalho e devolve o objeto que ele responde."""
    controle = controle or Controle()
    if controle.cancelado:
        raise Cancelado("Geração cancelada.")
    try:
        processo = abrir_processo(montar_comando(exe, esquema=esquema), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, cwd=str(pasta_de_trabalho), text=True, encoding="utf-8", errors="replace",
                                  creationflags=SEM_JANELA)
    except OSError as exc:
        raise ErroIA("Não consegui iniciar o Claude Code deste computador.") from exc
    controle.processo = processo
    if controle.cancelado:  # cancelado entre abrir o processo e guardá-lo: ninguém o teria encerrado
        try:
            processo.terminate()
        except OSError:
            pass
    try:
        saida, erro = processo.communicate(entrada, timeout=tempo_limite)
    except subprocess.TimeoutExpired as exc:
        processo.kill()
        processo.communicate()
        raise ErroIA(f"O Claude demorou mais de {int(tempo_limite // 60)} minutos e foi interrompido.") from exc
    finally:
        controle.processo = None
    if controle.cancelado:
        raise Cancelado("Geração cancelada.")
    if not (saida or "").strip():
        raise ErroIA("O Claude Code não devolveu nada" + (f": {(erro or '').strip()[:200]}" if (erro or "").strip() else "."))
    return extrair_resposta(saida)


def gerar_roteiro(ciclo: Ciclo, base: Path | str, exe: Path, controle: Controle | None = None,
                  abrir_processo: Callable = subprocess.Popen,
                  tempo_limite: float = TEMPO_LIMITE_S) -> tuple[Path, int]:
    """Gera o roteiro do ciclo sozinho e o grava. Devolve (arquivo, nº de casos). Levanta ErroIA com a explicação.

    As telas vão reduzidas, dentro do pedido; o Claude roda numa pasta temporária vazia, apagada no fim.
    """
    testes, ausentes = fluxo_ciclo.testes_de_referencia(ciclo, base)
    telas = preparar_telas(testes)
    if testes and not telas:
        raise ErroIA("Não consegui preparar as telas dos testes de referência para enviar.")
    mensagem = montar_mensagem(montar_prompt_roteiro_local(ciclo, resumo_das_telas(telas), ausentes), telas)
    with tempfile.TemporaryDirectory(prefix="capt_ia_") as vazia:
        bruto = executar(exe, mensagem, Path(vazia), controle, abrir_processo, tempo_limite)
    try:  # o app é quem valida: a IA só sugere. Nada é gravado se algo não servir.
        casos = ciclos.validar_casos(bruto.get("casos"))
        arquivo = ciclos.gravar_roteiro(ciclo.pasta, casos, bruto.get("observacoes"),
                                        ciclo_sugerido=bruto.get("ciclo_sugerido"))
    except ValueError as exc:
        raise ErroIA(f"O roteiro devolvido pelo Claude não passou na validação do app: {exc}") from exc
    return arquivo, len(casos)


def _teste_da_base(pasta: Path | str, base: Path | str) -> PastaTeste:
    """O teste em `pasta`, só se for mesmo uma pasta de teste direto dentro de `base` (nada de atalhos nem pastas de trabalho)."""
    pasta, base = Path(pasta), Path(base)
    mesma_pasta = os.path.normcase(os.path.abspath(pasta.parent)) == os.path.normcase(os.path.abspath(base))
    if pasta.name.startswith(("_", ".")) or not mesma_pasta or not pasta.is_dir() or _e_atalho(pasta):
        raise ErroIA("Este teste não está na pasta de evidências configurada.")
    try:
        teste = metadados.ler(pasta.resolve())  # resolvida: é com ela que gravacao confere onde estão as imagens
    except (OSError, ValueError) as exc:
        raise ErroIA(f"Não consegui ler o teste: {exc}") from exc
    if not teste.evidencias:
        raise ErroIA("Este teste não tem imagens de evidência para o Claude analisar.")
    return teste


def dividir_em_partes(evidencias: list, maximo: int | None = None) -> list[list]:
    """As evidências em trechos consecutivos, do mesmo tamanho e com até `maximo` (padrão: MAX_IMAGENS) cada.

    É o que deixa o relatório olhar TODAS as telas: 44 viram 22 + 22, em vez de 40 espaçadas com 4 de fora.
    """
    maximo = MAX_IMAGENS if maximo is None else maximo
    if not evidencias:
        return []
    quantas = -(-len(evidencias) // maximo)
    tamanho = -(-len(evidencias) // quantas)
    return [evidencias[i:i + tamanho] for i in range(0, len(evidencias), tamanho)]


def _pior_status(relatos: list[ParteRelatorio]) -> str:
    for status in ("Reprovado", "Inconclusivo", "Aprovado"):
        if any(r.status == status for r in relatos):
            return status
    return "Inconclusivo"


def _pedir_relatorio(exe: Path, mensagem: str, controle: Controle | None, abrir_processo: Callable,
                     tempo_limite: float) -> dict:
    """Uma chamada ao Claude, numa pasta temporária vazia (apagada no fim), que devolve status, resumo e texto do relatório."""
    with tempfile.TemporaryDirectory(prefix="capt_ia_") as vazia:
        bruto = executar(exe, mensagem, Path(vazia), controle, abrir_processo, tempo_limite, esquema=ESQUEMA_RELATORIO)
    texto = bruto.get("relatorio_markdown")
    if not isinstance(texto, str) or not texto.strip():
        raise ErroIA("O Claude não devolveu o texto do relatório; tente de novo.")
    status, resumo = bruto.get("status_sugerido"), bruto.get("resumo")
    return {"status": status if status in STATUS_SUGERIDOS else "Inconclusivo",
            "resumo": resumo if isinstance(resumo, str) else "", "texto": texto.strip()}


def _juntar_partes(teste: PastaTeste, relatos: list[ParteRelatorio], exe: Path, controle: Controle | None,
                   abrir_processo: Callable, tempo_limite: float) -> ParteRelatorio:
    """Os relatórios das partes num só. O Claude junta (chamada só com texto); se ele falhar, o app empilha as partes.

    Falta de login e cancelamento seguem como estão. Qualquer outra falha não pode jogar fora o trabalho já feito:
    o documento sai com as partes uma após a outra e um aviso, no próprio texto, de que não foram reunidas.
    """
    primeira, ultima = min(r.primeira for r in relatos), max(r.ultima for r in relatos)
    try:
        feito = _pedir_relatorio(exe, montar_mensagem(montar_prompt_relatorio_unir(teste, relatos), []), controle,
                                 abrir_processo, tempo_limite)
        return ParteRelatorio(primeira, ultima, feito["status"], feito["resumo"], feito["texto"])
    except (Cancelado, NaoLogado):
        raise
    except ErroIA as exc:
        log.warning("O Claude não reuniu as partes do relatório de %s: %s", teste.pasta.name, exc)
        corpo = "\n\n---\n\n".join(f"# Parte {i} de {len(relatos)}: evidências {r.primeira} a {r.ultima}\n\n{r.markdown}"
                                  for i, r in enumerate(relatos, 1))
        aviso = (f"**Atenção:** o Claude não conseguiu reunir as {len(relatos)} partes num relatório só ({exc}). Abaixo estão "
                 "os relatórios das partes, um após o outro; os IDs dos casos recomeçam em cada parte.")
        return ParteRelatorio(primeira, ultima, _pior_status(relatos), "", f"{aviso}\n\n{corpo}")


def _analisar_parte(teste: PastaTeste, k: int, total: int, grupo: list, exe: Path, controle: Controle | None,
                    abrir_processo: Callable, tempo_limite: float) -> ParteRelatorio:
    """Uma parte do teste: prepara as telas dela (só estas ficam na memória), pede ao Claude e devolve o relatório da parte."""
    numeros = [e.numero for e in grupo]
    if controle is not None and controle.cancelado:  # uma parte que ainda nem começou não gasta nada
        raise Cancelado("Geração cancelada.")
    telas = preparar_telas([replace(teste, evidencias=grupo)], max_imagens=len(grupo))
    if not telas:
        raise ErroIA("Não consegui preparar as telas do teste para enviar." if total == 1 else
                     f"Não consegui preparar as telas das evidências {min(numeros)} a {max(numeros)} para enviar.")
    parte = (k, total, numeros) if total > 1 else None
    mensagem = montar_mensagem(montar_prompt_relatorio_local(teste, [t.numero for t in telas], parte), telas)
    del telas
    feito = _pedir_relatorio(exe, mensagem, controle, abrir_processo, tempo_limite)
    return ParteRelatorio(min(numeros), max(numeros), feito["status"], feito["resumo"], feito["texto"])


def _analisar_partes(teste: PastaTeste, grupos: list[list], exe: Path, controle: Controle | None,
                     abrir_processo: Callable, tempo_limite: float, avisar: Callable[[str], None]) -> list[ParteRelatorio]:
    """Os relatórios das partes, na ordem do teste. As partes rodam AO MESMO TEMPO (até MAX_PARALELO), uma chamada cada.

    Se uma falhar, as outras são interrompidas na hora (não adianta pagar por um relatório que já não sai) e sobe o erro
    da primeira que falhou. Se foi o usuário quem cancelou, sobe o cancelamento. `avisar` só é chamado por quem chamou
    esta função (nunca pelas threads das partes).
    """
    total = len(grupos)
    if total == 1:
        return [_analisar_parte(teste, 1, 1, grupos[0], exe, controle, abrir_processo, tempo_limite)]
    pai = controle or Controle()
    simultaneas = min(total, MAX_PARALELO)
    avisar(f"em {total} partes " + ("ao mesmo tempo" if simultaneas == total else f"({simultaneas} por vez)"))
    filhos = [pai.derivar() for _ in grupos]
    relatos: list[ParteRelatorio | None] = [None] * total
    primeiro_erro: Exception | None = None
    prontas = 0
    with ThreadPoolExecutor(max_workers=simultaneas, thread_name_prefix="parte-relatorio") as pool:
        futuros = {pool.submit(_analisar_parte, teste, k, total, grupo, exe, filho, abrir_processo, tempo_limite): k - 1
                   for k, (grupo, filho) in enumerate(zip(grupos, filhos), 1)}
        for futuro in as_completed(futuros):
            try:
                relatos[futuros[futuro]] = futuro.result()
            except Exception as exc:  # noqa: BLE001 - qualquer falha de uma parte derruba as outras e sobe depois
                if primeiro_erro is None:
                    primeiro_erro = exc
                    for filho in filhos:
                        filho.cancelar()
                continue
            prontas += 1
            if primeiro_erro is None:
                avisar(f"{prontas} de {total} partes prontas")
    if pai.cancelado:
        raise Cancelado("Geração cancelada.")
    if primeiro_erro is not None:
        raise primeiro_erro
    return [r for r in relatos if r is not None]


def gerar_relatorio(pasta: Path | str, base: Path | str, exe: Path, controle: Controle | None = None,
                    abrir_processo: Callable = subprocess.Popen, tempo_limite: float = TEMPO_LIMITE_S,
                    progresso: Callable[[str], None] | None = None) -> dict:
    """Gera sozinho o relatório do teste em `pasta` e o grava em PDF na própria pasta. Devolve os dados do arquivo.

    As telas vão reduzidas, dentro do pedido, e TODAS são analisadas: até MAX_IMAGENS cabem num pedido só; um teste
    maior é dividido em partes consecutivas, analisadas ao mesmo tempo (uma chamada por parte, até MAX_PARALELO), e uma
    última chamada (só com texto) junta os relatórios. A IA devolve só o texto: o app põe a capa, anexa as imagens e
    grava o PDF (nunca sobrescreve). `progresso` recebe "em 3 partes ao mesmo tempo", "1 de 3 partes prontas" e
    "juntando as partes" (só quando há mais de uma parte); chamado sempre pela thread de quem chamou. Levanta ErroIA.
    """
    teste = _teste_da_base(pasta, base)
    avisar = progresso or (lambda _texto: None)
    relatos = _analisar_partes(teste, dividir_em_partes(teste.evidencias), exe, controle, abrir_processo, tempo_limite, avisar)
    if len(relatos) > 1:
        avisar("juntando as partes")
    final = relatos[0] if len(relatos) == 1 else _juntar_partes(teste, relatos, exe, controle, abrir_processo, tempo_limite)
    texto = f"**Status sugerido pela IA:** {final.status} (a decisão final é do testador).\n\n{final.markdown}\n"
    try:
        return gravacao.gravar_relatorio_pdf(teste, f"Relatório de testes - {teste.nome_teste}", texto, True)
    except ValueError as exc:
        raise ErroIA(f"Não consegui gravar o relatório: {exc}") from exc
