"""Gravação do relatório em PDF na pasta do teste (usada pelo servidor MCP e pelo relatório automático do app)."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from capturador import gravacao, metadados
from capturador.sessao import Sessao


class GravarRelatorio(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        raiz = Path(self._tmp.name)
        sessao = Sessao(raiz / "trab")
        sessao.adicionar(Image.new("RGB", (800, 600), "navy"), "tela")
        sessao.adicionar(Image.new("RGB", (400, 300), "green"), "recorte")
        self.pasta = sessao.finalizar("Login no ERP", "QA", raiz / "Evidencias")
        self.pasta = self.pasta.resolve()  # quem chama entrega a pasta já resolvida (o temporário pode vir com nome curto)
        self.dados = metadados.ler(self.pasta)

    def test_grava_o_pdf_e_o_markdown_com_as_imagens_anexadas(self):
        r = gravacao.gravar_relatorio_pdf(self.dados, "Relatório de testes", "# Resumo\n\n- tudo certo\n")
        self.assertTrue((self.pasta / r["pdf"]).read_bytes().startswith(b"%PDF"))
        self.assertEqual((self.pasta / r["markdown"]).read_text(encoding="utf-8"), "# Resumo\n\n- tudo certo\n")
        self.assertEqual(r["evidencias_anexadas"], 2)
        self.assertEqual(r["caminho_pdf"], str(self.pasta / "Relatório de testes.pdf"))

    def test_sem_imagens_quando_nao_pedidas(self):
        r = gravacao.gravar_relatorio_pdf(self.dados, "Só texto", "# Oi", incluir_evidencias=False)
        self.assertEqual(r["evidencias_anexadas"], 0)

    def test_nunca_sobrescreve(self):
        (self.pasta / "Relatório.md").write_text("antigo", encoding="utf-8")
        r = gravacao.gravar_relatorio_pdf(self.dados, "Relatório", "# Novo")
        self.assertEqual(r["pdf"], "Relatório (2).pdf")
        self.assertEqual((self.pasta / "Relatório.md").read_text(encoding="utf-8"), "antigo")

    def test_titulo_e_conteudo_validos_sao_obrigatorios(self):
        for titulo, conteudo in (("", "x"), ("  ", "x"), ("t" * (gravacao.MAX_TITULO + 1), "x"), ("t", ""), ("t", "  "),
                                 ("t", "x" * (gravacao.MAX_MARKDOWN + 1))):
            with self.subTest(titulo=titulo[:10], conteudo=conteudo[:10]), self.assertRaises(ValueError):
                gravacao.gravar_relatorio_pdf(self.dados, titulo, conteudo)
        self.assertEqual(list(self.pasta.glob("*.pdf")), [self.pasta / self.dados.pdf])

    def test_so_grava_em_pasta_de_teste_do_app(self):
        vazia = metadados.PastaTeste(pasta=self.pasta, nome_teste="x", testador="", pdf=None, evidencias=[])
        with self.assertRaises(ValueError):
            gravacao.gravar_relatorio_pdf(vazia, "t", "x")

    def test_limite_de_pdfs_por_pasta(self):
        with self.assertRaises(ValueError):
            gravacao.gravar_relatorio_pdf(self.dados, "t", "x", max_pdfs=1)  # já existe o PDF das evidências

    def test_o_markdown_fica_guardado_quando_o_pdf_falha(self):
        with mock.patch.object(gravacao, "gerar_pdf_de_markdown", side_effect=RuntimeError("falha")):
            with self.assertRaises(RuntimeError):
                gravacao.gravar_relatorio_pdf(self.dados, "Parcial", "# conteudo")
        self.assertEqual((self.pasta / "Parcial.md").read_text(encoding="utf-8"), "# conteudo")
        self.assertFalse((self.pasta / "Parcial.pdf").exists())


if __name__ == "__main__":
    unittest.main()
