"""Step 8 — terminal state. Show what was written and let the user quit."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static

from metagen.tui.screens.base import WizardScreen


class DoneScreen(WizardScreen):
    step_number = 6
    title = "Done"
    next_label = "Quit"
    show_back = False
    show_quit = False  # primary action already quits — no redundant button

    def compose_body(self) -> ComposeResult:
        session = self.app.session  # type: ignore[attr-defined]
        catalog = session.catalog

        if catalog is not None:
            yield Static(
                f"[ok]Wrote {len(catalog.tables)} tables, "
                f"{sum(len(t.columns) for t in catalog.tables)} columns.[/]"
            )
        yield Static("")
        yield Static("[b]Files written:[/]")
        for p in session.written_paths or []:
            yield Static(f"  · {p}")
        yield Static("")
        yield Static(
            "Open the Markdown in VS Code or any Markdown viewer — "
            "GitHub-flavored Mermaid renders ERDs inline.",
            classes="dim",
        )

    def on_next(self) -> None:
        self.app.exit()
