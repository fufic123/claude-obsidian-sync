from __future__ import annotations

import re
from pathlib import Path

from config import Config
from src.parser import Conversation, Message


class NoteFormatter:
    """Formats a Conversation into Obsidian markdown."""

    def __init__(self, config: Config) -> None:
        self._config = config

    def format(self, conversation: Conversation) -> str:
        user_messages = [m for m in conversation.messages if m.role == "user"]
        title = self._make_title(user_messages)
        frontmatter = self._make_frontmatter(conversation, title)
        summary = self._make_summary(user_messages)
        body = self._make_body(conversation.messages)
        return f"{frontmatter}\n# {title}\n\n## Summary\n{summary}\n\n---\n\n## Conversation\n\n{body}"

    def make_filename(self, conversation: Conversation) -> str:
        user_messages = [m for m in conversation.messages if m.role == "user"]
        title = self._make_title(user_messages)
        safe_title = self._sanitize_filename(title)
        return f"{conversation.date} - {safe_title}.md"

    def _make_title(self, user_messages: list[Message]) -> str:
        if not user_messages:
            return "Untitled Conversation"
        first_text = user_messages[0].text
        truncated = first_text[: self._config.first_user_message_max_chars]
        if len(first_text) > self._config.first_user_message_max_chars:
            truncated = truncated.rstrip() + "..."
        return truncated

    def _make_frontmatter(self, conversation: Conversation, title: str) -> str:
        return (
            f"---\n"
            f"date: {conversation.date}\n"
            f"session_id: {conversation.session_id}\n"
            f"tags: [claude, conversation]\n"
            f"---\n\n"
        )

    def _make_summary(self, user_messages: list[Message]) -> str:
        count = self._config.summary_message_count
        max_chars = self._config.summary_message_max_chars
        lines = []
        for msg in user_messages[:count]:
            truncated = msg.text[:max_chars]
            if len(msg.text) > max_chars:
                truncated = truncated.rstrip() + "..."
            lines.append(f"- {truncated}")
        return "\n".join(lines) if lines else "- (no messages)"

    def _make_body(self, messages: list[Message]) -> str:
        parts = []
        for msg in messages:
            if msg.role == "user":
                parts.append(f"**User:** {msg.text}\n\n---")
            else:
                parts.append(f"**Claude:** {msg.text}\n\n---")
        return "\n\n".join(parts)

    def _sanitize_filename(self, text: str) -> str:
        # Remove characters not allowed in filenames
        sanitized = re.sub(r'[<>:"/\\|?*\n\r\t]', "", text)
        sanitized = sanitized.strip(". ")
        return sanitized or "Untitled"
