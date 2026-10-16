import os
import struct
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

from capturador import registro_pdfs, winutil
from capturador.registro_pdfs import RegistroPdf, filtrar, formatar_tamanho, listar_pdfs


def criar(pasta: Path, nome: str, conteudo: bytes = b"%PDF-1.4", mtime: float | None = None) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / nome
    arquivo.write_bytes(conteudo)
    if mtime is not None:
        os.utime(arquivo, (mtime, mtime))
    return arquivo


class ListarPdfs(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def test_lista_evidencias_e_relatorios_do_mais_recente_para_o_mais_antigo(self):
        agora = time.time()
        criar(self.base / "2026-10-09_1400 - Login", "Evidencias - Login.pdf", mtime=agora - 300)
        criar(self.base / "2026-10-09_1400 - Login", "Relatório de testes - Login.pdf", mtime=agora - 100)
        criar(self.base / "2026-10-08_0900 - Cadastro", "Evidencias - Cadastro.pdf", mtime=agora - 900)
        itens = listar_pdfs(self.base)
        self.assertEqual([i.caminho.name for i in itens], [
            "Relatório de testes - Login.pdf", "Evidencias - Login.pdf", "Evidencias - Cadastro.pdf"])
        self.assertEqual([i.tipo for i in itens], ["Relatório", "Evidências", "Evidências"])

    def test_nome_do_teste_vem_da_pasta_sem_o_prefixo_de_data(self):
        criar(self.base / "2026-10-09_1400 - Login no ERP", "Evidencias - Login no ERP.pdf")
        item = listar_pdfs(self.base)[0]
        self.assertEqual(item.teste, "Login no ERP")
        self.assertEqual(item.pasta_teste, "2026-10-09_1400 - Login no ERP")

    def test_ignora_pastas_de_trabalho_arquivos_soltos_e_nao_pdfs(self):
        criar(self.base / "_em_andamento", "x.pdf")
        criar(self.base / ".oculta", "y.pdf")
        criar(self.base / "teste", "foto.png")
        criar(self.base / "teste", "MAIUSCULO.PDF")  # extensão em maiúsculas conta
        (self.base / "solto.pdf").write_bytes(b"%PDF")  # PDF direto na base: não é de um teste
        self.assertEqual([i.caminho.name for i in listar_pdfs(self.base)], ["MAIUSCULO.PDF"])

    def test_pasta_inexistente_ou_vazia_devolve_lista_vazia(self):
        self.assertEqual(listar_pdfs(self.base / "nao_existe"), [])
        self.assertEqual(listar_pdfs(self.base), [])

    def test_limite_mantem_os_mais_recentes(self):
        agora = time.time()
        for i in range(5):
            criar(self.base / f"t{i}", f"Relatório {i}.pdf", mtime=agora - i * 100)
        itens = listar_pdfs(self.base, limite=2)
        self.assertEqual([i.caminho.name for i in itens], ["Relatório 0.pdf", "Relatório 1.pdf"])

    def test_tamanho_e_momento_do_arquivo(self):
        criar(self.base / "t", "Evidencias - t.pdf", conteudo=b"x" * 2048, mtime=time.time() - 60)
        item = listar_pdfs(self.base)[0]
        self.assertEqual(item.tamanho, 2048)
        self.assertLess((datetime.now() - item.momento).total_seconds(), 120)


class Filtro(unittest.TestCase):
    def setUp(self):
        agora = datetime.now()
        self.registros = [
            RegistroPdf(Path("C:/b/t1/Relatório de testes - Inclusão de despesa.pdf"),
                        "Inclusão de despesa", "2026-10-15_1431 - Inclusão de despesa", "Relatório", agora, 100),
            RegistroPdf(Path("C:/b/t2/Evidencias - Motivo da rejeição.pdf"),
                        "Motivo da rejeição", "2026-10-15_0942 - Motivo da rejeição", "Evidências", agora, 100),
        ]

    def test_ignora_acentos_e_maiusculas(self):
        self.assertEqual(len(filtrar(self.registros, "RELATORIO")), 1)
        self.assertEqual(len(filtrar(self.registros, "inclusao")), 1)
        self.assertEqual(len(filtrar(self.registros, "rejeicao")), 1)

    def test_todas_as_palavras_precisam_aparecer(self):
        self.assertEqual(len(filtrar(self.registros, "despesa relatorio")), 1)
        self.assertEqual(len(filtrar(self.registros, "despesa evidencias")), 0)

    def test_filtro_vazio_mantem_tudo(self):
        self.assertEqual(len(filtrar(self.registros, "   ")), 2)

    def test_procura_tambem_no_tipo(self):
        self.assertEqual([r.tipo for r in filtrar(self.registros, "evidencias")], ["Evidências"])


class Tamanho(unittest.TestCase):
    def test_formatos(self):
        self.assertEqual(formatar_tamanho(10), "1 KB")
        self.assertEqual(formatar_tamanho(2048), "2 KB")
        self.assertEqual(formatar_tamanho(3_500_000), "3,3 MB")


class AreaDeTransferencia(unittest.TestCase):
    def test_dropfiles_tem_o_formato_cf_hdrop(self):
        dados = winutil.montar_dropfiles([r"C:\a\um.pdf", r"C:\b\dois.pdf"])
        p_files, x, y, f_nc, f_wide = struct.unpack("<IiiII", dados[:20])
        self.assertEqual((p_files, f_wide), (20, 1))  # cabeçalho de 20 bytes; caminhos em UTF-16
        texto = dados[p_files:].decode("utf-16-le")
        self.assertEqual(texto, "C:\\a\\um.pdf\0C:\\b\\dois.pdf\0\0")  # separados por NUL e fim com NUL duplo

    def test_dropfiles_preserva_acentos_e_c_cedilha(self):
        caminho = r"C:\Users\x\Documents\AUTOMAÇOES\Relatório de testes.pdf"
        dados = winutil.montar_dropfiles([caminho])
        self.assertEqual(dados[20:].decode("utf-16-le"), caminho + "\0\0")


class AgruparPorTeste(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        agora = time.time()
        criar(self.base / "2026-10-09_1400 - Login", "Evidencias - Login.pdf", mtime=agora - 500)
        criar(self.base / "2026-10-09_1400 - Login", "Relatório de testes - Login.pdf", mtime=agora - 100)
        criar(self.base / "2026-10-09_1400 - Login", "Relatório de testes - Login (2).pdf", mtime=agora - 50)
        criar(self.base / "2026-10-08_0900 - Cadastro", "Evidencias - Cadastro.pdf", mtime=agora - 900)
        criar(self.base / "2026-10-10_0800 - So relatorio", "Relatório - X.pdf", mtime=agora - 10)

    def agrupados(self):
        return registro_pdfs.agrupar_por_teste(listar_pdfs(self.base))

    def test_um_item_por_teste_do_mais_recente_para_o_mais_antigo(self):
        self.assertEqual([t.teste for t in self.agrupados()], ["So relatorio", "Login", "Cadastro"])

    def test_separa_evidencias_e_relatorios_com_o_relatorio_mais_novo_primeiro(self):
        login = next(t for t in self.agrupados() if t.teste == "Login")
        self.assertEqual(login.evidencias.caminho.name, "Evidencias - Login.pdf")
        self.assertEqual([r.caminho.name for r in login.relatorios],
                         ["Relatório de testes - Login (2).pdf", "Relatório de testes - Login.pdf"])
        self.assertEqual(len(login.pdfs), 3)

    def test_pdf_principal_e_o_relatorio_mais_recente_ou_senao_o_de_evidencias(self):
        por_nome = {t.teste: t for t in self.agrupados()}
        self.assertEqual(por_nome["Login"].principal.caminho.name, "Relatório de testes - Login (2).pdf")
        self.assertEqual(por_nome["Cadastro"].principal.caminho.name, "Evidencias - Cadastro.pdf")
        self.assertEqual(por_nome["Cadastro"].relatorios, ())
        self.assertIsNone(por_nome["So relatorio"].evidencias)

    def test_a_ordem_vem_do_dia_do_teste_e_nao_do_relatorio_gerado_depois(self):
        # o relatório do Login é mais novo que o PDF do teste de 10/10, mas o teste de 10/10 ainda vem primeiro
        self.assertEqual(self.agrupados()[0].momento.day, 10)

    def test_pasta_sem_prefixo_de_data_usa_o_pdf_mais_antigo(self):
        criar(self.base / "Pasta sem data", "Evidencias - Sem data.pdf", mtime=time.time() - 5000)
        sem_data = next(t for t in self.agrupados() if t.pasta_nome == "Pasta sem data")
        self.assertAlmostEqual(sem_data.momento.timestamp(), time.time() - 5000, delta=5)

    def test_lista_vazia(self):
        self.assertEqual(registro_pdfs.agrupar_por_teste([]), [])

    def test_filtro_por_teste_combina_palavras_ignora_acento_e_olha_os_arquivos(self):
        testes = self.agrupados()
        achar = lambda texto: [t.teste for t in registro_pdfs.filtrar_testes(testes, texto)]  # noqa: E731
        self.assertEqual(achar(""), ["So relatorio", "Login", "Cadastro"])
        self.assertEqual(achar("login"), ["Login"])
        self.assertEqual(achar("relatorio login"), ["Login"])  # a palavra do arquivo "Relatório de testes - Login"
        self.assertEqual(achar("cadastro evidencias"), ["Cadastro"])
        self.assertEqual(achar("zzz"), [])


if __name__ == "__main__":
    unittest.main()
