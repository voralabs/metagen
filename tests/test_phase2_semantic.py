"""Phase 2 tests: analyzer, cache, Markdown determinism."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from metagen.cache.store import Cache
from metagen.connectors.file_connector import FileConnector
from metagen.core import build_catalog
from metagen.export.markdown_export import export as export_markdown
from metagen.schema.models import (
    Catalog,
    CatalogSource,
    ColumnProfile,
    ColumnStats,
    Generator,
    TableProfile,
)
from metagen.semantic.analyzer import analyze
from metagen.semantic.llm_provider import FakeLLMProvider, LLMRequest, LLMResponse

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "ecommerce"


def _tiny_catalog() -> Catalog:
    col = ColumnProfile(name="id", dtype="int64", stats=ColumnStats(null_count=0, null_fraction=0.0, distinct_count=3))
    tbl = TableProfile(name="t", row_count=3, columns=[col])
    return Catalog(
        generated_at=datetime.now(timezone.utc),
        generator=Generator(version="test"),
        source=CatalogSource(type="files", paths=["./x"]),
        tables=[tbl],
    )


def test_analyzer_with_fake_llm_layers_descriptions():
    catalog = _tiny_catalog()
    analyzed = analyze(catalog, FakeLLMProvider())
    assert analyzed.tables[0].description is not None
    assert analyzed.tables[0].description.source == "llm"
    assert "t" in analyzed.tables[0].description.text
    assert analyzed.tables[0].columns[0].description is not None
    assert analyzed.tables[0].columns[0].description.source == "llm"


def test_cache_hit_miss_and_prompt_version_invalidation(tmp_path):
    cache = Cache(root=tmp_path / "c")
    calls: list[str] = []

    class CountingProvider(FakeLLMProvider):
        def complete(self, request: LLMRequest) -> LLMResponse:  # type: ignore[override]
            calls.append(request.prompt_version)
            return super().complete(request)

    provider = CountingProvider()
    catalog = _tiny_catalog()

    analyze(catalog, provider, cache)
    first = len(calls)
    assert first > 0
    assert cache.misses == first
    assert cache.hits == 0

    # Re-run identical pipeline → all cache hits, no new provider calls.
    analyze(catalog, provider, cache)
    assert len(calls) == first
    assert cache.hits == first

    # Now simulate a prompt edit by bumping the version: cache key changes,
    # provider must be called again.
    import metagen.semantic.prompts as prompts_module

    original = prompts_module.VERSION
    try:
        prompts_module.VERSION = "p1-bumped"
        analyze(catalog, provider, cache)
    finally:
        prompts_module.VERSION = original

    assert len(calls) > first


def test_markdown_is_deterministic_given_same_catalog(tmp_path):
    catalog = build_catalog(FileConnector(EXAMPLES), llm=FakeLLMProvider())
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    export_markdown(catalog, out_a, layout="multi")
    export_markdown(catalog, out_b, layout="multi")
    for rel in ["CATALOG.md", "quality.md", "tables/customers.md", "tables/orders.md"]:
        assert (out_a / rel).read_text() == (out_b / rel).read_text()


def test_markdown_contains_source_badges(tmp_path):
    catalog = build_catalog(FileConnector(EXAMPLES), llm=FakeLLMProvider())
    out = tmp_path / "md"
    export_markdown(catalog, out, layout="multi")
    index = (out / "CATALOG.md").read_text()
    assert "[llm" in index
    orders = (out / "tables" / "orders.md").read_text()
    assert "[computed]" in orders
    assert "[llm" in orders


def test_markdown_single_layout_produces_one_file(tmp_path):
    catalog = build_catalog(FileConnector(EXAMPLES), llm=FakeLLMProvider())
    out = tmp_path / "single"
    written = export_markdown(catalog, out, layout="single")
    assert len(written) == 1
    assert written[0].name == "CATALOG.md"
    content = written[0].read_text()
    assert "# customers" in content
    assert "# orders" in content
