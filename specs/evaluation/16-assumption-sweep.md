# Spec 16 — Assumption Sweep (pre-registration)

**Status:** pre-registered before any sweep result was computed. Committed ahead
of the run so the win criterion and the interpretation rules cannot drift to fit
whatever the grid shows.

**Depends on:** specs 04 (clustering), 08 (repair loop), 09/10 (conditions, eval),
and the 150-sample run `experiments/gpt4o_per50_n50/`.

## 1. The question

At 150-sample scale the paper's clustering advantage did not reproduce
(`docs/02-execution-results.md`). Two explanations remain open:

- **(a)** the result is genuinely absent on AMBROSIA — functional clustering does
  not help on these tiny, structurally-similar databases;
- **(b)** our gap-fills are wrong — the paper is silent on output serialization
  (**A4**), linkage/threshold (**A5**) and termination granularity (**A12**), and
  the verified over-merge mechanism shows those decisions are load-bearing.

This sweep exists to separate (a) from (b). It is **not** a search for the best
number.

## 2. The fixed yardstick (blocking design constraint)

`gold_label_entropy` is scored against the gold-intent assignment. The default
assignment (**A14**) embeds outputs with *the same embedder/serialization this
sweep varies*, so "reached zero entropy" would be **redefined in every cell** and
cells would not be comparable.

Therefore every cell is scored against `assign_gold_intents_exec` (**A14b**):
labels derived only from executed SQLite output (exact row-multiset match, then
row Jaccard, else unassigned). MiniLM is thereby confined to the *clustering under
test* and removed from the *scoring* entirely.

This changes absolute numbers relative to the committed 150-sample run. Both are
reported; only the fixed-yardstick numbers are compared across cells.

## 3. Grid

Every cell is tagged, because the tag decides what a win is allowed to claim.

| Axis | Values | Tag |
|---|---|---|
| **A4** serialization | `header_rows` (current), `values_only`, `columns_only`, `cells_sorted` | within-spec |
| **A4′** similarity backend | `rowset_jaccard` (row-multiset overlap, no embedding) | **beyond-spec** |
| **A5** threshold | 0.02, 0.05, 0.10 (current), 0.20, 0.40 | within-spec |
| **A5** linkage | `average` (current), `complete`, `single` | within-spec |
| **A12** termination | `cluster_or_uninformative` (current), `uninformative_only` | within-spec |

- **within-spec** = a decision the paper leaves unstated. A win here licenses
  *"we replicated the result, and here is the undocumented decision it depends
  on."*
- **beyond-spec** = a decision the paper states. `rowset_jaccard` replaces
  embedding-cosine clustering, which the paper specifies (`all-MiniLM-L6-v2`). A
  win here licenses only *"the paper's embedding clustering fails on AMBROSIA; a
  set-overlap method works"* — **not** a reproduction.

Baselines (`clustering=False`) are invariant to every axis under the fixed
yardstick, so they are computed once and reused as the reference.

## 4. Split

Samples are split **50/50 by sample, stratified by ambiguity type**, deterministic
(sorted `sample_id`, seed 0):

- **dev** — the whole grid runs here; the winning cell is selected here.
- **held-out** — touched *once*, with the dev-selected cell only.

## 5. Pre-registered win criterion

Primary metric: **reach-zero rate** — the fraction of genuinely-ambiguous runs
(fixed-yardstick entropy > 0 at turn 0) that reach zero gold-label entropy within
10 turns.

Let `Δ = reach_zero(Ours: Clustering + EIG + Feature Grouping) − reach_zero(Baseline ERG + Atomic)`.

- **Replication is declared** iff a *within-spec* cell has `Δ_dev > 0` **and** that
  same cell has `Δ_heldout ≥ 0` on the untouched half.
- **Non-replication (a) stands** if no within-spec cell has `Δ_dev > 0`, or the
  dev winner fails to hold up (`Δ_heldout < 0`).
- Secondary (reported, not decisive): mean gold-label entropy per turn.

## 6. Interpretation guards (fixed in advance)

1. **Degeneracy guard.** The verified over-merge mechanism predicts that lowering
   the threshold merges less and converges better — but at threshold → 0 every
   candidate is its own cluster, which *is* the atomic baseline. So each cell also
   records `merge_ratio = mean(#clusters / #survivors)` at turn 0. **If the winning
   cell has `merge_ratio ≥ 0.9`, the finding reads as "clustering only helps when it
   barely clusters" — i.e. (a) holds — and is NOT reported as a recovery**, whatever
   `Δ` says.
2. **No post-hoc interior cell.** If `Δ` is monotone in the threshold toward the
   baseline, that is the degeneracy pattern of guard 1, not a discovered optimum.
   The best interior cell is not to be cherry-picked out of a monotone curve.
3. **Multiplicity.** ~120 dev cells are searched, so a positive `Δ_dev` alone is
   expected by chance. The held-out confirmation is what carries the claim; the
   held-out half is looked at exactly once.
4. **Tag discipline.** A `rowset_jaccard` win is reported under its own heading and
   never described as reproducing the paper.

## 7. Outputs

`experiments/<run_id>/results/`: `sweep_grid.csv` (one row per cell × condition
with `Δ`, reach-zero, mean entropy per turn, `merge_ratio`, tag, split),
`sweep_winner.json` (dev winner + held-out confirmation), `sweep_summary.md`.
