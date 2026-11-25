[Setup]
AppName=TTRPG AI Hub
AppVersion=1.0.0
DefaultDirName={localappdata}\Programs\TTRPG_AI_Hub
DefaultGroupName=TTRPG AI Hub
OutputDir=dist
OutputBaseFilename=TTRPG_AI_Hub_Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest

[Files]
Source: "dist_win\TTRPG_AI_Hub\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\TTRPG AI Hub"; Filename: "{app}\TTRPG_AI_Hub.exe"
Name: "{autodesktop}\TTRPG AI Hub"; Filename: "{app}\TTRPG_AI_Hub.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\TTRPG_AI_Hub.exe"; Description: "Launch TTRPG AI Hub"; Flags: nowait postinstall skipifsilent
