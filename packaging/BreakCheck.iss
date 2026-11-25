; BreakCheck per-user Windows installer (Inno Setup 6).
#ifndef AppVersion
  #error AppVersion must be supplied by build-windows.ps1
#endif
[Setup]
AppId={{A2F54BE4-2BAA-414B-8AE3-1B15F3517D5E}
AppName=BreakCheck
AppVersion={#AppVersion}
AppPublisher=BreakCheck contributors
AppPublisherURL=https://github.com/PCTestAdmin/BreakCheck
AppSupportURL=https://github.com/PCTestAdmin/BreakCheck/issues
AppUpdatesURL=https://github.com/PCTestAdmin/BreakCheck/releases
DefaultDirName={localappdata}\Programs\BreakCheck
DefaultGroupName=BreakCheck
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
UninstallDisplayIcon={app}\BreakCheck.exe
LicenseFile=..\LICENSE
OutputDir=..\release
OutputBaseFilename=BreakCheck-{#AppVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "explorer"; Description: "Add Inspect with BreakCheck to File Explorer"; GroupDescription: "File Explorer integration:"; Flags: unchecked

[Files]
Source: "..\dist\BreakCheck.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\BreakCheckCLI.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\BreakCheck"; Filename: "{app}\BreakCheck.exe"
Name: "{group}\Uninstall BreakCheck"; Filename: "{uninstallexe}"
Name: "{autodesktop}\BreakCheck"; Filename: "{app}\BreakCheck.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Classes\*\shell\BreakCheck.Inspect"; ValueType: string; ValueName: ""; ValueData: "Inspect with BreakCheck"; Flags: uninsdeletekey; Tasks: explorer
Root: HKCU; Subkey: "Software\Classes\*\shell\BreakCheck.Inspect"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\BreakCheck.exe"; Tasks: explorer
Root: HKCU; Subkey: "Software\Classes\*\shell\BreakCheck.Inspect\command"; ValueType: string; ValueName: ""; ValueData: """{app}\BreakCheck.exe"" --inspect=""%1"""; Tasks: explorer
Root: HKCU; Subkey: "Software\Classes\Directory\shell\BreakCheck.Inspect"; ValueType: string; ValueName: ""; ValueData: "Inspect with BreakCheck"; Flags: uninsdeletekey; Tasks: explorer
Root: HKCU; Subkey: "Software\Classes\Directory\shell\BreakCheck.Inspect"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\BreakCheck.exe"; Tasks: explorer
Root: HKCU; Subkey: "Software\Classes\Directory\shell\BreakCheck.Inspect\command"; ValueType: string; ValueName: ""; ValueData: """{app}\BreakCheck.exe"" --inspect=""%1"""; Tasks: explorer

[Run]
Filename: "{app}\BreakCheck.exe"; Description: "Launch BreakCheck"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssInstall) and (not WizardIsTaskSelected('explorer')) then
  begin
    RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Classes\*\shell\BreakCheck.Inspect');
    RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Classes\Directory\shell\BreakCheck.Inspect');
  end;
end;
