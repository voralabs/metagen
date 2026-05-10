"""Core pipeline — shared engine behind CLI and TUI.

connector → stats (sampled) → relationship inference → (optional) semantic analyzer.

`CatalogGrains` lets callers opt out of any specific section of the catalog.
The TUI exposes these as checkboxes; the CLI keeps independent flags
(`--no-relationships`, etc.) so existing scripts keep working.
"""

from __future__ import annotations

from dataclasses import dataclass

from metagen import __version__
from metagen.cache.store import Cache
from metagen.connectors.base import DataConnector
from metagen.profiler.grain import detect as detect_grain
from metagen.profiler.relationships import infer as infer_relationships
from metagen.profiler.sampling import SamplePlan
from metagen.profiler.statistical import profile_table
from metagen.schema.models import (
    Catalog,
    CatalogSource,
    ColumnProfile,
    ColumnStats,
    TableProfile,
    UserContext,
)
from metagen.semantic.analyzer import AnalyzerGrains, analyze
from metagen.semantic.llm_provider import LLMProvider


@dataclass(frozen=True)
class CatalogGrains:
    """Toggles for what the catalog actually contains. All on by default.

    Off-switches:
      - table_descriptions / column_descriptions: skip LLM calls
      - column_stats: keep dtype + null count, drop everything else
      - relationships: skip FK inference
      - quality: blank the per-table quality grade
    """

    table_descriptions: bool = True
    column_descriptions: bool = True
    column_stats: bool = True
    relationships: bool = True
    quality: bool = True
    grain: bool = True

    def to_analyzer(self) -> AnalyzerGrains:
        return AnalyzerGrains(
            table_descriptions=self.table_descriptions,
            column_descriptions=self.column_descriptions,
            grain=self.grain,
        )


def _strip_stats(profile: TableProfile) -> TableProfile:
    """Reduce stats to dtype + null count when the user opted out of full stats."""
    new_cols = [
        col.model_copy(
            update={
                "stats": ColumnStats(
                    null_count=col.stats.null_count,
                    null_fraction=col.stats.null_fraction,
                )
            }
        )
        for col in profile.columns
    ]
    return profile.model_copy(update={"columns": new_cols})


def build_catalog(
    connector: DataConnector,
    *,
    llm: LLMProvider | None = None,
    cache: Cache | None = None,
    sample_plan: SamplePlan | None = None,
    infer_fks: bool = True,
    grains: CatalogGrains | None = None,
    user_context: str | None = None,
) -> Catalog:
    grains = grains or CatalogGrains()
    do_relationships = infer_fks and grains.relationships

    loaded = list(connector.tables())
    tables: list[TableProfile] = [profile_table(lt, sample_plan) for lt in loaded]
    relationships = infer_relationships(loaded) if do_relationships else []

    # Grain detection (computed): pair each TableProfile with its raw pyarrow
    # table for a quick natural-key search. Reasons are stashed for the analyzer
    # so the LLM can phrase the grain humanly.
    grain_reasons: dict[str, str] = {}
    if grains.grain:
        keyed_tables: list[TableProfile] = []
        for tp, lt in zip(tables, loaded):
            result = detect_grain(tp, lt.table)
            grain_reasons[tp.name] = result.reason
            keyed_tables.append(tp.model_copy(update={"natural_key": result.natural_key}))
        tables = keyed_tables

    source = CatalogSource(**connector.describe_source())  # type: ignore[arg-type]
    catalog = Catalog.new(generator_version=__version__, source=source, tables=tables)
    update: dict[str, object] = {"relationships": relationships}
    if user_context:
        update["user_context"] = UserContext(notes=user_context)
    catalog = catalog.model_copy(update=update)

    if llm is not None and (
        grains.table_descriptions
        or grains.column_descriptions
        or grains.grain
    ):
        catalog = analyze(
            catalog, llm, cache,
            grains=grains.to_analyzer(),
            grain_reasons=grain_reasons,
        )

    # Strip stats and quality AFTER analysis so the LLM can use them while writing
    # descriptions, even though the user asked us not to surface them in the output.
    if not grains.column_stats:
        catalog = catalog.model_copy(
            update={"tables": [_strip_stats(t) for t in catalog.tables]}
        )
    if not grains.quality:
        catalog = catalog.model_copy(
            update={"tables": [t.model_copy(update={"quality": None}) for t in catalog.tables]}
        )
    return catalog
