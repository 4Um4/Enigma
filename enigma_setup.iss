; enigma_setup.iss — Скрипт установочника Bloodloom

#ifndef AppVersion
  #define AppVersion "0.0.0.0"
#endif

[Setup]
AppName=Bloodloom
AppVersion={#AppVersion}
AppPublisher=Bloodloom Team
DefaultDirName={localappdata}\Programs\Bloodloom
DefaultGroupName=Bloodloom
DisableProgramGroupPage=yes
OutputDir=build
OutputBaseFilename=Bloodloom_setup_v{#AppVersion}
; Устанавливаем в профиль пользователя (не нужны права админа, нет ошибки доступа)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; Настройки разбиения и сжатия
DiskSpanning=yes
DiskSliceSize=1900000000
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
; Иконка установщика (убери эту строку, если файла Bloodloom.ico пока нет)
SetupIconFile=Bloodloom.ico

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
; 1. Ядро игры (ИСКЛЮЧАЕМ документацию, кэши и виртуальное окружение)
Source: "*"; DestDir: "{app}"; Excludes: ".venv,.git,__pycache__,*.log,logs,reports,build,*.egg-info,*.spec,docs,Tests,tests,architecture,Models LLM,payload"; Components: core; Flags: recursesubdirs ignoreversion createallsubdirs

; 1.1 Портативный Python (Embeddable Python + зависимости)
Source: "payload\python\*"; DestDir: "{app}\_internal\python"; Components: core; Flags: recursesubdirs ignoreversion createallsubdirs

; 2. LLM-модель
Source: "Models LLM\Qwen2.5-7B-Instruct-abliterated-v2.Q5_K_M.gguf"; DestDir: "{app}\Models LLM"; Components: llm; Flags: nocompression ignoreversion

; 3. llama.cpp бинарники
Source: "Models LLM\llama\*"; DestDir: "{app}\Models LLM\llama"; Components: llama_cpp; Flags: recursesubdirs ignoreversion nocompression

[Icons]
; Ярлык запускает Bloodloom.exe (бывший updater.exe) с иконкой
Name: "{group}\Bloodloom"; Filename: "{app}\Bloodloom.exe"; IconFilename: "{app}\Bloodloom.ico"
Name: "{userdesktop}\Bloodloom"; Filename: "{app}\Bloodloom.exe"; Tasks: desktopicon; IconFilename: "{app}\Bloodloom.ico"

[Run]
Filename: "{app}\Bloodloom.exe"; Description: "{cm:LaunchProgram,Bloodloom}"; Flags: nowait postinstall skipifsilent