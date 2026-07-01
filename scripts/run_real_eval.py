"""Real-data validation: GPT-4o generation + MiniLM embeddings on AMBROSIA.

Generates the candidate pool once per sample with the real LLM (cached to disk,
threaded), then runs the five-condition benchmark (spec 09/10) with real MiniLM
output embeddings and renders Figure 5. Usage:

    OPENAI_BASE_URL=... OPENAI_API_KEY=... uv run python scripts/run_real_eval.py \
        --per-type 4 --n 30 --max-turns 10
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path

from pleasqlarify.data.ambrosia import load_ambrosia
from pleasqlarify.eval.conditions import five_conditions
from pleasqlarify.eval.run_benchmark import (
    EvalSample,
    aggregate,
    mean_convergence_turn,
    run_benchmark,
)
from pleasqlarify.llm.client import CachedLLMClient, OpenAIClient
from pleasqlarify.pipeline.embed import MiniLMEmbedder
from pleasqlarify.pipeline.generate import build_prompt

OUT = Path("docs/results")
CACHE = Path("data/generations")


def select_samples(per_type: int):
    picked = defaultdict(list)
    for s in load_ambrosia():  # whole test set, all domains
        if len(picked[s.ambiguity_type]) < per_type:
            picked[s.ambiguity_type].append(s)
        if all(len(picked[t]) >= per_type for t in ("scope", "attachment", "vague")):
            break
    return [s for v in picked.values() for s in v]


def generate_cache(sample, client, n, temperature, threads=8):
    """Sample the LLM n times (threaded) and cache raw completions on disk."""
    prompt = build_prompt(sample.utterance, sample.schema)
    key = hashlib.blake2b(f"{sample.sample_id}|{n}|{prompt}".encode(), digest_size=12).hexdigest()
    path = CACHE / f"{key}.json"
    if path.exists():
        raw = json.loads(path.read_text())
    else:
        def one(_):
            return client.generate(prompt, n=1, temperature=temperature)[0]

        with cf.ThreadPoolExecutor(max_workers=threads) as ex:
            raw = list(ex.map(one, range(n)))
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw))
    return {prompt: raw}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-type", type=int, default=4)
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--max-turns", type=int, default=10)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    print("loading MiniLM embedder...")
    embedder = MiniLMEmbedder()
    llm = OpenAIClient(model="gpt-4o")

    samples = select_samples(args.per_type)
    print(f"selected {len(samples)} samples "
          f"({', '.join(sorted({s.ambiguity_type for s in samples}))})")

    eval_samples = []
    for s in samples:
        print(f"  generating N={args.n} for {s.sample_id} ({s.ambiguity_type})...")
        cache = generate_cache(s, llm, args.n, 0.7)
        eval_samples.append(
            EvalSample(
                sample_id=s.sample_id,
                ambiguity_type=s.ambiguity_type,
                utterance=s.utterance,
                schema=s.schema,
                db_path=s.db_path,
                gold_sqls=[g.sql for g in s.gold_queries],
                client=CachedLLMClient(cache),
            )
        )

    print("running benchmark with real MiniLM embeddings...")
    rows = run_benchmark(eval_samples, embedder=embedder, max_turns=args.max_turns)

    # tidy results
    with open(OUT / "real_eval_results.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["condition", "ambiguity_type", "sample_id", "gold", "turn", "entropy", "similarity"])
        for r in rows:
            w.writerow([r.condition, r.ambiguity_type, r.sample_id, r.gold, r.turn,
                        f"{r.entropy:.6f}", f"{r.similarity:.6f}"])

    # ---- summary: per-turn median entropy + convergence + ambiguity coverage ----
    import statistics as st

    def median_entropy_at(condition, turn):
        vals = [r.entropy for r in rows if r.condition == condition and r.turn == turn]
        return st.median(vals) if vals else float("nan")

    # how many (sample,gold) runs had genuine initial ambiguity (entropy>0 at t0)
    initial = {(r.sample_id, r.gold): r.entropy for r in rows if r.turn == 0}
    nontrivial = sum(1 for v in initial.values() if v > 1e-9)

    summary = {
        "n_runs": len({(r.sample_id, r.gold) for r in rows}),
        "nontrivial_initial_ambiguity": nontrivial,
        "per_condition": {},
    }
    turns_report = [0, 1, 2, 3, 5, args.max_turns]
    print(f"\nruns with genuine initial ambiguity (entropy>0 at t0): "
          f"{nontrivial}/{summary['n_runs']}")
    print(f"\n{'condition':45s} " + " ".join(f"t{t:<5}" for t in turns_report) + "  conv")
    for c in five_conditions():
        ent = {t: median_entropy_at(c.name, t) for t in turns_report}
        conv = mean_convergence_turn(rows, c.name)
        summary["per_condition"][c.name] = {
            "median_entropy_by_turn": ent,
            "median_convergence_turn": conv,
        }
        print(f"  {c.name:43s} "
              + " ".join(f"{ent[t]:<6.3f}" for t in turns_report)
              + f"  {conv}")
    (OUT / "convergence_summary.json").write_text(json.dumps(summary, indent=2))

    try:
        from pleasqlarify.eval.plot_figure5 import plot_figure5
        plot_figure5(rows, str(OUT / "figure5_real.png"))
        print("wrote", OUT / "figure5_real.png")
    except Exception as exc:  # pragma: no cover
        print("plot skipped:", exc)


if __name__ == "__main__":
    main()
