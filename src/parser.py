from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Message:
    role: str  # "user" or "assistant"
    text: str
    timestamp: str


@dataclass
class Conversation:
    session_id: str
    date: str  # ISO date YYYY-MM-DD from first message timestamp
    messages: list[Message] = field(default_factory=list)
    tool_use_count: int = 0


class ConversationParser:
    """Parses a Claude JSONL conversation file into a structured Conversation."""

    def parse(self, path: Path) -> Conversation | None:
        try:
            return self._parse_file(path)
        except Exception as exc:
            logger.error("Failed to parse %s: %s", path, exc)
            return None

    def _parse_file(self, path: Path) -> Conversation | None:
        lines = path.read_text(encoding="utf-8").splitlines()
        records = self._load_records(lines)

        session_id, date = self._extract_metadata(records)
        if not session_id:
            logger.warning("No session_id found in %s", path)
            return None

        messages = self._extract_messages(records)
        if not messages:
            logger.warning("No messages found in %s", path)
            return None

        tool_use_count = self._count_tool_uses(records)
        return Conversation(
            session_id=session_id,
            date=date,
            messages=messages,
            tool_use_count=tool_use_count,
        )

    def _load_records(self, lines: list[str]) -> list[dict]:
        records = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.debug("Skipping malformed JSON line: %s", exc)
        return records

    def _extract_metadata(self, records: list[dict]) -> tuple[str, str]:
        session_id = ""
        date = ""
        for record in records:
            if not session_id and "sessionId" in record:
                session_id = record["sessionId"]
            if not date and "timestamp" in record:
                date = record["timestamp"][:10]  # YYYY-MM-DD
            if session_id and date:
                break
        return session_id, date

    def _extract_messages(self, records: list[dict]) -> list[Message]:
        messages = []
        seen_uuids: set[str] = set()

        for record in records:
            msg_type = record.get("type")
            uuid = record.get("uuid", "")

            if msg_type not in ("user", "assistant"):
                continue

            # Deduplicate: Claude may emit partial assistant messages followed
            # by a final complete one (same uuid, later entry wins).
            # We process all and let duplicates overwrite by uuid.
            if msg_type == "user":
                text = self._extract_user_text(record)
                if text and not self._is_system_message(text):
                    msg = Message(
                        role="user",
                        text=text,
                        timestamp=record.get("timestamp", ""),
                    )
                    if uuid and uuid in seen_uuids:
                        # Replace last occurrence with same uuid
                        for i in range(len(messages) - 1, -1, -1):
                            if messages[i].role == "user" and messages[i].timestamp == msg.timestamp:
                                messages[i] = msg
                                break
                    else:
                        messages.append(msg)
                        if uuid:
                            seen_uuids.add(uuid)

            elif msg_type == "assistant":
                text = self._extract_assistant_text(record)
                if text:
                    msg = Message(
                        role="assistant",
                        text=text,
                        timestamp=record.get("timestamp", ""),
                    )
                    if uuid and uuid in seen_uuids:
                        for i in range(len(messages) - 1, -1, -1):
                            if messages[i].role == "assistant":
                                messages[i] = msg
                                break
                    else:
                        messages.append(msg)
                        if uuid:
                            seen_uuids.add(uuid)

        return messages

    def _count_tool_uses(self, records: list[dict]) -> int:
        """Count assistant content items with type == 'tool_use' across all records."""
        count = 0
        for record in records:
            if record.get("type") != "assistant":
                continue
            content = record.get("message", {}).get("content", [])
            if not isinstance(content, list):
                continue
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_use":
                    count += 1
        return count

    def _extract_user_text(self, record: dict) -> str:
        content = record.get("message", {}).get("content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", "").strip())
            return "\n".join(parts).strip()
        return ""

    def _extract_assistant_text(self, record: dict) -> str:
        content = record.get("message", {}).get("content", [])
        if not isinstance(content, list):
            return ""
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", "").strip())
        return "\n".join(parts).strip()

    def _is_system_message(self, text: str) -> bool:
        """Filter out internal Claude Code system messages."""
        system_prefixes = (
            "[Request interrupted by user]",
            "[Request interrupted by user for tool",
        )
        return any(text.startswith(prefix) for prefix in system_prefixes)
