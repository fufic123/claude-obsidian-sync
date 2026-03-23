from __future__ import annotations

import logging
from pathlib import Path

from config import Config
from src.formatter import NoteFormatter
from src.parser import Conversation

logger = logging.getLogger(__name__)


class VaultWriter:
    """Writes a formatted conversation note to the Obsidian vault."""

    def __init__(self, config: Config, formatter: NoteFormatter) -> None:
        self._config = config
        self._formatter = formatter

    def write(self, conversation: Conversation) -> Path:
        """Write the note and return its path."""
        self._config.vault_conversations_dir.mkdir(parents=True, exist_ok=True)

        filename = self._formatter.make_filename(conversation)
        note_path = self._config.vault_conversations_dir / filename
        content = self._formatter.format(conversation)

        note_path.write_text(content, encoding="utf-8")
        logger.info("Wrote note: %s", note_path)
        return note_path
