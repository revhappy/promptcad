; PromptCAD installer.
;
; Compiled by build\build.ps1, which passes the staging directory and the
; version on the command line:
;
;   ISCC /DAppVersion=2.8.0 /DStageDir=...\dist\stage /O...\dist PromptCAD.iss
;
; The staging tree contains an unmodified FreeCAD install plus our own files
; (PromptCAD.exe, bin\branding.xml, bin\promptcad-*.png, Mod\PromptCAD, legal\).
; This script only packages it - all assembly happens in build.ps1.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#ifndef StageDir
  #error StageDir must be passed with /DStageDir=<path to dist\stage>
#endif

#ifndef CompressionMode
  #define CompressionMode "lzma2/normal"
#endif

#define AppName        "PromptCAD"
#define AppPublisher   "Robb Sharma"
#define AppUrl         "https://github.com/revhappy/GPT4FreeCAD"
#define AppExe         "PromptCAD.exe"

; Must match APP_ID in overlay\promptcad\distro\taskbar.py exactly, and must
; stay stable forever. PromptCAD.exe launches bin\freecad.exe and exits, so the
; window belongs to freecad.exe; without a shared identity on both sides,
; Windows groups that window under FreeCAD and "Pin to taskbar" pins FreeCAD.
; Changing this orphans every pin and jump list a user has already made.
#define AppUserModelID "AlphaIntelLabs.PromptCAD"

[Setup]
; Keep this GUID stable forever: it is how Windows recognises an upgrade
; rather than a second parallel installation.
AppId={{7027B73E-7965-4C1E-9A70-D818A56C6ABD}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}

DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes

; The payload is ~2GB of FreeCAD. Solid compression is what does the heavy
; lifting (the bin\ directory is hundreds of similar DLLs); the preset only
; trades minutes of compile time for a few percent of size. Default to
; normal and let release builds opt into max with build.ps1 -MaxCompression.
Compression={#CompressionMode}
SolidCompression=yes
LZMANumBlockThreads=4

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
PrivilegesRequired=admin

OutputBaseFilename={#AppName}-{#AppVersion}-setup
SetupIconFile={#StageDir}\PromptCAD.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName} {#AppVersion}

WizardStyle=modern
WizardImageFile={#StageDir}\..\..\branding\generated\wizard-large.bmp
WizardSmallImageFile={#StageDir}\..\..\branding\generated\wizard-small.bmp
LicenseFile={#StageDir}\legal\NOTICE.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; \
    GroupDescription: "Shortcuts:"

; Off by default and clearly labelled: a machine may also have FreeCAD
; installed, and silently stealing its file association would be rude.
Name: "associate"; Description: "Open .FCStd files with {#AppName}"; \
    GroupDescription: "File associations:"; Flags: unchecked

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; \
    Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
; AppUserModelID on the launcher shortcuts is half of the taskbar fix - the
; running process claims the same ID from promptcad\distro\taskbar.py. With
; both in place Windows resolves our window to these shortcuts, so pinning
; pins PromptCAD (and its icon) instead of the bundled freecad.exe.
; The licences entry points at a folder, which has no app identity, so it is
; deliberately left off that one.
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; \
    AppUserModelID: "{#AppUserModelID}"
Name: "{group}\{#AppName} licences"; Filename: "{app}\legal"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; \
    AppUserModelID: "{#AppUserModelID}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.FCStd\OpenWithProgids"; \
    ValueType: string; ValueName: "PromptCAD.Document"; ValueData: ""; \
    Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\PromptCAD.Document"; \
    ValueType: string; ValueName: ""; ValueData: "FreeCAD Document"; \
    Flags: uninsdeletekey; Tasks: associate
Root: HKA; Subkey: "Software\Classes\PromptCAD.Document\DefaultIcon"; \
    ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"; \
    Tasks: associate
Root: HKA; Subkey: "Software\Classes\PromptCAD.Document\shell\open\command"; \
    ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; \
    Tasks: associate

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; FreeCAD writes caches and compiled python into its own tree at runtime;
; without this the install directory survives uninstall as a shell of .pyc.
Type: filesandordirs; Name: "{app}\Mod\PromptCAD\__pycache__"
Type: filesandordirs; Name: "{app}\bin\Lib\__pycache__"
Type: dirifempty; Name: "{app}"
