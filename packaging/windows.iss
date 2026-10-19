#ifndef Payload
  #error "Defina /DPayload=caminho do pacote auditado"
#endif
#ifndef Output
  #error "Defina /DOutput=caminho de saída"
#endif
[Setup]
AppId=org.khcom.ptbr.experimental
AppName=KHCoM PT-BR Experimental
AppVersion=0.1.0
DefaultDirName={localappdata}\Programs\KHCoM PT-BR
DefaultGroupName=KHCoM PT-BR
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#Output}
OutputBaseFilename=KHCoM-PTBR-windows-x64-setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\khcom-desktop.exe
CloseApplications=yes
RestartApplications=no
[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
[Files]
Source: "{#Payload}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\KHCoM PT-BR"; Filename: "{app}\khcom-desktop.exe"
[Run]
Filename: "{app}\khcom-desktop.exe"; Description: "Abrir KHCoM PT-BR"; Flags: nowait postinstall skipifsilent
; Nenhum UninstallDelete: dados em SDL_GetPrefPath ficam fora da instalação.
