; Pixels Toolkit Installer Script
; Styled to match application aesthetic

#define AppName "Pixels Toolkit"
#define AppVersion "1.0.0"
#define AppPublisher "Seveneves"
#define AppURL "https://seveneves.ai/pixels"
#define AppExeName "Pixels.exe"

[Setup]
; Basic app info
AppId={{A7B2C3D4-E5F6-4A7B-8C9D-0E1F2A3B4C5D}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}

; Installation directories
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes

; Output settings
OutputDir=installer_output
OutputBaseFilename=PixelsToolkit-v{#AppVersion}-Setup
SetupIconFile=assets\icon.ico

; Compression (best available)
Compression=lzma2/max
SolidCompression=yes

; Visual style - modern flat design matching your app
WizardStyle=modern
WizardSizePercent=100,100

; CHANGE THIS - Require admin for Program Files installation
PrivilegesRequired=admin
; REMOVE THIS LINE:
; PrivilegesRequiredOverridesAllowed=dialog

; Architecture
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

[Files]
Source: "dist\Pixels\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\Pixels\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; NOTE: Don't use "Flags: ignoreversion" on any shared system files

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: quicklaunchicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// Custom welcome page text
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpWelcome then
  begin
    WizardForm.WelcomeLabel2.Caption := 
      'This will install {#AppName} on your computer.' + #13#10#13#10 +
      'Professional pixel art processing toolkit featuring:' + #13#10 +
      '  • AI image downscaling' + #13#10 +
      '  • Batch post-processing' + #13#10 +
      '  • Sprite sheet packing' + #13#10#13#10 +
      'Click Next to continue, or Cancel to exit Setup.';
  end;
end;