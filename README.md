# Chatbot

Chatbot 是一个独立的 Windows 本地桌面陪聊软件，适合日常聊天、解闷、吐槽、复盘生活和整理想法。它使用 CustomTkinter 制作桌面界面，通过 Ollama 调用本机大模型。

Chatbot 不内置 Ollama，不内置任何大模型文件，也不会连接云端 API。所有聊天、记忆、日记和日志默认都保存在你自己的电脑本地。

## 功能特点

- Windows 本地桌面窗口，不是网页界面
- 使用 Ollama 本地模型作为后端
- 默认模型：`qwen3:8b`
- 支持流式输出，回复会逐步显示
- 支持停止生成
- 支持多轮对话管理：新建、切换、删除、重命名
- 启动后自动恢复上次活跃对话
- 支持长期记忆，保存在本地 `data/memory.json`
- 支持日记命令，保存在本地 `data/diary.jsonl`
- 支持陪聊反馈数据，用于后续优化回复风格
- 支持分层上下文管理，不会每次把全部历史塞给模型

## 隐私说明

Chatbot 的私人数据默认保存在程序目录下，例如：

- `data/conversations/`
- `data/memory.json`
- `data/diary.jsonl`
- `data/feedback/`
- `logs/`
- `config.yaml`

这些文件不会提交到 GitHub，也不会包含在公开发行包中。公开发行包只包含程序、示例配置、人格提示词模板和说明文档。

## 运行前准备

使用 Chatbot 前，你需要先在本机安装 Ollama，并下载本地模型。

1. 安装 Ollama：

   https://ollama.com

2. 下载默认模型：

```powershell
ollama pull qwen3:8b
```

3. 确认 Ollama 已启动。

如果你想换模型，可以修改 `config.yaml` 里的：

```yaml
model: qwen3:8b
```

## 运行 exe 版

从 GitHub Release 下载：

```text
chatbot-windows-v0.1.1.zip
```

解压后双击：

```text
Chatbot.exe
```

第一次运行时，程序会自动创建：

```text
config.yaml
data/
logs/
```

如果 Ollama 没启动，界面会提示：

```text
未检测到本地模型服务，请先启动 Ollama。
```

如果模型没有安装，请先运行：

```powershell
ollama pull qwen3:8b
```

## 源码运行方式

进入项目目录后执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

如果 PowerShell 不允许激活虚拟环境，可以临时执行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## 配置说明

公开仓库中提供的是：

```text
config.example.yaml
```

程序启动时如果没有 `config.yaml`，会自动根据 `config.example.yaml` 创建一个本地配置文件。

常用配置项：

```yaml
model: qwen3:8b
ollama_url: http://localhost:11434/api/chat
persona_path: prompts/persona.md
memory_path: data/memory.json
diary_path: data/diary.jsonl
conversations_dir: data/conversations
logs_dir: logs
```

## 本地数据

Chatbot 会在本地保存：

- 历史对话
- 长期记忆
- 日记
- 回复反馈
- 程序日志

这些数据只在你的电脑上，不会自动上传。

## 打包说明

如果你想自己重新打包 exe，可以运行：

```powershell
.\build_exe.bat
```

打包输出位于：

```text
release/
```

生成的压缩包：

```text
release/chatbot-windows-v0.1.1.zip
```

注意：Ollama 和大模型不会被打包进 exe。用户仍然需要自己安装 Ollama 并下载模型。

## 版本规则

Chatbot 使用常见的语义化版本号：

```text
主版本.次版本.修订版本
```

示例：

- `0.1.1`：小修小改，例如性能优化、界面微调、提示词调整、Bug 修复
- `0.2.0`：功能级更新，例如新增较完整的新模块或重要能力
- `1.0.0`：稳定正式版，代表核心功能和使用体验进入相对稳定阶段

当前版本：`0.1.1`

## 许可证

本项目使用 MIT License。


