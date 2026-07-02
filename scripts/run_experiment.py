"""Run a fully-provenanced, scalable experiment.

Each run is written to its own partitioned folder under experiments/, capturing
every LLM request/response body and every intermediate result. Example:

    OPENAI_BASE_URL=... OPENAI_API_KEY=... \
    uv run python scripts/run_experiment.py --model gpt-4o --per-type 5 --n 50

Offline dry run (no API, deterministic embedder):

    uv run python scripts/run_experiment.py --offline --per-type 1 --n 8
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from pleasqlarify.experiment.runner import ExperimentConfig, run_experiment


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-4o")
    ap.add_argument("--per-type", type=int, default=5)
    ap.add_argument("--domain", default=None)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--max-turns", type=int, default=10)
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--gold-k", action="store_true")
    ap.add_argument("--real-embedder", dest="real_embedder", action="store_true", default=True)
    ap.add_argument("--hash-embedder", dest="real_embedder", action="store_false")
    ap.add_argument("--offline", action="store_true", help="use a demo mock LLM, no API")
    ap.add_argument("--no-resume", dest="resume", action="store_false", default=True)
    ap.add_argument("--run-dir", default=None)
    args = ap.parse_args()

    config = ExperimentConfig(
        model="mock" if args.offline else args.model,
        per_type=args.per_type,
        domain=args.domain,
        n=args.n,
        temperature=args.temperature,
        max_turns=args.max_turns,
        threads=args.threads,
        gold_k=args.gold_k,
        real_embedder=(False if args.offline else args.real_embedder),
        resume=args.resume,
    )

    if args.run_dir:
        run_dir = args.run_dir
    else:
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = str(
            Path("experiments") / f"{config.model}__n{config.n}__per{config.per_type}__{stamp}"
        )

    live_client_factory = None
    if args.offline:
        from pleasqlarify.data.demo import DEMO_COMPLETIONS
        from pleasqlarify.llm.client import MockLLMClient

        live_client_factory = lambda: MockLLMClient(DEMO_COMPLETIONS)  # noqa: E731

    print(f"run dir: {run_dir}")
    run_experiment(config, run_dir, live_client_factory=live_client_factory)
    print(f"artifacts written to {run_dir}")


if __name__ == "__main__":
    main()
