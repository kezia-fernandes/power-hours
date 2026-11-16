"""Download data from the Energy-Charts API into the local store.

Usage
    python -m powerhours.ingest backfill --start 2024-01-01          # prices, all zones
    python -m powerhours.ingest backfill --start 2024-01-01 --zone DE-LU --what power exog
    python -m powerhours.ingest update --zone DE-LU --what prices power exog   # daily

What can be downloaded (--what)
    prices   day-ahead prices per bidding zone (kept at the API's resolution)
    power    what was really generated and consumed: solar, wind, load, renewable share
    exog     the grid operators' day-ahead FORECASTS of solar, wind and load

The API allows only 2 requests per minute and endpoint, so a backfill is slow on purpose.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from powerhours import store
from powerhours.client import EnergyChartsClient, envelope_to_frame, is_open_licence
from powerhours.config import BACKFILL_CHUNK_DAYS, EXOG_TYPES, POWER_SERIES, ZONES


def date_chunks(start: date, end: date, days: int) -> list[tuple[date, date]]:
    """Split [start, end] into consecutive inclusive chunks of at most `days` days."""
    chunks = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=days - 1), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def to_hourly(frame: pd.DataFrame) -> pd.DataFrame:
    """Average each series per hour. Generation data arrives in 15-minute steps;
    hourly is all the model needs and keeps the repository small."""
    if frame.empty:
        return frame
    hourly = (
        frame.set_index("ts_utc")
        .groupby("series")["value"]
        .resample("1h")
        .mean()
        .dropna()
        .reset_index()
    )
    return hourly[["ts_utc", "series", "value"]]


def ingest_prices(client: EnergyChartsClient, zone: str, start: date, end: date, root=None) -> int:
    """Day-ahead prices for one bidding zone. Returns rows written."""
    total = 0
    for chunk_start, chunk_end in date_chunks(start, end, BACKFILL_CHUNK_DAYS):
        envelope = client.get(
            "price", bzn=zone, start=chunk_start.isoformat(), end=chunk_end.isoformat()
        )
        frame = envelope_to_frame(envelope)
        public = is_open_licence(envelope)
        rows = store.upsert(frame, "price", zone, public=public, root=root)
        total += rows
        where = "public" if public else "PRIVATE (restricted licence)"
        print(f"price {zone} {chunk_start}..{chunk_end}: {rows} rows -> {where}", flush=True)
    return total


def ingest_power(
    client: EnergyChartsClient, country: str, start: date, end: date, root=None
) -> int:
    """Actual generation and consumption for one country, hourly, selected series only."""
    total = 0
    for chunk_start, chunk_end in date_chunks(start, end, BACKFILL_CHUNK_DAYS):
        envelope = client.get(
            "public_power",
            country=country,
            start=chunk_start.isoformat(),
            end=chunk_end.isoformat(),
        )
        frame = envelope_to_frame(envelope)
        frame = to_hourly(frame[frame["series"].isin(POWER_SERIES)])
        rows = store.upsert(frame, "power", country, public=is_open_licence(envelope), root=root)
        total += rows
        print(f"power {country} {chunk_start}..{chunk_end}: {rows} rows", flush=True)
    return total


def ingest_exog(
    client: EnergyChartsClient,
    country: str,
    start: date,
    end: date,
    root=None,
    now: datetime | None = None,
) -> int:
    """Day-ahead forecasts of solar, wind and load, stored as `<type>_forecast`.

    Also records in the `exog_seen` dataset the moment each forecast value was first
    seen by us. That log answers a question the API's history cannot: was the
    forecast for tomorrow already published when our morning job ran?
    """
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    total = 0
    for kind in EXOG_TYPES:
        for chunk_start, chunk_end in date_chunks(start, end, BACKFILL_CHUNK_DAYS):
            envelope = client.get(
                "public_power_forecast",
                country=country,
                production_type=kind,
                forecast_type="day-ahead",
                start=chunk_start.isoformat(),
                end=chunk_end.isoformat(),
            )
            frame = to_hourly(envelope_to_frame(envelope))
            if frame.empty:
                print(f"exog {kind} {chunk_start}..{chunk_end}: nothing published", flush=True)
                continue
            frame["series"] = f"{kind}_forecast"
            public = is_open_licence(envelope)
            rows = store.upsert(frame, "exog", country, public=public, root=root)
            seen = frame[["ts_utc", "series"]].assign(first_seen_utc=now)
            store.insert_new(seen, "exog_seen", country, public=public, root=root)
            total += rows
            last = frame["ts_utc"].max()
            print(f"exog {kind} {chunk_start}..{chunk_end}: {rows} rows, up to {last}", flush=True)
    return total


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=["backfill", "update"])
    parser.add_argument("--zone", action="append", help="bidding zone; default: all configured")
    parser.add_argument("--start", type=date.fromisoformat, help="backfill start date")
    parser.add_argument(
        "--what",
        nargs="+",
        choices=["prices", "power", "exog"],
        default=["prices"],
        help="which data to download (default: prices)",
    )
    args = parser.parse_args(argv)

    today = date.today()
    if args.command == "backfill":
        if not args.start:
            parser.error("backfill needs --start YYYY-MM-DD")
        start = args.start
    else:
        start = today - timedelta(days=7)  # overlap on purpose: upsert makes this safe
    tomorrow = today + timedelta(days=1)

    client = EnergyChartsClient()
    for code in args.zone or list(ZONES):
        zone = ZONES[code]
        if "prices" in args.what:
            ingest_prices(client, zone.code, start, tomorrow)  # tomorrow exists after ~13:00
        if "power" in args.what:
            ingest_power(client, zone.country, start, today)
        if "exog" in args.what:
            ingest_exog(client, zone.country, start, today + timedelta(days=2))


if __name__ == "__main__":
    main()
