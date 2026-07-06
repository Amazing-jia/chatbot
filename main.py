from __future__ import annotations

import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from bot.commands import handle_diary_command, handle_memory_command
from bot.config import load_config, resolve_path
from bot.context import build_layered_messages, context_settings_from_config
from bot.history import append_chat_record, load_recent_messages
from bot.ollama_client import ChatResult, OllamaClient, OllamaConnectionError
from bot.ollama_client import OllamaResponseError


def get_base_dir() -> Path:
    """Return project directory in source mode, or exe directory when frozen."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = get_base_dir()
EXIT_COMMANDS = {"/exit", "/quit", "exit", "quit", "退出"}


def format_speed_line(result: ChatResult) -> str:
    """Format a compact performance line for the command line and GUI."""
    parts: list[str] = []

    if result.tokens_per_second is not None:
        parts.append(f"输出速度 {result.tokens_per_second:.2f} tokens/s")
    if result.output_tokens is not None:
        parts.append(f"输出 {result.output_tokens} tokens")
    if result.prompt_tokens is not None:
        parts.append(f"输入 {result.prompt_tokens} tokens")
    if result.eval_duration_seconds is not None:
        parts.append(f"生成耗时 {result.eval_duration_seconds:.2f}s")
    if result.total_duration_seconds is not None:
        parts.append(f"总耗时 {result.total_duration_seconds:.2f}s")

    if not parts:
        return "速度信息：当前 Ollama 响应没有返回可用的性能指标。"

    return "速度信息：" + " | ".join(parts)


def load_runtime() -> dict[str, Any]:
    """Load config and resolve all runtime paths in one place."""
    config = load_config(BASE_DIR)
    return {
        "config": config,
        "model": config.get("model", "qwen3:8b"),
        "ollama_url": config.get("ollama_url", "http://localhost:11434"),
        "timeout": int(config.get("request_timeout", 120)),
        "history_turns": int(config.get("history_turns_in_context", 8)),
        "persona_path": resolve_path(BASE_DIR, config.get("persona_path", "prompts/persona.md")),
        "memory_path": resolve_path(BASE_DIR, config.get("memory_path", "data/memory.json")),
        "diary_path": resolve_path(BASE_DIR, config.get("diary_path", "data/diary.jsonl")),
        "history_path": resolve_path(BASE_DIR, config.get("history_path", "data/chat_history.jsonl")),
    }


def build_messages(runtime: dict[str, Any], user_text: str) -> list[dict[str, str]]:
    """Build Ollama messages with the same layered context as the GUI."""
    settings = context_settings_from_config(runtime["config"])
    recent = load_recent_messages(runtime["history_path"], turns=int(settings["recent_rounds"]))
    conversation = {
        "id": "cli",
        "title": "CLI",
        "summary": "",
        "messages": [*recent, {"role": "user", "content": user_text}],
    }
    return build_layered_messages(
        runtime["config"],
        runtime["persona_path"],
        runtime["memory_path"],
        conversation,
        user_text,
    )


def print_welcome(model: str) -> None:
    print("=" * 60)
    print("本地私人陪聊 bot")
    print(f"当前模型：{model}")
    print("模型命令：/models，/model，/model 模型名")
    print("记忆命令：/memory，/remember 内容，/forget 关键词")
    print("日记命令：/diary 内容，/diary_today，/diary_recent，/diary_search 关键词")
    print("其他命令：/clear，/exit")
    print("=" * 60)


def handle_model_command(user_text: str, client: OllamaClient) -> bool:
    """Handle /model and /models commands. Return True if handled."""
    if user_text == "/models":
        try:
            models = client.list_models()
        except OllamaConnectionError:
            print("连接 Ollama 失败，暂时无法读取本地模型列表。")
            return True
        except OllamaResponseError as exc:
            print(f"Ollama 返回异常：{exc}")
            return True

        if not models:
            print("没有从 Ollama 读到本地模型。你可以先确认 `ollama list` 是否有结果。")
            return True

        print("本地可用模型：")
        for name in models:
            marker = " *" if name == client.model else ""
            print(f"- {name}{marker}")
        return True

    if user_text == "/model":
        print(f"当前模型：{client.model}")
        print("切换示例：/model qwen3:8b")
        return True

    if user_text.startswith("/model "):
        new_model = user_text.removeprefix("/model ").strip()
        if not new_model:
            print("请输入模型名，例如：/model qwen3:8b")
            return True

        client.set_model(new_model)
        print(f"已切换模型：{client.model}")
        print("提示：如果模型名不存在，下一轮请求时 Ollama 会返回错误。")
        return True

    return False


def main() -> int:
    try:
        runtime = load_runtime()
        client = OllamaClient(
            base_url=runtime["ollama_url"],
            model=runtime["model"],
            timeout=runtime["timeout"],
        )
    except Exception as exc:
        print(f"启动失败：{exc}")
        return 1

    print_welcome(client.model)

    while True:
        try:
            user_text = input("\n你：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已退出。")
            return 0

        if not user_text:
            continue

        if user_text.lower() in EXIT_COMMANDS:
            print("已退出。")
            return 0

        if user_text == "/clear":
            os.system("cls")
            print_welcome(client.model)
            continue

        handled_diary, diary_message = handle_diary_command(user_text, runtime["diary_path"])
        if handled_diary:
            print(diary_message)
            continue

        handled, command_message, should_exit = handle_memory_command(user_text, runtime["memory_path"])
        if handled:
            print(command_message)
            if should_exit:
                return 0
            continue

        if handle_model_command(user_text, client):
            continue

        try:
            result = client.chat(build_messages(runtime, user_text))
        except OllamaConnectionError:
            print(
                "\n连接 Ollama 失败。请确认 Ollama 已启动，并检查 config.yaml 里的 "
                "ollama_url 是否正确。常见地址是 http://localhost:11434"
            )
            continue
        except OllamaResponseError as exc:
            print(f"\nOllama 返回异常：{exc}")
            continue
        except Exception as exc:
            print(f"\n发生未知错误：{exc}")
            continue

        print(f"\nbot：{result.content}")
        print(format_speed_line(result))
        append_chat_record(
            runtime["history_path"],
            user_text,
            result.content,
            client.model,
            metrics=asdict(result),
        )


if __name__ == "__main__":
    sys.exit(main())

