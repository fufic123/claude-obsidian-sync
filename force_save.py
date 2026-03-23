#!/usr/bin/env python3
"""
Force-save a Claude conversation to the Obsidian vault, bypassing the classifier.

Usage:
    python3 force_save.py              # saves the most recent conversation
    python3 force_save.py <session-id> # saves a specific session by UUID prefix
"""
from __future__ import annotations

import sys
import logging
from pathlib import Path

# Allow running from any directory
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from src.parser import ConversationParser
from src.formatter import NoteFormatter
from src.writer import VaultWriter
from src.notifier import Notifier

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


class ForceSaver:
    """Finds and force-saves a conversation, bypassing classification."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._parser = ConversationParser()
        self._writer = VaultWriter(config, NoteFormatter(config))
        self._notifier = Notifier()

    def save_latest(self) -> None:
        path = self._find_latest()
        if path is None:
            logger.error("No conversation files found in %s", self._config.claude_projects_dir)
            sys.exit(1)
        self._save(path)

    def save_by_id(self, session_prefix: str) -> None:
        path = self._find_by_prefix(session_prefix)
        if path is None:
            logger.error("No conversation matching '%s'", session_prefix)
            sys.exit(1)
        self._save(path)

    def _save(self, path: Path) -> None:
        logger.info("Force-saving: %s", path.name)
        conversation = self._parser.parse(path)
        if conversation is None:
            logger.error("Could not parse %s", path)
            sys.exit(1)
        if not conversation.messages:
            logger.error("No messages found in %s", path)
            sys.exit(1)
        note_path = self._writer.write(conversation)
        self._notifier.report(
            "Claude Vault Sync",
            f"Saved: {note_path.name}",
        )
        logger.info("Done → %s", note_path)

    def _find_latest(self) -> Path | None:
        files = [
            p for p in self._config.claude_projects_dir.rglob("*.jsonl")
            if "subagents" not in p.parts
        ]
        if not files:
            return None
        return max(files, key=lambda p: p.stat().st_mtime)

    def _find_by_prefix(self, prefix: str) -> Path | None:
        for p in self._config.claude_projects_dir.rglob("*.jsonl"):
            if "subagents" not in p.parts and p.stem.startswith(prefix):
                return p
        return None


if __name__ == "__main__":
    config = Config()
    saver = ForceSaver(config)
    if len(sys.argv) > 1:
        saver.save_by_id(sys.argv[1])
    else:
        saver.save_latest()
