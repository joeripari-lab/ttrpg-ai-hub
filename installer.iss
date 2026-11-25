#ifndef SourceDir
  #define SourceDir "dist_win\TTRPG_AI_Hub"
#endif

[Setup]
AppId={{8D4F2E1A-9C3B-4B7E-A2D1-6E5F4C3B2A10}
AppName=TTRPG AI Hub
AppVersion=1.0.0
DefaultDirName={localappdata}\Programs\TTRPG_AI_Hub
DefaultGroupName=TTRPG AI Hub
OutputDir=dist
OutputBaseFilename=TTRPG_AI_Hub_Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
CloseApplications=yes
RestartApplications=yes

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\TTRPG AI Hub"; Filename: "{app}\TTRPG_AI_Hub.exe"
Name: "{autodesktop}\TTRPG AI Hub"; Filename: "{app}\TTRPG_AI_Hub.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\TTRPG_AI_Hub.exe"; Description: "Launch TTRPG AI Hub"; Flags: nowait postinstall skipifsilent
