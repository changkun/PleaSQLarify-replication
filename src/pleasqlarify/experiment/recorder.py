"""RunRecorder: partitioned, fully-provenanced experiment artifacts.

Every experiment run gets its own directory under ``experiments/<run_id>/`` so
runs never collide. The recorder captures:

    experiments/<run_id>/
      config.json                 run parameters (model, N, temperature, seed, ...)
      manifest.json               samples processed, counts, status, timing
      run.log                     human-readable progress log
      llm/<model>/<sample_id>/
        call_0000.json            FULL request + response body per LLM call
        ...
        completions.json          aggregated raw completions for the sample
      samples/<sample_id>/
        sample.json               utterance, ambiguity type, db, gold queries
        candidates.json           parsed candidates: sql, gen_count, z atoms, output
        vocabulary.json           the atomic-feature vocabulary
        similarity_matrix.npy     the functional output-similarity matrix S
        clusters.json             functional clusters (threshold-k and gold-k)
        gold_assignment.json      candidate -> nearest gold interpretation
        traces/<condition>__gold<gi>.json   per-turn interaction trace
      results/
        real_eval_results.csv, aggregate.json, coverage_by_type.json, ...

All writes are best-effort-atomic (write to a temp file, then rename).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

try:  # numpy is a core dep, but keep the recorder importable without it
    import numpy as np
except Exception:  # pragma: no cover
    np = None  # type: ignore


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, default=_fallback))
    tmp.replace(path)


def _fallback(o: Any):
    # make numpy/scalars and sets JSON-serializable
    if np is not None and isinstance(o, (np.integer,)):
        return int(o)
    if np is not None and isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    return str(o)


class RunRecorder:
    """Writes all artifacts for a single experiment run into ``run_dir``."""

    def __init__(self, run_dir: str | os.PathLike, config: dict):
        self.root = Path(run_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "llm").mkdir(exist_ok=True)
        (self.root / "samples").mkdir(exist_ok=True)
        (self.root / "results").mkdir(exist_ok=True)
        _write_json(self.root / "config.json", config)
        self._log_path = self.root / "run.log"

    # ---------------------------------------------------------------- logging
    def log(self, message: str) -> None:
        with open(self._log_path, "a") as fh:
            fh.write(message.rstrip() + "\n")

    # ------------------------------------------------------------------- LLM
    def llm_sink(self, model: str, sample_id: str):
        """Return a call-sink that writes each request/response body to disk."""
        d = self.root / "llm" / _safe(model) / _safe(sample_id)
        d.mkdir(parents=True, exist_ok=True)

        def sink(record: dict) -> None:
            idx = record.get("index", 0)
            _write_json(d / f"call_{idx:04d}.json", record)

        return sink

    def save_completions(self, model: str, sample_id: str, completions: list[str]) -> None:
        d = self.root / "llm" / _safe(model) / _safe(sample_id)
        _write_json(d / "completions.json", completions)

    def completions_path(self, model: str, sample_id: str) -> Path:
        return self.root / "llm" / _safe(model) / _safe(sample_id) / "completions.json"

    def load_completions(self, model: str, sample_id: str) -> Optional[list[str]]:
        p = self.completions_path(model, sample_id)
        return json.loads(p.read_text()) if p.exists() else None

    def llm_call_count(self, model: str, sample_id: str) -> int:
        d = self.root / "llm" / _safe(model) / _safe(sample_id)
        return len(list(d.glob("call_*.json"))) if d.exists() else 0

    # --------------------------------------------------------------- samples
    def sample_dir(self, sample_id: str) -> Path:
        d = self.root / "samples" / _safe(sample_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_sample_json(self, sample_id: str, name: str, obj: Any) -> None:
        _write_json(self.sample_dir(sample_id) / name, obj)

    def save_similarity_matrix(self, sample_id: str, matrix) -> None:
        if np is None:  # pragma: no cover
            self.save_sample_json(sample_id, "similarity_matrix.json", matrix.tolist())
            return
        np.save(self.sample_dir(sample_id) / "similarity_matrix.npy", matrix)

    def save_trace(self, sample_id: str, name: str, trace: Any) -> None:
        d = self.sample_dir(sample_id) / "traces"
        d.mkdir(parents=True, exist_ok=True)
        _write_json(d / f"{_safe(name)}.json", trace)

    def sample_done(self, sample_id: str) -> bool:
        """Resume support: a sample is complete once its candidates are written."""
        return (self.root / "samples" / _safe(sample_id) / "candidates.json").exists()

    # --------------------------------------------------------------- results
    def save_result(self, name: str, obj: Any) -> None:
        _write_json(self.root / "results" / name, obj)

    def result_path(self, name: str) -> Path:
        return self.root / "results" / name

    def total_token_usage(self) -> dict:
        """Sum token usage + call count across all captured LLM call bodies."""
        prompt = completion = total = calls = 0
        for f in (self.root / "llm").rglob("call_*.json"):
            try:
                usage = (json.loads(f.read_text()).get("response") or {}).get("usage") or {}
            except Exception:
                continue
            calls += 1
            prompt += usage.get("prompt_tokens", 0) or 0
            completion += usage.get("completion_tokens", 0) or 0
            total += usage.get("total_tokens", 0) or 0
        return {
            "llm_calls": calls,
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
        }

    def write_manifest(self, manifest: dict) -> None:
        _write_json(self.root / "manifest.json", manifest)


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "._-#" else "_" for c in str(name))


__all__ = ["RunRecorder"]
