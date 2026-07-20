# Experiment runs (not versioned)

Runs live here as `experiments/<run_id>/` and are **deliberately excluded from git**.
Their artifacts embed AMBROSIA-derived content — the ambiguous questions, the gold
queries, and executed database outputs — and AMBROSIA's authors ask that the
dataset not be redistributed (see [`NOTICE.md`](NOTICE.md)). Only this file and
`NOTICE.md` are tracked.

Nothing is lost: every run is reproducible from the committed code plus the inputs
below.

## What a run contains

```
experiments/<run_id>/
  config.json                          run parameters
  manifest.json                        samples, counts, token totals
  run.log
  llm/<model>/<sample_id>/
    call_0000.json                     FULL request + response body per LLM call
    completions.json                   aggregated raw completions
  samples/<sample_id>/
    sample.json                        utterance, ambiguity type, db, gold queries
    candidates.json                    parsed candidates: sql, gen_count, atoms, output
    vocabulary.json                    the atomic-feature vocabulary
    similarity_matrix.npy              functional output-similarity matrix S
    clusters.json, gold_assignment.json
    traces/<condition>__gold<i>.json   per-turn interaction trace
  results/
    real_eval_results.csv, aggregate.json, summary.json,
    coverage_by_type.json, figure5.png
```

Layout and scaling guidance: [`../docs/04-experiments.md`](../docs/04-experiments.md).

## Prerequisites

**1. AMBROSIA.** Not on HuggingFace. Download from
[ambrosia-benchmark.github.io](https://ambrosia-benchmark.github.io) (password
`AM8R0S1A`, Edinburgh DataSync), extract locally, and point the loader at it:

```bash
export PLEASQL_AMBROSIA_ROOT=/path/to/ambrosia
```

Keep it out of version control — `data/ambrosia/` is gitignored for this reason.

**2. An OpenAI-compatible endpoint** (only for runs that generate; replaying a
cached run needs none):

```bash
export OPENAI_BASE_URL=...   # e.g. your gateway
export OPENAI_API_KEY=...    # never committed; env-only, and never written to artifacts
```

## Reproduce the runs

```bash
uv venv --python 3.11
uv pip install -e ".[all]"

# the 150-question run reported in docs/ (7,500 GPT-4o calls, ~1.6M tokens)
uv run python scripts/run_experiment.py --model gpt-4o --per-type 50 --n 50 \
    --run-dir experiments/gpt4o_per50_n50

# a small smoke run
uv run python scripts/run_experiment.py --model gpt-4o --per-type 1 --n 6 \
    --run-dir experiments/demo_gpt4o

# fully offline, no API and no downloads
uv run python scripts/run_experiment.py --offline --per-type 1 --n 8
```

Runs resume: re-invoking with the same `--run-dir` reuses cached completions and
only regenerates what is missing or stale (a cached pool whose size no longer
matches `--n` is regenerated rather than silently reused).

## Analyses over a completed run

```bash
# pre-registered A4/A5/A12 assumption sweep — replays cached generations, 0 LLM calls
uv run python scripts/run_sweep.py \
    --source experiments/gpt4o_per50_n50 --out experiments/sweep_a4a5a12
```

## The authors' own pools

The authors' supplementary material ships their precomputed generation pools
(`27154505_diverse_sql_output.jsonl`: 300 questions, ~95 candidates each). Running
against those removes candidate generation as a confound and costs no API calls.
It is not redistributed here either — obtain it from the authors' supplement. See
[`../specs/evaluation/17-authors-supplement.md`](../specs/evaluation/17-authors-supplement.md).

## Provenance note

No credentials are ever stored in artifacts: the API key is read from the
environment and never written. Captured request bodies do include the configured
`base_url`, which is an endpoint address, not a secret.
