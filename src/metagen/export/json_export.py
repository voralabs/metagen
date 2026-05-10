"""JSON exporter — the canonical, versioned output contract.

Every catalog written here is validated against `output_schema_v1.json`
*before* the file hits disk. A broken schema fails the run loudly.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from metagen.schema.models import Catalog


def _load_schema() -> dict[str, Any]:
    ref = resources.files("metagen.schema").joinpath("output_schema_v1.json")
    return json.loads(ref.read_text(encoding="utf-8"))


_SCHEMA: dict[str, Any] | None = None


def get_schema() -> dict[str, Any]:
    global _SCHEMA
    if _SCHEMA is None:
        _SCHEMA = _load_schema()
    return _SCHEMA


def catalog_to_dict(catalog: Catalog) -> dict[str, Any]:
    """Serialize a Catalog to a JSON-ready dict (ISO strings for datetimes)."""
    return json.loads(catalog.model_dump_json(exclude_none=False))


class SchemaValidationError(RuntimeError):
    """Raised when a catalog does not match output_schema_v1.json."""


def validate(catalog_dict: dict[str, Any]) -> None:
    validator = Draft202012Validator(get_schema())
    errors = sorted(validator.iter_errors(catalog_dict), key=lambda e: list(e.absolute_path))
    if errors:
        msg = "\n".join(
            f"  - {'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
            for e in errors[:10]
        )
        raise SchemaValidationError(f"Catalog failed schema validation:\n{msg}")


def export(catalog: Catalog, out_path: Path, *, indent: int = 2) -> Path:
    payload = catalog_to_dict(catalog)
    validate(payload)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=indent, default=str), encoding="utf-8")
    return out_path
