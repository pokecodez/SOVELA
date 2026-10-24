; Sovela Windows installer - Inno Setup 6
; Keep AppId unchanged in later versions so upgrades install over the same app.
#define MyAppName "Sovela"
#define MyAppVersion "3.1.0"
#define MyAppExeName "Sovela.exe"

[Setup]
AppId={{31A0CDB0-D029-4BF7-B227-CDA0227EB250}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName=Sovela {#MyAppVersion}
AppPublisher=Sovela PC Care
AppPublisherURL=https://github.com/pokecodez/SOVELA
AppSupportURL=https://github.com/pokecodez/SOVELA/issues
AppUpdatesURL=https://github.com/pokecodez/SOVELA/releases
DefaultDirName={localappdata}\Programs\Sovela
DefaultGroupName=Sovela
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
MinVersion=10.0
OutputDir=installer-output
OutputBaseFilename=SovelaSetup-v{#MyAppVersion}
SetupIconFile=sovela.ico
UninstallDisplayIcon={app}\Sovela.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "dist\Sovela\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Sovela"; Filename: "{app}\Sovela.exe"
Name: "{autodesktop}\Sovela"; Filename: "{app}\Sovela.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Sovela.exe"; Description: "Launch Sovela"; Flags: nowait postinstall skipifsilent
