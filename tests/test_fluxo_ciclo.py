"""Do teste capturado ao ciclo: criação só com as telas e o pedido ao Claude."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from capturador import ciclos, fluxo_ciclo
from capturador.sessao import Sessao


class FluxoDoCiclo(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = Path(self._tmp.name)
        self.base = self.raiz / "Evidencias"

    def criar(self, nome, imagens=2):
        sessao = Sessao(self.raiz / f"trab_{nome[:3]}")
        for _ in range(imagens):
            sessao.adicionar(Image.new("RGB", (80, 50), "navy"), "tela")
        return sessao.finalizar(nome, "QA", self.base)

    def test_cria_o_ciclo_so_com_as_telas_e_o_nome_vem_do_teste(self):
        login = self.criar("Login no ERP")
        ciclo, ignorados = fluxo_ciclo.criar_a_partir_de_testes(self.base, [login])
        self.assertEqual(ignorados, [])
        self.assertEqual((ciclo.nome, ciclo.testes_base), ("Ciclo - Login no ERP", [login.name]))
        self.assertEqual((ciclo.objetivo, ciclo.escopo, ciclo.criterios_entrada, ciclo.criterios_saida), ("", [], None, None))
        self.assertEqual(ciclos.ler_ciclo(ciclo.pasta).nome, ciclo.nome)

    def test_varias_telas_e_ajustes_opcionais_do_usuario(self):
        a, b = self.criar("Login"), self.criar("Cadastro")
        ciclo, _ = fluxo_ciclo.criar_a_partir_de_testes(self.base, [a, b], {"tipo": "Regressão", "objetivo": "Meu objetivo",
                                                                            "nome": "  "})
        self.assertEqual((ciclo.nome, ciclo.tipo, ciclo.objetivo), ("Ciclo - Login e mais 1", "Regressão", "Meu objetivo"))
        self.assertEqual(len(ciclo.testes_base), 2)

    def test_nome_do_usuario_vale_mais_que_o_automatico(self):
        ciclo, _ = fluxo_ciclo.criar_a_partir_de_testes(self.base, [self.criar("Login")], {"nome": "Rodada de outubro"})
        self.assertEqual(ciclo.nome, "Rodada de outubro")

    def test_teste_sem_imagens_fica_de_fora_com_aviso(self):
        bom = self.criar("Login")
        vazio = self.base / "2026-01-01_0900 - So PDF"
        vazio.mkdir()
        (vazio / "Evidencias - So PDF.pdf").write_bytes(b"%PDF")
        ciclo, ignorados = fluxo_ciclo.criar_a_partir_de_testes(self.base, [vazio, bom])
        self.assertEqual(ciclo.testes_base, [bom.name])
        self.assertEqual([n for n, _ in ignorados], [vazio.name])

    def test_nenhum_teste_servindo_nao_cria_ciclo(self):
        with self.assertRaises(ValueError):
            fluxo_ciclo.criar_a_partir_de_testes(self.base, [self.raiz / "nao existe"])
        self.assertFalse((self.base / "_ciclos").exists())

    def test_parametro_invalido_nao_deixa_ciclo_pela_metade(self):
        with self.assertRaises(ValueError):
            fluxo_ciclo.criar_a_partir_de_testes(self.base, [self.criar("Login")], {"tipo": "carga"})
        self.assertEqual(ciclos.listar_ciclos(self.base), [])

    def test_o_pedido_traz_as_telas_de_referencia(self):
        login = self.criar("Login no ERP", 3)
        ciclo, _ = fluxo_ciclo.criar_a_partir_de_testes(self.base, [login])
        pedido = fluxo_ciclo.montar_pedido(ciclo, self.base)
        self.assertIn(f'pasta "{login.name}" — 3 evidências', pedido)
        self.assertIn(f'ciclo="{ciclo.pasta.name}"', pedido)
        self.assertNotIn("não foram encontrados", pedido)

    def test_tela_de_referencia_arquivada_vira_aviso_no_pedido(self):
        login, cadastro = self.criar("Login"), self.criar("Cadastro")
        ciclo, _ = fluxo_ciclo.criar_a_partir_de_testes(self.base, [login, cadastro])
        from capturador import arquivamento
        arquivamento.arquivar(login, self.base)
        testes, ausentes = fluxo_ciclo.testes_de_referencia(ciclo, self.base)
        self.assertEqual(([t.pasta.name for t in testes], ausentes), ([cadastro.name], [login.name]))
        self.assertIn("não foram encontrados", fluxo_ciclo.montar_pedido(ciclo, self.base))

    def test_nomes_perigosos_no_ciclo_json_nao_saem_da_base(self):
        ciclo, _ = fluxo_ciclo.criar_a_partir_de_testes(self.base, [self.criar("Login")])
        ciclo.testes_base[:] = ["_ciclos", "..", "a/b", "nao existe"]  # como se o ciclo.json tivesse sido adulterado
        testes, ausentes = fluxo_ciclo.testes_de_referencia(ciclo, self.base)
        self.assertEqual((testes, len(ausentes)), ([], 4))

    def test_situacao_do_ciclo(self):
        ciclo, _ = fluxo_ciclo.criar_a_partir_de_testes(self.base, [self.criar("Login")])
        self.assertEqual(fluxo_ciclo.situacao(ciclo), ("sem roteiro", 0))
        caso = {"id": "CT-01", "titulo": "T", "objetivo": "O", "tecnica": "Checklist", "prioridade": "Alta",
                "passos": [{"acao": "a", "resultado_esperado": "r"}]}
        ciclos.gravar_roteiro(ciclo.pasta, ciclos.validar_casos([caso, {**caso, "id": "CT-02"}]))
        self.assertEqual(fluxo_ciclo.situacao(ciclo), ("roteiro pronto", 2))


if __name__ == "__main__":
    unittest.main()
