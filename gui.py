from __future__ import annotations

import queue
import threading
import time
from dataclasses import asdict
from datetime import datetime
from tkinter import messagebox, simpledialog
from typing import Any

import customtkinter as ctk

from bot.commands import handle_diary_command, handle_memory_command
from bot.config import load_config, resolve_path, save_config
from bot.context import build_layered_messages, context_settings_from_config
from bot.conversation import (
    append_message as append_conversation_message,
    create_conversation,
    delete_conversation,
    get_last_active_conversation,
    load_conversation,
    load_conversations_index,
    make_title_from_user_text,
    rename_conversation,
    set_last_active_conversation,
    update_summary,
    update_conversation_title,
)
from bot.diary import add_diary_entry, get_today_entries, search_diary_entries
from bot.feedback import ensure_feedback_files, save_disliked, save_liked, save_rewrite
from bot.history import append_chat_record
from bot.logger import get_logger
from bot.memory import add_memory, delete_memory_by_id, load_memory
from bot.ollama_client import OllamaClient, OllamaConnectionError, OllamaResponseError
from main import BASE_DIR, format_speed_line


class Theme:
    app_bg = "#F6F8FB"
    shell = "#FFFFFF"
    sidebar = "#F8FAFF"
    panel = "#FFFFFF"
    panel_soft = "#F8FAFC"
    border = "#E5EAF2"
    text = "#0F172A"
    body = "#334155"
    muted = "#64748B"
    soft_text = "#94A3B8"
    faint = "#CBD5E1"
    blue = "#3B82F6"
    blue_dark = "#2563EB"
    blue_soft = "#DBEAFE"
    blue_pale = "#EAF2FF"
    green = "#22C55E"
    bot_avatar = "#EFF6FF"
    bot_bubble = "#FFFFFF"
    user_bubble = "#3B82F6"
    system_bubble = "#F8FAFC"


FONT = "Microsoft YaHei UI"


class ChatGui(ctk.CTk):
    """CustomTkinter desktop UI with chat, memory, diary, and settings pages."""

    def __init__(self) -> None:
        super().__init__()

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.config_path = BASE_DIR / "config.yaml"
        self.config = load_config(BASE_DIR)
        self.logger = get_logger(BASE_DIR)
        self._apply_theme_config(self.config.get("theme", {}))

        self.title("Bot Buddy")
        self.geometry("1120x720")
        self.minsize(1000, 650)
        self.configure(fg_color=Theme.app_bg)

        self.response_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.is_sending = False
        self.stop_requested = False
        self.streaming_message_index: int | None = None
        self.placeholder = "输入你的消息..."
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self.conversation_buttons: dict[str, ctk.CTkButton] = {}
        self.current_page = ""
        self.chat_messages: list[tuple[str, str, str]] = []

        self._load_runtime_from_config(self.config)
        self.data_dir = BASE_DIR / "data"
        ensure_feedback_files(self.data_dir)
        self.current_conversation = get_last_active_conversation(self.data_dir)
        self.current_conversation_id = str(self.current_conversation["id"])
        self.logger.info(
            "app startup model=%s ollama_url=%s conversation_id=%s",
            self.model,
            self.ollama_url,
            self.current_conversation_id,
        )
        self.chat_messages = self._messages_from_conversation(self.current_conversation)
        self.client = OllamaClient(
            base_url=self.ollama_url,
            model=self.model,
            timeout=self.timeout,
        )

        self._build_layout()
        self.show_chat_page()
        self._set_status(f"当前模型：{self.client.model}")
        self._refresh_models_async()
        self._poll_queue()

    def _apply_theme_config(self, theme: object) -> None:
        if not isinstance(theme, dict):
            return
        Theme.app_bg = str(theme.get("background_color") or Theme.app_bg)
        Theme.sidebar = str(theme.get("sidebar_color") or Theme.sidebar)
        Theme.blue = str(theme.get("primary_color") or Theme.blue)
        Theme.blue_dark = str(theme.get("accent_color") or Theme.blue_dark)

    def _load_runtime_from_config(self, config: dict[str, Any]) -> None:
        self.model = str(config.get("model", "qwen3:8b"))
        self.ollama_url = str(config.get("ollama_url", "http://localhost:11434/api/chat"))
        self.timeout = int(config.get("request_timeout", 120))
        self.history_turns = int(config.get("history_turns_in_context", 8))
        self.persona_path = resolve_path(BASE_DIR, config.get("persona_path", "prompts/persona.md"))
        self.memory_path = resolve_path(BASE_DIR, config.get("memory_path", "data/memory.json"))
        self.diary_path = resolve_path(BASE_DIR, config.get("diary_path", "data/diary.jsonl"))
        self.history_path = resolve_path(BASE_DIR, config.get("history_path", "data/chat_history.jsonl"))

    def _messages_from_conversation(self, conversation: dict[str, Any]) -> list[tuple[str, str, str]]:
        messages: list[tuple[str, str, str]] = []
        for item in conversation.get("messages", []):
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if role not in {"user", "assistant"} or not isinstance(content, str):
                continue
            speaker = "\u4f60" if role == "user" else "bot"
            timestamp = self._time_from_created_at(str(item.get("created_at") or ""))
            messages.append((speaker, content, timestamp))
        return messages

    def _time_from_created_at(self, created_at: str) -> str:
        try:
            return datetime.fromisoformat(created_at).strftime("%H:%M")
        except ValueError:
            return self._now_time()

    def _load_current_conversation(self) -> None:
        self.current_conversation = load_conversation(self.data_dir, self.current_conversation_id)
        self.chat_messages = self._messages_from_conversation(self.current_conversation)

    def _conversation_title(self) -> str:
        return str(self.current_conversation.get("title") or "\u65b0\u5bf9\u8bdd")

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.shell = ctk.CTkFrame(
            self,
            fg_color=Theme.shell,
            corner_radius=24,
            border_width=1,
            border_color=Theme.border,
        )
        self.shell.grid(row=0, column=0, sticky="nsew", padx=24, pady=22)
        self.shell.grid_columnconfigure(1, weight=1)
        self.shell.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(
            self.shell,
            width=220,
            fg_color=Theme.sidebar,
            corner_radius=22,
        )
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_columnconfigure(0, weight=1)

        self.main_content_frame = ctk.CTkFrame(
            self.shell,
            fg_color=Theme.panel,
            corner_radius=22,
        )
        self.main_content_frame.grid(row=0, column=1, sticky="nsew")
        self.main_content_frame.grid_columnconfigure(0, weight=1)
        self.main_content_frame.grid_rowconfigure(1, weight=1)

        self._build_sidebar()

    def _build_sidebar(self) -> None:
        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=22, pady=(28, 24))
        brand.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            brand,
            text="Bot Buddy",
            text_color=Theme.text,
            font=ctk.CTkFont(family=FONT, size=20, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            brand,
            text="本地陪聊助手",
            text_color=Theme.soft_text,
            font=ctk.CTkFont(family=FONT, size=12),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 0))

        nav = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        nav.grid(row=1, column=0, sticky="ew", padx=14)
        nav.grid_columnconfigure(0, weight=1)

        self.new_chat_button = ctk.CTkButton(
            nav,
            text="+  \u65b0\u5efa\u5bf9\u8bdd",
            height=40,
            corner_radius=12,
            fg_color=Theme.blue,
            hover_color=Theme.blue_dark,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family=FONT, size=12, weight="bold"),
            anchor="w",
            command=self._new_conversation,
        )
        self.new_chat_button.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        nav_items = [
            ("\u5bf9\u8bdd", "\U0001f4ac", self.show_chat_page),
            ("\u8bb0\u5fc6", "\U0001f9e0", self.show_memory_page),
            ("\u65e5\u8bb0", "\u2713", self.show_diary_page),
            ("\u8bbe\u7f6e", "\u2699", self.show_settings_page),
        ]
        for row, (name, icon, command) in enumerate(nav_items, start=1):
            button = ctk.CTkButton(
                nav,
                text=f"{icon}  {name}",
                height=42,
                corner_radius=12,
                fg_color="transparent",
                hover_color=Theme.blue_pale,
                text_color=Theme.muted,
                font=ctk.CTkFont(family=FONT, size=12),
                anchor="w",
                command=command,
            )
            button.grid(row=row, column=0, sticky="ew", pady=3)
            self.nav_buttons[name] = button

        history_wrap = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        history_wrap.grid(row=2, column=0, sticky="nsew", padx=14, pady=(16, 0))
        history_wrap.grid_columnconfigure(0, weight=1)
        history_wrap.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            history_wrap,
            text="\u5386\u53f2\u5bf9\u8bdd",
            text_color=Theme.muted,
            font=ctk.CTkFont(family=FONT, size=12, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=4, pady=(0, 8))
        self.conversation_list_frame = ctk.CTkScrollableFrame(
            history_wrap,
            fg_color="transparent",
            corner_radius=0,
            height=190,
            scrollbar_button_color=Theme.border,
            scrollbar_button_hover_color=Theme.faint,
        )
        self.conversation_list_frame.grid(row=1, column=0, sticky="nsew")
        self.conversation_list_frame.grid_columnconfigure(0, weight=1)
        self._refresh_conversation_list()

        model_box = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        model_box.grid(row=3, column=0, sticky="ew", padx=18, pady=(16, 0))
        model_box.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            model_box,
            text="本地模型",
            text_color=Theme.muted,
            font=ctk.CTkFont(family=FONT, size=12, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.model_var = ctk.StringVar(value=self.model)
        self.model_combo = ctk.CTkComboBox(
            model_box,
            variable=self.model_var,
            values=[self.model],
            height=36,
            corner_radius=12,
            border_width=1,
            border_color=Theme.border,
            fg_color=Theme.panel,
            button_color=Theme.panel,
            button_hover_color=Theme.panel_soft,
            dropdown_fg_color=Theme.panel,
            dropdown_hover_color=Theme.blue_pale,
            text_color=Theme.body,
            font=ctk.CTkFont(family=FONT, size=11),
        )
        self.model_combo.grid(row=1, column=0, sticky="ew")

        buttons = ctk.CTkFrame(model_box, fg_color="transparent")
        buttons.grid(row=2, column=0, sticky="ew", pady=(9, 0))
        buttons.grid_columnconfigure((0, 1), weight=1)
        self.refresh_button = self._soft_button(buttons, "刷新", self._refresh_models_async)
        self.refresh_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.switch_button = self._soft_button(buttons, "切换", self._switch_model)
        self.switch_button.grid(row=0, column=1, sticky="ew", padx=(5, 0))

        self.sidebar.grid_rowconfigure(2, weight=1)
        self.sidebar.grid_rowconfigure(4, weight=0)
        bottom = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        bottom.grid(row=5, column=0, sticky="ew", padx=22, pady=(0, 24))
        bottom.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            bottom,
            text="●",
            text_color=Theme.green,
            font=ctk.CTkFont(family=FONT, size=14),
            width=12,
        ).grid(row=0, column=0, padx=(0, 8), sticky="w")
        ctk.CTkLabel(
            bottom,
            text="专注陪伴中",
            text_color=Theme.muted,
            font=ctk.CTkFont(family=FONT, size=12),
            anchor="w",
        ).grid(row=0, column=1, sticky="ew")
        self.status_var = ctk.StringVar(value="准备就绪")
        ctk.CTkLabel(
            bottom,
            textvariable=self.status_var,
            text_color=Theme.soft_text,
            font=ctk.CTkFont(family=FONT, size=10),
            anchor="w",
            justify="left",
            wraplength=170,
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))

    def _soft_button(self, parent: ctk.CTkFrame, text: str, command: object) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            height=34,
            corner_radius=12,
            fg_color=Theme.panel,
            hover_color=Theme.panel_soft,
            text_color=Theme.muted,
            border_width=1,
            border_color=Theme.border,
            font=ctk.CTkFont(family=FONT, size=11),
            command=command,
        )

    def _refresh_conversation_list(self) -> None:
        if not hasattr(self, "conversation_list_frame"):
            return
        for child in self.conversation_list_frame.winfo_children():
            child.destroy()
        self.conversation_buttons.clear()

        for row, item in enumerate(load_conversations_index(self.data_dir)):
            conversation_id = item.get("id", "")
            title = self._compact_title(item.get("title", "\u65b0\u5bf9\u8bdd"), 15)
            active = conversation_id == self.current_conversation_id

            row_frame = ctk.CTkFrame(
                self.conversation_list_frame,
                fg_color=Theme.blue_pale if active else "transparent",
                corner_radius=12,
            )
            row_frame.grid(row=row, column=0, sticky="ew", pady=3)
            row_frame.grid_columnconfigure(0, weight=1)

            title_button = ctk.CTkButton(
                row_frame,
                text=title,
                height=34,
                corner_radius=10,
                fg_color="transparent",
                hover_color=Theme.blue_pale,
                text_color=Theme.blue_dark if active else Theme.muted,
                font=ctk.CTkFont(family=FONT, size=11),
                anchor="w",
                command=lambda cid=conversation_id: self._switch_conversation(cid),
            )
            title_button.grid(row=0, column=0, sticky="ew", padx=(4, 0), pady=3)
            self.conversation_buttons[conversation_id] = title_button

            self._tiny_button(row_frame, "\u270e", lambda cid=conversation_id: self._rename_conversation(cid)).grid(
                row=0,
                column=1,
                padx=(2, 0),
                pady=3,
            )
            self._tiny_button(row_frame, "\u00d7", lambda cid=conversation_id: self._delete_conversation(cid)).grid(
                row=0,
                column=2,
                padx=(2, 4),
                pady=3,
            )

    def _tiny_button(self, parent: ctk.CTkFrame, text: str, command: object) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            width=26,
            height=30,
            corner_radius=9,
            fg_color="transparent",
            hover_color=Theme.panel_soft,
            text_color=Theme.soft_text,
            font=ctk.CTkFont(family=FONT, size=13),
            command=command,
        )

    def _compact_title(self, title: str, limit: int = 18) -> str:
        title = " ".join(str(title).split()) or "\u65b0\u5bf9\u8bdd"
        return title if len(title) <= limit else title[:limit] + "..."

    def _new_conversation(self) -> None:
        if self.is_sending:
            self._set_status("\u751f\u6210\u4e2d\uff0c\u8bf7\u5148\u505c\u6b62\u6216\u7b49\u5f85\u5b8c\u6210\u3002")
            return
        self.current_conversation = create_conversation(self.data_dir)
        self.current_conversation_id = str(self.current_conversation["id"])
        set_last_active_conversation(self.data_dir, self.current_conversation_id)
        self._load_current_conversation()
        self._refresh_conversation_list()
        self.show_chat_page()
        self._set_status("\u5df2\u65b0\u5efa\u5bf9\u8bdd")

    def _switch_conversation(self, conversation_id: str) -> None:
        if self.is_sending:
            self._set_status("\u751f\u6210\u4e2d\uff0c\u8bf7\u5148\u505c\u6b62\u6216\u7b49\u5f85\u5b8c\u6210\u3002")
            return
        try:
            self.current_conversation_id = conversation_id
            set_last_active_conversation(self.data_dir, conversation_id)
            self._load_current_conversation()
            self._refresh_conversation_list()
            self.show_chat_page()
            self._set_status("\u5df2\u5207\u6362\u5bf9\u8bdd")
        except Exception as exc:
            messagebox.showerror("\u5207\u6362\u5931\u8d25", str(exc))

    def _delete_conversation(self, conversation_id: str) -> None:
        if self.is_sending:
            self._set_status("\u751f\u6210\u4e2d\uff0c\u8bf7\u5148\u505c\u6b62\u6216\u7b49\u5f85\u5b8c\u6210\u3002")
            return
        if not messagebox.askyesno("\u5220\u9664\u5bf9\u8bdd", "\u786e\u5b9a\u8981\u5220\u9664\u8fd9\u4e2a\u5bf9\u8bdd\u5417\uff1f"):
            return
        delete_conversation(self.data_dir, conversation_id)
        if conversation_id == self.current_conversation_id:
            self.current_conversation = get_last_active_conversation(self.data_dir)
            self.current_conversation_id = str(self.current_conversation["id"])
            set_last_active_conversation(self.data_dir, self.current_conversation_id)
            self._load_current_conversation()
            self.show_chat_page()
        self._refresh_conversation_list()
        self._set_status("\u5df2\u5220\u9664\u5bf9\u8bdd")

    def _rename_conversation(self, conversation_id: str) -> None:
        if self.is_sending:
            self._set_status("\u751f\u6210\u4e2d\uff0c\u8bf7\u5148\u505c\u6b62\u6216\u7b49\u5f85\u5b8c\u6210\u3002")
            return
        current_title = "\u65b0\u5bf9\u8bdd"
        for item in load_conversations_index(self.data_dir):
            if item.get("id") == conversation_id:
                current_title = item.get("title", current_title)
                break
        new_title = simpledialog.askstring(
            "\u91cd\u547d\u540d\u5bf9\u8bdd",
            "\u8bf7\u8f93\u5165\u65b0\u6807\u9898\uff1a",
            initialvalue=current_title,
            parent=self,
        )
        if new_title is None:
            return
        try:
            conversation = rename_conversation(self.data_dir, conversation_id, new_title)
            if conversation_id == self.current_conversation_id:
                self.current_conversation = conversation
                self.show_chat_page()
            self._refresh_conversation_list()
            self._set_status("\u5df2\u91cd\u547d\u540d\u5bf9\u8bdd")
        except Exception as exc:
            messagebox.showerror("\u91cd\u547d\u540d\u5931\u8d25", str(exc))

    def clear_main_content(self) -> None:
        for child in self.main_content_frame.winfo_children():
            child.destroy()
        self.main_content_frame.grid_columnconfigure(0, weight=1)
        self.main_content_frame.grid_rowconfigure(1, weight=1)

    def set_active_nav(self, name: str) -> None:
        self.current_page = name
        for button_name, button in self.nav_buttons.items():
            active = button_name == name
            button.configure(
                fg_color=Theme.blue_soft if active else "transparent",
                text_color=Theme.blue_dark if active else Theme.muted,
                font=ctk.CTkFont(family=FONT, size=12, weight="bold" if active else "normal"),
            )

    def _page_header(self, title: str, subtitle: str = "") -> None:
        header = ctk.CTkFrame(self.main_content_frame, fg_color=Theme.panel, height=72, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(0, weight=1)
        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=0, sticky="w", padx=32, pady=14)
        ctk.CTkLabel(
            title_box,
            text=title,
            text_color=Theme.text,
            font=ctk.CTkFont(family=FONT, size=16, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        if subtitle:
            ctk.CTkLabel(
                title_box,
                text=subtitle,
                text_color=Theme.soft_text,
                font=ctk.CTkFont(family=FONT, size=11),
                anchor="w",
            ).grid(row=1, column=0, sticky="w", pady=(3, 0))
        ctk.CTkFrame(self.main_content_frame, fg_color=Theme.border, height=1, corner_radius=0).grid(
            row=0,
            column=0,
            sticky="sew",
        )

    def show_chat_page(self) -> None:
        self.clear_main_content()
        self.set_active_nav("\u5bf9\u8bdd")
        self._build_chat_page()
        for index, (speaker, text, timestamp) in enumerate(self.chat_messages):
            self._render_message(speaker, text, timestamp, index)
        self._set_status(f"当前模型：{self.client.model}")

    def _build_chat_page(self) -> None:
        header = ctk.CTkFrame(self.main_content_frame, fg_color=Theme.panel, height=72, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)
        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=0, sticky="w", padx=32, pady=18)
        ctk.CTkLabel(
            title_box,
            text="●",
            text_color=Theme.blue,
            font=ctk.CTkFont(family=FONT, size=13),
            width=16,
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkLabel(
            title_box,
            text=self._compact_title(self._conversation_title(), 28),
            text_color=Theme.text,
            font=ctk.CTkFont(family=FONT, size=16, weight="bold"),
        ).grid(row=0, column=1, sticky="w")
        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=2, sticky="e", padx=28)
        for col, (text, command) in enumerate(
            [
                ("⌕", lambda: self._set_status("搜索功能后续接入。")),
                ("↻", self._refresh_models_async),
                ("⋯", lambda: self._set_status(f"当前模型：{self.client.model}")),
            ]
        ):
            self._icon_button(actions, text, command).grid(row=0, column=col, padx=4)
        ctk.CTkFrame(self.main_content_frame, fg_color=Theme.border, height=1, corner_radius=0).grid(
            row=0,
            column=0,
            sticky="sew",
        )
        self.message_list = ctk.CTkScrollableFrame(
            self.main_content_frame,
            fg_color=Theme.panel,
            corner_radius=0,
            scrollbar_button_color=Theme.border,
            scrollbar_button_hover_color=Theme.faint,
        )
        self.message_list.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self.message_list.grid_columnconfigure(0, weight=1)
        self._build_input()

    def _icon_button(self, parent: ctk.CTkFrame, text: str, command: object) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            width=34,
            height=34,
            corner_radius=10,
            fg_color="transparent",
            hover_color=Theme.panel_soft,
            text_color=Theme.muted,
            font=ctk.CTkFont(family=FONT, size=15),
            command=command,
        )

    def _build_input(self) -> None:
        input_wrap = ctk.CTkFrame(self.main_content_frame, fg_color=Theme.panel, corner_radius=0)
        input_wrap.grid(row=2, column=0, sticky="ew", padx=32, pady=(0, 24))
        input_wrap.grid_columnconfigure(0, weight=1)
        self.input_shell = ctk.CTkFrame(
            input_wrap,
            fg_color=Theme.panel,
            corner_radius=18,
            border_width=1,
            border_color=Theme.border,
        )
        self.input_shell.grid(row=0, column=0, sticky="ew")
        self.input_shell.grid_columnconfigure(0, weight=1)
        self.input_text = ctk.CTkTextbox(
            self.input_shell,
            height=58,
            fg_color=Theme.panel,
            text_color=Theme.faint,
            border_width=0,
            corner_radius=16,
            font=ctk.CTkFont(family=FONT, size=14),
            wrap="word",
        )
        self.input_text.grid(row=0, column=0, sticky="ew", padx=(8, 0), pady=5)
        self.input_text.insert("1.0", self.placeholder)
        self.input_text.bind("<FocusIn>", self._clear_placeholder)
        self.input_text.bind("<FocusOut>", self._restore_placeholder)
        self.input_text.bind("<Return>", self._on_enter)
        self.input_text.bind("<Shift-Return>", self._on_shift_enter)
        self.send_button = ctk.CTkButton(
            self.input_shell,
            text="➤",
            width=38,
            height=38,
            corner_radius=19,
            fg_color=Theme.blue,
            hover_color=Theme.blue_dark,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family=FONT, size=15, weight="bold"),
            command=self._send_message,
        )
        self.send_button.grid(row=0, column=2, padx=(8, 12), pady=10)

        self.stop_button = ctk.CTkButton(
            self.input_shell,
            text="停止",
            width=58,
            height=38,
            corner_radius=19,
            fg_color=Theme.panel_soft,
            hover_color=Theme.blue_pale,
            text_color=Theme.muted,
            font=ctk.CTkFont(family=FONT, size=12),
            command=self._stop_generation,
            state="disabled",
        )
        self.stop_button.grid(row=0, column=1, padx=(8, 0), pady=10)

    def show_memory_page(self) -> None:
        self.clear_main_content()
        self.set_active_nav("\u8bb0\u5fc6")
        self._page_header("长期记忆", "这些内容会作为背景信息帮助 bot 更懂你。")

        body = ctk.CTkScrollableFrame(
            self.main_content_frame,
            fg_color=Theme.panel,
            corner_radius=0,
            scrollbar_button_color=Theme.border,
            scrollbar_button_hover_color=Theme.faint,
        )
        body.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        body.grid_columnconfigure(0, weight=1)

        add_card = self._card(body)
        add_card.grid(row=0, column=0, sticky="ew", padx=32, pady=(26, 12))
        add_card.grid_columnconfigure(0, weight=1)
        self.memory_input = ctk.CTkEntry(
            add_card,
            placeholder_text="写下一条希望 bot 记住的长期信息...",
            height=40,
            corner_radius=12,
            border_width=1,
            border_color=Theme.border,
            fg_color=Theme.panel,
            text_color=Theme.body,
            font=ctk.CTkFont(family=FONT, size=13),
        )
        self.memory_input.grid(row=0, column=0, sticky="ew", padx=18, pady=18)
        ctk.CTkButton(
            add_card,
            text="添加记忆",
            width=110,
            height=40,
            corner_radius=12,
            fg_color=Theme.blue,
            hover_color=Theme.blue_dark,
            command=self._add_memory_from_page,
        ).grid(row=0, column=1, padx=(0, 18), pady=18)

        memories = load_memory(self.memory_path)
        if not memories:
            self._empty_text(body, "暂无长期记忆。").grid(row=1, column=0, sticky="ew", padx=32, pady=18)
            return

        for index, item in enumerate(memories, start=1):
            self._memory_card(body, item).grid(row=index, column=0, sticky="ew", padx=32, pady=8)

    def _add_memory_from_page(self) -> None:
        content = self.memory_input.get().strip()
        if not content:
            self._set_status("记忆内容不能为空")
            return
        add_memory(self.memory_path, content)
        self._set_status("已添加记忆")
        self.show_memory_page()

    def _memory_card(self, parent: ctk.CTkFrame, item: dict[str, str]) -> ctk.CTkFrame:
        card = self._card(parent)
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            card,
            text=item.get("content", ""),
            text_color=Theme.body,
            font=ctk.CTkFont(family=FONT, size=14),
            anchor="w",
            justify="left",
            wraplength=620,
        ).grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 4))
        ctk.CTkLabel(
            card,
            text=item.get("created_at", ""),
            text_color=Theme.faint,
            font=ctk.CTkFont(family=FONT, size=11),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 16))
        ctk.CTkButton(
            card,
            text="删除",
            width=72,
            height=32,
            corner_radius=10,
            fg_color=Theme.panel_soft,
            hover_color=Theme.blue_pale,
            text_color=Theme.muted,
            command=lambda memory_id=item.get("id", ""): self._delete_memory(memory_id),
        ).grid(row=0, column=1, rowspan=2, padx=(8, 18), pady=16)
        return card

    def _delete_memory(self, memory_id: str) -> None:
        if delete_memory_by_id(self.memory_path, memory_id):
            self._set_status("已删除记忆")
        else:
            self._set_status("没有找到这条记忆")
        self.show_memory_page()

    def show_diary_page(self) -> None:
        self.clear_main_content()
        self.set_active_nav("\u65e5\u8bb0")
        self._page_header("日记", "记录今天的想法、心情和复盘。")

        body = ctk.CTkScrollableFrame(
            self.main_content_frame,
            fg_color=Theme.panel,
            corner_radius=0,
            scrollbar_button_color=Theme.border,
            scrollbar_button_hover_color=Theme.faint,
        )
        body.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        body.grid_columnconfigure(0, weight=1)

        write_card = self._card(body)
        write_card.grid(row=0, column=0, sticky="ew", padx=32, pady=(26, 12))
        write_card.grid_columnconfigure(0, weight=1)
        self.diary_text = ctk.CTkTextbox(
            write_card,
            height=96,
            corner_radius=12,
            border_width=1,
            border_color=Theme.border,
            fg_color=Theme.panel,
            text_color=Theme.body,
            font=ctk.CTkFont(family=FONT, size=13),
            wrap="word",
        )
        self.diary_text.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 10))
        ctk.CTkButton(
            write_card,
            text="写入今日日记",
            width=130,
            height=38,
            corner_radius=12,
            fg_color=Theme.blue,
            hover_color=Theme.blue_dark,
            command=self._add_diary_from_page,
        ).grid(row=1, column=0, sticky="e", padx=18, pady=(0, 18))

        search_card = self._card(body)
        search_card.grid(row=1, column=0, sticky="ew", padx=32, pady=12)
        search_card.grid_columnconfigure(0, weight=1)
        self.diary_search_input = ctk.CTkEntry(
            search_card,
            placeholder_text="搜索日记关键词...",
            height=38,
            corner_radius=12,
            border_width=1,
            border_color=Theme.border,
            fg_color=Theme.panel,
            text_color=Theme.body,
            font=ctk.CTkFont(family=FONT, size=13),
        )
        self.diary_search_input.grid(row=0, column=0, sticky="ew", padx=18, pady=18)
        ctk.CTkButton(
            search_card,
            text="搜索",
            width=90,
            height=38,
            corner_radius=12,
            fg_color=Theme.panel_soft,
            hover_color=Theme.blue_pale,
            text_color=Theme.muted,
            command=self._search_diary_from_page,
        ).grid(row=0, column=1, padx=(0, 18), pady=18)

        self.diary_results_frame = ctk.CTkFrame(body, fg_color="transparent")
        self.diary_results_frame.grid(row=2, column=0, sticky="ew", padx=32, pady=(10, 24))
        self.diary_results_frame.grid_columnconfigure(0, weight=1)
        self._render_diary_entries(get_today_entries(self.diary_path), "今日日记", "今天还没有日记。")

    def _add_diary_from_page(self) -> None:
        content = self.diary_text.get("1.0", "end").strip()
        if not content:
            self._set_status("日记内容不能为空")
            return
        add_diary_entry(self.diary_path, content)
        self._set_status("已写入今日日记")
        self.show_diary_page()

    def _search_diary_from_page(self) -> None:
        keyword = self.diary_search_input.get().strip()
        if not keyword:
            self._set_status("请输入搜索关键词")
            return
        self._render_diary_entries(
            search_diary_entries(self.diary_path, keyword),
            f"搜索结果：{keyword}",
            f"没有找到包含“{keyword}”的日记。",
        )

    def _render_diary_entries(self, entries: list[dict[str, str]], title: str, empty_text: str) -> None:
        for child in self.diary_results_frame.winfo_children():
            child.destroy()
        ctk.CTkLabel(
            self.diary_results_frame,
            text=title,
            text_color=Theme.text,
            font=ctk.CTkFont(family=FONT, size=14, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))
        if not entries:
            self._empty_text(self.diary_results_frame, empty_text).grid(row=1, column=0, sticky="ew")
            return
        for index, entry in enumerate(entries, start=1):
            self._diary_card(self.diary_results_frame, entry).grid(
                row=index,
                column=0,
                sticky="ew",
                pady=8,
            )

    def _diary_card(self, parent: ctk.CTkFrame, entry: dict[str, str]) -> ctk.CTkFrame:
        card = self._card(parent)
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            card,
            text=entry.get("content", ""),
            text_color=Theme.body,
            font=ctk.CTkFont(family=FONT, size=14),
            anchor="w",
            justify="left",
            wraplength=680,
        ).grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 4))
        ctk.CTkLabel(
            card,
            text=entry.get("created_at", ""),
            text_color=Theme.faint,
            font=ctk.CTkFont(family=FONT, size=11),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 16))
        return card

    def show_settings_page(self) -> None:
        self.clear_main_content()
        self.set_active_nav("\u8bbe\u7f6e")
        self._page_header("设置", "修改常用本地配置。")

        scroll = ctk.CTkScrollableFrame(
            self.main_content_frame,
            fg_color=Theme.panel,
            corner_radius=0,
            scrollbar_button_color=Theme.border,
            scrollbar_button_hover_color=Theme.faint,
        )
        scroll.grid(row=1, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        card = self._card(scroll)
        card.grid(row=0, column=0, sticky="ew", padx=34, pady=28)
        card.grid_columnconfigure(1, weight=1)
        config = load_config(BASE_DIR)
        self.settings_entries: dict[str, ctk.CTkEntry | ctk.CTkComboBox] = {}
        rows = [
            ("model", "模型名称", "默认 qwen3:8b。"),
            ("ollama_url", "Ollama API 地址", "可填写 http://localhost:11434 或完整 /api/chat 地址。"),
            ("persona_path", "人格提示词路径", "默认 prompts/persona.md。"),
            ("memory_path", "记忆文件路径", "默认 data/memory.json。"),
            ("diary_path", "日记文件路径", "默认 data/diary.jsonl。"),
            ("history_path", "聊天记录路径", "默认 data/chat_history.jsonl。"),
        ]
        for row_index, (key, label, help_text) in enumerate(rows):
            self._settings_entry_row(card, row_index, key, label, help_text, str(config.get(key, "")))
        self.settings_message_var = ctk.StringVar(value="")
        ctk.CTkLabel(
            card,
            textvariable=self.settings_message_var,
            text_color=Theme.muted,
            font=ctk.CTkFont(family=FONT, size=12),
            anchor="w",
        ).grid(row=len(rows) * 2, column=1, sticky="ew", padx=(0, 24), pady=(6, 0))
        ctk.CTkButton(
            card,
            text="保存设置",
            height=42,
            corner_radius=14,
            fg_color=Theme.blue,
            hover_color=Theme.blue_dark,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family=FONT, size=13, weight="bold"),
            command=self._save_settings,
        ).grid(row=len(rows) * 2 + 1, column=1, sticky="e", padx=(0, 24), pady=(14, 24))
        ctk.CTkButton(
            card,
            text="\u68c0\u6d4b\u672c\u5730\u6a21\u578b\u670d\u52a1",
            height=38,
            corner_radius=14,
            fg_color=Theme.panel_soft,
            hover_color=Theme.blue_pale,
            text_color=Theme.muted,
            font=ctk.CTkFont(family=FONT, size=12),
            command=self._check_model_service_async,
        ).grid(row=len(rows) * 2 + 1, column=0, sticky="w", padx=(24, 18), pady=(14, 24))

    def _settings_entry_row(
        self,
        parent: ctk.CTkFrame,
        row: int,
        key: str,
        label: str,
        help_text: str,
        value: str,
    ) -> None:
        ctk.CTkLabel(
            parent,
            text=label,
            text_color=Theme.text,
            font=ctk.CTkFont(family=FONT, size=13, weight="bold"),
            anchor="w",
        ).grid(row=row * 2, column=0, sticky="nw", padx=(24, 18), pady=(16, 4))
        entry = ctk.CTkEntry(
            parent,
            height=38,
            corner_radius=12,
            border_width=1,
            border_color=Theme.border,
            fg_color=Theme.panel,
            text_color=Theme.body,
            font=ctk.CTkFont(family=FONT, size=12),
        )
        entry.insert(0, value)
        entry.grid(row=row * 2, column=1, sticky="ew", padx=(0, 24), pady=(16, 4))
        self.settings_entries[key] = entry
        ctk.CTkLabel(
            parent,
            text=help_text,
            text_color=Theme.soft_text,
            font=ctk.CTkFont(family=FONT, size=11),
            anchor="w",
            wraplength=560,
            justify="left",
        ).grid(row=row * 2 + 1, column=1, sticky="ew", padx=(0, 24), pady=(0, 6))

    def _save_settings(self) -> None:
        try:
            values = {key: widget.get().strip() for key, widget in self.settings_entries.items()}
            required = {
                "model": "模型名称",
                "ollama_url": "Ollama API 地址",
                "persona_path": "人格提示词路径",
                "memory_path": "记忆文件路径",
                "diary_path": "日记文件路径",
                "history_path": "聊天记录路径",
            }
            for key, label in required.items():
                if not values.get(key):
                    self._show_settings_error(f"{label}不能为空。")
                    return
            for key in ("persona_path", "memory_path", "diary_path", "history_path"):
                if any(char in values[key] for char in '<>"|?*'):
                    self._show_settings_error(f"{required[key]}包含 Windows 不支持的字符。")
                    return
            config = load_config(BASE_DIR)
            config.update(values)
            save_config(self.config_path, config)
            self.config = load_config(BASE_DIR)
            self._reload_runtime_from_config(self.config)
            self.settings_message_var.set("保存成功。新的配置已应用到后续聊天。")
            self._set_status("设置已保存")
        except Exception as exc:
            self._show_settings_error(f"保存失败：{exc}")

    def _show_settings_error(self, message: str) -> None:
        if hasattr(self, "settings_message_var"):
            self.settings_message_var.set(message)
        self._set_status(message)

    def _check_model_service_async(self) -> None:
        if hasattr(self, "settings_message_var"):
            self.settings_message_var.set("\u6b63\u5728\u68c0\u6d4b\u672c\u5730\u6a21\u578b\u670d\u52a1...")
        self._set_status("\u6b63\u5728\u68c0\u6d4b Ollama...")
        thread = threading.Thread(target=self._check_model_service_worker, daemon=True)
        thread.start()

    def _check_model_service_worker(self) -> None:
        started = time.perf_counter()
        try:
            models = self.client.list_models()
            elapsed = time.perf_counter() - started
            if self.client.model in models:
                message = "\u672c\u5730\u6a21\u578b\u670d\u52a1\u6b63\u5e38"
            else:
                message = f"\u5f53\u524d\u6a21\u578b\u672a\u5b89\u88c5\uff0c\u8bf7\u5148\u8fd0\u884c ollama pull {self.client.model}"
            self.logger.info(
                "service check model=%s models=%s elapsed=%.3fs",
                self.client.model,
                len(models),
                elapsed,
            )
            self.response_queue.put(("service_check_result", message))
        except OllamaConnectionError as exc:
            self.logger.warning("service check connection failed error=%s", exc)
            self.response_queue.put(("service_check_result", "\u672a\u68c0\u6d4b\u5230 Ollama"))
        except OllamaResponseError as exc:
            self.logger.warning("service check response failed error=%s", exc)
            self.response_queue.put(("service_check_result", f"Ollama \u8fd4\u56de\u5f02\u5e38\uff1a{exc}"))
        except Exception as exc:
            self.logger.exception("service check unknown error=%s", exc)
            self.response_queue.put(("service_check_result", f"\u8bf7\u6c42\u8d85\u65f6\u6216\u68c0\u6d4b\u5931\u8d25\uff1a{exc}"))

    def _friendly_ollama_error(self, error: object) -> str:
        text = str(error)
        lowered = text.lower()
        if isinstance(error, OllamaConnectionError):
            if "\u8d85\u65f6" in text or "timeout" in lowered:
                return "\u8bf7\u6c42\u8d85\u65f6\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5\u3002"
            return "\u672a\u68c0\u6d4b\u5230\u672c\u5730\u6a21\u578b\u670d\u52a1\uff0c\u8bf7\u5148\u542f\u52a8 Ollama\u3002"
        if isinstance(error, OllamaResponseError):
            if "not found" in lowered or "pull" in lowered or "404" in lowered:
                return f"\u5f53\u524d\u6a21\u578b\u672a\u5b89\u88c5\uff0c\u8bf7\u5148\u8fd0\u884c ollama pull {self.client.model}\u3002"
            return f"Ollama \u8fd4\u56de\u5f02\u5e38\uff1a{text}"
        return f"\u53d1\u751f\u672a\u77e5\u9519\u8bef\uff1a{text}"

    def _reload_runtime_from_config(self, config: dict[str, Any]) -> None:
        self._apply_theme_config(config.get("theme", {}))
        self._load_runtime_from_config(config)
        self.client.set_model(self.model)
        self.client.set_base_url(self.ollama_url)
        self.client.timeout = self.timeout
        self.model_var.set(self.model)

    def _card(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        return ctk.CTkFrame(
            parent,
            fg_color=Theme.panel,
            corner_radius=18,
            border_width=1,
            border_color=Theme.border,
        )

    def _empty_text(self, parent: ctk.CTkFrame, text: str) -> ctk.CTkLabel:
        return ctk.CTkLabel(
            parent,
            text=text,
            text_color=Theme.soft_text,
            font=ctk.CTkFont(family=FONT, size=13),
            anchor="w",
            justify="left",
        )

    def _clear_placeholder(self, _event: object) -> None:
        if self.input_text.get("1.0", "end").strip() == self.placeholder:
            self.input_text.delete("1.0", "end")
            self.input_text.configure(text_color=Theme.body)
        self.input_shell.configure(border_color="#93C5FD")

    def _restore_placeholder(self, _event: object) -> None:
        if not self.input_text.get("1.0", "end").strip():
            self.input_text.insert("1.0", self.placeholder)
            self.input_text.configure(text_color=Theme.faint)
        self.input_shell.configure(border_color=Theme.border)

    def _append_message(self, speaker: str, text: str) -> int:
        timestamp = self._now_time()
        self.chat_messages.append((speaker, text, timestamp))
        index = len(self.chat_messages) - 1
        if self.current_page in {"\u5bf9\u8bdd", "???"} and hasattr(self, "message_list"):
            self._render_message(speaker, text, timestamp, index)
        return index

    def _update_message(self, index: int, text: str) -> None:
        if index < 0 or index >= len(self.chat_messages):
            return
        speaker, _old_text, timestamp = self.chat_messages[index]
        self.chat_messages[index] = (speaker, text, timestamp)
        if self.current_page in {"\u5bf9\u8bdd", "???"} and hasattr(self, "message_list"):
            self._rerender_chat_messages()

    def _rerender_chat_messages(self) -> None:
        for child in self.message_list.winfo_children():
            child.destroy()
        for index, (speaker, text, timestamp) in enumerate(self.chat_messages):
            self._render_message(speaker, text, timestamp, index)

    def _render_message(self, speaker: str, text: str, timestamp: str, message_index: int | None = None) -> None:
        is_user = speaker == "\u4f60"
        is_system = speaker != "bot" and not is_user
        row = ctk.CTkFrame(self.message_list, fg_color="transparent")
        row.grid(row=len(self.message_list.winfo_children()), column=0, sticky="ew", padx=38, pady=(18, 0))
        row.grid_columnconfigure(0, weight=1)
        row.grid_columnconfigure(1, weight=0)
        row.grid_columnconfigure(2, weight=1)
        if is_system:
            content = self._system_message(row, text)
            content.grid(row=0, column=1)
        elif is_user:
            content = self._user_message(row, text, timestamp)
            content.grid(row=0, column=2, sticky="e")
        else:
            content = self._bot_message(row, text, timestamp, message_index)
            content.grid(row=0, column=0, sticky="w")
        self.after(50, self._scroll_to_bottom)

    def _clear_messages(self) -> None:
        self.chat_messages.clear()
        if hasattr(self, "message_list"):
            for child in self.message_list.winfo_children():
                child.destroy()

    def _bot_message(
        self,
        parent: ctk.CTkFrame,
        text: str,
        timestamp: str,
        message_index: int | None = None,
    ) -> ctk.CTkFrame:
        group = ctk.CTkFrame(parent, fg_color="transparent")
        group.grid_columnconfigure(1, weight=1)
        avatar = ctk.CTkFrame(group, width=36, height=36, corner_radius=18, fg_color=Theme.bot_avatar)
        avatar.grid(row=0, column=0, sticky="nw", padx=(0, 12))
        avatar.grid_propagate(False)
        ctk.CTkLabel(
            avatar,
            text="B",
            text_color=Theme.blue_dark,
            font=ctk.CTkFont(family=FONT, size=12, weight="bold"),
        ).place(relx=0.5, rely=0.5, anchor="center")
        bubble_col = ctk.CTkFrame(group, fg_color="transparent")
        bubble_col.grid(row=0, column=1, sticky="w")
        bubble = ctk.CTkFrame(
            bubble_col,
            fg_color=Theme.bot_bubble,
            corner_radius=16,
            border_width=1,
            border_color=Theme.border,
        )
        bubble.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            bubble,
            text=text,
            text_color=Theme.body,
            font=ctk.CTkFont(family=FONT, size=14),
            justify="left",
            anchor="w",
            wraplength=520,
        ).grid(row=0, column=0, padx=16, pady=12)
        self._timestamp(bubble_col, "w", timestamp).grid(row=1, column=0, sticky="w", pady=(5, 0))
        if self._should_show_feedback(message_index):
            self._feedback_bar(bubble_col, message_index, text).grid(row=2, column=0, sticky="w", pady=(6, 0))
        return group

    def _should_show_feedback(self, message_index: int | None) -> bool:
        if message_index is None:
            return False
        if self.is_sending and message_index == self.streaming_message_index:
            return False
        return bool(self._previous_user_message(message_index))

    def _feedback_bar(self, parent: ctk.CTkFrame, message_index: int, assistant_reply: str) -> ctk.CTkFrame:
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        buttons = [
            ("\u559c\u6b22", lambda: self._save_feedback("liked", message_index, assistant_reply)),
            ("\u4e0d\u559c\u6b22", lambda: self._save_feedback("disliked", message_index, assistant_reply)),
            ("\u6539\u5199", lambda: self._save_feedback("rewrite", message_index, assistant_reply)),
        ]
        for column, (text, command) in enumerate(buttons):
            ctk.CTkButton(
                bar,
                text=text,
                width=48 if column != 1 else 58,
                height=24,
                corner_radius=9,
                fg_color=Theme.panel_soft,
                hover_color=Theme.blue_pale,
                text_color=Theme.soft_text,
                font=ctk.CTkFont(family=FONT, size=10),
                command=command,
            ).grid(row=0, column=column, padx=(0, 6))
        return bar

    def _save_feedback(self, kind: str, message_index: int, assistant_reply: str) -> None:
        user_message = self._previous_user_message(message_index)
        chat_mode = self._detect_chat_mode(user_message)
        try:
            if kind == "liked":
                save_liked(
                    self.data_dir,
                    self.current_conversation_id,
                    user_message,
                    assistant_reply,
                    chat_mode,
                )
                self._set_status("\u5df2\u4fdd\u5b58\u201c\u559c\u6b22\u201d\u53cd\u9988")
            elif kind == "disliked":
                reason = simpledialog.askstring(
                    "\u4e0d\u559c\u6b22\u7684\u539f\u56e0",
                    "\u53ef\u4ee5\u5199\u4e00\u53e5\u539f\u56e0\uff0c\u4e5f\u53ef\u4ee5\u7559\u7a7a\uff1a",
                    parent=self,
                )
                save_disliked(
                    self.data_dir,
                    self.current_conversation_id,
                    user_message,
                    assistant_reply,
                    chat_mode,
                    reason or "",
                )
                self._set_status("\u5df2\u4fdd\u5b58\u201c\u4e0d\u559c\u6b22\u201d\u53cd\u9988")
            elif kind == "rewrite":
                ideal_reply = simpledialog.askstring(
                    "\u6539\u5199\u8fd9\u6b21\u56de\u590d",
                    "\u4f60\u5e0c\u671b bot \u8fd9\u6837\u56de\u590d\uff1a",
                    parent=self,
                )
                if not ideal_reply:
                    return
                save_rewrite(
                    self.data_dir,
                    self.current_conversation_id,
                    user_message,
                    assistant_reply,
                    ideal_reply,
                    chat_mode,
                )
                self._set_status("\u5df2\u4fdd\u5b58\u201c\u6539\u5199\u201d\u53cd\u9988")
        except Exception as exc:
            messagebox.showerror("\u53cd\u9988\u4fdd\u5b58\u5931\u8d25", str(exc))

    def _previous_user_message(self, message_index: int) -> str:
        for index in range(message_index - 1, -1, -1):
            speaker, text, _timestamp = self.chat_messages[index]
            if speaker == "\u4f60":
                return text
        return ""

    def _detect_chat_mode(self, user_message: str) -> str:
        text = user_message.strip()
        if not text:
            return "unknown"
        advice_keywords = ["\u600e\u4e48\u529e", "\u5efa\u8bae", "\u5206\u6790", "\u89c4\u5212", "\u89e3\u51b3", "\u5e2e\u6211"]
        learning_keywords = ["\u4ee3\u7801", "\u5b66\u4e60", "\u8003\u8bd5", "\u9879\u76ee", "bug", "Python", "python"]
        emotion_keywords = ["\u7d2f", "\u70e6", "\u59d4\u5c48", "\u96be\u53d7", "\u5931\u843d", "\u538b\u529b", "\u5b64\u72ec", "\u5d29\u6e83"]
        vent_keywords = ["\u5410\u69fd", "\u65e0\u8bed", "\u79bb\u8c31", "\u6c14\u6b7b", "\u771f\u670d\u4e86"]
        if any(keyword in text for keyword in advice_keywords):
            return "advice"
        if any(keyword in text for keyword in learning_keywords):
            return "learning"
        if any(keyword in text for keyword in vent_keywords):
            return "venting"
        if any(keyword in text for keyword in emotion_keywords):
            return "emotional_support"
        return "casual"

    def _user_message(self, parent: ctk.CTkFrame, text: str, timestamp: str) -> ctk.CTkFrame:
        group = ctk.CTkFrame(parent, fg_color="transparent")
        bubble = ctk.CTkFrame(group, fg_color=Theme.user_bubble, corner_radius=16)
        bubble.grid(row=0, column=0, sticky="e")
        ctk.CTkLabel(
            bubble,
            text=text,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family=FONT, size=14),
            justify="left",
            anchor="w",
            wraplength=520,
        ).grid(row=0, column=0, padx=16, pady=12)
        self._timestamp(group, "e", timestamp).grid(row=1, column=0, sticky="e", pady=(5, 0))
        return group

    def _system_message(self, parent: ctk.CTkFrame, text: str) -> ctk.CTkFrame:
        group = ctk.CTkFrame(parent, fg_color="transparent")
        bubble = ctk.CTkFrame(
            group,
            fg_color=Theme.system_bubble,
            corner_radius=14,
            border_width=1,
            border_color=Theme.border,
        )
        bubble.grid(row=0, column=0)
        ctk.CTkLabel(
            bubble,
            text=text,
            text_color=Theme.muted,
            font=ctk.CTkFont(family=FONT, size=12),
            justify="center",
            wraplength=460,
        ).grid(row=0, column=0, padx=14, pady=9)
        return group

    def _timestamp(self, parent: ctk.CTkFrame, anchor: str, timestamp: str) -> ctk.CTkLabel:
        return ctk.CTkLabel(
            parent,
            text=timestamp,
            text_color=Theme.faint,
            font=ctk.CTkFont(family=FONT, size=11),
            anchor=anchor,
        )

    def _scroll_to_bottom(self) -> None:
        try:
            self.message_list._parent_canvas.yview_moveto(1.0)
        except AttributeError:
            pass

    def _on_enter(self, _event: object) -> str:
        self._send_message()
        return "break"

    def _on_shift_enter(self, _event: object) -> None:
        return None

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _set_sending_state(self, sending: bool) -> None:
        self.is_sending = sending
        state = "disabled" if sending else "normal"
        if hasattr(self, "send_button"):
            self.send_button.configure(state=state)
        if hasattr(self, "stop_button"):
            self.stop_button.configure(state="normal" if sending else "disabled")
        self.switch_button.configure(state=state)
        self.refresh_button.configure(state=state)
        if hasattr(self, "new_chat_button"):
            self.new_chat_button.configure(state=state)
        for button in self.nav_buttons.values():
            button.configure(state=state)
        for button in self.conversation_buttons.values():
            button.configure(state=state)

    def _stop_generation(self) -> None:
        if not self.is_sending:
            return
        self.stop_requested = True
        self.stop_button.configure(state="disabled")
        self._set_status("正在停止生成...")

    def _switch_model(self) -> None:
        model = self.model_var.get().strip()
        if not model:
            messagebox.showinfo("模型名为空", "请输入或选择一个模型名。")
            return
        self.client.set_model(model)
        self._set_status(f"已切换模型：{self.client.model}")
        self._append_message("系统", f"已切换模型：{self.client.model}")

    def _refresh_models_async(self) -> None:
        self._set_status("正在读取本地模型列表...")
        thread = threading.Thread(target=self._refresh_models_worker, daemon=True)
        thread.start()

    def _refresh_models_worker(self) -> None:
        try:
            models = self.client.list_models()
            self.response_queue.put(("models", models))
        except Exception as exc:
            self.response_queue.put(("models_error", exc))

    def _send_message(self) -> None:
        if self.is_sending:
            return
        user_text = self.input_text.get("1.0", "end").strip()
        if not user_text or user_text == self.placeholder:
            return
        self.input_text.delete("1.0", "end")
        self.input_text.configure(text_color=Theme.body)
        if user_text == "/clear":
            self._clear_messages()
            self._append_message("系统", "已清空当前聊天窗口。聊天记录文件不会被删除。")
            self._set_status("已清空当前聊天窗口")
            return
        handled_diary, diary_message = handle_diary_command(user_text, self.diary_path)
        if handled_diary:
            self._append_message("系统", diary_message)
            self._set_status("已处理日记命令")
            return
        handled, command_message, should_exit = handle_memory_command(user_text, self.memory_path)
        if handled:
            if should_exit:
                self._append_message("系统", "正在退出。")
                self.after(200, self.destroy)
                return
            self._append_message("系统", command_message)
            self._set_status("已处理本地命令")
            return
        try:
            conversation_before = load_conversation(self.data_dir, self.current_conversation_id)
            was_empty = len(conversation_before.get("messages", [])) == 0
            self.current_conversation = append_conversation_message(
                self.data_dir,
                self.current_conversation_id,
                "user",
                user_text,
            )
            if was_empty:
                self.current_conversation = update_conversation_title(
                    self.data_dir,
                    self.current_conversation_id,
                    make_title_from_user_text(user_text),
                )
            self._refresh_conversation_list()
        except Exception as exc:
            self._append_message("\u7cfb\u7edf", f"\u4fdd\u5b58\u5bf9\u8bdd\u5931\u8d25\uff1a{exc}")
            self._set_status("\u4fdd\u5b58\u5bf9\u8bdd\u5931\u8d25")
            return

        self._append_message("\u4f60", user_text)
        bot_index = self._append_message("bot", "\u6b63\u5728\u601d\u8003...")
        self.streaming_message_index = bot_index
        self.stop_requested = False
        self._set_status("\u6b63\u5728\u751f\u6210\u56de\u590d...")
        self._set_sending_state(True)
        thread = threading.Thread(
            target=self._chat_worker,
            args=(user_text, bot_index, self.current_conversation_id),
            daemon=True,
        )
        thread.start()

    def _chat_worker(self, user_text: str, bot_index: int, conversation_id: str) -> None:
        request_started = time.perf_counter()
        first_token_at: float | None = None
        conversation = load_conversation(self.data_dir, conversation_id)
        messages = build_layered_messages(
            self.config,
            self.persona_path,
            self.memory_path,
            conversation,
            user_text,
        )
        self.logger.info(
            "chat request start conversation_id=%s model=%s input_chars=%s context_messages=%s",
            conversation_id,
            self.client.model,
            len(user_text),
            len(messages),
        )
        try:
            for event in self.client.stream_chat(messages, should_stop=lambda: self.stop_requested):
                event_type = event.get("type")
                if event_type == "content":
                    if first_token_at is None:
                        first_token_at = time.perf_counter()
                        self.logger.info(
                            "chat first token conversation_id=%s first_token_seconds=%.3f",
                            conversation_id,
                            first_token_at - request_started,
                        )
                    self.response_queue.put(("stream_chunk", (bot_index, event.get("content", ""))))
                    continue

                if event_type == "done":
                    result = event["result"]
                    interrupted = bool(event.get("interrupted"))
                    metrics = asdict(result)
                    metrics["interrupted"] = interrupted
                    if result.content:
                        assistant_text = result.content
                    else:
                        assistant_text = "（已停止，尚未生成内容。）" if interrupted else ""
                    updated_conversation = append_conversation_message(
                        self.data_dir,
                        conversation_id,
                        "assistant",
                        assistant_text,
                    )
                    settings = context_settings_from_config(self.config)
                    if settings["enable_conversation_summary"]:
                        updated_conversation = update_summary(
                            self.data_dir,
                            conversation_id,
                            trigger_rounds=int(settings["summary_trigger_rounds"]),
                            max_chars=int(settings["max_summary_chars"]),
                        )
                    if conversation_id == self.current_conversation_id:
                        self.current_conversation = updated_conversation
                    total_elapsed = time.perf_counter() - request_started
                    self.logger.info(
                        "chat request done conversation_id=%s interrupted=%s first_token_seconds=%s total_seconds=%.3f output_chars=%s",
                        conversation_id,
                        interrupted,
                        f"{first_token_at - request_started:.3f}" if first_token_at else "",
                        total_elapsed,
                        len(assistant_text),
                    )
                    append_chat_record(
                        self.history_path,
                        user_text,
                        assistant_text,
                        self.client.model,
                        metrics=metrics,
                    )
                    self.response_queue.put(("stream_done", (bot_index, result, interrupted)))
                    return
        except Exception as exc:
            self.logger.exception("chat request failed conversation_id=%s error=%s", conversation_id, exc)
            self.response_queue.put(("chat_error", (bot_index, exc)))

    def _poll_queue(self) -> None:
        try:
            while True:
                event, payload = self.response_queue.get_nowait()
                self._handle_event(event, payload)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _handle_event(self, event: str, payload: object) -> None:
        if event == "models":
            models = payload if isinstance(payload, list) else []
            if models:
                self.model_combo.configure(values=models)
                self._set_status(f"已读取 {len(models)} 个模型")
            else:
                self._set_status("没有读取到本地模型")
            return
        if event == "models_error":
            self._set_status("读取模型失败，请确认 Ollama 已启动")
            return
        if event == "service_check_result":
            message = str(payload)
            if hasattr(self, "settings_message_var"):
                self.settings_message_var.set(message)
            self._set_status(message)
            return
        if event == "chat_result":
            self._set_sending_state(False)
            if hasattr(payload, "content"):
                self._append_message("bot", payload.content)
                self._set_status(format_speed_line(payload))
            return
        if event == "stream_chunk":
            bot_index, chunk = payload
            if not isinstance(bot_index, int) or not isinstance(chunk, str):
                return
            current_text = self.chat_messages[bot_index][1] if 0 <= bot_index < len(self.chat_messages) else ""
            if current_text == "正在思考...":
                next_text = chunk
            else:
                next_text = current_text + chunk
            self._update_message(bot_index, next_text)
            self._set_status("正在生成回复...")
            return
        if event == "stream_done":
            bot_index, result, interrupted = payload
            self._set_sending_state(False)
            self.stop_requested = False
            self.streaming_message_index = None
            try:
                self.current_conversation = load_conversation(self.data_dir, self.current_conversation_id)
                self._refresh_conversation_list()
            except Exception:
                pass
            if isinstance(bot_index, int) and hasattr(result, "content"):
                current_text = self.chat_messages[bot_index][1] if 0 <= bot_index < len(self.chat_messages) else ""
                if result.content:
                    self._update_message(bot_index, result.content)
                elif interrupted and current_text == "正在思考...":
                    self._update_message(bot_index, "（已停止，尚未生成内容。）")
                if interrupted:
                    self._set_status("已停止生成，部分回复已保存。")
                else:
                    self._set_status(format_speed_line(result))
            return
        if event == "chat_error":
            self._set_sending_state(False)
            bot_index: int | None = None
            error_payload = payload
            if isinstance(payload, tuple) and len(payload) == 2:
                maybe_index, maybe_error = payload
                if isinstance(maybe_index, int):
                    bot_index = maybe_index
                    error_payload = maybe_error
            self.stop_requested = False
            self.streaming_message_index = None
            message = self._friendly_ollama_error(error_payload)
            self.logger.exception("chat error conversation_id=%s error=%s", self.current_conversation_id, error_payload)
            self._set_status(message)
            if bot_index is not None:
                self._update_message(bot_index, message)
            else:
                self._append_message("\u7cfb\u7edf", message)
            return
    def _now_time(self) -> str:
        return datetime.now().strftime("%H:%M")


def main() -> int:
    try:
        app = ChatGui()
        app.mainloop()
        return 0
    except Exception as exc:
        messagebox.showerror("启动失败", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
