# Execution Results

Real-backend runs: **GPT-4o generation + `all-MiniLM-L6-v2` embeddings + UMAP** on
the **real AMBROSIA** benchmark. Reproduce with `scripts/run_real_eval.py`.

> **Headline:** the real backends and the full pipeline run end to end on real
> AMBROSIA. On this small subset the result is **inconclusive**: by the paper's
> per-turn entropy metric the clustering "ours" conditions are **mid-pack** (they
> reduce gold-label entropy, comparable to Random and better than greedy, but
> behind EIG-on-atomic and without reaching zero), so the paper's *clear*
> multi-turn separation is not reproduced at this scale — but neither do the
> baselines decisively win. CIs are wide on 20 runs. Two earlier headlines were
> wrong in opposite directions: a "clean reproduction" (loader-bug artifact) and a
> "baselines win / ours stalls" (over-read of a harsh first-zero-turn statistic).
> This version leads with the entropy curves and a mechanism verified by
> inspecting survivors.

## 1. Real-stack smoke test (demo database)

Full pipeline once with real backends on the paper's running example ("What was
the review of the drama film?"):

- GPT-4o sampled `N=20 @ T=0.7` → **10** unique parseable candidates.
- MiniLM output embeddings → **3 functional clusters**.
- Top decision variable by information gain: `SELECT reviews.audiencereviews`
  (IG ≈ 0.637); UMAP produced real 2-D Action-Space coordinates.

On this cleanly-separable demo the algorithm behaves as intended and the offline
directional test passes. The difficulty below is specific to AMBROSIA's tiny,
near-degenerate database outputs.

## 2. Quantitative evaluation on AMBROSIA

**Setup.** 15 ambiguous test questions (5 each of *scope*, *attachment*, *vague*,
unique questions), GPT-4o `N=50 @ T=0.7` (cached), real MiniLM output similarity,
the five conditions of spec 09, simulated-user oracle, max 10 turns, fixed pool.
**35** (question × gold-interpretation) runs; **20** had genuine initial ambiguity
(entropy > 0 at turn 0).

### Mean gold-label entropy per turn (the 20 genuinely-ambiguous runs)

| Condition | t0 | t1 | t2 | t3 |
|---|---|---|---|---|
| Baseline Random + Atomic | 0.570 | 0.366 | 0.342 | 0.172 |
| Baseline ERG + Atomic (EIG, no clustering) | 0.570 | 0.475 | 0.262 | **0.080** |
| Baseline Max-Prob-First + Atomic | 0.570 | 0.560 | 0.483 | 0.305 |
| Ours: Clustering + EIG + Atomic | 0.570 | 0.521 | 0.228 | 0.144 |
| Ours: Clustering + EIG + Feature Grouping | 0.570 | 0.521 | 0.261 | 0.144 |

**Reading (by the paper's per-turn entropy metric).**
- Every condition reduces gold-label entropy over turns. By t3 the ranking is
  ERG (0.080) < **Ours** (0.144) < Random (0.172) < Max-Prob-First (0.305).
- The clustering "ours" conditions are **mid-pack**: slower at t1 (they spend the
  first turn on a cluster-level split) but they catch up by t2–t3, beating Random
  and clearly beating greedy, while trailing EIG-on-atomic. They do **not** reach
  zero within 10 turns (see mechanism below).
- Paper-consistent signal: greedy **Max-Prob-First is the worst**, supporting
  information-gain-driven selection.
- **Do not** read the "first turn reaching zero" statistic as a ranking: because
  "ours" plateaus just above zero, that metric assigns it a large sentinel and
  makes it look far worse than the entropy curves justify. It is a symptom of the
  mechanism below, not a fair comparison.

### Diagnosed cause (verified by inspecting survivors)

`gold-label entropy` reaches 0 only when survivors are gold-homogeneous. Our
"ours" conditions terminate at a **single functional cluster** (spec 08, **A12**).
We dumped the survivors at termination for nontrivial *Feature Grouping* runs to
check *why* entropy stays positive. Example (`vague_2cols_duration`, "profit per
operation and when it occurred", termination entropy 0.61, 10 survivors):

- The survivors have **6 genuinely distinct output tables** — `TotalMonths`,
  `MonthsSinceStart`, `OperationYears+OperationMonths`, `OperationDurationMonths`,
  … — mapping across gold interpretations 1 and 2.
- These are **not** near-identical coin-flips; they are real, different SQL
  interpretations. Yet functional clustering **merged them into one cluster**,
  because MiniLM rates these structurally-similar small tables (shared
  `OperationID | Profit | …` prefix, identical profit values) at cosine ≥ 0.9.

So the residual entropy is a **real** effect: on AMBROSIA's tiny,
structurally-similar outputs, output-embedding clustering **over-merges** distinct
interpretations, so "ours" terminates at a "functional cluster" that actually
spans multiple gold intents. This is a concrete, verified demonstration that the
flagged clustering-similarity assumptions (**A4** serialization/metric, **A5**
linkage/`k`) and termination (**A12**) are load-bearing — the point of the spec
deck. It is *not* an assignment-noise artifact (the survivor outputs genuinely
differ).

### Clustering-`k` sensitivity (assumption A5)

Forcing `k = #gold interpretations` ("exactly specify the number of clusters",
spec 10) does **not** rescue the result — mean entropy at t1 stays high for "ours"
(≈ 0.21) vs. Random/ERG (≈ 0.0). Data: `docs/results/goldk_sensitivity.json`.
Coarser gold-`k` clusters align even less with gold intents than threshold-`k`.

## 3. Ambiguity-coverage finding (model collapse)

Fraction of runs where GPT-4o's `N=50` pool spanned ≥ 2 gold interpretations:

| Ambiguity type | runs | with genuine ambiguity |
|---|---|---|
| vague | 15 | 12 / 15 |
| attachment | 10 | 6 / 10 |
| scope | 10 | **2 / 10** |

GPT-4o **usually collapses scope ambiguity** (only 2/10 surfaced ≥ 2
interpretations) and often attachment, while reliably surfacing vague column
ambiguity. This supports the paper's motivation (systems sample the most probable
interpretation) and is a robust finding independent of the algorithm comparison.
Data: `docs/results/coverage_by_type.json`.

## 4. Caveats

- **Small scale, wide CIs:** 15 questions, one subset/seed — inconclusive at this
  scale (neither a reproduction nor a refutation). `--per-type` scales it up.
- **Tiny databases** make interpretation outputs embed similarly, which is the
  crux of the clustering difficulty; larger databases would separate outputs more.
- **Metric harshness:** "first reach exactly 0" penalizes methods that terminate
  at functional equivalence; the per-turn entropy curves (`figure5_real.png`,
  `real_eval_results.csv`) are the fuller picture.
- **Oracle-driven** (optimal answers) — measures the algorithm, not humans.

## Correction note

An earlier committed version of this file (and a figure caption sent to the
project owner) claimed the clustering conditions "collapse uncertainty faster —
the paper's directional result." That was produced from results corrupted by a
loader bug: one AMBROSIA database hosts several distinct ambiguous questions, and
`sample_id` (the DB filename) collided across them, so runs overwrote each other.
After fixing `sample_id` to be unique per question (and re-running), the clean
result is the non-reproduction reported above.
