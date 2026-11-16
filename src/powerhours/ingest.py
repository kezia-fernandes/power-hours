"""Download data from the Energy-Charts API into the local store.

Usage
    python -m powerhours.ingest backfill --start 2024-01-01      # once, takes a while
    python -m powerhours.ingest update                           # daily, last few days
    python -m powerhours.ingest backfill --zone NO2 --start 2024-01-01

The API allows only 2 requests per minute, so a backfill is slow on purpose.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from powerhours import store
from powerhours.client import EnergyChartsClient, envelope_to_frame, is_open_licence
from powerhours.config import BACKFILL_CHUNK_DAYS, ZONES


def date_chunks(start: date, end: date, days: int) -> list[tuple[date, date]]:
    """Split [start, end] into consecutive inclusive chunks of at most `days` days."""
    chunks = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=days - 1), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


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
        print(f"price {zone} {chunk_start}..{chunk_end}: {rows} rows -> {where}")
    return total


def ingest_power(
    client: EnergyChartsClient, country: str, start: date, end: date, root=None
) -> int:
    """Electricity generation per source (solar, wind, ...) for one country."""
    total = 0
    for chunk_start, chunk_end in date_chunks(start, end, BACKFILL_CHUNK_DAYS):
        envelope = client.get(
            "public_power",
            country=country,
            start=chunk_start.isoformat(),
            end=chunk_end.isoformat(),
        )
        frame = envelope_to_frame(envelope)
        rows = store.upsert(frame, "power", country, public=is_open_licence(envelope), root=root)
        total += rows
        print(f"power {country} {chunk_start}..{chunk_end}: {rows} rows")
    return total


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=["backfill", "update"])
    parser.add_argument("--zone", action="append", help="bidding zone; default: all configured")
    parser.add_argument("--start", type=date.fromisoformat, help="backfill start date")
    parser.add_argument("--with-power", action="store_true", help="also fetch generation mix")
    args = parser.parse_args(argv)

    today = date.today()
    if args.command == "backfill":
        if not args.start:
            parser.error("backfill needs --start YYYY-MM-DD")
        start = args.start
    else:
        start = today - timedelta(days=7)  # overlap on purpose: upsert makes this safe
    end = today + timedelta(days=1)  # tomorrow's prices exist after ~13:00 CET

    client = EnergyChartsClient()
    for code in args.zone or list(ZONES):
        zone = ZONES[code]
        ingest_prices(client, zone.code, start, end)
        if args.with_power:
            ingest_power(client, zone.country, start, min(end, today))


if __name__ == "__main__":
    main()
