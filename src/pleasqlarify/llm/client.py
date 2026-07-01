"""LLM client seam for candidate generation (spec 03).

The pipeline depends only on the :class:`LLMClient` protocol, so the paper's
GPT-4o backend, an offline cache, and a deterministic mock all interchange.
"""

from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    def generate(self, prompt: str, n: int, temperature: float) -> list[str]: ...


class MockLLMClient:
    """Returns a fixed list of completions - deterministic, offline (spec 03, A4)."""

    def __init__(self, completions: list[str]):
        self._completions = list(completions)

    def generate(self, prompt: str, n: int, temperature: float) -> list[str]:
        return list(self._completions)


class CachedLLMClient:
    """Serves completions from a JSON cache keyed by prompt (offline replay)."""

    def __init__(self, cache: dict[str, list[str]]):
        self._cache = cache

    def generate(self, prompt: str, n: int, temperature: float) -> list[str]:
        if prompt not in self._cache:
            raise KeyError("prompt not in generation cache")
        return list(self._cache[prompt])


class OpenAIClient:  # pragma: no cover - needs network + 'llm' extra
    """The paper's generator: GPT-4o via an OpenAI-compatible API (spec 03).

    ``base_url`` / ``api_key`` default to the ``OPENAI_BASE_URL`` /
    ``OPENAI_API_KEY`` environment variables so credentials are never hardcoded.
    Works against any OpenAI-compatible gateway (e.g. an internal proxy).
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        base_url: str | None = None,
        api_key: str | None = None,
    ):
        import os

        from openai import OpenAI

        self._client = OpenAI(
            base_url=base_url or os.environ.get("OPENAI_BASE_URL") or None,
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        )
        self._model = model

    def generate(self, prompt: str, n: int, temperature: float) -> list[str]:
        # Independent samples for genuine i.i.d. sampling (spec 03, A3).
        out: list[str] = []
        for _ in range(n):
            resp = self._client.chat.completions.create(
                model=self._model,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            out.append(resp.choices[0].message.content or "")
        return out


__all__ = ["LLMClient", "MockLLMClient", "CachedLLMClient", "OpenAIClient"]
