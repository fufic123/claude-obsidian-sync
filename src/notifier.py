from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_TERMINAL_NOTIFIER = Path("/opt/homebrew/bin/terminal-notifier")


class Notifier:
    """Sends macOS Notification Center alerts.

    Prefers ``terminal-notifier`` for persistent notifications that stay in
    Notification Center.  Falls back to ``osascript`` when the binary is not
    found.
    """

    def __init__(self) -> None:
        self._use_terminal_notifier = _TERMINAL_NOTIFIER.is_file()
        if self._use_terminal_notifier:
            logger.debug("Notifier: using terminal-notifier at %s", _TERMINAL_NOTIFIER)
        else:
            logger.debug("Notifier: terminal-notifier not found, using osascript fallback")

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def alert(self, title: str, message: str, subtitle: str | None = None) -> None:
        """Send a warning / limit-alert notification."""
        self._send(title=title, message=message, subtitle=subtitle)

    def report(self, title: str, message: str) -> None:
        """Send a daily-report notification."""
        self._send(title=title, message=message, subtitle=None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _send(self, title: str, message: str, subtitle: str | None) -> None:
        if self._use_terminal_notifier:
            self._send_terminal_notifier(title, message, subtitle)
        else:
            self._send_osascript(title, message, subtitle)

    def _send_terminal_notifier(
        self, title: str, message: str, subtitle: str | None
    ) -> None:
        cmd: list[str] = [
            str(_TERMINAL_NOTIFIER),
            "-title", title,
            "-message", message,
        ]
        if subtitle:
            cmd += ["-subtitle", subtitle]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except (subprocess.CalledProcessError, OSError) as exc:
            logger.warning("terminal-notifier failed (%s); falling back to osascript", exc)
            self._send_osascript(title, message, subtitle)

    def _send_osascript(
        self, title: str, message: str, subtitle: str | None
    ) -> None:
        # Build the AppleScript string.  Escape double-quotes inside user text.
        def _esc(s: str) -> str:
            return s.replace('"', '\\"')

        parts = [f'display notification "{_esc(message)}" with title "{_esc(title)}"']
        if subtitle:
            parts[0] += f' subtitle "{_esc(subtitle)}"'

        script = parts[0]
        cmd = ["osascript", "-e", script]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except (subprocess.CalledProcessError, OSError) as exc:
            logger.error("osascript notification failed: %s", exc)
