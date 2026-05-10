"""Tiered sampling for profiling.

Phase 3: single tier — random sample of N rows when `num_rows > threshold`.
True row count is never lost; it flows through `TableProfile.row_count` from
the connector. Stats marked implicitly approximate when sampled.

Multi-tier / stratified sampling (time-partitioned scans, top-k accuracy
guarantees) is a Phase 4+ extension — still source=computed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pyarrow as pa

DEFAULT_SAMPLE_ROWS = 100_000
DEFAULT_SAMPLE_THRESHOLD = 500_000  # leave small tables fully profiled


@dataclass(frozen=True)
class SamplePlan:
    sample_rows: int = DEFAULT_SAMPLE_ROWS
    threshold: int = DEFAULT_SAMPLE_THRESHOLD
    seed: int = 0


@dataclass(frozen=True)
class SampledTable:
    table: pa.Table
    true_row_count: int
    sampled: bool
    sample_size: int


def sample(table: pa.Table, plan: SamplePlan = SamplePlan()) -> SampledTable:
    n = table.num_rows
    if n <= plan.threshold:
        return SampledTable(table=table, true_row_count=n, sampled=False, sample_size=n)
    rng = np.random.default_rng(plan.seed)
    indices = rng.choice(n, size=plan.sample_rows, replace=False)
    indices.sort()
    sub = table.take(pa.array(indices))
    return SampledTable(
        table=sub,
        true_row_count=n,
        sampled=True,
        sample_size=plan.sample_rows,
    )
