"""Shared in-memory state passed between TUI screens.

One-shot tool: nothing persists across runs except the output files the user
explicitly writes. No fingerprints, no annotations, no recall.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from metagen.core import CatalogGrains
from metagen.schema.models import Catalog


@dataclass
class SessionState:
    # Source: where the data lives (file or directory of files)
    file_path: Path | None = None
    sheet: str | None = None             # Excel only
    selected_tables: list[str] = field(default_factory=list)

    # Optional human context fed into LLM prompts
    user_context: str = ""

    # Output configuration
    grains: CatalogGrains = field(default_factory=CatalogGrains)
    output_format: str = "both"          # "json" | "md" | "both"
    md_layout: str = "multi"             # "single" | "multi"
    output_path: Path = field(default_factory=lambda: Path("catalog"))
    # True once the user has typed/edited the output path on step 4. Until
    # then, picking a source auto-defaults the output dir alongside the data.
    output_path_user_set: bool = False

    # Run results (set by the Run screen)
    catalog: Catalog | None = None
    written_paths: list[Path] = field(default_factory=list)
    run_error: str | None = None
