"""Single-column foreign-key inference.

Algorithm:
  1. For each column in each table, look for plausible parents in other tables:
       - `X_id` → `X.id` or `Xs.id` (strict, high prior)
       - exact column-name match across tables (weak)
     dtype must match.
  2. Parent candidate qualifies only if parent-side values are unique (candidate key).
  3. Measure containment: fraction of child non-null values present in parent's value set.
     Accept when containment ≥ MIN_CONTAINMENT.
  4. Cardinality:
       - child distinct == child row_count (ignoring nulls) → one-to-one
       - otherwise                                          → many-to-one
  5. Confidence = containment × name_prior.

Multi-column / composite FK inference is deliberately out of scope for Phase 3.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import pyarrow as pa
import pyarrow.compute as pc

from metagen.connectors.base import LoadedTable
from metagen.schema.models import Relationship

MIN_CONTAINMENT = 0.95
STRICT_NAME_PRIOR = 0.95
LOOSE_NAME_PRIOR = 0.70


@dataclass(frozen=True)
class _Candidate:
    child_table: str
    child_column: str
    parent_table: str
    parent_column: str
    name_prior: float


def _singularize(name: str) -> str:
    # Cheap stemmer — good enough for `orders` → `order`, `categories` → `category`.
    if name.endswith("ies") and len(name) > 3:
        return name[:-3] + "y"
    if name.endswith("ses"):
        return name[:-2]
    if name.endswith("s") and not name.endswith("ss"):
        return name[:-1]
    return name


def _strict_name_parent(child_column: str) -> str | None:
    """`orders.customer_id` → `customer` (singular parent name guess)."""
    if child_column.endswith("_id") and len(child_column) > 3:
        return child_column[:-3]
    return None


def _candidate_pairs(loaded: list[LoadedTable]) -> Iterable[_Candidate]:
    table_names = {lt.name: lt for lt in loaded}
    for child in loaded:
        for child_field in child.table.schema:
            child_col = child_field.name
            parent_hint = _strict_name_parent(child_col)
            for parent in loaded:
                if parent.name == child.name:
                    continue
                for parent_field in parent.table.schema:
                    if parent_field.type != child_field.type:
                        continue
                    # strict: orders.customer_id → customers.id (or customer.id)
                    if (
                        parent_hint is not None
                        and parent_field.name == "id"
                        and _singularize(parent.name) == parent_hint
                    ):
                        yield _Candidate(
                            child_table=child.name,
                            child_column=child_col,
                            parent_table=parent.name,
                            parent_column=parent_field.name,
                            name_prior=STRICT_NAME_PRIOR,
                        )
                        continue
                    # loose: exact same column name on another table
                    if parent_field.name == child_col and child_col != "id":
                        yield _Candidate(
                            child_table=child.name,
                            child_column=child_col,
                            parent_table=parent.name,
                            parent_column=parent_field.name,
                            name_prior=LOOSE_NAME_PRIOR,
                        )
        # fallthrough; table_names retained for potential future multi-column work
    _ = table_names


def _is_unique(col: pa.ChunkedArray) -> bool:
    if col.null_count > 0:
        return False
    distinct = pc.count_distinct(col, mode="only_valid").as_py()
    return int(distinct) == len(col)


def _containment(child_col: pa.ChunkedArray, parent_col: pa.ChunkedArray) -> float:
    child_non_null = pc.drop_null(child_col.combine_chunks())
    total = len(child_non_null)
    if total == 0:
        return 0.0
    parent_set = pc.unique(parent_col.combine_chunks())
    present = pc.is_in(child_non_null, value_set=parent_set)
    hit = pc.sum(present).as_py() or 0
    return float(hit) / float(total)


def _cardinality(child_col: pa.ChunkedArray) -> str:
    non_null = pc.drop_null(child_col.combine_chunks())
    if len(non_null) == 0:
        return "many-to-one"
    distinct = pc.count_distinct(non_null, mode="only_valid").as_py()
    if int(distinct) == len(non_null):
        return "one-to-one"
    return "many-to-one"


def infer(loaded: list[LoadedTable]) -> list[Relationship]:
    by_name = {lt.name: lt for lt in loaded}
    relationships: list[Relationship] = []
    seen: set[tuple[str, str, str, str]] = set()

    for cand in _candidate_pairs(loaded):
        key = (cand.child_table, cand.child_column, cand.parent_table, cand.parent_column)
        if key in seen:
            continue
        seen.add(key)
        parent_col = by_name[cand.parent_table].table.column(cand.parent_column)
        child_col = by_name[cand.child_table].table.column(cand.child_column)
        if not _is_unique(parent_col):
            continue
        containment = _containment(child_col, parent_col)
        if containment < MIN_CONTAINMENT:
            continue
        cardinality = _cardinality(child_col)
        relationships.append(
            Relationship(
                table_a=cand.child_table,
                columns_a=[cand.child_column],
                table_b=cand.parent_table,
                columns_b=[cand.parent_column],
                cardinality=cardinality,  # type: ignore[arg-type]
                confidence=round(min(1.0, containment * cand.name_prior), 4),
                source="computed",
            )
        )
    return relationships
