from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, date

import psutil

from config import Config
from src.notifier import Notifier

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 30
_BYTES_PER_MB = 1024 * 1024


@dataclass
class _DailyStats:
    conversations_saved: int = 0
    conversations_skipped: int = 0
    peak_ram_mb: float = 0.0
    _cpu_samples: list[float] = field(default_factory=list)

    @property
    def avg_cpu_pct(self) -> float:
        if not self._cpu_samples:
            return 0.0
        return sum(self._cpu_samples) / len(self._cpu_samples)

    def add_cpu_sample(self, pct: float) -> None:
        self._cpu_samples.append(pct)

    def update_peak_ram(self, ram_mb: float) -> None:
        if ram_mb > self.peak_ram_mb:
            self.peak_ram_mb = ram_mb

    def reset(self) -> None:
        self.conversations_saved = 0
        self.conversations_skipped = 0
        self.peak_ram_mb = 0.0
        self._cpu_samples.clear()


class ResourceMonitor:
    """Monitors CPU and RAM of the current process in a background daemon thread.

    Sends macOS Notification Center alerts when configurable thresholds are
    exceeded and emits a daily summary report at a configurable time.
    """

    def __init__(self, config: Config, notifier: Notifier) -> None:
        self._config = config
        self._notifier = notifier
        self._process = psutil.Process(os.getpid())

        self._stats = _DailyStats()
        self._stats_lock = threading.Lock()

        # Alert cooldown tracking: threshold_key -> last alert timestamp
        self._last_alert: dict[str, float] = {}
        self._alert_lock = threading.Lock()

        # CPU consecutive high-reading counter
        self._cpu_high_count = 0

        # Track the date for midnight reset and daily report
        self._last_report_date: date | None = None
        self._last_poll_date: date | None = None

        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="ResourceMonitor", daemon=True)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background monitoring thread."""
        self._thread.start()
        logger.info("ResourceMonitor started (poll every %ds)", _POLL_INTERVAL_SECONDS)

    def stop(self) -> None:
        """Signal the monitoring thread to exit and wait for it."""
        self._stop_event.set()
        self._thread.join(timeout=5)
        logger.info("ResourceMonitor stopped.")

    def record_saved(self) -> None:
        """Increment the saved-conversations counter for today's stats."""
        with self._stats_lock:
            self._stats.conversations_saved += 1

    def record_skipped(self) -> None:
        """Increment the skipped-conversations counter for today's stats."""
        with self._stats_lock:
            self._stats.conversations_skipped += 1

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        # Prime psutil's CPU percent (first call always returns 0.0)
        self._process.cpu_percent(interval=None)

        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=_POLL_INTERVAL_SECONDS)
            if self._stop_event.is_set():
                break
            try:
                self._tick()
            except Exception:
                logger.exception("ResourceMonitor: unhandled error in poll loop")

    def _tick(self) -> None:
        now = datetime.now()
        today = now.date()

        # Midnight reset
        if self._last_poll_date is not None and today != self._last_poll_date:
            with self._stats_lock:
                self._stats.reset()
            logger.debug("ResourceMonitor: daily stats reset at midnight.")
        self._last_poll_date = today

        # Gather metrics
        cpu_pct = self._process.cpu_percent(interval=None)
        ram_mb = self._process.memory_info().rss / _BYTES_PER_MB

        with self._stats_lock:
            self._stats.add_cpu_sample(cpu_pct)
            self._stats.update_peak_ram(ram_mb)

        logger.debug("ResourceMonitor: cpu=%.1f%% ram=%.1fMB", cpu_pct, ram_mb)

        # Check thresholds
        self._check_cpu(cpu_pct)
        self._check_ram(ram_mb)

        # Daily report
        self._maybe_send_daily_report(now, today)

    # ------------------------------------------------------------------
    # Threshold checks
    # ------------------------------------------------------------------

    def _check_cpu(self, cpu_pct: float) -> None:
        threshold = self._config.cpu_alert_threshold
        if cpu_pct > threshold:
            self._cpu_high_count += 1
        else:
            self._cpu_high_count = 0

        if self._cpu_high_count >= 2:
            if self._cooldown_ok("cpu"):
                logger.warning("CPU alert: %.1f%% > %.1f%%", cpu_pct, threshold)
                self._notifier.alert(
                    title="Claude Vault Sync — High CPU",
                    message=f"CPU at {cpu_pct:.1f}% (threshold {threshold:.0f}%) for 1+ minute.",
                    subtitle="Resource Alert",
                )
                self._mark_alerted("cpu")

    def _check_ram(self, ram_mb: float) -> None:
        threshold = self._config.ram_alert_threshold_mb
        if ram_mb > threshold:
            if self._cooldown_ok("ram"):
                logger.warning("RAM alert: %.1fMB > %.1fMB", ram_mb, threshold)
                self._notifier.alert(
                    title="Claude Vault Sync — High RAM",
                    message=f"RAM at {ram_mb:.0f} MB (threshold {threshold:.0f} MB).",
                    subtitle="Resource Alert",
                )
                self._mark_alerted("ram")

    # ------------------------------------------------------------------
    # Daily report
    # ------------------------------------------------------------------

    def _maybe_send_daily_report(self, now: datetime, today: date) -> None:
        report_time = self._parse_report_time()
        if report_time is None:
            return

        report_hour, report_minute = report_time
        at_report_time = (now.hour == report_hour and now.minute == report_minute)

        if at_report_time and self._last_report_date != today:
            self._last_report_date = today
            self._send_daily_report()

    def _send_daily_report(self) -> None:
        with self._stats_lock:
            saved = self._stats.conversations_saved
            skipped = self._stats.conversations_skipped
            peak_ram = self._stats.peak_ram_mb
            avg_cpu = self._stats.avg_cpu_pct

        message = (
            f"Saved: {saved} | Skipped: {skipped} | "
            f"Peak RAM: {peak_ram:.0f}MB | Avg CPU: {avg_cpu:.1f}%"
        )
        logger.info("Daily report: %s", message)
        self._notifier.report(
            title="Claude Vault Sync \u2014 Daily Report",
            message=message,
        )

    # ------------------------------------------------------------------
    # Cooldown helpers
    # ------------------------------------------------------------------

    def _cooldown_ok(self, key: str) -> bool:
        cooldown_seconds = self._config.alert_cooldown_minutes * 60
        with self._alert_lock:
            # Use float('-inf') as the sentinel meaning "never alerted";
            # that guarantees the subtraction always exceeds any cooldown.
            last = self._last_alert.get(key, float("-inf"))
            return (time.monotonic() - last) >= cooldown_seconds

    def _mark_alerted(self, key: str) -> None:
        with self._alert_lock:
            self._last_alert[key] = time.monotonic()

    # ------------------------------------------------------------------
    # Config parsing
    # ------------------------------------------------------------------

    def _parse_report_time(self) -> tuple[int, int] | None:
        raw = self._config.daily_report_time
        try:
            hour_str, minute_str = raw.split(":")
            return int(hour_str), int(minute_str)
        except (ValueError, AttributeError):
            logger.warning("Invalid daily_report_time %r; daily report disabled.", raw)
            return None
