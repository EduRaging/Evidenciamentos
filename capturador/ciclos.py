"""Ciclos (rodadas) de teste: parâmetros, roteiro de casos gerado pela IA e a validação de tudo isso.

O roteiro é escrito por uma IA e lido de arquivo: nada disso é confiável. Estrutura, tamanhos e
textos são validados tanto ao GRAVAR (pela extensão) quanto ao LER (pelo app), e os textos viram
linhas simples, sem caracteres de controle nem de direção.

Pasta de um ciclo:  <pasta de evidências>\\_ciclos\\<AAAA-MM-DD_HHMM - Nome>\\
    ciclo.json         parâmetros da rodada (o usuário preenche)
    roteiro-001.json   casos de teste gerados pela IA (cada geração nova cria o próximo número)
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

from .metadados import _texto_seguro
from .sessao import nome_seguro

PASTA_CICLOS = "_ciclos"  # com "_": o registro de testes e o servidor MCP ignoram, sem confundir com um teste
ARQUIVO_CICLO = "ciclo.json"
_PADRAO_ROTEIRO = re.compile(r"^roteiro-(\d{3})\.json$", re.IGNORECASE)  # o Windows não distingue maiúsculas
LIMITE_JSON_BYTES = 2_000_000
MAX_CASOS = 80
MAX_PASSOS = 30
MAX_ITENS = 12  # itens por lista (pré-condições, dados, critérios...)
MAX_ESCOPO = 20
MAX_TESTES_BASE = 12

TIPOS_DE_RODADA = ("Funcional", "Regressão", "Confirmação de correção", "Fumaça")
PRIORIDADES = ("Alta", "Média", "Baixa")

CRITERIOS_ENTRADA_PADRAO = (
    "Ambiente de teste disponível e estável",
    "Versão a testar implantada e identificada",
    "Usuários e dados de teste disponíveis",
    "Roteiro de testes revisado pelo testador",
    "Acesso às funcionalidades do escopo",
)
CRITERIOS_SAIDA_PADRAO = (
    "Todos os casos de prioridade Alta executados",
    "Pelo menos 90% dos casos planejados executados",
    "Nenhum defeito crítico ou de severidade alta em aberto",
    "Todo defeito encontrado registrado com evidência",
    "Relatório de execução do ciclo emitido",
)


def _sem_acento(texto: str) -> str:
    base = unicodedata.normalize("NFD", str(texto).casefold())
    return "".join(c for c in base if unicodedata.category(c) != "Mn")


def _canonico(valor, opcoes: tuple[str, ...], padrao: str | None = None) -> str:
    """O valor da lista `opcoes` que corresponde ao texto (sem acento nem maiúsculas)."""
    chave = _sem_acento(valor).strip()
    for opcao in opcoes:
        if _sem_acento(opcao) == chave:
            return opcao
    if padrao is not None and not chave:
        return padrao
    raise ValueError(f"Valor inválido {str(valor)[:40]!r}; use um de: {', '.join(opcoes)}.")


# --- ciclo ---------------------------------------------------------------------------------------
@dataclass
class Ciclo:
    """Uma rodada de testes. O usuário só escolhe os testes de referência (as telas capturadas):
    o que ele deixar em branco a IA propõe a partir das evidências (veja `definicao_efetiva`)."""
    pasta: Path
    nome: str
    objetivo: str = ""
    tipo: str = "Funcional"
    sistema: str = ""
    versao_sistema: str = ""
    ambiente: str = ""
    escopo: list[str] = field(default_factory=list)
    fora_do_escopo: str = ""
    riscos: str = ""
    testador: str = ""
    inicio: str = ""  # AAAA-MM-DD ou vazio
    fim: str = ""
    testes_base: list[str] = field(default_factory=list)  # nomes das pastas de teste usadas como referência
    criterios_entrada: list[str] | None = None  # None = automático (a IA propõe; senão, o padrão do CTFL)
    criterios_saida: list[str] | None = None
    observacoes: str = ""
    criado_em: str = ""


def _lista(valor, limite_itens: int, limite_texto: int, campo: str) -> list[str]:
    if valor is None or valor == "":
        return []
    if isinstance(valor, str):
        valor = [valor]
    if not isinstance(valor, list) or len(valor) > limite_itens:
        raise ValueError(f"{campo}: deve ser uma lista de até {limite_itens} itens.")
    itens = [_texto_seguro(v, limite_texto) for v in valor if not isinstance(v, (dict, list))]
    if len(itens) != len(valor):
        raise ValueError(f"{campo}: cada item deve ser um texto.")
    return [i for i in itens if i]


def _data(valor, campo: str) -> str:
    texto = _texto_seguro(valor or "", 10)
    if not texto:
        return ""
    try:
        date.fromisoformat(texto)
    except ValueError as exc:
        raise ValueError(f"{campo}: use a data no formato AAAA-MM-DD.") from exc
    return texto


def _nome_simples(nome: str, campo: str) -> str:
    nome = str(nome).strip()
    if (not nome or nome in (".", "..") or len(nome) > 200 or any(c in nome for c in '/\\:\x00')
            or Path(nome).name != nome):
        raise ValueError(f"{campo}: nome de pasta inválido.")
    return nome


def validar_parametros(dados: dict) -> dict:
    """Parâmetros de um ciclo, validados e limpos (ValueError em português se algo não servir)."""
    if not isinstance(dados, dict):
        raise ValueError("Os parâmetros do ciclo devem ser um objeto.")
    nome = _texto_seguro(dados.get("nome", ""), 100)
    objetivo = _texto_seguro(dados.get("objetivo", ""), 500)
    if not nome:
        raise ValueError("Dê um nome ao ciclo.")
    inicio, fim = _data(dados.get("inicio"), "início"), _data(dados.get("fim"), "fim")
    if inicio and fim and fim < inicio:
        raise ValueError("A data final não pode ser anterior à inicial.")
    bases = [_nome_simples(n, "testes de referência") for n in _lista(dados.get("testes_base"), MAX_TESTES_BASE, 200,
                                                                      "testes de referência")]
    if not objetivo and not bases:
        raise ValueError("Escolha ao menos um teste de referência (as telas capturadas) ou informe o objetivo.")
    entrada = dados.get("criterios_entrada")
    saida = dados.get("criterios_saida")
    return {
        "nome": nome, "objetivo": objetivo,
        "tipo": _canonico(dados.get("tipo") or "", TIPOS_DE_RODADA, TIPOS_DE_RODADA[0]),
        "sistema": _texto_seguro(dados.get("sistema", ""), 100),
        "versao_sistema": _texto_seguro(dados.get("versao_sistema", ""), 60),
        "ambiente": _texto_seguro(dados.get("ambiente", ""), 100),
        "escopo": _lista(dados.get("escopo"), MAX_ESCOPO, 200, "escopo"),
        "fora_do_escopo": _texto_seguro(dados.get("fora_do_escopo", ""), 400),
        "riscos": _texto_seguro(dados.get("riscos", ""), 400),
        "testador": _texto_seguro(dados.get("testador", ""), 100),
        "inicio": inicio, "fim": fim, "testes_base": list(dict.fromkeys(bases)),
        # None = "automático": a IA propõe a partir das evidências; sem proposta vale o padrão do CTFL
        "criterios_entrada": _lista(entrada, MAX_ITENS, 300, "critérios de entrada") if entrada is not None else None,
        "criterios_saida": _lista(saida, MAX_ITENS, 300, "critérios de saída") if saida is not None else None,
        "observacoes": _texto_seguro(dados.get("observacoes", ""), 500),
    }


def nome_automatico(nomes_dos_testes: list[str]) -> str:
    """Nome do ciclo quando o usuário não escolhe um: derivado dos testes de referência."""
    nomes = [n for n in (_texto_seguro(n, 60) for n in nomes_dos_testes) if n]
    if not nomes:
        return "Ciclo de testes"
    return f"Ciclo - {nomes[0]}" + (f" e mais {len(nomes) - 1}" if len(nomes) > 1 else "")


def _e_atalho(caminho: Path) -> bool:
    return os.path.islink(caminho) or os.path.isjunction(caminho)


def pasta_dos_ciclos(base: Path | str) -> Path:
    return Path(base) / PASTA_CICLOS


def criar_ciclo(base: Path | str, dados: dict, agora: datetime | None = None) -> Ciclo:
    """Cria a pasta do ciclo e grava o ciclo.json. ValueError se os parâmetros não servirem."""
    limpos = validar_parametros(dados)
    raiz = pasta_dos_ciclos(base)
    if raiz.exists() and (not raiz.is_dir() or _e_atalho(raiz)):
        raise ValueError(f'"{PASTA_CICLOS}" na pasta de evidências não é uma pasta comum.')
    raiz.mkdir(parents=True, exist_ok=True)
    agora = agora or datetime.now()
    prefixo = f"{agora:%Y-%m-%d_%H%M} - {nome_seguro(limpos['nome'])}"
    for n in range(1, 100):
        destino = raiz / (prefixo if n == 1 else f"{prefixo} ({n})")
        try:
            destino.mkdir()
            break
        except FileExistsError:
            continue
    else:
        raise ValueError("Já existem ciclos demais com esse nome; escolha outro.")
    limpos["criado_em"] = agora.isoformat(timespec="seconds")
    with (destino / ARQUIVO_CICLO).open("x", encoding="utf-8") as f:
        json.dump({"versao": 1, **limpos}, f, ensure_ascii=False, indent=2)
    return Ciclo(pasta=destino, **limpos)


def ler_ciclo(pasta: Path | str) -> Ciclo:
    """Lê (e revalida) o ciclo.json de uma pasta de ciclo. ValueError se não for um ciclo válido."""
    pasta = Path(pasta)
    arquivo = pasta / ARQUIVO_CICLO
    try:
        if not pasta.is_dir() or _e_atalho(pasta) or _e_atalho(arquivo) or arquivo.stat().st_size > LIMITE_JSON_BYTES:
            raise ValueError("pasta ou arquivo inválido")
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        criado = _texto_seguro(dados.get("criado_em", ""), 30) if isinstance(dados, dict) else ""
        return Ciclo(pasta=pasta, criado_em=criado, **validar_parametros(dados))
    except (OSError, ValueError, TypeError, RecursionError, UnicodeError, AttributeError) as exc:
        raise ValueError("Esta pasta não tem um ciclo válido (ciclo.json ausente ou inválido).") from exc


def listar_ciclos(base: Path | str) -> list[Ciclo]:
    """Ciclos válidos da pasta de evidências, do mais recente para o mais antigo (inválidos são ignorados)."""
    raiz = pasta_dos_ciclos(base)
    if not raiz.is_dir() or _e_atalho(raiz):
        return []
    achados = []
    try:
        pastas = list(raiz.iterdir())
    except OSError:
        return []
    for pasta in pastas:
        try:
            if pasta.name.startswith(("_", ".")) or not pasta.is_dir():
                continue
            achados.append(ler_ciclo(pasta))
        except (ValueError, OSError):
            continue
    achados.sort(key=lambda c: (c.criado_em, c.pasta.name), reverse=True)
    return achados


def resolver_ciclo(base: Path | str, nome: str) -> Path:
    """Pasta do ciclo pelo nome, confinada a `<base>\\_ciclos`. ValueError se for inválida."""
    nome = (nome or "").strip()
    if (not nome or nome in (".", "..") or nome.startswith(("_", ".")) or any(c in nome for c in '/\\:\x00')):
        raise ValueError("Informe só o nome da pasta do ciclo, como aparece na janela Ciclos do app.")
    raiz = pasta_dos_ciclos(base)
    nao_achado = ValueError(f"Ciclo não encontrado: {nome!r}.")
    if not raiz.is_dir() or _e_atalho(raiz):
        raise nao_achado
    candidata = raiz / nome
    if _e_atalho(candidata):
        raise nao_achado
    pasta = candidata.resolve()
    if pasta.parent != raiz.resolve() or not pasta.is_dir():
        raise nao_achado
    return pasta


# --- roteiro (casos de teste) --------------------------------------------------------------------
@dataclass
class Passo:
    acao: str
    resultado_esperado: str


@dataclass
class Caso:
    id: str
    titulo: str
    objetivo: str
    tecnica: str
    prioridade: str
    passos: list[Passo]
    tipo: str = "Funcional"
    pre_condicoes: list[str] = field(default_factory=list)
    dados_de_teste: list[str] = field(default_factory=list)
    pos_condicoes: list[str] = field(default_factory=list)
    rastreio: list[str] = field(default_factory=list)
    evidencias_base: list[dict] = field(default_factory=list)  # [{"teste": pasta, "numero": n}]
    a_confirmar: bool = False  # o resultado esperado é hipótese (a IA não viu a regra nas evidências)


@dataclass
class Roteiro:
    arquivo: Path
    numero: int
    gerado_em: str
    casos: list[Caso]
    observacoes: list[str]
    ciclo_sugerido: dict = field(default_factory=dict)  # o que a IA propôs para o que o usuário não preencheu


def validar_ciclo_sugerido(bruto) -> dict:
    """A definição do ciclo proposta pela IA (objetivo, escopo, riscos, critérios...). {} se não veio."""
    if bruto is None or bruto == {}:
        return {}
    if not isinstance(bruto, dict):
        raise ValueError("`ciclo_sugerido` deve ser um objeto com objetivo, escopo, riscos e critérios.")
    saida: dict = {}
    for chave, limite in (("objetivo", 500), ("sistema", 100), ("ambiente", 100), ("fora_do_escopo", 400),
                          ("riscos", 400)):
        texto = _texto_seguro(bruto.get(chave, ""), limite)
        if texto:
            saida[chave] = texto
    for chave, itens, limite in (("escopo", MAX_ESCOPO, 200), ("criterios_entrada", MAX_ITENS, 300),
                                 ("criterios_saida", MAX_ITENS, 300)):
        lista = _lista(bruto.get(chave), itens, limite, f"ciclo_sugerido.{chave}")
        if lista:
            saida[chave] = lista
    return saida


def definicao_efetiva(ciclo: Ciclo, roteiro: Roteiro | None) -> dict:
    """O ciclo "de verdade": o que o usuário preencheu vale; o resto vem da proposta da IA e, por último,
    do padrão do CTFL (critérios). Devolve também `origem` ("usuário" | "IA" | "padrão") de cada item."""
    sugerido = roteiro.ciclo_sugerido if roteiro else {}
    efetiva: dict = {}
    origem: dict = {}
    campos = {"objetivo": ciclo.objetivo, "escopo": ciclo.escopo, "fora_do_escopo": ciclo.fora_do_escopo,
              "riscos": ciclo.riscos, "sistema": ciclo.sistema, "ambiente": ciclo.ambiente,
              "criterios_entrada": ciclo.criterios_entrada, "criterios_saida": ciclo.criterios_saida}
    padroes = {"criterios_entrada": list(CRITERIOS_ENTRADA_PADRAO), "criterios_saida": list(CRITERIOS_SAIDA_PADRAO)}
    for chave, do_usuario in campos.items():
        if do_usuario is not None and do_usuario != "" and do_usuario != []:
            efetiva[chave], origem[chave] = do_usuario, "usuário"
        elif sugerido.get(chave):
            efetiva[chave], origem[chave] = sugerido[chave], "IA"
        elif chave in padroes:
            efetiva[chave], origem[chave] = padroes[chave], "padrão"
        else:
            efetiva[chave], origem[chave] = ([] if isinstance(do_usuario, list) else ""), ""
    efetiva["origem"] = origem
    return efetiva


_ID_CASO = re.compile(r"^[A-Za-z]{1,5}-\d{1,4}$")


def _obrigatorio(valor, limite: int, campo: str) -> str:
    texto = _texto_seguro(valor if valor is not None else "", limite)
    if not texto:
        raise ValueError(f"{campo}: obrigatório (até {limite} caracteres).")
    return texto


def validar_casos(brutos) -> list[Caso]:
    """Valida a lista de casos vinda da IA (ou de um arquivo). ValueError lista o que corrigir."""
    if not isinstance(brutos, list) or not brutos:
        raise ValueError("`casos` deve ser uma lista com ao menos um caso.")
    if len(brutos) > MAX_CASOS:
        raise ValueError(f"Casos demais: no máximo {MAX_CASOS} por roteiro (vieram {len(brutos)}).")
    casos: list[Caso] = []
    ids: set[str] = set()
    problemas: list[str] = []
    for i, bruto in enumerate(brutos):
        local = f"casos[{i}]"
        try:
            casos.append(_validar_caso(bruto, local, ids))
        except ValueError as exc:
            problemas.append(str(exc))
            if len(problemas) >= 8:
                problemas.append("(há mais problemas; corrija estes primeiro)")
                break
    if problemas:
        raise ValueError("Roteiro recusado, corrija e envie de novo:\n- " + "\n- ".join(problemas))
    return casos


def _validar_caso(bruto, local: str, ids: set[str]) -> Caso:
    if not isinstance(bruto, dict):
        raise ValueError(f"{local}: cada caso deve ser um objeto.")
    id_ = _texto_seguro(bruto.get("id", ""), 12).upper()
    if not _ID_CASO.match(id_):
        raise ValueError(f'{local}.id: use o formato "CT-01" (letras, hífen e número).')
    if id_ in ids:
        raise ValueError(f"{local}.id: {id_} repetido.")
    ids.add(id_)
    passos_brutos = bruto.get("passos")
    if not isinstance(passos_brutos, list) or not 1 <= len(passos_brutos) <= MAX_PASSOS:
        raise ValueError(f"{local}.passos: lista de 1 a {MAX_PASSOS} passos, cada um com `acao` e `resultado_esperado`.")
    passos = []
    for j, passo in enumerate(passos_brutos):
        if not isinstance(passo, dict):
            raise ValueError(f"{local}.passos[{j}]: deve ser um objeto com `acao` e `resultado_esperado`.")
        passos.append(Passo(_obrigatorio(passo.get("acao"), 400, f"{local}.passos[{j}].acao"),
                            _obrigatorio(passo.get("resultado_esperado"), 400, f"{local}.passos[{j}].resultado_esperado")))
    try:
        prioridade = _canonico(bruto.get("prioridade", ""), PRIORIDADES)
    except ValueError as exc:
        raise ValueError(f"{local}.prioridade: {exc}") from exc
    evidencias = []
    brutas = bruto.get("evidencias_base") or []
    if not isinstance(brutas, list) or len(brutas) > MAX_ITENS:
        raise ValueError(f"{local}.evidencias_base: lista de até {MAX_ITENS} itens {{teste, numero}}.")
    for k, ev in enumerate(brutas):
        try:
            numero = int(ev["numero"])
            if not 1 <= numero <= 9999:
                raise ValueError
            evidencias.append({"teste": _nome_simples(ev["teste"], f"{local}.evidencias_base[{k}].teste"),
                               "numero": numero})
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{local}.evidencias_base[{k}]: use {{\"teste\": \"<pasta>\", \"numero\": <1 a N>}}.") from exc
    return Caso(
        id=id_,
        titulo=_obrigatorio(bruto.get("titulo"), 120, f"{local}.titulo"),
        objetivo=_obrigatorio(bruto.get("objetivo"), 400, f"{local}.objetivo"),
        tecnica=_obrigatorio(bruto.get("tecnica"), 60, f"{local}.tecnica"),
        prioridade=prioridade,
        passos=passos,
        tipo=_texto_seguro(bruto.get("tipo", ""), 40) or "Funcional",
        pre_condicoes=_lista(bruto.get("pre_condicoes"), MAX_ITENS, 300, f"{local}.pre_condicoes"),
        dados_de_teste=_lista(bruto.get("dados_de_teste"), MAX_ITENS, 300, f"{local}.dados_de_teste"),
        pos_condicoes=_lista(bruto.get("pos_condicoes"), MAX_ITENS, 300, f"{local}.pos_condicoes"),
        rastreio=_lista(bruto.get("rastreio"), MAX_ITENS, 120, f"{local}.rastreio"),
        evidencias_base=evidencias,
        a_confirmar=bruto.get("a_confirmar") is True,  # só um verdadeiro de verdade: "false" (texto) não conta
    )


def _numeros_de_roteiro(pasta: Path) -> list[int]:
    numeros = []
    try:
        for item in pasta.iterdir():
            achado = _PADRAO_ROTEIRO.match(item.name)
            if achado and item.is_file() and not _e_atalho(item):
                numeros.append(int(achado.group(1)))
    except OSError:
        pass
    return sorted(numeros)


def contar_roteiros(pasta_ciclo: Path | str) -> int:
    """Quantos arquivos `roteiro-NNN.json` o ciclo já tem."""
    return len(_numeros_de_roteiro(Path(pasta_ciclo)))


def gravar_roteiro(pasta_ciclo: Path | str, casos: list[Caso], observacoes=None,
                   agora: datetime | None = None, ciclo_sugerido=None) -> Path:
    """Grava `roteiro-NNN.json` (o próximo número livre; nunca sobrescreve). Devolve o caminho."""
    pasta = Path(pasta_ciclo)
    if not pasta.is_dir() or _e_atalho(pasta):
        raise ValueError("A pasta do ciclo não existe mais ou é um atalho.")
    notas = _lista(observacoes, MAX_ITENS, 400, "observacoes")
    conteudo = {"versao": 1, "ciclo": pasta.name, "gerado_em": (agora or datetime.now()).isoformat(timespec="seconds"),
                "gerado_por": "IA (rascunho a revisar)", "ciclo_sugerido": validar_ciclo_sugerido(ciclo_sugerido),
                "casos": [asdict(c) for c in casos], "observacoes": notas}
    texto = json.dumps(conteudo, ensure_ascii=False, indent=2)
    if len(texto.encode("utf-8")) > LIMITE_JSON_BYTES:
        raise ValueError("O roteiro ficou grande demais; gere menos casos ou casos mais enxutos.")
    for _ in range(10):  # concorrência: se o número foi tomado entre a leitura e a criação, tenta o seguinte
        numeros = _numeros_de_roteiro(pasta)
        destino = pasta / f"roteiro-{(numeros[-1] + 1 if numeros else 1):03d}.json"
        try:
            with destino.open("x", encoding="utf-8") as f:
                f.write(texto)
            return destino
        except FileExistsError:
            continue
    raise ValueError("Não foi possível reservar um número de roteiro; tente de novo.")


def ler_roteiro_mais_recente(pasta_ciclo: Path | str) -> Roteiro | None:
    """O roteiro mais novo que for VÁLIDO (um arquivo adulterado é pulado). None se não houver nenhum."""
    pasta = Path(pasta_ciclo)
    if _e_atalho(pasta):
        return None
    for numero in reversed(_numeros_de_roteiro(pasta)):
        arquivo = pasta / f"roteiro-{numero:03d}.json"
        try:
            if arquivo.stat().st_size > LIMITE_JSON_BYTES:
                continue
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
            casos = validar_casos(dados["casos"])
            return Roteiro(arquivo, numero, _texto_seguro(dados.get("gerado_em", ""), 30), casos,
                           _lista(dados.get("observacoes"), MAX_ITENS, 400, "observacoes"),
                           validar_ciclo_sugerido(dados.get("ciclo_sugerido")))
        except (OSError, ValueError, KeyError, TypeError, RecursionError, UnicodeError, AttributeError):
            continue
    return None
