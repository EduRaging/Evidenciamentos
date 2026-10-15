"""Leitura de vários testes de uma vez para o envio ao Claude (aba "PDFs gerados")."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from capturador.dialogo_prompt import ler_testes
from capturador.sessao import Sessao


class LerTestes(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = Path(self._tmp.name)
        self.base = self.raiz / "base"

    def criar(self, nome, imagens=2):
        sessao = Sessao(self.raiz / f"trab_{nome[:3]}")
        for _ in range(imagens):
            sessao.adicionar(Image.new("RGB", (60, 40), "navy"), "tela")
        return sessao.finalizar(nome, "QA", self.base)

    def test_le_varios_testes_na_ordem_pedida(self):
        a, b = self.criar("Login"), self.criar("Despesa")
        testes, ignorados = ler_testes([b, a])
        self.assertEqual([t.nome_teste for t in testes], ["Despesa", "Login"])
        self.assertEqual(ignorados, [])

    def test_pasta_repetida_conta_uma_vez(self):
        a = self.criar("Login")
        testes, _ = ler_testes([a, a, str(a), Path(str(a).upper())])
        self.assertEqual(len(testes), 1)

    def test_pasta_sem_imagens_e_ignorada_com_motivo(self):
        a = self.criar("Login")
        vazia = self.base / "2026-01-01_0900 - So PDF"
        vazia.mkdir()
        (vazia / "Evidencias - So PDF.pdf").write_bytes(b"%PDF-1.4 x")
        testes, ignorados = ler_testes([vazia, a])
        self.assertEqual([t.nome_teste for t in testes], ["Login"])
        self.assertEqual([nome for nome, _ in ignorados], ["2026-01-01_0900 - So PDF"])
        self.assertIn("sem imagens", ignorados[0][1])

    def test_pasta_inexistente_ou_que_nao_e_de_teste_e_ignorada(self):
        a = self.criar("Login")
        testes, ignorados = ler_testes([self.raiz / "nao existe", a])
        self.assertEqual(len(testes), 1)
        self.assertEqual(len(ignorados), 1)

    def test_tudo_ilegivel_devolve_lista_vazia(self):
        testes, ignorados = ler_testes([self.raiz / "x", self.raiz / "y"])
        self.assertEqual((testes, len(ignorados)), ([], 2))


if __name__ == "__main__":
    unittest.main()
