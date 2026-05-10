"""Phase 6 engine tests: user_context in prompts, grain flags, Excel."""

from __future__ import annotations

from pathlib import Path

from metagen.connectors.file_connector import FileConnector
from metagen.core import CatalogGrains, build_catalog
from metagen.semantic.llm_provider import FakeLLMProvider, LLMRequest, LLMResponse

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "ecommerce"
EXCEL_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample.xlsx"


# ---------- user_context flow ---------------------------------------------------------------


class _RecordingProvider(FakeLLMProvider):
    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:  # type: ignore[override]
        self.requests.append(request)
        return super().complete(request)


def test_user_context_lands_in_llm_prompts():
    provider = _RecordingProvider()
    context = "FY24 ecommerce orders for Acme Corp; negative totals are refunds."
    catalog = build_catalog(
        FileConnector(EXAMPLES),
        llm=provider,
        cache=None,
        user_context=context,
    )

    relevant = [
        r
        for r in provider.requests
        if r.kind in {"table_description", "column_description"}
    ]
    assert len(relevant) > 0
    for r in relevant:
        assert "Domain context" in r.prompt
        assert "Acme Corp" in r.prompt

    assert catalog.user_context.notes == context


def test_user_context_empty_does_not_inject_block():
    provider = _RecordingProvider()
    build_catalog(FileConnector(EXAMPLES), llm=provider, user_context="")
    for r in provider.requests:
        assert "Domain context" not in r.prompt


# ---------- grain flags ---------------------------------------------------------------------


def test_grain_flags_drop_descriptions_and_relationships():
    grains = CatalogGrains(
        table_descriptions=False,
        column_descriptions=False,
        relationships=False,
        column_stats=True,
        quality=True,
    )
    catalog = build_catalog(FileConnector(EXAMPLES), llm=FakeLLMProvider(), grains=grains)

    for t in catalog.tables:
        assert t.description is None
        for c in t.columns:
            assert c.description is None
    assert catalog.relationships == []


def test_grain_column_stats_off_strips_to_nulls_only():
    grains = CatalogGrains(column_stats=False)
    catalog = build_catalog(FileConnector(EXAMPLES), llm=None, grains=grains)
    for t in catalog.tables:
        for c in t.columns:
            assert c.stats.null_count >= 0
            assert c.stats.distinct_count is None
            assert c.stats.min is None
            assert c.stats.max is None
            assert c.stats.mean is None
            assert c.stats.top_values == []


def test_grain_quality_off_blanks_quality():
    catalog = build_catalog(FileConnector(EXAMPLES), llm=None, grains=CatalogGrains(quality=False))
    for t in catalog.tables:
        assert t.quality is None


# ---------- Excel ----------------------------------------------------------------------------


def test_excel_connector_loads_each_sheet_as_a_table():
    connector = FileConnector(EXCEL_FIXTURE)
    tables = list(connector.tables())
    names = sorted(t.name for t in tables)
    assert names == ["sample__lookups", "sample__people"]
    people = next(t for t in tables if t.name == "sample__people")
    assert people.table.num_rows == 3
    assert set(people.table.schema.names) == {"id", "name"}
