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


@unittest.skipUnless(TEM_MCP, "pacote mcp não instalado")
class RoteiroDoCicloPeloServidor(unittest.TestCase):
    """`salvar_casos` e o prompt `gerar_roteiro`: a IA escreve o roteiro, o servidor confina e valida tudo."""

    CASO = {"id": "CT-01", "titulo": "Login válido", "objetivo": "Entrar no sistema", "tecnica": "Partição de equivalência",
            "prioridade": "Alta", "passos": [{"acao": "Entrar com dados válidos", "resultado_esperado": "Painel exibido"}]}

    def setUp(self):
        from capturador import ciclos, mcp_servidor
        from capturador.sessao import Sessao

        self.srv, self.ciclos = mcp_servidor, ciclos
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self._anterior = os.environ.get("CAPTURADOR_PASTA_BASE")
        os.environ["CAPTURADOR_PASTA_BASE"] = str(self.base)
        self.addCleanup(lambda: os.environ.pop("CAPTURADOR_PASTA_BASE", None) if self._anterior is None
                        else os.environ.__setitem__("CAPTURADOR_PASTA_BASE", self._anterior))
        sessao = Sessao(self.base / "_em_andamento")
        sessao.adicionar(Image.new("RGB", (300, 200), "navy"), "tela")
        self.teste = sessao.finalizar("Cadastro de fornecedor", "QA", self.base).name
        self.ciclo = ciclos.criar_ciclo(self.base, {"nome": "Ciclo - Cadastro", "testes_base": [self.teste]})

    def _erro(self, chamada, *args, **kwargs):
        from mcp.server.mcpserver.exceptions import ToolError

        with self.assertRaises(ToolError) as contexto:
            chamada(*args, **kwargs)
        return str(contexto.exception)

    def _salvar(self, casos=None, **extra):
        return self.srv.salvar_casos(self.ciclo.pasta.name, [self.CASO] if casos is None else casos, **extra)

    def test_grava_o_roteiro_e_o_app_consegue_ler(self):
        resposta = self._salvar([self.CASO, {**self.CASO, "id": "CT-02", "prioridade": "baixa"}],
                                ciclo_sugerido={"objetivo": "Validar o cadastro", "escopo": ["Cadastro"]},
                                observacoes=["Qual a regra de CNPJ duplicado?"])
        self.assertEqual((resposta["arquivo"], resposta["casos"], resposta["por_prioridade"]),
                         ("roteiro-001.json", 2, {"Alta": 1, "Baixa": 1}))
        self.assertTrue(Path(resposta["caminho"]).samefile(self.ciclo.pasta / "roteiro-001.json"))  # 8.3 x nome longo
        roteiro = self.ciclos.ler_roteiro_mais_recente(self.ciclo.pasta)
        self.assertEqual([c.id for c in roteiro.casos], ["CT-01", "CT-02"])
        self.assertEqual((roteiro.ciclo_sugerido["objetivo"], roteiro.observacoes), ("Validar o cadastro", ["Qual a regra de CNPJ duplicado?"]))

    def test_cada_chamada_cria_o_proximo_arquivo_e_nunca_sobrescreve(self):
        primeiro = self._salvar()["arquivo"]
        segundo = self._salvar()["arquivo"]
        self.assertEqual((primeiro, segundo), ("roteiro-001.json", "roteiro-002.json"))
        self.assertEqual(self.ciclos.contar_roteiros(self.ciclo.pasta), 2)

    def test_roteiro_invalido_volta_com_a_mensagem_para_a_ia_se_corrigir(self):
        mensagem = self._erro(self._salvar, [{**self.CASO, "prioridade": "urgentíssima"}, {**self.CASO, "id": "x"}])
        self.assertIn("casos[0].prioridade", mensagem)
        self.assertIn("casos[1].id", mensagem)
        self.assertEqual(self.ciclos.contar_roteiros(self.ciclo.pasta), 0)  # nada foi gravado

    def test_ciclo_sugerido_e_observacoes_invalidos_tambem_sao_recusados_sem_gravar(self):
        self._erro(self._salvar, ciclo_sugerido="texto solto")
        self._erro(self._salvar, observacoes=["x"] * 50)
        self.assertEqual(self.ciclos.contar_roteiros(self.ciclo.pasta), 0)

    def test_so_aceita_o_nome_de_um_ciclo_existente_dentro_de__ciclos(self):
        for nome in ("..", "a/b", "..\\x", "C:\\Windows", "_oculta", "nao existe", "", self.teste):
            with self.subTest(nome=nome):
                self._erro(self.srv.salvar_casos, nome, [self.CASO])
        antes = sorted(p.name for p in self.base.rglob("*"))
        self._erro(self.srv.salvar_casos, "../" + self.teste, [self.CASO])
        self.assertEqual(sorted(p.name for p in self.base.rglob("*")), antes)

    def test_pasta_em__ciclos_sem_ciclo_json_nao_recebe_nada(self):
        intrusa = self.base / "_ciclos" / "2026-10-19_1000 - Intrusa"
        intrusa.mkdir()
        self._erro(self.srv.salvar_casos, intrusa.name, [self.CASO])
        self.assertEqual(list(intrusa.iterdir()), [])

    def test_ciclo_json_adulterado_nao_recebe_roteiro(self):
        (self.ciclo.pasta / "ciclo.json").write_text("{adulterado", encoding="utf-8")
        self._erro(self._salvar)

    def test_limite_de_roteiros_por_ciclo(self):
        for n in range(1, self.srv.MAX_ROTEIROS_POR_CICLO + 1):
            (self.ciclo.pasta / f"roteiro-{n:03d}.json").write_text("{}", encoding="utf-8")
        self.assertIn(str(self.srv.MAX_ROTEIROS_POR_CICLO), self._erro(self._salvar))

    def test_gravacoes_simultaneas_geram_arquivos_distintos(self):
        import threading

        resultados, erros = [], []

        def gravar():
            try:
                resultados.append(self._salvar()["arquivo"])
            except Exception as exc:  # noqa: BLE001
                erros.append(exc)

        threads = [threading.Thread(target=gravar) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(erros, [])
        self.assertEqual(len(set(resultados)), 6)
        self.assertEqual(self.ciclos.contar_roteiros(self.ciclo.pasta), 6)

    def test_ferramenta_exposta_como_gravacao_nao_destrutiva(self):
        import asyncio

        ferramentas = {t.name: t for t in asyncio.run(self.srv.mcp.list_tools())}
        self.assertIn("salvar_casos", ferramentas)
        anotacoes = ferramentas["salvar_casos"].annotations
        self.assertFalse(anotacoes.read_only_hint)
        self.assertFalse(anotacoes.destructive_hint)
        self.assertFalse(anotacoes.open_world_hint)
        self.assertTrue(ferramentas["listar_testes"].annotations.read_only_hint)  # as leituras seguem somente leitura

    def test_prompt_gerar_roteiro_traz_o_ciclo_as_telas_e_a_ferramenta(self):
        prompt = self.srv.gerar_roteiro(self.ciclo.pasta.name)
        for esperado in ("Ciclo - Cadastro", f'pasta "{self.teste}"', "`salvar_casos`", f'ciclo="{self.ciclo.pasta.name}"',
                         "`ver_evidencia`", "ISTQB CTFL 4.0"):
            with self.subTest(esperado=esperado):
                self.assertIn(esperado, prompt)

    def test_prompt_avisa_de_teste_de_referencia_que_sumiu(self):
        import shutil

        shutil.rmtree(self.base / self.teste)
        prompt = self.srv.gerar_roteiro(self.ciclo.pasta.name)
        self.assertIn("não foram encontrados", prompt)
        self.assertIn(self.teste, prompt)

    def test_prompt_recusa_ciclo_inexistente(self):
        with self.assertRaises(ValueError):
            self.srv.gerar_roteiro("nao existe")


if __name__ == "__main__":
    unittest.main()
