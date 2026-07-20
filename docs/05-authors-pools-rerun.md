# Re-run on the Authors' Own Pools

The first like-for-like comparison: **their candidate pools, their sample filter,
their configuration.** Zero API calls.

Reproduce:

```bash
uv run python scripts/run_authors_pools.py \
    --pools /path/to/27154505_diverse_sql_output.jsonl \
    --out experiments/authors_pools --preset authors
uv run python scripts/run_authors_pools.py ... --preset ours_original
```

## Setup

| | |
|---|---|
| Source | authors' `27154505_diverse_sql_output.jsonl` (300 questions, median 95 candidates) |
| Split | `test` → 268 samples load (265 from their `db_dump`, 3 from AMBROSIA fallback) |
| Sample filter | their `run_eval.py:1522` — every gold query must already be in the pool |
| **Samples kept** | **59** (attachment 7/88, scope 9/91, vague 43/89) — their own run used 64 |
| Runs | 59 × 5 conditions × golds = **805**, all genuinely ambiguous by construction |
| Entropy | bits, un-normalized (A15) |
| Gold labels | execution-match (A14) under `authors`; embedding under `ours_original` |

## Result — fraction of runs reaching zero gold-label entropy

| Condition | `authors` preset | `ours_original` |
|---|---|---|
| **Baseline EIG + Atomic Features** | **0.975** | **0.938** |
| Clustering + EIG + Atomic Features | 0.901 | 0.820 |
| Clustering + EIG + Feature Grouping | 0.901 | 0.807 |
| Baseline Random + Atomic Features | 0.534 | 0.422 |
| Baseline Max-Prob-First + Atomic Features | 0.012 | 0.012 |

## Mean gold-label entropy per turn (bits), `authors` preset

| Condition | t0 | t1 | t2 | t3 | t4 | t5 |
|---|---|---|---|---|---|---|
| Baseline EIG + Atomic Features | 1.194 | **0.903** | **0.636** | **0.347** | **0.166** | **0.054** |
| Clustering + EIG + Atomic Features | 1.194 | 0.978 | 0.814 | 0.558 | 0.396 | 0.266 |
| Clustering + EIG + Feature Grouping | 1.194 | 0.978 | 0.815 | 0.565 | 0.394 | 0.258 |
| Baseline Random + Atomic Features | 1.194 | 1.150 | 1.094 | 0.993 | 0.907 | 0.840 |
| Baseline Max-Prob-First + Atomic Features | 1.194 | 1.197 | 1.198 | 1.203 | 1.202 | 1.207 |

## What this does and does not establish

**Alignment mattered, and it helped everything.** Every condition improves under the
authors' configuration (EIG 0.938 → 0.975; clustering 0.820 → 0.901). Our earlier
implementation was genuinely worse, so the six corrections were not cosmetic.

**But the ordering did not flip.** With generation, sample selection, similarity,
`k`, atom granularity, termination, gold labelling and entropy units all matching
the authors, **EIG on atomic features still resolves more runs than either
clustering condition** (0.975 vs 0.901) and dominates at every turn. The paper's
claimed advantage for functional clustering does not appear here.

**Max-Prob-First is catastrophic, not merely worst** (0.012). It almost never
resolves — a much sharper separation than we previously reported, and one that does
support the paper's framing that greedy most-probable-first questioning is a poor
strategy.

## Remaining gaps — why this is not yet a verdict

1. **A8 mining is now aligned — and Feature Grouping is structurally inert here.**
   Their itemset mining is implemented (apriori per length 1..4, lift ≥ 1.3,
   length chosen by `sum((lift-1)*supp_in/(1+0.25*(size-1)))`, `min_len=2`, top-1
   per cluster) and it *works*: on their pools it finds 3–4 groups per sample with
   **lift 21–85**. Yet the Feature Grouping row came out **bit-identical** to the
   Atomic row, and the reason is architectural, not a bug:

   > Our decision variables partition **intents** (A10: one intent per cluster). A
   > group that characterises cluster *c* induces the partition `{c}` — which some
   > **single atom** in *c* already induces — so the partition-dedup drops it. The
   > authors avoid this because their variables split **candidates** by the
   > conjunction mask (`build_group_decision_vars`, `split_mode="mask"` by default):
   > a 3-atom group and a 1-atom group filter the action space differently even when
   > their cluster partitions coincide.

   So *no* amount of better mining can make Feature Grouping differ from Atomic
   under our cluster-partition variables. Reproducing their Feature Grouping
   condition requires candidate-mask decision variables — a change to A10, not A8.
   Pinned by `test_a_mined_group_adds_no_cluster_level_partition_beyond_single_atoms`.
   (A cluster-value majority rule was added for mined groups, **A8e**, a documented
   interpolation since their variables are candidate-level and our belief is
   cluster-level.)
2. ✅ **Their logged curves are now extracted** — see the section below. They
   change the conclusion.
3. **`SIM_IG_UNIFORM` is not implemented.** They ran it in all three modes and did
   not report it; we do not have it.
4. **Sample filter is approximate.** Their filter compares Spider-parsed forms; we
   canonicalize with sqlglot. We keep 59 where they kept 64, so the populations are
   close but not identical.

The correct statement is therefore: **the clustering advantage does not reproduce
under the authors' configuration as far as we have aligned it**, and one of their
two "ours" conditions (Feature Grouping) *cannot* be reproduced at all without
moving decision variables from cluster partitions to candidate masks. Implementation
drift is now largely eliminated, which makes this stronger than any earlier claim —
but the A10 change and the comparison against their logged curves are both
outstanding, so it is not final.


## Their own logged results (from `full_logs_08111341.jsonl`)

Extracted from the 4.6 GB log the paper's Figure 5 was plotted from: mean of the
two branches' `label_entropy` per turn, exactly as their notebook does.

| mode \| strategy | n | reach-0 | t0 | t1 | t2 | t3 | t5 |
|---|---|---|---|---|---|---|---|
| **CLUSTER_GROUP \| EIG** | 117 | **0.855** | 0.427 | 0.356 | 0.297 | 0.250 | 0.153 |
| ATOMIC \| EIG | 131 | 0.740 | 0.439 | 0.475 | 0.344 | 0.281 | 0.207 |
| CLUSTER_CHARACTERISTIC \| EIG | 131 | **0.649** | 0.435 | 0.411 | 0.388 | 0.346 | 0.318 |
| CLUSTER_GROUP \| RANDOM | 120 | 0.792 | 0.443 | 0.395 | 0.350 | 0.308 | 0.224 |
| CLUSTER_GROUP \| SIM_IG_UNIFORM | 120 | **0.883** | 0.428 | 0.373 | 0.305 | 0.213 | 0.099 |
| ATOMIC \| MAX_PROB_FIRST | 134 | 0.194 | 0.409 | 0.422 | 0.381 | 0.362 | 0.402 |

### What this settles

**1. The paper's advantage is real in their data — but it comes from *feature
grouping*, not from functional clustering.** Among their EIG conditions,
`CLUSTER_GROUP` wins (0.855) — yet `CLUSTER_CHARACTERISTIC`, which is clustering
**without** grouping, is the **worst of the three** (0.649), losing to plain
`ATOMIC` (0.740).

**2. Our result agrees with theirs exactly where we can compare it.** We found
Clustering + EIG + Atomic *underperforms* EIG + Atomic (0.901 vs 0.975). Their own
log shows the same ordering (0.649 vs 0.740). Our "clustering hurts" finding is
**not** a replication failure — it reproduces their data.

**3. The one condition we disagree on is the one we cannot compute.** Their win is
`CLUSTER_GROUP`, and our Feature Grouping condition is structurally inert
(gap 1 above): mined groups collapse onto single atoms under cluster-partition
decision variables. So the disagreement is entirely explained by the A10 difference
— candidate-mask vs cluster-partition variables — and is not evidence against the
paper.

**4. The unreported condition is their best.** `SIM_IG_UNIFORM | CLUSTER_GROUP`
reaches 0.883, beating every condition the paper reports. It appears nowhere in the
paper.

### Revised status

The earlier headline — "the clustering advantage does not reproduce" — is
**withdrawn as stated**. The accurate statement is:

> Functional clustering *alone* does not help; their own logs show it hurting
> (0.649 vs 0.740), which we independently reproduce. The paper's gain comes from
> **lift-mined multi-atom feature groups used as candidate-level decision
> variables**. We have implemented the mining but not the candidate-level variable
> (A10), so we cannot yet confirm or refute that specific mechanism.

Reproducing the paper now has one concrete blocker: **A10 — candidate-mask decision
variables**.

> Caveat: absolute values are not comparable across the two tables. Their entropies
> are computed over their own label scheme (`classify_behavior`, with `other` /
> `unclear` classes and the highest encoded label dropped) on 64 examples; ours use
> execution-match labels on the 59 samples our filter keeps. Only the *ordering
> within* each table is being compared.
