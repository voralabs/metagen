"""Deterministic column and table statistics.

Everything here is source=computed — verifiable from the data alone.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

from metagen.connectors.base import LoadedTable
from metagen.profiler.sampling import SamplePlan, sample
from metagen.schema.models import (
    ColumnProfile,
    ColumnStats,
    QualityIssue,
    TableProfile,
    TableQuality,
)

TOP_K_DEFAULT = 10


def _is_numeric(dtype: pa.DataType) -> bool:
    return pa.types.is_integer(dtype) or pa.types.is_floating(dtype)


def _to_py(value: Any) -> Any:
    if isinstance(value, pa.Scalar):
        value = value.as_py()
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def profile_column(name: str, array: pa.ChunkedArray) -> ColumnProfile:
    total = len(array)
    null_count = int(array.null_count)
    null_fraction = (null_count / total) if total else 0.0

    distinct_count: int | None = None
    distinct_fraction: float | None = None
    minimum: Any = None
    maximum: Any = None
    mean: float | None = None
    stddev: float | None = None
    top_values: list[dict[str, Any]] = []

    non_null = total - null_count

    try:
        distinct_count = int(pc.count_distinct(array, mode="only_valid").as_py())
        distinct_fraction = (distinct_count / non_null) if non_null else None
    except pa.ArrowNotImplementedError:
        distinct_count = None

    if non_null > 0:
        try:
            minimum = _to_py(pc.min(array))
            maximum = _to_py(pc.max(array))
        except pa.ArrowNotImplementedError:
            pass

        if _is_numeric(array.type):
            try:
                mean = float(pc.mean(array).as_py())
                stddev_val = pc.stddev(array, ddof=1).as_py() if non_null > 1 else None
                stddev = float(stddev_val) if stddev_val is not None else None
            except pa.ArrowNotImplementedError:
                pass

        # Top-k values for low-cardinality columns — skip for high-cardinality numerics.
        if distinct_count is not None and distinct_count <= max(TOP_K_DEFAULT * 5, 100):
            counter: Counter[Any] = Counter()
            for chunk in array.chunks:
                for v in chunk.to_pylist():
                    if v is not None:
                        counter[v] += 1
            top_values = [
                {"value": _to_py(v), "count": c}
                for v, c in counter.most_common(TOP_K_DEFAULT)
            ]

    stats = ColumnStats(
        null_count=null_count,
        null_fraction=null_fraction,
        distinct_count=distinct_count,
        distinct_fraction=distinct_fraction,
        min=minimum,
        max=maximum,
        mean=mean,
        stddev=stddev,
        top_values=top_values,
    )

    return ColumnProfile(name=name, dtype=str(array.type), stats=stats)


def _completeness(columns: list[ColumnProfile]) -> float | None:
    if not columns:
        return None
    return 1.0 - sum(c.stats.null_fraction for c in columns) / len(columns)


def _grade(completeness: float | None) -> str | None:
    if completeness is None:
        return None
    if completeness >= 0.99:
        return "A"
    if completeness >= 0.95:
        return "B"
    if completeness >= 0.85:
        return "C"
    if completeness >= 0.70:
        return "D"
    return "F"


def profile_table(loaded: LoadedTable, plan: SamplePlan | None = None) -> TableProfile:
    # If the connector already sampled at read time (`true_row_count` set),
    # skip the profiler's own sampling — we don't have the other rows to sample from.
    if loaded.true_row_count is not None and loaded.true_row_count != loaded.table.num_rows:
        table = loaded.table
        sampled_flag = True
        sample_size = table.num_rows
        true_rows = loaded.true_row_count
    else:
        sampled = sample(loaded.table, plan or SamplePlan())
        table = sampled.table
        sampled_flag = sampled.sampled
        sample_size = sampled.sample_size
        true_rows = sampled.true_row_count

    columns = [profile_column(field.name, table.column(field.name)) for field in table.schema]
    completeness = _completeness(columns)
    issues: list[QualityIssue] = []
    if sampled_flag:
        issues.append(
            QualityIssue(
                column=None,
                code="sampled_stats",
                message=(
                    f"Stats computed on a sample of {sample_size:,} "
                    f"of {true_rows:,} rows."
                ),
            )
        )
    quality = TableQuality(
        grade=_grade(completeness),  # type: ignore[arg-type]
        completeness=completeness,
        issues=issues,
    )
    return TableProfile(
        name=loaded.name,
        row_count=true_rows,
        columns=columns,
        quality=quality,
    )
