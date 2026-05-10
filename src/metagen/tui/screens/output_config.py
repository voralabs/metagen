"""Step 6 — pick what to include in the catalog and where to write it.

Grain checkboxes start all-on. Format defaults to Both. Output path defaults
to ./catalog.

Uses individual `Checkbox` widgets for grains rather than a `SelectionList`:
for a fixed list of boolean toggles, separate checkboxes match the user's
mental model (and the visual norm) better than a multi-select list whose
"selected" indicator looks like a delete affordance.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.widgets import Checkbox, Input, Label, RadioButton, RadioSet, Static

from metagen.core import CatalogGrains
from metagen.tui.path_utils import clean_path
from metagen.tui.screens.base import WizardScreen

GRAIN_OPTIONS = [
    ("table_descriptions", "Table descriptions (LLM)"),
    ("column_descriptions", "Column descriptions (LLM)"),
    ("column_stats", "Column statistics (nulls, distinct, min/max, mean)"),
    ("grain", "Dataset grain (natural key + plain-English summary)"),
    ("relationships", "Relationships (FK inference — single-column only in v1)"),
    ("quality", "Data quality grade"),
]


class OutputConfigScreen(WizardScreen):
    step_number = 4
    title = "What to include"
    next_label = "Run ▶"

    def compose_body(self) -> ComposeResult:
        session = self.app.session  # type: ignore[attr-defined]
        grains = session.grains

        yield Static(
            "Every value in the catalog is tagged with its source so you can\n"
            "tell facts from inferences:\n"
            "  [computed]    derived from the data itself\n"
            "  [llm · 0.85]  written by the LLM, with confidence 0–1\n"
            "  [user]        from the context you provided",
            classes="dim",
        )
        yield Static("")
        yield Static("Sections to include in the catalog:", classes="dim")
        for key, label in GRAIN_OPTIONS:
            yield Checkbox(label, value=getattr(grains, key), id=f"grain-{key}")

        yield Static("")
        yield Label("Output format")
        yield RadioSet(
            RadioButton("JSON", id="fmt-json", value=session.output_format == "json"),
            RadioButton("Markdown", id="fmt-md", value=session.output_format == "md"),
            RadioButton("Both", id="fmt-both", value=session.output_format == "both"),
            id="fmt",
        )

        yield Label("Markdown layout")
        yield RadioSet(
            RadioButton("Single file (CATALOG.md only)", id="layout-single", value=session.md_layout == "single"),
            RadioButton("Multi (index + tables/*.md)", id="layout-multi", value=session.md_layout == "multi"),
            id="layout",
        )

        yield Label("Output directory")
        yield Input(value=str(session.output_path), id="out-input")

    # ---- handlers ---------------------------------------------------------------------------

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        session = self.app.session  # type: ignore[attr-defined]
        if event.radio_set.id == "fmt":
            mapping = {"fmt-json": "json", "fmt-md": "md", "fmt-both": "both"}
            session.output_format = mapping[event.pressed.id]
        elif event.radio_set.id == "layout":
            session.md_layout = "single" if event.pressed.id == "layout-single" else "multi"

    def on_next(self) -> None:
        session = self.app.session  # type: ignore[attr-defined]
        # Read every checkbox state so direct widget toggles are picked up.
        grain_values: dict[str, bool] = {}
        for key, _label in GRAIN_OPTIONS:
            grain_values[key] = self.query_one(f"#grain-{key}", Checkbox).value
        session.grains = CatalogGrains(**grain_values)

        # Output path: clean quotes/whitespace/`~` the same way as Connection.
        raw = self.query_one("#out-input", Input).value
        cleaned = clean_path(raw) or "catalog"
        session.output_path = Path(cleaned)
        session.output_path_user_set = True

        from metagen.tui.screens.run import RunScreen

        self.app.push_screen(RunScreen())
