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

## Status

See [`specs/README.md`](specs/README.md) for the spec deck and the consolidated
register of undocumented decisions. The advertised upstream code repo
(`github.com/chanr0/pleasqlarify`) is, as of 2026-07, effectively empty (a
Copilot-generated stub that contradicts the paper), so this replication is
paper-first throughout.
