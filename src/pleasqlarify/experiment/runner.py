"""Scalable, fully-provenanced experiment runner.

Runs the five-condition benchmark over AMBROSIA samples while a
:class:`RunRecorder` captures every LLM request/response body and every
intermediate pipeline result into a per-run directory. Supports resume and
threaded generation for scale.
"""

from __future__ import annotations

import concurrent.futures as cf
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from statistics import median
from typing import Callable, Optional

from ..data.ambrosia import GoldQuery, load_ambrosia
from ..eval.conditions import Condition, five_conditions
from ..eval.metrics import (
    bootstrap_ci,
    gold_label_entropy,
    mean_pairwise_similarity,
)
from ..eval.oracle import GoldOracle, assign_gold_intents
from ..llm.client import CachedLLMClient, LLMClient, OpenAIClient
from ..pipeline.embed import DeterministicEmbedder, Embedder, serialize_result
from ..pipeline.generate import build_prompt
from ..session import build_session
from .recorder import RunRecorder


@dataclass
class ExperimentConfig:
    model: str = "gpt-4o"
    per_type: int = 5              # samples per ambiguity type (None-ish via samples=)
    domain: Optional[str] = None   # restrict to one AMBROSIA domain
    n: int = 50                    # generations per sample
    temperature: float = 0.7
    max_turns: int = 10
    seed: int = 0
    threads: int = 8               # parallel generation calls (OpenAI only)
    gold_k: bool = False           # clustering-k assumption (spec 04 A5)
    threshold: float = 0.1
    real_embedder: bool = False    # MiniLM vs deterministic offline embedder
    resume: bool = True
    sample_ids: Optional[list[str]] = field(default=None)  # explicit selection


def select_samples(config: ExperimentConfig):
    picked = defaultdict(list)
    chosen = []
    for s in load_ambrosia(domain=config.domain):
        if config.sample_ids is not None:
            if s.sample_id in config.sample_ids:
                chosen.append(s)
            if len(chosen) == len(config.sample_ids):
                break
            continue
        if len(picked[s.ambiguity_type]) < config.per_type:
            picked[s.ambiguity_type].append(s)
            chosen.append(s)
        if all(len(picked[t]) >= config.per_type for t in ("scope", "attachment", "vague")):
            break
    return chosen


def _cand_json(cand, vocab) -> dict:
    rt = cand.result
    return {
        "id": cand.id,
        "sql": cand.sql,
        "gen_count": cand.gen_count,
        "cluster_id": cand.cluster_id,
        "z": [
            {"index": i, "kind": vocab.features[i].kind, "payload": vocab.features[i].payload}
            for i in sorted(cand.z)
        ],
        "result": None
        if rt is None
        else {
            "columns": rt.columns,
            "n_rows": rt.n_rows,
            "n_cols": rt.n_cols,
            "error": rt.error,
            "rows": [list(r) for r in rt.rows[:20]],
        },
    }


def _clusters_json(intents) -> list:
    return [
        {"id": c.id, "member_ids": c.member_ids, "representative_id": c.representative_id}
        for c in intents
    ]


def _generate(config, recorder, sample, prompt, live_client_factory) -> list[str]:
    model = config.model
    if config.resume:
        cached = recorder.load_completions(model, sample.sample_id)
        if cached is not None and len(cached) == config.n:
            recorder.log(f"[resume] reuse {len(cached)} completions for {sample.sample_id}")
            return cached
        if cached is not None:
            # resume + changed --n: cache is stale, regenerate to avoid silent reuse
            recorder.log(
                f"[resume] cache size {len(cached)} != n={config.n} for "
                f"{sample.sample_id}; regenerating"
            )
    client = live_client_factory()
    sink = recorder.llm_sink(model, sample.sample_id)
    if isinstance(client, OpenAIClient) and config.threads > 1:
        raw: list = [None] * config.n

        def one(i: int):
            return i, client.generate_one(prompt, config.temperature, i, sink)

        with cf.ThreadPoolExecutor(max_workers=config.threads) as ex:
            for i, content in ex.map(one, range(config.n)):
                raw[i] = content
        raw = list(raw)
    else:
        client.set_sink(sink)
        raw = client.generate(prompt, n=config.n, temperature=config.temperature)
    recorder.save_completions(model, sample.sample_id, raw)
    return raw


def _run_traced(sess, cond: Condition, oracle: GoldOracle, assign, vocab, max_turns):
    turns = []
    rows = []  # (turn, entropy, similarity) forward-filled for metrics
    for t in range(max_turns + 1):
        e = gold_label_entropy(sess.surviving_ids, assign)
        s = mean_pairwise_similarity(sess.surviving_indices(), sess.sim)
        rows.append((t, e, s))
        step = {
            "turn": t,
            "entropy": e,
            "similarity": s,
            "n_surviving": len(sess.surviving_ids),
            "n_clusters": len(sess.intents),
            "belief": {str(k): v for k, v in sess.belief.items()},
            "surviving_ids": list(sess.surviving_ids),
            "ranked_variables": [
                {
                    "id": v.id,
                    "label": v.label,
                    "ig": v.ig,
                    "group_payloads": [vocab.features[i].payload for i in sorted(v.group)],
                }
                for v in sess.ranked[:8]
            ],
        }
        if sess.terminated:
            step["chosen"] = None
            turns.append(step)
            break
        v = cond.select(sess)
        if v is None:
            step["chosen"] = None
            turns.append(step)
            break
        ans = oracle.answer(v)
        step["chosen"] = {
            "id": v.id,
            "label": v.label,
            "ig": v.ig,
            "group_payloads": [vocab.features[i].payload for i in sorted(v.group)],
            "oracle_answer": ans,
        }
        turns.append(step)
        sess.answer(v.id, ans)
    last = rows[-1]
    for t in range(last[0] + 1, max_turns + 1):
        rows.append((t, last[1], last[2]))
    final = sess.final_query()
    trace = {
        "condition": cond.name,
        "turns": turns,
        "final_entropy": turns[-1]["entropy"] if turns else None,
        "final_sql": final.sql if final else None,
    }
    return trace, rows


def run_experiment(
    config: ExperimentConfig,
    run_dir: str,
    live_client_factory: Optional[Callable[[], LLMClient]] = None,
    embedder: Optional[Embedder] = None,
) -> RunRecorder:
    """Run one experiment; write all artifacts under ``run_dir``. Returns the recorder."""
    recorder = RunRecorder(run_dir, asdict(config))
    if embedder is None:
        embedder = _make_embedder(config)
    if live_client_factory is None:
        live_client_factory = lambda: OpenAIClient(model=config.model)  # noqa: E731

    samples = select_samples(config)
    conditions = five_conditions(config.seed)
    recorder.log(f"selected {len(samples)} samples")

    all_rows = []  # (condition, ambiguity_type, sample_id, gold, turn, entropy, similarity)
    coverage = defaultdict(lambda: {"runs": 0, "with_ambiguity": 0})

    for sample in samples:
        sid = sample.sample_id
        recorder.log(f"=== sample {sid} ({sample.ambiguity_type})")
        prompt = build_prompt(sample.utterance, sample.schema)
        completions = _generate(config, recorder, sample, prompt, live_client_factory)
        cache_client = CachedLLMClient({prompt: completions})  # no sink: no re-record

        gold_sqls = [g.sql for g in sample.gold_queries]
        # base session (grouped, threshold-k) for candidate/feature/cluster artifacts
        base = build_session(
            sample.utterance, sample.schema, sample.db_path, cache_client,
            embedder=embedder, mode="grouped", clustering=True, threshold=config.threshold,
        )
        recorder.save_sample_json(sid, "sample.json", {
            "sample_id": sid,
            "ambiguity_type": sample.ambiguity_type,
            "utterance": sample.utterance,
            "db_path": sample.db_path,
            "gold_queries": [{"label": g.intent_label, "sql": g.sql} for g in sample.gold_queries],
            "n_candidates": len(base.candidates),
        })
        recorder.save_sample_json(sid, "candidates.json",
                                  [_cand_json(c, base.vocab) for c in base.candidates])
        recorder.save_sample_json(sid, "vocabulary.json",
                                  [{"index": f.index, "kind": f.kind, "payload": f.payload}
                                   for f in base.vocab.features])
        recorder.save_similarity_matrix(sid, base.sim)
        recorder.save_sample_json(sid, "clusters.json", {
            "threshold_k": _clusters_json(base.intents),
        })
        assign = assign_gold_intents(base.candidates, gold_sqls, sample.db_path, embedder)
        recorder.save_sample_json(sid, "gold_assignment.json", assign)

        # per condition x gold: traced run
        k = len(gold_sqls) if config.gold_k else None
        for cond in conditions:
            for gi, gold_sql in enumerate(gold_sqls):
                sess = build_session(
                    sample.utterance, sample.schema, sample.db_path, cache_client,
                    embedder=embedder, mode=cond.mode, clustering=cond.clustering,
                    k=k if cond.clustering else None, threshold=config.threshold,
                )
                oracle = GoldOracle(gold_sql, sample.schema, sess.vocab)
                trace, rows = _run_traced(sess, cond, oracle, assign, sess.vocab, config.max_turns)
                recorder.save_trace(sid, f"{cond.name}__gold{gi}", trace)
                for (t, e, s) in rows:
                    all_rows.append((cond.name, sample.ambiguity_type, sid, gi, t, e, s))

        # coverage: initial ambiguity per (sample,gold) — condition-independent at t0
        for gi in range(len(gold_sqls)):
            coverage[sample.ambiguity_type]["runs"] += 1
        e0 = gold_label_entropy(base.surviving_ids, assign)
        if e0 > 1e-9:
            for gi in range(len(gold_sqls)):
                coverage[sample.ambiguity_type]["with_ambiguity"] += 1

    _write_results(recorder, all_rows, conditions, config, dict(coverage))
    recorder.write_manifest({
        "n_samples": len(samples),
        "sample_ids": [s.sample_id for s in samples],
        "n_runs": len({(r[2], r[3]) for r in all_rows}),
        "token_usage": recorder.total_token_usage(),
        "config": asdict(config),
    })
    recorder.log("done")
    return recorder


def _write_results(recorder, all_rows, conditions, config, coverage):
    import csv

    with open(recorder.result_path("real_eval_results.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["condition", "ambiguity_type", "sample_id", "gold", "turn", "entropy", "similarity"])
        for r in all_rows:
            w.writerow([r[0], r[1], r[2], r[3], r[4], f"{r[5]:.6f}", f"{r[6]:.6f}"])

    # aggregate median + bootstrap CI per (condition, type, turn)
    groups = defaultdict(lambda: {"entropy": [], "similarity": []})
    for r in all_rows:
        key = f"{r[0]}|{r[1]}|{r[4]}"
        groups[key]["entropy"].append(r[5])
        groups[key]["similarity"].append(r[6])
    agg = {
        k: {"entropy": bootstrap_ci(v["entropy"]), "similarity": bootstrap_ci(v["similarity"]),
            "n": len(v["entropy"])}
        for k, v in groups.items()
    }
    recorder.save_result("aggregate.json", agg)
    recorder.save_result("coverage_by_type.json", coverage)

    # convergence + per-turn entropy summary
    def med_ent(cond, turn):
        vals = [r[5] for r in all_rows if r[0] == cond and r[4] == turn]
        return median(vals) if vals else None

    summary = {c.name: {"median_entropy_by_turn": {t: med_ent(c.name, t)
                                                   for t in range(config.max_turns + 1)}}
               for c in conditions}
    recorder.save_result("summary.json", summary)

    try:
        from ..eval.plot_figure5 import plot_figure5
        from ..eval.run_benchmark import RunRow

        rows = [RunRow(*r) for r in all_rows]
        plot_figure5(rows, str(recorder.result_path("figure5.png")))
    except Exception as exc:  # pragma: no cover
        recorder.log(f"[plot skipped] {exc}")


def _make_embedder(config: ExperimentConfig) -> Embedder:
    if config.real_embedder:
        from ..pipeline.embed import MiniLMEmbedder

        return MiniLMEmbedder()
    return DeterministicEmbedder()


__all__ = ["ExperimentConfig", "run_experiment", "select_samples"]
