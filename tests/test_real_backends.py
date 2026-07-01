"""Real-backend integration tests (opt-in).

Skipped unless PLEASQL_RUN_REAL=1, because they download the MiniLM model and/or
call a live GPT-4o endpoint. Run with:

    PLEASQL_RUN_REAL=1 OPENAI_BASE_URL=... OPENAI_API_KEY=... uv run pytest tests/test_real_backends.py
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("PLEASQL_RUN_REAL") != "1",
    reason="set PLEASQL_RUN_REAL=1 to run real-backend tests",
)


def test_minilm_embedder_similarity():
    from pleasqlarify.pipeline.embed import MiniLMEmbedder

    emb = MiniLMEmbedder()
    v = emb.embed(["Opinion|A masterpiece.", "Opinion|A masterpiece.", "Genre|Drama"])
    assert v.shape[0] == 3
    # identical strings -> ~1 cosine; different -> lower
    assert float(v[0] @ v[1]) > 0.99
    assert float(v[0] @ v[2]) < float(v[0] @ v[1])


def test_umap_projection_runs():
    import numpy as np

    from pleasqlarify.pipeline.project import umap_project

    rng = np.random.default_rng(0)
    x = rng.random((12, 5))
    dist = np.linalg.norm(x[:, None] - x[None], axis=-1)
    coords = umap_project(dist)
    assert coords.shape == (12, 2)


def test_gpt4o_generation():
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("no OPENAI_API_KEY")
    from pleasqlarify.llm.client import OpenAIClient

    out = OpenAIClient(model="gpt-4o").generate("Reply with exactly: OK", n=1, temperature=0.0)
    assert "OK" in out[0]
