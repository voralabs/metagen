"""Markdown exporter — deterministic, same JSON → same Markdown.

Contract defined in `claude_code_docs/product_plan.md` ("Output Contracts").
Renders source-tagged values as inline badges so every claim stays traceable:

    [computed] · [llm · 0.85] (confidence shown only when < 1.0) · [user]

Layouts:
  - `single` — one CATALOG.md (good for ≤ 3 tables)
  - `multi`  — CATALOG.md (index + ERD + questions) + tables/*.md + quality.md

Never hand-edited; regenerate from JSON on every run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from metagen.schema.models import (
    Catalog,
    ColumnProfile,
    Relationship,
    TableProfile,
    TaggedText,
)

Layout = Literal["single", "multi"]

MD_OVERVIEW_DESCRIPTION_MAX = 120


# ---------- badges / helpers ----------------------------------------------------------------


def _badge(source: str, confidence: float | None = None) -> str:
    if source == "llm" and confidence is not None and confidence < 1.0:
        return f"[llm · {confidence:.2f}]"
    return f"[{source}]"


def _tagged(tag: TaggedText | None) -> str:
    if tag is None:
        return ""
    return f"{tag.text} {_badge(tag.source, tag.confidence)}"


def _truncate(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _fmt_int(n: int) -> str:
    return f"{n:,}"


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def _stable_anchor(name: str) -> str:
    return name.lower().replace(" ", "-")


# ---------- sections ------------------------------------------------------------------------


def _render_header(catalog: Catalog) -> str:
    gen = catalog.generator
    gen_at = catalog.generated_at.strftime("%Y-%m-%d %H:%M UTC")
    src = catalog.source
    src_line = (
        f"**Source:** {src.type} — {', '.join(f'`{p}`' for p in src.paths)}"
        if src.paths
        else f"**Source:** {src.type}"
    )
    return (
        "# Data Catalog\n\n"
        f"**Generated:** {gen_at} · **Generator:** {gen.name} {gen.version} "
        f"· **Schema:** v{catalog.schema_version}\n"
        f"{src_line}\n\n"
        "> **Provenance.** Every value below is tagged with its source so you\n"
        "> can tell facts from inferences:\n"
        "> `[computed]` derived from the data · "
        "`[llm · 0.85]` written by the LLM (confidence 0–1) · "
        "`[user]` from the context you provided.\n"
    )


def _render_summary(catalog: Catalog) -> str:
    total_rows = sum(t.row_count for t in catalog.tables)
    grades = [t.quality.grade for t in catalog.tables if t.quality and t.quality.grade]
    avg_grade = grades[0] if len(set(grades)) == 1 and grades else "mixed"
    return (
        "## Summary\n"
        f"Tables: {len(catalog.tables)} · Total rows: {_fmt_int(total_rows)} · "
        f"Relationships: {len(catalog.relationships)} · Quality: {avg_grade}\n"
    )


def _render_tables_index(catalog: Catalog, *, link_prefix: str = "tables/") -> str:
    lines = [
        "## Tables\n",
        "| Table | Rows | Grain | Quality | Description |",
        "|---|---|---|---|---|",
    ]
    for t in catalog.tables:
        link = f"[{t.name}]({link_prefix}{t.name}.md)" if link_prefix else f"[{t.name}](#{_stable_anchor(t.name)})"
        grade = (t.quality.grade if t.quality else None) or "-"
        if t.description is not None:
            desc = _truncate(t.description.text, MD_OVERVIEW_DESCRIPTION_MAX)
            desc = f"{desc} {_badge(t.description.source, t.description.confidence)}"
        else:
            desc = ""
        if t.grain is not None:
            grain_cell = _truncate(t.grain.text, 60)
        elif t.natural_key:
            grain_cell = "key: " + ", ".join(f"`{c}`" for c in t.natural_key)
        else:
            grain_cell = "—"
        lines.append(f"| {link} | {_fmt_int(t.row_count)} | {grain_cell} | {grade} | {desc} |")
    return "\n".join(lines) + "\n"


def _render_relationships(relationships: list[Relationship]) -> str:
    if not relationships:
        return ""
    lines = ["## Relationships\n", "`````mermaid", "erDiagram"]
    arrows = {
        "one-to-one": "||--||",
        "one-to-many": "||--o{",
        "many-to-one": "}o--||",
        "many-to-many": "}o--o{",
    }
    for r in relationships:
        arrow = arrows.get(r.cardinality, "}o--||")
        label = ",".join(r.columns_a)
        lines.append(f"  {r.table_a} {arrow} {r.table_b} : {label}")
    lines.append("`````")
    return "\n".join(lines) + "\n"


def _render_glossary(catalog: Catalog) -> str:
    glossary = catalog.user_context.glossary
    if not glossary:
        return ""
    lines = ["## Glossary"]
    for term, definition in sorted(glossary.items()):
        lines.append(f"- **{term}** — {definition} [user]")
    return "\n".join(lines) + "\n"


# ---------- per-table rendering -------------------------------------------------------------


def _column_overview_row(c: ColumnProfile) -> str:
    sem = c.semantic_type.value if c.semantic_type else "—"
    null_pct = _fmt_pct(c.stats.null_fraction)
    distinct = _fmt_int(c.stats.distinct_count) if c.stats.distinct_count is not None else "—"
    if c.description is not None:
        desc = f"{_truncate(c.description.text, MD_OVERVIEW_DESCRIPTION_MAX)} {_badge(c.description.source, c.description.confidence)}"
    else:
        desc = ""
    return f"| `{c.name}` | {c.dtype} | {sem} | {null_pct} | {distinct} | {desc} |"


def _column_detail(c: ColumnProfile) -> str:
    lines: list[str] = [f"### `{c.name}`"]
    type_bits = [f"**Type:** {c.dtype}"]
    if c.semantic_type is not None:
        type_bits.append(
            f"**Semantic type:** {c.semantic_type.value} "
            f"{_badge(c.semantic_type.source, c.semantic_type.confidence)}"
        )
    lines.append(" · ".join(type_bits))
    if c.description is not None:
        lines.append(f"- **Description:** {_tagged(c.description)}")
    s = c.stats
    stat_parts = [f"nulls {_fmt_int(s.null_count)}"]
    if s.distinct_count is not None:
        stat_parts.append(f"distinct {_fmt_int(s.distinct_count)}")
    if s.min is not None:
        stat_parts.append(f"min {s.min}")
    if s.max is not None:
        stat_parts.append(f"max {s.max}")
    if s.mean is not None:
        stat_parts.append(f"mean {s.mean:.2f}")
    lines.append(f"- **Stats** [computed]: {' · '.join(stat_parts)}")
    if c.validation_flags:
        for f in c.validation_flags:
            lines.append(f"> {f.severity.upper()}: {f.code} — {f.message} [computed]")
    return "\n".join(lines) + "\n"


def _render_table(table: TableProfile, relationships: list[Relationship]) -> str:
    lines: list[str] = [f"# {table.name}\n"]
    grade = (table.quality.grade if table.quality else None) or "-"
    lines.append(
        f"**Rows:** {_fmt_int(table.row_count)} · **Columns:** {len(table.columns)} · "
        f"**Quality:** {grade}\n"
    )
    if table.description is not None:
        lines.append(f"> {table.description.text}\n> — {_badge(table.description.source, table.description.confidence)}\n")

    # Grain block — what does one row represent? Always render if either piece is known.
    if table.grain is not None or table.natural_key:
        nk = ", ".join(f"`{c}`" for c in table.natural_key) if table.natural_key else "_undetermined_"
        if table.grain is not None:
            grain_text = f"{table.grain.text} {_badge(table.grain.source, table.grain.confidence)}"
        else:
            grain_text = "_grain not phrased (LLM grain step disabled)_"
        lines.append(f"**Grain:** {grain_text}\n\n*Natural key:* {nk}\n")

    lines.append("## Columns (overview)\n")
    lines.append("| Column | Type | Semantic | Null % | Distinct | Description |")
    lines.append("|---|---|---|---|---|---|")
    for c in table.columns:
        lines.append(_column_overview_row(c))
    lines.append("")

    lines.append("## Columns (detail)\n")
    for c in table.columns:
        lines.append(_column_detail(c))

    related = [
        r
        for r in relationships
        if r.table_a == table.name or r.table_b == table.name
    ]
    if related:
        lines.append("## Relationships")
        for r in related:
            if r.table_a == table.name:
                left, right = f"`{','.join(r.columns_a)}`", f"`{r.table_b}.{','.join(r.columns_b)}`"
            else:
                left, right = f"`{','.join(r.columns_b)}`", f"`{r.table_a}.{','.join(r.columns_a)}`"
            lines.append(
                f"- {left} → {right} — {r.cardinality} {_badge(r.source, r.confidence)}"
            )
        lines.append("")

    if table.quality and table.quality.issues:
        lines.append("## Data Quality")
        if table.quality.completeness is not None:
            lines.append(
                f"**Grade:** {grade} · **Completeness:** {_fmt_pct(table.quality.completeness)}\n"
            )
        lines.append("**Issues** [computed]:")
        for issue in table.quality.issues:
            prefix = f"`{issue.column}`: " if issue.column else ""
            lines.append(f"- {prefix}{issue.message}")
        lines.append("")

    return "\n".join(lines)


def _render_quality_summary(catalog: Catalog) -> str:
    lines = ["# Data Quality\n", "| Table | Grade | Completeness | Issues |", "|---|---|---|---|"]
    for t in catalog.tables:
        q = t.quality
        grade = (q.grade if q else None) or "-"
        completeness = _fmt_pct(q.completeness) if (q and q.completeness is not None) else "—"
        issue_count = len(q.issues) if q else 0
        lines.append(f"| `{t.name}` | {grade} | {completeness} | {issue_count} |")
    return "\n".join(lines) + "\n"


# ---------- top-level entry points ----------------------------------------------------------


def _render_single(catalog: Catalog) -> str:
    sections = [
        _render_header(catalog),
        _render_summary(catalog),
        _render_tables_index(catalog, link_prefix=""),
        _render_relationships(catalog.relationships),
        _render_glossary(catalog),
    ]
    sections = [s for s in sections if s]
    body = "\n".join(sections)
    table_sections = [_render_table(t, catalog.relationships) for t in catalog.tables]
    return body + "\n" + "\n---\n\n".join(table_sections)


def _render_index(catalog: Catalog) -> str:
    sections = [
        _render_header(catalog),
        _render_summary(catalog),
        _render_tables_index(catalog, link_prefix="tables/"),
        _render_relationships(catalog.relationships),
        _render_glossary(catalog),
        "## Data Quality\nSee [quality.md](quality.md).\n",
    ]
    return "\n".join(s for s in sections if s)


def export(catalog: Catalog, out_dir: Path, *, layout: Layout = "multi") -> list[Path]:
    """Write Markdown to `out_dir`. Returns the list of written file paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    if layout == "single":
        path = out_dir / "CATALOG.md"
        path.write_text(_render_single(catalog), encoding="utf-8")
        written.append(path)
        return written

    # multi
    (out_dir / "tables").mkdir(parents=True, exist_ok=True)
    index_path = out_dir / "CATALOG.md"
    index_path.write_text(_render_index(catalog), encoding="utf-8")
    written.append(index_path)
    for t in catalog.tables:
        p = out_dir / "tables" / f"{t.name}.md"
        p.write_text(_render_table(t, catalog.relationships), encoding="utf-8")
        written.append(p)
    quality_path = out_dir / "quality.md"
    quality_path.write_text(_render_quality_summary(catalog), encoding="utf-8")
    written.append(quality_path)
    return written
