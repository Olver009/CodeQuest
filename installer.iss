; Script generated with Inno Setup 6 — сборка установщика CodeQuest.
; Не запускайте его напрямую: используйте build.py (он передаёт номер версии).
; Либо вручную: ISCC.exe installer.iss /DAppVersion=1.0.0
; Перед сборкой должен быть собран dist\CodeQuest (python -m PyInstaller CodeQuest.spec).

; Номер версии приходит из build.py (он читает version.ini). Значение ниже —
; только на случай ручного запуска ISCC без параметра.
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#define MyAppName "CodeQuest"
#define MyAppPublisher "Olver009"
#define MyAppURL "https://github.com/Olver009/CodeQuest"
#define MyAppExeName "CodeQuest.exe"

[Setup]
AppId={{8F3C1D6E-9B4A-4F27-9E51-2C7D84A0B315}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppVerName={#MyAppName} {#AppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=LICENSE
OutputDir=release
#ifdef CoreOnly
  OutputBaseFilename=CodeQuest-Setup-Core-{#AppVersion}
#else
  OutputBaseFilename=CodeQuest-Setup-Full-{#AppVersion}
#endif
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
; Установка в профиль без прав администратора: скачал, запустил, поставилось.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DisableWelcomePage=no
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no


[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Весь бандл PyInstaller (onedir): CodeQuest.exe + _internal\ с портативным Python, уроками и интерфейсом.
Source: "dist\CodeQuest\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#ifndef CoreOnly
Source: "dist\CodeQuest\_internal\runtime\*"; DestDir: "{app}\_internal\runtime"; Flags: recursesubdirs
#endif

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
// WebView2 обязателен: на его движке pywebview рисует окно. В Windows 10/11 он
// обычно уже есть, но на свежих сборках Windows 10 его может не быть.
function WebView2Installed: Boolean;
var
  Version: String;
begin
  Result :=
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) or
    RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) or
    RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version);
  Result := Result and (Version <> '') and (Version <> '0.0.0.0');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and not WebView2Installed then
    MsgBox('Для работы CodeQuest нужен Microsoft Edge WebView2 Runtime — похоже, что он не установлен.' + #13#10 +
           'Скачайте и установите его по ссылке на странице Microsoft, затем перезапустите CodeQuest.' + #13#10 + #13#10 +
           'https://developer.microsoft.com/microsoft-edge/webview2/',
           mbInformation, MB_OK);
end;

// Прогресс и настройки живут рядом с exe и не входят в список установленных файлов.
// Спрашиваем при удалении, стирать их или оставить, чтобы не потерять пройденные уроки.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Saved: TArrayOfString;
  I: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if MsgBox('Удалить также ваш прогресс и настройки (progress.json)?' + #13#10 +
              'Если оставить — при следующей установке прогресс продолжится.',
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      SetArrayLength(Saved, 3);
      Saved[0] := ExpandConstant('{app}\progress.json');
      Saved[1] := ExpandConstant('{app}\codequest_backup.json');
      Saved[2] := ExpandConstant('{app}\user.json');
      for I := 0 to GetArrayLength(Saved) - 1 do
        if FileExists(Saved[I]) then
          DeleteFile(Saved[I]);
    end;
  end;
end;
