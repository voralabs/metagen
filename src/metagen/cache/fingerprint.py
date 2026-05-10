"""Content fingerprints — stable hashes used as cache keys."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pyarrow as pa


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    return hash_bytes(text.encode("utf-8"))


def hash_json(payload: Any) -> str:
    return hash_text(json.dumps(payload, sort_keys=True, default=str))


def fingerprint_table(name: str, table: pa.Table, *, sample_rows: int = 1000) -> str:
    """Fingerprint a table from its schema plus a deterministic row sample.

    Cheap enough for repeated runs, sensitive enough to detect real changes.
    Not a cryptographic guarantee — just cache correctness.
    """
    h = hashlib.sha256()
    h.update(name.encode("utf-8"))
    h.update(b"\x00")
    for field in table.schema:
        h.update(field.name.encode("utf-8"))
        h.update(b"|")
        h.update(str(field.type).encode("utf-8"))
        h.update(b"\x00")
    h.update(str(table.num_rows).encode("utf-8"))
    h.update(b"\x00")
    head = table.slice(0, min(sample_rows, table.num_rows))
    for col in head.columns:
        for chunk in col.chunks:
            h.update(chunk.to_string().encode("utf-8"))
            h.update(b"\x00")
    return h.hexdigest()
