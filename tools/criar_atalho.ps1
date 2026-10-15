# Cria o atalho "Capturador de Evidências" (com o ícone do app) para abrir o programa
# sem janela de console.
# Uso:  powershell -File tools\criar_atalho.ps1                 (cria na pasta do projeto)
#       powershell -File tools\criar_atalho.ps1 -AreaDeTrabalho (cria na Área de Trabalho)
# Este arquivo precisa ficar salvo em UTF-8 com BOM para os acentos saírem certos.
param([switch]$AreaDeTrabalho)

# Mesma identidade que capturador\winutil.py define no programa: com ela igual no atalho e na
# janela, a barra de tarefas junta o atalho fixado e o app aberto num botão só.
$identidade = "EduRaging.CapturadorEvidencias"

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;

public static class IdentidadeDoAtalho {
    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    struct PROPERTYKEY { public Guid fmtid; public uint pid; }

    [StructLayout(LayoutKind.Explicit, Size = 24)]
    struct PROPVARIANT {
        [FieldOffset(0)] public ushort vt;
        [FieldOffset(8)] public IntPtr texto;
    }

    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPropertyStore {
        int GetCount(out uint cProps);
        int GetAt(uint iProp, out PROPERTYKEY pkey);
        int GetValue(ref PROPERTYKEY key, out PROPVARIANT pv);
        int SetValue(ref PROPERTYKEY key, ref PROPVARIANT pv);
        int Commit();
    }

    [DllImport("ole32.dll")]
    static extern int PropVariantClear(ref PROPVARIANT pv);

    static PROPERTYKEY ChaveId() {
        // System.AppUserModel.ID
        return new PROPERTYKEY { fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), pid = 5 };
    }

    public static void Definir(string caminho, string identidade) {
        object link = Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("00021401-0000-0000-C000-000000000046")));
        try {
            ((IPersistFile)link).Load(caminho, 2);
            var chave = ChaveId();
            var valor = new PROPVARIANT { vt = 31, texto = Marshal.StringToCoTaskMemUni(identidade) };
            try {
                Marshal.ThrowExceptionForHR(((IPropertyStore)link).SetValue(ref chave, ref valor));
                Marshal.ThrowExceptionForHR(((IPropertyStore)link).Commit());
            } finally { PropVariantClear(ref valor); }
            ((IPersistFile)link).Save(caminho, true);
        } finally { Marshal.ReleaseComObject(link); }
    }

    public static string Ler(string caminho) {
        object link = Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("00021401-0000-0000-C000-000000000046")));
        try {
            ((IPersistFile)link).Load(caminho, 0);
            var chave = ChaveId();
            PROPVARIANT valor;
            Marshal.ThrowExceptionForHR(((IPropertyStore)link).GetValue(ref chave, out valor));
            string texto = valor.vt == 31 ? Marshal.PtrToStringUni(valor.texto) : null;
            PropVariantClear(ref valor);
            return texto;
        } finally { Marshal.ReleaseComObject(link); }
    }
}
'@

$raiz = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $raiz ".venv\Scripts\pythonw.exe"
$exe = Join-Path $raiz "dist\CapturadorEvidencias.exe"
$icone = Join-Path $raiz "assets\icone.ico"

$pasta = if ($AreaDeTrabalho) { [Environment]::GetFolderPath("Desktop") } else { $raiz }
$caminho = Join-Path $pasta "Capturador de Evidências.lnk"

$atalho = (New-Object -ComObject WScript.Shell).CreateShortcut($caminho)
if (Test-Path $pythonw) {
    $atalho.TargetPath = $pythonw
    $atalho.Arguments = '"' + (Join-Path $raiz "main.py") + '"'
} elseif (Test-Path $exe) {
    $atalho.TargetPath = $exe
} else {
    Write-Error "Nao encontrei o ambiente (.venv) nem o executavel. Rode o Iniciar.bat ou o build.bat primeiro."
    exit 1
}
$atalho.WorkingDirectory = $raiz
$atalho.IconLocation = "$icone,0"
$atalho.Description = "Capturador de Evidências"
$atalho.Save()

try {
    [IdentidadeDoAtalho]::Definir($caminho, $identidade)
} catch {
    Write-Warning "Atalho criado, mas sem a identidade da barra de tarefas (o botao fixado pode aparecer separado do app aberto): $($_.Exception.Message)"
}
Write-Host "Atalho criado: $caminho"
