import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from PIL import Image

from capturador import relatorio_md
from capturador.relatorio_md import EvidenciaPdf, gerar_pdf_de_markdown


def paginas(pdf: Path) -> int:
    return len(re.findall(rb"/Type /Page\b", pdf.read_bytes()))


class Inline(unittest.TestCase):
    def test_negrito_italico_e_codigo(self):
        self.assertEqual(relatorio_md._inline("um **forte** e *leve* e `x`"),
                         'um <b>forte</b> e <i>leve</i> e <font face="Courier">x</font>')

    def test_marcacao_perigosa_e_escapada(self):
        saida = relatorio_md._inline('<script>alert(1)</script> & <b>x</b> <font color="red">')
        self.assertNotIn("<script>", saida)
        self.assertNotIn("<font color", saida)
        self.assertIn("&lt;script&gt;", saida)
        self.assertIn("&amp;", saida)

    def test_br_nas_celulas_vira_quebra_de_linha(self):
        self.assertEqual(relatorio_md._inline("a<br>b<br/>c"), "a<br/>b<br/>c")

    def test_asteriscos_soltos_nao_viram_italico(self):
        self.assertEqual(relatorio_md._inline("2 * 3 * 4"), "2 * 3 * 4")


class GerarPdf(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = Path(self._tmp.name)

    def _imagem(self, nome: str, tamanho=(800, 600)) -> Path:
        caminho = self.raiz / nome
        Image.new("RGB", tamanho, (30, 64, 120)).save(caminho)
        return caminho

    def test_relatorio_completo_gera_pdf_valido(self):
        markdown = (
            "# Resumo\n\nTudo **certo** (Evidência 1).\n\n"
            "| ID | Título | Evidências |\n|---|---|---|\n| CT-01 | Login<br>com sucesso | 1, 2 |\n\n"
            "- item um\n- item dois\n\n1. primeiro\n2. segundo\n\n---\nfim\n"
        )
        destino = self.raiz / "r.pdf"
        n = gerar_pdf_de_markdown(destino, "Relatório", markdown, "sub")
        self.assertTrue(destino.read_bytes().startswith(b"%PDF"))
        self.assertEqual(paginas(destino), n)
        self.assertGreaterEqual(n, 1)

    def test_evidencias_entram_em_anexo(self):
        sem = self.raiz / "sem.pdf"
        com = self.raiz / "com.pdf"
        evidencias = [EvidenciaPdf(self._imagem(f"{i}.png", (1920, 1080)), "Tela inteira", i,
                                   datetime(2026, 10, 9, 14, 0, i)) for i in range(1, 6)]
        gerar_pdf_de_markdown(sem, "R", "texto")
        n = gerar_pdf_de_markdown(com, "R", "texto", evidencias=evidencias)
        self.assertGreater(n, paginas(sem))
        self.assertGreater(com.stat().st_size, sem.stat().st_size)

    def test_tabela_larga_e_texto_longo_nao_quebram(self):
        colunas = 9
        cab = "| " + " | ".join(f"Coluna {i}" for i in range(colunas)) + " |"
        sep = "|" + "---|" * colunas
        linha = "| " + " | ".join("palavra" * (i + 1) for i in range(colunas)) + " |"
        markdown = "\n".join([cab, sep] + [linha] * 40) + "\n\n" + ("Parágrafo longo. " * 400)
        n = gerar_pdf_de_markdown(self.raiz / "t.pdf", "Tabela", markdown)
        self.assertGreater(n, 1)

    def test_markdown_vazio_ou_estranho_nao_quebra(self):
        for conteudo in ("", "   \n\n", "| só uma barra", "# ", "***", "- \n- \n"):
            with self.subTest(conteudo=conteudo):
                destino = self.raiz / "x.pdf"
                gerar_pdf_de_markdown(destino, "T", conteudo)
                self.assertTrue(destino.read_bytes().startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
