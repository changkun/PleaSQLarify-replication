---
title: "Visual Interface — Predicted Query and Predicted Output Views"
status: drafted
depends_on:
  - interface/11-backend-api.md
  - algorithm/05-atomic-feature-extraction.md
  - algorithm/06-decision-variables.md
affects:
  - src/pleasqlarify/server/views/predicted_query.py
  - frontend/src/views/PredictedQuery.*
  - frontend/src/views/PredictedOutput.*
effort: medium
created: 2026-07-01
updated: 2026-07-01
author: changkun
dispatched_task_id: null
---

# Visual Interface — Predicted Query and Predicted Output Views

## Overview

The **Predicted Query** (Figure 6, panel 4) and **Predicted Output** (Figure 6,
panel 5) are the two right-hand / bottom views of the interface. Together they
answer the question *"given my decisions so far, what will the final query look
like and what will it return?"* The Predicted Query surfaces the **provenance of
decisions**: it lists the atomic features (spec 05) that are likely to appear in
the final query, each with a probability computed from the current query sample
(spec 06), and lets the user make the same binary Yes/No decisions at the
**clause level** (workflow W2). The Predicted Output shows the **result table**
that executing the current most-probable query would produce, supporting data
exploration and confirmation.

Both are views over one `SessionState` (spec 02) and share the backend
`/predicted_query` endpoint (spec 11). Like the other panels, they are
**interlinked**: hovering or deciding here updates the Action Space (spec 12) and
Decision Space (spec 13), and vice-versa (Figure 8).

## Paper grounding

- **Interface layout.** "The visual interactive interface consists of the user's
  input/utterance field (1), three main analysis views, i.e., the *Action Space*
  (2), *Decision Space* (3) for decision making, and *Predicted Query* (4) for
  confirmation tasks, and the *Predicted Output* view (5) showing the predicted
  result of the database." (Figure 6 caption, p. 8).
- **Provenance goal.** "The goal of the *Predicted Query* is to support the
  provenance of the decisions made. The users are informed about their made
  decisions and the likely atomic features that will be included in the final
  query." (p. 10). Also: "the *Predicted Query* supports the provenance of the
  decisions made … this view provides an overview of the most probable atomic
  features in the final query, conditioned on the user's decisions." (p. 9,
  Design Rationale).
- **Query Visualization (shared encoding).** "a query has two types of
  representation … by default, the query is visualized as a list of atomic
  features, where a feature is built from a keyword (a span with a black
  background, e.g., `SELECT`) and a value (a span with a light gray background,
  e.g., `Opinion`)." (p. 9). "the atomic features are visualized in the same way
  as in the other two panels." (p. 10).
- **Likely-but-unconfirmed border.** "Unlike other panels, the atomic features
  that are considered likely but remain unconfirmed by the user are indicated
  with a surrounding border." (p. 10).
- **Probability from the current sample.** "The likelihood of atomic features is
  computed based on the current query sample displayed in the *Action Space*.
  Every time a new query sample is created, by selecting queries in the *Action
  Space* or decision variables in the *Decision Space*, the atomic features are
  filtered (probability > 0) and their probabilities updated." (p. 10). Each
  feature row shows a percentage (Figure 6: `SELECT Opinion` 66%, `SELECT
  AudienceReviews` 41%, `SELECT DISTINCT Opinion` 15%, `FROM Reviews` 100%
  `determined`).
- **Determined marker.** "In case a feature has a 100% probability to be part of
  the final query, it is marked as *determined*." (Figure 9 caption, p. 11; also
  Figure 6, `FROM Reviews 100% determined`).
- **Linking-and-brushing + clause-level decisions (W2).** "we apply a
  linking-and-brushing method similar to that in the *Decision Space*. The user
  can hover over an atomic feature, and all queries containing the feature will
  be highlighted in the *Action Space*. Furthermore, the user can make the same
  binary decisions by clicking on 'Yes' or 'No' buttons for the *Action Space*.
  New decision variables will be computed based on the new query sample and
  listed in the *Decision Space*, atomic features will be filtered, and their
  probabilities updated in this panel." (p. 10). Figure 8 marker 3 shows the
  Predicted Query being updated ("filter") when a decision is accepted.
- **Every decision reduces the feature list; Back reverses.** "Every time a
  decision is made by the user (1), the number of atomic features in the
  *Predicted Query* is reduced. In particular, the features are retained only if
  they are included in the filtered queries. We color the selected decision
  variables and update the probabilities for the remaining ones. In case a
  feature has a 100% probability … it is marked as *determined*. Every decision
  made can be reversed by clicking on the *Back* button displayed in the
  *Decision Space* (2)." (Figure 9 caption, p. 11). Note the **Back button
  physically sits in the Decision Space panel** (spec 13), not this view.
- **Predicted Output.** "the *Predicted Output* view (5) showing the predicted
  result of the database." (Figure 6 caption, p. 8). "the bottom of the page
  displays the intermediate predicted results table." (p. 9, Design Rationale).
  Figure 6 shows a table with columns `Opinion` / `AudienceReviews` and sample
  rows (`A masterpiece.` / `Five stars!`, `Terrific acting.` / `Audience loved
  it!`).

## Architecture

```mermaid
graph TD
  subgraph Backend
    SAMP["Current filtered sample M_t / candidates (spec 08)"]
    CO["Co-occurrence over current sample<br/>p(atom | selections) = #(atom ∈ filtered) / #filtered  (spec 06, Eq 6)"]
    FL["Feature list: prob% + state ∈ {determined, likely, present}"]
    MPQ["Most-probable query:<br/>argmax belief p_t(m) → cluster representative (spec 02)"]
    EXE["Execute query on DB → ResultTable (spec 01/04)"]
    SAMP --> CO --> FL
    SAMP --> MPQ --> EXE
  end
  subgraph Frontend
    PQ["Predicted Query panel:<br/>keyword/value spans + border/percent + Yes/No"]
    PO["Predicted Output panel:<br/>result-table renderer"]
  end
  FL -->|/predicted_query| PQ
  EXE -->|/predicted_query| PO
  PQ -->|clause-level Yes/No → /answer<br/>single-atom decision var| SAMP
  PQ -->|hover feature| HL["highlight in Action Space (spec 12)"]
  PQ -.->|Back (control in Decision Space) → /undo| SAMP
```

## Components

### Server payload (`GET /session/{id}/predicted_query`, spec 11)

File: `src/pleasqlarify/server/views/predicted_query.py`. Builds the payload from
the current `SessionState` (spec 02). No new algorithm logic — it reuses spec 06's
co-occurrence over the **current filtered candidate set**.

```
PredictedFeatureRow:
  atom_index: int              # dimension in z (spec 02 AtomicFeature.index)
  keyword: str                 # black-background span, e.g. "SELECT", "FROM", "WHERE"
  value: str                   # light-gray span, e.g. "Opinion", "Reviews"
  probability: float           # p(atom | current selections), 0 < p ≤ 1 (see below)
  state: enum { determined,    # probability == 1  → "determined" marker, no Yes/No
                likely,        # 0 < probability < 1, unconfirmed → surrounding border
                present }       # user-confirmed via a prior Yes decision (provenance)
  decision_variable_id: str    # the single-atom decision var this row maps to (A-pq-1)

PredictedQueryView:
  features: list[PredictedFeatureRow]   # only atoms with probability > 0 (p.10)
  output: ResultTable                    # predicted output of the most-probable query
```

- **Feature list.** One row per atom `i` present in at least one query of the
  current filtered sample (`probability > 0`, p. 10). Each row renders as a
  keyword span + value span exactly like spec 12/13 (shared `AtomicFeature.kind`
  → keyword, `payload` → value; spec 05). Rows carry the co-occurrence
  probability and the `{determined, likely, present}` state.
- **Probability = co-occurrence over the current sample.** For the current
  filtered candidate set `S` (⊆ `A`, induced by all selections so far),
  `probability(atom) = #{a ∈ S : z_atom(a) = 1} / |S|`. This is spec 06's Eq 6
  `p(z_Z = 1 | z_g = 1)` evaluated with `g` = "the current selections" and the
  conditioning set restricted to `S` — i.e. the paper's "computed based on the
  current query sample displayed in the Action Space" (p. 10). Test math must
  compute over `S`, **not** Eq 6 over the full `A`.
- **`state` derivation.** `determined` when `probability ≥ 1 - ε` (spec 06 A8d,
  `ε ≈ 1e-3`); `likely` when `0 < probability < 1` and the atom has not been
  explicitly confirmed; `present` when the atom was fixed by a prior Yes decision
  in `history` (spec 02). See A-pq-3 — the `present` tier is inferred, not spelled
  out by the paper.
- **Predicted output.** The `ResultTable` (spec 01) obtained by executing the
  **most-probable query** on the database `C`. See A-pq-2 for how that query is
  chosen (default: `argmax p_t(m)` → cluster `representative_id` → execute).

### Frontend — Predicted Query panel

File: `frontend/src/views/PredictedQuery.*`. Renders `features` top-to-bottom
(Figure 6). Each row:
- keyword span (black background) + value span (light gray background) — shared
  query-visualization component (p. 9);
- `likely` rows get a **surrounding border** (p. 10); `present` rows are colored
  like the selected/confirmed decision variables (Figure 9, "we color the
  selected decision variables");
- a **percentage** badge (e.g. `66%`);
- **`Yes` / `No`** buttons for `likely` rows (clause-level decision, W2);
  `determined` rows show the **`determined`** marker **instead of** Yes/No
  (Figures 6, 9).
- hovering a row triggers linking-and-brushing (highlight in Action Space).

### Frontend — Predicted Output panel

File: `frontend/src/views/PredictedOutput.*`. A plain result-table renderer for
the `output` `ResultTable`: header row of column names, data rows (Figure 6:
`Opinion` / `AudienceReviews`). Truncated for display (A-pq-4). Supports data
exploration/confirmation (p. 8, p. 9).

## Interactions

| Gesture | Effect | Backend call |
|---|---|---|
| Hover an atomic-feature row | All queries containing that atom highlight in the Action Space (linking-and-brushing) | none (client-side highlight over cached Action-Space payload); or `GET /predicted_query` re-fetch if needed |
| Click **Yes** on a `likely` feature (keep) | Filter to queries that **contain** the atom; recompute decision variables + probabilities; feature list shrinks | `POST /answer` with `{variable_id: <single-atom var>, value: true}` (spec 11; A-pq-1) |
| Click **No** on a `likely` feature (exclude) | Filter to queries that **exclude** the atom; recompute | `POST /answer` with `{variable_id: <single-atom var>, value: false}` |
| Click **Back** (button lives in Decision Space, spec 13) | Reverse the last decision; feature list grows back to prior turn | `POST /undo` (spec 11) |
| (Linked) accept/reject in Decision Space or select in Action Space | This panel's feature list is re-filtered and probabilities updated; predicted output re-executed | driven by the other views' `/answer` / `/select`; refreshed via returned `StateView` |

Every mutating call returns the full `StateView` (spec 11, A-be-2), so this panel
and the Predicted Output refresh together with the other two views.

## Core Assumptions & Undocumented Decisions

- **A-pq-1 — Clause-level Yes/No → backend mapping.** The paper lets the user
  "make the same binary decisions" on an atomic feature here (p. 10), but spec 11
  `/answer` takes a `{variable_id, value}` for a *decision variable*, and most
  displayed atoms are not in the ranked Decision-Space list. **Gap:** how does
  clicking Yes on `SELECT Opinion` reach the backend?
  - *Recommended default:* treat each atomic-feature row as a **single-atom
    decision variable** (`|g| = 1` — exactly spec 06 A8c's "atomic variant"),
    with a stable `decision_variable_id`. Yes/No then POSTs to `/answer` and flows
    through the same `apply_answer` / `history` / `undo` path uniformly, so
    clause-level (W2) and Decision-Space navigation are one code path.
  - *Alternatives:* (a) a dedicated `/select`-style feature filter endpoint
    (`{atom_index, keep}`) that filters candidates directly without minting a
    decision variable (diverges from the unified answer/undo history);
    (b) restrict Yes/No to atoms that happen to already be decision variables
    (contradicts p. 10 "the same binary decisions" on any feature). Flagged: this
    defines what a clause-level decision *is*.
- **A-pq-2 — Choice of the "most probable query" for Predicted Output.** The
  paper says the panel shows "the predicted result of the database" (p. 8) for the
  current query but never names which single query.
  - *Recommended default:* `argmax_m p_t(m)` (highest-belief intent/cluster,
    spec 02 `Belief`) → that cluster's `representative_id` (spec 02) → execute on
    `C` → `ResultTable`. Ties broken by lowest cluster id for determinism.
  - *Alternatives:* (a) the candidate with the highest `gen_count` in the current
    sample (most-sampled ≈ most probable under the LLM prior); (b) a cluster
    centroid / medoid by functional distance (spec 04). All fields exist in
    spec 02. Flagged.
- **A-pq-3 — Tri-state feature semantics `{determined, likely, present}`.** The
  paper gives two tiers cleanly: `determined` = 100% (Figure 9, p. 11) and
  `likely` = 0<p<1 with a surrounding border (p. 10). The **`present`** tier
  (an atom fixed by a prior explicit Yes decision — the "provenance of decisions
  made", p. 10) is inferred to distinguish user-confirmed atoms (colored like
  selected decision variables, Figure 9) from merely-likely ones.
  - *Recommended default:* three tiers as above; `present` colored, `likely`
    bordered, `determined` marked. A `determined` atom that was *also* explicitly
    confirmed is shown as `determined` (the stronger, terminal state).
  - *Alternative:* collapse `present` into `determined` (only two tiers,
    strictly paper-literal) — loses the visual distinction between "you decided
    this" and "the sample forced this to 100%". Flagged as inferred.
- **A-pq-4 — Feature-list ordering.** The paper does not state the row order.
  Figure 6 shows `SELECT` rows grouped together, then `FROM`, then `JOIN`,
  suggesting **clause order**.
  - *Recommended default:* order by clause (`SELECT` → `FROM` → `JOIN` → `WHERE`
    → `GROUP BY` → `HAVING` → `ORDER BY` → `LIMIT`, matching spec 05's `kind`
    taxonomy), then by descending probability within a clause (reads like a real
    query, groups related atoms — Figure 6).
  - *Alternative:* pure descending probability (surfaces the most-likely atoms
    first regardless of clause; less query-like). Flagged.
- **A-pq-5 — Probability shown for a not-yet-decided feature.** Resolved by the
  probability definition above: it is the co-occurrence marginal over the
  **current filtered sample** `S`, i.e. `p(atom | selections so far)` — not Eq 6
  over the full `A`. Recorded here to prevent the common mis-implementation of
  computing against `A`.
- **A-pq-6 — Predicted-output truncation for display.** The DB result may be
  large; the paper's figure shows only a few rows.
  - *Recommended default:* return at most `N_rows = 50` rows and all columns in
    the `ResultTable`, with a `truncated: bool` + `total_rows` field so the UI can
    indicate "showing 50 of K". *Alternatives:* paginate; cap columns too. Flagged.

## Testing Strategy

- **Feature probabilities match co-occurrence over the current sample.** On a
  hand-built `SessionState` fixture with a known filtered set `S`, assert each
  `PredictedFeatureRow.probability` equals `#{a ∈ S : z_atom(a)=1} / |S|`
  (spec 06 Eq 6 over `S`, A-pq-5). Include a zero-probability atom and assert it
  is **absent** from `features` (probability > 0 filter, p. 10).
- **Determined flag at prob = 1.** An atom present in every query of `S` has
  `probability = 1`, `state = determined`, and its row exposes the `determined`
  marker and **no** Yes/No buttons (Figures 6, 9).
- **Likely border at 0<p<1.** An atom present in some but not all of `S` has
  `state = likely` and is marked bordered with Yes/No buttons.
- **Clause-level Yes updates state like a Decision-Space answer.** POSTing a Yes
  on a feature (single-atom variable, A-pq-1) produces the *same* resulting
  `SessionState` (surviving set, belief, history length) as answering the
  equivalent decision variable in the Decision Space — the unified-path property.
- **Predicted output equals executing the chosen query.** `output` equals the
  `ResultTable` from executing the `argmax p_t(m)` cluster's representative query
  on the fixture DB (A-pq-2), truncated per A-pq-6.
- **Feature count is non-increasing across turns.** For a sequence of decisions,
  `len(features)` at turn `t+1` ≤ turn `t` (Figure 9); `undo` restores the prior
  count exactly.
- **Linked-view consistency.** After a clause-level Yes, the returned `StateView`
  has the same `turn` and surviving set as the Action Space and Decision Space
  payloads (spec 11 linked-views property).

## Acceptance Criteria

1. `GET /session/{id}/predicted_query` returns `features` (only atoms with
   probability > 0), each with `keyword`/`value` spans, a co-occurrence
   `probability` over the current filtered sample, and a `state ∈ {determined,
   likely, present}`, plus a predicted-output `ResultTable`.
2. Atoms at probability 1 are flagged `determined` (marker, no Yes/No); atoms at
   0<p<1 are `likely` (surrounding border, Yes/No); confirmed atoms are `present`
   (colored). (p. 10, p. 11 Figure 9.)
3. Clicking Yes/No on a feature routes to `POST /answer` as a single-atom
   decision variable (A-pq-1) and yields the same state transition as the
   equivalent Decision-Space answer; Back routes to `POST /undo`.
4. Hovering a feature highlights all queries containing it in the Action Space
   (linking-and-brushing, p. 10).
5. The Predicted Output renders the `ResultTable` of the most-probable query
   (A-pq-2), truncated per A-pq-6.
6. The feature count is non-increasing across decisions and exactly restored by
   undo (Figure 9).
7. Assumptions A-pq-1..A-pq-6 are recorded with defaults, alternatives, and the
   paper text they rest on.
