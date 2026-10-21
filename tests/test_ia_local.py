"""Chamada do Claude Code pelo app (sem chamar o Claude de verdade): comando, pasta de trabalho, resposta e falhas."""
import io
import json
import os
import re
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


class TelasNoPedido(unittest.TestCase):
    """As telas vão reduzidas e na memória, dentro do próprio pedido: nada é copiado para o disco."""

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

    def test_telas_reduzidas_na_memoria_e_nenhum_outro_arquivo_do_teste(self):
        pasta = self.criar("Login", 2, (4000, 3000))
        (pasta / "Relatório de testes - Login.pdf").write_bytes(b"%PDF segredo")
        (pasta / "Relatório de testes - Login.md").write_text("relatório antigo", encoding="utf-8")
        telas = ia_local.preparar_telas(self.criar_testes(pasta))
        self.assertEqual([(t.numero, t.formato, t.rotulo) for t in telas],
                         [(1, "png", "Evidência 1:"), (2, "png", "Evidência 2:")])
        self.assertTrue(all(t.teste == pasta.name for t in telas))
        with Image.open(io.BytesIO(telas[0].dados)) as img:
            self.assertEqual(max(img.size), ia_local.LADO_MAXIMO)
        self.assertNotIn(b"segredo", b"".join(t.dados for t in telas))

    def test_tela_pesada_vai_como_jpeg_leve(self):
        from tests.test_imagens import tela_com_foto
        sessao = Sessao(self.raiz / "trab_pesada")
        sessao.adicionar(tela_com_foto(), "tela")
        sessao.adicionar(Image.new("RGB", (800, 600), "navy"), "tela")
        pasta = sessao.finalizar("Login com foto", "QA", self.base)
        telas = ia_local.preparar_telas(self.criar_testes(pasta))
        self.assertEqual([(t.numero, t.formato) for t in telas], [(1, "jpeg"), (2, "png")])
        self.assertLessEqual(len(telas[0].dados), ia_local.LIMITE_IMAGEM_BYTES)
        with Image.open(io.BytesIO(telas[0].dados)) as img:
            self.assertEqual(img.format, "JPEG")

    def test_telas_pequenas_nao_sao_ampliadas(self):
        pasta = self.criar("Login", 1, (300, 200))
        with Image.open(io.BytesIO(ia_local.preparar_telas(self.criar_testes(pasta))[0].dados)) as img:
            self.assertEqual(img.size, (300, 200))

    def test_limite_de_imagens_com_telas_espacadas_e_numero_original_preservado(self):
        pasta = self.criar("Login", 12)
        numeros = [t.numero for t in ia_local.preparar_telas(self.criar_testes(pasta), max_imagens=4)]
        self.assertEqual(len(numeros), 4)
        self.assertEqual((numeros[0], numeros[-1]), (1, 12))  # primeira e última sempre entram

    def test_varios_testes_dividem_o_limite_e_o_rotulo_diz_de_qual_teste_e_a_tela(self):
        pastas = [self.criar(f"Teste {i}", 10) for i in range(1, 5)]
        telas = ia_local.preparar_telas(self.criar_testes(*pastas), max_imagens=8)
        resumo = ia_local.resumo_das_telas(telas)
        self.assertEqual(list(resumo), [p.name for p in pastas])
        self.assertTrue(all(len(numeros) == 3 for numeros in resumo.values()))  # no mínimo 3 por teste
        self.assertEqual(telas[0].rotulo, f'Teste "{pastas[0].name}", evidência 1:')

    def test_pngs_invalidos_sao_pulados(self):
        pasta = self.criar("Login", 3)
        (pasta / "02_tela.png").write_bytes(b"BM" + b"\x00" * 100)  # outro formato com nome de .png
        self.assertEqual([t.numero for t in ia_local.preparar_telas(self.criar_testes(pasta))], [1, 3])

    def test_teste_sem_nenhuma_tela_aproveitavel_nao_entra(self):
        pasta = self.criar("Login", 1)
        (pasta / "01_tela.png").write_bytes(b"lixo")
        self.assertEqual(ia_local.preparar_telas(self.criar_testes(pasta)), [])

    def test_a_soma_das_telas_respeita_o_limite_do_pedido(self):
        from tests.test_imagens import tela_com_foto
        sessao = Sessao(self.raiz / "trab_soma")
        for _ in range(4):
            sessao.adicionar(tela_com_foto((400, 300)), "tela")
        pasta = sessao.finalizar("Quatro fotos", "QA", self.base)
        with mock.patch.object(ia_local, "LIMITE_TOTAL_BYTES", 80_000):
            telas = ia_local.preparar_telas(self.criar_testes(pasta))
        self.assertEqual(len(telas), 4)
        self.assertLessEqual(sum(len(t.dados) for t in telas), 80_000)

    def test_a_mensagem_leva_o_texto_e_cada_tela_com_o_seu_rotulo(self):
        telas = [ia_local.Tela("Teste A", 1, b"\x89PNG-falso", "png", "Evidência 1:"),
                 ia_local.Tela("Teste A", 3, b"\xff\xd8jpeg-falso", "jpeg", "Evidência 3:")]
        linha = ia_local.montar_mensagem("PEDIDO", telas)
        self.assertTrue(linha.endswith("\n") and linha.count("\n") == 1)  # uma linha JSON só
        conteudo = json.loads(linha)["message"]["content"]
        self.assertEqual([c["type"] for c in conteudo], ["text", "text", "image", "text", "image"])
        self.assertEqual((conteudo[0]["text"], conteudo[1]["text"], conteudo[3]["text"]), ("PEDIDO", "Evidência 1:", "Evidência 3:"))
        self.assertEqual((conteudo[2]["source"]["media_type"], conteudo[4]["source"]["media_type"]), ("image/png", "image/jpeg"))
        import base64
        self.assertEqual(base64.b64decode(conteudo[4]["source"]["data"]), b"\xff\xd8jpeg-falso")

    def test_espacadas(self):
        self.assertEqual(ia_local._espacadas([1, 2, 3], 5), [1, 2, 3])
        self.assertEqual(ia_local._espacadas(list(range(10)), 1), [0])
        escolhidas = ia_local._espacadas(list(range(100)), 5)
        self.assertEqual((escolhidas[0], escolhidas[-1], len(escolhidas)), (0, 99, 5))
        self.assertEqual(escolhidas, sorted(set(escolhidas)))


class Comando(unittest.TestCase):
    def test_modo_restrito_sem_nenhuma_ferramenta_e_sem_permissao_para_nada(self):
        c = ia_local.montar_comando(Path("C:/x/claude.exe"))
        pares = {c[i]: c[i + 1] for i in range(len(c) - 1)}
        self.assertEqual(c[0], "C:\\x\\claude.exe".replace("\\", os.sep) if os.sep == "/" else str(Path("C:/x/claude.exe")))
        self.assertIn("-p", c)
        self.assertEqual(pares["--tools"], "")  # nenhuma ferramenta: as telas vão dentro do pedido
        self.assertNotIn("--allowedTools", c)
        self.assertEqual((pares["--permission-mode"], pares["--permission-prompts"]), ("dontAsk", "none"))
        for bandeira in ("--restricted", "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"):
            self.assertIn(bandeira, c)
        self.assertEqual((pares["--input-format"], pares["--output-format"]), ("stream-json", "stream-json"))
        self.assertIn("--verbose", c)  # o stream-json exige
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

    def test_saida_em_eventos_stream_json_usa_o_evento_result(self):
        eventos = [{"type": "system", "subtype": "init", "tools": []},
                   {"type": "assistant", "message": {"content": [{"type": "text", "text": "pensando"}]}},
                   json.loads(saida_ok({**ROTEIRO, "observacoes": ["do result"]}))]
        saida = "\n".join(json.dumps(e) for e in eventos) + "\n"
        self.assertEqual(ia_local.extrair_resposta(saida)["observacoes"], ["do result"])

    def test_nao_logado_em_eventos_stream_json(self):
        eventos = [{"type": "assistant", "error": "authentication_failed", "message": {"content": [{"type": "text", "text": "Not logged in"}]}},
                   {"type": "result", "is_error": True, "result": "Not logged in · Please run /login"}]
        with self.assertRaises(ia_local.NaoLogado):
            ia_local.extrair_resposta("\n".join(json.dumps(e) for e in eventos))

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

    def test_o_pedido_leva_as_telas_dentro_dele_e_nao_usa_ferramentas(self):
        processo = ProcessoFalso(saida_ok())
        self.gerar(processo)
        conteudo = json.loads(processo.entrada)["message"]["content"]
        texto = conteudo[0]["text"]
        self.assertEqual(sum(1 for c in conteudo if c["type"] == "image"), 3)
        self.assertIn(f'Teste "{self.teste.name}": evidências 1, 2, 3', texto)
        self.assertIn("Responda SOMENTE com um objeto JSON", texto)
        for proibido in ("salvar_casos", "ver_evidencia", "Read", "t1/01.png"):
            self.assertNotIn(proibido, texto)

    def test_o_claude_roda_numa_pasta_vazia_que_some_no_fim_e_nenhuma_tela_vai_para_o_disco(self):
        usada = {}

        def abrir(comando, **opcoes):
            usada["pasta"] = Path(opcoes["cwd"])
            usada["conteudo"] = sorted(p.name for p in usada["pasta"].rglob("*"))
            return ProcessoFalso(saida_ok())

        ia_local.gerar_roteiro(self.ciclo, self.base, Path("claude.exe"), abrir_processo=abrir)
        self.assertEqual(usada["conteudo"], [])
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
        conteudo = json.loads(processo.entrada)["message"]["content"]
        self.assertEqual([c["text"] for c in conteudo if c["type"] == "text"][1:], ["Evidência 1:", "Evidência 2:", "Evidência 3:"])
        self.assertEqual(sum(1 for c in conteudo if c["type"] == "image"), 3)
        self.assertIn("Cadastro de fornecedor", conteudo[0]["text"])
        for proibido in ("salvar_relatorio_pdf", "ver_evidencia", "Read"):
            self.assertNotIn(proibido, conteudo[0]["text"])

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



class FabricaEmSequencia:
    """Substitui subprocess.Popen: cada chamada devolve o próximo processo falso (parte 1, parte 2... e a junção)."""

    def __init__(self, *processos):
        self.processos, self.chamadas = list(processos), []

    def __call__(self, comando, **opcoes):
        self.chamadas.append((comando, opcoes))
        return self.processos[len(self.chamadas) - 1]


def relato(status, texto):
    return ProcessoFalso(saida_ok({"status_sugerido": status, "resumo": f"resumo de {texto}", "relatorio_markdown": texto}))


def conteudo_do_pedido(processo):
    return json.loads(processo.entrada)["message"]["content"]


def telas_do_pedido(processo):
    """Os números das evidências que foram dentro do pedido (os rótulos 'Evidência N:' que antecedem cada imagem)."""
    return [int(re.search(r"\d+", c["text"]).group()) for c in conteudo_do_pedido(processo)
            if c["type"] == "text" and c["text"].startswith("Evidência")]


class DividirEmPartes(unittest.TestCase):
    def test_o_teste_que_cabe_num_pedido_fica_numa_parte_so(self):
        for quantas in (1, 3, ia_local.MAX_IMAGENS):
            with self.subTest(quantas=quantas):
                self.assertEqual(len(ia_local.dividir_em_partes(list(range(quantas)))), 1)
        self.assertEqual(ia_local.dividir_em_partes([]), [])

    def test_o_que_passa_do_limite_vira_partes_do_mesmo_tamanho(self):
        tamanhos = {n: [len(p) for p in ia_local.dividir_em_partes(list(range(n)))] for n in (41, 44, 80, 81, 82, 200)}
        self.assertEqual(tamanhos, {41: [21, 20], 44: [22, 22], 80: [40, 40], 81: [27, 27, 27], 82: [28, 28, 26],
                                    200: [40] * 5})

    def test_nenhuma_evidencia_fica_de_fora_nem_repete_e_a_ordem_se_mantem(self):
        for n in range(1, 130):
            partes = ia_local.dividir_em_partes(list(range(n)))
            self.assertEqual([x for p in partes for x in p], list(range(n)), n)
            self.assertTrue(all(len(p) <= ia_local.MAX_IMAGENS for p in partes), n)

    def test_o_limite_pode_ser_trocado(self):
        with mock.patch.object(ia_local, "MAX_IMAGENS", 4):
            self.assertEqual([len(p) for p in ia_local.dividir_em_partes(list(range(10)))], [4, 4, 2])


class GerarRelatorioEmPartes(unittest.TestCase):
    """Teste com mais telas do que cabem num pedido: nenhuma fica de fora (partes, e uma chamada que junta)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = Path(self._tmp.name)
        self.base = self.raiz / "Evidencias"
        sessao = Sessao(self.raiz / "trab")
        for _ in range(10):
            sessao.adicionar(Image.new("RGB", (300, 200), "navy"), "tela")
        self.teste = sessao.finalizar("Aprovadores", "QA", self.base)
        limite = mock.patch.object(ia_local, "MAX_IMAGENS", 4)  # 10 telas: partes de 4, 4 e 2
        limite.start()
        self.addCleanup(limite.stop)

    def gerar(self, fabrica, **extra):
        return ia_local.gerar_relatorio(self.teste, self.base, Path("claude.exe"), abrir_processo=fabrica, **extra)

    def partes(self):
        return [relato("Aprovado", "TEXTO-A"), relato("Inconclusivo", "TEXTO-B"), relato("Aprovado", "TEXTO-C")]

    def test_todas_as_telas_vao_uma_so_vez_e_com_o_numero_real(self):
        partes, juncao = self.partes(), relato("Inconclusivo", "RELATORIO-UNICO")
        fabrica = FabricaEmSequencia(*partes, juncao)
        self.gerar(fabrica)
        self.assertEqual([telas_do_pedido(p) for p in partes], [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10]])
        self.assertEqual(len(fabrica.chamadas), 4)
        self.assertIn("PARTE 2 de 3", conteudo_do_pedido(partes[1])[0]["text"])

    def test_a_juncao_recebe_so_texto_com_as_tres_partes(self):
        partes, juncao = self.partes(), relato("Inconclusivo", "RELATORIO-UNICO")
        self.gerar(FabricaEmSequencia(*partes, juncao))
        conteudo = conteudo_do_pedido(juncao)
        self.assertEqual([c["type"] for c in conteudo], ["text"])  # nenhuma imagem na junção
        for esperado in ("TEXTO-A", "TEXTO-B", "TEXTO-C", "evidências 1 a 4", "evidências 5 a 8", "evidências 9 a 10"):
            self.assertIn(esperado, conteudo[0]["text"])

    def test_o_relatorio_gravado_e_o_da_juncao_com_as_dez_imagens_anexadas(self):
        dados = self.gerar(FabricaEmSequencia(*self.partes(), relato("Inconclusivo", "RELATORIO-UNICO")))
        texto = (self.teste / dados["markdown"]).read_text(encoding="utf-8")
        self.assertTrue(texto.startswith("**Status sugerido pela IA:** Inconclusivo"))
        self.assertIn("RELATORIO-UNICO", texto)
        self.assertNotIn("TEXTO-A", texto)
        self.assertEqual(dados["evidencias_anexadas"], 10)
        self.assertTrue((self.teste / dados["pdf"]).read_bytes().startswith(b"%PDF"))

    def test_todas_as_chamadas_sao_restritas_e_sem_ferramentas(self):
        fabrica = FabricaEmSequencia(*self.partes(), relato("Aprovado", "UNICO"))
        self.gerar(fabrica)
        for comando, opcoes in fabrica.chamadas:
            self.assertEqual(comando[comando.index("--tools") + 1], "")
            self.assertIn("relatorio_markdown", comando[comando.index("--json-schema") + 1])
            self.assertIn("--restricted", comando)
            self.assertFalse(Path(opcoes["cwd"]).exists())  # a pasta temporária de cada chamada some no fim

    def test_o_andamento_diz_a_parte_e_depois_que_esta_juntando(self):
        etapas = []
        self.gerar(FabricaEmSequencia(*self.partes(), relato("Aprovado", "UNICO")), progresso=etapas.append)
        self.assertEqual(etapas, ["parte 1 de 3", "parte 2 de 3", "parte 3 de 3", "juntando as partes"])

    def test_se_cabe_num_pedido_nao_ha_partes_nem_juncao_nem_andamento(self):
        etapas = []
        with mock.patch.object(ia_local, "MAX_IMAGENS", 10):
            processo = relato("Aprovado", "TEXTO-UNICO")
            fabrica = FabricaEmSequencia(processo)
            dados = self.gerar(fabrica, progresso=etapas.append)
        self.assertEqual((len(fabrica.chamadas), etapas), (1, []))
        self.assertEqual(telas_do_pedido(processo), list(range(1, 11)))
        self.assertNotIn("PARTE", conteudo_do_pedido(processo)[0]["text"])
        self.assertIn("TEXTO-UNICO", (self.teste / dados["markdown"]).read_text(encoding="utf-8"))

    def test_tela_ilegivel_numa_parte_continua_marcada_so_nela(self):
        (self.teste / "02_tela.png").write_bytes(b"lixo")
        partes = self.partes()
        with mock.patch.object(ia_local.gravacao, "gravar_relatorio_pdf", return_value={}):  # aqui só importa o pedido
            self.gerar(FabricaEmSequencia(*partes, relato("Aprovado", "UNICO")))
        self.assertEqual([telas_do_pedido(p) for p in partes], [[1, 3, 4], [5, 6, 7, 8], [9, 10]])
        self.assertIn("2. Tela inteira", conteudo_do_pedido(partes[0])[0]["text"])
        self.assertIn("→ NÃO enviada", conteudo_do_pedido(partes[0])[0]["text"])
        self.assertNotIn("NÃO enviada", conteudo_do_pedido(partes[1])[0]["text"])

    def test_se_o_claude_nao_junta_o_app_empilha_as_partes_e_avisa_no_documento(self):
        for juncao in (ProcessoFalso("", "quebrou"),
                       relato("Aprovado", "   "), ProcessoFalso("não é json")):
            with self.subTest(juncao=juncao.stdout[:12]):
                partes = [relato("Aprovado", "TEXTO-A"), relato("Reprovado", "TEXTO-B"), relato("Inconclusivo", "TEXTO-C")]
                with self.assertLogs("capturador.ia_local", level="WARNING"):
                    dados = self.gerar(FabricaEmSequencia(*partes, juncao))
                texto = (self.teste / dados["markdown"]).read_text(encoding="utf-8")
                self.assertTrue(texto.startswith("**Status sugerido pela IA:** Reprovado"))  # o pior das partes
                self.assertIn("**Atenção:** o Claude não conseguiu reunir as 3 partes", texto)
                for esperado in ("# Parte 1 de 3: evidências 1 a 4", "# Parte 3 de 3: evidências 9 a 10",
                                 "TEXTO-A", "TEXTO-B", "TEXTO-C"):
                    self.assertIn(esperado, texto)
                self.assertEqual(dados["evidencias_anexadas"], 10)

    def test_o_status_do_teste_na_falha_da_juncao_e_inconclusivo_sem_reprovada(self):
        partes = [relato("Aprovado", "A"), relato("Aprovado", "B"), relato("Inconclusivo", "C")]
        with self.assertLogs("capturador.ia_local", level="WARNING"):
            dados = self.gerar(FabricaEmSequencia(*partes, ProcessoFalso("", "quebrou")))
        self.assertTrue((self.teste / dados["markdown"]).read_text(encoding="utf-8").startswith(
            "**Status sugerido pela IA:** Inconclusivo"))

    def test_sem_login_na_juncao_nao_grava_nada(self):
        saida = json.dumps({"type": "result", "is_error": True, "result": "Not logged in · Please run /login"})
        with self.assertRaises(ia_local.NaoLogado):
            self.gerar(FabricaEmSequencia(*self.partes(), ProcessoFalso(saida)))
        self.assertEqual(list(self.teste.glob("Relat*")), [])

    def test_cancelar_entre_as_partes_para_na_hora_e_nao_grava_nada(self):
        controle = ia_local.Controle()
        partes = self.partes()

        class Cancela(FabricaEmSequencia):
            def __call__(self, comando, **opcoes):
                processo = super().__call__(comando, **opcoes)
                controle.cancelar()  # o usuário cancela durante a primeira parte
                return processo

        fabrica = Cancela(*partes, relato("Aprovado", "UNICO"))
        with self.assertRaises(ia_local.Cancelado):
            self.gerar(fabrica, controle=controle)
        self.assertEqual(len(fabrica.chamadas), 1)
        self.assertEqual(list(self.teste.glob("Relat*")), [])

    def test_falha_numa_parte_derruba_o_relatorio_sem_gravar_pela_metade(self):
        fabrica = FabricaEmSequencia(relato("Aprovado", "TEXTO-A"), ProcessoFalso("", "quebrou"), relato("Aprovado", "C"))
        with self.assertRaises(ia_local.ErroIA):
            self.gerar(fabrica)
        self.assertEqual(len(fabrica.chamadas), 2)
        self.assertEqual(list(self.teste.glob("Relat*")), [])

    def test_parte_sem_nenhuma_tela_legivel_diz_quais_evidencias(self):
        for numero in (5, 6, 7, 8):
            (self.teste / f"{numero:02d}_tela.png").write_bytes(b"lixo")
        with self.assertRaises(ia_local.ErroIA) as erro:
            self.gerar(FabricaEmSequencia(relato("Aprovado", "A"), relato("Aprovado", "B"), relato("Aprovado", "C"),
                                          relato("Aprovado", "UNICO")))
        self.assertIn("evidências 5 a 8", str(erro.exception))
        self.assertEqual(list(self.teste.glob("Relat*")), [])


class EsperarOLogin(unittest.TestCase):
    """Depois do login o app continua sozinho: precisa saber quando a janela do login fechou e em que conta ficou."""

    CONTA = {"loggedIn": True, "email": "ana@empresa.com.br", "orgName": "Empresa"}

    class Processo:
        def __init__(self, termina_em=0):
            self.consultas, self.termina_em = 0, termina_em

        def poll(self):
            self.consultas += 1
            return 0 if self.consultas > self.termina_em else None

    def espera(self, processo, verificar, tempo_limite=600):
        relogio = [0.0]

        def dormir(segundos):
            relogio[0] += segundos

        return ia_local.esperar_login(processo, Path("claude.exe"), tempo_limite, verificar, dormir, lambda: relogio[0])

    def test_situacao_traz_a_conta_quando_ha_login_e_vazio_quando_nao(self):
        def com_login(*a, **k):
            return mock.Mock(stdout=json.dumps(self.CONTA))

        def sem_login(*a, **k):
            return mock.Mock(stdout=json.dumps({"loggedIn": False, "authMethod": "none"}))

        def quebrado(*a, **k):
            raise subprocess.TimeoutExpired("claude", 30)

        self.assertEqual(ia_local.situacao_login(Path("c.exe"), com_login)["email"], "ana@empresa.com.br")
        self.assertEqual(ia_local.situacao_login(Path("c.exe"), sem_login), {})
        self.assertEqual(ia_local.situacao_login(Path("c.exe"), quebrado), {})
        self.assertTrue(ia_local.esta_logado(Path("c.exe"), com_login))
        self.assertFalse(ia_local.esta_logado(Path("c.exe"), sem_login))

    def test_abrir_login_devolve_o_processo_para_o_app_esperar(self):
        processo = object()
        self.assertIs(ia_local.abrir_login(Path("claude.exe"), lambda *a, **k: processo), processo)

    def test_devolve_a_conta_assim_que_a_janela_do_login_fecha(self):
        consultas = []
        processo = self.Processo(termina_em=3)
        conta = self.espera(processo, lambda exe: consultas.append(exe) or self.CONTA)
        self.assertEqual(conta["email"], "ana@empresa.com.br")
        self.assertEqual(len(consultas), 1)  # não consulta a conta enquanto a janela do login está aberta

    def test_a_conta_pode_demorar_um_instante_a_aparecer(self):
        respostas = iter([{}, {}, self.CONTA])
        conta = self.espera(self.Processo(), lambda exe: next(respostas))
        self.assertEqual(conta["orgName"], "Empresa")

    def test_login_fechado_sem_conta_devolve_vazio_depois_de_tres_tentativas(self):
        consultas = []
        conta = self.espera(self.Processo(), lambda exe: consultas.append(1) or {})
        self.assertEqual((conta, len(consultas)), ({}, 3))

    def test_desiste_depois_do_tempo_limite_se_a_janela_nunca_fecha(self):
        consultas = []
        conta = self.espera(self.Processo(termina_em=10**9), lambda exe: consultas.append(1) or self.CONTA, tempo_limite=30)
        self.assertEqual((conta, consultas), ({}, []))


if __name__ == "__main__":
    unittest.main()
