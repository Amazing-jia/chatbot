# GitHub Release Guide

Repository name:

```text
chatbot
```

Software name:

```text
Chatbot
```

## Files That Must Not Be Uploaded

Never commit:

- `config.yaml`
- `data/conversations/`
- `data/trash/`
- `data/memory.json`
- `data/diary.jsonl`
- `data/app_state.json`
- `data/conversations_index.json`
- `logs/`
- `.env`
- `*.bak`
- `*.log`
- model files such as `*.gguf`, `*.bin`, `*.safetensors`, `*.pt`, `*.pth`, `*.onnx`
- `build/`
- `dist/`
- `release/`
- `.venv/`

## Create Repository With GitHub CLI

Check login:

```powershell
gh auth status
```

If not logged in, run:

```powershell
gh auth login
```

Initialize and push:

```powershell
git init
git branch -M main
git add .
git commit -m "Initial release of Chatbot"
gh repo create chatbot --public --source=. --remote=origin --push
```

If the repository already exists, verify the remote first:

```powershell
git remote -v
```

Then push:

```powershell
git push -u origin main
```

## Create Release

Create tag:

```powershell
git tag v0.1.0
git push origin v0.1.0
```

Upload release zip:

```powershell
gh release create v0.1.0 release/chatbot-windows-v0.1.0.zip --title "Chatbot v0.1.0" --notes "First Windows preview release of Chatbot. This app runs locally and uses Ollama for local model inference. Please install Ollama and pull qwen3:8b before running."
```

## Final Safety Check

Before pushing:

```powershell
git status
git status --ignored
git ls-files
```

Inspect the release zip:

```powershell
tar -tf release/chatbot-windows-v0.1.0.zip
```

The zip must not contain private `data/`, `logs/`, or `config.yaml`.
