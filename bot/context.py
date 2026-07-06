from __future__ import annotations

from pathlib import Path
from typing import Any

from bot.conversation import Conversation, conversation_messages_for_ollama
from bot.memory import format_memory_for_prompt, load_memory, select_memories_for_context
from bot.persona import load_persona


DEFAULT_CONTEXT_SETTINGS = {
    "recent_rounds": 4,
    "max_memory_items": 10,
    "enable_conversation_summary": True,
    "summary_trigger_rounds": 12,
    "max_summary_chars": 600,
    "include_diary_by_default": False,
}


DEFAULT_COMPANION_PREFERENCES = {
    "tone": "温柔、自然、生活化，像朋友一样接话，少一点客服味。",
    "default_length": "普通闲聊默认 2 到 6 句话，除非用户明确要求详细分析。",
    "emotional_support": "用户诉苦时先接住情绪，不急着给建议。",
    "advice_style": "用户明确要建议时，先简短共情，再给 1 到 3 个可执行建议。",
    "avoid": "不要说教，不要强行分析，不要制造依赖感，不要假装是真人。",
}


def build_layered_messages(
    config: dict[str, Any],
    persona_path: Path,
    memory_path: Path,
    conversation: Conversation,
    latest_user_text: str,
) -> list[dict[str, str]]:
    """Build Ollama messages with stable layered context and short recency."""
    settings = context_settings_from_config(config)
    persona_text = load_persona(persona_path)
    chat_mode = detect_chat_mode(latest_user_text)
    preferences = companion_preferences_from_config(config)
    memories = select_memories_for_context(
        load_memory(memory_path),
        limit=int(settings["max_memory_items"]),
    )

    system_prompt = build_system_prompt(
        persona_text=persona_text,
        chat_mode=chat_mode,
        preferences=preferences,
        memories=memories,
        conversation_summary=str(conversation.get("summary") or ""),
    )
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation_messages_for_ollama(conversation, int(settings["recent_rounds"])))
    return messages


def build_system_prompt(
    persona_text: str,
    chat_mode: str,
    preferences: dict[str, Any],
    memories: list[dict[str, Any]],
    conversation_summary: str,
) -> str:
    return (
        "【人格设定】\n"
        f"{persona_text.strip()}\n\n"
        "【当前聊天模式】\n"
        f"{format_chat_mode(chat_mode)}\n\n"
        "【用户陪聊偏好】\n"
        f"{format_preferences(preferences)}\n\n"
        "【长期记忆】\n"
        f"{format_memory_for_prompt(memories)}\n\n"
        "【当前对话摘要】\n"
        f"{conversation_summary.strip() if conversation_summary.strip() else '暂无当前对话摘要。'}"
    )


def context_settings_from_config(config: dict[str, Any]) -> dict[str, Any]:
    loaded = config.get("context_settings", {})
    settings = dict(DEFAULT_CONTEXT_SETTINGS)
    if isinstance(loaded, dict):
        settings.update(loaded)
    settings["recent_rounds"] = _positive_int(settings.get("recent_rounds"), 4)
    settings["max_memory_items"] = _positive_int(settings.get("max_memory_items"), 10)
    settings["summary_trigger_rounds"] = _positive_int(settings.get("summary_trigger_rounds"), 12)
    settings["max_summary_chars"] = _positive_int(settings.get("max_summary_chars"), 600)
    settings["enable_conversation_summary"] = bool(settings.get("enable_conversation_summary"))
    settings["include_diary_by_default"] = bool(settings.get("include_diary_by_default"))
    return settings


def companion_preferences_from_config(config: dict[str, Any]) -> dict[str, Any]:
    loaded = config.get("companion_preferences", {})
    preferences = dict(DEFAULT_COMPANION_PREFERENCES)
    if isinstance(loaded, dict):
        preferences.update({str(key): value for key, value in loaded.items()})
    return preferences


def detect_chat_mode(user_text: str) -> str:
    text = user_text.strip()
    if not text:
        return "普通陪聊"
    advice_keywords = ["怎么办", "建议", "分析", "规划", "解决", "帮我"]
    learning_keywords = ["代码", "学习", "考试", "项目", "bug", "Python", "python"]
    review_keywords = ["复盘", "总结一下", "整理思路", "梳理"]
    vent_keywords = ["吐槽", "无语", "离谱", "气死", "真服了"]
    distress_keywords = ["累", "烦", "委屈", "难受", "失落", "压力", "孤独", "崩溃", "憋屈"]
    casual_keywords = ["无聊", "聊聊天", "随便聊", "陪我"]

    if any(keyword in text for keyword in learning_keywords):
        return "学习助手"
    if any(keyword in text for keyword in review_keywords):
        return "复盘模式"
    if any(keyword in text for keyword in advice_keywords):
        return "普通陪聊 / 建议辅助"
    if any(keyword in text for keyword in vent_keywords):
        return "吐槽模式"
    if any(keyword in text for keyword in distress_keywords):
        return "诉苦模式"
    if any(keyword in text for keyword in casual_keywords):
        return "轻松闲聊"
    return "普通陪聊"


def format_chat_mode(chat_mode: str) -> str:
    descriptions = {
        "普通陪聊": "普通陪聊：自然接话，轻松陪伴，不急着分析或给建议。",
        "吐槽模式": "吐槽模式：先站在用户视角接住吐槽，可以轻松一点，但不煽动冲动行为。",
        "诉苦模式": "诉苦模式：先共情和理解，一次只轻轻问一个问题，不急着解决。",
        "轻松闲聊": "轻松闲聊：语气放松，可以适度幽默，回复短一点。",
        "学习助手": "学习助手：更清晰、耐心、结构化，但保持温和。",
        "复盘模式": "复盘模式：陪用户梳理脉络，拆小问题，帮助看清下一步。",
        "普通陪聊 / 建议辅助": "建议辅助：先简短共情，再给 1 到 3 个可执行建议，语气像商量。",
    }
    return descriptions.get(chat_mode, descriptions["普通陪聊"])


def format_preferences(preferences: dict[str, Any]) -> str:
    if not preferences:
        return "暂无额外陪聊偏好。"
    return "\n".join(f"* {key}: {value}" for key, value in preferences.items())


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, parsed)

