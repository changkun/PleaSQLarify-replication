# CHI Replication-with-Agents Study
## Document 4 of 5 · Team Site Report

> **Fields marked `‹TO FILL›` require information the agent does not have** (team
> identity, human hours, institutional details, sign-off). They are deliberately
> left blank rather than estimated. Everything else is drawn from the repository,
> the git history, and the session transcript.

---

## 1. Team identification

| | |
|---|---|
| **Team name** | ‹TO FILL› |
| **Members and roles** | Changkun Ou — study lead, human operator, decision authority.<br>Claude Code (Opus 4.8) — implementing agent: specs, implementation, experiments, analysis, documentation.<br>‹TO FILL: any additional members› |
| **Institution(s) and country** | ‹TO FILL› |
| **Target paper (full citation)** | Chan, R., Sevastjanova, R., El-Assady, M. *PleaSQLarify: Visual Pragmatic Repair for Natural Language Database Querying.* Proc. CHI '26. ACM. |

---

## 2. Replication outcome

**Did you collect any data?**
☑ **Yes, primary study completed** — *computational* data only. No human
participants. The paper's §9 user study was reproduced as an executable protocol
but not run.

*If not, why?* The §9 user study (12 participants) was out of scope for the
available week and would have required ethics review; the paper's §5–7
computational contributions were targeted instead.

### 2a. Fidelity — did you build the right study?

**Fidelity verdict from the original authors:**
☑ **Pending** — authors not yet contacted.

**Our own fidelity self-assessment, before hearing back:**

**Moderate-to-high for the algorithm and evaluation; low for the interface.**

We hold an unusually strong evidence base for this judgement, because the authors'
supplementary code became available mid-project and we aligned against it directly
rather than against prose. Eight decisions the paper leaves unstated were settled
from their code (A3–A6, A8, A10, A12, A14–A16), and two of our earlier differences
turned out to be outright bugs on our side. The `run_eval.py:1522` sample filter,
which conditions all their reported numbers on candidate pools that already contain
every gold query, is now applied; our filter keeps 59 samples where theirs kept 64,
which is close corroboration.

Three fidelity gaps remain, in decreasing importance. **(i)** Their `CLUSTER_GROUP`
condition — their strongest — is still not reproduced; we obtain it at baseline
level, so some detail of the mined-group→variable mapping still differs. **(ii)**
Our reach-zero metric saturates at 0.98–0.99 where theirs spans 0.65–0.86, which
strongly suggests our gold-label scheme differs from their `classify_behavior`
(they add `other`/`unclear` classes and drop the highest encoded label). **(iii)**
The §8 interface was **built by the agent from figures and prose**; no source was
released and we have not validated it against the original visually or
behaviourally, so its fidelity is essentially unassessed.

### 2b. Replication outcome, conditional on fidelity

| Contribution targeted | Verdict | What we observed |
|---|---|---|
| **§5–6 pragmatic-repair algorithm** (generate → cluster → atoms → decision variables → EIG → loop) | **Replicated** | Implemented end-to-end and runs on real backends; 161 offline tests. Behaves as specified once A3–A6/A8/A10/A12 match their code. |
| **§7 core claim: functional clustering + EIG beats EIG alone** | **Replicated** | On the authors' pools with their filter and configuration: reach-zero **0.994** (Clustering+EIG+Atomic) vs **0.981** (EIG+Atomic), with lower entropy at turns 1–2. |
| **§7 claim: feature grouping is the strongest condition** | **Not replicated** | We obtain 0.981 — level with the plain baseline. Their own logs make `CLUSTER_GROUP` their best condition (0.855 vs 0.740 for `ATOMIC`). |
| **§7 claim: greedy Max-Prob-First is a poor strategy** | **Replicated** | Catastrophic in our run (0.068) and weakest in theirs (0.194). |
| **§7 claim (implicit): clustering alone helps** | **Refuted in their own data** | Their logs show `CLUSTER_CHARACTERISTIC` (clustering without grouping) is the **worst** EIG condition (0.649), losing to `ATOMIC` (0.740). We independently reproduced this ordering under our pre-A10 architecture. |
| **§8 visual interface** | **Not testable** | Built, runs, three linked views implemented; but no released original to compare against and no user evaluation performed. |
| **§9 user study** | **Not testable** | Protocol reproduced as spec 15; not run. |

### Form of the result

Quantitative, system-level. Per-turn mean gold-label entropy (bits) and fraction of
runs reaching zero entropy, across five conditions × 59 samples × gold
interpretations = **805 runs**. Reported against two references: our own aligned
re-run, and the authors' **own logged curves** extracted from their 4.6 GB result
log (12 mode × strategy cells, 1,599 records, 64 examples).

Absolute values are **not** comparable across the two: their entropies use their
label scheme on 64 examples, ours use execution-match labels on the 59 our filter
keeps. Only orderings *within* each table are compared — stated explicitly in
`docs/05-authors-pools-rerun.md`.

---

## 3. Feasibility outcome

**Overall feasibility:** ☑ **Partially feasible** — the agent-driven workflow
produced a complete, tested, runnable computational replication end-to-end, but
required human override at three decisive points and would have shipped a **wrong
headline three times** without correction.

**Stages where the workflow worked well**

- **Spec generation from the paper.** The dependency-ordered deck with an explicit
  register of undocumented decisions (A1–A18) was the single highest-value artefact:
  when the authors' code arrived, alignment was a matter of walking the register.
- **Implementation and test discipline.** 161 tests, every bug fix carrying a
  regression test. Several tests later *caught the agent's own* misconceptions.
- **Infrastructure and provenance.** Partitioned run folders capturing every LLM
  request/response body, resume support, and a zero-API-cost replay path.
- **Reading the authors' 110 KB `helpers.py` / 64 KB `run_eval.py`** and extracting
  exact parameter values, including spotting that their silhouette-based `k`
  selector is dead code and their live rule is a size heuristic.
- **Performance debugging.** Three real speed-ups (O(n³) clustering, per-pair
  re-embedding, Python-loop bootstrap) took the suite from 300 s to 3 s.

**Stages where it broke**

- **Premature confident reporting.** The agent reported directional findings to the
  human *before* validating them, three times.
- **Measurement design.** Two of the three retractions were bad *metrics*, not bad
  code: a colliding sample id, and a span criterion that nested gold outputs make
  structurally impossible. Both passed their own tests.
- **Architectural assumptions.** The agent implemented cluster-level decision
  variables from the paper's prose and did not question that choice for three
  weeks; it was the decisive error.
- **Scale reasoning.** The agent recommended a ~57,000-call / ~12M-token scale-up
  that was later shown to be unnecessary — the paper's own evaluation rests on 64
  examples, fewer runs than we already had.

---

## 4. Effort accounting

| | |
|---|---|
| **Total human hours (per member)** | ‹TO FILL — not observable by the agent› |
| **Approximate API / compute spend** | Measured GPT-4o usage for the primary run: **7,500 calls, 1,606,504 tokens** (1,218,150 prompt + 388,354 completion). At list GPT-4o pricing ≈ **US$9–10**. Plus agent-session token spend for development ‹TO FILL — from the operator's billing›. All post-supplement analysis (authors' pools, sweep engine, logged-curve extraction) cost **$0** in API calls: replay only. |
| **Other costs** | None. No participants, no paid infrastructure. Local CPU only (MiniLM, UMAP, scipy). |

**Hours by phase:** ‹TO FILL›. For calibration, the *agent-side* work decomposed
roughly as: spec authoring (1 session-day), implementation + tests (1), real-backend
wiring and the 150-question run (1), provenance/scaling infrastructure (1), and the
supplement-driven realignment + three re-runs + write-up (1 long session). Debugging
the agent's own wrong conclusions — as opposed to its code — consumed a
disproportionate share of the final phase.

---

## 5. Fidelity to the original

**Deviations logged in Document 3:** Low **8** · Medium **10** · High **6**.

**Single largest fidelity concern**

We cannot yet reproduce the authors' strongest condition, `CLUSTER_GROUP` (feature
grouping). We have implemented their itemset mining faithfully — apriori over
lengths 1–4, `lift ≥ 1.3`, length selected by
`Σ(lift−1)·supp_in/(1+0.25(size−1))`, `min_len=2`, top-1 per cluster — and verified
it fires on their data (3–4 groups per sample, lift 21–85). We then corrected the
architectural gap that made those groups inert (A10: their variables split
candidates, not clusters). Yet the condition still lands at baseline level (0.981)
where their own logs put it clearly first (0.855 vs 0.740). Something in the
mined-group→decision-variable mapping still differs — most likely `min_bin_frac`
handling, the dedup key (they key on `(cluster_id, mask)`), or `include_atomic`
interacting with `groups_only_turns`. Compounding this, our reach-zero metric
saturates at 0.98–0.99 while theirs spans 0.65–0.86, which points at a different
gold-label scheme and independently compresses every difference we report.

**What we would want the original authors to check first**

1. **The mode → configuration mapping.** `run_eval.py` never emits the `mode` column
   the plotting notebook filters on, so the driver that varied `ATOMIC` /
   `CLUSTER_CHARACTERISTIC` / `CLUSTER_GROUP` is not in the supplement. We inferred
   `CLUSTER_GROUP ↔ split_mode="mask"` and `CLUSTER_CHARACTERISTIC ↔
   split_mode="cluster"`. Is that right?
2. **The gold-label scheme.** Does dropping the highest `LabelEncoder` class
   (`run_eval.py:1616-1620`) intentionally exclude `unclear`, and how should
   `other` be treated in the entropy?
3. **`SIM_IG_UNIFORM`.** It was run across all three modes and is the best condition
   in the log (0.883), but appears nowhere in the paper. Was its omission
   deliberate?
4. **Sample selection.** Confirm that Figure 5 is conditioned on the
   all-golds-present filter, and whether the `.head(3)` cap was in the reported run
   (the log shows 64 examples, not ≤9).
5. **Candidate generation.** Model, prompt, `N` and temperature are absent from the
   supplement — the one decision we could not align.

---

## 6. Agent workflow report

**Agent stack actually used**

Claude Code with Claude Opus 4.8 as the implementing agent, run in a single-agent
loop with shell, file and web tools; one delegated subagent used once to extract
parameter values from the authors' 174 KB of Python. A stronger reviewer model was
consulted at decision points (an "advisor" tool with full transcript visibility).
No multi-agent orchestration. ‹TO FILL: comparison against the Document 2 plan›.

**Most useful single capability**

Reading a large, undocumented third-party codebase and extracting exact,
load-bearing parameter values — including noticing that a function is *dead code*
(their silhouette `k` selector, whose body is commented out) and that a local
definition **shadows** an imported one with different behaviour. That is the work
that converted "the paper doesn't say" into "here is what they actually did", and
it is what ultimately flipped the replication verdict.

**Most damaging single failure mode**

**Confident reporting ahead of validation.** The agent produced three headline
findings — "clean reproduction", "clustering does not reproduce", "the model never
surfaces both readings" — and communicated each to the human before it was sound.
Each was overturned. Notably, the failures were *not* sloppy coding: each headline
was backed by passing tests, a plausible mechanism, and in one case a dump of
survivor outputs offered as verification. The tests validated the code, not the
measurement, and the agent did not distinguish the two.

**Times a human took the keyboard back:** 4

1. Directed that the empty upstream repo be double-checked rather than trusted —
   correct; it was a Copilot stub contradicting the paper.
2. Supplied the authors' supplementary material, which the agent had no way to
   obtain and which changed the project's ground truth.
3. Overrode the "version everything" artefact policy after the agent surfaced the
   AMBROSIA redistribution conflict, and chose history rewriting.
4. Executed the `git push --force` itself (the agent's tooling declined the
   destructive operation).

**Times the agent caught a human error / a shared error:** 4

1. Found the `sample_id` collision that had made its own prior "clean reproduction"
   spurious — self-caught, then retracted publicly to the operator.
2. Found two bugs its own test suite had *encoded* as correct behaviour: only the
   first `UNION` branch was parsed, and `sqlglot` 30's `from` → `from_` rename meant
   `FROM` atoms were never produced in any run.
3. Found a latent bug where a `#` in a path silently opened a different, empty
   SQLite database via URI-fragment parsing.
4. Surfaced that the public repository was redistributing a dataset whose authors
   ask that it not be redistributed — a compliance issue the human had authorised
   without that context.

*Also counted against the agent:* the reviewer model caught the nested-gold
measurement bug before the agent published "0/103 — total model collapse", which
would have been retraction #4.

---

## 7. Lessons for the next team

**Three things we would tell a team about to start**

1. **Write the assumption register before the code, and treat it as the deliverable.**
   Every decision the paper leaves unstated should be a numbered row with a chosen
   default, the alternatives, and what the paper implies. When the authors' code
   arrived, realignment was a walk down that register instead of an archaeology
   project. Without it we would not have been able to say *which* eight decisions
   differed, let alone which one inverted the result.
2. **Agents test code, not measurements — so review the metric, not the diff.**
   All three of our retracted headlines passed a green test suite. A colliding
   identifier, a nats/bits mismatch, and a span criterion that was structurally
   impossible on nested data are invisible to unit tests and obvious to five
   minutes of adversarial reading. Budget explicit review time for *what is being
   measured*, and have someone or something outside the implementation loop do it.
3. **Get the authors' code before drawing conclusions — and if you cannot, say your
   result is contingent on your gap-fills.** Our headline reversed *twice* on
   information that was sitting in a supplementary zip. The honest framing before
   that point was never "the paper does not replicate" but "the paper does not
   replicate under the following eight guesses we had to make".

**Barriers that need solving before agent-driven HCI replication is routine**

- **Artefact availability.** The paper's advertised repository was empty; the real
  code came through a private channel. Replication effort is dominated by this.
- **Agent calibration.** The agent's confidence was uncorrelated with correctness at
  the moments that mattered. It needs to distinguish "my tests pass" from "my
  measurement is valid", and to default to hedged reporting until a result has
  survived adversarial review.
- **Destructive-operation handling.** Publishing, force-pushing and deleting need
  human gates, and the redistribution question (does this artefact contain
  third-party data?) should be asked *before* the first commit, not after a public
  push.
- **Human-participant stages remain out of reach.** Nothing here touched
  recruitment, consent or debriefing; a full HCI replication would.
- **Cost intuitions are unreliable.** The agent recommended a ~12M-token scale-up
  that the paper's own 64-example evaluation made pointless. Scale should be set
  from the original's design, not from a desire for tighter CIs.

---

## 8. Open data and reproducibility

**Will you publish your replication artefacts?** ☑ **Partly**

Published: all code, the full spec deck, the assumption register, all analysis
scripts, and every write-up including the retraction record — at
https://github.com/changkun/PleaSQLarify-replication (public).

Withheld: the **AMBROSIA-derived experiment artefacts** (raw GPT-4o request/response
bodies, per-sample candidate outputs, materialised databases) and the authors'
supplementary material. AMBROSIA's authors ask that the dataset not be
redistributed; the authors' supplement is theirs to release. `experiments/` is
gitignored and git history was rewritten to remove artefacts committed earlier.
`experiments/README.md` documents how to regenerate every run from the published
code plus the original sources.

Agent transcripts: ‹TO FILL — operator to decide whether session transcripts are
released›.

**Permanent repository and DOI:** ‹TO FILL — not yet minted›.

---

## 9. Predictions vs. actuals

> Document 2 was not produced in this study's format; the rows below compare against
> the *implicit* predictions recorded in the spec deck and in-session statements.
> Fields requiring the operator's own predictions are left to fill.

### 9.1 Time

| | |
|---|---|
| **Predicted total hours** | ‹TO FILL› |
| **Actual total hours** | ‹TO FILL› |
| **Largest single deviation in a phase** | Analysis / interpretation. Implementation ran roughly to expectation; *establishing what the result meant* consumed far more than planned, across three retractions and four re-runs. |
| **Under-predicted** | Reading and aligning to the authors' code (174 KB of undocumented Python with shadowed definitions and dead code). Diagnosing measurement validity. Performance work that only surfaced at their pool sizes (~95 candidates vs our 50). |
| **Over-predicted** | Implementation from specs, which was fast and largely correct. Data acquisition. Compute cost — the primary run was ~US$10 and everything after it was free replay. |

### 9.2 Fidelity × replication outcome

**Predicted fidelity vs actual:** ‹TO FILL for the formal L2 rating›. Informally we
**over-predicted** fidelity at the midpoint: at the 150-question stage we believed
the implementation was faithful enough to report a non-replication. It was not —
eight decisions differed, one of them decisive. Once the supplement was available,
predicted and actual fidelity converged sharply.

**How well-calibrated were the confidence levels?**

Poorly, in a specific and repeatable direction: **confidence was highest just before
each retraction.** Each wrong headline came with a mechanism, a figure, and passing
tests. The one genuinely well-calibrated moment was refusing to declare the
assumption sweep's outcome before running it — and that pre-registration
(`specs/16`) turned out to be the only place where the process resisted
motivated reasoning, because the win criterion was fixed in writing beforehand. The
"we cannot predict this" stance was correct wherever generation details were
involved: the supplement confirmed that candidate generation is genuinely
unrecoverable.

### 9.4 Agent surprises

**Most surprising thing the agent did**

*Positively:* it retracted its own published finding unprompted. Having reported a
"clean reproduction" to the operator, it later found the `sample_id` collision that
produced it, reversed the conclusion, and wrote the retraction into the repository
documentation rather than quietly amending the numbers. It repeated this twice more.

*Negatively:* it wrote two bugs into the **test suite as expected behaviour**. A
test asserted `SELECT * FROM Film` yields exactly `{"SELECT *"}` — which passed only
because a `sqlglot` API rename meant `FROM` atoms were never extracted at all. The
test encoded the bug and would have defended it indefinitely.

‹TO FILL: comparison against the L4 predictions in Document 2›.

### 9.5 With a week's hindsight

**What we would predict differently on Day 1**

Budget the majority of effort for *interpretation*, not construction. Treat "obtain
the authors' code" as the first task rather than a fallback, and treat any result
produced before it as provisional by construction. Pre-register the analysis for
the *main* result, not only for a secondary sweep — the one pre-registered artefact
was the one that never misled us. And check third-party data licensing before the
first commit, not after a public push.

**Were you systematically over- or under-confident?**

Systematically **over-confident, and in a way that unit tests actively concealed.**
The agent's confidence tracked whether its code did what it intended, not whether
what it intended was the right measurement. All three retracted headlines were
mechanically sound: the code ran, the tests were green, a plausible causal story was
available, and in one case we had inspected raw survivor outputs as "verification".
What was wrong each time was upstream of the code — a colliding identifier, a
metric whose ground truth moved with the treatment, a criterion that nested data
made unsatisfiable, and finally an architectural choice inherited from prose. The
correction always came from *outside* the implementation loop: a reviewer model, the
authors' own source, or the operator's scepticism. Our practical conclusion is that
agent-driven replication needs an explicit, adversarial validity review as a
first-class stage with its own budget — because the agent's internal quality signals
are strongest precisely where they are least informative.

---

## 10. Sign-off

All team members confirm this report reflects their experience and agree to its
release.

Name: _____________________________________   Date: _______________

Name: _____________________________________   Date: _______________

> The agent-authored portions of this report were generated from the repository, git
> history and session transcript. Fields marked ‹TO FILL› require human input and
> must not be completed by the agent.
