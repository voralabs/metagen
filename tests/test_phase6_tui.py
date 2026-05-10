"""TUI smoke test — drive the wizard end-to-end via Pilot.

Uses the bundled CSV example via the Welcome → "Try sample data" affordance,
and the stats-only path (all LLM grains off) so no API keys are needed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from metagen.tui.app import MetagenApp
from metagen.tui.screens.context import ContextScreen
from metagen.tui.screens.done import DoneScreen
from metagen.tui.screens.output_config import OutputConfigScreen
from metagen.tui.screens.run import RunScreen
from metagen.tui.screens.tables import TablesScreen
from metagen.tui.screens.welcome import WelcomeScreen


@pytest.mark.asyncio
async def test_full_wizard_via_sample_button(tmp_path):
    app = MetagenApp()
    async with app.run_test() as pilot:
        # Welcome — click "Try sample data" to skip the Source screen.
        assert isinstance(app.screen, WelcomeScreen)
        await pilot.click("#welcome-sample")
        await pilot.pause()
        assert isinstance(app.screen, ContextScreen)

        # Context — leave blank, continue.
        await pilot.press("enter")
        await pilot.pause()

        # Tables — wait for discovery worker, then continue with all selected.
        assert isinstance(app.screen, TablesScreen)
        from textual.widgets import SelectionList, Static

        for _ in range(20):
            sel = app.screen.query_one("#tables-list", SelectionList)
            if sel.option_count >= 2:
                break
            await app.workers.wait_for_complete()
            await pilot.pause()
        assert sel.option_count >= 2, (
            f"discovery never populated; option_count={sel.option_count}"
        )
        sel.select_all()
        await pilot.pause()
        app.screen.action_next()
        await pilot.pause()

        # Output config — turn off LLM grains so we don't need API keys.
        assert isinstance(app.screen, OutputConfigScreen)
        from textual.widgets import Checkbox, Input

        for key in ("table_descriptions", "column_descriptions"):
            app.screen.query_one(f"#grain-{key}", Checkbox).value = False
        app.screen.query_one("#out-input", Input).value = str(tmp_path / "out")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        # Run — pipeline runs in a worker; allow time to drain and switch.
        for _ in range(8):
            if isinstance(app.screen, DoneScreen):
                break
            await app.workers.wait_for_complete()
            await pilot.pause()

        assert isinstance(app.screen, DoneScreen), (
            f"expected DoneScreen, got {type(app.screen).__name__}; "
            f"run_error={app.session.run_error!r}"
        )
        assert app.session.catalog is not None
        assert {t.name for t in app.session.catalog.tables} == {"customers", "orders"}

    assert (tmp_path / "out" / "catalog.json").exists()
    assert (tmp_path / "out" / "CATALOG.md").exists()


@pytest.mark.asyncio
async def test_source_screen_validates_path(tmp_path):
    """Type a bogus path on the Source screen — should NOT advance."""
    from metagen.tui.screens.source import SourceScreen
    from textual.widgets import Input

    app = MetagenApp()
    async with app.run_test() as pilot:
        await pilot.press("enter")  # Welcome → Source
        await pilot.pause()
        assert isinstance(app.screen, SourceScreen)

        bogus = str(tmp_path / "no_such_file.csv")
        app.screen.query_one("#path-input", Input).value = bogus
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        # Still on Source — bogus path doesn't exist.
        assert isinstance(app.screen, SourceScreen)
