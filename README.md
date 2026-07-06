# Chatbot

Chatbot is an independent Windows local desktop companion chat app. It is designed for everyday conversation, venting, journaling-style reflection, and gentle thought organization.

It uses a local Ollama model through the Ollama API. Chatbot does not include Ollama, does not include any model files, and does not connect to cloud APIs.

## Features

- CustomTkinter desktop UI
- Local Ollama chat backend
- Default model: `qwen3:8b`
- Streaming assistant replies
- Stop generation button
- Conversation history with local restore
- Long-term memory stored locally
- Diary commands stored locally
- Local feedback files for reply preference tuning
- Layered context management to avoid sending full history to the model

## Privacy

All user data is stored locally under the app directory:

- `data/conversations/`
- `data/memory.json`
- `data/diary.jsonl`
- `data/feedback/`
- `logs/`

Private data is ignored by Git and is not included in the release zip.

## Requirements

Install Ollama first:

https://ollama.com/

Pull the default model:

```powershell
ollama pull qwen3:8b
```

Start Ollama if it is not already running:

```powershell
ollama serve
```

## Run From Source

```powershell
cd D:\bot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

You can also run:

```powershell
python gui.py
```

## Run EXE Version

Download `chatbot-windows-v0.1.0.zip` from GitHub Releases.

Unzip it and double-click:

```text
Chatbot.exe
```

Before running the exe, make sure Ollama is installed and the default model exists:

```powershell
ollama pull qwen3:8b
```

## Configuration

The app reads `config.yaml` from the app directory.

For GitHub, the repository only includes:

```text
config.example.yaml
```

If `config.yaml` is missing, the app creates it from `config.example.yaml`.

## Data

Runtime data is created automatically:

```text
data/
logs/
```

The UI may show full local conversation history, but model calls only use a limited recent context plus persona, memory, preferences, and summary.

## Build

See:

```text
README_BUILD.md
```
