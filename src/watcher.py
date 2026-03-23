from __future__ import annotations

import logging
import threading
from pathlib import Path

from watchdog.events import FileCreatedEvent, FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from config import Config
from src.syncer import ConversationSyncer

logger = logging.getLogger(__name__)


class _JsonlEventHandler(FileSystemEventHandler):
    """Handles file-system events for JSONL files with debouncing."""

    def __init__(self, syncer: ConversationSyncer, debounce_seconds: int) -> None:
        super().__init__()
        self._syncer = syncer
        self._debounce_seconds = debounce_seconds
        # Map of path -> pending timer
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def on_created(self, event: FileCreatedEvent) -> None:
        if not event.is_directory:
            self._schedule(Path(event.src_path))

    def on_modified(self, event: FileModifiedEvent) -> None:
        if not event.is_directory:
            self._schedule(Path(event.src_path))

    def _schedule(self, path: Path) -> None:
        if path.suffix != ".jsonl":
            return
        key = str(path)
        with self._lock:
            # Cancel any existing timer for this file
            existing = self._timers.get(key)
            if existing is not None:
                existing.cancel()
            timer = threading.Timer(
                self._debounce_seconds, self._process, args=(path,)
            )
            timer.daemon = True
            self._timers[key] = timer
            timer.start()
            logger.debug(
                "Debounce timer set for %s (%.0fs)", path.name, self._debounce_seconds
            )

    def _process(self, path: Path) -> None:
        with self._lock:
            self._timers.pop(str(path), None)
        try:
            self._syncer.sync_file(path)
        except Exception as exc:
            logger.error("Error processing %s: %s", path, exc)


class FileWatcher:
    """Watches the Claude projects directory for new/changed JSONL files."""

    def __init__(self, config: Config, syncer: ConversationSyncer) -> None:
        self._config = config
        self._syncer = syncer
        self._observer = Observer()

    def start(self) -> None:
        handler = _JsonlEventHandler(self._syncer, self._config.debounce_seconds)
        watch_path = str(self._config.claude_projects_dir)
        self._observer.schedule(handler, watch_path, recursive=True)
        self._observer.start()
        logger.info(
            "Watching %s (debounce=%ds)",
            self._config.claude_projects_dir,
            self._config.debounce_seconds,
        )

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join()
        logger.info("File watcher stopped.")

    def join(self) -> None:
        """Block until the observer thread exits."""
        self._observer.join()
