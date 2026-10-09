# -*- mode: python ; coding: utf-8 -*-
# Build:  pyinstaller --noconfirm Capturador.spec   (ou rode build.bat)
import sys

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
)

sys.path.insert(0, SPECPATH)
from capturador import __version__  # noqa: E402

_partes = [int(p) for p in __version__.split(".")]
_tupla = tuple((_partes + [0, 0, 0, 0])[:4])

versao = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_tupla, prodvers=_tupla, mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0),
    kids=[
        StringFileInfo([StringTable("041604B0", [  # pt-BR, Unicode
            StringStruct("FileDescription", "Capturador de Evidências"),
            StringStruct("FileVersion", __version__),
            StringStruct("InternalName", "CapturadorEvidencias"),
            StringStruct("OriginalFilename", "CapturadorEvidencias.exe"),
            StringStruct("ProductName", "Capturador de Evidências"),
            StringStruct("ProductVersion", __version__),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0416, 1200])]),
    ],
)

a = Analysis(
    ["main.py"],
    pathex=[SPECPATH],
    datas=[("assets/icone.ico", "assets")],
    excludes=["numpy", "matplotlib", "scipy", "pandas", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="CapturadorEvidencias",
    console=False,  # app de janela: sem terminal aberto
    icon="assets/icone.ico",
    version=versao,
    upx=False,  # UPX aumenta falsos positivos de antivírus
)
