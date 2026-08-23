; enigma_setup.iss — Скрипт установочника Bloodloom с лог-зоной (стиль Xatab)

#ifndef AppVersion
  #define AppVersion "0.0.0.0"
#endif

[Dirs]
Name: "{app}\backend\logs"; Flags: uninsneveruninstall

[Setup]
AppName=Bloodloom
AppVersion={#AppVersion}
AppPublisher=Bloodloom Team
DefaultDirName={localappdata}\Programs\Bloodloom
DefaultGroupName=Bloodloom
DisableProgramGroupPage=yes
OutputDir=build
OutputBaseFilename=Bloodloom_setup_v{#AppVersion}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
SetupIconFile=Bloodloom.ico
; Отключаем стандартные страницы, чтобы было как у Xatab (сразу установка)
DisableWelcomePage=no
DisableReadyPage=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать значок на Рабочем столе"; GroupDescription: "Дополнительные значки:"

[Types]
Name: "full"; Description: "Полная установка (с AI-моделью)"
Name: "compact"; Description: "Облегченная установка (скачать модель позже)"
Name: "custom"; Description: "Выборочная установка"; Flags: iscustom

[Components]
Name: "core"; Description: "Ядро игры (обязательно)"; Types: full compact custom; Flags: fixed
Name: "llm"; Description: "AI-модель Qwen 7B (около 5 ГБ)"; Types: full
Name: "llama_cpp"; Description: "Движок llama.cpp (CUDA + CPU)"; Types: full compact custom

[Files]
; 1. Ядро игры (Берем из временной папки staging, где лежат .pyc)
Source: "build\staging\*"; DestDir: "{app}"; Excludes: ".venv,.git,__pycache__,*.log,logs,backend\logs,reports,build,*.egg-info,*.spec,docs,Tests,tests,Models LLM,payload"; Components: core; Flags: recursesubdirs ignoreversion createallsubdirs; BeforeInstall: UpdateLog

; 1.1 Портативный Python — S210: payload-пайплайн не автоматизирован (payload/
; не создаётся сборкой). До его реализации установщик — dev-дистрибутив:
; требует установленный Python 3.13 на целевой машине. TODO(payload): embeddable
; Python + pip install -r requirements + упаковка в payload/python — отдельная
; задача релизного пайплайна (см. MUTATIONS S210, долг BUILD-P1).
Source: "payload\python\*"; DestDir: "{app}\_internal\python"; Components: core; Flags: recursesubdirs ignoreversion createallsubdirs; BeforeInstall: UpdateLog

; 2. LLM-модель (ИСКЛЮЧЕНА! Скачивается отдельным установщиком)
; Source: "Models LLM\Qwen2.5-7B-Instruct-abliterated-v2.Q5_K_M.gguf"; DestDir: "{app}\Models LLM"; Components: llm; Flags: nocompression ignoreversion

; 3. llama.cpp бинарники
Source: "Models LLM\llama\*"; DestDir: "{app}\Models LLM\llama"; Components: llama_cpp; Flags: recursesubdirs ignoreversion nocompression; BeforeInstall: UpdateLog

[Icons]
Name: "{group}\Bloodloom"; Filename: "{app}\Bloodloom.exe"; IconFilename: "{app}\Bloodloom.ico"
Name: "{userdesktop}\Bloodloom"; Filename: "{app}\Bloodloom.exe"; Tasks: desktopicon; IconFilename: "{app}\Bloodloom.ico"

[Run]
Filename: "{app}\Bloodloom.exe"; Description: "{cm:LaunchProgram,Bloodloom}"; Flags: nowait postinstall skipifsilent

[Code]
var
  LogMemo: TNewMemo;

procedure InitializeWizard();
begin
  // Перекрашиваем окно в темный стиль (Xatab-modern)
  WizardForm.Color := $0F1419;
  WizardForm.MainPanel.Color := $0F1419;
  WizardForm.WelcomeLabel1.Font.Color := $00A887;
  WizardForm.WelcomeLabel2.Font.Color := $9DB4D3;
  WizardForm.PageNameLabel.Font.Color := $FFFFFF;
  WizardForm.PageDescriptionLabel.Font.Color := $9DB4D3;
  
  // Создаем лог-зону на странице установки
  LogMemo := TNewMemo.Create(WizardForm);
  LogMemo.Parent := WizardForm.InstallingPage;
  // Размещаем под стандартным прогресс-баром и текстом
  LogMemo.Top := WizardForm.ProgressGauge.Top + WizardForm.ProgressGauge.Height + ScaleY(15);
  LogMemo.Left := WizardForm.ProgressGauge.Left;
  LogMemo.Width := WizardForm.ProgressGauge.Width;
  LogMemo.Height := ScaleY(150); // Высота лога
  LogMemo.ReadOnly := True;
  LogMemo.ScrollBars := ssVertical;
  LogMemo.Color := $0A0F1A; // Очень темный фон
  LogMemo.Font.Color := $9DB4D3; // Серо-голубой текст
  LogMemo.Font.Name := 'Consolas';
  LogMemo.Font.Size := 9;
  LogMemo.BorderStyle := bsNone;
  LogMemo.Lines.Add('=== Журнал установки Bloodloom ===');
end;

procedure UpdateLog();
var
  CurrentFile: string;
begin
  if Assigned(LogMemo) then
  begin
    // Извлекаем имя текущего файла из стандартной метки Inno Setup
    CurrentFile := WizardForm.FileNameLabel.Caption;
    if CurrentFile <> '' then
    begin
      LogMemo.Lines.Add('Распаковка: ' + ExtractFileName(CurrentFile));
      // Автоскролл вниз
      LogMemo.SelStart := Length(LogMemo.Text);
      LogMemo.SelLength := 0;
    end;
  end;
end;