# NOTICE — experiment artifacts and third-party data

> **Superseded:** runs under `experiments/` are **no longer versioned**. They are
> gitignored and reproduced locally — see [`README.md`](README.md). The warning
> below is retained because the run artifacts still exist in this repository's git
> **history** (they were tracked between commits `1274f61` and the removal commit).
>
> ---

The runs under `experiments/` were versioned in this repository by the project
owner's explicit choice, to preserve full experimental provenance (every LLM
request/response body and every intermediate result).

## Third-party data warning

These artifacts **embed AMBROSIA-derived content**:

- LLM **request** bodies contain AMBROSIA database schemas and the benchmark's
  ambiguous questions (in the prompt).
- `samples/*/` artifacts contain AMBROSIA gold queries, database outputs, and
  derived features.

AMBROSIA (Saparina & Lapata, 2024; https://ambrosia-benchmark.github.io/) is
distributed under CC BY 4.0, and **its authors explicitly ask that the dataset
not be re-uploaded to GitHub or model hubs.** Committing these runs to a **public**
repository redistributes AMBROSIA-derived content and may conflict with that
request. If this repository is or becomes public, consider one of:

- removing `experiments/` from version control (add it back to `.gitignore`), or
- keeping only aggregate `results/` (metrics/figures, no raw bodies), or
- confirming with the AMBROSIA authors.

The raw AMBROSIA dataset itself (`data/ambrosia/`) remains gitignored regardless.

## LLM provenance

Generation used GPT-4o via an OpenAI-compatible endpoint. **No API keys or
endpoint credentials are stored** in these artifacts or anywhere in the repo —
they are provided only via environment variables at run time. Each `call_*.json`
records the request payload and the full response body (id, resolved model, token
usage, content).
