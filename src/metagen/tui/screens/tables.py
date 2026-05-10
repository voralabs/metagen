"""Step 3 — multi-select which tables/files to profile.

Discovery happens in a worker so the UI never blocks. For a single CSV that's
one row; for a directory it's one row per CSV/Parquet file; for an Excel
workbook it's one row per sheet. All selected by default.
"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, SelectionList, Static
from textual.widgets.selection_list import Selection

from metagen.connectors.file_connector import FileConnector
from metagen.tui.screens.base import WizardScreen


class TablesScreen(WizardScreen):
    step_number = 3
    title = "Pick what to include"

    def compose_body(self) -> ComposeResult:
        yield Static("Discovering tables…", id="tables-status", classes="dim")
        yield Static("[dim]Press Space to toggle a table; ↑/↓ to move.[/]")
        yield SelectionList[str](id="tables-list")
        yield Horizontal(
            Button("Select all", id="select-all"),
            Button("Select none", id="select-none"),
        )

    def on_mount(self) -> None:
        self._discover_tables()

    @work(thread=True, exclusive=True)
    def _discover_tables(self) -> None:
        session = self.app.session  # type: ignore[attr-defined]
        try:
            connector = FileConnector(session.file_path, sheet=session.sheet)
            names = [lt.name for lt in connector.tables()]
        except Exception as e:  # noqa: BLE001
            self.app.call_from_thread(
                self.query_one("#tables-status", Static).update,
                f"[error]{type(e).__name__}: {e}[/]",
            )
            return

        def _populate() -> None:
            status = self.query_one("#tables-status", Static)
            sel = self.query_one("#tables-list", SelectionList)
            sel.clear_options()
            for n in names:
                already = bool(session.selected_tables)
                initial = (n in session.selected_tables) if already else True
                sel.add_option(Selection(n, n, initial))
            status.update(f"[ok]Found {len(names)} tables.[/]")

        self.app.call_from_thread(_populate)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "select-all":
            self.query_one("#tables-list", SelectionList).select_all()
        elif event.button.id == "select-none":
            self.query_one("#tables-list", SelectionList).deselect_all()
        else:
            super().on_button_pressed(event)

    def on_next(self) -> None:
        sel = self.query_one("#tables-list", SelectionList)
        selected: list[str] = list(sel.selected)
        if not selected:
            self.query_one("#tables-status", Static).update(
                "[error]Pick at least one table.[/]"
            )
            return
        self.app.session.selected_tables = selected  # type: ignore[attr-defined]
        from metagen.tui.screens.output_config import OutputConfigScreen

        self.app.push_screen(OutputConfigScreen())
