"""Experiment log: every backtest you care about gets written down automatically.

Usage
    python -m powerhours.experiment run --name "baseline" --days 180 --notes "first run"
    python -m powerhours.experiment list

Each run appends one line per model to experiments/log.jsonl, with the date, the git
commit, the test period, the feature list and the scores. Commit that file: it is the
honest history of what you tried, including what did not work.

Why not MLflow? This does the one thing needed here in 100 lines you can read.
Swapping in MLflow later is a reasonable roadmap item.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from powerhours.backtest import backtest, summarize
from powerhours.config import DEFAULT_ZONE, ZONES
from powerhours.features import load_features
from powerhours.models import MODELS

LOG_PATH = Path(__file__).resolve().parents[2] / "experiments" / "log.jsonl"


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).parent,
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def run_experiment(
    name: str,
    zone: str = DEFAULT_ZONE,
    days: int = 180,
    duration: int = 2,
    notes: str = "",
    models: dict | None = None,
    features: pd.DataFrame | None = None,
    log_path: Path | None = None,
) -> pd.DataFrame:
    """Backtest `models` (default: all registered), log the scores, return the summary."""
    models = models or MODELS
    features = features if features is not None else load_features(zone)
    predictions = backtest(features, test_days=days, models=models)
    summary = summarize(predictions, duration=duration)

    log_path = log_path or LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    common = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "name": name,
        "notes": notes,
        "commit": git_commit(),
        "zone": zone,
        "test_from": str(predictions["date"].min().date()),
        "test_to": str(predictions["date"].max().date()),
        "window_hours": duration,
    }
    with log_path.open("a", encoding="utf-8") as handle:
        for model, row in summary.iterrows():
            record = {
                **common,
                "model": model,
                "features": models[model]().features,
                **{key: round(float(value), 4) for key, value in row.items()},
            }
            handle.write(json.dumps(record) + "\n")
    return summary


def read_log(log_path: Path | None = None) -> pd.DataFrame:
    """All logged runs as a table, newest first."""
    log_path = log_path or LOG_PATH
    if not log_path.exists():
        return pd.DataFrame()
    records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    return pd.DataFrame(records).sort_values(["run_at", "mae"], ascending=[False, True])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run and list logged experiments.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--name", required=True, help="short label, e.g. 'add holidays'")
    run.add_argument("--notes", default="", help="what you changed and what you expect")
    run.add_argument("--zone", default=DEFAULT_ZONE, choices=list(ZONES))
    run.add_argument("--days", type=int, default=180)
    run.add_argument("--duration", type=int, default=2)
    sub.add_parser("list")
    args = parser.parse_args(argv)

    if args.command == "run":
        summary = run_experiment(args.name, args.zone, args.days, args.duration, args.notes)
        print(f"\nExperiment '{args.name}': {args.zone}, last {args.days} days\n")
        print(summary.round(3).to_string())
    else:
        log = read_log()
        if log.empty:
            print("No experiments logged yet.")
            return
        columns = ["run_at", "name", "model", "mae", "skill_vs_naive", "window_regret", "test_from"]
        print(log[columns].to_string(index=False))


if __name__ == "__main__":
    main()
