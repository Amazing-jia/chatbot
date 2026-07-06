from __future__ import annotations

from pathlib import Path

from bot.diary import add_diary_entry, format_diary_entries, get_recent_entries
from bot.diary import get_today_entries, search_diary_entries
from bot.memory import add_memory, forget_memory, format_memory_for_display, load_memory
from bot.memory import pop_memory_warning


def handle_memory_command(text: str, memory_path: Path) -> tuple[bool, str, bool]:
    """Handle memory/chat commands.

    Returns:
        handled: whether this was a local command
        message: message to show to the user
        should_exit: whether the app should exit
    """
    command = text.strip()

    if command == "/memory":
        memories = load_memory(memory_path)
        return True, _with_warning(memory_path, format_memory_for_display(memories)), False

    if command.startswith("/remember "):
        content = command.removeprefix("/remember ").strip()
        if not content:
            return True, "请输入要记住的内容，例如：/remember 我喜欢简洁的回答。", False
        add_memory(memory_path, content)
        return True, _with_warning(memory_path, f"已记住：{content}"), False

    if command.startswith("/forget "):
        keyword = command.removeprefix("/forget ").strip()
        if not keyword:
            return True, "请输入要删除的关键词，例如：/forget 咖啡", False
        deleted = forget_memory(memory_path, keyword)
        if not deleted:
            return True, _with_warning(memory_path, f"没有找到包含“{keyword}”的记忆。"), False
        return True, _with_warning(memory_path, f"已删除 {len(deleted)} 条包含“{keyword}”的记忆。"), False

    if command == "/exit":
        return True, "已收到退出命令。", True

    return False, "", False


def handle_diary_command(text: str, diary_path: Path) -> tuple[bool, str]:
    """Handle local diary commands.

    Returns:
        handled: whether this was a diary command
        message: message to show to the user
    """
    command = text.strip()

    if command.startswith("/diary "):
        content = command.removeprefix("/diary ").strip()
        if not content:
            return True, "请输入日记内容，例如：/diary 今天散步时感觉轻松了一点。"
        add_diary_entry(diary_path, content)
        return True, "已写入今天的日记。"

    if command == "/diary_today":
        entries = get_today_entries(diary_path)
        return True, format_diary_entries(entries, "今天还没有日记。")

    if command == "/diary_recent":
        entries = get_recent_entries(diary_path, limit=7)
        return True, format_diary_entries(entries, "还没有日记记录。")

    if command.startswith("/diary_search "):
        keyword = command.removeprefix("/diary_search ").strip()
        if not keyword:
            return True, "请输入搜索关键词，例如：/diary_search 散步"
        entries = search_diary_entries(diary_path, keyword)
        return True, format_diary_entries(entries, f"没有找到包含“{keyword}”的日记。")

    return False, ""


def _with_warning(memory_path: Path, message: str) -> str:
    warning = pop_memory_warning(memory_path)
    if not warning:
        return message
    return f"{warning}\n{message}"
