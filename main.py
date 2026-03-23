#!/usr/bin/env python3
"""
claude-vault-sync: Watch Claude Code conversation files and sync them to Obsidian.

Usage:
    python main.py [--no-initial-sync] [--log-level LEVEL]
"""
import argparse
import logging
import signal
import sys

try:
    from setproctitle import setproctitle
    setproctitle("claude-vault-sync")
except ImportError:
    pass

from config import Config
from src.monitor import ResourceMonitor
from src.notifier import Notifier
from src.syncer import ConversationSyncer
from src.watcher import FileWatcher


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-initial-sync",
        action="store_true",
        help="Skip syncing existing files on startup.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    _configure_logging(args.log_level)
    logger = logging.getLogger(__name__)

    config = Config()
    notifier = Notifier()
    monitor = ResourceMonitor(config, notifier)
    syncer = ConversationSyncer(config, monitor)
    watcher = FileWatcher(config, syncer)

    monitor.start()
    notifier.report("Claude Vault Sync", "Started — watching for conversations 👁")

    if not args.no_initial_sync:
        logger.info("Running initial sync of existing files…")
        syncer.sync_all_existing()
        logger.info("Initial sync complete.")

    watcher.start()

    def _shutdown(signum, frame):  # noqa: ANN001
        logger.info("Received signal %s, shutting down…", signum)
        watcher.stop()
        monitor.stop()
        notifier.report("Claude Vault Sync", "Stopped — no longer watching")
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info(
        "claude-vault-sync is running. Output vault: %s",
        config.vault_conversations_dir,
    )
    logger.info("Press Ctrl-C to stop.")

    try:
        watcher.join()
    except KeyboardInterrupt:
        watcher.stop()
        monitor.stop()
        notifier.report("Claude Vault Sync", "Stopped — no longer watching")


if __name__ == "__main__":
    main()
