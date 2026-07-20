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

1. **A8 (feature grouping) is still ours, not theirs.** Their `CLUSTER_GROUP`
   condition mines itemsets with mlxtend apriori (`min_support=0.10`,
   `min_lift=1.3`, `top_k=12`, `gamma_size_penalty=0.25`, `top_per_cluster=1`,
   `min_len=2`); we use cluster common-atom signatures. This is *the* mechanism the
   clustering conditions depend on, so it is the most likely remaining explanation
   for the gap and the next thing to align.
2. **Their logged curves have not been extracted.** Their 4.6 GB
   `full_logs_08111341.jsonl` contains the per-turn entropies behind Figure 5.
   Comparing our curves against *their own recorded numbers* — rather than against
   the figure — is the decisive check and has not been done.
3. **`SIM_IG_UNIFORM` is not implemented.** They ran it in all three modes and did
   not report it; we do not have it.
4. **Sample filter is approximate.** Their filter compares Spider-parsed forms; we
   canonicalize with sqlglot. We keep 59 where they kept 64, so the populations are
   close but not identical.

Given (1) especially, the correct statement is: **the clustering advantage does not
reproduce under the authors' configuration as far as we have aligned it**, with the
feature-grouping mechanism still outstanding. That is a stronger claim than before
— implementation drift is now largely eliminated — but it is not final.
