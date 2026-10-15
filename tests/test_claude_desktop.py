"""Envio do prompt ao Claude desktop: link, comando registrado no Windows e quedas para a área de transferência."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from capturador import claude_desktop as cd
from capturador.prompt_ia import Formulario, montar_prompt
from tests.test_prompt_ia import teste_exemplo


class Lancador:
    """Substitui subprocess.Popen: guarda o que seria executado."""

    def __init__(self, falhar: bool = False):
        self.chamadas = []
        self.falhar = falhar

    def __call__(self, comando, **opcoes):
        if self.falhar:
            raise OSError("não abriu")
        self.chamadas.append((comando, opcoes))


class ClaudeFalso(unittest.TestCase):
    """Cria um 'claude.exe' de mentira numa pasta com espaço no nome, como em C:\\Program Files."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        pasta = Path(self._tmp.name) / "Meu Claude"
        pasta.mkdir()
        self.exe = pasta / "claude.exe"
        self.exe.write_bytes(b"MZ")
        self.linha = f'"{self.exe}" "%1"'


class LinkDoPrompt(unittest.TestCase):
    def test_sem_texto_abre_conversa_em_branco(self):
        self.assertEqual(cd.montar_link(), "claude://claude.ai/new")
        self.assertEqual(cd.montar_link(""), "claude://claude.ai/new")

    def test_o_texto_vai_codificado_e_volta_identico(self):
        texto = "Análise & revisão: 100% #1 ção\nlinha 2 + \"aspas\" <tag> ?x=y\t\u202e"
        link = cd.montar_link(texto)
        partes = urlsplit(link)
        self.assertEqual((partes.scheme, partes.netloc, partes.path), ("claude", "claude.ai", "/new"))
        self.assertEqual(parse_qs(partes.query)["q"], [texto])
        self.assertNotIn(" ", link)
        self.assertNotIn('"', link)  # nada que quebre a linha de comando
        self.assertNotIn("\n", link)

    def test_o_prompt_completo_do_app_cabe_no_limite(self):
        prompt = montar_prompt(teste_exemplo(), Formulario(via_mcp=True))
        self.assertLessEqual(len(prompt), cd.LIMITE_PROMPT)
        self.assertEqual(parse_qs(urlsplit(cd.montar_link(prompt)).query)["q"], [prompt])


class ComandoRegistrado(ClaudeFalso):
    def test_monta_executavel_e_link_no_lugar_do_percent_1(self):
        link = cd.montar_link("oi")
        self.assertEqual(cd.comando_para_abrir(link, self.linha), [str(self.exe), link])

    def test_aceita_o_percent_1_dentro_de_um_argumento(self):
        link = cd.montar_link("oi")
        linha = f'"{self.exe}" --url=%1'
        self.assertEqual(cd.comando_para_abrir(link, linha), [str(self.exe), f"--url={link}"])

    def test_recusa_programa_que_nao_e_o_claude(self):
        outro = self.exe.with_name("outro.exe")
        outro.write_bytes(b"MZ")
        self.assertIsNone(cd.comando_para_abrir(cd.montar_link(), f'"{outro}" "%1"'))

    def test_recusa_executavel_inexistente(self):
        self.exe.unlink()
        self.assertIsNone(cd.comando_para_abrir(cd.montar_link(), self.linha))

    def test_recusa_formato_desconhecido(self):
        self.assertIsNone(cd.comando_para_abrir(cd.montar_link(), f'"{self.exe}"'))  # sem %1
        self.assertIsNone(cd.comando_para_abrir(cd.montar_link(), ""))

    def test_recusa_linha_de_comando_grande_demais(self):
        link = "claude://claude.ai/new?q=" + "a" * cd.LIMITE_LINHA_DE_COMANDO
        self.assertIsNone(cd.comando_para_abrir(link, self.linha))


class AbrirConversa(ClaudeFalso):
    def abrir(self, prompt, lancador=None):
        lancador = lancador or Lancador()
        resultado = cd.abrir_conversa(prompt, linha_registrada=self.linha, iniciar=lancador)
        return resultado, lancador

    def test_prompt_pequeno_vai_no_link(self):
        resultado, lancador = self.abrir("Analise o teste Login")
        self.assertEqual(resultado, cd.PREENCHIDO)
        comando, opcoes = lancador.chamadas[0]
        self.assertEqual(parse_qs(urlsplit(comando[1]).query)["q"], ["Analise o teste Login"])
        self.assertIs(opcoes["close_fds"], True)
        self.assertEqual(opcoes["stdin"], subprocess.DEVNULL)

    def test_o_programa_roda_sem_shell(self):
        _, lancador = self.abrir("oi")
        self.assertIsInstance(lancador.chamadas[0][0], list)  # lista de argumentos, nunca uma string de shell
        self.assertNotIn("shell", lancador.chamadas[0][1])

    def test_prompt_grande_abre_conversa_em_branco_para_colar(self):
        resultado, lancador = self.abrir("x" * (cd.LIMITE_PROMPT + 1))
        self.assertEqual(resultado, cd.VAZIA)
        self.assertEqual(lancador.chamadas[0][0], [str(self.exe), cd.LINK_NOVA_CONVERSA])  # nada truncado

    def test_prompt_no_limite_ainda_vai_no_link(self):
        resultado, _ = self.abrir("x" * cd.LIMITE_PROMPT)
        self.assertEqual(resultado, cd.PREENCHIDO)

    def test_link_codificado_grande_demais_cai_para_conversa_em_branco(self):
        texto = "ç\n" * (cd.LIMITE_PROMPT // 2)  # cada ç\n vira 9 caracteres codificados
        resultado, lancador = self.abrir(texto)
        self.assertEqual(resultado, cd.VAZIA)
        self.assertEqual(lancador.chamadas[0][0][1], cd.LINK_NOVA_CONVERSA)

    def test_sem_texto_abre_em_branco(self):
        resultado, lancador = self.abrir(None)
        self.assertEqual(resultado, cd.VAZIA)
        self.assertEqual(lancador.chamadas[0][0][1], cd.LINK_NOVA_CONVERSA)

    def test_claude_nao_instalado(self):
        self.exe.unlink()
        resultado, lancador = self.abrir("oi")
        self.assertEqual(resultado, cd.INDISPONIVEL)
        self.assertEqual(lancador.chamadas, [])

    def test_falha_ao_iniciar_o_processo(self):
        resultado, _ = self.abrir("oi", Lancador(falhar=True))
        self.assertEqual(resultado, cd.INDISPONIVEL)


class EntregaDeVerdadePeloWindows(unittest.TestCase):
    """O Windows entrega a linha de comando inteira (acentos e vários milhares de caracteres) ao programa?"""

    def test_prompt_completo_chega_intacto_ao_processo(self):
        prompt = montar_prompt(teste_exemplo(), Formulario(via_mcp=True)) + "ação ✓ 日本\n" * 40
        link = cd.montar_link(prompt)
        self.assertGreater(len(link), 2083)  # acima do limite de URL do ShellExecute
        with tempfile.TemporaryDirectory() as tmp:
            receptor = Path(tmp) / "receptor.py"
            receptor.write_text(
                "import sys\nfrom urllib.parse import parse_qs, urlsplit\n"
                "sys.stdout.buffer.write(parse_qs(urlsplit(sys.argv[1]).query)['q'][0].encode('utf-8'))\n",
                encoding="utf-8")
            linha = f'"{sys.executable}" -I "{receptor}" "%1"'
            comando = cd.comando_para_abrir(link, linha, nome_exe=Path(sys.executable).name)
            self.assertIsNotNone(comando)
            saida = subprocess.run(comando, capture_output=True, check=True).stdout.decode("utf-8")
        self.assertEqual(saida, prompt)


if __name__ == "__main__":
    unittest.main()
