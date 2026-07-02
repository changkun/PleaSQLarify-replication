"""Tests for the experiment artifact system (offline)."""

from __future__ import annotations

import json
import os

import numpy as np
import pytest

from pleasqlarify.data.ambrosia import DEFAULT_AMBROSIA_ROOT
from pleasqlarify.experiment.recorder import RunRecorder
from pleasqlarify.llm.client import MockLLMClient


def test_llm_sink_captures_request_and_response():
    records = []
    client = MockLLMClient(["SELECT 1", "SELECT 2"])
    client.set_sink(records.append)
    out = client.generate("the prompt", n=2, temperature=0.7)
    assert out == ["SELECT 1", "SELECT 2"]
    assert len(records) == 2
    for r in records:
        assert "request" in r and "response" in r
        assert r["request"]["prompt"] == "the prompt"
        assert "content" in r["response"]


def test_recorder_writes_tree(tmp_path):
    rec = RunRecorder(tmp_path / "run", {"model": "mock", "n": 2})
    assert (rec.root / "config.json").exists()

    sink = rec.llm_sink("mock", "s1")
    sink({"index": 0, "request": {"prompt": "p"}, "response": {"content": "SELECT 1"}})
    rec.save_completions("mock", "s1", ["SELECT 1"])
    assert json.loads((rec.root / "llm/mock/s1/call_0000.json").read_text())["response"]
    assert rec.load_completions("mock", "s1") == ["SELECT 1"]
    assert rec.llm_call_count("mock", "s1") == 1

    rec.save_sample_json("s1", "candidates.json", [{"id": "c0"}])
    rec.save_similarity_matrix("s1", np.eye(2))
    rec.save_trace("s1", "cond__gold0", {"turns": []})
    rec.save_result("summary.json", {"ok": True})
    assert rec.sample_done("s1")
    assert (rec.root / "samples/s1/similarity_matrix.npy").exists()
    assert (rec.root / "samples/s1/traces/cond__gold0.json").exists()
    assert (rec.root / "results/summary.json").exists()


@pytest.mark.skipif(
    not os.path.exists(os.path.join(DEFAULT_AMBROSIA_ROOT, "data", "ambrosia.csv")),
    reason="AMBROSIA not downloaded",
)
def test_run_experiment_offline_produces_full_tree(tmp_path):
    from pleasqlarify.data.demo import DEMO_COMPLETIONS
    from pleasqlarify.experiment.runner import ExperimentConfig, run_experiment

    cfg = ExperimentConfig(
        model="mock", per_type=1, n=6, max_turns=4,
        real_embedder=False, resume=False, threads=1,
    )
    rec = run_experiment(
        cfg, str(tmp_path / "run"),
        live_client_factory=lambda: MockLLMClient(DEMO_COMPLETIONS),
    )
    root = rec.root
    # config + manifest
    assert (root / "config.json").exists()
    assert (root / "manifest.json").exists()
    # full LLM request/response bodies captured
    calls = list(root.glob("llm/mock/*/call_*.json"))
    assert calls
    body = json.loads(calls[0].read_text())
    assert "request" in body and "response" in body
    # intermediate artifacts per sample
    assert list(root.glob("samples/*/candidates.json"))
    assert list(root.glob("samples/*/similarity_matrix.npy"))
    assert list(root.glob("samples/*/clusters.json"))
    assert list(root.glob("samples/*/gold_assignment.json"))
    # per-condition/gold interaction traces
    assert list(root.glob("samples/*/traces/*.json"))
    # aggregated results
    assert (root / "results/real_eval_results.csv").exists()
    assert (root / "results/aggregate.json").exists()
