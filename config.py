from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    claude_projects_dir: Path = field(
        default_factory=lambda: Path.home() / ".claude" / "projects"
    )
    vault_conversations_dir: Path = field(
        default_factory=lambda: Path.home()
        / "Documents"
        / "personal"
        / "obsidian"
        / "Claude Conversations"
    )
    state_file: Path = field(
        default_factory=lambda: Path.home()
        / "Documents"
        / "personal"
        / "claude-vault-sync"
        / "processed.json"
    )
    debounce_seconds: int = 10
    first_user_message_max_chars: int = 60
    summary_message_max_chars: int = 100
    summary_message_count: int = 3
    cpu_alert_threshold: float = 5.0        # percent
    ram_alert_threshold_mb: float = 50.0   # megabytes RSS
    alert_cooldown_minutes: int = 30
    daily_report_time: str = "17:00"        # HH:MM local time (Vilnius)
