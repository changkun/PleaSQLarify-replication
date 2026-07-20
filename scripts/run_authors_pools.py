"""Re-run the evaluation on the authors' own candidate pools (spec 17 §7).

The first like-for-like comparison to Figure 5: their pools, their sample filter,
their configuration. Costs no API calls.

    uv run python scripts/run_authors_pools.py \
        --pools "/path/to/27154505_diverse_sql_output.jsonl" \
        --out experiments/authors_pools --preset authors

Run both presets to see how much of our earlier result was configuration:

    ... --preset authors
    ... --preset ours_original
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from pleasqlarify.authors_config import get_preset
from pleasqlarify.data.authors_pools import load_authors_pools
from pleasqlarify.eval.conditions import five_conditions
from pleasqlarify.eval.metrics import gold_label_entropy
from pleasqlarify.eval.oracle import GoldOracle, assign_gold_intents, assign_gold_intents_exec
from pleasqlarify.llm.client import CachedLLMClient
from pleasqlarify.pipeline.generate import build_prompt
from pleasqlarify.session import build_session


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pools", required=True, help="authors' 27154505_diverse_sql_output.jsonl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--preset", default="authors", choices=("authors", "ours_original"))
    ap.add_argument("--max-turns", type=int, default=10)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--ambrosia-root", default="data/ambrosia")
    ap.add_argument("--cache-dir", default="data/authors_dbs")
    ap.add_argument("--no-filter", action="store_true",
                    help="skip the authors' all-golds-present filter")
    ap.add_argument("--hash-embedder", action="store_true")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cfg = get_preset(args.preset)

    def log(msg: str) -> None:
        print(msg, flush=True)
        with open(out / f"run_{args.preset}.log", "a") as fh:
            fh.write(msg + "\n")

    embedder = None
    if not args.hash_embedder:
        from pleasqlarify.pipeline.embed import MiniLMEmbedder

        embedder = MiniLMEmbedder()

    stats: dict = {}
    samples = list(load_authors_pools(
        args.pools, cache_dir=args.cache_dir, split="test",
        require_all_golds=not args.no_filter,
        ambrosia_root=args.ambrosia_root, stats=stats,
    ))
    if args.limit:
        samples = samples[: args.limit]
    log(f"preset={args.preset} cfg={cfg.as_dict()}")
    log(f"samples={len(samples)} loader_stats={stats}")

    conditions = five_conditions(args.seed, group_mode=cfg.group_mode)
    rows = []
    t0 = time.time()
    for i, s in enumerate(samples, 1):
        prompt = build_prompt(s.utterance, s.schema)
        client = CachedLLMClient({prompt: s.generated_sql})
        kwargs = cfg.session_kwargs()

        base = build_session(s.utterance, s.schema, s.db_path, client,
                             embedder=embedder, n=len(s.generated_sql), **kwargs)
        if not base.candidates:
            continue
        gold_sqls = [g.sql for g in s.gold_queries]
        if cfg.gold_assignment == "execution":
            assign = assign_gold_intents_exec(base.candidates, gold_sqls, s.db_path)
        else:
            assign = assign_gold_intents(base.candidates, gold_sqls, s.db_path, embedder)

        for cond in conditions:
            for gi, gold_sql in enumerate(gold_sqls):
                sess = build_session(
                    s.utterance, s.schema, s.db_path, client, embedder=embedder,
                    n=len(s.generated_sql), mode=cond.mode, clustering=cond.clustering,
                    sim=base.sim, **{k: v for k, v in kwargs.items() if k != "serialization"},
                )
                oracle = GoldOracle(gold_sql, s.schema, sess.vocab)
                ent = []
                for _t in range(args.max_turns + 1):
                    ent.append(gold_label_entropy(sess.surviving_ids, assign))
                    if sess.terminated:
                        break
                    v = cond.select(sess)
                    if v is None:
                        break
                    sess.answer(v.id, oracle.answer(v))
                ent += [ent[-1]] * (args.max_turns + 1 - len(ent))
                rows.append({
                    "condition": cond.name, "ambiguity_type": s.ambiguity_type,
                    "sample_id": s.sample_id, "gold": gi,
                    "initially_ambiguous": ent[0] > 1e-9,
                    "reached_zero": any(e <= 1e-9 for e in ent),
                    "entropy": ent,
                })
        if i % 10 == 0:
            log(f"  {i}/{len(samples)} ({time.time() - t0:.0f}s)")

    _summarize(rows, out, args, cfg, log)


def _summarize(rows, out, args, cfg, log) -> None:
    amb = [r for r in rows if r["initially_ambiguous"]]
    by_cond = defaultdict(list)
    for r in amb:
        by_cond[r["condition"]].append(r)

    summary = {"preset": args.preset, "config": cfg.as_dict(),
               "n_runs": len(rows), "n_ambiguous_runs": len(amb), "conditions": {}}
    log(f"\nruns={len(rows)}  genuinely-ambiguous runs={len(amb)}")
    log(f"{'condition':46s} {'reach0':>8s}  mean entropy by turn (bits)")
    for name, rs in sorted(by_cond.items()):
        reach = sum(r["reached_zero"] for r in rs) / len(rs)
        curve = [float(np.mean([r["entropy"][t] for r in rs]))
                 for t in range(args.max_turns + 1)]
        summary["conditions"][name] = {
            "n": len(rs), "reach_zero_rate": reach, "mean_entropy_by_turn": curve,
        }
        log(f"{name:46s} {reach:8.3f}  " + " ".join(f"{c:.3f}" for c in curve[:6]))

    (out / f"summary_{args.preset}.json").write_text(json.dumps(summary, indent=2))
    with open(out / f"runs_{args.preset}.json", "w") as fh:
        json.dump(rows, fh)
    log(f"\nwrote {out}/summary_{args.preset}.json")


if __name__ == "__main__":
    main()
