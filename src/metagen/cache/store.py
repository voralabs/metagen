"""On-disk two-tier cache.

Tiers:
  - `llm/`   — LLM responses keyed on (system, prompt, prompt_version)
  - `stats/` — reserved for Phase 3 when sampling-based stats get expensive;
               currently unused (computed stats are cheap).

Location: `~/.metagen/cache/` by default. Deleting the directory is safe.
Cache hits are pure reads; misses compute via the supplied callback and write.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from metagen.cache.fingerprint import hash_text
from metagen.semantic.llm_provider import LLMProvider, LLMRequest, LLMResponse

DEFAULT_CACHE_ROOT = Path.home() / ".metagen" / "cache"


def _llm_key(request: LLMRequest, provider_name: str) -> str:
    # prompt_version + provider are both load-bearing: bumping a prompt OR
    # switching from fake → openai must invalidate old entries, or cached
    # Fake stubs leak into real-provider runs.
    material = "\n---\n".join(
        [
            provider_name,
            request.prompt_version,
            request.system or "",
            request.prompt,
        ]
    )
    return hash_text(material)


class Cache:
    def __init__(self, root: Path = DEFAULT_CACHE_ROOT, *, enabled: bool = True) -> None:
        self._root = root
        self._enabled = enabled
        self.hits = 0
        self.misses = 0
        if enabled:
            (self._root / "llm").mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def clear(self) -> None:
        if not self._root.exists():
            return
        for p in self._root.rglob("*.json"):
            p.unlink()

    def get_or_compute_llm(
        self,
        request: LLMRequest,
        compute: Callable[[], LLMResponse],
        *,
        provider: LLMProvider | str,
    ) -> LLMResponse:
        if not self._enabled:
            self.misses += 1
            return compute()
        provider_name = provider if isinstance(provider, str) else provider.name
        key = _llm_key(request, provider_name)
        path = self._root / "llm" / f"{key}.json"
        if path.exists():
            self.hits += 1
            data = json.loads(path.read_text(encoding="utf-8"))
            return LLMResponse(**data)
        self.misses += 1
        response = compute()
        path.write_text(json.dumps(asdict(response)), encoding="utf-8")
        return response
