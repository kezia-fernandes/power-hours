"""A daily plain-language briefing, written by an LLM and checked against the numbers.

Usage
    python -m powerhours.briefing --zone DE-LU

The idea
    1. `build_facts` computes every number from the saved forecast. No LLM involved.
    2. The LLM only turns those facts into three or four friendly sentences.
    3. `check_grounding` verifies the text: every number in it must be one of the facts,
       and the cheapest start time must be mentioned.
    4. If there is no API key, the call fails, or the check fails, a fixed template
       is used instead. The daily job never depends on the LLM.

Every briefing is appended to data/public/briefing/<zone>.jsonl together with the facts
and the check result, so over time you can measure how often the LLM gets it right.

The check is deliberately simple. It catches invented numbers; it does not catch a
sentence that uses the right numbers with the wrong meaning. Improving it is on the roadmap.

Needs the `anthropic` package and the ANTHROPIC_API_KEY environment variable for the
LLM part: pip install -e ".[llm]"
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from powerhours.config import DEFAULT_ZONE, ZONES, data_dir
from powerhours.features import load_features
from powerhours.forecast import latest_forecast, score_forecasts
from powerhours.window import best_window, window_means

DEFAULT_LLM_MODEL = "claude-haiku-5-5"

SYSTEM_PROMPT = """You write a short daily note for people in Germany who want to run \
their washing machine when electricity is cheap and green.

Rules:
- Use ONLY the facts in the JSON you are given. Never add a number that is not in it.
- Copy numbers and times exactly as they appear. Do not round, convert or combine them.
- Always state the cheapest start time.
- 3 to 4 sentences, plain friendly English, no bullet points, no headings, no emojis.
- Prices are wholesale market prices, not what a household pays. Say so briefly.
- These are forecasts. Do not sound certain."""


def _hhmm(hour: int) -> str:
    return f"{hour % 24:02d}:00"


def build_facts(zone: str, duration: int = 2, root=None) -> dict | None:
    """Everything the briefing may say, computed from stored data. None if no forecast."""
    forecast = latest_forecast(zone, root=root)
    if forecast.empty:
        return None
    tz = ZONES[zone].timezone
    local = forecast["ts_utc"].dt.tz_convert(tz)
    hours = local.dt.hour.to_numpy()
    prices = forecast["yhat"].to_numpy()
    means = window_means(prices, duration)
    cheap, pricey = best_window(prices, duration), best_window(prices, duration, largest=True)
    day = local.iloc[0]

    facts = {
        "date": f"{day:%A} {day.day} {day:%B}",
        "window_hours": duration,
        "cheapest_start": _hhmm(hours[cheap]),
        "cheapest_end": _hhmm(hours[cheap] + duration),
        "cheapest_price_eur_per_mwh": int(round(means[cheap])),
        "cheapest_price_cent_per_kwh": round(float(means[cheap]) / 10, 1),
        "most_expensive_start": _hhmm(hours[pricey]),
        "most_expensive_end": _hhmm(hours[pricey] + duration),
        "most_expensive_price_eur_per_mwh": int(round(means[pricey])),
        "day_average_price_eur_per_mwh": int(round(prices.mean())),
    }

    # Wind and solar outlook, if the grid operators' forecast for that day is in the store.
    features = load_features(zone, root=root)
    target = features[features["date"] == pd.Timestamp(day.date())].sort_values("hour")
    share = target["ws_share_fc"].to_numpy()
    if len(share) == len(prices) and not np.isnan(share).any():
        share_means = window_means(share, duration)
        green = best_window(share, duration, largest=True)
        facts |= {
            "greenest_start": _hhmm(hours[green]),
            "greenest_end": _hhmm(hours[green] + duration),
            "wind_solar_share_in_greenest_window_pct": int(round(share_means[green])),
            "wind_solar_share_in_cheapest_window_pct": int(round(share_means[cheap])),
            "wind_solar_share_day_average_pct": int(round(share.mean())),
        }

    # Honest track record: only forecasts made before the auction, last 30 days.
    scored = score_forecasts(zone, root=root)
    if not scored.empty:
        real = scored[scored["before_auction"] & (scored["model"] == forecast["model"].iloc[0])]
        recent = real[real["ts_utc"] >= real["ts_utc"].max() - pd.Timedelta(days=30)]
        if len(recent) >= 24:
            facts["recent_average_error_eur_per_mwh"] = int(round(recent["abs_error"].mean()))
    return facts


def template_briefing(facts: dict) -> str:
    """The fallback text. Dull, but always correct."""
    text = (
        f"On {facts['date']}, the cheapest {facts['window_hours']} hours to run the washing "
        f"machine are forecast to start at {facts['cheapest_start']}, at a wholesale price of "
        f"about {facts['cheapest_price_eur_per_mwh']} EUR/MWh. The most expensive start at "
        f"{facts['most_expensive_start']}, at about "
        f"{facts['most_expensive_price_eur_per_mwh']} EUR/MWh."
    )
    if "greenest_start" in facts:
        text += (
            f" The greenest window starts at {facts['greenest_start']}, when wind and solar "
            f"are forecast to cover about {facts['wind_solar_share_in_greenest_window_pct']}% "
            "of demand."
        )
    return text + " These are forecasts of market prices, not household prices."


NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _numbers(text: str) -> set[float]:
    return {float(match.replace(",", ".")) for match in NUMBER.findall(text)}


def check_grounding(text: str, facts: dict) -> list[str]:
    """Return a list of problems. An empty list means the text passed.

    Rule 1: every number in the text must appear somewhere in the facts.
    Rule 2: the cheapest start time must be stated.
    """
    allowed = set()
    for value in facts.values():
        allowed |= _numbers(str(value))
    problems = [f"number not in facts: {number:g}" for number in sorted(_numbers(text) - allowed)]
    if facts["cheapest_start"] not in text:
        problems.append("cheapest start time is missing")
    return problems


def call_claude(facts: dict, model: str) -> str:
    """Ask the Anthropic API for the briefing text."""
    import anthropic  # imported here so the rest of the project works without it

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    message = client.messages.create(
        model=model,
        max_tokens=300,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(facts, indent=2)}],
    )
    return "".join(block.text for block in message.content if block.type == "text").strip()


def make_briefing(
    facts: dict, complete: Callable[[dict, str], str] | None = None, model: str | None = None
) -> dict:
    """Produce the briefing record: text plus how it was made and whether it passed."""
    model = model or os.environ.get("POWERHOURS_LLM_MODEL", DEFAULT_LLM_MODEL)
    record = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "date": facts["date"],
        "facts": facts,
        "source": "template",
        "llm_model": None,
        "llm_text": None,
        "problems": [],
        "text": template_briefing(facts),
    }
    if complete is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            record["problems"] = ["no API key, used template"]
            return record
        complete = call_claude
    try:
        llm_text = complete(facts, model)
    except Exception as error:  # the daily job must survive any API problem
        record["problems"] = [f"LLM call failed: {type(error).__name__}"]
        return record

    record |= {"llm_model": model, "llm_text": llm_text}
    record["problems"] = check_grounding(llm_text, facts)
    if not record["problems"]:
        record |= {"source": "llm", "text": llm_text}
    return record


def briefing_path(zone: str, root=None) -> Path:
    return (root or data_dir()) / "public" / "briefing" / f"{zone}.jsonl"


def read_briefings(zone: str, root=None) -> list[dict]:
    path = briefing_path(zone, root)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def save_briefing(record: dict, zone: str, root=None) -> bool:
    """Append the record. One briefing per day: a second one is only kept if it
    upgrades a template text to a checked LLM text."""
    existing = read_briefings(zone, root)
    same_day = [r for r in existing if r["date"] == record["date"]]
    if same_day and not (record["source"] == "llm" and same_day[-1]["source"] != "llm"):
        return False
    path = briefing_path(zone, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    return True


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Write today's briefing.")
    parser.add_argument("--zone", default=DEFAULT_ZONE, choices=list(ZONES))
    parser.add_argument("--duration", type=int, default=2)
    args = parser.parse_args(argv)

    facts = build_facts(args.zone, args.duration)
    if facts is None:
        raise SystemExit("No forecast saved yet. Run `python -m powerhours.forecast` first.")
    record = make_briefing(facts)
    saved = save_briefing(record, args.zone)
    print(f"[{record['source']}] {record['text']}")
    if record["problems"]:
        print("Check:", "; ".join(record["problems"]))
    print("Saved." if saved else "A briefing for this day already exists; not saved again.")


if __name__ == "__main__":
    main()
