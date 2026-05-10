"""Welcome — start a new run, or jump in with bundled sample data."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Static

from metagen import __version__
from metagen.tui.screens.base import WizardScreen

EXAMPLES_DIR = Path(__file__).resolve().parents[4] / "examples" / "ecommerce"


class WelcomeScreen(WizardScreen):
    title = "metagen"
    next_label = "Get started ▶"
    show_back = False

    def compose_body(self) -> ComposeResult:
        yield Static(f"v{__version__}", classes="dim")
        yield Static("")
        yield Static(
            "Profile a CSV, Excel, or Parquet dataset and generate a\n"
            "semantic catalog — JSON + Markdown describing every table\n"
            "and column, with statistics, relationships, and plain-English\n"
            "descriptions."
        )
        yield Static("")
        yield Static(
            "Use it as grounding context for LLMs that answer questions\n"
            "over your data.",
            classes="dim",
        )
        yield Static("")
        yield Horizontal(Button("Try sample data", id="welcome-sample"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "welcome-sample":
            self._launch_sample()
        else:
            super().on_button_pressed(event)

    def _launch_sample(self) -> None:
        session = self.app.session  # type: ignore[attr-defined]
        session.file_path = EXAMPLES_DIR
        session.sheet = None
        if not session.output_path_user_set:
            session.output_path = EXAMPLES_DIR / "catalog"
        from metagen.tui.screens.context import ContextScreen

        self.app.push_screen(ContextScreen())

    def on_next(self) -> None:
        from metagen.tui.screens.source import SourceScreen

        self.app.push_screen(SourceScreen())
