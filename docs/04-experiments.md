# Experiments: scaling & full provenance

`scripts/run_experiment.py` (backed by `src/pleasqlarify/experiment/`) runs the
five-condition benchmark at any scale while capturing **complete provenance** —
every LLM request/response body and every intermediate pipeline result — into a
**partitioned per-run folder**. Runs never collide and are fully resumable.

## Run it

```bash
# Real GPT-4o + real MiniLM, 5 samples/type, N=50 (the paper's setting)
export OPENAI_BASE_URL=... OPENAI_API_KEY=...
uv run python scripts/run_experiment.py --model gpt-4o --per-type 5 --n 50

# Offline dry run (deterministic mock LLM + hashing embedder, no network)
uv run python scripts/run_experiment.py --offline --per-type 1 --n 8

# A different LLM → its own run folder (swap the model string)
uv run python scripts/run_experiment.py --model gpt-4o-mini --per-type 5 --n 50
```

Key flags: `--per-type N` (samples per ambiguity type; scale here), `--n`
(generations per sample), `--model`, `--domain Filmmaking`, `--gold-k`
(clustering-k = #gold, see spec 04 A5), `--threads` (parallel generation),
`--hash-embedder` (skip MiniLM), `--run-dir PATH`, `--no-resume`.

## Per-run folder layout

```
experiments/<run_id>/                 # e.g. gpt-4o__n50__per5__20260702_101500
  config.json                         # all run parameters
  manifest.json                       # samples, run counts, status
  run.log
  llm/<model>/<sample_id>/
    call_0000.json …                  # FULL request + response body per LLM call
    completions.json                  # aggregated raw completions for the sample
  samples/<sample_id>/
    sample.json                       # utterance, ambiguity type, db, gold queries
    candidates.json                   # parsed candidates: sql, gen_count, z atoms, output
    vocabulary.json                   # the atomic-feature vocabulary
    similarity_matrix.npy             # functional output-similarity matrix S
    clusters.json                     # functional clusters
    gold_assignment.json              # candidate → nearest gold interpretation
    traces/<condition>__gold<gi>.json # per-turn interaction trace
  results/
    real_eval_results.csv             # tidy per-turn (condition,type,sample,gold,turn,entropy,similarity)
    aggregate.json                    # median + 95% bootstrap CI per (condition,type,turn)
    summary.json                      # median entropy by turn per condition
    coverage_by_type.json             # initial-ambiguity coverage per ambiguity type
    figure5.png                       # reproduced Figure 5 for this run
```

### What a captured LLM call looks like (`llm/gpt-4o/<sample>/call_0000.json`)

```json
{
  "index": 0,
  "model": "gpt-4o",
  "base_url": "https://.../openai/v1",
  "request": { "model": "gpt-4o", "temperature": 0.7,
               "messages": [{"role": "user", "content": "You are a text-to-SQL system. …"}] },
  "response": { "id": "chatcmpl-…", "model": "gpt-4o-2024-08-06",
                "usage": {"prompt_tokens": 211, "completion_tokens": 24, "total_tokens": 235},
                "choices": [{"message": {"content": "```sql SELECT … ```"}}] }
}
```

The full OpenAI response body (id, resolved model, token usage, all choices) is
preserved verbatim. Offline clients (mock/cache) write the same shape with a
synthetic body so downstream tooling is uniform.

### What a trace turn contains (`traces/<condition>__gold<gi>.json`)

Each turn records the complete decision state: `entropy`, `similarity`,
`n_surviving`, `n_clusters`, the full `belief` distribution, the `surviving_ids`,
the top ranked decision variables with their information gain, and the `chosen`
variable + `oracle_answer`. This is enough to replay or audit any interaction.

## Scaling

- **Cost/time:** one sample ≈ `N` generation calls. `--threads` parallelizes them
  (the OpenAI SDK client is thread-safe). N=50 × 5/type × 3 types ≈ 750 calls.
- **Resume:** re-running the same `--run-dir` reuses cached `completions.json` per
  sample (logged as `[resume]`), so an interrupted large run continues without
  re-billing the LLM. Use `--no-resume` to force regeneration.
- **Multiple LLMs:** run once per `--model`; each writes its own folder, and the
  `llm/<model>/…` partition means bodies never mix.
- **Whole benchmark:** raise `--per-type` (AMBROSIA has 326 attachment / 450 scope
  / 373 vague ambiguous test questions); `--domain` restricts scope.

## Data handling

`experiments/` is **gitignored**: the request bodies embed AMBROSIA schemas and
questions, and AMBROSIA is not redistributable (see `03-findings-and-decisions.md`
§A2). Keep runs locally; share only aggregate `results/` if needed.
