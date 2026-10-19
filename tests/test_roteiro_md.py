"""Roteiro do ciclo em Markdown e PDF."""
import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from capturador import ciclos
from capturador.roteiro_md import gerar_pdf_do_roteiro, roteiro_para_markdown

CASO = {"id": "CT-01", "titulo": "Login válido", "objetivo": "Entrar no sistema", "tecnica": "Partição de equivalência",
        "prioridade": "Alta", "pre_condicoes": ["Usuário ativo"], "dados_de_teste": ["usuario.teste"],
        "passos": [{"acao": "Abrir a tela de login", "resultado_esperado": "Campos visíveis"},
                   {"acao": "Entrar com | dados válidos", "resultado_esperado": "Painel exibido"}],
        "pos_condicoes": ["Sessão iniciada"], "rastreio": ["Login"], "a_confirmar": True,
        "evidencias_base": [{"teste": "2026-10-09_1400 - Login", "numero": 2}]}


class RoteiroEmMarkdown(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.ciclo = ciclos.criar_ciclo(self.base, {"nome": "Ciclo - Login", "testes_base": ["2026-10-09_1400 - Login"],
                                                    "tipo": "Regressão", "versao_sistema": "2.3.1", "testador": "QA"})
        ciclos.gravar_roteiro(self.ciclo.pasta, ciclos.validar_casos([CASO, {**CASO, "id": "CT-02", "prioridade": "Baixa"}]),
                              ["Qual a regra de bloqueio?"],
                              ciclo_sugerido={"objetivo": "Validar o login", "escopo": ["Login"], "sistema": "ERP",
                                              "criterios_saida": ["Casos de prioridade Alta executados"]})
        self.roteiro = ciclos.ler_roteiro_mais_recente(self.ciclo.pasta)

    def md(self):
        return roteiro_para_markdown(self.ciclo, self.roteiro)

    def test_traz_ciclo_criterios_resumo_e_casos(self):
        md = self.md()
        for esperado in ("## Ciclo", "| Rodada | Ciclo - Login |", "| Tipo | Regressão |", "| Sistema | ERP |",
                         "| Versão | 2.3.1 |", "| Casos | 2 (1 Alta, 1 Baixa) |", "## Critérios de entrada", "## Critérios de saída",
                         "## Resumo dos casos", "| CT-01 | Login válido | Partição de equivalência | Alta | 2 |",
                         "## Casos de teste", "### CT-01 — Login válido", "| # | Ação | Resultado esperado |",
                         "**Pré-condições:**", "**Dados de teste:**", "**Pós-condições:**", "**Rastreio:** Login",
                         "## Dúvidas e hipóteses a confirmar", "- Qual a regra de bloqueio?"):
            with self.subTest(esperado=esperado):
                self.assertIn(esperado, md)

    def test_indica_de_onde_veio_cada_parte_do_ciclo(self):
        md = self.md()
        self.assertIn("**Objetivo:** *(proposto pela IA)* Validar o login", md)
        self.assertIn("## Critérios de saída *(proposto pela IA)*", md)
        self.assertIn("## Critérios de entrada *(padrão do CTFL)*", md)  # a IA não propôs: vale o padrão

    def test_o_que_o_usuario_preencheu_nao_leva_etiqueta(self):
        ciclo = ciclos.criar_ciclo(self.base, {"nome": "Meu ciclo", "objetivo": "Meu objetivo", "criterios_entrada": ["Só este"]})
        md = roteiro_para_markdown(ciclo, self.roteiro)
        self.assertIn("**Objetivo:** Meu objetivo", md)
        self.assertIn("## Critérios de entrada\n\n- Só este", md)

    def test_barra_vertical_nao_quebra_a_tabela_dos_passos(self):
        md = self.md()
        self.assertIn("| 2 | Entrar com / dados válidos | Painel exibido |", md)
        for linha in md.splitlines():
            if linha.startswith("| 1 |") or linha.startswith("| 2 |"):
                self.assertEqual(linha.count("|"), 4)

    def test_caso_a_confirmar_e_sinalizado(self):
        self.assertIn("**Resultado esperado a confirmar**", self.md())

    def test_evidencias_de_referencia_aparecem(self):
        self.assertIn("2026-10-09_1400 - Login (evidência 2)", self.md())

    def test_sem_observacoes_nao_cria_a_secao(self):
        ciclos.gravar_roteiro(self.ciclo.pasta, ciclos.validar_casos([CASO]))
        self.assertNotIn("Dúvidas e hipóteses", roteiro_para_markdown(self.ciclo, ciclos.ler_roteiro_mais_recente(self.ciclo.pasta)))

    def test_gera_um_pdf_valido_na_pasta_do_ciclo_sem_sobrescrever(self):
        agora = datetime(2026, 10, 19, 15, 0)
        primeiro = gerar_pdf_do_roteiro(self.ciclo, self.roteiro, agora)
        segundo = gerar_pdf_do_roteiro(self.ciclo, self.roteiro, agora)
        self.assertEqual((primeiro.name, segundo.name), ("Roteiro de testes - Ciclo - Login.pdf",
                                                         "Roteiro de testes - Ciclo - Login (2).pdf"))
        dados = primeiro.read_bytes()
        self.assertTrue(dados.startswith(b"%PDF"))
        self.assertGreaterEqual(len(re.findall(rb"/Type\s*/Page(?![s\w])", dados)), 1)
        self.assertEqual(primeiro.parent, self.ciclo.pasta)

    def test_roteiro_grande_gera_pdf_com_varias_paginas(self):
        casos = [{**CASO, "id": f"CT-{i:02d}", "passos": [{"acao": "Ação " * 20, "resultado_esperado": "Resultado " * 20}] * 12}
                 for i in range(1, 41)]
        ciclos.gravar_roteiro(self.ciclo.pasta, ciclos.validar_casos(casos))
        roteiro = ciclos.ler_roteiro_mais_recente(self.ciclo.pasta)
        pdf = gerar_pdf_do_roteiro(self.ciclo, roteiro)
        paginas = len(re.findall(rb"/Type\s*/Page(?![s\w])", pdf.read_bytes()))
        self.assertGreater(paginas, 10)

    def test_texto_com_acentos_e_marcacao_estranha_nao_quebra_o_pdf(self):
        estranho = {**CASO, "titulo": "Ação <b>ç</b> & *itálico* **negrito** `código`", "objetivo": "<script>x</script> {0} %s"}
        ciclos.gravar_roteiro(self.ciclo.pasta, ciclos.validar_casos([estranho]))
        roteiro = ciclos.ler_roteiro_mais_recente(self.ciclo.pasta)
        self.assertTrue(gerar_pdf_do_roteiro(self.ciclo, roteiro).read_bytes().startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
