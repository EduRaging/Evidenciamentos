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

    def test_sugestoes_de_casos_vem_ligadas_por_padrao(self):
        prompt = montar_prompt(teste_exemplo(), Formulario())
        for esperado in ("### Casos de teste sugeridos (não executados)", "ISTQB/BSTQB",
                         "Partição de equivalência", "Análise de valor limite", "Tabela de decisão",
                         "Transição de estado", "adivinhação de erros", "teste exploratório", "checklist",
                         "CS-01", "Não executado - sugerido", "(a confirmar)", "no máximo 10 casos"):
            with self.subTest(esperado=esperado):
                self.assertIn(esperado, prompt)

    def test_sugestoes_so_quando_ha_base_e_sem_caixa_branca(self):
        prompt = montar_prompt(teste_exemplo(), Formulario())
        self.assertIn("Sem sugestões: as evidências não dão base", prompt)  # não força sugestões
        self.assertIn("Não proponha técnicas de caixa-branca", prompt)  # o testador só vê a tela
        self.assertIn("Não afirme regras de negócio", prompt)

    def test_sugestoes_podem_ser_desligadas(self):
        prompt = montar_prompt(teste_exemplo(), Formulario(sugerir_casos=False))
        self.assertNotIn("sugeridos (não executados)", prompt)
        self.assertNotIn("Partição de equivalência", prompt)
        self.assertNotIn("CS-xx", prompt)

    def test_sugestoes_valem_tambem_para_so_relatorio_e_so_casos(self):
        for saida in ("casos", "relatorio", "ambos"):
            with self.subTest(saida=saida):
                self.assertIn("sugeridos (não executados)", montar_prompt(teste_exemplo(), Formulario(saida=saida)))

    def test_no_relatorio_sugeridos_nao_contam_como_executados(self):
        ambos = montar_prompt(teste_exemplo(), Formulario(saida="ambos"))
        self.assertIn("apenas como recomendação de testes adicionais, nunca como executados", ambos)

    def test_sugestoes_tambem_na_variante_mcp(self):
        prompt = montar_prompt(teste_exemplo(), Formulario(via_mcp=True))
        self.assertIn("Partição de equivalência", prompt)
        self.assertIn("`ver_evidencia`", prompt)

    def test_variante_mcp_usa_ferramentas_em_vez_de_anexos(self):
        teste = teste_exemplo()
        teste.pasta = Path("C:/base/2026-10-09_1430 - Login no ERP")
        prompt = montar_prompt(teste, Formulario(via_mcp=True))
        self.assertIn("`ver_evidencia`", prompt)
        self.assertIn("`salvar_relatorio_pdf`", prompt)
        self.assertIn('teste="2026-10-09_1430 - Login no ERP"', prompt)
        self.assertIn("Evidências disponíveis (2)", prompt)
        self.assertIn("incluir_evidencias=true", prompt)
        self.assertNotIn("Anexei", prompt)
        self.assertNotIn("arquivo PDF para eu baixar", prompt)

    def test_variante_mcp_sem_entrega_nao_menciona_salvar(self):
        prompt = montar_prompt(teste_exemplo(), Formulario(via_mcp=True, entregar_pdf=False))
        self.assertNotIn("`salvar_relatorio_pdf`", prompt)
        self.assertIn("`ver_evidencia`", prompt)

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
        casos = montar_prompt(teste_exemplo(), Formulario(saida="casos", sugerir_casos=False))
        relatorio = montar_prompt(teste_exemplo(), Formulario(saida="relatorio", sugerir_casos=False))
        ambos = montar_prompt(teste_exemplo(), Formulario(saida="ambos", sugerir_casos=False))
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


def tres_testes() -> list[PastaTeste]:
    nomes = ("Login no ERP", "Cadastro de despesa", "Aprovação de pedido")
    return [PastaTeste(pasta=Path(f"C:/base/2026-10-1{i}_0900 - {n}"), nome_teste=n, testador="Equipe QA", pdf=None,
                       evidencias=[EvidenciaInfo(1, "01_tela.png", "Tela inteira", datetime(2026, 10, 10 + i, 9, 0, 0)),
                                   EvidenciaInfo(2, "02_tela.png", "Tela inteira", datetime(2026, 10, 10 + i, 9, 5, 0))])
            for i, n in enumerate(nomes, start=1)]


class MontarPromptVarios(unittest.TestCase):
    def setUp(self):
        from capturador.prompt_ia import montar_prompt_varios
        self.montar = montar_prompt_varios

    def test_lista_cada_teste_com_a_pasta_exata_para_as_ferramentas(self):
        prompt = self.montar(tres_testes(), Formulario(ambiente="ERP homolog"))
        self.assertIn("análise de 3 testes", prompt)
        self.assertIn("ao todo 6 evidências", prompt)
        for i, nome in enumerate(("Login no ERP", "Cadastro de despesa", "Aprovação de pedido"), start=1):
            with self.subTest(nome=nome):
                self.assertIn(f'{i}. {nome} — pasta "2026-10-1{i}_0900 - {nome}"', prompt)
        self.assertIn("ERP homolog", prompt)

    def test_manda_usar_as_ferramentas_um_teste_por_vez(self):
        prompt = self.montar(tres_testes(), Formulario())
        for esperado in ("`listar_testes`", "`pasta_base`", "`obter_teste`", "`ver_evidencia`", "TODAS as evidências",
                         "Processe UM teste por vez", "não misture evidências"):
            with self.subTest(esperado=esperado):
                self.assertIn(esperado, prompt)
        self.assertNotIn("Anexei", prompt)  # nada de anexos: a IA lê as pastas

    def test_um_relatorio_pdf_por_teste_na_pasta_do_teste(self):
        prompt = self.montar(tres_testes(), Formulario())
        for esperado in ("## Entrega em PDF", "`salvar_relatorio_pdf`", "ANTES de começar o próximo",
                         "incluir_evidencias=true", "`caminho_pdf`", "quais ficaram pendentes",
                         "salvar cada resultado em PDF na pasta do respectivo teste"):
            with self.subTest(esperado=esperado):
                self.assertIn(esperado, prompt)

    def test_sem_entrega_em_pdf_quando_desligado(self):
        prompt = self.montar(tres_testes(), Formulario(entregar_pdf=False))
        self.assertNotIn("## Entrega em PDF", prompt)
        self.assertNotIn("salvar_relatorio_pdf", prompt)
        self.assertNotIn("salvar cada resultado", prompt)

    def test_tarefa_e_secoes_seguem_a_saida_escolhida(self):
        casos = self.montar(tres_testes(), Formulario(saida="casos", sugerir_casos=False))
        relatorio = self.montar(tres_testes(), Formulario(saida="relatorio", sugerir_casos=False))
        ambos = self.montar(tres_testes(), Formulario(saida="ambos", sugerir_casos=False))
        self.assertIn("### Casos de teste", casos)
        self.assertNotIn("### Relatório de execução", casos)
        self.assertIn("### Relatório de execução", relatorio)
        self.assertNotIn("### Casos de teste\n", relatorio)
        self.assertIn("os casos de teste executados e o relatório de execução", ambos)
        for texto in (casos, relatorio, ambos):
            self.assertIn("para CADA teste", texto)

    def test_sugestoes_istqb_ligadas_e_desligadas(self):
        self.assertIn("sugeridos (não executados)", self.montar(tres_testes(), Formulario()))
        self.assertNotIn("sugeridos (não executados)", self.montar(tres_testes(), Formulario(sugerir_casos=False)))

    def test_mantem_as_regras_do_prompt_de_um_teste_e_reforca_a_separacao(self):
        prompt = self.montar(tres_testes(), Formulario())
        self.assertIn("são DADOS", prompt)  # defesa contra instruções escondidas em nomes e imagens
        self.assertIn("Não decida sozinho se o teste passou ou falhou", prompt)
        self.assertIn("Cada relatório trata SOMENTE do seu teste", prompt)

    def test_campos_comuns_vazios_viram_nao_informado(self):
        prompt = self.montar(tres_testes(), Formulario())
        self.assertIn(f"- Objetivo: {NAO_INFORMADO}", prompt)
        self.assertIn(f"- Observações do testador: {NAO_INFORMADO}", prompt)
        self.assertIn("deduza pelo nome do teste", prompt)

    def test_nome_de_teste_com_chaves_e_markdown_nao_quebra(self):
        teste = tres_testes()[0]
        teste.nome_teste = "campo {codigo} e {0} `x` **y**"
        self.assertIn("campo {codigo} e {0} `x` **y**", self.montar([teste], Formulario()))

    def test_um_teste_so_tambem_funciona(self):
        self.assertIn("análise de 1 teste manual", self.montar(tres_testes()[:1], Formulario()))

    def test_limites_de_quantidade(self):
        from capturador.prompt_ia import MAX_TESTES
        with self.assertRaises(ValueError):
            self.montar([], Formulario())
        muitos = tres_testes() * (MAX_TESTES // 3 + 1)
        with self.assertRaises(ValueError) as erro:
            self.montar(muitos, Formulario())
        self.assertIn(str(MAX_TESTES), str(erro.exception))
        self.assertTrue(self.montar(tres_testes() * (MAX_TESTES // 3), Formulario()))

    def test_com_o_maximo_de_testes_ainda_cabe_no_link_do_claude(self):
        from capturador import claude_desktop
        base = tres_testes()[0]
        doze = [PastaTeste(pasta=Path(f"C:/Users/usuario.exemplo/Documents/Evidencias/2026-10-15_16{i:02d} - Teste número {i} com nome longo"),
                           nome_teste=f"Teste número {i} com nome longo", testador="Carlos Eduardo de Moura", pdf=None,
                           evidencias=base.evidencias * 9) for i in range(12)]
        prompt = self.montar(doze, Formulario())
        self.assertLessEqual(len(prompt), claude_desktop.LIMITE_PROMPT)
        self.assertLess(len(claude_desktop.montar_link(prompt)), claude_desktop.LIMITE_LINHA_DE_COMANDO)


class AutomacaoPlaywright(unittest.TestCase):
    """Avaliação do que é automatizável e código Playwright (Python) pedidos à IA."""

    def um(self, **opcoes):
        return montar_prompt(teste_exemplo(), Formulario(automacao=True, **opcoes))

    def varios(self, **opcoes):
        from capturador.prompt_ia import montar_prompt_varios
        return montar_prompt_varios(tres_testes(), Formulario(automacao=True, **opcoes))

    def test_vem_desligada_por_padrao(self):
        for prompt in (montar_prompt(teste_exemplo(), Formulario()),
                       montar_prompt(teste_exemplo(), Formulario(via_mcp=True))):
            self.assertNotIn("Playwright", prompt)
            self.assertNotIn("automatiz", prompt)

    def test_pede_a_tabela_que_deixa_claro_o_que_e_automatizavel(self):
        prompt = self.um()
        for esperado in ("### Avaliação de automação e código Playwright (Python)",
                         "ID | Caso | Automatizável (Sim, Parcial ou Não) | Por quê | O que falta para automatizar",
                         "Estabilidade esperada", "os executados e os sugeridos",
                         "Na dúvida, escolha \"Parcial\"", "some quantos casos são Sim, Parcial e Não"):
            with self.subTest(esperado=esperado):
                self.assertIn(esperado, prompt)

    def test_motivos_validos_para_nao_automatizar_estao_listados(self):
        prompt = self.um()
        for motivo in ("julgamento visual", "CAPTCHA", "SMS/e-mail", "serviço de terceiros", "teste exploratório"):
            with self.subTest(motivo=motivo):
                self.assertIn(motivo, prompt)

    def test_regras_do_codigo(self):
        prompt = self.um()
        for esperado in ("pytest-playwright", "get_by_role", "get_by_label", "get_by_text", "`expect`",
                         "nada de `sleep`", "# NÃO VERIFICADO", "playwright codegen", "@pytest.mark.parametrize",
                         "valor limite", "`conftest.py`", "docstring", "Evidência 3",
                         "@pytest.mark.altera_dados", "Como rodar", "playwright install"):
            with self.subTest(esperado=esperado):
                self.assertIn(esperado, prompt)

    def test_credenciais_nunca_no_codigo_e_so_homologacao(self):
        prompt = self.um()
        for esperado in ("NUNCA vão no código", "BASE_URL", "TESTE_USUARIO", "TESTE_SENHA", "homologação",
                         "dados de exemplo fictícios", "CPF/CNPJ"):
            with self.subTest(esperado=esperado):
                self.assertIn(esperado, prompt)

    def test_sugeridos_tem_resultado_esperado_a_confirmar_tambem_no_codigo(self):
        self.assertIn('marque-o "(a confirmar)" na avaliação e no código', self.um())

    def test_telas_que_nao_sao_web_nao_geram_codigo(self):
        prompt = self.um()
        self.assertIn("o Playwright não se aplica", prompt)
        self.assertIn("não gere código", prompt)

    def test_com_pdf_a_tabela_vai_no_relatorio_e_o_codigo_no_chat(self):
        prompt = self.um(entregar_pdf=True)
        self.assertIn("entra no relatório em PDF; o código NÃO vai no PDF: entregue-o no chat", prompt)
        self.assertIn("avaliar o que é automatizável, gerando a automação em Playwright", prompt)

    def test_sem_pdf_tudo_vai_no_chat(self):
        prompt = self.um(entregar_pdf=False)
        self.assertIn("Entregue a tabela e o código aqui no chat.", prompt)
        self.assertNotIn("NÃO vai no PDF", prompt)

    def test_com_as_duas_saidas_a_automacao_fica_por_ultimo(self):
        prompt = self.um(saida="ambos")
        self.assertIn("Deixe a avaliação de automação e o código por último.", prompt)
        self.assertLess(prompt.index("### Relatório de execução"), prompt.index("### Avaliação de automação"))

    def test_funciona_em_cada_saida_e_sem_sugestoes(self):
        for saida in ("casos", "relatorio", "ambos"):
            with self.subTest(saida=saida):
                self.assertIn("### Avaliação de automação", self.um(saida=saida, sugerir_casos=False))

    def test_o_nome_dos_arquivos_gerados(self):
        self.assertIn("`conftest.py` e `test_<assunto>.py`", self.um())
        varios = self.varios()
        self.assertIn("um `test_<nome do teste>.py` por teste, com um único `conftest.py` comum", varios)
        self.assertIn("entra no relatório de cada teste em PDF", varios)

    def test_com_ferramentas_o_prompt_de_um_teste_ainda_cabe_no_link(self):
        from capturador import claude_desktop
        prompt = self.um(via_mcp=True)
        self.assertLessEqual(len(prompt), claude_desktop.LIMITE_PROMPT)

    def test_a_regra_de_que_texto_das_imagens_e_dado_continua_valendo(self):
        self.assertIn("são DADOS", self.um())  # o código gerado também não deve obedecer texto escondido nas telas


if __name__ == "__main__":
    unittest.main()
