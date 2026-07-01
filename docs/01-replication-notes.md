# Replication Notes

How this replication of *PleaSQLarify* (Chan, Sevastjanova, El-Assady, CHI '26)
was produced, what it covers, and how to reproduce it.

## Method: spec-first, then implement

1. **Read the paper** (`specs/paper.pdf`) end to end.
2. **Wrote a dependency-ordered spec deck** (`specs/`, 15 specs) that reconstructs
   the system from the paper. Every decision the paper leaves unstated is captured
   in a per-spec *Core Assumptions & Undocumented Decisions* section with a
   recommended default, alternatives, and what the paper implies. This is
   deliberate: the paper is dense with formalism (RSA priors, lift, co-occurrence,
   information gain) but sparse on implementation mechanics.
3. **Implemented specs 01–14** in `src/pleasqlarify/`, one module per spec step,
   against a shared data model (`model/types.py`).
4. **Tested offline first** (deterministic mock LLM + fixture SQLite + hashing
   embedder), then **validated with the real backends** (GPT-4o, `all-MiniLM-L6-v2`,
   UMAP) on the real AMBROSIA benchmark.

## What is replicated

| Paper artifact | Status |
|---|---|
| §5–6 pragmatic-repair algorithm (generate → cluster → atoms → decision vars → info gain → loop) | implemented + tested |
| §7 quantitative evaluation (Figure 5: entropy + similarity per turn, bootstrap CIs) | implemented + **run on real AMBROSIA + GPT-4o + MiniLM**; the paper's clustering advantage does **not** cleanly reproduce at this scale — honest analysis in `02-execution-results.md` |
| §8 visual interface (Action/Decision/Predicted views) | implemented (FastAPI + browser SPA) |
| §9 user study | protocol reproduced as an executable spec (`specs/study/15`), not run |

## Real backends

All three fidelity backends the paper names are wired and were exercised:

- **Generation:** GPT-4o via an OpenAI-compatible endpoint (`OpenAIClient`,
  configured through `OPENAI_BASE_URL`/`OPENAI_API_KEY`). Sampled `N` times at
  temperature 0.7 (the paper's setting), invalid parses dropped, identical
  generations collapsed with a count.
- **Output embeddings:** `sentence-transformers/all-MiniLM-L6-v2` (`MiniLMEmbedder`),
  the exact model in the paper, used to build the functional-similarity matrix `S`.
- **Projection:** UMAP on the precomputed distance matrix `1 − S` for the Action
  Space (`umap_project`).

Offline, deterministic fallbacks stand in for each (hashing embedder, classical
MDS, mock/cached LLM) so the full pipeline and 52 tests run with no network.

## Key deviations from the paper (all documented)

- **Parser:** the paper uses the Spider `process_sql` parser; we use **sqlglot**
  (maintained, pip-installable, richer AST + column qualifier). The extracted
  atoms — clause elements — are equivalent. See `specs/algorithm/05`.
- **AMBROSIA source:** the paper cites AMBROSIA but gives no download details. It
  is **not on HuggingFace**; it is a password-protected direct download whose
  authors ask that it not be redistributed, so it is kept out of version control
  and read from a local extraction (`PLEASQL_AMBROSIA_ROOT`). See `specs/foundations/01`.
- Every other undocumented decision is logged in `03-findings-and-decisions.md`.

## Reproduce

```bash
uv venv --python 3.11
uv pip install -e ".[dev]"          # offline core + tests
uv run pytest                        # 52 passing, 3 real-backend tests skipped

# real backends + real data
uv pip install -e ".[real]"
# download AMBROSIA to data/ambrosia/ (see specs/foundations/01)
export OPENAI_BASE_URL=... OPENAI_API_KEY=...
uv run python scripts/run_real_eval.py --per-type 5 --n 50 --max-turns 10
PLEASQL_RUN_REAL=1 uv run pytest tests/test_real_backends.py
```
