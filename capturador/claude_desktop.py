"""Abre o Claude desktop numa conversa nova com o prompt já preenchido (link `claude://`).

O Claude só PREENCHE a caixa de texto: quem envia é o usuário, apertando Enter. Nada sai do
computador por aqui. Segundo a ajuda oficial, o texto do link é truncado em cerca de 14 mil
caracteres, então prompts maiores seguem pela área de transferência (quem chama copia o texto).

O link é entregue ao programa que o Windows registrou para `claude://` chamando-o direto (sem
ShellExecute), porque assim não há o limite de ~2 mil caracteres de URL do ShellExecute: o prompt
completo tem alguns milhares de caracteres.
"""
from __future__ import annotations

import ctypes
import subprocess
from pathlib import Path
from urllib.parse import quote

LINK_NOVA_CONVERSA = "claude://claude.ai/new"
LIMITE_PROMPT = 12_000  # o Claude trunca em ~14 mil; a margem evita cortar o fim do prompt
LIMITE_LINHA_DE_COMANDO = 30_000  # o Windows aceita 32.767 caracteres numa linha de comando
ESPERA_DE_FALHA = 2.0  # segundos esperando o processo sair com erro antes de dar o envio por feito

PREENCHIDO = "preenchido"  # a conversa abriu com o prompt na caixa de texto
VAZIA = "vazia"  # a conversa abriu sem texto (prompt grande demais): cole da área de transferência
INDISPONIVEL = "indisponivel"  # não achou o Claude desktop ou não conseguiu abri-lo


def montar_link(prompt: str | None = None) -> str:
    """Link de nova conversa; com `prompt`, ele vai codificado no parâmetro q."""
    if not prompt:
        return LINK_NOVA_CONVERSA
    return f"{LINK_NOVA_CONVERSA}?q={quote(prompt, safe='')}"


def _linha_registrada() -> str | None:
    """Comando que o Windows associou ao protocolo claude:// (ex.: '"C:\\...\\claude.exe" "%1"')."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"claude\shell\open\command") as chave:
            return winreg.QueryValueEx(chave, "")[0]
    except (ImportError, OSError):
        return None


def _dividir(linha: str) -> list[str]:
    """Divide a linha de comando como o Windows faz (CommandLineToArgvW)."""
    quantidade = ctypes.c_int()
    shell32, kernel32 = ctypes.windll.shell32, ctypes.windll.kernel32
    shell32.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
    shell32.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    argv = shell32.CommandLineToArgvW(linha, ctypes.byref(quantidade))
    if not argv:
        return []
    try:
        return [argv[i] for i in range(quantidade.value)]
    finally:
        kernel32.LocalFree(ctypes.cast(argv, ctypes.c_void_p))


def _lancador_atual(exe: Path) -> Path:
    """Troca o claude.exe de uma pasta de versão pelo lançador da pasta-mãe, quando existir.

    O registro do Windows costuma apontar para uma pasta de versão (…\\app-2.31226.1\\claude.exe)
    que as atualizações deixam velha ou pela metade: ela abre e fecha na hora (visto aqui, com a
    pasta sem o icudtl.dat). O claude.exe da pasta-mãe é o lançador do instalador (Squirrel), que
    sempre abre a versão atual repassando os argumentos.
    """
    if exe.parent.name.lower().startswith("app-"):
        lancador = exe.parent.parent / exe.name
        if lancador.is_file():
            return lancador
    return exe


def comando_para_abrir(link: str, linha_registrada: str | None = None,
                       nome_exe: str = "claude.exe") -> list[str] | None:
    """Monta [executável, ...argumentos] que abre `link`, ou None se não achar o Claude desktop.

    Só aceita o programa registrado se for mesmo o `claude.exe` e existir: um registro apontando
    para outra coisa é tratado como "Claude não encontrado", nunca executado.
    """
    linha = _linha_registrada() if linha_registrada is None else linha_registrada
    if not linha:
        return None
    partes = _dividir(linha)
    if not partes or Path(partes[0]).name.lower() != nome_exe.lower() or not Path(partes[0]).is_file():
        return None
    if not any("%1" in p for p in partes[1:]):
        return None  # formato desconhecido: sem onde colocar o link
    comando = [str(_lancador_atual(Path(partes[0])))] + [p.replace("%1", link) for p in partes[1:]]
    if sum(len(p) + 1 for p in comando) > LIMITE_LINHA_DE_COMANDO:
        return None
    return comando


def abrir_conversa(prompt: str | None = None, *, linha_registrada: str | None = None,
                   nome_exe: str = "claude.exe", iniciar=subprocess.Popen) -> str:
    """Abre o Claude desktop numa conversa nova. Devolve PREENCHIDO, VAZIA ou INDISPONIVEL.

    `prompt` vazio/None abre a conversa em branco (PREENCHIDO só quando o texto foi no link).
    Prompt grande demais abre a conversa em branco e devolve VAZIA, para o chamador copiá-lo.
    """
    texto = prompt if prompt and len(prompt) <= LIMITE_PROMPT else None
    comando = comando_para_abrir(montar_link(texto), linha_registrada, nome_exe)
    if comando is None and texto:  # o link com texto ficou grande demais para a linha de comando
        texto = None
        comando = comando_para_abrir(montar_link(), linha_registrada, nome_exe)
    if comando is None:
        return INDISPONIVEL
    try:
        processo = iniciar(comando, close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,
                           creationflags=0x00000008 | 0x00000200)  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    except OSError:
        return INDISPONIVEL
    # Quem entrega o link a um Claude já aberto sai com código 0 (e quem inicia um novo segue rodando).
    # Sair logo com erro é falha de verdade (ex.: versão quebrada): avisar, em vez de "não aconteceu nada".
    try:
        codigo = processo.wait(timeout=ESPERA_DE_FALHA) if processo is not None else 0
    except subprocess.TimeoutExpired:
        codigo = 0  # continua rodando: o Claude está iniciando
    if codigo != 0:
        return INDISPONIVEL
    return PREENCHIDO if texto else VAZIA
