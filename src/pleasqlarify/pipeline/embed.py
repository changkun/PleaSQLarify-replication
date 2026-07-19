"""Step 2 (part 1) - result serialization + output embeddings (spec 04).

Produces the pairwise functional-similarity matrix ``S`` from query outputs.

Two embedders are provided:

* :class:`DeterministicEmbedder` (default) - a dependency-free hashing
  bag-of-tokens embedder. Identical outputs map to identical vectors (cosine 1);
  outputs sharing values map to higher cosine. This makes the whole pipeline and
  its tests run offline with no model download.
* :class:`MiniLMEmbedder` - the paper's ``all-MiniLM-L6-v2`` (ref [34]), used when
  the ``embeddings`` extra is installed (spec 04). Selecting it is a fidelity
  upgrade; the algorithm is identical.
"""

from __future__ import annotations

import hashlib
from typing import Protocol

import numpy as np

from ..model.types import Candidate, ResultTable

# One sentinel string for all degenerate outputs so error/empty results cluster
# together and away from value-bearing outputs (spec 04, A4).
_SENTINEL = "\x00NO_RESULT\x00"


# A4 serialization styles (spec 04). ``header_rows`` is the documented default;
# the others are the alternatives the assumption register lists, exposed so the
# A4 axis can be swept without editing code.
SerializationStyle = str  # "header_rows" | "values_only" | "columns_only" | "cells_sorted"
SERIALIZATION_STYLES = ("header_rows", "values_only", "columns_only", "cells_sorted")


def serialize_result(
    rt: ResultTable, max_chars: int = 4000, style: SerializationStyle = "header_rows"
) -> str:
    """Deterministic text rendering of a result table for embedding (spec 04, A3).

    Styles (assumption **A4**, all deterministic and length-capped):

    * ``header_rows`` (default) - header line of column names, then each
      (canonically pre-sorted, spec 01) row rendered ``col=value``.
    * ``values_only`` - rows without column names, so two queries that project the
      same values under different aliases embed identically and column-name
      overlap cannot inflate similarity.
    * ``columns_only`` - the header alone: purely structural similarity.
    * ``cells_sorted`` - the sorted set of distinct ``col=value`` cells, so row
      order and row count cannot dominate the embedding.
    """
    if rt.is_error or rt.is_empty:
        return _SENTINEL
    if style == "columns_only":
        text = "|".join(rt.columns)
    elif style == "values_only":
        text = "\n".join("; ".join(str(v) for v in row) for row in rt.rows)
    elif style == "cells_sorted":
        cells = {f"{c}={v}" for row in rt.rows for c, v in zip(rt.columns, row)}
        text = "; ".join(sorted(cells))
    elif style == "header_rows":
        lines = ["|".join(rt.columns)]
        for row in rt.rows:
            lines.append("; ".join(f"{c}={v}" for c, v in zip(rt.columns, row)))
        text = "\n".join(lines)
    else:
        raise ValueError(f"unknown serialization style: {style!r}")
    return text[:max_chars]


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> np.ndarray: ...


class DeterministicEmbedder:
    """Offline hashing bag-of-tokens embedder (L2-normalized)."""

    def __init__(self, dim: int = 256):
        self.dim = dim

    def _tokens(self, text: str) -> list[str]:
        # word tokens + character 3-grams, so both values and structure count
        import re

        words = re.findall(r"[A-Za-z0-9_.]+", text.lower())
        trigrams = [text[i : i + 3] for i in range(max(0, len(text) - 2))]
        return words + trigrams

    def embed(self, texts: list[str]) -> np.ndarray:
        vecs = np.zeros((len(texts), self.dim), dtype=np.float64)
        for i, text in enumerate(texts):
            for tok in self._tokens(text):
                h = int.from_bytes(
                    hashlib.blake2b(tok.encode(), digest_size=8).digest(), "little"
                )
                vecs[i, h % self.dim] += 1.0
            norm = np.linalg.norm(vecs[i])
            if norm > 0:
                vecs[i] /= norm
        return vecs


class MiniLMEmbedder:  # pragma: no cover - optional heavy dependency
    """The paper's all-MiniLM-L6-v2 embedder (spec 04); needs the 'embeddings' extra."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.asarray(
            self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False),
            dtype=np.float64,
        )


def similarity_matrix(
    candidates: list[Candidate],
    embedder: Embedder | None = None,
    style: SerializationStyle = "header_rows",
) -> np.ndarray:
    """Build the symmetric functional-similarity matrix S = cosine(outputs)."""
    embedder = embedder or DeterministicEmbedder()
    texts = [
        serialize_result(c.result or ResultTable(error="unrun"), style=style)
        for c in candidates
    ]
    vecs = embedder.embed(texts)
    # embeddings are L2-normalized, so the Gram matrix is cosine similarity
    sim = vecs @ vecs.T
    np.clip(sim, -1.0, 1.0, out=sim)
    # enforce exact symmetry + unit diagonal despite float error
    sim = (sim + sim.T) / 2.0
    np.fill_diagonal(sim, 1.0)
    return sim


__all__ = [
    "serialize_result",
    "SERIALIZATION_STYLES",
    "SerializationStyle",
    "Embedder",
    "DeterministicEmbedder",
    "MiniLMEmbedder",
    "similarity_matrix",
]
