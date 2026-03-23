from __future__ import annotations

from dataclasses import dataclass

from src.parser import Conversation


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class ClassificationResult:
    should_save: bool
    reason: str


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

class ConversationClassifier:
    """Decides whether a conversation is worth saving to the vault.

    Implements Option C (Hybrid) classification:

    1. Force-save override: any user message contains a save-trigger phrase.
    2. Auto-save: tool_use_count >= 3  OR  exchange_count >= 5.
    3. Auto-skip: first user message matches a trivial pattern AND the
       conversation is short (1 exchange, no tool uses).
    4. Default: save.
    """

    # Phrases that force a save regardless of other rules (case-insensitive).
    _FORCE_SAVE_PHRASES: tuple[str, ...] = (
        "save this",
        "remember this",
        "save conversation",
        "запомни это",
        "сохрани это",
    )

    # Phrases that block saving regardless of other rules (case-insensitive).
    _BLOCK_SAVE_PHRASES: tuple[str, ...] = (
        "don't save this",
        "do not save this",
        "don't save conversation",
        "block save",
        "не сохраняй это",
        "не сохраняй разговор",
        "не сохраняй",
    )

    # Prefixes on the *first* user message that suggest a trivial lookup.
    _TRIVIAL_PREFIXES: tuple[str, ...] = (
        "translate",
        "how to say",
        "what is",
        "what does",
        "definition of",
        "meaning of",
    )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def classify(self, conversation: Conversation) -> ClassificationResult:
        """Return a ClassificationResult for *conversation*."""
        user_messages = [m for m in conversation.messages if m.role == "user"]
        exchange_count = len(user_messages)
        tool_use_count = conversation.tool_use_count

        # --- Rule 0: block-save override (highest priority) ---
        for msg in conversation.messages:
            if msg.role == "user" and self._has_block_save_phrase(msg.text):
                return ClassificationResult(should_save=False, reason="skipped:block_save")

        # --- Rule 1: force-save override ---
        for msg in conversation.messages:
            if msg.role == "user" and self._has_force_save_phrase(msg.text):
                return ClassificationResult(should_save=True, reason="force_save")

        # --- Rule 2: auto-save ---
        if tool_use_count >= 3:
            return ClassificationResult(
                should_save=True, reason=f"tool_uses={tool_use_count}"
            )
        if exchange_count >= 5:
            return ClassificationResult(
                should_save=True, reason=f"exchanges={exchange_count}"
            )

        # --- Rule 3: auto-skip ---
        if exchange_count == 1 and tool_use_count == 0:
            first_text = user_messages[0].text if user_messages else ""
            if self._matches_trivial_prefix(first_text):
                return ClassificationResult(
                    should_save=False, reason="skipped:trivial_pattern"
                )

        # --- Default: save ---
        return ClassificationResult(should_save=True, reason="default")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _has_force_save_phrase(self, text: str) -> bool:
        lower = text.lower()
        return any(phrase in lower for phrase in self._FORCE_SAVE_PHRASES)

    def _has_block_save_phrase(self, text: str) -> bool:
        lower = text.lower()
        return any(phrase in lower for phrase in self._BLOCK_SAVE_PHRASES)

    def _matches_trivial_prefix(self, text: str) -> bool:
        lower = text.lower().lstrip()
        return any(lower.startswith(prefix) for prefix in self._TRIVIAL_PREFIXES)
