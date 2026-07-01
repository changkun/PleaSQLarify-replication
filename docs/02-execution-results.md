# Execution Results

Real-backend runs: **GPT-4o generation + `all-MiniLM-L6-v2` embeddings + UMAP** on
the **real AMBROSIA** benchmark. Reproduce with `scripts/run_real_eval.py`.

> **Headline:** the real backends and the full pipeline run end to end on real
> AMBROSIA. On this **small subset the paper's headline directional advantage for
> clustering-based repair does *not* cleanly reproduce** — the results are noisy
> and, under our default assumptions, the atomic baselines often reach zero
> gold-label entropy sooner than the clustering "ours" conditions. This section
> reports the honest numbers and the diagnosed cause. (An earlier version of this
> doc claimed a clean reproduction; that was an artifact of a loader bug — see
> the note at the end.)

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

### Mean "first turn reaching zero entropy" (10 = never, within 10 turns)

| Condition | mean first-zero turn |
|---|---|
| Baseline Random + Atomic | **2.75** |
| Baseline ERG + Atomic | **3.05** |
| Ours: Clustering + EIG + Atomic | ~17 (frequently never) |
| Ours: Clustering + EIG + Feature Grouping | ~17 (frequently never) |
| Baseline Max-Prob-First + Atomic | ~18 (frequently never) |

**Reading (honest).**
- The clustering "ours" conditions **reduce** gold-label entropy but frequently
  **plateau above zero** and do not converge within 10 turns.
- The atomic baselines *Random* and *ERG* reach zero sooner because, with
  clustering off, each candidate query is its own intent, so the loop keeps
  splitting until a single query — hence a single gold label — remains.
- The one paper-consistent signal: greedy **Max-Prob-First is the worst**
  baseline, supporting information-gain-driven selection over a greedy heuristic.
- Confidence intervals are wide on 20 runs; treat all gaps as noisy. This is a
  **non-reproduction at this scale**, not a refutation of the paper.

### Diagnosed cause

`gold-label entropy` reaches 0 only when the surviving candidates are
gold-homogeneous. Our "ours" conditions terminate at a **single functional
cluster** (spec 08, assumption **A12**), and on AMBROSIA's tiny databases
(< 10 rows) different interpretations often produce **near-identical MiniLM output
embeddings**, so a functional cluster is **not gold-pure** — the loop stops with
residual gold-label uncertainty it cannot remove. Three flagged assumptions drive
this: **A12** (terminate at cluster vs. single query), **A5** (clustering
linkage/`k`), and **A14** (gold-intent assignment). This is exactly the
assumption-sensitivity the spec deck exists to surface.

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

- **Small scale, wide CIs:** 15 questions, one subset/seed — directional at best,
  and here inconclusive-to-negative. `--per-type` scales it up.
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
