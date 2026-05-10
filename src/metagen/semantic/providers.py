"""Real LLM providers — Anthropic (Claude) and OpenAI.

The `anthropic` and `openai` SDKs are optional installs. Providers lazy-import
their SDK so users who only run `--llm fake` don't need them.

Tests never exercise these network-backed paths — use `FakeLLMProvider` there.
Unit tests for these adapters inject a stub client via the constructor.
"""

from __future__ import annotations

import os
from typing import Any

from metagen.semantic.llm_provider import LLMProvider, LLMRequest, LLMResponse


class MissingAPIKeyError(RuntimeError):
    pass


def _require_env(var: str) -> str:
    value = os.environ.get(var)
    if not value:
        raise MissingAPIKeyError(
            f"{var} is not set. Add it to your environment or a local .env file."
        )
    return value


DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-7"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


class AnthropicProvider(LLMProvider):
    """Claude adapter. Requires `anthropic` SDK and `ANTHROPIC_API_KEY`.

    Model is picked in this order:
      1. explicit `model=...` constructor arg
      2. `ANTHROPIC_MODEL` env var (or .env entry)
      3. `DEFAULT_ANTHROPIC_MODEL` baked above
    """

    def __init__(
        self,
        model: str | None = None,
        *,
        client: Any | None = None,
        api_key: str | None = None,
    ) -> None:
        self._model = model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_ANTHROPIC_MODEL
        if client is not None:
            self._client = client
        else:
            try:
                import anthropic  # type: ignore[import-not-found]
            except ImportError as e:
                raise RuntimeError(
                    "The 'anthropic' package is not installed. `uv add anthropic` to use Claude."
                ) from e
            self._client = anthropic.Anthropic(api_key=api_key or _require_env("ANTHROPIC_API_KEY"))

    @property
    def name(self) -> str:
        return self._model

    def complete(self, request: LLMRequest) -> LLMResponse:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=request.max_tokens,
            system=request.system or "",
            messages=[{"role": "user", "content": request.prompt}],
        )
        # Anthropic SDK returns content as a list of blocks; take the first text block.
        blocks = getattr(message, "content", []) or []
        text = ""
        for block in blocks:
            if getattr(block, "type", None) == "text":
                text = getattr(block, "text", "")
                break
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                break
        return LLMResponse(text=text, model=self._model, prompt_version=request.prompt_version)


class OpenAIProvider(LLMProvider):
    """OpenAI adapter. Requires `openai` SDK and `OPENAI_API_KEY`.

    Model is picked in this order:
      1. explicit `model=...` constructor arg
      2. `OPENAI_MODEL` env var (or .env entry)
      3. `DEFAULT_OPENAI_MODEL` baked above
    """

    def __init__(
        self,
        model: str | None = None,
        *,
        client: Any | None = None,
        api_key: str | None = None,
    ) -> None:
        self._model = model or os.environ.get("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
        if client is not None:
            self._client = client
        else:
            try:
                import openai  # type: ignore[import-not-found]
            except ImportError as e:
                raise RuntimeError(
                    "The 'openai' package is not installed. `uv add openai` to use OpenAI."
                ) from e
            self._client = openai.OpenAI(api_key=api_key or _require_env("OPENAI_API_KEY"))

    @property
    def name(self) -> str:
        return self._model

    def complete(self, request: LLMRequest) -> LLMResponse:
        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        # OpenAI renamed `max_tokens` → `max_completion_tokens` for gpt-5 / o-series;
        # older models still accept the new name. Use it everywhere.
        completion = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_completion_tokens=request.max_tokens,
        )
        text = completion.choices[0].message.content or ""
        return LLMResponse(text=text, model=self._model, prompt_version=request.prompt_version)
