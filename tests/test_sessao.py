import re
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from capturador.sessao import Sessao, nome_seguro


def imagem_teste(largura: int, altura: int, cor=(40, 90, 160)) -> Image.Image:
    img = Image.new("RGB", (largura, altura), cor)
    ImageDraw.Draw(img).rectangle((10, 10, largura - 10, altura - 10), outline="white", width=4)
    return img


class NomeSeguro(unittest.TestCase):
    def test_remove_caracteres_proibidos(self):
        self.assertEqual(nome_seguro('Login/Logout: "admin"?'), "Login-Logout- -admin")

    def test_vazio_ou_so_pontuacao(self):
        self.assertEqual(nome_seguro("   "), "teste")
        self.assertEqual(nome_seguro("..."), "teste")

    def test_nome_reservado_do_windows(self):
        self.assertEqual(nome_seguro("con"), "_con")

    def test_mantem_acentos(self):
        self.assertEqual(nome_seguro("Cadastro de usuário – ação"), "Cadastro de usuário – ação")

    def test_limita_tamanho(self):
        self.assertLessEqual(len(nome_seguro("a" * 300)), 80)


class FluxoDaSessao(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        raiz = Path(self._tmp.name)
        self.trabalho, self.base = raiz / "em_andamento", raiz / "Evidencias"

    def test_finaliza_cria_pasta_nomeada_com_imagens_e_pdf(self):
        s = Sessao(self.trabalho)
        s.adicionar(imagem_teste(1920, 1080), "tela")
        s.adicionar(imagem_teste(400, 700), "recorte")
        s.adicionar(imagem_teste(120, 60), "recorte")

        pasta = s.finalizar("Login do ERP", "Fulano", self.base)

        self.assertEqual(pasta.parent, self.base)
        self.assertRegex(pasta.name, r"^\d{4}-\d{2}-\d{2}_\d{4} - Login do ERP$")
        self.assertEqual(sorted(p.name for p in pasta.glob("*.png")),
                         ["01_tela.png", "02_recorte.png", "03_recorte.png"])
        pdf = pasta / "Evidencias - Login do ERP.pdf"
        dados = pdf.read_bytes()
        self.assertTrue(dados.startswith(b"%PDF"))
        self.assertEqual(len(re.findall(rb"/Type /Page\b", dados)), 4)  # capa + 3
        self.assertEqual(s.evidencias, [])
        self.assertEqual(list(self.trabalho.iterdir()), [])  # sessão limpa

    def test_mesmo_nome_na_mesma_hora_nao_sobrescreve(self):
        nomes = set()
        for _ in range(2):
            s = Sessao(self.trabalho)
            s.adicionar(imagem_teste(300, 200), "tela")
            nomes.add(s.finalizar("Repetido", "", self.base).name)
        self.assertEqual(len(nomes), 2)

    def test_sem_evidencias_nao_cria_pasta(self):
        with self.assertRaises(ValueError):
            Sessao(self.trabalho).finalizar("Vazio", "", self.base)
        self.assertFalse(self.base.exists())

    def test_sessao_sobrevive_a_reabrir_o_app(self):
        s = Sessao(self.trabalho)
        s.nome_teste = "Em andamento"
        s.adicionar(imagem_teste(300, 200), "tela")
        s.adicionar(imagem_teste(300, 200), "recorte")

        retomada = Sessao(self.trabalho)
        self.assertEqual(retomada.nome_teste, "Em andamento")
        self.assertEqual([e.tipo for e in retomada.evidencias], ["tela", "recorte"])

    def test_remover_nao_reaproveita_numero_de_arquivo(self):
        s = Sessao(self.trabalho)
        for _ in range(3):
            s.adicionar(imagem_teste(100, 100), "tela")
        s.remover(1)
        novo = s.adicionar(imagem_teste(100, 100), "tela")
        self.assertEqual(novo.arquivo, "004.png")
        self.assertEqual(len(s.evidencias), 3)

    def test_falha_no_pdf_preserva_sessao_e_nao_deixa_pasta(self):
        s = Sessao(self.trabalho)
        s.adicionar(imagem_teste(300, 200), "tela")
        (self.trabalho / "001.png").write_bytes(b"isto nao e um png")  # força erro na geração
        with self.assertRaises(Exception):
            s.finalizar("Quebrado", "", self.base)
        self.assertEqual(list(self.base.iterdir()), [])
        self.assertEqual(len(s.evidencias), 1)

    def test_descartar_apaga_tudo(self):
        s = Sessao(self.trabalho)
        s.adicionar(imagem_teste(100, 100), "tela")
        s.descartar()
        self.assertEqual(list(self.trabalho.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
