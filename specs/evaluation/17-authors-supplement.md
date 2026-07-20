# Spec 17 — The Authors' Supplementary Code as Ground Truth

**Status:** authoritative for every decision it settles. Supersedes our gap-fills
where they conflict.

The authors' supplementary material (`code/run_eval.py`, `code/helpers.py`,
`code/plot_runs.ipynb`, `code/spider/`, plus a 4.6 GB result log and their
precomputed generation pools) became available after specs 01–16 were written.
This spec records what it settles, what it does **not**, and how our
implementation now maps onto it.

> **Provenance.** Read from a local copy of the authors' supplement. Not
> redistributed in this repo. Line references are to their files as shipped.

## 1. Precedence

The ground-truth order is now:

1. **The paper** — still first for anything it states explicitly.
2. **The authors' supplementary code** — for decisions the paper leaves unstated.
   This is what the reported numbers were actually produced by.
3. **Our documented gap-fills** — only where neither of the above speaks.

The empty upstream GitHub repo (`github.com/chanr0/pleasqlarify`, a Copilot stub)
remains **not** ground truth; it contradicts both the paper and this supplement.

## 2. Decisions settled (and where we were wrong)

| # | Their implementation | What we had | Now |
|---|---|---|---|
| **A3/A4** | Embed each result **row**; pad shorter table with `<NULL>`; Hungarian-align on `1−cos`; mean of matched diagonal. Empty-vs-empty = 1 | one serialized table → cosine | `style="row_aligned"` in `pipeline/embed.py` |
| **A5** | Average linkage; **k = max(2, min(4, round(n/10) or 2))** on the *surviving* pool, recomputed every turn | distance threshold 0.1 | `k_mode="authors"` in `Session` |
| **A6** | The **whole WHERE clause is one atom**, boolean structure preserved and parenthesised; set-ops recurse into both branches with depth in the atom string | one atom per AND-predicate; only the first branch visited | `where_granularity="clause"` (default) + set-op recursion |
| **A12** | Stop when mean pairwise similarity of survivors **≥ 1** (`stop_mode="sim1"`, tol `1e-9`) | stop on a single functional cluster | `termination="similarity_one"` |
| **A14** | **Exact execution-output equality**, then per-ambiguity-type AST heuristics; unmatched → `other` | nearest gold by embedding similarity | `assign_gold_intents_exec` (spec 16) |
| **A15** | Shannon entropy in **bits** (`np.log2`), un-normalized | nats | `gold_label_entropy` now base 2 |
| **A16** | `ERG` **appears nowhere**. Figure 5's baseline is `ATOMIC`+`EIG`, labelled "Baseline EIG + Atomic Features" | flagged unresolved | condition names match their `mode_labels` |

Two of these were not merely different but **buggy on our side**, found while
aligning (both regression-tested):

- **Only the first UNION branch was visited.** AMBROSIA's attachment and scope
  ambiguities are UNIONs differing in *which branch* carries the filter, so the two
  readings could produce **identical atom sets** — no decision variable could
  separate them.
- **`sqlglot` 30 renamed the `Select` arg `from` → `from_`**, so `_atoms_for`
  produced **no `FROM` atoms at all** in every run to date.

## 3. What the supplement does NOT settle

- **A1/A2 — candidate generation.** There is no generation code: no LLM client
  import, no prompt, no `N`, no temperature. `27154505_diverse_sql_output.jsonl` is
  a *precomputed input*. Model, prompt and sampling remain unrecoverable.
  Their pools: **300 questions** (100 per ambiguity type), median **95** candidates
  each. Using their pools directly removes generation as a confound.
- **The condition sweep driver.** `run_eval.py` never emits the `mode` column their
  notebook filters on; the script that varied ATOMIC / CLUSTER_CHARACTERISTIC /
  CLUSTER_GROUP is not included. Their full log *does* contain `mode`, so the
  reported run used a driver that was not shipped.

## 4. Their executed evaluation (from the 4.6 GB log)

| Property | Value |
|---|---|
| Records | 1,599 |
| Distinct examples | **64** |
| Modes | `ATOMIC`, `CLUSTER_CHARACTERISTIC`, `CLUSTER_GROUP` (533 each) |
| Strategies | `RANDOM` 402, `MAX_PROB_FIRST` 402, `SIM_IG_UNIFORM` 402, `EIG` 393 |
| Per (mode × strategy) | ~131–134 runs |
| Ambiguity mix | attachment 1,104 / scope 288 / vague 207 |

Three consequences for us:

1. **Scale is not our problem.** Their Figure 5 rests on 64 questions and ~134 runs
   per condition; our 150-question run already produced 350. Earlier plans to scale
   to the full 1,149-question test set are withdrawn.
2. **They ran 12 cells and reported 5.** `SIM_IG_UNIFORM` (a similarity/info-gain
   mix, `MIX = 0.05`) was executed in all three modes and appears nowhere in the
   paper. Worth stating plainly in our write-up.
3. **Their executed sample is attachment-dominated** (69%), while the paper's setup
   reads as balanced.

## 5. Sample selection — the step that reframes our span finding

`run_eval.py:1522-1531` restricts the evaluation to samples where **every parsed
gold query already appears among the parsed generated queries**:

```python
subsample = ambrosia_samples_v4[
    ambrosia_samples_v4.apply(
        lambda x: all([str(i) in [str(j) for j in x.parsed_generated_queries]
                       for i in x.parsed_gold_queries]), axis=1)
    & (ambrosia_samples_v4.parsed_gold_queries.str.len() != 0)
]
```
then `.groupby("ambig_type").head(3)`.

So the paper's numbers are **conditioned on pools that already span every gold
interpretation**. Our measurement that GPT-4o's pool spans ≥2 interpretations in
only ~9% of questions is therefore *the same selection step*, not a defect and not
a refutation — it quantifies how often the precondition holds.

**Consequence:** any comparison to Figure 5 must apply this filter, or it is
measuring a different population.

## 6. Implementation status

All seven settled decisions are implemented and tested, each selectable so the
spec-16 sweep can still vary them:

| Decision | Selector | Default |
|---|---|---|
| A3/A4 | `similarity_matrix(..., style="row_aligned")` | `header_rows` (until re-run confirms) |
| A5 | `build_session(..., k_mode="authors")` | `threshold` |
| A6 | `extract_features(..., where_granularity="clause")` | **`clause`** (switched) |
| A12 | `build_session(..., termination="similarity_one")` | `cluster_or_uninformative` |
| A14 | `assign_gold_intents_exec` | used by the sweep |
| A15 | bits | **switched** |
| A16 | condition names | **switched** |

## 7. Status

| # | Item | Status |
|---|---|---|
| 1 | Authors' configuration preset (`authors_config.AUTHORS`) | ✅ |
| 2 | Re-run on their pools with their filter (59 samples, 805 runs) | ✅ `docs/05` |
| 3 | **A8** lift-mined feature groups | ✅ implemented |
| 4 | **A10** candidate-level decision variables | ✅ — **the change that flipped the result** |
| 5 | Their logged per-turn curves extracted from the 4.6 GB log | ✅ `docs/05` |
| 6 | `SIM_IG_UNIFORM` strategy (their best condition, unreported in the paper) | ⬜ |
| 7 | Their label scheme (`other`/`unclear`, highest encoded label dropped) | ⬜ |
| 8 | Spec-16 sweep as sensitivity analysis around the aligned centre | ⬜ |

**Outcome.** The paper's central claim reproduces: clustering + EIG beats EIG alone
(0.994 vs 0.981). *Feature grouping* — their strongest condition by their own logs —
does not; we find it level with the baseline. Items 6 and 7 are the most likely
remaining explanations, and item 7 probably also accounts for the reach-zero ceiling
(0.98–0.99 for us vs 0.65–0.86 for them) that compresses all our differences.

### The methodological finding

Eight decisions the paper leaves unstated turned out to be load-bearing, and one of
them — **A10** — inverted the headline on its own. A replication that stops at
"we followed the paper" can therefore land on a confident, well-tested, entirely
wrong conclusion. Ours did, three times. The assumption register (`specs/README.md`)
exists precisely so those decisions are visible and revisable rather than implicit.
