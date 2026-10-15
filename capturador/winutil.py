"""Pequenos recursos do Windows usados pela interface."""
from __future__ import annotations

import ctypes
import struct
import subprocess
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int,
                              ctypes.c_int, wintypes.UINT]
user32.LoadImageW.restype = wintypes.HANDLE
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = ctypes.c_void_p
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.restype = wintypes.BOOL
user32.CloseClipboard.restype = wintypes.BOOL
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
user32.RegisterClipboardFormatW.restype = wintypes.UINT
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE

CF_HDROP = 15
GMEM_MOVEABLE, GMEM_ZEROINIT = 0x0002, 0x0040
DROPEFFECT_COPY = 1

IMAGE_ICON, LR_LOADFROMFILE = 1, 0x10
WM_SETICON, ICON_SMALL, ICON_BIG = 0x80, 0, 1
SM_CXICON, SM_CYICON, SM_CXSMICON, SM_CYSMICON = 11, 12, 49, 50
GA_ROOT = 2
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WDA_EXCLUDEFROMCAPTURE = 0x11  # Windows 10 2004+
ERROR_ALREADY_EXISTS = 183

_mutex = None  # mantém o handle vivo enquanto o processo existir


def _hwnd(janela) -> int:
    janela.update_idletasks()
    return user32.GetAncestor(janela.winfo_id(), GA_ROOT)


def excluir_da_captura(janela) -> bool:
    """Faz a janela do app não aparecer nos prints (a tela por baixo é capturada)."""
    return bool(user32.SetWindowDisplayAffinity(_hwnd(janela), WDA_EXCLUDEFROMCAPTURE))


def definir_icone(janela, caminho) -> bool:
    """Declara o ícone (grande e pequeno) da janela ao Windows.

    O `iconbitmap` do Tk só define o ícone da classe; a barra de tarefas pergunta à janela
    (WM_GETICON) e, sem resposta, mostra o ícone do pythonw.exe em vez do nosso.
    """
    hwnd = _hwnd(janela)
    grande = user32.LoadImageW(None, str(caminho), IMAGE_ICON, user32.GetSystemMetrics(SM_CXICON),
                               user32.GetSystemMetrics(SM_CYICON), LR_LOADFROMFILE)
    pequeno = user32.LoadImageW(None, str(caminho), IMAGE_ICON, user32.GetSystemMetrics(SM_CXSMICON),
                                user32.GetSystemMetrics(SM_CYSMICON), LR_LOADFROMFILE)
    if grande:
        user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, grande)
    if pequeno:
        user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, pequeno)
    return bool(grande or pequeno)


def nao_ativar(janela) -> None:
    """Janela que aparece sem roubar o foco (não fecha menus abertos no sistema testado)."""
    hwnd = _hwnd(janela)
    estilo = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, estilo | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)


def definir_identidade_do_app(identidade: str = "EduRaging.CapturadorEvidencias") -> bool:
    """Dá ao processo uma identidade própria na barra de tarefas (AppUserModelID).

    Sem isso o Windows agrupa o app sob o pythonw.exe e mostra o ícone do Python no lugar do
    nosso. Deve ser chamada antes de criar a primeira janela.
    """
    shell32 = ctypes.WinDLL("shell32")
    shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [wintypes.LPCWSTR]
    shell32.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long  # HRESULT
    return shell32.SetCurrentProcessExplicitAppUserModelID(identidade) == 0


def montar_dropfiles(caminhos) -> bytes:
    """Estrutura DROPFILES (formato CF_HDROP): é o que o Explorador, o Outlook e o Teams entendem
    como "arquivos copiados". Cabeçalho de 20 bytes + caminhos em UTF-16 terminados por NUL duplo."""
    texto = "\0".join(str(c) for c in caminhos) + "\0\0"
    cabecalho = struct.pack("<IiiII", 20, 0, 0, 0, 1)  # pFiles, ponto (0,0), fNC, fWide
    return cabecalho + texto.encode("utf-16-le")


def _colocar_na_area_de_transferencia(formato: int, dados: bytes) -> None:
    memoria = kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, len(dados))
    if not memoria:
        raise OSError("Sem memória para copiar o arquivo.")
    ponteiro = kernel32.GlobalLock(memoria)
    ctypes.memmove(ponteiro, dados, len(dados))
    kernel32.GlobalUnlock(memoria)
    if not user32.SetClipboardData(formato, memoria):
        kernel32.GlobalFree(memoria)
        raise OSError("O Windows recusou o conteúdo da área de transferência.")


def copiar_arquivos_para_area_de_transferencia(caminhos) -> None:
    """Copia ARQUIVOS (não texto) para a área de transferência: dá para colar (Ctrl+V) num e-mail,
    no Teams ou numa pasta. O conteúdo fica com o Windows e sobrevive ao fechamento do app."""
    for _ in range(20):  # outro programa pode estar com a área de transferência aberta por instantes
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        raise OSError("A área de transferência está ocupada por outro programa; tente de novo.")
    try:
        user32.EmptyClipboard()
        _colocar_na_area_de_transferencia(CF_HDROP, montar_dropfiles(caminhos))
        efeito = user32.RegisterClipboardFormatW("Preferred DropEffect")
        if efeito:
            _colocar_na_area_de_transferencia(efeito, struct.pack("<I", DROPEFFECT_COPY))  # copiar, não mover
    finally:
        user32.CloseClipboard()


def revelar_no_explorador(caminho) -> None:
    """Abre o Explorador de Arquivos com o arquivo selecionado."""
    subprocess.Popen(f'explorer.exe /select,"{caminho}"')


def instancia_unica() -> bool:
    """True se esta é a única instância do app em execução."""
    global _mutex
    _mutex = kernel32.CreateMutexW(None, False, "Local\\CapturadorEvidencias")
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS
