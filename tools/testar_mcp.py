"""Testa o servidor MCP de forma isolada, sem tocar em nada seu.

Uso (com um Python que tenha o pacote mcp: pip install -r requirements-mcp.txt):

    python tools\\testar_mcp.py
        Autoteste: cria um teste FICTÍCIO numa pasta temporária, sobe o servidor por stdio e
        conversa com ele pelo protocolo MCP, como faria o Claude. Não usa IA, não lê suas
        evidências nem sua configuração, e apaga tudo no fim.

    python tools\\testar_mcp.py --criar-exemplo "C:\\caminho\\Evidencias_TESTE"
        Só cria um teste fictício (3 telas de um cadastro de exemplo) nessa pasta, para você
        apontar o servidor para ela ao testar com o Claude de verdade.

    python tools\\testar_mcp.py --bundle "C:\\pasta\\com\\a\\extensao\\descompactada"
        Testa a EXTENSÃO .mcpb como o Claude desktop a executaria: usa o Python do sistema (sem o
        pacote mcp instalado) e as dependências embutidas no pacote.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import io
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from capturador.sessao import Sessao  # noqa: E402


def _fonte(tamanho: int):
    for nome in ("segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(nome, tamanho)
        except OSError:
            continue
    return ImageFont.load_default()


def _tela_cadastro() -> Image.Image:
    img = Image.new("RGB", (1280, 720), (240, 243, 247))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 1280, 64), fill=(30, 64, 120))
    d.text((24, 16), "Sistema de Exemplo  >  Clientes  >  Novo cliente (PJ)", fill="white", font=_fonte(26))
    campos = [("CNPJ", "11.222.333/0001-81"), ("Razão social", "Empresa Exemplo Ltda"),
              ("E-mail", "contato@exemplo.com.br"), ("Limite de crédito (R$)", "5.000,00"),
              ("Status", "Ativo")]
    y = 110
    for rotulo, valor in campos:
        d.text((80, y), rotulo, fill=(60, 60, 60), font=_fonte(20))
        d.rectangle((80, y + 30, 700, y + 76), fill="white", outline=(170, 170, 170))
        d.text((92, y + 38), valor, fill=(20, 20, 20), font=_fonte(22))
        y += 100
    d.text((740, 270), "Faixa permitida: R$ 100,00 a R$ 50.000,00", fill=(120, 120, 120), font=_fonte(18))
    d.rectangle((80, 620, 260, 680), fill=(30, 130, 80))
    d.text((120, 636), "Salvar", fill="white", font=_fonte(24))
    return img


def _recorte_sucesso() -> Image.Image:
    img = Image.new("RGB", (620, 130), (226, 245, 233))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 619, 129), outline=(30, 130, 80), width=3)
    d.text((24, 42), "Cliente salvo com sucesso.", fill=(20, 90, 50), font=_fonte(30))
    return img


def _tela_listagem() -> Image.Image:
    img = Image.new("RGB", (1280, 520), (240, 243, 247))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 1280, 64), fill=(30, 64, 120))
    d.text((24, 16), "Sistema de Exemplo  >  Clientes", fill="white", font=_fonte(26))
    cabecalho = ["CNPJ", "Razão social", "Limite (R$)", "Status"]
    xs = [60, 340, 720, 960]
    for x, texto in zip(xs, cabecalho):
        d.text((x, 100), texto, fill=(30, 64, 120), font=_fonte(22))
    d.line((40, 140, 1240, 140), fill=(160, 160, 160), width=2)
    linhas = [["11.222.333/0001-81", "Empresa Exemplo Ltda", "5.000,00", "Ativo"],
              ["55.666.777/0001-90", "Comércio Modelo S.A.", "12.000,00", "Ativo"],
              ["99.888.777/0001-60", "Serviços Teste ME", "800,00", "Inativo"]]
    for i, linha in enumerate(linhas):
        for x, texto in zip(xs, linha):
            d.text((x, 160 + i * 60), texto, fill=(30, 30, 30), font=_fonte(21))
    return img


def criar_exemplo(base: Path, config: Path) -> Path:
    """Cria um teste fictício finalizado em `base` e devolve a pasta dele."""
    os.environ["CAPTURADOR_CONFIG_DIR"] = str(config)  # nada da sua configuração real é tocado
    sessao = Sessao(config / "em_andamento")
    sessao.adicionar(_tela_cadastro(), "tela")
    sessao.adicionar(_recorte_sucesso(), "recorte")
    sessao.adicionar(_tela_listagem(), "tela")
    return sessao.finalizar("Cadastro de cliente PJ (exemplo)", "Equipe QA", base)


async def _autoteste(base: Path, nome: str, bundle: Path | None = None) -> list[bool]:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError:
        sys.exit("Pacote mcp não instalado. Rode: pip install -r requirements-mcp.txt")

    resultados: list[bool] = []

    def confere(descricao: str, condicao: bool) -> None:
        resultados.append(bool(condicao))
        print(("  OK     " if condicao else "  FALHA  ") + descricao)

    ambiente = {**os.environ, "CAPTURADOR_PASTA_BASE": str(base)}
    if bundle:
        # como o host executa a extensão: Python do sistema, sem o mcp instalado nele
        sistema = Path(sys.base_prefix) / "python.exe"
        verificacao = subprocess.run([str(sistema), "-c", "import mcp"], capture_output=True)
        print(f"  (o Python do sistema {'NÃO tem' if verificacao.returncode else 'TEM'} o pacote mcp instalado)")
        params = StdioServerParameters(command=str(sistema), args=[str(bundle / "server" / "main.py")],
                                       cwd=str(bundle), env=ambiente)
    else:
        params = StdioServerParameters(command=sys.executable, args=[str(RAIZ / "servidor_mcp.py")],
                                       cwd=str(RAIZ), env=ambiente)
    async with stdio_client(params) as (leitura, escrita):
        async with ClientSession(leitura, escrita) as mcp:
            init = await mcp.initialize()
            confere("handshake: o servidor se apresenta", init.server_info.name == "capturador-evidencias")
            ferramentas = {t.name: t for t in (await mcp.list_tools()).tools}
            confere("4 ferramentas expostas", sorted(ferramentas) == [
                "listar_testes", "obter_teste", "salvar_relatorio_pdf", "ver_evidencia"])
            confere("leituras são somente leitura; a escrita não é destrutiva",
                    all(ferramentas[n].annotations.read_only_hint for n in
                        ("listar_testes", "obter_teste", "ver_evidencia"))
                    and ferramentas["salvar_relatorio_pdf"].annotations.destructive_hint is False)
            confere("prompt analisar_teste exposto",
                    [p.name for p in (await mcp.list_prompts()).prompts] == ["analisar_teste"])

            r = await mcp.call_tool("listar_testes", {})
            confere("listar_testes acha o teste de exemplo", not r.is_error and nome in str(r.content))
            r = await mcp.call_tool("ver_evidencia", {"teste": nome, "numero": 1})
            imagens = [c for c in r.content if c.type == "image"]
            confere("ver_evidencia devolve a imagem", not r.is_error and len(imagens) == 1)
            if imagens:
                confere("a imagem chega íntegra",
                        Image.open(io.BytesIO(base64.b64decode(imagens[0].data))).format == "PNG")

            for entrada in ("..", "C:\\Windows", "a/b"):
                r = await mcp.call_tool("obter_teste", {"teste": entrada})
                confere(f"recusa sair da pasta de evidências (teste={entrada!r})", r.is_error is True)

            r = await mcp.call_tool("salvar_relatorio_pdf", {
                "teste": nome, "titulo": "Relatório de autoteste",
                "conteudo_markdown": "# Resumo\n\nTeste **ok**.\n\n| ID | Status |\n|---|---|\n| CT-01 | Aprovado |\n"})
            confere("salvar_relatorio_pdf gera o PDF na pasta do teste", not r.is_error
                    and (base / nome / "Relatório de autoteste.pdf").is_file())

            p = await mcp.get_prompt("analisar_teste", {"teste": nome, "objetivo": "Validar o cadastro"})
            texto = p.messages[0].content.text
            confere("o prompt traz instruções e sugestões ISTQB/BSTQB",
                    "`ver_evidencia`" in texto and "Partição de equivalência" in texto)
    return resultados


def main() -> int:
    parser = argparse.ArgumentParser(description="Testa o servidor MCP de forma isolada.")
    parser.add_argument("--criar-exemplo", metavar="PASTA",
                        help="só cria um teste fictício nessa pasta (para testar com o Claude de verdade)")
    parser.add_argument("--bundle", metavar="PASTA",
                        help="testa a extensão .mcpb descompactada nessa pasta, em vez do código-fonte")
    args = parser.parse_args()

    if args.criar_exemplo:
        base = Path(args.criar_exemplo)
        config = Path(tempfile.mkdtemp(prefix="capt_exemplo_cfg_"))
        try:
            pasta = criar_exemplo(base, config)
        finally:
            shutil.rmtree(config, ignore_errors=True)
        print(f"Teste de exemplo criado em: {pasta}")
        print(f'Aponte o servidor para a pasta base: CAPTURADOR_PASTA_BASE="{base}"')
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="capt_mcp_autoteste_"))
    try:
        base = tmp / "base"
        nome = criar_exemplo(base, tmp / "cfg").name
        print("Autoteste do servidor MCP (pasta temporária, sem IA e sem tocar nos seus dados):")
        resultados = asyncio.run(_autoteste(base, nome, Path(args.bundle) if args.bundle else None))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{sum(resultados)}/{len(resultados)} verificações OK")
    return 0 if all(resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
