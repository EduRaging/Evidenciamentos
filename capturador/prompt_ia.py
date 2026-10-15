"""Monta o prompt para o usuário colar na IA de sua preferência (sem integração com nenhuma IA)."""
from __future__ import annotations

from dataclasses import dataclass

from .metadados import PastaTeste
from .sessao import nome_seguro

SAIDAS = {"casos": "Casos de teste", "relatorio": "Relatório de execução", "ambos": "Os dois"}
NAO_INFORMADO = "não informado"

_TAREFAS = {
    "casos": "montar os casos de teste executados",
    "relatorio": "montar o relatório de execução",
    "ambos": "montar os casos de teste executados e o relatório de execução",
}

_REGRAS = """\
- Baseie-se somente no que está visível nas evidências e nas informações acima. Não invente telas, campos, dados, mensagens nem resultados.
- Quando algo não puder ser confirmado pelas imagens, escreva "não evidenciado" e diga o que faltaria para confirmar.
- Cite o número da evidência (ex.: "Evidência 3") que sustenta cada afirmação.
- Se faltar informação para algum item, faça a suposição mínima necessária, declare-a em "Suposições" e liste as dúvidas em aberto no final. Não pare para perguntar antes de responder.
- Não decida sozinho se o teste passou ou falhou: sugira o status (Aprovado, Reprovado ou Inconclusivo) com justificativa. A decisão final é do testador.
- Se as imagens mostrarem dados pessoais ou sensíveis (nomes, CPF/CNPJ, valores, e-mails), não os reproduza na resposta; refira-se a eles de forma genérica (ex.: "dados do cliente").
- Seja objetivo e responda em português do Brasil."""

_SECAO_CASOS = """\
### Casos de teste
Monte os casos de teste executados, em uma tabela Markdown com as colunas: ID | Título | Pré-condições | Passos | Resultado esperado | Resultado observado | Status sugerido | Evidências.
- Use IDs sequenciais (CT-01, CT-02...) e agrupe no mesmo caso as evidências que pertencem ao mesmo fluxo.
- Se o resultado esperado não foi informado, deduza-o a partir do objetivo e marque como "(deduzido)"."""

_SECAO_RELATORIO = """\
### Relatório de execução
Escreva o relatório com estas seções:
1. Resumo (2 a 4 linhas)
2. Escopo e ambiente
3. Resultado por caso de teste (tabela: ID, status sugerido, evidências)
4. Defeitos ou anomalias observadas (o que, onde, evidência, severidade sugerida) ou "nenhuma observada"
5. Itens não evidenciados e riscos
6. Suposições e dúvidas em aberto
7. Conclusão e recomendação (aprovar, reprovar ou retestar), com justificativa"""


@dataclass
class Formulario:
    ambiente: str = ""
    objetivo: str = ""
    criterios: str = ""
    observacoes: str = ""
    saida: str = "ambos"  # chave de SAIDAS
    entregar_pdf: bool = True  # pede à IA o resultado já em arquivo PDF


def _ou_nao_informado(texto: str) -> str:
    return texto.strip() or NAO_INFORMADO


def _periodo(teste: PastaTeste) -> str:
    momentos = [e.momento for e in teste.evidencias if e.momento]
    if not momentos:
        return NAO_INFORMADO
    inicio, fim = min(momentos), max(momentos)
    if inicio.date() == fim.date():
        if inicio.strftime("%H:%M") == fim.strftime("%H:%M"):
            return inicio.strftime("%d/%m/%Y %H:%M")
        return f"{inicio:%d/%m/%Y} das {inicio:%H:%M} às {fim:%H:%M}"
    return f"{inicio:%d/%m/%Y %H:%M} a {fim:%d/%m/%Y %H:%M}"


def _lista_evidencias(teste: PastaTeste) -> str:
    linhas = []
    for e in teste.evidencias:
        hora = f" — {e.momento:%d/%m/%Y %H:%M:%S}" if e.momento else ""
        linhas.append(f"{e.numero}. {e.rotulo}{hora} ({e.arquivo})")
    return "\n".join(linhas)


def _anexo(teste: PastaTeste) -> str:
    if teste.pdf:
        return (f'Anexei o arquivo "{teste.pdf}": a primeira página é a capa e cada página seguinte '
                "é uma evidência, na mesma ordem da lista abaixo (a \"Evidência N\" do PDF é o item N). "
                "Se você não conseguir ler as imagens dentro do PDF, me avise que eu anexo as imagens separadas.")
    return "Anexei as imagens das evidências, com os nomes de arquivo da lista abaixo."


def _secao_entrega(nome_teste: str, saida: str) -> str:
    titulo = "Casos de teste" if saida == "casos" else "Relatório de testes"
    sugestao = f"{titulo} - {nome_seguro(nome_teste)}.pdf"
    return (
        "## Entrega em PDF\n"
        f'Entregue o resultado como um **arquivo PDF para eu baixar** (sugestão de nome: "{sugestao}"), '
        "com uma capa curta (nome do teste, sistema/ambiente, testador e data) seguida das seções acima.\n"
        "- Use tabelas legíveis (com quebra de linha dentro das células) e paginação limpa.\n"
        '- Se você conseguir, inclua no PDF as imagens das evidências, identificadas como "Evidência N", '
        "junto dos casos de teste correspondentes.\n"
        "- Se você não conseguir gerar arquivos, avise logo no início e entregue o conteúdo completo em "
        "Markdown, pronto para eu converter em PDF."
    )


def montar_prompt(teste: PastaTeste, form: Formulario) -> str:
    saida = form.saida if form.saida in SAIDAS else "ambos"
    secoes = []
    if saida in ("casos", "ambos"):
        secoes.append(_SECAO_CASOS)
    if saida in ("relatorio", "ambos"):
        secoes.append(_SECAO_RELATORIO)
    if saida == "ambos":
        secoes.append("Faça primeiro os casos de teste e depois o relatório, reaproveitando os mesmos IDs.")
    tarefa = _TAREFAS[saida] + (" e entregar o resultado em um arquivo PDF" if form.entregar_pdf else "")

    criterios = form.criterios.strip()
    if not criterios:
        criterios = f"{NAO_INFORMADO} (deduza pelo objetivo e marque como \"deduzido\")"

    partes = [
        "Você é um analista de qualidade (QA) sênior. Vou te enviar as evidências de um teste "
        f"manual de software e preciso que você faça o seguinte: {tarefa}.",
        "## Contexto do teste\n"
        f"- Teste: {teste.nome_teste}\n"
        f"- Sistema / ambiente: {_ou_nao_informado(form.ambiente)}\n"
        f"- Testador: {_ou_nao_informado(teste.testador)}\n"
        f"- Data da execução: {_periodo(teste)}\n"
        f"- Objetivo do teste: {_ou_nao_informado(form.objetivo)}\n"
        f"- Critérios de aceite / resultado esperado: {criterios}\n"
        f"- Observações do testador: {_ou_nao_informado(form.observacoes)}",
        f"## Evidências anexadas ({len(teste.evidencias)})\n{_anexo(teste)}\n\n{_lista_evidencias(teste)}",
        f"## Regras\n{_REGRAS}",
        "## O que produzir\n" + "\n\n".join(secoes),
    ]
    if form.entregar_pdf:
        partes.append(_secao_entrega(teste.nome_teste, saida))
    return "\n\n".join(partes) + "\n"
