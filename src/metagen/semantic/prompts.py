"""Versioned prompt templates.

Prompt text is part of the LLM cache key via `VERSION` — bumping the version
invalidates all cached LLM output generated with the previous prompt set.

**Change any prompt body → bump VERSION.** CLAUDE.md hard requirement.

`p2`: added `{user_context}` to table/column descriptions so user-provided
domain context shapes the LLM output (TUI Phase 6).
`p3`: added GRAIN_DESCRIPTION — phrases a detected natural key as plain English.
`p4`: removed BUSINESS_QUESTIONS — feature dropped from v1.
"""

from __future__ import annotations

from dataclasses import dataclass

VERSION = "p4"

SYSTEM = (
    "You are a senior data analyst. Given a table's schema and basic statistics, "
    "produce concise, factual descriptions. Never invent columns. If uncertain, say so. "
    "When the user provides domain context, weight it heavily — it reflects "
    "knowledge the stats can't show."
)


def _context_block(user_context: str | None) -> str:
    """Render an optional 'Domain context' block. Empty when none provided."""
    if not user_context or not user_context.strip():
        return ""
    return f"Domain context (provided by the user):\n{user_context.strip()}\n\n"


TABLE_DESCRIPTION = """\
{user_context_block}Describe the purpose of this table in 1-2 sentences.

Table: {table}
Row count: {row_count}
Columns: {columns}

Respond with only the description, no preamble.
"""

COLUMN_DESCRIPTION = """\
{user_context_block}Describe this column in one short sentence.

Table: {table}
Column: {column}
Type: {dtype}
Nulls: {null_fraction:.1%}
Distinct: {distinct}
Sample values: {samples}

Respond with only the description.
"""

GRAIN_DESCRIPTION = """\
{user_context_block}State the *grain* of this table — what does one row represent?
Use the format: "One row per <thing> [per <dimension> ...]".

Table: {table}
Row count: {row_count}
Columns: {columns}
Detected natural key: {natural_key}
Detection note: {detection_note}

If the natural key is empty, the table likely has duplicate rows or is denormalized;
say so plainly rather than inventing a grain.

Respond with only the grain sentence, no preamble.
"""


def render_table_description(*, user_context: str | None, table: str, row_count: int, columns: str) -> str:
    return TABLE_DESCRIPTION.format(
        user_context_block=_context_block(user_context),
        table=table,
        row_count=row_count,
        columns=columns,
    )


def render_column_description(
    *,
    user_context: str | None,
    table: str,
    column: str,
    dtype: str,
    null_fraction: float,
    distinct: object,
    samples: object,
) -> str:
    return COLUMN_DESCRIPTION.format(
        user_context_block=_context_block(user_context),
        table=table,
        column=column,
        dtype=dtype,
        null_fraction=null_fraction,
        distinct=distinct,
        samples=samples,
    )


def render_grain_description(
    *,
    user_context: str | None,
    table: str,
    row_count: int,
    columns: str,
    natural_key: list[str] | None,
    detection_note: str,
) -> str:
    return GRAIN_DESCRIPTION.format(
        user_context_block=_context_block(user_context),
        table=table,
        row_count=row_count,
        columns=columns,
        natural_key=", ".join(natural_key) if natural_key else "(none found)",
        detection_note=detection_note,
    )


@dataclass(frozen=True)
class PromptVersion:
    version: str = VERSION

    def cache_key(self) -> str:
        return self.version
