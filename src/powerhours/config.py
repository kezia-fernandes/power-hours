"""Central configuration. Everything that is a *choice* lives here, so it is easy to find."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

API_BASE_URL = "https://api.energy-charts.info"

# The API allows 2 price requests per minute. We stay safely below that.
MIN_SECONDS_BETWEEN_REQUESTS = 31.0

# How many days to ask for in one request during a backfill.
BACKFILL_CHUNK_DAYS = 90

# Day-ahead auction results for tomorrow are published around 12:45-13:00 CET.
# A forecast only counts as a real forecast if it was made before that.


@dataclass(frozen=True)
class Zone:
    code: str  # bidding zone code used by the API, e.g. "DE-LU"
    country: str  # country code used by the generation endpoints, e.g. "de"
    timezone: str  # local timezone; all "hour of day" logic uses this
    label: str


ZONES: dict[str, Zone] = {
    "DE-LU": Zone("DE-LU", "de", "Europe/Berlin", "Germany"),
    # NO2 is southern Norway (Kristiansand / Stavanger). Change this to the zone
    # where your aunt lives: NO1 Oslo, NO3 Trondheim, NO4 Tromsø, NO5 Bergen.
    "NO2": Zone("NO2", "no", "Europe/Oslo", "Norway (south)"),
}

DEFAULT_ZONE = "DE-LU"

# Series we keep from the generation data (the API returns about 20).
POWER_SERIES = [
    "solar",
    "wind_onshore",
    "wind_offshore",
    "load",
    "residual_load",
    "renewable_share_of_load",
]

# Day-ahead forecasts published by the grid operators, used as model inputs.
# "load" is electricity demand.
EXOG_TYPES = ["solar", "wind", "load"]


def data_dir() -> Path:
    """Root of the data folder. Override with the POWERHOURS_DATA environment variable."""
    env = os.environ.get("POWERHOURS_DATA")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "data"
