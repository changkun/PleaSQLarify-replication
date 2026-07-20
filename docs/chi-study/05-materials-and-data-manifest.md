# CHI Replication-with-Agents Study
## Document 5 of 5 · Materials & Data Manifest

> Fields marked `‹TO FILL›` require human input (DOI, licensing decisions, contact,
> transcript release). All locations are repository-relative unless stated.

---

## 1. Repository

| | |
|---|---|
| **Primary repository URL** | https://github.com/changkun/PleaSQLarify-replication (public) |
| **Persistent identifier / DOI** | ‹TO FILL — not yet minted; OSF or Zenodo deposit recommended before submission› |
| **License(s)** | ‹TO FILL — no LICENSE file is currently present. Recommended: MIT/Apache-2.0 for code; CC BY 4.0 for the specs and write-ups; AMBROSIA-derived data not redistributed under any licence› |

**Top-level structure**

```
specs/        17 dependency-ordered specs + consolidated assumption register
src/          implementation (pleasqlarify package)
tests/        161 offline, deterministic tests
scripts/      experiment / sweep / re-run entry points
docs/         replication notes, results, findings, this study suite
experiments/  run artefacts — GITIGNORED (see §4), only README + NOTICE tracked
data/         AMBROSIA + materialised DBs — GITIGNORED
```

---

## 2. Code

| Artefact | Description | Author | Location |
|---|---|---|---|
| Algorithm core | Generation, functional clustering, atomic features, decision variables, EIG ranking, repair loop (§5–6) | Agent | `src/pleasqlarify/pipeline/` |
| `session.py` | Cluster-level repair-loop driver (our original A10 architecture) | Agent | `src/pleasqlarify/session.py` |
| `candidate_space.py` | **Candidate-level** decision variables + belief — the authors' architecture (A10); the change that inverted the result | Agent | `src/pleasqlarify/candidate_space.py` |
| `mining.py` | Lift-based frequent-itemset mining of cluster-characteristic groups (A8); apriori implemented directly | Agent | `src/pleasqlarify/pipeline/mining.py` |
| `embed.py` | Output serialization + optimal-row-alignment similarity (A3/A4); MiniLM + deterministic fallback | Agent | `src/pleasqlarify/pipeline/embed.py` |
| `cluster.py` | Agglomerative clustering (scipy path + numpy fallback), authors' `k` heuristic (A5) | Agent | `src/pleasqlarify/pipeline/cluster.py` |
| `features.py` | sqlglot AST → atomic features; whole-WHERE atoms, set-op recursion with depth (A6) | Agent | `src/pleasqlarify/pipeline/features.py` |
| Evaluation harness | Five conditions, simulated-user oracle, gold assignment, metrics, bootstrap CIs (§7) | Agent | `src/pleasqlarify/eval/` |
| `interpretation_span.py` | Execution-level measurement of whether a pool spans ≥2 gold interpretations; encodes both failed criteria as regression tests | Agent | `src/pleasqlarify/eval/interpretation_span.py` |
| `authors_config.py` | `AUTHORS` / `OURS_ORIGINAL` configuration presets across all nine aligned axes | Agent | `src/pleasqlarify/authors_config.py` |
| `authors_pools.py` | Loader for the authors' generation pools; their sample filter; DB materialisation + dump repair | Agent | `src/pleasqlarify/data/authors_pools.py` |
| Experiment infrastructure | Partitioned run folders, full LLM request/response capture, resume, sweep engine | Agent | `src/pleasqlarify/experiment/` |
| Visual interface (§8) | FastAPI backend + vanilla-JS SPA: Action Space, Decision Space, Predicted Query/Output | Agent | `src/pleasqlarify/server/` |
| `run_experiment.py` | Scalable, fully-provenanced generation + evaluation run | Agent | `scripts/run_experiment.py` |
| `run_authors_pools.py` | **Primary result**: re-run on the authors' pools with their filter and preset | Agent | `scripts/run_authors_pools.py` |
| `run_sweep.py` | Pre-registered A4/A5/A12 assumption sweep (built, not executed — see Doc 3 §2) | Agent | `scripts/run_sweep.py` |
| `run_real_eval.py` | Earlier real-backend AMBROSIA evaluation | Agent | `scripts/run_real_eval.py` |
| Test suite | 161 offline deterministic tests, incl. regression tests for every bug and every retracted claim | Agent | `tests/` |

> **Authorship note.** All code in this repository was written by the agent. Human
> contribution was direction, authorisation, provision of the authors' supplement
> and the API endpoint, and the force-push. No third-party code is vendored; the
> authors' supplementary code was *read*, never copied.

---

## 3. Stimuli, interfaces, apparatus

| Artefact | Description | Author | Location |
|---|---|---|---|
| Visual interface clone | Three linked views reconstructed from the paper's figures and prose. **Not** obtained from the authors and not validated against the original | Agent | `src/pleasqlarify/server/` |
| Prompt template | Zero-shot text-to-SQL prompt with full `CREATE TABLE` DDL (assumption A1 — the authors' generation prompt is unrecoverable) | Agent | `src/pleasqlarify/pipeline/generate.py` |
| Simulated-user oracle | Answers each decision variable per whether the gold query carries its atoms (A13). Stands in for a human participant | Agent | `src/pleasqlarify/eval/oracle.py` |
| Demo database + fixtures | Filmmaking-style SQLite fixtures for offline tests and the running example | Agent | `src/pleasqlarify/data/demo.py`, `tests/conftest.py` |
| Spec deck (17 specs) | Reconstruction of the system from the paper, with per-spec undocumented-decision sections | Agent | `specs/` |

---

## 4. Data

| Dataset | Format and size | Access level | Location |
|---|---|---|---|
| AMBROSIA benchmark | SQLite DBs + CSV; 1,149 ambiguous questions | **Restricted — not redistributed.** Password-protected download from ambrosia-benchmark.github.io | gitignored `data/ambrosia/` |
| Authors' generation pools | JSONL, ~6 MB; 300 questions × ~95 candidates | **Restricted — authors' supplement, not ours to release** | external; path passed via `--pools` |
| Authors' result log | JSONL, 4.6 GB; 1,599 records, 12 mode × strategy cells | **Restricted — authors' supplement** | external |
| Our 150-question run | Per-run folder: 10,308 files, 52 MB; 7,500 GPT-4o request/response bodies, per-sample intermediates, traces | **Not published** — embeds AMBROSIA-derived content | gitignored `experiments/gpt4o_per50_n50/` |
| Authors'-pools re-run | Per-condition summaries + per-run entropy curves (805 runs) | **Not published** as files; all numbers reported in `docs/05` | gitignored `experiments/authors_pools/` |
| Extracted logged curves | Aggregated per-turn entropies from the authors' log, 12 cells | **Not published** — derived from their supplement; numbers reported in `docs/05` | gitignored `experiments/authors_logged_curves.json` |
| Reported results | All tables, curves and verdicts | **Open** | `docs/05-authors-pools-rerun.md`, `docs/02`, `docs/03` |

**Data dictionary attached?** ☑ **Yes** — the artefact layout is documented in
`docs/04-experiments.md` and `experiments/README.md`. Brief version:

- `llm/<model>/<sample_id>/call_NNNN.json` — one full LLM request + response body
  (model, temperature, messages → id, resolved model, token usage, content).
- `samples/<sample_id>/candidates.json` — parsed candidates: `sql`, `gen_count`,
  atomic features `z`, executed output.
- `samples/<sample_id>/similarity_matrix.npy` — functional similarity matrix `S`.
- `samples/<sample_id>/traces/<condition>__gold<i>.json` — per-turn entropy,
  similarity, belief, ranked decision variables with IG, chosen variable, oracle
  answer.
- `results/` — `real_eval_results.csv` (condition, type, sample, gold, turn,
  entropy, similarity), `aggregate.json` (median + bootstrap CI per
  condition × type × turn), `summary.json`, `coverage_by_type.json`, `figure5.png`.

> **Why so much is withheld.** AMBROSIA's authors explicitly ask that the dataset
> not be re-uploaded. Our run artefacts embed the ambiguous questions, gold queries
> and executed outputs, so publishing them would redistribute it. Artefacts had been
> committed earlier under an explicit owner decision; on discovering the conflict
> the repository history was rewritten with `git-filter-repo` and force-pushed
> (2026-07-20). Everything is regenerable from the published code plus the original
> sources — `experiments/README.md` gives the exact commands.

---

## 5. Agent transcripts and prompts

| Session / artefact | Description | Tool / model | Location |
|---|---|---|---|
| Main development sessions | Spec authoring → implementation → real-backend runs → supplement alignment → final write-up | Claude Code, Claude Opus 4.8 | ‹TO FILL — operator to decide on release› |
| Parameter-extraction subagent | One delegated agent reading the authors' `run_eval.py` + `helpers.py` for exact parameter values | Claude Code subagent | transcript within the main session |
| Reviewer-model consultations | Adversarial review at decision points; caught the nested-gold measurement bug pre-publication | Stronger reviewer model, full-transcript visibility | transcript within the main session |
| Commit history as process record | 46 commits; messages document each decision, bug and retraction with rationale | — | `git log` (public) |
| Generation prompts | The only prompt materially affecting reported results (candidate generation) | GPT-4o | `src/pleasqlarify/pipeline/generate.py` (published) |

> The **commit history is the most complete published record** of the agent
> workflow: each retraction, bug and alignment step is a commit with an explanatory
> message, so the process is auditable even if session transcripts are not released.

---

## 6. Documentation files (this suite)

| Document | Version / date | Status |
|---|---|---|
| Doc 1 · ‹protocol / scoping› | — | ‹TO FILL — not produced in this study's format› |
| Doc 2 · Pre-registration | Spec deck `specs/01`–`15` (2026-07-01); sweep pre-registration `specs/evaluation/16` (2026-07-20) | **Substitute artefacts.** No Doc 2 in the study's format; see Doc 3 §2 terminology note |
| **Doc 3 · Deviations & Adaptations Log** | v1.0, 2026-07-20 | Complete |
| **Doc 4 · Team Site Report** | v1.0, 2026-07-20 | Complete except ‹TO FILL› fields (team identity, hours, sign-off) |
| **Doc 5 · Materials & Data Manifest** | v1.0, 2026-07-20 | Complete except ‹TO FILL› fields (DOI, licence, contact) |
| Supporting: replication notes | `docs/01-replication-notes.md` | Current |
| Supporting: superseded results | `docs/02-execution-results.md` | **Superseded** — retained as provenance |
| Supporting: findings & decisions | `docs/03-findings-and-decisions.md` | Current, with section D retained as the record of a retracted conclusion |
| Supporting: experiment layout | `docs/04-experiments.md` | Current |
| **Supporting: primary result** | `docs/05-authors-pools-rerun.md` | **Canonical result document** |
| Supporting: assumption register | `specs/README.md` | Current — A1–A18, resolved rows marked |
| Supporting: authors' supplement | `specs/evaluation/17-authors-supplement.md` | Current — ground truth for undocumented decisions |

---

## 7. Ethics

**Not applicable — no human participants.**

This replication targeted the paper's computational contributions. No participants
were recruited, no personal data was collected or processed, and no consent,
debriefing or recruitment materials exist. The paper's §9 user study was reproduced
as a written protocol (`specs/study/15-user-study-protocol.md`) but **not executed**;
running it would require ethics review, which was not sought.

| Field | Value |
|---|---|
| IRB / ethics body and approval number | Not applicable |
| Date of approval | Not applicable |
| Approved documents on file | Not applicable |
| Amendments filed | Not applicable |

**Non-participant ethics issues that did arise, and how they were handled:**

1. **Third-party data redistribution.** Experiment artefacts embedding AMBROSIA
   content were committed to a public repository under an explicit owner decision.
   On surfacing the conflict with the dataset authors' request, artefacts were
   untracked, history was rewritten and force-pushed, and the constraint documented
   in `experiments/NOTICE.md`. Old objects may persist in the hosting provider's
   cache until garbage-collected.
2. **Credential handling.** The API key was passed via environment variables only,
   never written to artefacts or committed; verified by grep across the repository.
   Captured request bodies do record the gateway `base_url`, which is an endpoint
   address rather than a secret.
3. **Use of the authors' unpublished supplement.** Read as ground truth and cited
   by file and line; never copied into this repository or redistributed.

---

## 8. Reproducibility check

☑ **Partially**

**Verified on:** 2026-07-20 **by:** Claude Code (agent), on the operator's machine.

What is verified: the full test suite (161 passed, 3 skipped) runs offline and
deterministically from a clean `uv` environment; the primary result
(`scripts/run_authors_pools.py`) is reproducible end-to-end at zero API cost given
the authors' pool file; the 150-question GPT-4o run is reproducible given AMBROSIA
and an endpoint.

Why only partial:

- **No independent reproduction.** Everything was verified by the agent that wrote
  it, on one machine, by one operator. No second party has re-run it.
- **Two required inputs are not redistributable** (AMBROSIA; the authors'
  supplement), so a third party must obtain both before the primary result can be
  reproduced.
- **Generation is not fully deterministic.** GPT-4o at temperature 0.7 will not
  reproduce our exact pools; the cached completions make *our* run replayable, but a
  fresh generation run will differ.
- ‹TO FILL: independent verification by a second team member or the study lead›

---

## 9. Contact

**Corresponding team member for follow-up from the study lead or the original
paper's authors:**

Changkun Ou — ‹TO FILL: preferred contact address and affiliation›

> Suggested first contact with the original authors: the five questions in
> Document 4 §5 ("What you would want the original authors to check first"),
> particularly the `mode` → configuration mapping and the gold-label scheme, since
> those are the two most likely explanations for the one contribution we did not
> reproduce.
