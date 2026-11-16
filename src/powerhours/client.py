"""Small client for the Energy-Charts API (Fraunhofer ISE), v2 endpoints.

Docs: https://api.energy-charts.info/

Every v2 endpoint returns the same "envelope": metadata (unit, timezone, licence)
plus a list of records like
    {"timestamp": "2026-11-15T00:00:00+01:00", "values": {"day_ahead_price": 163.35}}
`envelope_to_frame` turns that into one tidy table, whatever the endpoint.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import pandas as pd
import requests

from powerhours.config import API_BASE_URL, MIN_SECONDS_BETWEEN_REQUESTS


class EnergyChartsError(RuntimeError):
    pass


class EnergyChartsClient:
    """Polite API client: spaces out requests and waits when the server says 429."""

    def __init__(
        self,
        base_url: str = API_BASE_URL,
        min_interval: float = MIN_SECONDS_BETWEEN_REQUESTS,
        session: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        max_retries: int = 4,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.min_interval = min_interval
        self.session = session or requests.Session()
        self._sleep = sleep
        self._clock = clock
        self.max_retries = max_retries
        self._last_request: dict[str, float] = {}  # rate limits are per endpoint

    def get(self, endpoint: str, **params: Any) -> dict:
        """GET /v2/<endpoint> and return the parsed JSON envelope."""
        url = f"{self.base_url}/v2/{endpoint}"
        params = {k: v for k, v in params.items() if v is not None}

        for attempt in range(self.max_retries + 1):
            self._wait_for_slot(endpoint)
            response = self.session.get(url, params=params, timeout=60)
            self._last_request[endpoint] = self._clock()

            if response.status_code == 429 and attempt < self.max_retries:
                retry_after = float(response.headers.get("Retry-After", self.min_interval))
                self._sleep(retry_after + 1)
                continue
            if response.status_code == 404:
                # The API uses 404 for "no data for this period (yet)".
                return {"endpoint": endpoint, "data": [], "series": []}
            if response.status_code >= 400:
                raise EnergyChartsError(
                    f"{endpoint} {params} -> HTTP {response.status_code}: {response.text[:200]}"
                )
            return response.json()

        raise EnergyChartsError(f"{endpoint}: still rate limited after {self.max_retries} retries")

    def _wait_for_slot(self, endpoint: str) -> None:
        last = self._last_request.get(endpoint)
        if last is None:
            return
        remaining = self.min_interval - (self._clock() - last)
        if remaining > 0:
            self._sleep(remaining)


def envelope_to_frame(envelope: dict) -> pd.DataFrame:
    """Turn a v2 envelope into a long table: one row per (timestamp, series).

    Columns: ts_utc (timezone-aware UTC), series, value.
    Missing values (null in the JSON = "not yet available") are dropped.
    """
    rows = [
        (record["timestamp"], series, value)
        for record in envelope.get("data", [])
        for series, value in record.get("values", {}).items()
        if value is not None
    ]
    frame = pd.DataFrame(rows, columns=["ts_utc", "series", "value"])
    frame["ts_utc"] = pd.to_datetime(frame["ts_utc"], utc=True)
    frame["value"] = frame["value"].astype("float64")
    return frame


def is_open_licence(envelope: dict) -> bool:
    """True if the data may be redistributed (CC BY). Otherwise it must stay private.

    Day-ahead prices carry a licence per bidding zone: some zones are CC BY 4.0
    (via Bundesnetzagentur | SMARD.de), the rest are "private and internal use" only.
    """
    return "CC BY" in str(envelope.get("license", ""))
