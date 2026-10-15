"""Testes do servidor MCP. Só rodam com o pacote `mcp` instalado (pip install -r requirements-mcp.txt)."""
import base64
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image

TEM_MCP = importlib.util.find_spec("mcp") is not None


@unittest.skipUnless(TEM_MCP, "pacote mcp não instalado")
class FerramentasDoServidor(unittest.TestCase):
    def setUp(self):
        from capturador import mcp_servidor
        from capturador.sessao import Sessao

        self.srv = mcp_servidor
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self._anterior = os.environ.get("CAPTURADOR_PASTA_BASE")
        os.environ["CAPTURADOR_PASTA_BASE"] = str(self.base)
        self.addCleanup(self._restaurar_ambiente)

        sessao = Sessao(self.base / "_em_andamento")
        sessao.adicionar(Image.new("RGB", (1920, 1080), "navy"), "tela")
        sessao.adicionar(Image.new("RGB", (640, 420), "green"), "recorte")
        self.pasta = sessao.finalizar("Login no ERP", "Equipe QA", self.base)
        self.nome = self.pasta.name

    def _restaurar_ambiente(self):
        if self._anterior is None:
            os.environ.pop("CAPTURADOR_PASTA_BASE", None)
        else:
            os.environ["CAPTURADOR_PASTA_BASE"] = self._anterior

    def _erro(self, chamada, *args, **kwargs):
        from mcp.server.mcpserver.exceptions import ToolError

        with self.assertRaises(ToolError) as contexto:
            chamada(*args, **kwargs)
        return str(contexto.exception)

    def test_listar_e_obter(self):
        resposta = self.srv.listar_testes()
        self.assertEqual(resposta["pasta_base"], str(self.base))  # a IA precisa poder dizer qual pasta lê
        lista = resposta["testes"]
        self.assertEqual([t["teste"] for t in lista], [self.nome])
        self.assertEqual(lista[0]["evidencias"], 2)
        dados = self.srv.obter_teste(self.nome)
        self.assertEqual([e["numero"] for e in dados["evidencias"]], [1, 2])
        self.assertEqual(dados["testador"], "Equipe QA")

    def test_listar_ignora_pastas_de_trabalho_e_estranhas(self):
        (self.base / "_cfg").mkdir()
        (self.base / "qualquer coisa").mkdir()
        self.assertEqual(len(self.srv.listar_testes()["testes"]), 1)

    def test_ver_evidencia_reduz_imagens_grandes_e_preserva_pequenas(self):
        grande = Image.open(io.BytesIO(base64.b64decode(
            self.srv.ver_evidencia(self.nome, 1).to_image_content().data)))
        pequena = Image.open(io.BytesIO(base64.b64decode(
            self.srv.ver_evidencia(self.nome, 2).to_image_content().data)))
        self.assertEqual(max(grande.size), self.srv.LADO_MAXIMO)
        self.assertEqual(pequena.size, (640, 420))

    def test_nao_sai_da_pasta_de_evidencias(self):
        for entrada in ("..", "../..", "C:\\Windows", "a/b", "a\\b", "", "   ", "nao_existe", "_em_andamento"):
            with self.subTest(entrada=entrada):
                self._erro(self.srv.obter_teste, entrada)
                self._erro(self.srv.ver_evidencia, entrada, 1)
                self._erro(self.srv.salvar_relatorio_pdf, entrada, "T", "texto")

    def test_mensagens_de_erro_ajudam_a_ia_a_se_corrigir(self):
        self.assertIn("de 1 a 2", self._erro(self.srv.ver_evidencia, self.nome, 9))
        self.assertIn("listar_testes", self._erro(self.srv.obter_teste, "nao_existe"))

    def test_salvar_relatorio_nunca_sobrescreve(self):
        a = self.srv.salvar_relatorio_pdf(self.nome, "Relatório de testes", "# Oi\n\ntexto")
        b = self.srv.salvar_relatorio_pdf(self.nome, "Relatório de testes", "# Oi\n\ntexto", False)
        self.assertEqual(a["pdf"], "Relatório de testes.pdf")
        self.assertEqual(b["pdf"], "Relatório de testes (2).pdf")
        self.assertTrue((self.pasta / a["pdf"]).is_file() and (self.pasta / b["pdf"]).is_file())
        self.assertEqual(a["evidencias_anexadas"], 2)
        self.assertEqual(b["evidencias_anexadas"], 0)
        self.assertEqual((self.pasta / a["markdown"]).read_text(encoding="utf-8"), "# Oi\n\ntexto")
        # a IA informa onde o arquivo foi parar (o caminho vem resolvido, sem o formato curto 8.3)
        self.assertTrue(Path(a["caminho_pdf"]).samefile(self.pasta / a["pdf"]))
        self.assertTrue(Path(a["caminho_markdown"]).samefile(self.pasta / a["markdown"]))

    def test_um_md_ja_existente_tambem_desvia_o_nome_do_par(self):
        (self.pasta / "Relatório.md").write_text("antigo", encoding="utf-8")
        resultado = self.srv.salvar_relatorio_pdf(self.nome, "Relatório", "# novo")
        self.assertEqual(resultado["pdf"], "Relatório (2).pdf")
        self.assertEqual((self.pasta / "Relatório.md").read_text(encoding="utf-8"), "antigo")  # intacto

    def test_markdown_e_gravado_antes_do_pdf(self):
        from unittest import mock

        with mock.patch.object(self.srv, "gerar_pdf_de_markdown", side_effect=RuntimeError("falha simulada")):
            with self.assertRaises(Exception):
                self.srv.salvar_relatorio_pdf(self.nome, "Parcial", "# conteudo da IA")
        self.assertEqual((self.pasta / "Parcial.md").read_text(encoding="utf-8"), "# conteudo da IA")
        self.assertFalse((self.pasta / "Parcial.pdf").exists())

    def test_sem_pasta_configurada_o_servidor_recusa_em_todas_as_ferramentas(self):
        """O incidente: sem a variável, o servidor caía na pasta REAL do app. Agora tem que recusar."""
        casos = {
            "ausente": None,
            "vazia": "",
            "so espacos": "   ",
            "nao substituida pelo host": "${user_config.pasta_base}",
            "inexistente": str(self.base / "nao_existe"),
        }
        for descricao, valor in casos.items():
            with self.subTest(pasta=descricao):
                if valor is None:
                    os.environ.pop("CAPTURADOR_PASTA_BASE", None)
                else:
                    os.environ["CAPTURADOR_PASTA_BASE"] = valor
                self._erro(self.srv.listar_testes)
                self._erro(self.srv.obter_teste, self.nome)
                self._erro(self.srv.ver_evidencia, self.nome, 1)
                self._erro(self.srv.salvar_relatorio_pdf, self.nome, "T", "texto")

    def test_mensagem_de_pasta_nao_configurada_diz_o_que_fazer(self):
        os.environ.pop("CAPTURADOR_PASTA_BASE", None)
        mensagem = self._erro(self.srv.listar_testes)
        self.assertIn("não está configurada", mensagem)
        self.assertIn("Extensões", mensagem)

    def test_salvar_valida_tamanhos(self):
        self._erro(self.srv.salvar_relatorio_pdf, self.nome, "", "x")
        self._erro(self.srv.salvar_relatorio_pdf, self.nome, "t", "")
        self._erro(self.srv.salvar_relatorio_pdf, self.nome, "t" * 151, "x")
        self._erro(self.srv.salvar_relatorio_pdf, self.nome, "t", "x" * (self.srv.MAX_MARKDOWN + 1))

    def test_prompt_mcp_manda_usar_as_ferramentas(self):
        prompt = self.srv.analisar_teste(self.nome, objetivo="Validar o login")
        for esperado in ("`ver_evidencia`", "`salvar_relatorio_pdf`", f'teste="{self.nome}"',
                         "Validar o login", "Não invente"):
            self.assertIn(esperado, prompt)
        self.assertNotIn("Anexei", prompt)
        self.assertIn("sugeridos (não executados)", prompt)  # sugestões ISTQB/BSTQB por padrão

    def test_prompt_mcp_sugestoes_podem_ser_desligadas(self):
        prompt = self.srv.analisar_teste(self.nome, sugerir_casos=False)
        self.assertNotIn("sugeridos (não executados)", prompt)


if __name__ == "__main__":
    unittest.main()
