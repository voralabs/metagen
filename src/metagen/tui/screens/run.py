"""Step 5 — run the pipeline and show progress.

LLM provider is auto-picked from environment:
  ANTHROPIC_API_KEY → Claude
  OPENAI_API_KEY    → OpenAI
  neither set       → fail with a clear message (unless every LLM-driven grain
                      is off, in which case we run stats-only)

The whole pipeline runs in a thread worker so the UI stays responsive and Esc
can cancel.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Static

from metagen.cache.store import Cache
from metagen.connectors.file_connector import FileConnector
from metagen.core import CatalogGrains, build_catalog
from metagen.export.json_export import export as export_json
from metagen.export.markdown_export import export as export_markdown
from metagen.semantic.llm_provider import LLMProvider
from metagen.tui.screens.base import WizardScreen


@dataclass
class StageMessage(Message):
    text: str


@dataclass
class PipelineDone(Message):
    written: list[Path]
    error: str | None = None


def _wants_llm(grains: CatalogGrains) -> bool:
    return grains.table_descriptions or grains.column_descriptions or grains.grain


def _pick_llm(grains: CatalogGrains) -> LLMProvider | None:
    if not _wants_llm(grains):
        return None
    if os.environ.get("ANTHROPIC_API_KEY"):
        from metagen.semantic.providers import AnthropicProvider

        return AnthropicProvider()
    if os.environ.get("OPENAI_API_KEY"):
        from metagen.semantic.providers import OpenAIProvider

        return OpenAIProvider()
    raise RuntimeError(
        "LLM-driven catalog sections are enabled but no API key is set.\n"
        "Add ANTHROPIC_API_KEY or OPENAI_API_KEY to your environment or .env, "
        "or untick the LLM grains on the previous step."
    )


class RunScreen(WizardScreen):
    step_number = 5
    title = "Generating catalog"
    next_label = "Cancel"
    show_back = False

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def compose_body(self) -> ComposeResult:
        with Vertical(id="run-log"):
            yield Static("Starting…", id="run-status")

    def on_mount(self) -> None:
        self._worker = self._run_pipeline()

    @work(thread=True, exclusive=True)
    def _run_pipeline(self) -> None:
        session = self.app.session  # type: ignore[attr-defined]
        try:
            self.post_message(StageMessage("Reading source files…"))
            connector = FileConnector(session.file_path, sheet=session.sheet)

            self.post_message(StageMessage("Picking LLM…"))
            llm = _pick_llm(session.grains)
            if llm is not None:
                self.post_message(StageMessage(f"Using {llm.name}"))

            cache = Cache()
            self.post_message(StageMessage("Profiling tables and columns…"))
            catalog = build_catalog(
                connector,
                llm=llm,
                cache=cache,
                grains=session.grains,
                user_context=session.user_context or None,
            )

            # Filter to user-selected tables (FileConnector returns all of them).
            if session.selected_tables:
                kept = [t for t in catalog.tables if t.name in set(session.selected_tables)]
                catalog = catalog.model_copy(update={"tables": kept})

            session.catalog = catalog

            self.post_message(StageMessage("Writing files…"))
            out = Path(session.output_path)
            out.mkdir(parents=True, exist_ok=True)
            written: list[Path] = []
            if session.output_format in ("json", "both"):
                written.append(export_json(catalog, out / "catalog.json"))
            if session.output_format in ("md", "both"):
                written.extend(export_markdown(catalog, out, layout=session.md_layout))

            session.written_paths = written
            self.post_message(PipelineDone(written=written))
        except Exception as e:  # noqa: BLE001
            session.run_error = str(e)
            self.post_message(PipelineDone(written=[], error=str(e)))

    def on_stage_message(self, message: StageMessage) -> None:
        log = self.query_one("#run-log", Vertical)
        log.mount(Static(f"[dim]·[/] {message.text}"))

    def on_pipeline_done(self, message: PipelineDone) -> None:
        if message.error:
            log = self.query_one("#run-log", Vertical)
            log.mount(Static(f"[error]Failed:[/] {message.error}", classes="error"))
            self.query_one("#run-status", Static).update("[error]Run failed.[/]")
            return
        from metagen.tui.screens.done import DoneScreen

        self.app.switch_screen(DoneScreen())

    def action_cancel(self) -> None:
        if getattr(self, "_worker", None) is not None:
            self._worker.cancel()
        self.app.pop_screen()
