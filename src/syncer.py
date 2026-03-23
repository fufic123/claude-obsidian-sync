from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from config import Config
from src.classifier import ConversationClassifier
from src.formatter import NoteFormatter
from src.notifier import Notifier
from src.parser import ConversationParser
from src.writer import VaultWriter

if TYPE_CHECKING:
    from src.monitor import ResourceMonitor

logger = logging.getLogger(__name__)


class ConversationSyncer:
    """Orchestrates parsing, formatting, and writing of a conversation file."""

    def __init__(self, config: Config, monitor: ResourceMonitor | None = None) -> None:
        self._config = config
        self._monitor = monitor
        self._notifier = Notifier()
        self._parser = ConversationParser()
        self._formatter = NoteFormatter(config)
        self._writer = VaultWriter(config, self._formatter)
        self._classifier = ConversationClassifier()
        # State: {"hash": str, "skipped": bool, "processed_lines": int}
        self._state: dict[str, dict] = {}
        self._load_state()
        self._silent: bool = False  # suppresses trigger notifications during initial sync

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def sync_file(self, path: Path) -> bool:
        """Parse, classify, and write the note for *path*. Returns True on success."""
        if self._is_subagent_file(path):
            logger.debug("Skipping subagent file: %s", path)
            return False

        current_hash = self._file_hash(path)
        entry = self._state.get(str(path), {})
        stored_hash = entry.get("hash", "")
        was_skipped = entry.get("skipped", False)
        processed_lines = entry.get("processed_lines", 0)

        if stored_hash == current_hash and not was_skipped:
            logger.debug("File unchanged, skipping: %s", path)
            return False

        # Read all lines to find new ones since last cursor position.
        all_lines = self._read_lines(path)
        total_lines = len(all_lines)
        new_lines = all_lines[processed_lines:]

        # Check triggers only in NEW lines to avoid re-notifying.
        new_user_texts = self._extract_user_texts(new_lines)
        trigger = self._classifier.detect_trigger(new_user_texts)

        logger.info("Syncing: %s", path)
        conversation = self._parser.parse(path)
        if conversation is None:
            return False

        if not conversation.messages:
            logger.warning("No usable messages in %s, skipping", path)
            return False

        result = self._classifier.classify(conversation)
        logger.debug(
            "Classification for %s: should_save=%s reason=%s trigger=%s",
            path.name, result.should_save, result.reason, trigger,
        )

        if not result.should_save:
            filename = self._formatter.make_filename(conversation)
            logger.info("Skipping %s: %s", filename, result.reason)
            self._state[str(path)] = {
                "hash": current_hash, "skipped": True, "processed_lines": total_lines,
            }
            self._save_state()
            if self._monitor is not None:
                self._monitor.record_skipped()
            return False

        note_path = self._writer.write(conversation)
        if trigger == "force_save" and not self._silent:
            self._notifier.report(
                "Claude Vault Sync",
                f"Force-saved: {note_path.name}",
            )
        self._state[str(path)] = {
            "hash": current_hash, "skipped": False, "processed_lines": total_lines,
        }
        self._save_state()
        if self._monitor is not None:
            self._monitor.record_saved()
        return True

    def sync_all_existing(self) -> None:
        """Process all existing JSONL files on startup — silently (no trigger notifications)."""
        self._silent = True
        for path in self._config.claude_projects_dir.rglob("*.jsonl"):
            if not self._is_subagent_file(path):
                self.sync_file(path)
        self._silent = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_subagent_file(self, path: Path) -> bool:
        return "subagents" in path.parts

    def _file_hash(self, path: Path) -> str:
        try:
            stat = path.stat()
            return f"{stat.st_size}-{stat.st_mtime}"
        except OSError:
            return ""

    def _read_lines(self, path: Path) -> list[str]:
        try:
            return path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []

    def _extract_user_texts(self, lines: list[str]) -> list[str]:
        """Extract text from user-type JSONL lines."""
        texts: list[str] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("type") != "user":
                continue
            content = record.get("message", {}).get("content", "")
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        texts.append(block.get("text", ""))
        return texts

    def _load_state(self) -> None:
        if not self._config.state_file.exists():
            return
        try:
            raw = json.loads(self._config.state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not load state file: %s", exc)
            return

        normalised: dict[str, dict] = {}
        for key, value in raw.items():
            if isinstance(value, str):
                normalised[key] = {"hash": value, "skipped": False, "processed_lines": 0}
            elif isinstance(value, dict):
                normalised[key] = value
            else:
                normalised[key] = {"hash": "", "skipped": False, "processed_lines": 0}
        self._state = normalised

    def _save_state(self) -> None:
        try:
            self._config.state_file.parent.mkdir(parents=True, exist_ok=True)
            self._config.state_file.write_text(
                json.dumps(self._state, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            logger.error("Could not save state file: %s", exc)
