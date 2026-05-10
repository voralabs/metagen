"""Phase 3 tests: relationships + sampling. (Provider tests dropped along with
DB support — Anthropic/OpenAI adapters are exercised via Phase 6 user-context
tests instead.)"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa

from metagen.connectors.base import LoadedTable
from metagen.connectors.file_connector import FileConnector
from metagen.core import build_catalog
from metagen.profiler.relationships import infer as infer_relationships
from metagen.profiler.sampling import SamplePlan
from metagen.profiler.statistical import profile_table
from metagen.semantic.llm_provider import FakeLLMProvider

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "ecommerce"


# ---------- relationships -------------------------------------------------------------------


def test_infer_detects_orders_customer_id_to_customers_id():
    loaded = list(FileConnector(EXAMPLES).tables())
    relationships = infer_relationships(loaded)
    assert len(relationships) == 1
    r = relationships[0]
    assert r.table_a == "orders"
    assert r.columns_a == ["customer_id"]
    assert r.table_b == "customers"
    assert r.columns_b == ["id"]
    assert r.cardinality == "many-to-one"
    assert r.source == "computed"
    assert r.confidence > 0.9


def test_infer_rejects_when_parent_not_unique():
    parent = pa.table({"id": [1, 1, 2]})
    child = pa.table({"id": [1, 2, 1]})
    rels = infer_relationships(
        [LoadedTable(name="customers", table=parent), LoadedTable(name="orders", table=child)]
    )
    assert rels == []


def test_infer_rejects_low_containment():
    parent = pa.table({"id": [1, 2, 3]})
    child = pa.table({"customer_id": [1, 2, 99, 100, 101]})
    rels = infer_relationships(
        [
            LoadedTable(name="customers", table=parent),
            LoadedTable(name="orders", table=child),
        ]
    )
    assert rels == []


# ---------- sampling ------------------------------------------------------------------------


def test_profile_table_samples_when_over_threshold():
    data = pa.table({"x": list(range(1000))})
    plan = SamplePlan(sample_rows=100, threshold=500, seed=0)
    profile = profile_table(LoadedTable(name="big", table=data), plan)
    assert profile.row_count == 1000
    assert profile.quality is not None
    codes = [i.code for i in profile.quality.issues]
    assert "sampled_stats" in codes
    col = profile.columns[0]
    assert col.stats.distinct_count is not None
    assert col.stats.distinct_count <= 100


def test_profile_table_skips_sampling_for_small_tables():
    data = pa.table({"x": list(range(50))})
    plan = SamplePlan(sample_rows=10, threshold=100)
    profile = profile_table(LoadedTable(name="small", table=data), plan)
    assert profile.row_count == 50
    assert profile.quality is not None
    assert all(i.code != "sampled_stats" for i in profile.quality.issues)


# ---------- build_catalog end-to-end with relationships -------------------------------------


def test_build_catalog_attaches_relationships():
    catalog = build_catalog(FileConnector(EXAMPLES), llm=FakeLLMProvider())
    assert len(catalog.relationships) == 1
    assert catalog.relationships[0].source == "computed"
