from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def append_chat_record(
    path: Path,
    user_text: str,
    assistant_text: str,
    model: str,
    metrics: dict[str, Any] | None = None,
) -> None:
    """Append one chat turn to a JSONL history file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "model": model,
        "user": user_text,
        "assistant": assistant_text,
        "metrics": metrics or {},
    }

    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_recent_messages(path: Path, turns: int = 8) -> list[dict[str, str]]:
    """Load recent chat turns and convert them into Ollama messages."""
    if turns <= 0 or not path.exists():
        return []

    records = _load_jsonl(path)
    recent_records = records[-turns:]
    messages: list[dict[str, str]] = []

    for record in recent_records:
        user_text = record.get("user")
        assistant_text = record.get("assistant")
        if isinstance(user_text, str) and user_text:
            messages.append({"role": "user", "content": user_text})
        if isinstance(assistant_text, str) and assistant_text:
            messages.append({"role": "assistant", "content": assistant_text})

    return messages


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read JSONL safely and skip malformed lines."""
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                records.append(record)
    return records
