#ifndef MyAppVersion
  #define MyAppVersion "1.0.18"
#endif
#ifndef MySourceDir
  #define MySourceDir "dist\YouTube Downloader Pro"
#endif
#ifndef MyOutputDir
  #define MyOutputDir "dist"
#endif

[Setup]
AppId={{7D8F7C63-842D-4D57-8A9E-63F3E6576013}
AppName=YouTube Downloader Pro
AppVersion={#MyAppVersion}
AppPublisher=DC Team
DefaultDirName={localappdata}\Programs\YouTube Downloader Pro
UsePreviousAppDir=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#MyOutputDir}
OutputBaseFilename=YouTubeDownloaderPro-Setup-v{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
CloseApplicationsFilter=YouTube Downloader Pro.exe,UpdaterLauncher.exe,UpdaterWorker-*.exe
Uninstallable=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "data\downloader_settings*.json,data\download_history.json,data\token*.json,data\credentials.json,data\proxy_settings.json,data\cookies.txt,data\browser\*,cookies.txt,youtube_cookies.txt,yt-dlp\*"
Source: "{#MySourceDir}\yt-dlp\*"; DestDir: "{app}\yt-dlp"; Flags: ignoreversion recursesubdirs createallsubdirs onlyifdoesntexist; Check: DirExists(ExpandConstant('{#MySourceDir}\yt-dlp'))

[Icons]
Name: "{autoprograms}\YouTube Downloader Pro"; Filename: "{app}\YouTube Downloader Pro.exe"
Name: "{autodesktop}\YouTube Downloader Pro"; Filename: "{app}\YouTube Downloader Pro.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\YouTube Downloader Pro.exe"; Description: "Launch YouTube Downloader Pro"; Flags: nowait postinstall skipifsilent
