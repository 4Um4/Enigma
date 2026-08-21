; models_setup.iss — Установщик AI-моделей Bloodloom

[Setup]
AppName=Bloodloom AI Models
AppVersion=1.0
DefaultDirName={reg:HKCU\Software\Bloodloom,InstallPath|{localappdata}\Programs\Bloodloom}
OutputDir=build
OutputBaseFilename=Bloodloom_models_setup
Compression=none
DiskSpanning=yes
DiskSliceSize=1900000000

[Files]
Source: "Models LLM\Qwen2.5-7B-Instruct-abliterated-v2.Q5_K_M.gguf"; DestDir: "{app}\Models LLM"; Flags: nocompression ignoreversion