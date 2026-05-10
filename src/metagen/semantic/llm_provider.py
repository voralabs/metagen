"""LLM provider abstraction and a deterministic Fake for tests/dev.

Phase 2: the Fake routes by `LLMRequest.kind` so it can produce meaningful,
prompt-appropriate stub output for the analyzer — still no network.
Claude/OpenAI adapters arrive in Phase 3.

Tests MUST use FakeLLMProvider — no live calls in CI.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

PromptKind = Literal[
    "table_description",
    "column_description",
    "grain_description",
]


@dataclass(frozen=True)
class LLMRequest:
    prompt: str
    system: str | None = None
    kind: PromptKind | None = None
    prompt_version: str = "unversioned"
    # Arbitrary payload to help deterministic Fakes produce targeted output.
    meta: dict[str, str] = field(default_factory=dict)
    max_tokens: int = 512


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    prompt_version: str


class LLMProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def complete(self, request: LLMRequest) -> LLMResponse: ...


class FakeLLMProvider(LLMProvider):
    """Deterministic stub. Returns prompt-appropriate canned text by `kind`.

    Output is stable across runs so golden-file tests work. Never makes a network call.
    """

    model_name = "fake-1"

    @property
    def name(self) -> str:
        return self.model_name

    def complete(self, request: LLMRequest) -> LLMResponse:
        kind = request.kind
        meta = request.meta
        if kind == "table_description":
            table = meta.get("table", "table")
            text = f"Auto-generated description for `{table}`."
        elif kind == "column_description":
            column = meta.get("column", "column")
            table = meta.get("table", "table")
            text = f"Auto-generated description for `{table}.{column}`."
        elif kind == "grain_description":
            table = meta.get("table", "table")
            key = meta.get("natural_key", "")
            text = f"One row per {key or 'record'} (table `{table}`)."
        else:
            text = "stubbed response"
        return LLMResponse(text=text, model=self.model_name, prompt_version=request.prompt_version)
