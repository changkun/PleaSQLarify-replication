# CHI Replication-with-Agents Study
## Document 3 of 5 · Deviations & Adaptations Log

**Target paper:** Chan, R., Sevastjanova, R., El-Assady, M. *PleaSQLarify: Visual
Pragmatic Repair for Natural Language Database Querying.* CHI '26.

**Replication repository:** https://github.com/changkun/PleaSQLarify-replication

> **Scope note.** This replication targets the paper's **computational**
> contributions (§5–6 algorithm, §7 quantitative evaluation, §8 interface). The §9
> user study was reproduced as an executable protocol (`specs/study/15`) but **not
> run**: no human participants were recruited, so no participant-facing deviations
> exist. Rows below concern software, data and analysis.

> **Terminology.** "Pre-registration" here means the repository's dependency-ordered
> **spec deck** (`specs/01`–`15`, written before implementation) and the explicitly
> pre-registered **sweep protocol** (`specs/evaluation/16-assumption-sweep.md`,
> committed before any sweep result existed). A separate Document 2 in the study's
> own format was not produced; Section 2 maps onto these artefacts and says so.

---

## 1. Deviations from the original paper

| Date | Original specification | What we did instead | Reason | Decided by | Severity |
|---|---|---|---|---|---|
| 2026-07-01 | Spider `process_sql` parser for SQL ASTs | **sqlglot** for parsing + alias qualification | Agent capability / maintainability: Spider's parser is a vendored single file covering a SQL subset and needing a bespoke schema object. Documented as spec 05 D1. | Both (agent proposed, human authorised "paper-first, best gap-fill") | Medium |
| 2026-07-01 | Paper cites AMBROSIA without acquisition details | Password-protected direct download (Edinburgh DataSync); dataset gitignored, never redistributed | Ethics / licensing: authors ask it not be re-uploaded. Resolved spec 01 assumption F1, which had wrongly guessed a HuggingFace id. | Both | Low |
| 2026-07-01 | GPT-4o as candidate generator | GPT-4o via a configurable OpenAI-compatible endpoint, with cached replay | Reproducibility + cost: allows offline replay of a fixed generation pool. | Human (supplied endpoint) | Low |
| 2026-07-01 | No offline story given | Deterministic fallbacks (hashing embedder, classical MDS, mock LLM) behind the same interfaces | Agent capability: lets the full pipeline and test suite run with no network. Never used for reported results. | Agent | Low |
| 2026-07-01 | Paper's advertised code repo `github.com/chanr0/pleasqlarify` | **Not used as ground truth.** Verified to be a 14-byte README plus a Copilot-generated draft PR that contradicts the paper | Fidelity: using it would have introduced non-authorial decisions. | Both (human asked us to double-check; agent verified) | Low |
| 2026-07-20 | Figure 5 legend names a baseline `ERG` | Treated as `EIG` (`ATOMIC`+`EIG`) | Resolved from the authors' supplement: `ERG` appears nowhere in their code; their plotting code labels this condition "Baseline EIG + Atomic Features". Was assumption A16. | Agent | Low |
| 2026-07-20 | Paper's §7 setup reads as a balanced evaluation | Reported that their executed run is **attachment-dominated** (69%) and rests on **64 examples**, with **12 condition cells run but 5 reported** | Transparency: extracted from their own 4.6 GB result log. Not a deviation in our procedure, but a deviation of the paper from its own description; logged here so it is visible. | Agent | Medium |
| 2026-07-20 | Paper describes five conditions | Their log contains a sixth strategy, `SIM_IG_UNIFORM`, which is their **best** condition (0.883) and appears nowhere in the paper. We did not implement it | Time; and it is not part of the paper's claims. Flagged as open work. | Agent | Medium |

---

## 2. Deviations from our own pre-registered protocol

| Date | Original specification | What we did instead | Reason | Decided by | Severity |
|---|---|---|---|---|---|
| 2026-07-05 | Spec deck assumed our documented gap-fills (A1–A18) would stand as the implementation | **Precedence re-ordered** to *paper → authors' supplementary code → our gap-fills* once the supplement was obtained | The supplement is what the paper's reported numbers were actually produced by. Recorded as spec 17. | Both (human supplied the supplement, agent proposed the precedence change, human approved) | High |
| 2026-07-20 | Spec 16 §3 grid: sweep A4/A5/A12 around **our** defaults, 120 cells, dev/held-out split | **Sweep not executed.** Superseded by aligning to the authors' verified decisions instead | The sweep's purpose was to discover whether our gap-fills explained the non-reproduction. The supplement answered that question directly and authoritatively, making the search redundant. | Both | Medium |
| 2026-07-20 | Spec 16 §2: score every cell with `assign_gold_intents_exec` (our exec-match yardstick) | Kept for the sweep, but the **authors' own** gold assignment (exact output equality + per-type AST heuristics) supersedes it for reported results | Fidelity to A14. | Agent | Medium |
| 2026-07-20 | Spec 16 §5 win criterion (`Δ_dev > 0` and `Δ_heldout ≥ 0`) | Never applied — no sweep was run, so no cell selection occurred | Follows from the row above. **No cell was ever selected post-hoc**; the pre-registration is retained unexecuted rather than quietly reused. | Both | Low |
| 2026-07-05 | Owner decision: version all experiment artefacts in git ("version everything") | **Reversed.** `experiments/` untracked, history rewritten with `git-filter-repo`, force-pushed | Ethics: the repository is public and the artefacts embed AMBROSIA-derived content the dataset authors ask not be redistributed. | Both (agent surfaced the conflict, human chose the remedy and executed the force-push) | Medium |
| 2026-07-20 | Metrics in nats (`math.log`) | Switched to **bits** (`log2`), for both gold-label entropy and the belief entropy feeding IG | Fidelity to A15: their `compute_label_entropy` and `entropy` both use `np.log2`. Rescales all prior numbers by 1/ln2; IG selection unaffected (argmax is scale-invariant). | Agent | Low |
| 2026-07-20 | Evaluate on our own GPT-4o generation pools (150 questions) | Primary result now computed on the **authors' 300 pools** with **their sample filter** | The supplement's generation code is absent, so generation was the one unspecifiable confound; their pools remove it at zero API cost. Our own run is retained as provenance. | Both | High |

---

## 3. Deviations from the pre-registered analysis plan

| Date | Original specification | What we did instead | Reason | Decided by | Severity |
|---|---|---|---|---|---|
| 2026-07-01 | Report Figure 5 reproduction from the first real-data run | **Retracted headline #1** ("clean reproduction") | A `sample_id` collision — one AMBROSIA database hosts several distinct ambiguous questions — made runs overwrite each other and manufacture agreement. Fixed by hashing the utterance into the id. | Agent (self-caught after a directional claim had already been reported to the human) | High |
| 2026-07-05 | Report the 150-sample result as the finding | **Retracted headline #2** ("the paper's clustering advantage does not reproduce") | Later shown to be an artefact of our decision-variable architecture (A10), not a property of AMBROSIA. | Agent | High |
| 2026-07-20 | Measure whether candidate pools span ≥2 gold interpretations | **Retracted headline #3** ("0/103 — GPT-4o never surfaces both readings") | The criterion ("candidate contains gold *i*'s distinctive values") is structurally impossible when gold outputs are **nested**, which they are in 102/150 AMBROSIA samples. Corrected criterion gives 14/148 (9%). Then reframed again: the authors *filter* to spanning pools, so this measures their selection step, not a defect. | Both (external reviewer model flagged the nesting bug before publication) | High |
| 2026-07-20 | Primary metric: fraction of runs reaching zero gold-label entropy | Retained, but **downgraded** in favour of per-turn entropy curves | Ceiling effect: after alignment three conditions sit at 0.98–0.99, so reach-zero can no longer separate them. Declared in `docs/05` rather than silently switching. | Agent | Medium |
| 2026-07-20 | Compare our curves against the paper's Figure 5 | Compared against the authors' **own logged per-turn entropies** extracted from `full_logs_08111341.jsonl` | Strictly stronger: compares numbers to numbers rather than to a rendered figure. Revealed that their `CLUSTER_CHARACTERISTIC` underperforms their `ATOMIC`, which our result had independently reproduced. | Agent | Medium |
| 2026-07-20 | Not planned | Added a **candidate-level architecture** (A10) and re-ran | Their belief and variables are candidate-level; ours were cluster-level. This single change inverted the headline. | Both (agent diagnosed and proposed; human approved "yes") | High |

---

## 4. Notes on translations / localisation / platform changes

No linguistic translation or localisation applies (English-only, no participants).
Platform and substitution notes:

| Item | Original | Ours | Note |
|---|---|---|---|
| SQL parser | Spider `process_sql` (vendored) | `sqlglot` 30.x | Same clause-element atoms. Two of *our* bugs traced to this substitution: `sqlglot` 30 renamed the `Select` arg `from` → `from_` (so `FROM` atoms were never produced), and our AST walk visited only the first `UNION` branch. |
| Itemset mining | `mlxtend.apriori` | Apriori implemented directly | Avoids adding a dependency; identical downward-closure semantics, `max_len ≤ 4`. |
| Hierarchical clustering | `scipy.cluster.hierarchy` | Same (after an initial pure-numpy implementation) | Our own version was O(n³) and could not process their ~95-candidate pools. Switching also corrected the semantics of `k`: `fcluster(criterion="maxclust")` gives *at most* k, since tied merges are cut together. |
| Interface | Hosted tool shown in the paper; no source released | FastAPI backend + vanilla-JS SPA **built by the agent** | The §8 interface was cloned from figures and prose, not obtained from the authors. Not visually validated against the original. |
| Databases | AMBROSIA `.sqlite` files | Materialised from the authors' `db_dump` field where possible | 10/300 of their dumps have malformed DDL (trailing comma before `)`); repaired, scoped to DDL. A few are internally inconsistent (INSERT naming a nonexistent column) and fall back to the real AMBROSIA file. All 268 test-split samples load; counts reported, none dropped silently. |
| OS / runtime | Unstated | macOS (Darwin 27), Python 3.11 via `uv` | Python 3.14 (system) was too new for some wheels. |

---

## 5. Severity rubric (self-rating)

- **Low:** cosmetic or technical.
- **Medium:** could plausibly affect a single measure, not the overall design.
- **High:** touches the manipulation, the dependent variable, the sample, or the analysis.

**Totals:** Low **8** · Medium **10** · High **6**.

All six High rows concern the *analysis and architecture*, not the sample or a
manipulation — consistent with a computational replication where the load-bearing
risk is undocumented implementation decisions rather than participant handling.
