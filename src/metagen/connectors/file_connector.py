"""File connector — reads CSV, Parquet, and Excel files from a path or glob.

Whole-file load via pyarrow (CSV/Parquet) or pandas+openpyxl (Excel).
Streaming/tiered sampling arrives later if needed; Excel files are typically
small enough that this isn't a concern.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pa_csv
import pyarrow.parquet as pa_parquet

from metagen.connectors.base import DataConnector, LoadedTable

CSV_SUFFIXES = {".csv"}
PARQUET_SUFFIXES = {".parquet"}
EXCEL_SUFFIXES = {".xlsx", ".xls"}
SUPPORTED_SUFFIXES = CSV_SUFFIXES | PARQUET_SUFFIXES | EXCEL_SUFFIXES


def _resolve_paths(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    if root.is_dir():
        return sorted(p for p in root.rglob("*") if p.suffix.lower() in SUPPORTED_SUFFIXES)
    matches = sorted(Path().glob(str(root)))
    if not matches:
        raise FileNotFoundError(f"No files matched: {root}")
    return matches


def _load_excel(path: Path, sheet: str | int | None) -> dict[str, pa.Table]:
    """Return a {sheet_name: pa.Table} mapping. `sheet=None` reads all sheets."""
    try:
        import pandas as pd
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pandas is required to read Excel files.") from e
    try:
        import openpyxl  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "Reading Excel files needs `openpyxl`. Install with `uv sync --extra excel`."
        ) from e
    raw = pd.read_excel(path, sheet_name=sheet)
    # pandas returns a dict when sheet_name=None, a DataFrame otherwise.
    if isinstance(raw, dict):
        return {str(name): pa.Table.from_pandas(df, preserve_index=False) for name, df in raw.items()}
    return {path.stem: pa.Table.from_pandas(raw, preserve_index=False)}


def _load_pa(path: Path) -> pa.Table:
    suffix = path.suffix.lower()
    if suffix in CSV_SUFFIXES:
        return pa_csv.read_csv(path)
    if suffix in PARQUET_SUFFIXES:
        return pa_parquet.read_table(path)
    raise ValueError(f"Unsupported file type: {path.suffix}")


class FileConnector(DataConnector):
    """Read CSV / Parquet / Excel files into pyarrow Tables.

    Excel: each sheet becomes its own logical table. With multiple sheets the
    table name is `<stem>__<sheet>`; single-sheet workbooks just use `<stem>`.
    Pass `sheet=...` to load only one sheet.
    """

    def __init__(self, path: str | Path, *, sheet: str | int | None = None) -> None:
        # `~` in user-provided paths is a common mistake (TUI/CLI both); expand it
        # here so every caller gets the same behavior.
        self._root = Path(path).expanduser()
        self._paths = _resolve_paths(self._root)
        if not self._paths:
            raise FileNotFoundError(f"No CSV/Parquet/Excel files under {self._root}")
        self._sheet = sheet

    def tables(self) -> Iterator[LoadedTable]:
        for p in self._paths:
            suffix = p.suffix.lower()
            if suffix in EXCEL_SUFFIXES:
                sheets = _load_excel(p, self._sheet)
                for name, table in sheets.items():
                    full_name = p.stem if len(sheets) == 1 else f"{p.stem}__{name}"
                    yield LoadedTable(name=full_name, table=table)
            else:
                yield LoadedTable(name=p.stem, table=_load_pa(p))

    def describe_source(self) -> dict[str, object]:
        return {"type": "files", "paths": [str(p) for p in self._paths]}
