from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


DiaryEntry = dict[str, str]


def ensure_diary_file(path: Path) -> None:
    """Create the diary JSONL file if it does not exist."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")


def add_diary_entry(path: Path, content: str, mood: str = "") -> DiaryEntry:
    """Append one diary entry to the JSONL diary file."""
    content = content.strip()
    if not content:
        raise ValueError("日记内容不能为空。")

    ensure_diary_file(path)
    now = datetime.now().astimezone()
    entry = {
        "id": str(uuid.uuid4()),
        "content": content,
        "mood": mood,
        "created_at": now.isoformat(timespec="seconds"),
        "date": now.strftime("%Y-%m-%d"),
    }

    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return entry


def load_diary_entries(path: Path) -> list[DiaryEntry]:
    """Load diary JSONL entries, skipping malformed lines."""
    ensure_diary_file(path)
    entries: list[DiaryEntry] = []

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if _is_diary_entry_like(data):
                entries.append(_normalize_entry(data))

    return entries


def get_today_entries(path: Path) -> list[DiaryEntry]:
    """Return diary entries for the local current date."""
    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    return [entry for entry in load_diary_entries(path) if entry.get("date") == today]


def get_recent_entries(path: Path, limit: int = 7) -> list[DiaryEntry]:
    """Return recent diary entries."""
    if limit <= 0:
        return []
    return load_diary_entries(path)[-limit:]


def search_diary_entries(path: Path, keyword: str) -> list[DiaryEntry]:
    """Search diary entries by keyword in content."""
    keyword = keyword.strip()
    if not keyword:
        raise ValueError("搜索关键词不能为空。")
    return [entry for entry in load_diary_entries(path) if keyword in entry.get("content", "")]


def format_diary_entries(entries: list[DiaryEntry], empty_message: str) -> str:
    """Format diary entries for display in CLI/GUI."""
    if not entries:
        return empty_message

    lines: list[str] = []
    for index, entry in enumerate(entries, start=1):
        created_at = entry.get("created_at", "")
        content = entry.get("content", "")
        mood = entry.get("mood", "")
        mood_text = f" 心情：{mood}" if mood else ""
        lines.append(f"{index}. [{created_at}]{mood_text}\n{content}")
    return "\n\n".join(lines)


def _is_diary_entry_like(data: Any) -> bool:
    return isinstance(data, dict) and isinstance(data.get("content"), str)


def _normalize_entry(data: dict[str, Any]) -> DiaryEntry:
    created_at = str(data.get("created_at") or datetime.now().astimezone().isoformat(timespec="seconds"))
    date = str(data.get("date") or created_at[:10])
    return {
        "id": str(data.get("id") or uuid.uuid4()),
        "content": str(data.get("content", "")),
        "mood": str(data.get("mood", "")),
        "created_at": created_at,
        "date": date,
    }

