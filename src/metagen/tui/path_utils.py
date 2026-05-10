"""Normalize user-typed paths.

Common paste artefacts on macOS / Linux:
  - "Copy as Pathname" wraps in single quotes
  - Drag-and-drop into many terminals backslash-escapes spaces
  - `~` is meaningful to shells but not to `pathlib.Path`
  - Stray surrounding whitespace
"""

from __future__ import annotations

from pathlib import Path


def clean_path(raw: str) -> str:
    """Return a clean string version of a user-typed path.

    Strips surrounding quotes and whitespace, unescapes spaces, and expands `~`.
    Returns an empty string if the input is empty or whitespace-only.
    """
    s = (raw or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        s = s[1:-1]
    s = s.replace("\\ ", " ")
    if not s:
        return ""
    return str(Path(s).expanduser())
