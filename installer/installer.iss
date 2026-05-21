; Inno Setup script for tango-note. Saved as UTF-8 WITH BOM so the
; Japanese strings below are read correctly by the compiler.

[Setup]
AppName=Tango Note
AppVersion=1.0.0
AppPublisher=TODO: Your Name
; Fixed AppId (generated once with uuid.uuid4) so upgrades are
; recognized as the same application.
AppId={{839E0FDC-3311-48B7-9A7E-D8AB1B8ABCFD}
DefaultDirName={autopf}\Tango Note
DefaultGroupName=Tango Note
OutputDir=..\dist
OutputBaseFilename=tango-note-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
UninstallDisplayIcon={app}\tango-note.exe
SetupIconFile=tango-note.ico

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\tango-note.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Tango Note"; Filename: "{app}\tango-note.exe"
Name: "{group}\{cm:UninstallProgram,Tango Note}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\Tango Note"; Filename: "{app}\tango-note.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Run]
Filename: "{app}\tango-note.exe"; Description: "Tango Note を起動する"; Flags: nowait postinstall skipifsilent
