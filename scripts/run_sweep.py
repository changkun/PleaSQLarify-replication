"""Run the pre-registered A4/A5/A12 assumption sweep (spec 16).

Replays the generations of a completed experiment run, so this costs **zero LLM
calls** -- only CPU. Every cell is scored with the fixed exec-match yardstick, the
grid is searched on the dev half only, and the held-out half is touched exactly
once with the dev-selected winner.

    uv run python scripts/run_sweep.py \
        --source experiments/gpt4o_per50_n50 \
        --out experiments/sweep_a4a5a12

    # sizing probe: a few samples, a few cells, no held-out confirmation
    uv run python scripts/run_sweep.py --source ... --out ... --limit-samples 4 --probe
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

from pleasqlarify.eval.conditions import five_conditions
from pleasqlarify.experiment.runner import ExperimentConfig, select_samples
from pleasqlarify.experiment.sweep import (
    BEYOND_SPEC_STYLES,
    OURS,
    REFERENCE,
    WITHIN_SPEC_STYLES,
    Cell,
    build_grid,
    evaluate_baselines,
    evaluate_cell,
    prepare_sample,
    stratified_split,
)


def _load_samples(source: Path, model: str):
    """The exact samples of the source run, with their cached completions."""
    manifest = json.loads((source / "manifest.json").read_text())
    ids = manifest["sample_ids"]
    config = ExperimentConfig(sample_ids=ids, per_type=10**9)
    samples = {s.sample_id: s for s in select_samples(config)}
    out = []
    for sid in ids:
        p = source / "llm" / model / sid / "completions.json"
        if not p.exists():
            p = source / "llm" / model.replace("/", "_") / sid / "completions.json"
        if sid in samples and p.exists():
            out.append((samples[sid], json.loads(p.read_text())))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="completed run dir to replay")
    ap.add_argument("--out", required=True, help="sweep output dir")
    ap.add_argument("--model", default="gpt-4o")
    ap.add_argument("--max-turns", type=int, default=10)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--limit-samples", type=int, default=None)
    ap.add_argument("--limit-cells", type=int, default=None)
    ap.add_argument("--probe", action="store_true", help="sizing probe: skip held-out")
    ap.add_argument("--hash-embedder", action="store_true", help="offline embedder")
    args = ap.parse_args()

    source, out = Path(args.source), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    log_path = out / "sweep.log"

    def log(msg: str) -> None:
        print(msg, flush=True)
        with open(log_path, "a") as fh:
            fh.write(msg + "\n")

    embedder = None
    if not args.hash_embedder:
        from pleasqlarify.pipeline.embed import MiniLMEmbedder

        embedder = MiniLMEmbedder()

    pairs = _load_samples(source, args.model)
    if args.limit_samples:
        pairs = pairs[: args.limit_samples]
    log(f"replaying {len(pairs)} samples from {source} (0 new LLM calls)")

    styles = list(WITHIN_SPEC_STYLES) + list(BEYOND_SPEC_STYLES)
    t0 = time.time()
    prepared = []
    for i, (sample, completions) in enumerate(pairs, 1):
        p = prepare_sample(sample, completions, styles, embedder)
        if p is not None:
            prepared.append(p)
        if i % 10 == 0:
            log(f"  prepared {i}/{len(pairs)} ({time.time() - t0:.0f}s)")
    log(f"prepared {len(prepared)} samples in {time.time() - t0:.0f}s")

    dev, held = stratified_split(prepared, seed=args.seed)
    log(f"split: dev={len(dev)} held-out={len(held)} (held-out is read once, at the end)")

    conditions = five_conditions(args.seed)
    ours_conds = [c for c in conditions if c.clustering]
    base_conds = [c for c in conditions if not c.clustering]

    rows: list[dict] = []
    base_dev = evaluate_baselines(dev, base_conds, "dev", args.max_turns, "header_rows")
    rows += [r.as_row() for r in base_dev]
    reference = next(r for r in base_dev if r.condition == REFERENCE)
    log(f"reference {REFERENCE}: reach-zero {reference.reach_zero_rate:.3f} "
        f"on {reference.n_ambiguous} ambiguous dev runs")

    grid = build_grid(include_beyond_spec=True)
    if args.limit_cells:
        grid = grid[: args.limit_cells]
    log(f"sweeping {len(grid)} cells x {len(ours_conds)} conditions on dev")

    t0 = time.time()
    for i, cell in enumerate(grid, 1):
        for r in evaluate_cell(dev, cell, ours_conds, "dev", args.max_turns):
            rows.append(r.as_row())
        if i % 10 == 0 or i == len(grid):
            log(f"  cell {i}/{len(grid)} ({time.time() - t0:.0f}s)")

    _write_csv(out / "sweep_grid.csv", rows)

    # ---- dev winner, per the pre-registered criterion (spec 16 s5)
    dev_ours = [r for r in rows if r["condition"] == OURS and r["split"] == "dev"]
    for r in dev_ours:
        r["delta"] = r["reach_zero_rate"] - reference.reach_zero_rate
    within = [r for r in dev_ours if r["tag"] == "within_spec"]
    beyond = [r for r in dev_ours if r["tag"] == "beyond_spec"]

    def best(rs):
        return max(rs, key=lambda r: (r["delta"], -r["merge_ratio"])) if rs else None

    winner, beyond_best = best(within), best(beyond)
    summary = {
        "reference_condition": REFERENCE,
        "reference_reach_zero_dev": reference.reach_zero_rate,
        "n_cells": len(grid),
        "dev_winner_within_spec": winner,
        "dev_best_beyond_spec": beyond_best,
    }

    if winner and not args.probe:
        cell = _cell_from_id(winner["cell_id"])
        log(f"dev winner (within-spec): {winner['cell_id']} delta={winner['delta']:+.3f} "
            f"merge_ratio={winner['merge_ratio']:.3f}")
        log("confirming on the held-out half (first and only look) ...")
        held_rows = [r.as_row() for r in evaluate_cell(held, cell, ours_conds, "heldout",
                                                       args.max_turns)]
        held_base = evaluate_baselines(held, base_conds, "heldout", args.max_turns,
                                       "header_rows")
        rows += held_rows + [r.as_row() for r in held_base]
        held_ref = next(r for r in held_base if r.condition == REFERENCE)
        held_ours = next(r for r in held_rows if r["condition"] == OURS)
        delta_held = held_ours["reach_zero_rate"] - held_ref.reach_zero_rate
        degenerate = held_ours["merge_ratio"] >= 0.9
        summary.update({
            "heldout_reference_reach_zero": held_ref.reach_zero_rate,
            "heldout_ours_reach_zero": held_ours["reach_zero_rate"],
            "heldout_delta": delta_held,
            "heldout_merge_ratio": held_ours["merge_ratio"],
            "degeneracy_guard_tripped": degenerate,
            "replication_declared": bool(
                winner["delta"] > 0 and delta_held >= 0 and not degenerate
            ),
        })
        _write_csv(out / "sweep_grid.csv", rows)

    (out / "sweep_winner.json").write_text(json.dumps(summary, indent=2, default=str))
    log(json.dumps(summary, indent=2, default=str))
    log(f"artifacts in {out}")


def _cell_from_id(cell_id: str) -> Cell:
    style, thr, linkage, termination = cell_id.split("|")
    return Cell(style, float(thr[1:]), linkage, termination)


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    fields = list({k: None for r in rows for k in r})
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


if __name__ == "__main__":
    main()
