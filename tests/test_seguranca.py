"""Defesas contra um evidencias.json adulterado (nomes de arquivo com caminhos)."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from capturador import metadados

TEM_MCP = importlib.util.find_spec("mcp") is not None


def pasta_com_json(raiz: Path, evidencias: list[dict], pdf="Evidencias - T.pdf") -> Path:
    pasta = raiz / "teste"
    pasta.mkdir()
    Image.new("RGB", (80, 60), "navy").save(pasta / "01_tela.png")
    (pasta / metadados.ARQUIVO).write_text(json.dumps({
        "versao": 1, "nome_teste": "T", "testador": "", "pdf": pdf, "evidencias": evidencias,
    }), encoding="utf-8")
    return pasta


class JsonAdulterado(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = Path(self._tmp.name)

    def test_nomes_com_caminho_sao_rejeitados_e_a_pasta_cai_na_varredura(self):
        for arquivo in ("..\\..\\segredo.png", "../segredo.png", "sub/01_tela.png", "C:\\x.png", "..", ""):
            with self.subTest(arquivo=arquivo):
                pasta = pasta_com_json(self.raiz, [
                    {"numero": 1, "arquivo": arquivo, "rotulo": "Tela inteira", "hora": None}])
                teste = metadados.ler(pasta)
                self.assertEqual([e.arquivo for e in teste.evidencias], ["01_tela.png"])  # só o real
                import shutil
                shutil.rmtree(pasta)

    def test_pdf_com_caminho_tambem_e_rejeitado(self):
        pasta = pasta_com_json(self.raiz, [
            {"numero": 1, "arquivo": "01_tela.png", "rotulo": "Tela inteira", "hora": None}],
            pdf="..\\..\\Windows\\x.pdf")
        teste = metadados.ler(pasta)
        self.assertIsNone(teste.pdf)  # caiu na varredura, que não achou PDF válido

    def test_json_legitimo_continua_valendo(self):
        pasta = pasta_com_json(self.raiz, [
            {"numero": 1, "arquivo": "01_tela.png", "rotulo": "Tela inteira", "hora": "2026-10-09T14:00:00"}])
        teste = metadados.ler(pasta)
        self.assertEqual(teste.pdf, "Evidencias - T.pdf")
        self.assertEqual(teste.evidencias[0].momento.hour, 14)


@unittest.skipUnless(TEM_MCP, "pacote mcp não instalado")
class ServidorNaoSaiDaPasta(unittest.TestCase):
    def setUp(self):
        from capturador import mcp_servidor

        self.srv = mcp_servidor
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self._anterior = os.environ.get("CAPTURADOR_PASTA_BASE")
        os.environ["CAPTURADOR_PASTA_BASE"] = str(self.base)
        self.addCleanup(lambda: os.environ.pop("CAPTURADOR_PASTA_BASE", None) if self._anterior is None
                        else os.environ.__setitem__("CAPTURADOR_PASTA_BASE", self._anterior))

    def test_imagem_fora_da_pasta_nunca_entra_no_pdf_nem_e_devolvida(self):
        # um "segredo" fora da pasta do teste, referenciado por um evidencias.json adulterado
        Image.new("RGB", (50, 50), "red").save(self.base / "segredo.png")
        pasta = self.base / "2026-10-09_1400 - Teste"
        pasta.mkdir()
        Image.new("RGB", (80, 60), "navy").save(pasta / "01_tela.png")
        (pasta / metadados.ARQUIVO).write_text(json.dumps({
            "versao": 1, "nome_teste": "Teste", "testador": "", "pdf": None,
            "evidencias": [
                {"numero": 1, "arquivo": "01_tela.png", "rotulo": "Tela inteira", "hora": None},
                {"numero": 2, "arquivo": "..\\segredo.png", "rotulo": "Tela inteira", "hora": None},
            ]}), encoding="utf-8")
        dados = self.srv.obter_teste(pasta.name)
        self.assertEqual([e["arquivo"] for e in dados["evidencias"]], ["01_tela.png"])
        resultado = self.srv.salvar_relatorio_pdf(pasta.name, "Relatório", "texto")
        self.assertEqual(resultado["evidencias_anexadas"], 1)  # o segredo ficou de fora


if __name__ == "__main__":
    unittest.main()
