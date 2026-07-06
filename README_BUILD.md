# Build Chatbot for Windows

This project uses PyInstaller to build `Chatbot.exe`.

The release package does not include Ollama, model files, private chat data, diaries, memories, logs, or local `config.yaml`.

## Install Build Dependencies

```powershell
cd D:\bot
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install pyinstaller
```

## Build EXE

```powershell
.\build_exe.bat
```

This generates:

```text
release/
  Chatbot.exe
  config.example.yaml
  prompts/
    persona.md
  README.md
  README_BUILD.md
  LICENSE
  chatbot-windows-v0.1.1.zip
```

## Release Zip

The zip file is:

```text
release/chatbot-windows-v0.1.1.zip
```

Zip contents:

```text
Chatbot.exe
config.example.yaml
prompts/persona.md
README.md
README_BUILD.md
LICENSE
```

The app creates runtime files on first launch:

```text
config.yaml
data/
logs/
```

## User Requirements

Before running `Chatbot.exe`, users must install Ollama and pull the model:

```powershell
ollama pull qwen3:8b
```

Then start Ollama if needed:

```powershell
ollama serve
```

## Path Notes

In exe mode, Chatbot uses the directory containing `Chatbot.exe` as the app directory.

Keep these files next to the exe:

```text
Chatbot.exe
config.example.yaml
prompts/
```

Do not move `Chatbot.exe` alone to another folder unless you also move its support files.


当前构建版本由 build_exe.bat 中的 VERSION=0.1.1 控制。

