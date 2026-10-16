import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from capturador import arquivamento, registro_pdfs


def criar_teste(base: Path, nome: str) -> Path:
    pasta = base / nome
    pasta.mkdir(parents=True)
    (pasta / f"Evidencias - {nome}.pdf").write_bytes(b"%PDF-1.4")
    (pasta / "01_tela.png").write_bytes(b"png")
    return pasta


class Arquivar(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name) / "Evidencias"
        self.base.mkdir()

    def test_move_a_pasta_inteira_para_o_arquivo_sem_apagar_nada(self):
        pasta = criar_teste(self.base, "2026-10-09_1400 - Login")
        destino = arquivamento.arquivar(pasta, self.base)
        self.assertEqual(destino, self.base / "_arquivo" / "2026-10-09_1400 - Login")
        self.assertFalse(pasta.exists())
        self.assertEqual(sorted(p.name for p in destino.iterdir()),
                         ["01_tela.png", "Evidencias - 2026-10-09_1400 - Login.pdf"])

    def test_o_teste_arquivado_some_da_lista_de_pdfs(self):
        a = criar_teste(self.base, "2026-10-09_1400 - Login")
        criar_teste(self.base, "2026-10-09_1500 - Cadastro")
        self.assertEqual(len(registro_pdfs.listar_pdfs(self.base)), 2)
        arquivamento.arquivar(a, self.base)
        self.assertEqual([r.teste for r in registro_pdfs.listar_pdfs(self.base)], ["Cadastro"])

    def test_nome_repetido_no_arquivo_nao_sobrescreve(self):
        pasta = criar_teste(self.base, "2026-10-09_1400 - Login")
        primeiro = arquivamento.arquivar(pasta, self.base)
        criar_teste(self.base, "2026-10-09_1400 - Login")
        segundo = arquivamento.arquivar(self.base / "2026-10-09_1400 - Login", self.base)
        self.assertNotEqual(primeiro, segundo)
        self.assertTrue(primeiro.is_dir() and segundo.is_dir())
        self.assertEqual(segundo.name, "2026-10-09_1400 - Login (2)")

    def test_pasta_que_nao_esta_diretamente_na_base_e_recusada(self):
        fora = criar_teste(Path(self._tmp.name) / "Outra", "teste")
        with self.assertRaises(ValueError):
            arquivamento.arquivar(fora, self.base)
        aninhada = criar_teste(self.base / "grupo", "teste")
        with self.assertRaises(ValueError):
            arquivamento.arquivar(aninhada, self.base)
        self.assertTrue(fora.exists() and aninhada.exists())

    def test_pastas_de_trabalho_e_o_proprio_arquivo_nao_podem_ser_arquivadas(self):
        for nome in ("_em_andamento", ".oculta", "_arquivo"):
            with self.subTest(nome=nome):
                (self.base / nome).mkdir()
                with self.assertRaises(ValueError):
                    arquivamento.arquivar(self.base / nome, self.base)

    def test_pasta_inexistente_e_recusada(self):
        with self.assertRaises(ValueError):
            arquivamento.arquivar(self.base / "nao existe", self.base)

    def test_juncao_para_fora_e_recusada_e_o_alvo_nao_e_movido(self):
        alvo = criar_teste(Path(self._tmp.name) / "Segredo", "dados")
        juncao = self.base / "2026-10-09_1400 - Atalho"
        resultado = subprocess.run(["cmd", "/c", "mklink", "/J", str(juncao), str(alvo)],
                                   capture_output=True, text=True)
        if resultado.returncode != 0 or not os.path.isjunction(juncao):
            self.skipTest("não foi possível criar a junção neste ambiente")
        with self.assertRaises(ValueError):
            arquivamento.arquivar(juncao, self.base)
        self.assertTrue((alvo / "01_tela.png").exists())

    def test_pasta_arquivo_que_e_um_arquivo_comum_e_recusada(self):
        pasta = criar_teste(self.base, "2026-10-09_1400 - Login")
        (self.base / "_arquivo").write_text("x", encoding="utf-8")
        with self.assertRaises(ValueError):
            arquivamento.arquivar(pasta, self.base)
        self.assertTrue(pasta.exists())

    def test_arquivo_aberto_por_outro_programa_falha_sem_perder_nada(self):
        pasta = criar_teste(self.base, "2026-10-09_1400 - Login")
        aberto = open(pasta / "01_tela.png", "rb")  # o Windows não deixa mover uma pasta com arquivo aberto
        try:
            with self.assertRaises(OSError):
                arquivamento.arquivar(pasta, self.base)
        finally:
            aberto.close()
        self.assertTrue((pasta / "01_tela.png").exists())


if __name__ == "__main__":
    unittest.main()
