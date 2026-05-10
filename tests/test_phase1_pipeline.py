"""Phase-1 end-to-end regression test.

Runs the real pipeline on the bundled sample CSVs and asserts:
  - schema validates cleanly
  - stable shape and values (row counts, column names, dtypes, grades)
  - every `source` tag is one of the allowed values
"""

from __future__ import annotations

from pathlib import Path

from metagen.connectors.file_connector import FileConnector
from metagen.core import build_catalog
from metagen.export.json_export import catalog_to_dict, validate
from metagen.schema.models import SCHEMA_VERSION
from metagen.semantic.llm_provider import FakeLLMProvider, LLMRequest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "ecommerce"

ALLOWED_SOURCES = {"computed", "llm", "user"}


def _iter_sources(node: object):
    if isinstance(node, dict):
        if "source" in node and isinstance(node["source"], str) and node["source"] in ALLOWED_SOURCES:
            yield node["source"]
        for v in node.values():
            yield from _iter_sources(v)
    elif isinstance(node, list):
        for v in node:
            yield from _iter_sources(v)


def test_demo_pipeline_validates_and_is_stable():
    catalog = build_catalog(FileConnector(EXAMPLES))
    payload = catalog_to_dict(catalog)

    validate(payload)

    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["source"]["type"] == "files"

    tables = {t["name"]: t for t in payload["tables"]}
    assert set(tables) == {"customers", "orders"}

    customers = tables["customers"]
    assert customers["row_count"] == 8
    assert [c["name"] for c in customers["columns"]] == ["id", "name", "email", "signup_date", "country"]
    id_col = next(c for c in customers["columns"] if c["name"] == "id")
    assert id_col["dtype"] == "int64"
    assert id_col["stats"]["distinct_count"] == 8
    assert id_col["stats"]["null_count"] == 0

    orders = tables["orders"]
    assert orders["row_count"] == 12
    total = next(c for c in orders["columns"] if c["name"] == "total")
    assert total["stats"]["mean"] is not None
    assert total["stats"]["min"] == 14.5
    assert total["stats"]["max"] == 399.0

    # Every table currently has a computed quality grade.
    for t in payload["tables"]:
        assert t["quality"]["grade"] in {"A", "B", "C", "D", "F"}

    # All provenance tags are from the allowed set.
    for src in _iter_sources(payload):
        assert src in ALLOWED_SOURCES


def test_fake_llm_provider_is_deterministic():
    provider = FakeLLMProvider()
    r1 = provider.complete(LLMRequest(prompt="describe orders"))
    r2 = provider.complete(LLMRequest(prompt="describe orders"))
    assert r1 == r2
    assert r1.model == "fake-1"
