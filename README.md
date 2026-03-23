# claude-vault-sync

Watches Claude Code conversations and saves the important ones to an Obsidian vault automatically.

## How it works

1. Monitors `~/.claude/projects/` for new and updated conversation files (JSONL)
2. Classifies each conversation — only saves the ones worth keeping
3. Formats them as Markdown notes and writes to `~/Documents/personal/obsidian/Claude Conversations/`
4. Sends macOS Notification Center alerts on resource spikes and a daily report at 17:00

---

## Classification rules

| Condition | Result |
|-----------|--------|
| Any message contains `save this` / `remember this` / `save conversation` / `сохрани это` / `запомни это` | Always save |
| 3+ tool uses (file reads, edits, code runs) | Save |
| 5+ message exchanges | Save |
| Single exchange, no tools, trivial prompt (translate, what is…) | Skip |
| Everything else | Save |

---

## Installation

```bash
cd ~/Documents/personal/claude-vault-sync
pip3 install -r requirements.txt
```

## Running

```bash
# Start the watcher (initial sync + live watch)
python3 main.py

# Watch only (skip initial sync)
python3 main.py --no-initial-sync

# Verbose logging
python3 main.py --log-level DEBUG
```

Add `start.sh` as a **Login Item** (System Settings → General → Login Items) to run automatically on login.

---

## Force-saving a conversation

Use this when Claude didn't auto-save but you want to keep the conversation.

```bash
# Save the most recent conversation
python3 force_save.py

# Save a specific session by UUID prefix
python3 force_save.py 94bd9ec8
```

You can also ask Claude directly:
> "сохрани этот разговор" / "save this conversation"

Claude will run `force_save.py` via the terminal and you'll get a Notification Center confirmation.

---

## Configuration (`config.py`)

| Field | Default | Description |
|-------|---------|-------------|
| `debounce_seconds` | 10 | Wait N seconds after last file change before processing |
| `cpu_alert_threshold` | 5.0% | Alert when CPU exceeds this |
| `ram_alert_threshold_mb` | 50 MB | Alert when RAM exceeds this |
| `alert_cooldown_minutes` | 30 | Min time between repeated alerts |
| `daily_report_time` | `"17:00"` | Daily report time (local, Vilnius) |

---

## Note format

```
---
date: 2026-03-23
session_id: 94bd9ec8-...
tags: [claude, conversation]
---

# First user message (up to 60 chars)

## Summary
- Question 1
- Question 2
- Question 3

---

## Conversation

**User:** ...

**Claude:** ...
```

---

## File structure

```
claude-vault-sync/
├── main.py              # Entry point
├── force_save.py        # Manual force-save CLI
├── start.sh             # Login Item launcher
├── config.py            # All configuration
├── requirements.txt
├── processed.json       # State tracker (auto-generated)
├── service.log          # Log output when running as Login Item
└── src/
    ├── classifier.py    # Importance classification
    ├── formatter.py     # Markdown note formatting
    ├── monitor.py       # Resource monitoring + daily report
    ├── notifier.py      # macOS Notification Center
    ├── parser.py        # JSONL conversation parser
    ├── syncer.py        # Orchestrator
    ├── watcher.py       # File system watcher (FSEvents)
    └── writer.py        # Vault note writer
```
