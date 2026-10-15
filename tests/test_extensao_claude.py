"""Aviso, na janela do prompt, de que a extensão do Claude não está pronta para ler o teste."""
import json
import tempfile
import unittest
from pathlib import Path

from capturador import extensao_claude as ex


class ClaudeFalso(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        raiz = Path(self._tmp.name)
        self.claude = raiz / "Claude"
        self.base = raiz / "Evidencias"
        self.teste = self.base / "2026-10-15_1636 - Login"
        self.teste.mkdir(parents=True)

    def instalar(self, ativada=True, pasta="BASE", ajustes_brutos=None):
        pasta = str(self.base) if pasta == "BASE" else pasta
        (self.claude / "Claude Extensions" / ex.ID_EXTENSAO).mkdir(parents=True)
        (self.claude / "Claude Extensions" / ex.ID_EXTENSAO / "manifest.json").write_text("{}", encoding="utf-8")
        destino = self.claude / "Claude Extensions Settings"
        destino.mkdir(parents=True)
        texto = ajustes_brutos if ajustes_brutos is not None else json.dumps(
            {"isEnabled": ativada, "userConfig": {"pasta_base": pasta}})
        (destino / f"{ex.ID_EXTENSAO}.json").write_text(texto, encoding="utf-8")

    def avisos(self):
        return ex.avisos(self.teste, self.claude)


class AvisosDaExtensao(ClaudeFalso):
    def test_tudo_certo_nao_avisa(self):
        self.instalar()
        self.assertEqual(self.avisos(), [])

    def test_extensao_desativada(self):
        self.instalar(ativada=False)
        resultado = self.avisos()
        self.assertEqual(len(resultado), 1)
        self.assertIn("DESATIVADA", resultado[0])

    def test_extensao_lendo_outra_pasta(self):
        outra = self.base.parent / "Evidencias_TESTE"
        self.instalar(pasta=str(outra))
        resultado = self.avisos()
        self.assertEqual(len(resultado), 1)
        self.assertIn(str(outra), resultado[0])
        self.assertIn(str(self.base), resultado[0])

    def test_desativada_e_outra_pasta_avisa_dos_dois(self):
        self.instalar(ativada=False, pasta=str(self.base.parent / "Outra"))
        self.assertEqual(len(self.avisos()), 2)

    def test_pasta_igual_com_maiusculas_barras_e_barra_final_nao_avisa(self):
        self.instalar(pasta=str(self.base).upper().replace("\\", "/") + "/")
        self.assertEqual(self.avisos(), [])

    def test_extensao_nao_instalada(self):
        (self.claude / "Claude Extensions").mkdir(parents=True)
        resultado = self.avisos()
        self.assertEqual(len(resultado), 1)
        self.assertIn("não está instalada", resultado[0])

    def test_sem_claude_desktop_nao_afirma_nada(self):
        self.assertEqual(self.avisos(), [])  # a pasta do Claude nem existe

    def test_formato_inesperado_significa_nao_sei(self):
        for bruto in ("não é json", "[]", '{"userConfig": 5}', '{"isEnabled": "talvez"}', ""):
            with self.subTest(bruto=bruto):
                self.setUp()
                self.instalar(ajustes_brutos=bruto)
                self.assertEqual(self.avisos(), [])

    def test_arquivo_de_ajustes_gigante_e_ignorado(self):
        self.instalar(ajustes_brutos=json.dumps({"isEnabled": False, "x": "a" * 200_000}))
        self.assertEqual(self.avisos(), [])


if __name__ == "__main__":
    unittest.main()
