"""Textual application root — `metagen`.

Linear wizard:
  Welcome → Source → Context → Tables → Output → Run → Done

Every screen has Tab/Shift+Tab navigation, Enter for the primary action,
and Esc to go back. No memorised shortcuts.
"""

from __future__ import annotations

from dotenv import load_dotenv
from textual.app import App
from textual.binding import Binding

from metagen.tui.screens.welcome import WelcomeScreen
from metagen.tui.state import SessionState

# Load credentials from a local .env before any provider reads
# ANTHROPIC_API_KEY / OPENAI_API_KEY. `override=False` respects values
# already set in the shell environment.
load_dotenv(override=False)


class MetagenApp(App[None]):
    CSS = """
    Screen { background: $surface; align: center middle; }
    .wizard {
        width: 80;
        max-width: 90%;
        height: 100%;
        padding: 1 2;
        layout: vertical;
    }
    .wizard-body {
        height: 1fr;        /* takes all space above the buttons */
        padding-right: 1;
    }
    .wizard-buttons {
        height: auto;
        padding: 1 0 0 0;
    }
    .wizard-footer {
        height: 1;
        padding: 0;
        color: $text-muted;
    }
    .title { text-style: bold; color: $accent; }
    .step  { color: $text-muted; }
    .dim   { color: $text-muted; }
    .error { color: $error; }
    .ok    { color: $success; }
    Input, TextArea, Select { margin: 0 0 1 0; }
    Button { margin: 0 1 0 0; }
    Horizontal { height: auto; }
    """

    # Textual's default Ctrl+C asks the user to press Ctrl+Q to confirm — but
    # Ctrl+Q is intercepted by some IDEs (Cursor opens its sidebar). Override
    # so Ctrl+C just quits, and offer redundant alternatives.
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True, priority=True),
        Binding("ctrl+q", "quit", "Quit", show=False, priority=True),
        Binding("ctrl+d", "quit", "Quit", show=False, priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.session = SessionState()

    def on_mount(self) -> None:
        self.push_screen(WelcomeScreen())


def run() -> None:
    MetagenApp().run()
