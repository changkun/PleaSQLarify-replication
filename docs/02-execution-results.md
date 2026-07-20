# Execution Results

> ⚠️ **Numbers below are superseded.** They were produced before the authors'
> supplementary code was available, under assumptions now known to differ from
> theirs in six load-bearing ways (two of them our bugs), and without their
> sample-selection filter. Entropies are also in **nats** here; the authors use
> **bits**. Kept for provenance; see
> [`specs/evaluation/17-authors-supplement.md`](../specs/evaluation/17-authors-supplement.md).


Real-backend runs: **GPT-4o generation + `all-MiniLM-L6-v2` embeddings + UMAP** on
the **real AMBROSIA** benchmark. The primary result below is a **150-sample run**
(`experiments/gpt4o_per50_n50/`, 7,500 GPT-4o calls, 1.6M tokens); reproduce with
`scripts/run_experiment.py` (see `04-experiments.md`).

> **Headline (150 samples, 114 genuinely-ambiguous runs).** The paper's clustering
> advantage **does not reproduce** on AMBROSIA. By the per-turn entropy metric the
> clustering "ours" conditions are **consistently slightly behind** the
> atomic-feature baselines at every turn, and reach zero gold-label entropy in
> **71%** of ambiguous runs vs **86–89%** for the baselines. The strongest
> condition is **EIG on atomic features without clustering** (the "ERG" baseline).
> The gaps are modest but consistent across 114 runs (much better powered than the
> earlier 20-run subset). The cause is a **verified over-merging mechanism**: on
> AMBROSIA's tiny, structurally-similar tables MiniLM merges genuinely-distinct
> outputs, so functional clustering terminates on a cluster spanning gold intents.
> (Two earlier headlines were wrong — a loader-bug "clean reproduction" and an
> over-read "baselines win / ours stalls"; and "greedy is worst" does not survive
> at scale.)

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

**Setup.** 150 ambiguous test questions (50 each of *scope*, *attachment*,
*vague*), GPT-4o `N=50 @ T=0.7` (7,500 calls, 1.6M tokens, full bodies captured),
real MiniLM output similarity, the five conditions of spec 09, simulated-user
oracle, max 10 turns, fixed pool. **350** (question × gold-interpretation) runs;
**114** had genuine initial ambiguity (entropy > 0 at turn 0).

### Mean gold-label entropy per turn (the 114 genuinely-ambiguous runs)

| Condition | t0 | t1 | t2 | t3 | t5 |
|---|---|---|---|---|---|
| Baseline ERG + Atomic (EIG, no clustering) | 0.499 | 0.381 | 0.263 | **0.124** | **0.097** |
| Baseline Random + Atomic | 0.499 | 0.373 | 0.217 | 0.169 | 0.115 |
| Baseline Max-Prob-First + Atomic | 0.499 | 0.368 | 0.303 | 0.199 | 0.143 |
| Ours: Clustering + EIG + Atomic | 0.499 | 0.404 | 0.246 | 0.204 | 0.143 |
| Ours: Clustering + EIG + Feature Grouping | 0.499 | 0.404 | 0.243 | 0.192 | 0.143 |

### Fraction of ambiguous runs reaching zero entropy within 10 turns

| Condition | reached 0 |
|---|---|
| Baseline ERG + Atomic | **101/114 = 0.89** |
| Baseline Max-Prob-First + Atomic | 100/114 = 0.88 |
| Baseline Random + Atomic | 98/114 = 0.86 |
| Ours: Clustering + EIG + Atomic | 81/114 = 0.71 |
| Ours: Clustering + EIG + Feature Grouping | 81/114 = 0.71 |

**Reading.**
- The clustering "ours" conditions sit **at or slightly above** the atomic
  baselines at every turn (higher = more residual uncertainty), and resolve fully
  in **71%** of ambiguous runs vs **86–89%** for the atomic baselines. So the
  paper's clustering advantage **does not reproduce** on AMBROSIA — clustering
  modestly *hurts* here.
- **EIG on atomic features without clustering (ERG) is the strongest** — pure
  information gain helps; adding functional clustering is what costs accuracy.
- At scale, greedy Max-Prob-First is **not** clearly the worst (it was on the tiny
  subset); the only stable ordering is ERG best, clustering conditions behind.
- Gaps are modest (≈0.02–0.08 nats per turn; ≈15pp on the reach-zero rate) but
  **consistent across 114 runs**, so more trustworthy than the earlier 20-run read.

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
spec 10) does **not** rescue the result — coarser gold-`k` clusters align even
less with gold intents than threshold-`k`. (Measured on the earlier 15-sample run;
`docs/results/goldk_sensitivity.json`.)

## 3. Ambiguity-coverage finding (model collapse)

Fraction of the 150-sample runs where GPT-4o's `N=50` pool spanned ≥ 2 gold
interpretations:

| Ambiguity type | runs | with genuine ambiguity |
|---|---|---|
| vague | 150 | 60 / 150 = 40% |
| attachment | 100 | 32 / 100 = 32% |
| scope | 100 | **22 / 100 = 22%** |

GPT-4o most often collapses to a single reading: even at `N=50` only **33%** of
ambiguous questions surfaced ≥ 2 interpretations overall, and **scope** is the
hardest to surface (22%), *vague* the easiest (40%). This supports the paper's
motivation (systems sample the most probable interpretation) and is a robust,
well-powered finding independent of the algorithm comparison. Data:
`experiments/gpt4o_per50_n50/results/coverage_by_type.json`.

## 4. Caveats

- **One seed/subset** (first 50 per type). Gaps are modest though consistent
  across 114 runs; a multi-seed run would tighten them.
- **Tiny databases** make interpretation outputs embed similarly, which is the
  crux of the clustering difficulty; larger databases would separate outputs more.
- **Oracle-driven** (optimal answers) — measures the algorithm, not humans.
- The per-turn entropy curves (`experiments/gpt4o_per50_n50/results/figure5.png`)
  are the fuller picture behind the summary tables.

## Correction note

An earlier committed version of this file (and a figure caption sent to the
project owner) claimed the clustering conditions "collapse uncertainty faster —
the paper's directional result." That was produced from results corrupted by a
loader bug: one AMBROSIA database hosts several distinct ambiguous questions, and
`sample_id` (the DB filename) collided across them, so runs overwrote each other.
After fixing `sample_id` to be unique per question (and re-running), the clean
result is the non-reproduction reported above.
