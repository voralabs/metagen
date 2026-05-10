"""Semantic analyzer — layers LLM-sourced descriptions on top of computed stats.

Reads a Catalog already populated with computed stats, and augments tables and
columns with `description` TaggedText (source=llm). All LLM calls go through
an `LLMProvider`; tests use `FakeLLMProvider`.

Honors a `CatalogGrains` flag set so the TUI/CLI can opt out of any specific
section (table descriptions, column descriptions, grain phrasing) without
touching the engine internals.
"""

from __future__ import annotations

from dataclasses import dataclass

from metagen.cache.store import Cache
from metagen.schema.models import (
    Catalog,
    ColumnProfile,
    QualityIssue,
    TableProfile,
    TaggedText,
    ValidationFlag,
)
from metagen.semantic import prompts
from metagen.semantic.llm_provider import LLMProvider, LLMRequest
from metagen.semantic.validator import validate_description

# Heuristic "confidence" for the Fake / baseline case — real providers will
# eventually return model-derived confidence. For now every llm description
# gets a fixed default so the contract is satisfied without lying.
DEFAULT_CONFIDENCE = 0.8


@dataclass(frozen=True)
class AnalyzerGrains:
    """Subset of CatalogGrains the analyzer cares about. Defaults: everything on."""

    table_descriptions: bool = True
    column_descriptions: bool = True
    grain: bool = True


def _sample_values(column: ColumnProfile, n: int = 5) -> list[object]:
    return [tv["value"] for tv in column.stats.top_values[:n]]


def _describe_table(
    table: TableProfile,
    provider: LLMProvider,
    cache: Cache | None,
    user_context: str | None,
) -> tuple[TaggedText | None, list[ValidationFlag]]:
    prompt = prompts.render_table_description(
        user_context=user_context,
        table=table.name,
        row_count=table.row_count,
        columns=", ".join(c.name for c in table.columns),
    )
    request = LLMRequest(
        prompt=prompt,
        system=prompts.SYSTEM,
        kind="table_description",
        prompt_version=prompts.VERSION,
        meta={"table": table.name},
    )
    response = _cached_complete(provider, request, cache)
    outcome = validate_description(response.text)
    if not outcome.ok:
        flag = ValidationFlag(
            code=outcome.flag_code or "llm_invalid",
            message=outcome.flag_message or "LLM output rejected.",
            severity="warning",
        )
        return None, [flag]
    return (
        TaggedText(text=outcome.text, source="llm", confidence=DEFAULT_CONFIDENCE),
        [],
    )


def _describe_column(
    table: TableProfile,
    column: ColumnProfile,
    provider: LLMProvider,
    cache: Cache | None,
    user_context: str | None,
) -> tuple[TaggedText | None, list[ValidationFlag]]:
    prompt = prompts.render_column_description(
        user_context=user_context,
        table=table.name,
        column=column.name,
        dtype=column.dtype,
        null_fraction=column.stats.null_fraction,
        distinct=column.stats.distinct_count if column.stats.distinct_count is not None else "unknown",
        samples=_sample_values(column),
    )
    request = LLMRequest(
        prompt=prompt,
        system=prompts.SYSTEM,
        kind="column_description",
        prompt_version=prompts.VERSION,
        meta={"table": table.name, "column": column.name},
    )
    response = _cached_complete(provider, request, cache)
    outcome = validate_description(response.text)
    if not outcome.ok:
        flag = ValidationFlag(
            code=outcome.flag_code or "llm_invalid",
            message=outcome.flag_message or "LLM output rejected.",
            severity="warning",
        )
        return None, [flag]
    return (
        TaggedText(text=outcome.text, source="llm", confidence=DEFAULT_CONFIDENCE),
        [],
    )


def _phrase_grain(
    table: TableProfile,
    detection_note: str,
    provider: LLMProvider,
    cache: Cache | None,
    user_context: str | None,
) -> TaggedText | None:
    """Ask the LLM to phrase a detected natural key as plain English."""
    prompt = prompts.render_grain_description(
        user_context=user_context,
        table=table.name,
        row_count=table.row_count,
        columns=", ".join(c.name for c in table.columns),
        natural_key=table.natural_key,
        detection_note=detection_note,
    )
    request = LLMRequest(
        prompt=prompt,
        system=prompts.SYSTEM,
        kind="grain_description",
        prompt_version=prompts.VERSION,
        meta={
            "table": table.name,
            "natural_key": ", ".join(table.natural_key) if table.natural_key else "",
        },
    )
    response = _cached_complete(provider, request, cache)
    outcome = validate_description(response.text)
    if not outcome.ok:
        return None
    return TaggedText(text=outcome.text, source="llm", confidence=DEFAULT_CONFIDENCE)


def _cached_complete(provider: LLMProvider, request: LLMRequest, cache: Cache | None):
    if cache is None:
        return provider.complete(request)
    return cache.get_or_compute_llm(request, lambda: provider.complete(request), provider=provider)


def analyze(
    catalog: Catalog,
    provider: LLMProvider,
    cache: Cache | None = None,
    *,
    grains: AnalyzerGrains | None = None,
    grain_reasons: dict[str, str] | None = None,
) -> Catalog:
    """Return a new Catalog with LLM descriptions and business questions layered on.

    Pulls user context from `catalog.user_context.notes` so prompts can be
    shaped by domain knowledge the user typed in.

    `grain_reasons` is an optional `{table_name: detection_note}` map produced
    by `profiler/grain.py`. When supplied (and `grains.grain` is on), the LLM
    phrases each table's grain in plain English using its natural key.
    """
    grains = grains or AnalyzerGrains()
    grain_reasons = grain_reasons or {}
    user_context = catalog.user_context.notes

    new_tables: list[TableProfile] = []
    for table in catalog.tables:
        table_desc: TaggedText | None = None
        table_flags: list[ValidationFlag] = []
        if grains.table_descriptions:
            table_desc, table_flags = _describe_table(table, provider, cache, user_context)

        grain_text: TaggedText | None = table.grain
        if grains.grain and (table.natural_key or grain_reasons.get(table.name)):
            grain_text = _phrase_grain(
                table,
                grain_reasons.get(table.name, "natural key undetermined"),
                provider,
                cache,
                user_context,
            )

        new_columns: list[ColumnProfile] = []
        for column in table.columns:
            if grains.column_descriptions:
                col_desc, col_flags = _describe_column(table, column, provider, cache, user_context)
                new_columns.append(
                    column.model_copy(
                        update={
                            "description": col_desc,
                            "validation_flags": [*column.validation_flags, *col_flags],
                        }
                    )
                )
            else:
                new_columns.append(column)

        quality = table.quality
        if table_flags and quality is not None:
            quality = quality.model_copy(
                update={
                    "issues": [
                        *quality.issues,
                        *[
                            QualityIssue(column=None, code=f.code, message=f.message)
                            for f in table_flags
                        ],
                    ],
                }
            )
        new_tables.append(
            table.model_copy(
                update={
                    "description": table_desc,
                    "columns": new_columns,
                    "quality": quality,
                    "grain": grain_text,
                }
            )
        )

    return catalog.model_copy(update={"tables": new_tables})
