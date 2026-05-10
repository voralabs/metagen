"""Step 1 — pick the source file or directory.

Single screen replaces SourceKind + Provider + Connection from earlier drafts.
The format (CSV / Excel / Parquet) is detected from the path's suffix; for
Excel we expose an optional sheet name.

Validation is inline: clean the path (quotes, `~`, escaped spaces), confirm it
exists. No "Test connection" button — the path either resolves or it doesn't.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from textual.app import ComposeResult
from textual.widgets import Input, Label, Static

from metagen.connectors.file_connector import EXCEL_SUFFIXES, SUPPORTED_SUFFIXES
from metagen.tui.path_utils import clean_path
from metagen.tui.screens.base import WizardScreen


@dataclass(frozen=True)
class _ScanResult:
    supported: set[str]
    seen: set[str]            # all suffixes (including unsupported)
    file_count: int           # files seen with extensions
    bare_count: int           # files with NO extension
    error: str | None = None  # PermissionError or other access issue


def _scan_directory(path: Path) -> _ScanResult:
    """Scan a directory for supported and unsupported file suffixes.

    Returns supported + seen + counts + error. Prefers immediate children for
    speed; only falls back to a recursive walk when nothing supported turns up
    at the top level. Errors are reported, not silently swallowed.
    """
    supported: set[str] = set()
    seen: set[str] = set()
    file_count = 0
    bare_count = 0

    def _scan(it) -> None:
        nonlocal file_count, bare_count
        for p in it:
            try:
                if not p.is_file():
                    continue
            except OSError:
                continue
            suf = p.suffix.lower()
            if suf:
                file_count += 1
                seen.add(suf)
                if suf in SUPPORTED_SUFFIXES:
                    supported.add(suf)
            else:
                bare_count += 1

    try:
        _scan(path.iterdir())
    except PermissionError as e:
        return _ScanResult(set(), set(), 0, 0, f"Permission denied: {e.strerror or e}")
    except OSError as e:
        return _ScanResult(set(), set(), 0, 0, f"{type(e).__name__}: {e}")

    if not supported:
        try:
            _scan(p for p in path.rglob("*") if p != path)
        except (PermissionError, OSError):
            pass

    return _ScanResult(supported, seen, file_count, bare_count, None)


def _format_scan_error(path: Path, result: _ScanResult) -> str:
    """Build a diagnostic status line so users can see why detection failed."""
    if result.error:
        hint = ""
        if "Permission denied" in result.error:
            hint = (
                "  [dim]On macOS, give your terminal app access to this folder in\n"
                "  System Settings → Privacy & Security → Files and Folders.[/]"
            )
        return f"[error]{result.error}[/]\n{hint}".rstrip()

    if result.file_count == 0 and result.bare_count == 0:
        # Probably an empty directory, or one full of only subdirs.
        sub = sum(1 for p in path.iterdir() if p.is_dir()) if path.is_dir() else 0
        if sub > 0:
            return (
                f"[error]No files found here.[/] [dim]({sub} subdirectories — "
                "point at one of them, or a specific file.)[/]"
            )
        return "[error]Directory is empty.[/]"

    parts = ["[error]No CSV / Excel / Parquet files found.[/]"]
    if result.seen:
        parts.append(f"[dim]Saw extensions: {', '.join(sorted(result.seen))}[/]")
    if result.bare_count:
        parts.append(f"[dim]Plus {result.bare_count} file(s) with no extension.[/]")
    # Common gotcha: gzipped CSVs.
    if any(s in result.seen for s in (".gz", ".bz2", ".zip")):
        parts.append("[dim]Compressed files aren't supported yet — extract them first.[/]")
    if ".tsv" in result.seen:
        parts.append("[dim]TSV not yet supported. Rename to .csv (works fine — pyarrow auto-detects the delimiter).[/]")
    return "\n".join(parts)


def _classify(supported: set[str]) -> str | None:
    if not supported:
        return None
    if supported <= EXCEL_SUFFIXES:
        return "excel"
    if supported == {".csv"}:
        return "csv"
    if supported == {".parquet"}:
        return "parquet"
    return "mixed"


def _detect_format(path: Path) -> tuple[str | None, _ScanResult]:
    """Return (format, scan_result)."""
    if path.is_file():
        suffix = path.suffix.lower()
        seen = {suffix} if suffix else set()
        if suffix in EXCEL_SUFFIXES:
            fmt = "excel"
        elif suffix == ".csv":
            fmt = "csv"
        elif suffix == ".parquet":
            fmt = "parquet"
        else:
            fmt = None
        return fmt, _ScanResult(
            supported=({suffix} if fmt else set()),
            seen=seen,
            file_count=1,
            bare_count=0 if suffix else 1,
        )
    if path.is_dir():
        result = _scan_directory(path)
        return _classify(result.supported), result
    return None, _ScanResult(set(), set(), 0, 0)


class SourceScreen(WizardScreen):
    step_number = 1
    title = "Pick a file or directory"

    def compose_body(self) -> ComposeResult:
        session = self.app.session  # type: ignore[attr-defined]
        yield Static(
            "Supported formats: [b]CSV[/b], [b]Excel[/b] (.xlsx / .xls), [b]Parquet[/b].\n"
            "Point at a single file or a directory of files.",
            classes="dim",
        )
        yield Static("")
        yield Label("File or directory path")
        yield Input(
            value=str(session.file_path) if session.file_path else "",
            placeholder="/path/to/data.csv  or  /path/to/dir",
            id="path-input",
        )

        # Optional sheet field — only displayed when the path looks like Excel.
        # Hidden by default; we toggle visibility on input change.
        yield Label("Sheet name (Excel only — leave blank for all sheets)", id="sheet-label")
        yield Input(
            value=session.sheet or "",
            placeholder="e.g. Sheet1",
            id="sheet-input",
        )

        yield Static("", id="source-status", classes="dim")

    def on_mount(self) -> None:
        self._refresh_sheet_visibility()

    # ---- live format hint -------------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id in ("path-input", "sheet-input"):
            self._refresh_sheet_visibility()

    def _refresh_sheet_visibility(self) -> None:
        path_input = self.query_one("#path-input", Input)
        cleaned = clean_path(path_input.value)
        path = Path(cleaned) if cleaned else None
        fmt, result = _detect_format(path) if path else (None, _ScanResult(set(), set(), 0, 0))

        sheet_label = self.query_one("#sheet-label", Label)
        sheet_input = self.query_one("#sheet-input", Input)
        is_excel = fmt == "excel"
        sheet_label.display = is_excel
        sheet_input.display = is_excel

        status = self.query_one("#source-status", Static)
        if not cleaned or path is None:
            status.update("")
            return
        if not path.exists():
            status.update("[dim]Path doesn't exist yet — keep typing.[/]")
            return
        if fmt is None:
            status.update(_format_scan_error(path, result))
            return
        if fmt == "mixed":
            status.update("[dim]Detected: mixed formats (will load each by extension)[/]")
        else:
            status.update(f"[dim]Detected: {fmt}[/]")

    # ---- advance ----------------------------------------------------------------------------

    def on_next(self) -> None:
        session = self.app.session  # type: ignore[attr-defined]
        status = self.query_one("#source-status", Static)
        cleaned = clean_path(self.query_one("#path-input", Input).value)
        if not cleaned:
            status.update("[error]Path is required.[/]")
            return
        path = Path(cleaned)
        if not path.exists():
            status.update(f"[error]Path not found: {path}[/]")
            return
        fmt, result = _detect_format(path)
        if fmt is None:
            status.update(_format_scan_error(path, result))
            return

        session.file_path = path
        session.sheet = self.query_one("#sheet-input", Input).value.strip() or None
        # Default the output dir next to the data — but never clobber a value
        # the user already typed on step 4.
        if not session.output_path_user_set:
            base = path if path.is_dir() else path.parent
            session.output_path = base / "catalog"

        from metagen.tui.screens.context import ContextScreen

        self.app.push_screen(ContextScreen())
