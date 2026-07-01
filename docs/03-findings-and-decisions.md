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

See `02-execution-results.md` for the numbers. Key findings:

1. **A loader bug nearly produced a false positive.** One AMBROSIA database hosts
   several distinct ambiguous questions; our first `sample_id` was the DB filename,
   so different questions **collided** and their eval runs overwrote each other.
   The corrupted results looked like a clean reproduction of the paper. Fixing
   `sample_id` to be unique per question (and re-running) reversed that
   conclusion. Lesson recorded here because it is the kind of silent data bug that
   makes a replication *look* successful.
2. **Model collapse is real, and strongest for scope.** GPT-4o at `N=50` surfaced
   ≥ 2 interpretations in 12/15 *vague*, 6/10 *attachment*, but only **2/10
   *scope*** questions. It usually samples one reading — exactly the failure the
   paper motivates — and scope ambiguity is the hardest for it to surface. This is
   robust and independent of the algorithm comparison.
3. **The paper's clustering advantage does NOT cleanly reproduce on this subset.**
   Under our default assumptions the atomic baselines (Random, ERG) drive
   gold-label entropy to zero *sooner* than the clustering "ours" conditions,
   which reduce entropy but often plateau above zero. Diagnosed cause: "ours"
   terminates at a **single functional cluster** (A12), and on AMBROSIA's tiny
   databases different interpretations embed near-identically, so clusters are not
   gold-pure. This is a concrete demonstration that the flagged assumptions
   **A12** (termination granularity), **A5** (clustering `k`), and **A14** (gold
   assignment) are load-bearing — the whole point of the assumption register.
4. **One paper-consistent signal:** greedy Max-Prob-First is the worst selection
   policy, supporting information-gain-driven clarification.

Net: the *machinery* reproduces (real GPT-4o + MiniLM + UMAP + AMBROSIA run end to
end, and the demo with separable outputs shows the intended clustering advantage),
but the paper's *quantitative magnitudes* do not, at this scale and under these
assumptions. Reproducing them is future work that would sweep A5/A12/A14 and use
larger databases — enabled, not done, by this scaffold.
