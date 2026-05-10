"""Step 4 — optional free-form context the LLM should know about the data.

Think: "FY2024 e-commerce orders for Acme Corp; negative `total` means refund."
This is appended to every LLM prompt so descriptions are written *with* domain
knowledge the stats can't provide. Skipping is fine.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static, TextArea

from metagen.tui.screens.base import WizardScreen


class ContextScreen(WizardScreen):
    step_number = 2
    title = "Add context (optional)"

    def compose_body(self) -> ComposeResult:
        session = self.app.session  # type: ignore[attr-defined]
        yield Static(
            "Add anything the LLM should know about this data — domain, period,\n"
            "company, conventions, gotchas. The more relevant context, the more\n"
            "useful the generated descriptions. Or skip and continue.",
            classes="dim",
        )
        yield Static("")
        ta = TextArea(text=session.user_context, id="context-ta")
        ta.styles.height = 10
        yield ta

    def on_next(self) -> None:
        session = self.app.session  # type: ignore[attr-defined]
        session.user_context = self.query_one("#context-ta", TextArea).text
        from metagen.tui.screens.tables import TablesScreen

        self.app.push_screen(TablesScreen())
