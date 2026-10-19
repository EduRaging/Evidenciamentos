"""Ciclos de teste: parâmetros, roteiro de casos da IA, gravação segura e leitura que não confia em nada."""
import copy
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from capturador import ciclos


def caso(**mudancas) -> dict:
    base = {
        "id": "CT-01", "titulo": "Login com credenciais válidas", "objetivo": "Confirmar o acesso ao painel",
        "tecnica": "Partição de equivalência", "prioridade": "Alta", "tipo": "Funcional",
        "pre_condicoes": ["Usuário de teste ativo"], "dados_de_teste": ["usuario.teste / senha fictícia"],
        "passos": [{"acao": "Abrir a tela de login", "resultado_esperado": "Campos usuário e senha visíveis"},
                   {"acao": "Entrar com os dados válidos", "resultado_esperado": "O painel inicial é exibido"}],
        "pos_condicoes": ["Sessão iniciada"], "rastreio": ["Login"],
        "evidencias_base": [{"teste": "2026-10-09_1400 - Login", "numero": 1}], "a_confirmar": False,
    }
    base.update(mudancas)
    return base


PARAMETROS = {"nome": "Rodada 1 - Cadastro de fornecedor", "objetivo": "Validar o cadastro de fornecedor", "tipo": "Funcional",
              "sistema": "ERP", "versao_sistema": "2.3.1", "ambiente": "Homologação",
              "escopo": ["Cadastro", "Edição"], "testes_base": ["2026-10-09_1400 - Login"]}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name) / "Evidencias"
        self.base.mkdir()


class Parametros(Base):
    def test_cria_a_pasta_do_ciclo_com_o_json(self):
        ciclo = ciclos.criar_ciclo(self.base, PARAMETROS, agora=datetime(2026, 10, 19, 14, 5))
        self.assertEqual(ciclo.pasta, self.base / "_ciclos" / "2026-10-19_1405 - Rodada 1 - Cadastro de fornecedor")
        dados = json.loads((ciclo.pasta / "ciclo.json").read_text(encoding="utf-8"))
        self.assertEqual((dados["versao"], dados["nome"], dados["tipo"]), (1, PARAMETROS["nome"], "Funcional"))
        self.assertEqual(ciclos.ler_ciclo(ciclo.pasta).objetivo, "Validar o cadastro de fornecedor")

    def test_so_o_nome_e_obrigatorio_e_o_ciclo_precisa_de_testes_de_referencia_ou_objetivo(self):
        with self.assertRaises(ValueError):
            ciclos.validar_parametros({**PARAMETROS, "nome": "   "})
        # só os testes de referência (as telas capturadas), sem objetivo: é o caso automático
        so_testes = ciclos.validar_parametros({"nome": "Ciclo", "testes_base": ["2026-10-09_1400 - Login"]})
        self.assertEqual((so_testes["objetivo"], so_testes["testes_base"]), ("", ["2026-10-09_1400 - Login"]))
        # só o objetivo, sem testes
        self.assertEqual(ciclos.validar_parametros({"nome": "Ciclo", "objetivo": "Validar"})["testes_base"], [])
        with self.assertRaises(ValueError):  # nenhum dos dois: a IA não teria de onde partir
            ciclos.validar_parametros({"nome": "Ciclo"})

    def test_criterios_ficam_automaticos_quando_nao_informados_e_proprios_quando_informados(self):
        ciclo = ciclos.criar_ciclo(self.base, PARAMETROS)
        self.assertIsNone(ciclo.criterios_entrada)  # automático: a IA propõe, senão vale o padrão do CTFL
        self.assertIsNone(ciclo.criterios_saida)
        proprio = ciclos.validar_parametros({**PARAMETROS, "criterios_entrada": ["Só este"], "criterios_saida": []})
        self.assertEqual((proprio["criterios_entrada"], proprio["criterios_saida"]), (["Só este"], []))

    def test_tipo_de_rodada_aceita_sem_acento_e_recusa_o_que_nao_existe(self):
        self.assertEqual(ciclos.validar_parametros({**PARAMETROS, "tipo": "regressao"})["tipo"], "Regressão")
        self.assertEqual(ciclos.validar_parametros({**PARAMETROS, "tipo": "confirmacao de correcao"})["tipo"],
                         "Confirmação de correção")
        self.assertEqual(ciclos.validar_parametros({**PARAMETROS, "tipo": ""})["tipo"], "Funcional")
        with self.assertRaises(ValueError):
            ciclos.validar_parametros({**PARAMETROS, "tipo": "carga"})

    def test_datas_validas_e_na_ordem(self):
        self.assertEqual(ciclos.validar_parametros({**PARAMETROS, "inicio": "2026-10-01", "fim": "2026-10-15"})["fim"],
                         "2026-10-15")
        for ruim in ({"inicio": "01/10/2026"}, {"inicio": "2026-10-15", "fim": "2026-10-01"}, {"fim": "2026-13-40"}):
            with self.subTest(ruim=ruim), self.assertRaises(ValueError):
                ciclos.validar_parametros({**PARAMETROS, **ruim})

    def test_textos_viram_linha_simples_sem_controle_nem_direcao(self):
        limpos = ciclos.validar_parametros({**PARAMETROS, "nome": "Rodada\n\u202ex\x00 um", "objetivo": "a\r\nb\tc",
                                            "observacoes": "x" * 5000})
        self.assertEqual((limpos["nome"], limpos["objetivo"]), ("Rodada x um", "a b c"))
        self.assertEqual(len(limpos["observacoes"]), 500)

    def test_testes_de_referencia_so_aceitam_nome_de_pasta(self):
        for ruim in (["../fora"], ["a/b"], ["C:\\x"], [".."], [{"x": 1}]):
            with self.subTest(ruim=ruim), self.assertRaises(ValueError):
                ciclos.validar_parametros({**PARAMETROS, "testes_base": ruim})
        self.assertEqual(ciclos.validar_parametros({**PARAMETROS, "testes_base": ["a", "a", "b"]})["testes_base"], ["a", "b"])

    def test_listas_com_itens_demais_ou_de_tipo_errado_sao_recusadas(self):
        with self.assertRaises(ValueError):
            ciclos.validar_parametros({**PARAMETROS, "escopo": ["x"] * (ciclos.MAX_ESCOPO + 1)})
        with self.assertRaises(ValueError):
            ciclos.validar_parametros({**PARAMETROS, "criterios_saida": [["aninhada"]]})

    def test_dois_ciclos_com_o_mesmo_nome_no_mesmo_minuto_nao_se_sobrescrevem(self):
        agora = datetime(2026, 10, 19, 14, 5)
        a = ciclos.criar_ciclo(self.base, PARAMETROS, agora=agora)
        b = ciclos.criar_ciclo(self.base, PARAMETROS, agora=agora)
        self.assertNotEqual(a.pasta, b.pasta)
        self.assertTrue(b.pasta.name.endswith("(2)"))

    def test_lista_do_mais_recente_para_o_mais_antigo_e_ignora_pastas_invalidas(self):
        ciclos.criar_ciclo(self.base, {**PARAMETROS, "nome": "Antigo"}, agora=datetime(2026, 10, 1, 9, 0))
        ciclos.criar_ciclo(self.base, {**PARAMETROS, "nome": "Novo"}, agora=datetime(2026, 10, 19, 9, 0))
        (self.base / "_ciclos" / "lixo").mkdir()
        (self.base / "_ciclos" / "ruim").mkdir()
        (self.base / "_ciclos" / "ruim" / "ciclo.json").write_text("{não é json", encoding="utf-8")
        self.assertEqual([c.nome for c in ciclos.listar_ciclos(self.base)], ["Novo", "Antigo"])
        self.assertEqual(ciclos.listar_ciclos(self.base / "inexistente"), [])

    def test_ciclo_json_adulterado_e_recusado_na_leitura(self):
        ciclo = ciclos.criar_ciclo(self.base, PARAMETROS)
        arquivo = ciclo.pasta / "ciclo.json"
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        for adulteracao in ({"nome": ""}, {"tipo": "carga"}, {"testes_base": ["../x"]}, {"inicio": "ontem"}):
            with self.subTest(adulteracao=adulteracao):
                arquivo.write_text(json.dumps({**dados, **adulteracao}), encoding="utf-8")
                with self.assertRaises(ValueError):
                    ciclos.ler_ciclo(ciclo.pasta)
        arquivo.write_text("[]", encoding="utf-8")
        with self.assertRaises(ValueError):
            ciclos.ler_ciclo(ciclo.pasta)
        arquivo.write_text(json.dumps(dados) + " " * 3_000_000, encoding="utf-8")
        with self.assertRaises(ValueError):
            ciclos.ler_ciclo(ciclo.pasta)


class ResolverCiclo(Base):
    def test_resolve_so_pelo_nome_dentro_de_ciclos(self):
        ciclo = ciclos.criar_ciclo(self.base, PARAMETROS)
        self.assertEqual(ciclos.resolver_ciclo(self.base, ciclo.pasta.name).resolve(), ciclo.pasta.resolve())

    def test_recusa_caminhos_e_nomes_de_trabalho(self):
        ciclos.criar_ciclo(self.base, PARAMETROS)
        for nome in ("", "..", ".", "a/b", "..\\x", "C:\\Windows", "_oculta", ".oculta", "x\x00y", "nao existe"):
            with self.subTest(nome=nome), self.assertRaises(ValueError):
                ciclos.resolver_ciclo(self.base, nome)

    def test_juncao_para_fora_nao_e_um_ciclo(self):
        ciclos.criar_ciclo(self.base, PARAMETROS)
        fora = Path(self._tmp.name) / "Fora"
        fora.mkdir()
        (fora / "ciclo.json").write_text("{}", encoding="utf-8")
        juncao = self.base / "_ciclos" / "2026-10-19_1000 - Atalho"
        resultado = subprocess.run(["cmd", "/c", "mklink", "/J", str(juncao), str(fora)], capture_output=True, text=True)
        if resultado.returncode != 0 or not os.path.isjunction(juncao):
            self.skipTest("não foi possível criar a junção neste ambiente")
        with self.assertRaises(ValueError):
            ciclos.resolver_ciclo(self.base, juncao.name)
        self.assertEqual([c.nome for c in ciclos.listar_ciclos(self.base)], [PARAMETROS["nome"]])


class ValidarCasos(unittest.TestCase):
    def test_caso_completo_e_aceito_e_normalizado(self):
        (c,) = ciclos.validar_casos([caso(id="ct-01", prioridade="media")])
        self.assertEqual((c.id, c.prioridade), ("CT-01", "Média"))
        self.assertEqual(len(c.passos), 2)
        self.assertEqual(c.evidencias_base, [{"teste": "2026-10-09_1400 - Login", "numero": 1}])

    def test_campos_opcionais_podem_faltar(self):
        minimo = {"id": "CT-02", "titulo": "T", "objetivo": "O", "tecnica": "Checklist", "prioridade": "Baixa",
                  "passos": [{"acao": "a", "resultado_esperado": "r"}]}
        (c,) = ciclos.validar_casos([minimo])
        self.assertEqual((c.tipo, c.pre_condicoes, c.a_confirmar, c.evidencias_base), ("Funcional", [], False, []))

    def test_lista_vazia_ou_grande_demais(self):
        for ruim in ([], None, "texto", {"id": "CT-01"}):
            with self.subTest(ruim=ruim), self.assertRaises(ValueError):
                ciclos.validar_casos(ruim)
        muitos = [caso(id=f"CT-{i:02d}") for i in range(1, ciclos.MAX_CASOS + 2)]
        with self.assertRaises(ValueError) as erro:
            ciclos.validar_casos(muitos)
        self.assertIn(str(ciclos.MAX_CASOS), str(erro.exception))
        self.assertEqual(len(ciclos.validar_casos(muitos[:ciclos.MAX_CASOS])), ciclos.MAX_CASOS)

    def test_ids_repetidos_ou_mal_formados(self):
        with self.assertRaises(ValueError) as erro:
            ciclos.validar_casos([caso(), caso()])
        self.assertIn("repetido", str(erro.exception))
        for ruim in ("", "01", "CT01", "CT-", "CT-12345", "../x", "CT-01; DROP", "ABCDEFG-1"):
            with self.subTest(id=ruim), self.assertRaises(ValueError):
                ciclos.validar_casos([caso(id=ruim)])

    def test_campos_obrigatorios(self):
        for campo in ("titulo", "objetivo", "tecnica", "prioridade", "passos"):
            ruim = caso()
            ruim.pop(campo)
            with self.subTest(campo=campo), self.assertRaises(ValueError) as erro:
                ciclos.validar_casos([ruim])
            self.assertIn(campo, str(erro.exception))

    def test_prioridade_invalida(self):
        with self.assertRaises(ValueError) as erro:
            ciclos.validar_casos([caso(prioridade="urgentíssima")])
        self.assertIn("Alta, Média, Baixa", str(erro.exception))

    def test_passos_exigem_acao_e_resultado_esperado_e_tem_limite(self):
        for passos in ([], [{"acao": "só ação"}], [{"resultado_esperado": "só resultado"}], ["texto"], [{"acao": " ", "resultado_esperado": "x"}]):
            with self.subTest(passos=passos), self.assertRaises(ValueError):
                ciclos.validar_casos([caso(passos=passos)])
        trinta = [{"acao": f"a{i}", "resultado_esperado": "r"} for i in range(ciclos.MAX_PASSOS)]
        self.assertEqual(len(ciclos.validar_casos([caso(passos=trinta)])[0].passos), ciclos.MAX_PASSOS)
        with self.assertRaises(ValueError):
            ciclos.validar_casos([caso(passos=trinta + [{"acao": "a", "resultado_esperado": "r"}])])

    def test_evidencias_base_so_com_nome_de_pasta_e_numero_valido(self):
        for ruim in ([{"teste": "../x", "numero": 1}], [{"teste": "ok", "numero": 0}], [{"teste": "ok"}],
                     [{"teste": "ok", "numero": "abc"}], ["texto"], [{"teste": "a/b", "numero": 1}]):
            with self.subTest(ruim=ruim), self.assertRaises(ValueError):
                ciclos.validar_casos([caso(evidencias_base=ruim)])

    def test_textos_sao_limpos_e_cortados(self):
        (c,) = ciclos.validar_casos([caso(titulo="Linha 1\nLinha\u202e 2", objetivo="x" * 1000,
                                          pre_condicoes=["a\x00b"] + ["y" * 500])])
        self.assertEqual(c.titulo, "Linha 1 Linha 2")
        self.assertEqual(len(c.objetivo), 400)
        self.assertEqual((c.pre_condicoes[0], len(c.pre_condicoes[1])), ("a b", 300))

    def test_so_um_verdadeiro_de_verdade_marca_a_confirmar(self):
        self.assertTrue(ciclos.validar_casos([caso(a_confirmar=True)])[0].a_confirmar)
        for valor in ("true", "false", 1, None, "sim"):
            self.assertFalse(ciclos.validar_casos([caso(a_confirmar=valor)])[0].a_confirmar)

    def test_a_mensagem_de_erro_lista_os_problemas_para_a_ia_se_corrigir(self):
        with self.assertRaises(ValueError) as erro:
            ciclos.validar_casos([caso(id="x"), caso(id="CT-02", titulo=""), caso(id="CT-03", prioridade="zzz")])
        texto = str(erro.exception)
        self.assertIn("casos[0].id", texto)
        self.assertIn("casos[1].titulo", texto)
        self.assertIn("casos[2].prioridade", texto)

    def test_chaves_desconhecidas_sao_ignoradas_e_nao_chegam_ao_resultado(self):
        (c,) = ciclos.validar_casos([caso(comando="rm -rf /", __proto__={"x": 1})])
        self.assertFalse(hasattr(c, "comando"))


class Roteiro(Base):
    def setUp(self):
        super().setUp()
        self.ciclo = ciclos.criar_ciclo(self.base, PARAMETROS)

    def test_grava_e_le_o_roteiro(self):
        caminho = ciclos.gravar_roteiro(self.ciclo.pasta, ciclos.validar_casos([caso()]), ["Qual a regra de bloqueio?"])
        self.assertEqual(caminho.name, "roteiro-001.json")
        roteiro = ciclos.ler_roteiro_mais_recente(self.ciclo.pasta)
        self.assertEqual((roteiro.numero, len(roteiro.casos), roteiro.observacoes), (1, 1, ["Qual a regra de bloqueio?"]))
        self.assertEqual(roteiro.casos[0].passos[1].resultado_esperado, "O painel inicial é exibido")

    def test_cada_geracao_cria_o_proximo_numero_sem_apagar_a_anterior(self):
        a = ciclos.gravar_roteiro(self.ciclo.pasta, ciclos.validar_casos([caso()]))
        b = ciclos.gravar_roteiro(self.ciclo.pasta, ciclos.validar_casos([caso(), caso(id="CT-02")]))
        self.assertEqual((a.name, b.name), ("roteiro-001.json", "roteiro-002.json"))
        self.assertTrue(a.exists())
        self.assertEqual(len(ciclos.ler_roteiro_mais_recente(self.ciclo.pasta).casos), 2)

    def test_sem_roteiro_devolve_none(self):
        self.assertIsNone(ciclos.ler_roteiro_mais_recente(self.ciclo.pasta))

    def test_arquivo_adulterado_e_pulado_e_vale_o_anterior_valido(self):
        ciclos.gravar_roteiro(self.ciclo.pasta, ciclos.validar_casos([caso()]))
        ruim = ciclos.gravar_roteiro(self.ciclo.pasta, ciclos.validar_casos([caso(), caso(id="CT-02")]))
        dados = json.loads(ruim.read_text(encoding="utf-8"))
        dados["casos"][0]["prioridade"] = "inventada"
        ruim.write_text(json.dumps(dados), encoding="utf-8")
        self.assertEqual((ciclos.ler_roteiro_mais_recente(self.ciclo.pasta).numero), 1)
        ruim.write_text("{não é json", encoding="utf-8")
        self.assertEqual((ciclos.ler_roteiro_mais_recente(self.ciclo.pasta).numero), 1)

    def test_roteiro_grande_demais_nao_e_lido_nem_gravado(self):
        gigante = [caso(id=f"CT-{i:02d}", passos=[{"acao": "a" * 400, "resultado_esperado": "r" * 400}] * 30,
                        pre_condicoes=["p" * 300] * 12, dados_de_teste=["d" * 300] * 12, pos_condicoes=["x" * 300] * 12,
                        rastreio=["r" * 120] * 12) for i in range(1, 80)]
        with self.assertRaises(ValueError):
            ciclos.gravar_roteiro(self.ciclo.pasta, ciclos.validar_casos(gigante))
        (self.ciclo.pasta / "roteiro-009.json").write_text(" " * 2_100_000, encoding="utf-8")
        self.assertIsNone(ciclos.ler_roteiro_mais_recente(self.ciclo.pasta))

    def test_nunca_sobrescreve_um_arquivo_existente(self):
        existente = self.ciclo.pasta / "roteiro-001.json"
        existente.write_text("conteúdo do usuário", encoding="utf-8")  # inválido, mas existe
        novo = ciclos.gravar_roteiro(self.ciclo.pasta, ciclos.validar_casos([caso()]))
        self.assertEqual(novo.name, "roteiro-002.json")
        self.assertEqual(existente.read_text(encoding="utf-8"), "conteúdo do usuário")

    def test_pasta_inexistente_ou_atalho_e_recusada(self):
        with self.assertRaises(ValueError):
            ciclos.gravar_roteiro(self.base / "nao existe", ciclos.validar_casos([caso()]))

    def test_nomes_de_arquivo_fora_do_padrao_nao_contam_como_roteiro(self):
        for nome in ("roteiro-1.json", "roteiro-0001.json", "roteiro-001.json.bak", "roteiro-001.txt"):
            (self.ciclo.pasta / nome).write_text("{}", encoding="utf-8")
        self.assertIsNone(ciclos.ler_roteiro_mais_recente(self.ciclo.pasta))
        self.assertEqual(ciclos.gravar_roteiro(self.ciclo.pasta, ciclos.validar_casos([caso()])).name, "roteiro-001.json")

    def test_o_windows_nao_distingue_maiusculas_e_o_numero_nao_se_repete(self):
        (self.ciclo.pasta / "Roteiro-001.JSON").write_text("{}", encoding="utf-8")  # mesmo arquivo que roteiro-001.json
        self.assertEqual(ciclos.gravar_roteiro(self.ciclo.pasta, ciclos.validar_casos([caso()])).name, "roteiro-002.json")

    def test_o_roteiro_gravado_nao_guarda_nada_alem_dos_campos_conhecidos(self):
        arquivo = ciclos.gravar_roteiro(self.ciclo.pasta, ciclos.validar_casos([caso(comando="x", segredo="y")]))
        texto = arquivo.read_text(encoding="utf-8")
        self.assertNotIn("comando", texto)
        self.assertNotIn("segredo", texto)


class DefinicaoDoCiclo(Base):
    """O usuário só escolhe as telas; o resto a IA propõe, e o que ele preencher sempre vale."""

    SUGESTAO = {"objetivo": "Validar o cadastro de fornecedor", "escopo": ["Cadastro", "Edição"], "riscos": "Dados duplicados",
                "sistema": "ERP", "criterios_entrada": ["Ambiente no ar"], "criterios_saida": ["Casos de prioridade Alta executados"]}

    def ciclo_so_com_telas(self):
        return ciclos.criar_ciclo(self.base, {"nome": "Ciclo - Login", "testes_base": ["2026-10-09_1400 - Login"]})

    def test_a_ia_propoe_o_que_o_usuario_nao_preencheu(self):
        ciclo = self.ciclo_so_com_telas()
        ciclos.gravar_roteiro(ciclo.pasta, ciclos.validar_casos([caso()]), ciclo_sugerido=self.SUGESTAO)
        roteiro = ciclos.ler_roteiro_mais_recente(ciclo.pasta)
        efetiva = ciclos.definicao_efetiva(ciclo, roteiro)
        self.assertEqual(efetiva["objetivo"], "Validar o cadastro de fornecedor")
        self.assertEqual(efetiva["escopo"], ["Cadastro", "Edição"])
        self.assertEqual(efetiva["criterios_saida"], ["Casos de prioridade Alta executados"])
        self.assertEqual({efetiva["origem"][k] for k in ("objetivo", "escopo", "criterios_entrada")}, {"IA"})

    def test_o_que_o_usuario_preencheu_sempre_vale_mais_que_a_ia(self):
        ciclo = ciclos.criar_ciclo(self.base, {**PARAMETROS, "objetivo": "Meu objetivo", "criterios_saida": ["Só isto"]})
        ciclos.gravar_roteiro(ciclo.pasta, ciclos.validar_casos([caso()]), ciclo_sugerido=self.SUGESTAO)
        efetiva = ciclos.definicao_efetiva(ciclo, ciclos.ler_roteiro_mais_recente(ciclo.pasta))
        self.assertEqual((efetiva["objetivo"], efetiva["criterios_saida"]), ("Meu objetivo", ["Só isto"]))
        self.assertEqual((efetiva["origem"]["objetivo"], efetiva["origem"]["criterios_saida"]), ("usuário", "usuário"))
        self.assertEqual(efetiva["origem"]["criterios_entrada"], "IA")  # o resto continua automático

    def test_sem_roteiro_os_criterios_caem_no_padrao_do_ctfl(self):
        efetiva = ciclos.definicao_efetiva(self.ciclo_so_com_telas(), None)
        self.assertEqual(tuple(efetiva["criterios_entrada"]), ciclos.CRITERIOS_ENTRADA_PADRAO)
        self.assertEqual(tuple(efetiva["criterios_saida"]), ciclos.CRITERIOS_SAIDA_PADRAO)
        self.assertEqual((efetiva["origem"]["criterios_entrada"], efetiva["objetivo"], efetiva["origem"]["objetivo"]),
                         ("padrão", "", ""))

    def test_criterios_vazios_do_usuario_nao_apagam_a_proposta(self):
        # lista vazia = "não preenchi": cai na IA, e não num ciclo sem critério nenhum
        ciclo = ciclos.criar_ciclo(self.base, {**PARAMETROS, "criterios_saida": []})
        ciclos.gravar_roteiro(ciclo.pasta, ciclos.validar_casos([caso()]), ciclo_sugerido=self.SUGESTAO)
        efetiva = ciclos.definicao_efetiva(ciclo, ciclos.ler_roteiro_mais_recente(ciclo.pasta))
        self.assertEqual(efetiva["criterios_saida"], ["Casos de prioridade Alta executados"])

    def test_proposta_da_ia_e_validada_e_limpa(self):
        limpa = ciclos.validar_ciclo_sugerido({"objetivo": "a\nb‮" + "x" * 900, "escopo": ["A"] * 5, "comando": "rm -rf /",
                                               "criterios_entrada": "um só como texto"})
        self.assertEqual(len(limpa["objetivo"]), 500)
        self.assertNotIn("‮", limpa["objetivo"])
        self.assertNotIn("comando", limpa)
        self.assertEqual(limpa["criterios_entrada"], ["um só como texto"])
        self.assertEqual(ciclos.validar_ciclo_sugerido(None), {})
        for ruim in ("texto", [1, 2], {"escopo": ["x"] * (ciclos.MAX_ESCOPO + 1)}, {"escopo": [{"a": 1}]}):
            with self.subTest(ruim=ruim), self.assertRaises(ValueError):
                ciclos.validar_ciclo_sugerido(ruim)

    def test_proposta_adulterada_no_arquivo_invalida_so_aquele_roteiro(self):
        ciclo = self.ciclo_so_com_telas()
        ciclos.gravar_roteiro(ciclo.pasta, ciclos.validar_casos([caso()]))
        ruim = ciclos.gravar_roteiro(ciclo.pasta, ciclos.validar_casos([caso()]), ciclo_sugerido=self.SUGESTAO)
        dados = json.loads(ruim.read_text(encoding="utf-8"))
        dados["ciclo_sugerido"] = "adulterado"
        ruim.write_text(json.dumps(dados), encoding="utf-8")
        self.assertEqual(ciclos.ler_roteiro_mais_recente(ciclo.pasta).numero, 1)

    def test_nome_automatico_vem_dos_testes_de_referencia(self):
        self.assertEqual(ciclos.nome_automatico(["Login no ERP"]), "Ciclo - Login no ERP")
        self.assertEqual(ciclos.nome_automatico(["Login", "Cadastro", "Pedido"]), "Ciclo - Login e mais 2")
        self.assertEqual(ciclos.nome_automatico([]), "Ciclo de testes")
        self.assertEqual(ciclos.nome_automatico(["x" * 200]), "Ciclo - " + "x" * 60)


if __name__ == "__main__":
    unittest.main()
