# Findings & Decisions

Consolidated record of what we discovered while replicating *PleaSQLarify* and
every non-trivial decision we made where the paper was silent. The authoritative,
per-step reasoning lives in each spec's *Core Assumptions & Undocumented
Decisions* section; this is the executive summary.

## A. Meta-findings (about the paper's reproducibility)

1. **The advertised code is not available.** The paper links
   `github.com/chanr0/pleasqlarify`. Its `main` branch is a 14-byte README; the
   only code is a **draft PR authored by GitHub Copilot** ("Bootstrap CHI'26
   publication repository") that *contradicts* the paper (uses `sqlparse`, no LLM
   sampling, clustering, embeddings, UMAP, information gain, or AMBROSIA). It has
   no more authority than a guess, so this replication is **paper-first** and does
   not use it as ground truth.
2. **AMBROSIA is not on HuggingFace.** Despite the "Transformers Hub" phrasing
   around such benchmarks, AMBROSIA ships as a **password-protected direct
   download** (`ambrosia-benchmark.github.io`, Edinburgh DataSync). The authors
   explicitly ask that it not be re-uploaded to GitHub/HF, so we keep it
   gitignored and load it locally. This resolves spec 01 assumption **F1** (which
   had guessed an HF id).
3. **A legend/text mismatch in the evaluation.** Figure 5's legend names a
   baseline `ERG` while the Setup text lists "expected information gain without
   functional clustering". We treat them as the same condition (EIG on atomic
   features, no clustering) and label it `ERG` in plots to match the figure. This
   is assumption **A16**; flagged in code.

## B. Deviations from the paper (deliberate, documented)

| # | Paper says | We do | Why |
|---|---|---|---|
| D1 | Spider `process_sql` parser | **sqlglot** | maintained, pip-installable, richer AST + alias qualifier; same clause-element atoms |
| D2 | GPT-4o (closed) | GPT-4o via configurable OpenAI-compatible endpoint, cached | reproducibility + offline replay; swappable |
| D3 | — (no offline story) | deterministic fallbacks (hashing embedder, MDS, mock LLM) | make the whole pipeline + tests run with no network |

## C. Undocumented decisions and our defaults

Grouped by pipeline step. "Default" = what we implemented; alternatives are in the
owning spec.

### Generation (spec 03)
- **A1 prompt/schema context** → zero-shot, full `CREATE TABLE` DDL, single-query
  instruction, no sample rows.
- **A2 validity + dedup** → drop on parse failure only; collapse byte-identical
  generations into one candidate with a `gen_count`; keep functional duplicates
  (clustering groups them).
- **A3 sampling** → independent per-sample calls; **A5 temperature = 0.7** (pinned
  by the paper).

### Functional clustering (spec 04)
- **A3 output→text** → header + `col=value` rows, canonically sorted, length-capped.
- **A4 metric + degenerate outputs** → cosine; errors/empties → one sentinel class.
- **A5 linkage + k** → average linkage on `1 − S`; k by distance threshold in the
  interactive tool, k = #gold intents in the benchmark (the paper's "exactly
  specify the number of clusters").

### Atomic features (spec 05)
- **A6 granularity** → a projected column is one atom; a WHERE predicate
  `(col, op, normalized-literal)` is one atom (so `=` vs `LIKE` differ, per
  Figure 4); a JOIN (table + on-condition) is one atom.
- **A7 aliases** → resolved to base `table.column` before encoding.
- **A8 star** → `SELECT *` kept as a single atom (not expanded).

### Decision variables (spec 06)
- **A8a grouping** → single atoms + each cluster's common-atom signature
  (captures the paper's "interaction neglect"); **A8b** keep `lift > 1`.
- **A8c atomic vs grouped** → the two "ours" eval variants; grouped adds the
  multi-atom signatures. Verified non-inert by a dedicated test.
- **A8d "determined"** → co-occurrence ≥ 0.999.

### Belief + information gain (spec 07)
- **A9 belief init** → uniform over surviving clusters (generation-frequency prior
  available behind a flag).
- **A10 intent = cluster**; **A11 binary value set** (contains/excludes).

### Repair loop (spec 08)
- **A12 termination** → single functional class; **A12c** belief recomputed on the
  reclustered survivors.

### Evaluation (specs 09/10)
- **A13 oracle** → answer yes/no by whether the gold query carries the decision
  variable's atoms.
- **A14 gold-intent assignment** → nearest gold by functional output similarity.
- **A15 metrics** → gold-label entropy = Shannon entropy of the count-based
  survivor→gold distribution; functional similarity = mean pairwise `S` among
  survivors; **A15b** forward-fill terminated runs.

### Interface (specs 11–14)
- **A-be-1 stack** → FastAPI backend + vanilla-JS SPA; **A17 UMAP** on precomputed
  `1 − S`, MDS fallback; per-session JSONL trace logging for the study.

## D. Empirical observations from the real run

See `02-execution-results.md` for numbers. Notable qualitative findings:

- **Model collapse is real and measurable.** With small `N`, GPT-4o often samples
  only the dominant interpretation, so some ambiguous questions surface *zero*
  residual ambiguity in the candidate pool (gold-label entropy 0 at turn 0). This
  is exactly the failure the paper motivates ("systems sample the most probable
  interpretation"), and larger `N` surfaces more interpretations — which is why
  the paper fixes `N = 50`.
- On samples with genuine initial ambiguity, clustering-based repair reduces
  gold-label entropy at least as fast as the baselines, reproducing the paper's
  directional claim (magnitudes in `02-execution-results.md`).
