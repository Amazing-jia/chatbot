from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from bot.logger import get_logger


MemoryItem = dict[str, Any]
_WARNINGS: dict[str, str] = {}
VALID_TYPES = {"preference", "project", "fact", "relationship", "style"}
TYPE_RANK = {"style": 0, "preference": 1, "project": 2, "relationship": 3, "fact": 4}


def now_string() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_memory(path: Path) -> list[MemoryItem]:
    """Load long-term memory as a normalized JSON array."""
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = get_logger(path.parent.parent if path.parent.name == "data" else path.parent)

    if not path.exists():
        save_memory(path, [])
        return []

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError:
        backup_path = _backup_invalid_file(path)
        save_memory(path, [])
        logger.exception("memory json invalid backup=%s", backup_path)
        _set_warning(path, f"记忆文件格式损坏，已备份到：{backup_path}")
        return []

    if isinstance(data, dict):
        migrated = _migrate_legacy_memory(data)
        save_memory(path, migrated)
        return migrated

    if not isinstance(data, list):
        backup_path = _backup_invalid_file(path)
        save_memory(path, [])
        logger.error("memory root not list backup=%s", backup_path)
        _set_warning(path, f"记忆文件不是 JSON 数组，已备份到：{backup_path}")
        return []

    normalized = [_normalize_memory_item(item) for item in data if _is_memory_item_like(item)]
    if normalized != data:
        save_memory(path, normalized)
    return normalized


def save_memory(path: Path, memory: list[MemoryItem]) -> None:
    """Save long-term memory as readable UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
    with path.open("w", encoding="utf-8") as file:
        json.dump([_normalize_memory_item(item) for item in memory], file, ensure_ascii=False, indent=2)
        file.write("\n")


def add_memory(
    path: Path,
    content: str,
    memory_type: str = "preference",
    priority: int = 3,
) -> MemoryItem:
    """Append one manually provided long-term memory item."""
    content = content.strip()
    if not content:
        raise ValueError("记忆内容不能为空。")

    now = now_string()
    item = {
        "id": str(uuid.uuid4()),
        "type": _normalize_type(memory_type),
        "content": content,
        "priority": _normalize_priority(priority),
        "created_at": now,
        "updated_at": now,
    }
    memories = load_memory(path)
    memories.append(item)
    save_memory(path, memories)
    return item


def forget_memory(path: Path, keyword: str) -> list[MemoryItem]:
    """Delete memory items containing keyword and return deleted items."""
    keyword = keyword.strip()
    if not keyword:
        raise ValueError("关键词不能为空。")

    memories = load_memory(path)
    deleted = [item for item in memories if keyword in item.get("content", "")]
    kept = [item for item in memories if keyword not in item.get("content", "")]
    save_memory(path, kept)
    return deleted


def delete_memory_by_id(path: Path, memory_id: str) -> bool:
    """Delete one memory item by id. Returns True when something was deleted."""
    memory_id = memory_id.strip()
    if not memory_id:
        return False

    memories = load_memory(path)
    kept = [item for item in memories if item.get("id") != memory_id]
    deleted = len(kept) != len(memories)
    if deleted:
        save_memory(path, kept)
    return deleted


def clear_memory(path: Path) -> None:
    save_memory(path, [])


def select_memories_for_context(memories: list[MemoryItem], limit: int = 20) -> list[MemoryItem]:
    """Prefer style/preference memories, then higher priority, capped by limit."""
    limit = max(0, int(limit))
    if limit == 0:
        return []
    normalized = [_normalize_memory_item(item) for item in memories if _is_memory_item_like(item)]
    return sorted(
        normalized,
        key=lambda item: (
            TYPE_RANK.get(str(item.get("type")), 99),
            -int(item.get("priority", 3)),
            str(item.get("updated_at", "")),
        ),
    )[:limit]


def format_memory_for_display(memories: list[MemoryItem]) -> str:
    if not memories:
        return "暂无长期记忆。"

    lines: list[str] = []
    for index, item in enumerate(memories, start=1):
        memory_type = item.get("type", "preference")
        priority = item.get("priority", 3)
        created_at = item.get("created_at", "")
        suffix = f"（{memory_type} / P{priority} / {created_at}）" if created_at else f"（{memory_type} / P{priority}）"
        lines.append(f"{index}. {item.get('content', '')}{suffix}")
    return "\n".join(lines)


def format_memory_for_prompt(memories: list[MemoryItem]) -> str:
    if not memories:
        return "暂无长期记忆。"
    lines = []
    for item in memories:
        lines.append(
            f"* [{item.get('type', 'preference')} / P{item.get('priority', 3)}] {item.get('content', '')}"
        )
    return "\n".join(lines)


def build_system_prompt(persona_text: str, memories: list[MemoryItem]) -> str:
    """Backward-compatible simple system prompt builder."""
    selected = select_memories_for_context(memories, limit=20)
    return (
        "【人格设定】\n"
        f"{persona_text.strip()}\n\n"
        "【长期记忆】\n"
        f"{format_memory_for_prompt(selected)}"
    )


def pop_memory_warning(path: Path) -> str:
    return _WARNINGS.pop(str(path.resolve()), "")


def _set_warning(path: Path, message: str) -> None:
    _WARNINGS[str(path.resolve())] = message


def _backup_invalid_file(path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_name(f"{path.stem}.invalid.{timestamp}{path.suffix}")
    path.replace(backup_path)
    return backup_path


def _is_memory_item_like(item: Any) -> bool:
    return isinstance(item, dict) and isinstance(item.get("content"), str)


def _normalize_memory_item(item: dict[str, Any]) -> MemoryItem:
    created_at = str(item.get("created_at") or now_string())
    return {
        "id": str(item.get("id") or uuid.uuid4()),
        "type": _normalize_type(str(item.get("type") or "preference")),
        "content": str(item.get("content", "")),
        "priority": _normalize_priority(item.get("priority", 3)),
        "created_at": created_at,
        "updated_at": str(item.get("updated_at") or created_at),
    }


def _normalize_type(memory_type: str) -> str:
    memory_type = memory_type.strip().lower()
    return memory_type if memory_type in VALID_TYPES else "preference"


def _normalize_priority(priority: Any) -> int:
    try:
        value = int(priority)
    except (TypeError, ValueError):
        value = 3
    return min(5, max(1, value))


def _migrate_legacy_memory(data: dict[str, Any]) -> list[MemoryItem]:
    memories: list[MemoryItem] = []
    for key, memory_type in (
        ("preferences", "preference"),
        ("projects", "project"),
        ("notes", "fact"),
    ):
        value = data.get(key, [])
        if isinstance(value, list):
            for content in value:
                if isinstance(content, str) and content.strip():
                    memories.append(_new_legacy_item(content.strip(), memory_type))
    recent_status = data.get("recent_status")
    if isinstance(recent_status, str) and recent_status.strip():
        memories.append(_new_legacy_item(f"近期状态：{recent_status.strip()}", "fact"))
    return memories


def _new_legacy_item(content: str, memory_type: str) -> MemoryItem:
    now = now_string()
    return {
        "id": str(uuid.uuid4()),
        "type": memory_type,
        "content": content,
        "priority": 3,
        "created_at": now,
        "updated_at": now,
    }
