from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def now_string() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def feedback_dir(data_dir: Path) -> Path:
    return data_dir / "feedback"


def liked_path(data_dir: Path) -> Path:
    return feedback_dir(data_dir) / "liked.jsonl"


def disliked_path(data_dir: Path) -> Path:
    return feedback_dir(data_dir) / "disliked.jsonl"


def rewrites_path(data_dir: Path) -> Path:
    return feedback_dir(data_dir) / "rewrites.jsonl"


def ensure_feedback_files(data_dir: Path) -> None:
    feedback_dir(data_dir).mkdir(parents=True, exist_ok=True)
    for path in (liked_path(data_dir), disliked_path(data_dir), rewrites_path(data_dir)):
        if not path.exists():
            path.write_text("", encoding="utf-8")


def save_liked(
    data_dir: Path,
    conversation_id: str,
    user_message: str,
    assistant_reply: str,
    chat_mode: str,
) -> dict[str, Any]:
    record = {
        "conversation_id": conversation_id,
        "user_message": user_message,
        "assistant_reply": assistant_reply,
        "chat_mode": chat_mode,
        "created_at": now_string(),
    }
    _append_jsonl(liked_path(data_dir), record)
    return record


def save_disliked(
    data_dir: Path,
    conversation_id: str,
    user_message: str,
    assistant_reply: str,
    chat_mode: str,
    reason: str = "",
) -> dict[str, Any]:
    record = {
        "conversation_id": conversation_id,
        "user_message": user_message,
        "assistant_reply": assistant_reply,
        "chat_mode": chat_mode,
        "reason": reason,
        "created_at": now_string(),
    }
    _append_jsonl(disliked_path(data_dir), record)
    return record


def save_rewrite(
    data_dir: Path,
    conversation_id: str,
    user_message: str,
    bad_reply: str,
    ideal_reply: str,
    chat_mode: str,
) -> dict[str, Any]:
    record = {
        "conversation_id": conversation_id,
        "user_message": user_message,
        "bad_reply": bad_reply,
        "ideal_reply": ideal_reply,
        "chat_mode": chat_mode,
        "created_at": now_string(),
    }
    _append_jsonl(rewrites_path(data_dir), record)
    return record


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    ensure_feedback_files(path.parent.parent)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False))
        file.write("\n")
