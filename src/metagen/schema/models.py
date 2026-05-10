"""Pydantic models for the semantic catalog.

The JSON serialization of `Catalog` is the canonical output contract,
validated against `output_schema_v1.json` on export.

Source tagging — every claim carries a `source` of `computed | llm | user`,
so downstream consumers can know which facts are verifiable from data and
which are inferred.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"

Source = Literal["computed", "llm", "user"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaggedValue(_Base):
    """A value plus provenance. `confidence` is required for llm, omitted otherwise."""

    value: Any
    source: Source
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class TaggedText(_Base):
    """Text field with provenance (description-style)."""

    text: str
    source: Source
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ColumnStats(_Base):
    """Deterministic per-column statistics. Always source=computed."""

    null_count: int = 0
    null_fraction: float = 0.0
    distinct_count: int | None = None
    distinct_fraction: float | None = None
    min: Any | None = None
    max: Any | None = None
    mean: float | None = None
    stddev: float | None = None
    top_values: list[dict[str, Any]] = Field(default_factory=list)
    histogram: list[dict[str, Any]] | None = None


class ValidationFlag(_Base):
    code: str
    message: str
    severity: Literal["info", "warning", "error"] = "warning"


class ColumnProfile(_Base):
    name: str
    dtype: str
    semantic_type: TaggedValue | None = None
    description: TaggedText | None = None
    stats: ColumnStats
    validation_flags: list[ValidationFlag] = Field(default_factory=list)


class QualityIssue(_Base):
    column: str | None = None
    code: str
    message: str


class TableQuality(_Base):
    grade: Literal["A", "B", "C", "D", "F"] | None = None
    completeness: float | None = None
    issues: list[QualityIssue] = Field(default_factory=list)


class TableProfile(_Base):
    name: str
    row_count: int
    description: TaggedText | None = None
    columns: list[ColumnProfile]
    quality: TableQuality | None = None
    # Grain — what does one row represent? `natural_key` is the computed
    # evidence (minimal column subset that uniquely identifies a row);
    # `grain` is its plain-English phrasing, source="llm" when phrased by an
    # LLM, source="computed" when we fell back to a stock template.
    natural_key: list[str] | None = None
    grain: TaggedText | None = None


class Relationship(_Base):
    table_a: str
    columns_a: list[str]
    table_b: str
    columns_b: list[str]
    cardinality: Literal["one-to-one", "one-to-many", "many-to-one", "many-to-many"]
    confidence: float = Field(ge=0.0, le=1.0)
    source: Source


class UserContext(_Base):
    glossary: dict[str, str] = Field(default_factory=dict)
    notes: str | None = None


class CatalogSource(_Base):
    type: Literal["files", "database"]
    paths: list[str] = Field(default_factory=list)
    connection_label: str | None = None


class Generator(_Base):
    name: str = "metagen"
    version: str


class Catalog(_Base):
    schema_version: str = SCHEMA_VERSION
    generated_at: datetime
    generator: Generator
    source: CatalogSource
    tables: list[TableProfile]
    relationships: list[Relationship] = Field(default_factory=list)
    user_context: UserContext = Field(default_factory=UserContext)

    @classmethod
    def new(cls, *, generator_version: str, source: CatalogSource, tables: list[TableProfile]) -> "Catalog":
        return cls(
            generated_at=datetime.now(timezone.utc),
            generator=Generator(version=generator_version),
            source=source,
            tables=tables,
        )
