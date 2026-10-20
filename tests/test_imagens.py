"""Redução das evidências para a IA: cabe no limite de 1 MB do Claude desktop sem perder a leitura do texto."""
import base64
import io
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from capturador import imagens


def salvar_png(caminho: Path, imagem: Image.Image) -> Path:
    imagem.save(caminho, "PNG")
    return caminho


def tela_com_foto(tamanho=(1920, 1080)) -> Image.Image:
    """Uma tela com fundo de foto (ruído) e texto por cima: o PNG dela passa de 1 MB, como a de login com a foto do prédio."""
    imagem = Image.frombytes("RGB", tamanho, os.urandom(tamanho[0] * tamanho[1] * 3))
    ImageDraw.Draw(imagem).rectangle((200, 200, 900, 400), fill="white")
    return imagem


class ReduzirParaIa(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.pasta = Path(self._tmp.name)

    def test_tela_simples_continua_png_sem_perda(self):
        caminho = salvar_png(self.pasta / "a.png", Image.new("RGB", (1920, 1080), "navy"))
        dados, formato = imagens.reduzir_evidencia(caminho, 1568)
        self.assertEqual(formato, "png")
        with Image.open(io.BytesIO(dados)) as img:
            self.assertEqual((img.format, max(img.size)), ("PNG", 1568))

    def test_tela_pequena_nao_e_ampliada(self):
        caminho = salvar_png(self.pasta / "a.png", Image.new("RGB", (300, 200), "green"))
        dados, formato = imagens.reduzir_evidencia(caminho)
        with Image.open(io.BytesIO(dados)) as img:
            self.assertEqual((formato, img.size), ("png", (300, 200)))

    def test_tela_pesada_vira_jpeg_que_cabe_no_limite_do_claude_desktop(self):
        caminho = salvar_png(self.pasta / "foto.png", tela_com_foto())
        self.assertGreater(caminho.stat().st_size, 1_000_000)  # o caso real: PNG acima de 1 MB
        dados, formato = imagens.reduzir_evidencia(caminho, 1568)
        self.assertEqual(formato, "jpeg")
        self.assertLessEqual(len(dados), imagens.LIMITE_BYTES_IA)
        self.assertLess(len(base64.b64encode(dados)), 1_000_000)  # o que de fato vai pelo protocolo
        with Image.open(io.BytesIO(dados)) as img:
            self.assertEqual(img.format, "JPEG")
            self.assertLessEqual(max(img.size), 1568)

    def test_limite_apertado_encolhe_ate_caber(self):
        caminho = salvar_png(self.pasta / "foto.png", tela_com_foto((800, 600)))
        dados, formato = imagens.reduzir_evidencia(caminho, 800, limite_bytes=60_000)
        self.assertEqual(formato, "jpeg")
        self.assertLessEqual(len(dados), 60_000)
        with Image.open(io.BytesIO(dados)) as img:
            self.assertLess(max(img.size), 800)

    def test_impossivel_de_caber_e_recusado_com_mensagem(self):
        caminho = salvar_png(self.pasta / "foto.png", tela_com_foto((400, 300)))
        with self.assertRaises(ValueError) as erro:
            imagens.reduzir_evidencia(caminho, 400, limite_bytes=10)
        self.assertIn("tamanho que a IA aceita", str(erro.exception))

    def test_so_jpeg_nem_tenta_o_png_mesmo_numa_tela_simples(self):
        caminho = salvar_png(self.pasta / "a.png", Image.new("RGB", (1920, 1080), "navy"))
        dados, formato = imagens.reduzir_evidencia(caminho, 1800, so_jpeg=True)
        self.assertEqual(formato, "jpeg")
        with Image.open(io.BytesIO(dados)) as img:
            self.assertEqual((img.format, max(img.size)), ("JPEG", 1800))

    def test_continua_recusando_o_que_nao_e_png(self):
        falso = self.pasta / "falso.png"
        Image.new("RGB", (50, 50), "red").save(falso, "JPEG")
        with self.assertRaises(ValueError):
            imagens.reduzir_evidencia(falso)


if __name__ == "__main__":
    unittest.main()
