"""Chamada do Claude Code pelo app (sem chamar o Claude de verdade): comando, pasta de trabalho, resposta e falhas."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from capturador import ciclos, fluxo_ciclo, ia_local
from capturador.sessao import Sessao

CASO = {"id": "CT-01", "titulo": "Login válido", "objetivo": "Entrar", "tecnica": "Partição de equivalência",
        "prioridade": "Alta", "passos": [{"acao": "Entrar", "resultado_esperado": "Painel"}]}
ROTEIRO = {"casos": [CASO], "ciclo_sugerido": {"objetivo": "Validar o login", "escopo": ["Login"]}, "observacoes": ["Dúvida?"]}


def saida_ok(objeto=None, **extra) -> str:
    return json.dumps({"type": "result", "subtype": "success", "is_error": False,
                       "structured_output": ROTEIRO if objeto is None else objeto, "total_cost_usd": 0.12, **extra})


class ProcessoFalso:
    def __init__(self, stdout="", stderr="", demora=False):
        self.stdout, self.stderr, self.demora = stdout, stderr, demora
        self.entrada, self.terminado, self.morto = None, False, False

    def communicate(self, entrada=None, timeout=None):
        if self.demora and not self.morto:
            self.morto = True
            raise subprocess.TimeoutExpired("claude", timeout)
        self.entrada = entrada
        return self.stdout, self.stderr

    def terminate(self):
        self.terminado = True

    def kill(self):
        self.morto = True


class FabricaDeProcessos:
    """Substitui subprocess.Popen: guarda os argumentos e devolve o processo falso."""

    def __init__(self, processo):
        self.processo, self.chamadas = processo, []

    def __call__(self, comando, **opcoes):
        self.chamadas.append((comando, opcoes))
        return self.processo


class Localizar(unittest.TestCase):
    def test_escolhe_a_versao_mais_nova_comparando_numeros_e_nao_texto(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            for versao in ("2.1.9", "2.1.100", "2.1.299"):
                (raiz / versao / "abc").mkdir(parents=True)
                (raiz / versao / "abc" / "claude.exe").write_bytes(b"MZ")
            self.assertEqual(ia_local.localizar_claude([raiz]).parent.parent.name, "2.1.299")

    def test_sem_nada_instalado_cai_no_path_ou_em_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("shutil.which", return_value=None):
                self.assertIsNone(ia_local.localizar_claude([Path(tmp)]))
            with mock.patch("shutil.which", return_value="C:\\bin\\claude.exe"):
                self.assertEqual(ia_local.localizar_claude([Path(tmp)]), Path("C:\\bin\\claude.exe"))

    def test_ignora_pasta_sem_o_executavel(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "2.9.9" / "x").mkdir(parents=True)
            with mock.patch("shutil.which", return_value=None):
                self.assertIsNone(ia_local.localizar_claude([Path(tmp)]))


class Login(unittest.TestCase):
    def estado(self, stdout="", erro=None):
        def executar(*a, **k):
            if erro:
                raise erro
            return subprocess.CompletedProcess(a, 0, stdout=stdout, stderr="")
        return ia_local.esta_logado(Path("claude.exe"), executar)

    def test_logado_e_nao_logado(self):
        self.assertTrue(self.estado('{"loggedIn": true, "authMethod": "claude.ai"}'))
        self.assertFalse(self.estado('{"loggedIn": false, "authMethod": "none"}'))

    def test_qualquer_duvida_conta_como_nao_logado(self):
        for saida in ("", "não é json", "[]", '{"loggedIn": "talvez"}'.replace('"talvez"', "0")):
            with self.subTest(saida=saida):
                self.assertFalse(self.estado(saida))
        self.assertFalse(self.estado(erro=OSError("sem executável")))
        self.assertFalse(self.estado(erro=subprocess.TimeoutExpired("claude", 30)))

    def test_o_login_abre_numa_janela_de_console_visivel_com_a_conta_do_plano(self):
        chamadas = []
        ia_local.abrir_login(Path("C:/x/claude.exe"), lambda comando, **o: chamadas.append((comando, o)))
        comando, opcoes = chamadas[0]
        self.assertEqual(comando[1:], ["auth", "login", "--claudeai"])
        self.assertEqual(opcoes["creationflags"], ia_local.NOVO_CONSOLE)


class PastaDeTrabalho(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = Path(self._tmp.name)
        self.base = self.raiz / "Evidencias"

    def criar(self, nome, imagens=3, tamanho=(200, 120)):
        sessao = Sessao(self.raiz / f"trab_{nome[:3]}")
        for _ in range(imagens):
            sessao.adicionar(Image.new("RGB", tamanho, "navy"), "tela")
        return sessao.finalizar(nome, "QA", self.base)

    def criar_testes(self, *pastas):
        from capturador import metadados
        return [metadados.ler(p) for p in pastas]

    def test_copia_so_as_telas_reduzidas_e_nenhum_outro_arquivo_do_teste(self):
        pasta = self.criar("Login", 2, (4000, 3000))
        (pasta / "Relatório de testes - Login.pdf").write_bytes(b"%PDF segredo")
        (pasta / "Relatório de testes - Login.md").write_text("relatório antigo", encoding="utf-8")
        destino = self.raiz / "trabalho"
        destino.mkdir()
        mapa = ia_local.preparar_pasta_de_trabalho(self.criar_testes(pasta), destino)
        arquivos = sorted(p.relative_to(destino).as_posix() for p in destino.rglob("*") if p.is_file())
        self.assertEqual(arquivos, ["t1/01.png", "t1/02.png"])
        with Image.open(destino / "t1" / "01.png") as img:
            self.assertEqual(max(img.size), ia_local.LADO_MAXIMO)
        self.assertEqual(mapa, {"t1": (pasta.name, [(1, "01.png"), (2, "02.png")])})

    def test_telas_pequenas_nao_sao_ampliadas(self):
        pasta = self.criar("Login", 1, (300, 200))
        destino = self.raiz / "trabalho"
        destino.mkdir()
        ia_local.preparar_pasta_de_trabalho(self.criar_testes(pasta), destino)
        with Image.open(destino / "t1" / "01.png") as img:
            self.assertEqual(img.size, (300, 200))

    def test_limite_de_imagens_com_telas_espacadas_e_numero_original_preservado(self):
        pasta = self.criar("Login", 12)
        destino = self.raiz / "trabalho"
        destino.mkdir()
        mapa = ia_local.preparar_pasta_de_trabalho(self.criar_testes(pasta), destino, max_imagens=4)
        numeros = [n for n, _ in mapa["t1"][1]]
        self.assertEqual(len(numeros), 4)
        self.assertEqual((numeros[0], numeros[-1]), (1, 12))  # primeira e última sempre entram
        self.assertEqual(sorted(p.name for p in (destino / "t1").iterdir()), [f"{n:02d}.png" for n in numeros])

    def test_varios_testes_dividem_o_limite_e_ficam_em_subpastas_proprias(self):
        pastas = [self.criar(f"Teste {i}", 10) for i in range(1, 5)]
        destino = self.raiz / "trabalho"
        destino.mkdir()
        mapa = ia_local.preparar_pasta_de_trabalho(self.criar_testes(*pastas), destino, max_imagens=8)
        self.assertEqual(sorted(mapa), ["t1", "t2", "t3", "t4"])
        self.assertTrue(all(len(v[1]) == 3 for v in mapa.values()))  # no mínimo 3 por teste
        self.assertEqual([v[0] for v in mapa.values()], [p.name for p in pastas])

    def test_pngs_invalidos_e_atalhos_sao_pulados(self):
        pasta = self.criar("Login", 3)
        (pasta / "02_tela.png").write_bytes(b"BM" + b"\x00" * 100)  # outro formato com nome de .png
        destino = self.raiz / "trabalho"
        destino.mkdir()
        mapa = ia_local.preparar_pasta_de_trabalho(self.criar_testes(pasta), destino)
        self.assertEqual([n for n, _ in mapa["t1"][1]], [1, 3])

    def test_teste_sem_nenhuma_tela_aproveitavel_nao_entra_no_mapa(self):
        pasta = self.criar("Login", 1)
        (pasta / "01_tela.png").write_bytes(b"lixo")
        destino = self.raiz / "trabalho"
        destino.mkdir()
        self.assertEqual(ia_local.preparar_pasta_de_trabalho(self.criar_testes(pasta), destino), {})

    def test_espacadas(self):
        self.assertEqual(ia_local._espacadas([1, 2, 3], 5), [1, 2, 3])
        self.assertEqual(ia_local._espacadas(list(range(10)), 1), [0])
        escolhidas = ia_local._espacadas(list(range(100)), 5)
        self.assertEqual((escolhidas[0], escolhidas[-1], len(escolhidas)), (0, 99, 5))
        self.assertEqual(escolhidas, sorted(set(escolhidas)))


class Comando(unittest.TestCase):
    def test_modo_restrito_so_com_read_e_sem_permissao_para_nada_alem_disso(self):
        c = ia_local.montar_comando(Path("C:/x/claude.exe"))
        pares = {c[i]: c[i + 1] for i in range(len(c) - 1)}
        self.assertEqual(c[0], "C:\\x\\claude.exe".replace("\\", os.sep) if os.sep == "/" else str(Path("C:/x/claude.exe")))
        self.assertIn("-p", c)
        self.assertEqual((pares["--tools"], pares["--allowedTools"]), ("Read", "Read"))
        self.assertEqual((pares["--permission-mode"], pares["--permission-prompts"]), ("dontAsk", "none"))
        for bandeira in ("--restricted", "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"):
            self.assertIn(bandeira, c)
        self.assertEqual(pares["--output-format"], "json")
        self.assertIn("--max-budget-usd", c)

    def test_nada_perigoso_na_linha_de_comando(self):
        texto = " ".join(ia_local.montar_comando(Path("claude.exe")))
        for proibido in ("--dangerously-skip-permissions", "bypassPermissions", "Bash", "Write", "Edit", "WebFetch",
                         "--add-dir", "--mcp-config", "acceptEdits"):
            self.assertNotIn(proibido, texto)

    def test_o_esquema_vai_junto_e_e_json_valido(self):
        c = ia_local.montar_comando(Path("claude.exe"))
        esquema = json.loads(c[c.index("--json-schema") + 1])
        self.assertEqual(esquema, ia_local.ESQUEMA_ROTEIRO)
        self.assertEqual(esquema["required"], ["casos"])

    def test_o_esquema_e_o_validador_concordam_nos_limites(self):
        casos = ia_local.ESQUEMA_ROTEIRO["properties"]["casos"]
        self.assertEqual(casos["maxItems"], ciclos.MAX_CASOS)
        self.assertEqual(casos["items"]["properties"]["passos"]["maxItems"], ciclos.MAX_PASSOS)
        self.assertEqual(casos["items"]["properties"]["prioridade"]["enum"], list(ciclos.PRIORIDADES))


class Resposta(unittest.TestCase):
    def test_saida_estruturada(self):
        self.assertEqual(ia_local.extrair_resposta(saida_ok())["casos"][0]["id"], "CT-01")

    def test_json_dentro_do_texto_do_resultado(self):
        for texto in (json.dumps(ROTEIRO), "```json\n" + json.dumps(ROTEIRO) + "\n```", "Aqui está:\n" + json.dumps(ROTEIRO) + "\nPronto."):
            with self.subTest(texto=texto[:30]):
                saida = json.dumps({"type": "result", "is_error": False, "result": texto})
                self.assertEqual(ia_local.extrair_resposta(saida)["observacoes"], ["Dúvida?"])

    def test_nao_logado_tem_erro_proprio(self):
        saida = json.dumps({"type": "result", "is_error": True, "result": "Not logged in · Please run /login"})
        with self.assertRaises(ia_local.NaoLogado):
            ia_local.extrair_resposta(saida)

    def test_outros_erros_do_claude_viram_mensagem(self):
        saida = json.dumps({"type": "result", "is_error": True, "result": "Credit balance is too low"})
        with self.assertRaises(ia_local.ErroIA) as erro:
            ia_local.extrair_resposta(saida)
        self.assertNotIsInstance(erro.exception, ia_local.NaoLogado)
        self.assertIn("Credit balance", str(erro.exception))

    def test_respostas_ilegiveis(self):
        for saida in ("", "não é json", "[]", "5", '{"result": "sem json nenhum"}', '{"result": "[1,2]"}', "null"):
            with self.subTest(saida=saida), self.assertRaises(ia_local.ErroIA):
                ia_local.extrair_resposta(saida)


class Execucao(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.pasta = Path(self._tmp.name)

    def test_o_prompt_vai_pela_entrada_padrao_na_pasta_de_trabalho_sem_janela(self):
        processo = ProcessoFalso(saida_ok())
        fabrica = FabricaDeProcessos(processo)
        resposta = ia_local.executar(Path("claude.exe"), "PROMPT LONGO", self.pasta, abrir_processo=fabrica)
        comando, opcoes = fabrica.chamadas[0]
        self.assertEqual(processo.entrada, "PROMPT LONGO")
        self.assertNotIn("PROMPT LONGO", comando)  # nunca na linha de comando (visível a outros programas)
        self.assertEqual(opcoes["cwd"], str(self.pasta))
        self.assertEqual(opcoes["creationflags"], ia_local.SEM_JANELA)
        self.assertEqual(opcoes["errors"], "replace")  # um erro em outra codificação não derruba a leitura
        self.assertEqual(resposta["casos"][0]["id"], "CT-01")

    def test_tempo_esgotado_interrompe_o_processo(self):
        processo = ProcessoFalso(demora=True)
        with self.assertRaises(ia_local.ErroIA) as erro:
            ia_local.executar(Path("claude.exe"), "x", self.pasta, abrir_processo=FabricaDeProcessos(processo), tempo_limite=60)
        self.assertIn("1 minutos", str(erro.exception))
        self.assertTrue(processo.morto)

    def test_cancelar_antes_de_comecar_nao_abre_processo(self):
        controle = ia_local.Controle()
        controle.cancelar()
        fabrica = FabricaDeProcessos(ProcessoFalso(saida_ok()))
        with self.assertRaises(ia_local.Cancelado):
            ia_local.executar(Path("claude.exe"), "x", self.pasta, controle, fabrica)
        self.assertEqual(fabrica.chamadas, [])

    def test_cancelar_durante_a_execucao_encerra_o_processo_e_descarta_a_resposta(self):
        controle = ia_local.Controle()

        class Cancelavel(ProcessoFalso):
            def communicate(self, entrada=None, timeout=None):
                controle.cancelar()  # o usuário cancela enquanto o Claude trabalha
                return super().communicate(entrada, timeout)

        processo = Cancelavel(saida_ok())
        with self.assertRaises(ia_local.Cancelado):
            ia_local.executar(Path("claude.exe"), "x", self.pasta, controle, FabricaDeProcessos(processo))
        self.assertTrue(processo.terminado)

    def test_saida_vazia_mostra_o_erro_do_processo(self):
        with self.assertRaises(ia_local.ErroIA) as erro:
            ia_local.executar(Path("claude.exe"), "x", self.pasta,
                              abrir_processo=FabricaDeProcessos(ProcessoFalso("", "falha de rede")))
        self.assertIn("falha de rede", str(erro.exception))

    def test_executavel_que_nao_abre(self):
        def abrir(*a, **k):
            raise OSError("nao achei")
        with self.assertRaises(ia_local.ErroIA):
            ia_local.executar(Path("claude.exe"), "x", self.pasta, abrir_processo=abrir)


class GerarRoteiro(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = Path(self._tmp.name)
        self.base = self.raiz / "Evidencias"
        sessao = Sessao(self.raiz / "trab")
        for _ in range(3):
            sessao.adicionar(Image.new("RGB", (300, 200), "navy"), "tela")
        self.teste = sessao.finalizar("Cadastro de fornecedor", "QA", self.base)
        self.ciclo, _ = fluxo_ciclo.criar_a_partir_de_testes(self.base, [self.teste])

    def gerar(self, processo, **extra):
        return ia_local.gerar_roteiro(self.ciclo, self.base, Path("claude.exe"), abrir_processo=FabricaDeProcessos(processo), **extra)

    def test_de_ponta_a_ponta_o_roteiro_da_ia_e_gravado_pelo_app(self):
        processo = ProcessoFalso(saida_ok())
        arquivo, casos = self.gerar(processo)
        self.assertEqual((arquivo.name, casos), ("roteiro-001.json", 1))
        roteiro = ciclos.ler_roteiro_mais_recente(self.ciclo.pasta)
        self.assertEqual((roteiro.casos[0].id, roteiro.ciclo_sugerido["objetivo"], roteiro.observacoes), ("CT-01", "Validar o login", ["Dúvida?"]))

    def test_o_prompt_lista_as_telas_com_o_nome_do_teste_e_nao_usa_ferramentas_da_extensao(self):
        processo = ProcessoFalso(saida_ok())
        self.gerar(processo)
        self.assertIn("t1/01.png", processo.entrada)
        self.assertIn(f'Teste "{self.teste.name}"', processo.entrada)
        self.assertIn("Responda SOMENTE com um objeto JSON", processo.entrada)
        self.assertNotIn("salvar_casos", processo.entrada)
        self.assertNotIn("ver_evidencia", processo.entrada)

    def test_a_pasta_temporaria_com_as_telas_some_no_fim(self):
        usada = {}

        def abrir(comando, **opcoes):
            usada["pasta"] = Path(opcoes["cwd"])
            usada["conteudo"] = sorted(p.relative_to(usada["pasta"]).as_posix() for p in usada["pasta"].rglob("*") if p.is_file())
            return ProcessoFalso(saida_ok())

        ia_local.gerar_roteiro(self.ciclo, self.base, Path("claude.exe"), abrir_processo=abrir)
        self.assertEqual(usada["conteudo"], ["t1/01.png", "t1/02.png", "t1/03.png"])
        self.assertFalse(usada["pasta"].exists())

    def test_a_pasta_temporaria_some_tambem_quando_da_erro(self):
        usada = {}

        def abrir(comando, **opcoes):
            usada["pasta"] = Path(opcoes["cwd"])
            return ProcessoFalso("", "quebrou")

        with self.assertRaises(ia_local.ErroIA):
            ia_local.gerar_roteiro(self.ciclo, self.base, Path("claude.exe"), abrir_processo=abrir)
        self.assertFalse(usada["pasta"].exists())

    def test_roteiro_invalido_da_ia_nao_e_gravado_e_a_mensagem_explica(self):
        ruim = {"casos": [{**CASO, "prioridade": "urgentíssima"}]}
        with self.assertRaises(ia_local.ErroIA) as erro:
            self.gerar(ProcessoFalso(saida_ok(ruim)))
        self.assertIn("não passou na validação", str(erro.exception))
        self.assertIn("casos[0].prioridade", str(erro.exception))
        self.assertIsNone(ciclos.ler_roteiro_mais_recente(self.ciclo.pasta))

    def test_roteiro_sem_casos_ou_com_formato_estranho(self):
        for ruim in ({"casos": []}, {"casos": "texto"}, {"outra": 1}, {"casos": [CASO], "ciclo_sugerido": "x"}):
            with self.subTest(ruim=ruim), self.assertRaises(ia_local.ErroIA):
                self.gerar(ProcessoFalso(saida_ok(ruim)))
        self.assertIsNone(ciclos.ler_roteiro_mais_recente(self.ciclo.pasta))

    def test_nao_logado_chega_como_erro_proprio_para_o_app_oferecer_o_login(self):
        saida = json.dumps({"type": "result", "is_error": True, "result": "Not logged in · Please run /login"})
        with self.assertRaises(ia_local.NaoLogado):
            self.gerar(ProcessoFalso(saida))

    def test_conteudo_hostil_na_resposta_nao_vira_arquivo_nem_comando(self):
        hostil = {"casos": [{**CASO, "titulo": "x\u202e\x00; rm -rf /", "passos": [{"acao": "../../../etc", "resultado_esperado": "ok"}],
                              "comando": "powershell -c calc"}], "ciclo_sugerido": {"escopo": ["a"] * 500}}
        with self.assertRaises(ia_local.ErroIA):  # escopo gigante é recusado inteiro
            self.gerar(ProcessoFalso(saida_ok(hostil)))
        hostil["ciclo_sugerido"] = {"objetivo": "ok"}
        self.gerar(ProcessoFalso(saida_ok(hostil)))
        texto = ciclos.ler_roteiro_mais_recente(self.ciclo.pasta).arquivo.read_text(encoding="utf-8")
        self.assertNotIn("powershell", texto)
        self.assertNotIn("\u202e", texto)

    def test_telas_que_nao_deu_para_preparar(self):
        for imagem in self.teste.glob("*.png"):
            imagem.write_bytes(b"lixo")
        with self.assertRaises(ia_local.ErroIA) as erro:
            self.gerar(ProcessoFalso(saida_ok()))
        self.assertIn("preparar as telas", str(erro.exception))



RELATORIO = {"status_sugerido": "Aprovado", "resumo": "Login funcionou.",
             "relatorio_markdown": "## Casos executados\n\n| ID | Resultado |\n|---|---|\n| CT-01 | Aprovado (Evidência 1) |\n"}


class GerarRelatorio(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = Path(self._tmp.name)
        self.base = self.raiz / "Evidencias"
        sessao = Sessao(self.raiz / "trab")
        for _ in range(3):
            sessao.adicionar(Image.new("RGB", (300, 200), "navy"), "tela")
        self.teste = sessao.finalizar("Cadastro de fornecedor", "QA", self.base)

    def gerar(self, processo, pasta=None, **extra):
        return ia_local.gerar_relatorio(pasta or self.teste, self.base, Path("claude.exe"),
                                        abrir_processo=FabricaDeProcessos(processo), **extra)

    def test_de_ponta_a_ponta_o_pdf_e_gravado_pelo_app_na_pasta_do_teste(self):
        dados = self.gerar(ProcessoFalso(saida_ok(RELATORIO)))
        pdf = self.teste / dados["pdf"]
        self.assertEqual(pdf.name, "Relatório de testes - Cadastro de fornecedor.pdf")
        self.assertTrue(pdf.read_bytes().startswith(b"%PDF"))
        self.assertEqual(dados["evidencias_anexadas"], 3)
        texto = (self.teste / dados["markdown"]).read_text(encoding="utf-8")
        self.assertTrue(texto.startswith("**Status sugerido pela IA:** Aprovado"))
        self.assertIn("CT-01", texto)

    def test_o_pedido_usa_o_esquema_do_relatorio_e_lista_as_telas_sem_ferramentas_da_extensao(self):
        processo = ProcessoFalso(saida_ok(RELATORIO))
        fabrica = FabricaDeProcessos(processo)
        ia_local.gerar_relatorio(self.teste, self.base, Path("claude.exe"), abrir_processo=fabrica)
        comando = fabrica.chamadas[0][0]
        self.assertIn("relatorio_markdown", comando[comando.index("--json-schema") + 1])
        self.assertNotIn('"casos"', comando[comando.index("--json-schema") + 1])
        self.assertIn("t1/01.png", processo.entrada)
        self.assertIn("Cadastro de fornecedor", processo.entrada)
        self.assertNotIn("salvar_relatorio_pdf", processo.entrada)
        self.assertNotIn("ver_evidencia", processo.entrada)

    def test_status_fora_da_lista_vira_inconclusivo_e_o_texto_da_ia_nao_vira_marcacao(self):
        ruim = {"status_sugerido": "Aprovado com louvor", "relatorio_markdown": "<script>alert(1)</script> **ok**"}
        dados = self.gerar(ProcessoFalso(saida_ok(ruim)))
        self.assertIn("Inconclusivo", (self.teste / dados["markdown"]).read_text(encoding="utf-8"))
        self.assertNotIn(b"<script>", (self.teste / dados["pdf"]).read_bytes())

    def test_resposta_sem_texto_do_relatorio_nao_grava_nada(self):
        for ruim in ({"status_sugerido": "Aprovado"}, {"status_sugerido": "Aprovado", "relatorio_markdown": "   "},
                     {"status_sugerido": "Aprovado", "relatorio_markdown": ["lista"]}):
            with self.subTest(ruim=ruim), self.assertRaises(ia_local.ErroIA):
                self.gerar(ProcessoFalso(saida_ok(ruim)))
        self.assertEqual(list(self.teste.glob("Relat*")), [])

    def test_nunca_sobrescreve_um_relatorio_que_ja_existe(self):
        antigo = self.teste / "Relatório de testes - Cadastro de fornecedor.pdf"
        antigo.write_bytes(b"%PDF antigo")
        dados = self.gerar(ProcessoFalso(saida_ok(RELATORIO)))
        self.assertEqual(dados["pdf"], "Relatório de testes - Cadastro de fornecedor (2).pdf")
        self.assertEqual(antigo.read_bytes(), b"%PDF antigo")

    def test_so_aceita_teste_direto_dentro_da_pasta_de_evidencias(self):
        fora = self.raiz / "Outra" / self.teste.name
        fora.parent.mkdir()
        (fora.parent / "x").mkdir()
        for pasta in (fora, self.base / "_em_andamento", self.base / "nao existe", self.base):
            with self.subTest(pasta=pasta), self.assertRaises(ia_local.ErroIA):
                self.gerar(ProcessoFalso(saida_ok(RELATORIO)), pasta=pasta)

    def test_a_pasta_temporaria_some_no_fim_dando_certo_ou_errado(self):
        usada = []

        def abrir_certo(comando, **opcoes):
            usada.append(Path(opcoes["cwd"]))
            return ProcessoFalso(saida_ok(RELATORIO))

        def abrir_errado(comando, **opcoes):
            usada.append(Path(opcoes["cwd"]))
            return ProcessoFalso("", "quebrou")

        ia_local.gerar_relatorio(self.teste, self.base, Path("claude.exe"), abrir_processo=abrir_certo)
        with self.assertRaises(ia_local.ErroIA):
            ia_local.gerar_relatorio(self.teste, self.base, Path("claude.exe"), abrir_processo=abrir_errado)
        self.assertEqual(len(usada), 2)
        self.assertFalse(any(p.exists() for p in usada))

    def test_nao_logado_e_cancelamento_chegam_como_erros_proprios(self):
        saida = json.dumps({"type": "result", "is_error": True, "result": "Not logged in · Please run /login"})
        with self.assertRaises(ia_local.NaoLogado):
            self.gerar(ProcessoFalso(saida))
        controle = ia_local.Controle()
        controle.cancelar()
        with self.assertRaises(ia_local.Cancelado):
            self.gerar(ProcessoFalso(saida_ok(RELATORIO)), controle=controle)
        self.assertEqual(list(self.teste.glob("Relat*")), [])

    def test_teste_sem_imagens_aproveitaveis(self):
        for imagem in self.teste.glob("*.png"):
            imagem.write_bytes(b"lixo")
        with self.assertRaises(ia_local.ErroIA) as erro:
            self.gerar(ProcessoFalso(saida_ok(RELATORIO)))
        self.assertIn("preparar as telas", str(erro.exception))


if __name__ == "__main__":
    unittest.main()
