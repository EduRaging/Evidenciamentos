import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from PIL import Image

from capturador import metadados
from capturador.metadados import EvidenciaInfo, PastaTeste
from capturador.prompt_ia import NAO_INFORMADO, Formulario, montar_prompt
from capturador.sessao import Sessao


def teste_exemplo(pdf: str | None = "Evidencias - Login.pdf") -> PastaTeste:
    return PastaTeste(
        pasta=Path("C:/x"), nome_teste="Login no ERP", testador="Equipe QA", pdf=pdf,
        evidencias=[
            EvidenciaInfo(1, "01_tela.png", "Tela inteira", datetime(2026, 10, 9, 14, 30, 5)),
            EvidenciaInfo(2, "02_recorte.png", "Recorte", datetime(2026, 10, 9, 14, 41, 12)),
        ],
    )


class MontarPrompt(unittest.TestCase):
    def test_contem_contexto_e_lista_de_evidencias(self):
        form = Formulario(ambiente="ERP homologação v2.3", objetivo="Validar o login",
                          criterios="Usuário entra e vê o painel", observacoes="Chrome 130")
        prompt = montar_prompt(teste_exemplo(), form)
        for esperado in ("Teste: Login no ERP", "ERP homologação v2.3", "Testador: Equipe QA",
                         "09/10/2026 das 14:30 às 14:41", "Validar o login",
                         "Usuário entra e vê o painel", "Chrome 130",
                         "Evidências anexadas (2)",
                         "1. Tela inteira — 09/10/2026 14:30:05 (01_tela.png)",
                         "2. Recorte — 09/10/2026 14:41:12 (02_recorte.png)"):
            with self.subTest(esperado=esperado):
                self.assertIn(esperado, prompt)

    def test_menciona_o_pdf_quando_existe(self):
        self.assertIn('"Evidencias - Login.pdf"', montar_prompt(teste_exemplo(), Formulario()))

    def test_sem_pdf_pede_anexo_das_imagens(self):
        prompt = montar_prompt(teste_exemplo(pdf=None), Formulario(entregar_pdf=False))
        self.assertNotIn(".pdf", prompt)
        self.assertIn("Anexei as imagens", prompt)

    def test_pede_a_entrega_em_pdf_por_padrao(self):
        prompt = montar_prompt(teste_exemplo(), Formulario())
        self.assertIn("## Entrega em PDF", prompt)
        self.assertIn("arquivo PDF para eu baixar", prompt)
        self.assertIn('"Relatório de testes - Login no ERP.pdf"', prompt)
        self.assertIn("entregar o resultado em um arquivo PDF", prompt)  # também na tarefa inicial
        self.assertIn("avise logo no início", prompt)  # plano B se a IA não gerar arquivos
        self.assertIn("Markdown", prompt)

    def test_sem_entrega_em_pdf_quando_desligado(self):
        prompt = montar_prompt(teste_exemplo(), Formulario(entregar_pdf=False))
        self.assertNotIn("## Entrega em PDF", prompt)
        self.assertNotIn("arquivo PDF para eu baixar", prompt)
        self.assertNotIn("entregar o resultado", prompt)

    def test_nome_sugerido_do_pdf_depende_da_saida_e_e_seguro(self):
        teste = teste_exemplo()
        teste.nome_teste = "Login/Logout: perfis"
        casos = montar_prompt(teste, Formulario(saida="casos"))
        relatorio = montar_prompt(teste, Formulario(saida="relatorio"))
        self.assertIn('"Casos de teste - Login-Logout- perfis.pdf"', casos)
        self.assertIn('"Relatório de testes - Login-Logout- perfis.pdf"', relatorio)

    def test_campos_vazios_viram_nao_informado(self):
        prompt = montar_prompt(teste_exemplo(), Formulario())
        self.assertIn(f"Objetivo do teste: {NAO_INFORMADO}", prompt)
        self.assertIn(f"Sistema / ambiente: {NAO_INFORMADO}", prompt)
        self.assertIn("deduza pelo objetivo", prompt)  # critérios ausentes

    def test_testador_ausente_vira_nao_informado(self):
        teste = teste_exemplo()
        teste.testador = ""
        self.assertIn(f"Testador: {NAO_INFORMADO}", montar_prompt(teste, Formulario()))

    def test_tipos_de_saida(self):
        casos = montar_prompt(teste_exemplo(), Formulario(saida="casos"))
        relatorio = montar_prompt(teste_exemplo(), Formulario(saida="relatorio"))
        ambos = montar_prompt(teste_exemplo(), Formulario(saida="ambos"))
        self.assertIn("### Casos de teste", casos)
        self.assertNotIn("### Relatório de execução", casos)
        self.assertIn("### Relatório de execução", relatorio)
        self.assertNotIn("### Casos de teste", relatorio)
        self.assertIn("### Casos de teste", ambos)
        self.assertIn("### Relatório de execução", ambos)
        self.assertIn("reaproveitando os mesmos IDs", ambos)

    def test_saida_invalida_cai_em_ambos(self):
        prompt = montar_prompt(teste_exemplo(), Formulario(saida="qualquer"))
        self.assertIn("### Casos de teste", prompt)
        self.assertIn("### Relatório de execução", prompt)

    def test_regras_anti_invencao_sempre_presentes(self):
        prompt = montar_prompt(teste_exemplo(), Formulario(saida="casos"))
        self.assertIn("Não invente", prompt)
        self.assertIn("não evidenciado", prompt)
        self.assertIn("A decisão final é do testador", prompt)

    def test_periodo_em_dias_diferentes_e_sem_horario(self):
        teste = teste_exemplo()
        teste.evidencias[1].momento = datetime(2026, 10, 10, 9, 0, 0)
        self.assertIn("09/10/2026 14:30 a 10/10/2026 09:00", montar_prompt(teste, Formulario()))
        for e in teste.evidencias:
            e.momento = None
        prompt = montar_prompt(teste, Formulario())
        self.assertIn(f"Data da execução: {NAO_INFORMADO}", prompt)
        self.assertIn("1. Tela inteira (01_tela.png)", prompt)

    def test_texto_do_usuario_com_chaves_nao_quebra(self):
        prompt = montar_prompt(teste_exemplo(), Formulario(objetivo="campo {codigo} e {0}"))
        self.assertIn("campo {codigo} e {0}", prompt)


class LerPasta(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = Path(self._tmp.name)

    def test_pasta_inexistente(self):
        with self.assertRaises(ValueError):
            metadados.ler(self.raiz / "nao_existe")

    def test_pasta_qualquer_nao_e_de_teste(self):
        (self.raiz / "foto.jpg").write_bytes(b"x")
        with self.assertRaises(ValueError):
            metadados.ler(self.raiz)

    def test_pasta_antiga_sem_json_e_varrida(self):
        pasta = self.raiz / "2026-10-09_1432 - Teste antigo"
        pasta.mkdir()
        for nome in ("02_recorte.png", "01_tela.png", "10_tela.png"):
            (pasta / nome).write_bytes(b"png")
        (pasta / "Evidencias - Teste antigo.pdf").write_bytes(b"%PDF")
        teste = metadados.ler(pasta)
        self.assertEqual(teste.nome_teste, "Teste antigo")
        self.assertEqual(teste.pdf, "Evidencias - Teste antigo.pdf")
        self.assertEqual([(e.numero, e.rotulo) for e in teste.evidencias],
                         [(1, "Tela inteira"), (2, "Recorte"), (10, "Tela inteira")])
        self.assertTrue(all(e.momento is None for e in teste.evidencias))

    def test_json_corrompido_cai_na_varredura(self):
        pasta = self.raiz / "t"
        pasta.mkdir()
        (pasta / metadados.ARQUIVO).write_text("{ isto nao e json", encoding="utf-8")
        (pasta / "01_tela.png").write_bytes(b"png")
        self.assertEqual(len(metadados.ler(pasta).evidencias), 1)

    def test_json_com_estrutura_inesperada_cai_na_varredura(self):
        pasta = self.raiz / "t"
        pasta.mkdir()
        (pasta / metadados.ARQUIVO).write_text(json.dumps({"nome_teste": "x"}), encoding="utf-8")
        (pasta / "01_tela.png").write_bytes(b"png")
        self.assertEqual(len(metadados.ler(pasta).evidencias), 1)


class FinalizarGravaMetadados(unittest.TestCase):
    def test_pasta_finalizada_pode_ser_lida_de_volta(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            sessao = Sessao(tmp / "em_andamento")
            sessao.adicionar(Image.new("RGB", (400, 300), "red"), "tela")
            sessao.adicionar(Image.new("RGB", (200, 100), "blue"), "recorte")
            pasta = sessao.finalizar("Cadastro de usuário", "Equipe QA", tmp / "base")

            self.assertTrue((pasta / metadados.ARQUIVO).exists())
            teste = metadados.ler(pasta)
            self.assertEqual(teste.nome_teste, "Cadastro de usuário")
            self.assertEqual(teste.testador, "Equipe QA")
            self.assertEqual(teste.pdf, "Evidencias - Cadastro de usuário.pdf")
            self.assertEqual([(e.numero, e.arquivo, e.rotulo) for e in teste.evidencias],
                             [(1, "01_tela.png", "Tela inteira"), (2, "02_recorte.png", "Recorte")])
            self.assertTrue(all(e.momento for e in teste.evidencias))
            prompt = montar_prompt(teste, Formulario())
            self.assertIn("Evidencias - Cadastro de usuário.pdf", prompt)


if __name__ == "__main__":
    unittest.main()
