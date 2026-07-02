"""LLM client seam for candidate generation (spec 03).

The pipeline depends only on the :class:`LLMClient` protocol, so the paper's
GPT-4o backend, an offline cache, and a deterministic mock all interchange.

Every client can emit a full record of each call (request + response body) to an
optional ``sink`` so an experiment run can capture complete LLM provenance. For
:class:`OpenAIClient` this is the real API request payload and the full response
(``response.model_dump()``); for the offline clients it is a synthetic body.
"""

from __future__ import annotations

from typing import Callable, Optional, Protocol

# A sink receives one dict per generated completion:
#   {"index", "model", "request", "response"}
CallSink = Callable[[dict], None]


class LLMClient(Protocol):
    def generate(self, prompt: str, n: int, temperature: float) -> list[str]: ...


class _SinkMixin:
    _sink: Optional[CallSink] = None

    def set_sink(self, sink: Optional[CallSink]) -> None:
        """Attach a per-call recorder (request/response bodies)."""
        self._sink = sink

    def _emit(self, record: dict) -> None:
        if self._sink is not None:
            self._sink(record)


class MockLLMClient(_SinkMixin):
    """Returns a fixed list of completions - deterministic, offline (spec 03, A4)."""

    def __init__(self, completions: list[str]):
        self._completions = list(completions)

    def generate(self, prompt: str, n: int, temperature: float) -> list[str]:
        for i, c in enumerate(self._completions):
            self._emit(
                {
                    "index": i,
                    "model": "mock",
                    "request": {"prompt": prompt, "n": n, "temperature": temperature},
                    "response": {"content": c},
                }
            )
        return list(self._completions)


class CachedLLMClient(_SinkMixin):
    """Serves completions from a JSON cache keyed by prompt (offline replay)."""

    def __init__(self, cache: dict[str, list[str]]):
        self._cache = cache

    def generate(self, prompt: str, n: int, temperature: float) -> list[str]:
        if prompt not in self._cache:
            raise KeyError("prompt not in generation cache")
        completions = list(self._cache[prompt])
        for i, c in enumerate(completions):
            self._emit(
                {
                    "index": i,
                    "model": "cache",
                    "request": {"prompt": prompt, "n": n, "temperature": temperature},
                    "response": {"content": c},
                }
            )
        return completions


class OpenAIClient(_SinkMixin):  # pragma: no cover - needs network + 'llm' extra
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

        self._base_url = base_url or os.environ.get("OPENAI_BASE_URL") or None
        self._client = OpenAI(
            base_url=self._base_url,
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        )
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def generate_one(
        self, prompt: str, temperature: float, index: int = 0, sink: Optional[CallSink] = None
    ) -> str:
        """A single thread-safe API call (the OpenAI SDK client is thread-safe).

        Records the full request + response body via ``sink`` (or ``self._sink``).
        Used by the experiment runner to parallelize recorded generation.
        """
        request = {
            "model": self._model,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        resp = self._client.chat.completions.create(**request)
        content = resp.choices[0].message.content or ""
        try:
            response_body = resp.model_dump()
        except Exception:
            response_body = {"content": content}
        record = {
            "index": index,
            "model": self._model,
            "base_url": self._base_url,
            "request": request,
            "response": response_body,
        }
        (sink or self._sink)(record) if (sink or self._sink) else None
        return content

    def generate(self, prompt: str, n: int, temperature: float) -> list[str]:
        # Independent samples for genuine i.i.d. sampling (spec 03, A3).
        return [self.generate_one(prompt, temperature, i) for i in range(n)]


__all__ = ["LLMClient", "CallSink", "MockLLMClient", "CachedLLMClient", "OpenAIClient"]
