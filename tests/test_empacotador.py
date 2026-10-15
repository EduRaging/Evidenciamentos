"""A lista de módulos do pacote da extensão precisa cobrir tudo que o servidor importa."""
import ast
import importlib.util
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def carregar_empacotador():
    especificacao = importlib.util.spec_from_file_location("empacotar_mcpb", RAIZ / "tools" / "empacotar_mcpb.py")
    modulo = importlib.util.module_from_spec(especificacao)
    especificacao.loader.exec_module(modulo)
    return modulo


def importados_do_pacote(nome: str) -> set[str]:
    """Módulos `capturador.*` que `nome` importa (import relativo `from . import x` / `from .x import y`)."""
    arvore = ast.parse((RAIZ / "capturador" / f"{nome}.py").read_text(encoding="utf-8"))
    achados: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom) and no.level == 1:
            if no.module:  # from .x import y
                achados.add(no.module.split(".")[0])
            else:  # from . import x, y
                achados.update(a.name for a in no.names)
    return achados


class ListaDeModulosDoPacote(unittest.TestCase):
    def test_o_pacote_leva_todos_os_modulos_que_o_servidor_importa_direta_ou_indiretamente(self):
        empacotador = carregar_empacotador()
        incluidos = set(empacotador.MODULOS)
        pendentes, vistos = ["mcp_servidor"], set()
        while pendentes:
            atual = pendentes.pop()
            if atual in vistos:
                continue
            vistos.add(atual)
            pendentes.extend(importados_do_pacote(atual))
        faltando = sorted(vistos - incluidos)
        self.assertEqual(faltando, [], f"módulos importados pelo servidor mas fora do pacote: {faltando}")

    def test_modulos_de_interface_nao_vao_no_pacote(self):
        empacotador = carregar_empacotador()
        for gui in ("app", "captura", "aviso", "dialogos", "dialogo_prompt", "painel_pdfs", "atalhos", "winutil"):
            self.assertNotIn(gui, empacotador.MODULOS)  # Tk e captura de tela não pertencem ao servidor

    def test_a_pasta_vem_por_argumento_e_por_variavel_e_sem_valor_padrao(self):
        manifesto = carregar_empacotador().manifesto()
        configuracao = manifesto["server"]["mcp_config"]
        self.assertIn("--pasta", configuracao["args"])
        self.assertEqual(configuracao["env"]["CAPTURADOR_PASTA_BASE"], "${user_config.pasta_base}")
        self.assertNotIn("default", manifesto["user_config"]["pasta_base"])  # escolha explícita obrigatória

    def test_python_do_pacote_roda_em_modo_isolado(self):
        args = carregar_empacotador().manifesto()["server"]["mcp_config"]["args"]
        self.assertEqual(args[:2], ["-I", "-B"])

    def test_faixa_de_python_e_valida_no_formato_node_semver(self):
        faixa = carregar_empacotador().manifesto()["compatibility"]["runtimes"]["python"]
        self.assertNotIn(",", faixa)  # com vírgula a faixa é inválida e o instalador acusa requisito não atendido
        self.assertRegex(faixa, r"^>=\d+\.\d+\.0 <\d+\.\d+\.0$")


if __name__ == "__main__":
    unittest.main()
