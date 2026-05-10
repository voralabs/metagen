"""Generates `sample.xlsx` next to itself (run with `python sample.xlsx.py`).

Kept as a script rather than committing the binary so reviewers can see the
exact contents and regenerate.
"""

from pathlib import Path

import pandas as pd

OUT = Path(__file__).parent / "sample.xlsx"

with pd.ExcelWriter(OUT, engine="openpyxl") as writer:
    pd.DataFrame(
        {"id": [1, 2, 3], "name": ["a", "b", "c"]}
    ).to_excel(writer, sheet_name="people", index=False)
    pd.DataFrame(
        {"id": [10, 20], "label": ["x", "y"]}
    ).to_excel(writer, sheet_name="lookups", index=False)

print(f"Wrote {OUT}")
