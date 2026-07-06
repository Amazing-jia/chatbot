from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from bot.logger import get_logger


ConversationIndexItem = dict[str, str]
Conversation = dict[str, Any]
AppState = dict[str, str]
DEFAULT_TITLE = "新对话"


def now_string() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def conversations_dir(data_dir: Path) -> Path:
    return data_dir / "conversations"


def index_path(data_dir: Path) -> Path:
    return data_dir / "conversations_index.json"


def app_state_path(data_dir: Path) -> Path:
    return data_dir / "app_state.json"


def conversation_path(data_dir: Path, conversation_id: str) -> Path:
    return conversations_dir(data_dir) / f"conversation_{conversation_id}.json"


def legacy_conversation_path(data_dir: Path, conversation_id: str) -> Path:
    return conversations_dir(data_dir) / f"{conversation_id}.json"


def ensure_conversation_storage(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    conversations_dir(data_dir).mkdir(parents=True, exist_ok=True)
    (data_dir / "trash").mkdir(parents=True, exist_ok=True)
    if not index_path(data_dir).exists():
        index_path(data_dir).write_text("[]\n", encoding="utf-8")
    if not app_state_path(data_dir).exists():
        save_app_state(data_dir, {"last_active_conversation_id": ""})


def ensure_conversation_store(data_dir: Path) -> None:
    """Backward-compatible alias for older callers."""
    ensure_conversation_storage(data_dir)


def load_conversations_index(data_dir: Path) -> list[ConversationIndexItem]:
    ensure_conversation_storage(data_dir)
    path = index_path(data_dir)
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError:
        backup_path = path.with_name(
            f"conversations_index.invalid.{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        path.replace(backup_path)
        get_logger(data_dir.parent).exception("conversation index invalid backup=%s", backup_path)
        save_conversations_index(data_dir, [])
        return []

    if not isinstance(data, list):
        save_conversations_index(data_dir, [])
        return []

    items = [_normalize_index_item(item) for item in data if isinstance(item, dict)]
    items = [item for item in items if item.get("id")]
    return sorted(items, key=lambda item: item.get("updated_at", ""), reverse=True)


def save_conversations_index(data_dir: Path, index: list[ConversationIndexItem]) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    conversations_dir(data_dir).mkdir(parents=True, exist_ok=True)
    sorted_index = sorted(index, key=lambda item: item.get("updated_at", ""), reverse=True)
    with index_path(data_dir).open("w", encoding="utf-8") as file:
        json.dump(sorted_index, file, ensure_ascii=False, indent=2)
        file.write("\n")


def load_app_state(data_dir: Path) -> AppState:
    ensure_conversation_storage(data_dir)
    path = app_state_path(data_dir)
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError:
        backup_path = path.with_name(f"app_state.invalid.{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        path.replace(backup_path)
        get_logger(data_dir.parent).exception("app state invalid backup=%s", backup_path)
        state = {"last_active_conversation_id": ""}
        save_app_state(data_dir, state)
        return state

    if not isinstance(data, dict):
        state = {"last_active_conversation_id": ""}
        save_app_state(data_dir, state)
        return state

    return {"last_active_conversation_id": str(data.get("last_active_conversation_id") or "")}


def save_app_state(data_dir: Path, state: AppState) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    with app_state_path(data_dir).open("w", encoding="utf-8") as file:
        json.dump(
            {"last_active_conversation_id": str(state.get("last_active_conversation_id") or "")},
            file,
            ensure_ascii=False,
            indent=2,
        )
        file.write("\n")


def set_last_active_conversation(data_dir: Path, conversation_id: str) -> None:
    save_app_state(data_dir, {"last_active_conversation_id": conversation_id})


def get_last_active_conversation(data_dir: Path) -> Conversation:
    ensure_conversation_storage(data_dir)
    state = load_app_state(data_dir)
    conversation_id = state.get("last_active_conversation_id", "")
    if conversation_id and _conversation_file_exists(data_dir, conversation_id):
        try:
            return load_conversation(data_dir, conversation_id)
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            pass

    index = load_conversations_index(data_dir)
    for item in index:
        candidate_id = item.get("id", "")
        if not candidate_id or not _conversation_file_exists(data_dir, candidate_id):
            continue
        try:
            conversation = load_conversation(data_dir, candidate_id)
            set_last_active_conversation(data_dir, candidate_id)
            return conversation
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            continue

    conversation = create_conversation(data_dir)
    set_last_active_conversation(data_dir, str(conversation["id"]))
    return conversation


def get_or_create_latest_conversation(data_dir: Path) -> Conversation:
    """Backward-compatible name. Prefer get_last_active_conversation()."""
    return get_last_active_conversation(data_dir)


def get_recent_conversations(data_dir: Path) -> list[ConversationIndexItem]:
    return load_conversations_index(data_dir)


def create_conversation(data_dir: Path, title: str = DEFAULT_TITLE) -> Conversation:
    ensure_conversation_storage(data_dir)
    created_at = now_string()
    conversation_id = str(uuid.uuid4())
    conversation: Conversation = {
        "id": conversation_id,
        "title": title,
        "summary": "",
        "summary_updated_at": "",
        "created_at": created_at,
        "updated_at": created_at,
        "messages": [],
    }
    save_conversation(data_dir, conversation)

    index = [item for item in load_conversations_index(data_dir) if item.get("id") != conversation_id]
    index.insert(
        0,
        {
            "id": conversation_id,
            "title": title,
            "created_at": created_at,
            "updated_at": created_at,
        },
    )
    save_conversations_index(data_dir, index)
    set_last_active_conversation(data_dir, conversation_id)
    return conversation


def load_conversation(data_dir: Path, conversation_id: str) -> Conversation:
    path = _existing_conversation_path(data_dir, conversation_id)
    if path is None:
        raise FileNotFoundError(f"Conversation file not found: {conversation_id}")
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError:
        get_logger(data_dir.parent).exception("conversation file invalid id=%s path=%s", conversation_id, path)
        raise
    if not isinstance(data, dict):
        raise ValueError("Conversation file must contain a JSON object.")
    conversation = _normalize_conversation(data)
    if path.name == legacy_conversation_path(data_dir, conversation_id).name:
        save_conversation(data_dir, conversation)
    return conversation


def save_conversation(data_dir: Path, conversation: Conversation) -> None:
    conversations_dir(data_dir).mkdir(parents=True, exist_ok=True)
    normalized = _normalize_conversation(conversation)
    with conversation_path(data_dir, str(normalized["id"])).open("w", encoding="utf-8") as file:
        json.dump(normalized, file, ensure_ascii=False, indent=2)
        file.write("\n")


def delete_conversation(data_dir: Path, conversation_id: str) -> None:
    index = [item for item in load_conversations_index(data_dir) if item.get("id") != conversation_id]
    save_conversations_index(data_dir, index)
    for path in (conversation_path(data_dir, conversation_id), legacy_conversation_path(data_dir, conversation_id)):
        if path.exists():
            _move_to_trash(data_dir, path)

    state = load_app_state(data_dir)
    if state.get("last_active_conversation_id") == conversation_id:
        remaining = load_conversations_index(data_dir)
        next_id = remaining[0]["id"] if remaining else ""
        set_last_active_conversation(data_dir, next_id)


def rename_conversation(data_dir: Path, conversation_id: str, new_title: str) -> Conversation:
    new_title = new_title.strip()
    if not new_title:
        raise ValueError("标题不能为空。")
    conversation = load_conversation(data_dir, conversation_id)
    conversation["title"] = new_title
    conversation["updated_at"] = now_string()
    save_conversation(data_dir, conversation)
    _update_index_item(data_dir, conversation)
    return conversation


def append_message(
    data_dir: Path,
    conversation_id: str,
    role: str,
    content: str,
    extra: dict[str, Any] | None = None,
) -> Conversation:
    if role not in {"user", "assistant"}:
        raise ValueError("role must be 'user' or 'assistant'.")
    conversation = load_conversation(data_dir, conversation_id)
    now = now_string()
    message: dict[str, Any] = {
        "role": role,
        "content": content,
        "created_at": now,
    }
    if extra:
        message.update(extra)
    conversation.setdefault("messages", []).append(message)
    conversation["updated_at"] = now
    save_conversation(data_dir, conversation)
    _update_index_item(data_dir, conversation)
    set_last_active_conversation(data_dir, conversation_id)
    return conversation


def update_conversation_title(data_dir: Path, conversation_id: str, title: str) -> Conversation:
    title = title.strip() or DEFAULT_TITLE
    conversation = load_conversation(data_dir, conversation_id)
    conversation["title"] = title
    conversation["updated_at"] = now_string()
    save_conversation(data_dir, conversation)
    _update_index_item(data_dir, conversation)
    return conversation


def update_summary(
    data_dir: Path,
    conversation_id: str,
    trigger_rounds: int = 16,
    max_chars: int = 600,
) -> Conversation:
    """Update a short rule-based summary for long conversations without model calls."""
    conversation = load_conversation(data_dir, conversation_id)
    messages = conversation.get("messages", [])
    user_rounds = sum(1 for item in messages if isinstance(item, dict) and item.get("role") == "user")
    if user_rounds <= trigger_rounds:
        return conversation

    max_chars = max(300, min(int(max_chars), 1000))
    snippets: list[str] = []
    for item in messages[-trigger_rounds * 2 :]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        label = "用户" if role == "user" else "bot"
        snippets.append(f"{label}：{_compact(content, 90)}")

    summary = "当前对话主要脉络：\n" + "\n".join(f"- {line}" for line in snippets)
    if len(summary) > max_chars:
        summary = summary[: max_chars - 3].rstrip() + "..."

    conversation["summary"] = summary
    conversation["summary_updated_at"] = now_string()
    save_conversation(data_dir, conversation)
    _update_index_item(data_dir, conversation)
    return conversation


def make_title_from_user_text(text: str) -> str:
    compact = " ".join(text.strip().split())
    if not compact:
        return DEFAULT_TITLE
    title = compact[:18]
    if len(compact) > 18:
        title += "..."
    return title


def conversation_messages_for_ollama(conversation: Conversation, limit_turns: int) -> list[dict[str, str]]:
    messages = conversation.get("messages", [])
    if not isinstance(messages, list):
        return []
    if limit_turns > 0:
        messages = messages[-limit_turns * 2 :]
    result: list[dict[str, str]] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and isinstance(content, str) and content:
            result.append({"role": role, "content": content})
    return result


def _conversation_file_exists(data_dir: Path, conversation_id: str) -> bool:
    return conversation_path(data_dir, conversation_id).exists() or legacy_conversation_path(data_dir, conversation_id).exists()


def _existing_conversation_path(data_dir: Path, conversation_id: str) -> Path | None:
    new_path = conversation_path(data_dir, conversation_id)
    if new_path.exists():
        return new_path
    old_path = legacy_conversation_path(data_dir, conversation_id)
    if old_path.exists():
        return old_path
    return None


def _move_to_trash(data_dir: Path, path: Path) -> Path:
    trash_dir = data_dir / "trash"
    trash_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = trash_dir / f"{path.stem}.deleted.{timestamp}{path.suffix}"
    counter = 1
    while target.exists():
        target = trash_dir / f"{path.stem}.deleted.{timestamp}.{counter}{path.suffix}"
        counter += 1
    shutil.move(str(path), str(target))
    get_logger(data_dir.parent).info("conversation moved to trash source=%s target=%s", path, target)
    return target


def _compact(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _update_index_item(data_dir: Path, conversation: Conversation) -> None:
    index = [item for item in load_conversations_index(data_dir) if item.get("id") != conversation["id"]]
    index.insert(
        0,
        {
            "id": str(conversation["id"]),
            "title": str(conversation.get("title") or DEFAULT_TITLE),
            "created_at": str(conversation.get("created_at") or now_string()),
            "updated_at": str(conversation.get("updated_at") or now_string()),
        },
    )
    save_conversations_index(data_dir, index)


def _normalize_index_item(item: dict[str, Any]) -> ConversationIndexItem:
    return {
        "id": str(item.get("id", "")),
        "title": str(item.get("title") or DEFAULT_TITLE),
        "created_at": str(item.get("created_at") or now_string()),
        "updated_at": str(item.get("updated_at") or item.get("created_at") or now_string()),
    }


def _normalize_conversation(data: dict[str, Any]) -> Conversation:
    conversation_id = str(data.get("id") or uuid.uuid4())
    created_at = str(data.get("created_at") or now_string())
    messages = data.get("messages", [])
    if not isinstance(messages, list):
        messages = []
    normalized_messages: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = message.get("content")
        if role in {"user", "assistant"} and isinstance(content, str):
            normalized = {
                "role": role,
                "content": content,
                "created_at": str(message.get("created_at") or now_string()),
            }
            for key, value in message.items():
                if key not in normalized:
                    normalized[key] = value
            normalized_messages.append(normalized)
    return {
        "id": conversation_id,
        "title": str(data.get("title") or DEFAULT_TITLE),
        "summary": str(data.get("summary") or ""),
        "summary_updated_at": str(data.get("summary_updated_at") or ""),
        "created_at": created_at,
        "updated_at": str(data.get("updated_at") or created_at),
        "messages": normalized_messages,
    }
