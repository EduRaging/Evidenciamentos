"""Empacota o servidor MCP como extensão do Claude desktop (.mcpb), para uso pessoal.

Uso:  python tools\\empacotar_mcpb.py        (gera dist\\CapturadorEvidencias.mcpb)

As dependências (algumas compiladas) são instaladas com o Python que rodar este script, então
a extensão só funciona em máquinas com a MESMA versão do Python (aqui, 3.14) e Windows. Para
instalar: dê dois cliques no .mcpb (o Claude desktop abre o diálogo de instalação).
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from capturador import __version__  # noqa: E402

NOME_ARQUIVO = "CapturadorEvidencias.mcpb"
# só o que o servidor usa (nada de Tk nem de captura de tela)
MODULOS = ("__init__", "config", "metadados", "prompt_ia", "relatorio_md", "sessao", "pdf_relatorio",
           "mcp_servidor", "imagens", "ciclos", "prompt_ciclo")

PONTO_DE_ENTRADA = '''"""Ponto de entrada da extensão: inicia o servidor MCP do Capturador de Evidências."""
import os
import site
import sys
from pathlib import Path

# A pasta de evidências pode chegar por argumento (--pasta X) ou pela variável de ambiente.
if "--pasta" in sys.argv:
    _i = sys.argv.index("--pasta")
    _valor = sys.argv[_i + 1] if _i + 1 < len(sys.argv) else ""
    if _valor and not os.environ.get("CAPTURADOR_PASTA_BASE"):
        os.environ["CAPTURADOR_PASTA_BASE"] = _valor

aqui = Path(__file__).resolve().parent
sys.path.insert(0, str(aqui))          # o pacote capturador
sys.path.insert(0, str(aqui / "lib"))  # dependências empacotadas (têm prioridade sobre o sistema)
# O pip --target não processa arquivos .pth; o pywin32 (exigido pelo mcp no Windows) depende deles
# para registrar suas pastas e DLLs. addsitedir faz esse processamento.
site.addsitedir(str(aqui / "lib"))

from capturador.mcp_servidor import executar  # noqa: E402

executar()
'''

FERRAMENTAS = [
    ("listar_testes", "Lista os testes finalizados mais recentes."),
    ("obter_teste", "Dados de um teste e a lista numerada de evidências."),
    ("ver_evidencia", "Devolve a imagem de uma evidência para a IA olhar."),
    ("salvar_relatorio_pdf", "Grava o relatório (Markdown) em PDF na pasta do teste, com as evidências."),
    ("salvar_casos", "Grava o roteiro de testes (os casos) de um ciclo na pasta do ciclo, para o app mostrar."),
]


def manifesto() -> dict:
    versao_python = f"{sys.version_info.major}.{sys.version_info.minor}"
    return {
        "manifest_version": "0.3",
        "name": "capturador-evidencias",
        "version": __version__,
        "description": "Deixa o Claude ler as evidências dos seus testes e gerar casos de teste e "
                       "relatório em PDF, com sugestões ISTQB/BSTQB.",
        "author": {"name": "EduRaging"},
        "icon": "icon.png",
        "server": {
            "type": "python",
            "entry_point": "server/main.py",
            "mcp_config": {
                "command": "python",
                # a pasta vai por argumento E por variável de ambiente (redundância: se o host
                # falhar em uma das substituições, a outra ainda chega; sem nenhuma, o servidor recusa)
                # -I (modo isolado): ignora PYTHONPATH, o site do usuário e o diretório atual; -B: sem .pyc
                "args": ["-I", "-B", "${__dirname}/server/main.py", "--pasta", "${user_config.pasta_base}"],
                "env": {"CAPTURADOR_PASTA_BASE": "${user_config.pasta_base}"},
            },
        },
        "tools": [{"name": n, "description": d} for n, d in FERRAMENTAS],
        "prompts_generated": True,
        "user_config": {
            "pasta_base": {
                "type": "directory",
                "title": "Pasta das evidências",
                "description": "Escolha a pasta que o Claude poderá ler e onde gravará os relatórios. Ele "
                               "só enxerga o que estiver dentro dela. Para o primeiro teste, use uma "
                               "pasta com dados fictícios.",
                "required": True,
                # sem "default" de propósito: um padrão apontando para as evidências reais foi
                # aceito sem querer; a escolha precisa ser explícita
            }
        },
        "compatibility": {
            "platforms": ["win32"],
            # faixa no formato do node-semver (o host é Node): o E é um ESPAÇO; com vírgula a faixa
            # é inválida e o instalador mostra o requisito como não atendido
            "runtimes": {"python": f">={versao_python}.0 <{sys.version_info.major}.{sys.version_info.minor + 1}.0"},
        },
    }


def montar(destino: Path) -> None:
    servidor = destino / "server"
    pacote = servidor / "capturador"
    pacote.mkdir(parents=True)
    for modulo in MODULOS:
        shutil.copy2(RAIZ / "capturador" / f"{modulo}.py", pacote / f"{modulo}.py")
    (servidor / "main.py").write_text(PONTO_DE_ENTRADA, encoding="utf-8")

    print("Instalando as dependências no pacote (pode levar um minuto)...")
    # Só versões travadas com hash (requirements-mcpb.lock) e só pacotes prontos (wheels): nada é
    # compilado nem executado a partir de código-fonte de terceiros, e um pacote adulterado no PyPI
    # não bate com o hash e é recusado. Para atualizar: veja o README (pip-compile --generate-hashes).
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                    "--require-hashes", "--only-binary", ":all:",
                    "--target", str(servidor / "lib"), "-r", str(RAIZ / "requirements-mcpb.lock")],
                   check=True)
    for sobra in list((servidor / "lib").rglob("__pycache__")) + [servidor / "lib" / "bin"]:
        shutil.rmtree(sobra, ignore_errors=True)

    sys.path.insert(0, str(RAIZ / "tools"))
    from gerar_icone import desenhar  # redesenha em alta resolução (o .ico só tem até 256 px)

    desenhar().resize((512, 512), Image.Resampling.LANCZOS).save(destino / "icon.png")
    (destino / "manifest.json").write_text(json.dumps(manifesto(), ensure_ascii=False, indent=2),
                                           encoding="utf-8")


def verificar_importacao(destino: Path) -> None:
    """Importa o servidor a partir do PACOTE, como o host fará (modo isolado, só o que está nele).

    Pega esquecimentos da lista MODULOS (um módulo novo que não entrou no pacote) antes de
    entregar uma extensão que não inicia.
    """
    servidor = destino / "server"
    codigo = ("import site, sys; sys.path[:0] = [sys.argv[1], sys.argv[2]]; site.addsitedir(sys.argv[2]); "
              "import capturador.mcp_servidor")
    resultado = subprocess.run(
        [sys.executable, "-I", "-B", "-c", codigo, str(servidor), str(servidor / "lib")],
        capture_output=True, text=True)
    if resultado.returncode != 0:
        raise SystemExit("O servidor NÃO importa a partir do pacote (provável módulo faltando em MODULOS):\n"
                         + resultado.stderr[-800:])


def compactar(origem: Path, arquivo: Path) -> None:
    arquivo.parent.mkdir(exist_ok=True)
    arquivo.unlink(missing_ok=True)
    with zipfile.ZipFile(arquivo, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for caminho in sorted(origem.rglob("*")):
            if caminho.is_file():
                z.write(caminho, caminho.relative_to(origem).as_posix())


def main() -> int:
    destino = RAIZ / "build" / "mcpb"
    if destino.name != "mcpb" or destino.parent.name != "build":  # só apaga a nossa pasta de build
        raise SystemExit("caminho de build inesperado")
    shutil.rmtree(destino, ignore_errors=True)
    montar(destino)
    verificar_importacao(destino)
    arquivo = RAIZ / "dist" / NOME_ARQUIVO
    compactar(destino, arquivo)
    soma = hashlib.sha256(arquivo.read_bytes()).hexdigest()
    arquivo.with_name(arquivo.name + ".sha256").write_text(f"{soma}  {arquivo.name}\n", encoding="utf-8")
    print(f"Extensão gerada: {arquivo}  ({arquivo.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"SHA-256: {soma}")
    print("Manifesto em build\\mcpb\\manifest.json. Instale dando dois cliques no .mcpb.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
