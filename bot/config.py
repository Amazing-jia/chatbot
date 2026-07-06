from __future__ import annotations

from copy import deepcopy
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from bot.logger import get_logger


DEFAULT_PERSONA = """# 本地私人陪聊伙伴人格设定

你是一个本地运行的私人陪聊 bot，用来陪用户聊天、解闷、吐槽、复盘生活和整理想法。

你不是冷冰冰的知识问答助手，不是客服，不是老师，也不是心理咨询师。你的默认目标不是立刻解决问题，而是先让用户感觉被听见、被理解、没有被评判，可以慢慢说。

## 核心定位

- 你是本地运行的 AI 陪聊伙伴，可以自然地陪用户聊一会儿。
- 你不能假装自己是真人，不能暗示自己有真实经历、现实身份或现实情感关系。
- 你不制造依赖感，不说“只有我懂你”“我会永远陪着你”这类话。
- 你可以温柔、轻松、像朋友一样接话，但要保持边界感。
- 你不接入云端 API，不声称自己能访问外部服务或实时信息。

## 默认说话风格

- 默认使用简体中文。
- 温柔自然，生活化，少一点 AI 味和客服味。
- 像朋友一样接话，不要每次都像在写总结报告。
- 普通闲聊控制在 2 到 6 句话，除非用户明确要求详细分析。
- 不要总是列 1、2、3，不要动不动就给行动清单。
- 不要上来就讲大道理，不要过度总结用户。
- 可以适度轻松、吐槽、幽默，但不要油腻，不要用力表演。
- 用户只是想说说时，先陪他说，不急着把话题变成“解决方案”。

## 情绪陪伴原则

当用户表达烦、累、委屈、失落、无聊、压力大、孤独、憋屈时，先接住情绪，再考虑是否需要建议。一次只问一个问题，不要连续追问很多。

## 吐槽模式

当用户明显是在吐槽时，陪用户吐槽，而不是立刻纠正。可以站在用户视角回应，但不要攻击具体个人，不鼓励冲动决定。

## 建议模式

只有当用户明确说“帮我分析一下”“我该怎么办”“给我建议”“帮我规划”“怎么解决”时，再进入建议模式。

建议模式里：先简短共情，再把问题拆小，给 1 到 3 个可执行建议。语气像商量，不像命令。

## 学习和项目模式

当用户问学习、代码、考试、项目问题时，可以更清晰、耐心、结构化。即使在学习模式，也保持温和自然。

## 边界和安全

不假装自己是真人，不制造依赖感，不鼓励用户远离现实中的朋友、家人、老师或专业帮助。
"""


DEFAULT_CONFIG: dict[str, Any] = {
    "model": "qwen3:8b",
    "ollama_url": "http://localhost:11434/api/chat",
    "persona_path": "prompts/persona.md",
    "memory_path": "data/memory.json",
    "diary_path": "data/diary.jsonl",
    "history_path": "data/chat_history.jsonl",
    "conversations_dir": "data/conversations",
    "conversations_index_path": "data/conversations_index.json",
    "app_state_path": "data/app_state.json",
    "feedback_dir": "data/feedback",
    "request_timeout": 120,
    "history_turns_in_context": 8,
    "context_settings": {
        "recent_rounds": 4,
        "max_memory_items": 10,
        "enable_conversation_summary": True,
        "summary_trigger_rounds": 12,
        "max_summary_chars": 600,
        "include_diary_by_default": False,
    },
    "companion_preferences": {
        "tone": "温柔、自然、生活化，像朋友一样接话，少一点客服味。",
        "default_length": "普通闲聊默认 2 到 6 句话，除非用户明确要求详细分析。",
        "emotional_support": "用户诉苦时先接住情绪，不急着给建议。",
        "advice_style": "用户明确要建议时，先简短共情，再给 1 到 3 个可执行建议。",
        "avoid": "不要说教，不要强行分析，不要制造依赖感，不要假装是真人。",
    },
    "theme": {
        "appearance": "light",
        "primary_color": "#3B82F6",
        "accent_color": "#2563EB",
        "background_color": "#F6F8FB",
        "sidebar_color": "#F8FAFF",
    },
}


def resolve_path(base_dir: Path, path_value: str) -> Path:
    """Resolve config paths relative to the project directory."""
    path = Path(path_value)
    if path.is_absolute():
        return path
    return base_dir / path


def load_config(base_dir: Path) -> dict[str, Any]:
    """Load config.yaml, creating and completing it when needed."""
    logger = get_logger(base_dir)
    config_path = base_dir / "config.yaml"

    if not config_path.exists():
        example_path = base_dir / "config.example.yaml"
        if example_path.exists():
            shutil.copy2(example_path, config_path)
            logger.info("created config from example path=%s", example_path)
            with config_path.open("r", encoding="utf-8") as file:
                loaded = yaml.safe_load(file) or {}
            config = _merge_defaults(loaded if isinstance(loaded, dict) else {}, DEFAULT_CONFIG)
            if config != loaded:
                save_config(config_path, config)
        else:
            config = deepcopy(DEFAULT_CONFIG)
            save_config(config_path, config)
        logger.info("created default config path=%s", config_path)
    else:
        try:
            with config_path.open("r", encoding="utf-8") as file:
                loaded = yaml.safe_load(file) or {}
        except yaml.YAMLError as exc:
            backup_path = _backup_invalid_file(config_path)
            logger.exception("config yaml invalid backup=%s error=%s", backup_path, exc)
            config = deepcopy(DEFAULT_CONFIG)
            save_config(config_path, config)
            ensure_project_files(base_dir, config)
            return config
        except OSError as exc:
            logger.exception("failed to read config path=%s error=%s", config_path, exc)
            config = deepcopy(DEFAULT_CONFIG)
            save_config(config_path, config)
            ensure_project_files(base_dir, config)
            return config
        if not isinstance(loaded, dict):
            backup_path = _backup_invalid_file(config_path)
            logger.error("config root is not dict backup=%s", backup_path)
            loaded = {}
        config = _merge_defaults(loaded, DEFAULT_CONFIG)
        if config != loaded:
            save_config(config_path, config)

    ensure_project_files(base_dir, config)
    return config


def save_config(config_path: Path, config: dict[str, Any]) -> None:
    """Save YAML config as UTF-8."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        shutil.copy2(config_path, config_path.with_suffix(config_path.suffix + ".bak"))
    with config_path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(config, file, allow_unicode=True, sort_keys=False)


def ensure_project_files(base_dir: Path, config: dict[str, Any]) -> None:
    """Create required folders and starter files if they are missing."""
    prompts_dir = base_dir / "prompts"
    data_dir = base_dir / "data"
    logs_dir = base_dir / "logs"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    persona_path = resolve_path(base_dir, config.get("persona_path", "prompts/persona.md"))
    memory_path = resolve_path(base_dir, config.get("memory_path", "data/memory.json"))
    diary_path = resolve_path(base_dir, config.get("diary_path", "data/diary.jsonl"))
    history_path = resolve_path(base_dir, config.get("history_path", "data/chat_history.jsonl"))
    conversations_path = resolve_path(base_dir, config.get("conversations_dir", "data/conversations"))
    conversations_index_path = resolve_path(
        base_dir,
        config.get("conversations_index_path", "data/conversations_index.json"),
    )
    app_state_path = resolve_path(base_dir, config.get("app_state_path", "data/app_state.json"))
    feedback_path = resolve_path(base_dir, config.get("feedback_dir", "data/feedback"))

    persona_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    diary_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    conversations_path.mkdir(parents=True, exist_ok=True)
    (data_dir / "trash").mkdir(parents=True, exist_ok=True)
    conversations_index_path.parent.mkdir(parents=True, exist_ok=True)
    app_state_path.parent.mkdir(parents=True, exist_ok=True)
    feedback_path.mkdir(parents=True, exist_ok=True)

    if not persona_path.exists():
        persona_path.write_text(DEFAULT_PERSONA, encoding="utf-8")
    if not memory_path.exists():
        memory_path.write_text("[]\n", encoding="utf-8")
    if not diary_path.exists():
        diary_path.write_text("", encoding="utf-8")
    if not history_path.exists():
        history_path.write_text("", encoding="utf-8")
    if not conversations_index_path.exists():
        conversations_index_path.write_text("[]\n", encoding="utf-8")
    if not app_state_path.exists():
        app_state_path.write_text('{"last_active_conversation_id": ""}\n', encoding="utf-8")
    for feedback_name in ("liked.jsonl", "disliked.jsonl", "rewrites.jsonl"):
        path = feedback_path / feedback_name
        if not path.exists():
            path.write_text("", encoding="utf-8")


def _merge_defaults(config: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    """Recursively fill missing config keys."""
    merged = deepcopy(config)
    for key, default_value in defaults.items():
        if key not in merged:
            merged[key] = deepcopy(default_value)
        elif isinstance(merged[key], dict) and isinstance(default_value, dict):
            merged[key] = _merge_defaults(merged[key], default_value)
    return merged


def _backup_invalid_file(path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_name(f"{path.name}.invalid.{timestamp}")
    if path.exists():
        path.replace(backup_path)
    return backup_path

