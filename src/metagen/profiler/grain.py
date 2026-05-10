"""Detect a table's natural key — the minimal column subset that uniquely
identifies a row.

The natural key is the computed evidence behind the LLM-phrased *grain*
(e.g. "one row per order per day per store"). When the analyzer is on, the
LLM turns the natural key into a human-readable sentence; when off, the
catalog still carries the structured evidence.

Strategy:
  1. Size-1: any column with `distinct == row_count` AND `nulls == 0`.
     Prefer ID-like names, then alphabetical.
  2. Size-2 / Size-3: only over "useful" columns (cardinality > 1 and not
     individually unique — those are already covered by Step 1).
  3. Hard cap at k=3. Above that we report `undetermined` rather than risk a
     combinatorial explosion.

Performance: per-column distinct counts come straight from the existing
`ColumnStats`, so no extra scans for Step 1. Step 2/3 use a pandas
`drop_duplicates` over the candidate subset, which is plenty fast at v1
scale (<10M rows, <50 cols).
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import pyarrow as pa

from metagen.schema.models import ColumnProfile, TableProfile

ID_NAME_TOKENS = ("_id", "id", "uuid", "key", "pk")
MAX_KEY_SIZE = 3
# Cardinality fences for combo search: skip columns that are constant
# (cardinality 1) or already unique alone (handled by size-1). Tighten more
# at higher k to keep the search bounded.
MIN_CARDINALITY = 2


@dataclass(frozen=True)
class GrainResult:
    natural_key: list[str] | None  # None when no key found within MAX_KEY_SIZE
    reason: str  # short, structured explanation for downstream rendering


def _id_priority(name: str) -> int:
    """Lower is better. ID-like names get priority 0, others priority 1."""
    lname = name.lower()
    return 0 if any(tok in lname for tok in ID_NAME_TOKENS) else 1


def _useful_columns(profile: TableProfile) -> list[ColumnProfile]:
    """Columns worth combining: not constant, not individually unique."""
    n = profile.row_count
    out: list[ColumnProfile] = []
    for c in profile.columns:
        d = c.stats.distinct_count
        if d is None:
            continue
        if d < MIN_CARDINALITY:
            continue
        if d == n and c.stats.null_count == 0:
            continue  # already a size-1 candidate, handled separately
        out.append(c)
    return out


def _is_unique(table: pa.Table, columns: list[str]) -> bool:
    """Return True iff the projection on `columns` has no duplicate rows.

    Uses pandas drop_duplicates — fast, simple, handles mixed dtypes cleanly.
    """
    df = table.select(columns).to_pandas()
    if df.isna().any().any():
        # Null in a key column is a smell; treat the combo as non-unique to be safe.
        return False
    return len(df) == len(df.drop_duplicates())


def detect(profile: TableProfile, table: pa.Table) -> GrainResult:
    n = profile.row_count
    if n == 0:
        return GrainResult(natural_key=None, reason="empty table")

    # Step 1 — single-column natural keys via stats only (no scan).
    size1: list[str] = [
        c.name
        for c in profile.columns
        if c.stats.distinct_count == n and c.stats.null_count == 0
    ]
    if size1:
        size1.sort(key=lambda name: (_id_priority(name), name))
        return GrainResult(natural_key=[size1[0]], reason="single-column unique key")

    # Step 2/3 — combo search over useful columns.
    candidates = _useful_columns(profile)
    candidate_names = [c.name for c in candidates]
    if len(candidate_names) < 2:
        return GrainResult(natural_key=None, reason="no key found within size 3 — table may have duplicate rows")

    for k in range(2, MAX_KEY_SIZE + 1):
        if len(candidate_names) < k:
            break
        # Sort combos by (sum of cardinalities, names) so smaller-cardinality
        # combos — which are more likely to BE the grain — come first.
        cardinality = {c.name: (c.stats.distinct_count or n) for c in candidates}
        combos = sorted(
            combinations(candidate_names, k),
            key=lambda combo: (sum(cardinality[c] for c in combo), combo),
        )
        for combo in combos:
            if _is_unique(table, list(combo)):
                return GrainResult(
                    natural_key=list(combo),
                    reason=f"size-{k} composite unique key",
                )

    return GrainResult(
        natural_key=None,
        reason="no key found within size 3 — table may have duplicate rows or be denormalized",
    )
