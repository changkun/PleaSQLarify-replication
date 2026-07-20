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
2. **Their logged curves have not been extracted.** Their 4.6 GB
   `full_logs_08111341.jsonl` contains the per-turn entropies behind Figure 5.
   Comparing our curves against *their own recorded numbers* — rather than against
   the figure — is the decisive check and has not been done.
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
