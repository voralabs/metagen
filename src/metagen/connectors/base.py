"""Connector abstraction — a source that yields named tables as pyarrow Tables."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass

import pyarrow as pa


@dataclass(frozen=True)
class LoadedTable:
    name: str
    table: pa.Table
    # Set by connectors that sample at read-time (e.g. DB LIMIT). None means
    # "the in-memory table is the full table" — the profiler uses table.num_rows.
    true_row_count: int | None = None


class DataConnector(ABC):
    """Abstract connector — subclasses yield one `LoadedTable` per logical table."""

    @abstractmethod
    def tables(self) -> Iterator[LoadedTable]: ...

    @abstractmethod
    def describe_source(self) -> dict[str, object]:
        """Return a dict shaped like `CatalogSource` (type + paths/label)."""
