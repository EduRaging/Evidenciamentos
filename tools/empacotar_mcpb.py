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
           "mcp_servidor")

PONTO_DE_ENTRADA = '''"""Ponto de entrada da extensão: inicia o servidor MCP do Capturador de Evidências."""
import site
import sys
from pathlib import Path

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
                "args": ["${__dirname}/server/main.py"],
                "env": {"CAPTURADOR_PASTA_BASE": "${user_config.pasta_base}"},
            },
        },
        "tools": [{"name": n, "description": d} for n, d in FERRAMENTAS],
        "prompts_generated": True,
        "user_config": {
            "pasta_base": {
                "type": "directory",
                "title": "Pasta das evidências",
                "description": "A mesma pasta onde o Capturador de Evidências salva os testes "
                               "(Configurações do app). O Claude só enxerga o que estiver dentro dela.",
                "required": True,
                "default": "${DOCUMENTS}/Evidencias",
            }
        },
        "compatibility": {
            "platforms": ["win32"],
            "runtimes": {"python": f">={versao_python},<{sys.version_info.major}.{sys.version_info.minor + 1}"},
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
