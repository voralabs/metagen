"""Wizard base screen — shared chrome (header + Back/Next/Quit) and key bindings.

The wizard body lives inside a `VerticalScroll` so screens with more fields
than the terminal height (e.g. Snowflake's 6 fields, BigQuery's 3) scroll
naturally instead of pushing content offscreen.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Static

TOTAL_STEPS = 6  # Welcome (no number) + 6 working steps:
# 1 Source · 2 Context · 3 Tables · 4 Output · 5 Run · 6 Done


class WizardScreen(Screen[None]):
    """Base class for the linear wizard.

    Subclasses implement `step_number`, `title`, and `compose_body()` plus
    `on_next()` for the primary action.
    """

    step_number: int = 0
    title: str = ""
    next_label: str = "Next"
    show_back: bool = True
    show_quit: bool = True   # set False on screens whose primary action IS quit

    BINDINGS = [
        Binding("enter", "next", "Continue", priority=True),
        Binding("ctrl+j", "next", "Continue", show=False, priority=True),
        Binding("escape", "back", "Back"),
    ]

    # ---- subclass hooks ---------------------------------------------------------------------

    def compose_body(self) -> ComposeResult:
        return iter(())

    def on_next(self) -> None:
        """Override to handle the primary action. Push the next screen here."""

    # ---- chrome -----------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical(classes="wizard"):
            with VerticalScroll(classes="wizard-body"):
                if self.step_number:
                    yield Static(f"Step {self.step_number} of {TOTAL_STEPS}", classes="step")
                yield Static(self.title or "", classes="title")
                yield Static("")  # spacer
                yield from self.compose_body()
            with Horizontal(classes="wizard-buttons"):
                if self.show_back:
                    yield Button("◀ Back", id="wizard-back")
                yield Button(self.next_label, id="wizard-next", variant="primary")
                if self.show_quit:
                    yield Button("Quit", id="wizard-quit", variant="error")
            yield Static(
                "[dim]Tab/Shift+Tab move focus · Enter continue · Esc back · Ctrl+C quit[/]",
                classes="wizard-footer",
            )

    # ---- actions ----------------------------------------------------------------------------

    def action_next(self) -> None:
        self.on_next()

    def action_back(self) -> None:
        if self.show_back:
            self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "wizard-next":
            self.on_next()
        elif event.button.id == "wizard-back":
            self.action_back()
        elif event.button.id == "wizard-quit":
            self.app.exit()
