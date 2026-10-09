; Instalador do Capturador de Evidências (Inno Setup 6)
; Compilar:  ISCC /DVersao=0.1.0 installer\Capturador.iss   (o build.bat faz isso)
; Este arquivo precisa ser salvo em UTF-8 com BOM para os acentos saírem certos.

#ifndef Versao
  #define Versao "0.1.0"
#endif
#define NomeApp "Capturador de Evidências"
#define ExeApp "CapturadorEvidencias.exe"

[Setup]
; AppId identifica o app para atualizações e desinstalação; não mude depois de publicar.
AppId={{3BB18892-98D8-4815-A0E8-FB9D74EEEC54}
AppName={#NomeApp}
AppVersion={#Versao}
DefaultDirName={autopf}\Capturador de Evidencias
DefaultGroupName={#NomeApp}
DisableProgramGroupPage=yes
; Instala só para o usuário atual, sem pedir administrador (o usuário pode escolher o contrário).
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; O app cria este mutex; o instalador avisa para fechá-lo antes de atualizar.
AppMutex=CapturadorEvidencias
SetupIconFile=..\assets\icone.ico
UninstallDisplayIcon={app}\{#ExeApp}
UninstallDisplayName={#NomeApp}
OutputDir=..\installer_output
OutputBaseFilename=Setup_CapturadorEvidencias_{#Versao}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar um atalho na Área de Trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked
Name: "iniciarcomowindows"; Description: "Iniciar o Capturador junto com o Windows (para os atalhos de teclado já estarem ativos)"; GroupDescription: "Atalhos:"; Flags: unchecked

[Files]
Source: "..\dist\{#ExeApp}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#NomeApp}"; Filename: "{app}\{#ExeApp}"
Name: "{autodesktop}\{#NomeApp}"; Filename: "{app}\{#ExeApp}"; Tasks: desktopicon
Name: "{userstartup}\{#NomeApp}"; Filename: "{app}\{#ExeApp}"; Tasks: iniciarcomowindows

[Run]
Filename: "{app}\{#ExeApp}"; Description: "Abrir o {#NomeApp}"; Flags: nowait postinstall skipifsilent

; Desinstalar remove o programa, mas mantém as configurações e as pastas de evidências do usuário.
