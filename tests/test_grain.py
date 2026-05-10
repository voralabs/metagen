"""Tests for natural-key / grain detection (`profiler/grain.py`) and its
end-to-end integration with the analyzer + Markdown renderer."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa

from metagen.connectors.file_connector import FileConnector
from metagen.core import CatalogGrains, build_catalog
from metagen.export.markdown_export import export as export_markdown
from metagen.profiler.grain import detect as detect_grain
from metagen.profiler.statistical import profile_table
from metagen.connectors.base import LoadedTable
from metagen.semantic.llm_provider import FakeLLMProvider, LLMRequest, LLMResponse

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "ecommerce"


def _make_loaded(name: str, table: pa.Table) -> LoadedTable:
    return LoadedTable(name=name, table=table)


# ---------- detection ----------------------------------------------------------------------


def test_detects_size1_id_key():
    table = pa.table({"order_id": [1, 2, 3, 4], "amount": [10, 20, 10, 20]})
    profile = profile_table(_make_loaded("orders", table))
    result = detect_grain(profile, table)
    assert result.natural_key == ["order_id"]
    assert "single-column" in result.reason


def test_prefers_id_named_columns_over_alternatives():
    # Both `id` and `email` are unique — `id` should win.
    table = pa.table({"id": [1, 2, 3], "email": ["a", "b", "c"]})
    profile = profile_table(_make_loaded("users", table))
    result = detect_grain(profile, table)
    assert result.natural_key == ["id"]


def test_detects_composite_key_when_no_single_column_unique():
    # No single column is unique (every value repeats), but (date, store_id) is.
    # sales repeats per date so (date, sales) is NOT unique — only (date, store_id) is.
    table = pa.table({
        "date": ["2024-01-01", "2024-01-01", "2024-01-02", "2024-01-02"],
        "store_id": [1, 2, 1, 2],
        "sales": [100, 100, 200, 200],
    })
    profile = profile_table(_make_loaded("daily_sales", table))
    result = detect_grain(profile, table)
    assert result.natural_key is not None
    assert set(result.natural_key) == {"date", "store_id"}
    assert "size-2" in result.reason


def test_reports_undetermined_when_table_has_duplicates():
    # Every row is identical — no key exists.
    table = pa.table({"a": [1, 1, 1], "b": [2, 2, 2]})
    profile = profile_table(_make_loaded("dup", table))
    result = detect_grain(profile, table)
    assert result.natural_key is None
    assert "duplicate" in result.reason or "denormalized" in result.reason


def test_empty_table_grain_undetermined():
    table = pa.table({"a": pa.array([], type=pa.int64())})
    profile = profile_table(_make_loaded("empty", table))
    result = detect_grain(profile, table)
    assert result.natural_key is None
    assert "empty" in result.reason


# ---------- end-to-end: build_catalog with grain on -----------------------------------------


def test_build_catalog_attaches_natural_key_and_llm_grain():
    catalog = build_catalog(FileConnector(EXAMPLES), llm=FakeLLMProvider())
    customers = next(t for t in catalog.tables if t.name == "customers")
    orders = next(t for t in catalog.tables if t.name == "orders")
    # FakeLLMProvider phrases grain with `One row per <key>`.
    assert customers.natural_key == ["id"]
    assert customers.grain is not None
    assert customers.grain.source == "llm"
    assert "One row per" in customers.grain.text
    assert orders.natural_key == ["order_id"]


def test_grain_flag_off_skips_detection_and_phrasing():
    grains = CatalogGrains(grain=False)
    catalog = build_catalog(FileConnector(EXAMPLES), llm=FakeLLMProvider(), grains=grains)
    for t in catalog.tables:
        assert t.natural_key is None
        assert t.grain is None


def test_grain_phrasing_off_keeps_natural_key():
    """Stats-only path: detection happens, LLM phrasing skipped."""
    grains = CatalogGrains(
        table_descriptions=False,
        column_descriptions=False,
        grain=True,  # detection runs
    )
    # No LLM at all — analyzer never gets called.
    catalog = build_catalog(FileConnector(EXAMPLES), llm=None, grains=grains)
    customers = next(t for t in catalog.tables if t.name == "customers")
    assert customers.natural_key == ["id"]
    assert customers.grain is None  # never phrased


# ---------- LLM gets the natural key in its prompt -------------------------------------------


class _RecordingProvider(FakeLLMProvider):
    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:  # type: ignore[override]
        self.requests.append(request)
        return super().complete(request)


def test_llm_grain_prompt_carries_natural_key():
    provider = _RecordingProvider()
    build_catalog(FileConnector(EXAMPLES), llm=provider)
    grain_requests = [r for r in provider.requests if r.kind == "grain_description"]
    assert len(grain_requests) == 2  # customers + orders
    # The natural key should be embedded in every grain prompt.
    customer_req = next(r for r in grain_requests if r.meta.get("table") == "customers")
    assert "id" in customer_req.prompt


# ---------- Markdown rendering --------------------------------------------------------------


def test_markdown_renders_grain_block(tmp_path):
    catalog = build_catalog(FileConnector(EXAMPLES), llm=FakeLLMProvider())
    out = tmp_path / "md"
    export_markdown(catalog, out, layout="multi")
    customers_md = (out / "tables" / "customers.md").read_text()
    assert "**Grain:**" in customers_md
    assert "Natural key:" in customers_md
    assert "`id`" in customers_md
    # Index also gets a Grain column
    index = (out / "CATALOG.md").read_text()
    assert "Grain" in index.split("## Tables")[1]
