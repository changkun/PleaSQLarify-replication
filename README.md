# PleaSQLarify (replication)

A spec-driven replication of **PleaSQLarify: Visual Pragmatic Repair for Natural
Language Database Querying** (Chan, Sevastjanova, El-Assady; CHI '26).

The paper reframes text-to-SQL ambiguity as *pragmatic repair*: instead of
collapsing an underspecified question into one query, the system samples the
LLM's probable interpretations, clusters them by what they actually return,
surfaces the most *informative* clarification, and narrows to the user's intent
over a few turns.

This repository contains:

- **`specs/`** — a dependency-ordered deck of specs (01→15) that reconstruct the
  system from the paper, with every undocumented implementation decision flagged.
  Start at [`specs/README.md`](specs/README.md).
- **`src/pleasqlarify/`** — the implementation of the Section 5–6 algorithm, the
  Section 7 evaluation, and the Section 8 interface.
- **`tests/`** — an offline, deterministic test suite.

## Design for offline reproducibility

The paper's fidelity backends (GPT-4o generation, `all-MiniLM-L6-v2` embeddings,
UMAP projection, the AMBROSIA dataset) are **optional extras**. The core pipeline
and the entire test suite run with no network and no model downloads, via
deterministic fallbacks behind stable interfaces:

| Concern | Paper backend (extra) | Offline default |
|---|---|---|
| Candidate generation | GPT-4o (`llm`) | `MockLLMClient` / `CachedLLMClient` |
| Output embeddings | `all-MiniLM-L6-v2` (`embeddings`) | `DeterministicEmbedder` (hashing) |
| 2-D projection | UMAP (`projection`) | classical MDS (numpy) |
| Dataset | AMBROSIA (`data`) | fixture SQLite DBs in tests |

The SQL AST/atom extraction uses **sqlglot** rather than the paper's Spider
`process_sql` parser — a documented, authorized gap-fill (see
`specs/algorithm/05-atomic-feature-extraction.md`). The produced atoms are the
same clause elements.

## Quickstart

```bash
uv venv --python 3.11
uv pip install -e ".[dev]"        # core + tests, fully offline
uv run pytest                      # run the test suite

# optional: research-fidelity backends
uv pip install -e ".[all]"
```

## Scaling & provenance

`scripts/run_experiment.py` runs the benchmark at any scale and captures **full
provenance** — every LLM request/response body and every intermediate result —
into a partitioned per-run folder (`experiments/<run_id>/`), with resume support.

```bash
export OPENAI_BASE_URL=... OPENAI_API_KEY=...
uv run python scripts/run_experiment.py --model gpt-4o --per-type 5 --n 50
uv run python scripts/run_experiment.py --offline --per-type 1 --n 8   # no network
```

Layout and scaling guidance: [`docs/04-experiments.md`](docs/04-experiments.md).
Runs under `experiments/` are **not versioned** — their artifacts embed
AMBROSIA-derived content, which its authors ask not be redistributed. They are
fully reproducible from the committed code;
[`experiments/README.md`](experiments/README.md) has the prerequisites and exact
commands. No credentials are ever stored in artifacts (env-only).

## Pipeline (Section 5–6)

```
utterance ─▶ 1. generate (LLM)        specs/algorithm/03
          ─▶ 2. execute + cluster     specs/algorithm/04
          ─▶ 3. atomic features       specs/algorithm/05
          ─▶ 3. decision variables    specs/algorithm/06   (lift, co-occurrence)
          ─▶ 4. info-gain ranking     specs/algorithm/07
          ─▶ 5. filter + recluster    specs/algorithm/08   (until 1 intent)
```

```python
from pleasqlarify.session import build_session
from pleasqlarify.llm.client import OpenAIClient  # or MockLLMClient

s = build_session(utterance, schema, db_path, OpenAIClient())
while not s.terminated:
    v = s.next_variable()
    s.answer(v.id, value=True)      # user says yes/no
print(s.final_query().sql)
```

## Replication result

**The paper's central claim reproduces.** On the authors' own candidate pools, with
their sample filter and their configuration, functional clustering + expected
information gain resolves more ambiguity than EIG alone (reach-zero **0.994** vs
**0.981**, and lower entropy at every early turn). The greedy Max-Prob-First
baseline is catastrophic (0.068), as the paper argues.

**One component does not reproduce:** *feature grouping*. Their own logs make
`CLUSTER_GROUP` their strongest condition; we find it level with the plain baseline.

Full numbers and caveats: [`docs/05-authors-pools-rerun.md`](docs/05-authors-pools-rerun.md).

### How we got there (and what we got wrong)

This replication produced **three successive headlines that were wrong**, each
corrected by better evidence. That trail is kept deliberately — it is the main
methodological finding.

| Claim | Why it was wrong |
|---|---|
| "Clean reproduction" (15 samples) | a `sample_id` collision made runs overwrite each other |
| "Clustering advantage does not reproduce" (150 samples) | our implementation differed from the authors' in **eight** load-bearing ways, two of them outright bugs |
| "GPT-4o spans ≥2 interpretations in only 9% of questions" | measured with a criterion that nested gold outputs make structurally impossible |

The decisive input was the authors' **supplementary code**, which settles decisions
the paper leaves unstated (A3–A6, A8, A10, A12, A14–A16) — see
[`specs/evaluation/17-authors-supplement.md`](specs/evaluation/17-authors-supplement.md).
Two of the eight differences were bugs in *our* code that our own tests had encoded:
only the first `UNION` branch was visited, and `sqlglot` 30's `from` → `from_` rename
meant `FROM` atoms were never produced at all.

The single change that flipped the result was **A10**: the authors' decision
variables split *candidates* (with a generation-frequency belief), not clusters.
Under cluster partitions, a mined feature group and a single atom induce the same
partition, so grouping was provably inert. Nothing about AMBROSIA, clustering or
the paper was at fault — the architecture was.

### Validation layers

- **Internal consistency** — 161 offline tests, deterministic, no network.
- **Real-backend validation** — GPT-4o, `all-MiniLM-L6-v2`, UMAP, real AMBROSIA;
  a 150-question run (7,500 calls, 1.6M tokens, full provenance).
- **Like-for-like comparison** — the authors' 300 pools + their filter, zero API
  cost, plus their per-turn curves extracted from their own 4.6 GB result log.

## Status

See [`specs/README.md`](specs/README.md) for the spec deck and the consolidated
register of undocumented decisions. The advertised upstream code repo
(`github.com/chanr0/pleasqlarify`) is, as of 2026-07, effectively empty (a
Copilot-generated stub that contradicts the paper), so this replication is
paper-first throughout.
