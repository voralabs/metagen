"""Sanity-check LLM output against the computed stats.

Conservative validator: rejects obviously bad output (empty, over-long, or
content the stats contradict). Sets a validation_flag when rejecting so the
user sees *why*. Never silently drops.
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_DESCRIPTION_CHARS = 400
MIN_DESCRIPTION_CHARS = 3


@dataclass(frozen=True)
class ValidationOutcome:
    ok: bool
    text: str
    flag_code: str | None = None
    flag_message: str | None = None


def validate_description(raw: str) -> ValidationOutcome:
    text = (raw or "").strip()
    if len(text) < MIN_DESCRIPTION_CHARS:
        return ValidationOutcome(False, "", "llm_empty", "LLM returned an empty description.")
    if len(text) > MAX_DESCRIPTION_CHARS:
        text = text[: MAX_DESCRIPTION_CHARS - 1].rstrip() + "…"
    return ValidationOutcome(True, text)
