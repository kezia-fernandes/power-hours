"""Print the shape of a few API responses. A development tool, not part of the pipeline."""

import json
import sys
import time

import requests

BASE = "https://api.energy-charts.info/v2/"
CALLS = [
    ("price", {"bzn": "DE-LU", "start": "2026-11-17", "end": "2026-11-17"}),
    ("public_power", {"country": "de", "start": "2026-11-15", "end": "2026-11-15"}),
    ("public_power_forecast", {"country": "de", "production_type": "solar",
                               "forecast_type": "day-ahead", "start": "2024-06-01", "end": "2024-06-02"}),
    ("ren_share_forecast", {"country": "de"}),
    ("signal", {"country": "de"}),
    ("public_power", {"country": "de", "start": "2024-01-01", "end": "2024-01-01"}),
    ("public_power_forecast", {"country": "de", "production_type": "load",
                               "forecast_type": "day-ahead", "start": "2024-06-01", "end": "2024-06-02"}),
    ("public_power_forecast", {"country": "de", "production_type": "wind_onshore",
                               "forecast_type": "current"}),
    ("public_power_forecast", {"country": "de", "production_type": "wind_offshore",
                               "forecast_type": "day-ahead", "start": "2026-11-16", "end": "2026-11-18"}),
    ("public_power_forecast", {"country": "de", "production_type": "solar",
                               "forecast_type": "intraday", "start": "2026-11-16", "end": "2026-11-18"}),
    ("public_power_forecast", {"country": "de", "production_type": "load",
                               "forecast_type": "day-ahead", "start": "2026-11-16", "end": "2026-11-18"}),
    ("public_power", {"country": "no", "start": "2026-11-15", "end": "2026-11-15"}),
]
last = {}
for endpoint, params in CALLS:
    wait = 32 - (time.time() - last.get(endpoint, 0))
    if wait > 0:
        time.sleep(wait)
    r = requests.get(BASE + endpoint, params=params, timeout=60)
    last[endpoint] = time.time()
    print("=" * 80, "\n", endpoint, params, "->", r.status_code)
    if r.status_code != 200:
        print(r.text[:300])
        continue
    env = r.json()
    data = env.pop("data", [])
    print(json.dumps(env)[:1500])
    print("records:", len(data))
    for rec in data[:1] + data[len(data) // 2 : len(data) // 2 + 1] + data[-1:]:
        print(json.dumps(rec)[:700])
    sys.stdout.flush()
