# Power hours: when should I run the washing machine?

> **Status: work in progress.** The pipeline runs; the analysis and results below are still to come.

My aunt in Norway told me she runs her washing machine at night because electricity is
cheaper then. I wanted to know whether the same rule holds in Germany, and whether I
could predict tomorrow's cheapest hours before the market publishes them.

This project:

1. collects day-ahead electricity prices for Germany every day,
2. forecasts tomorrow's 24 hourly prices each morning, before the auction results are out,
3. recommends the cheapest window for a 1 to 6 hour appliance run,
4. keeps score: every forecast is saved and later compared with what really happened,
5. compares the daily price pattern in Germany with Norway.

<!-- TODO (you): add a screenshot of the dashboard and the link to the live app here. -->

## Results

<!-- TODO (you): fill this in from your own backtest and analysis. Suggested content:
- a table from `python -m powerhours.backtest --days 180`
- one chart: typical day in Germany vs Norway
- two or three sentences on what you found and what surprised you -->

*Not filled in yet.*

## How it works

```
Energy-Charts API ──> ingest ──> Parquet files (data/) ──> DuckDB (SQL analysis)
                                        │
                                        ├──> features ──> models ──> backtest (how good is it?)
                                        │
                                        └──> daily forecast ──> saved, later scored ──> dashboard
```

A GitHub Actions job runs every morning at 07:10 UTC: it downloads the newest prices,
makes tomorrow's forecast and commits both to this repository.

| Part | File | What it does |
|---|---|---|
| API client | `src/powerhours/client.py` | Talks to the API, respects its rate limit |
| Storage | `src/powerhours/store.py` | Monthly Parquet files, queried with DuckDB |
| Ingestion | `src/powerhours/ingest.py` | Backfill and daily update |
| Features | `src/powerhours/features.py` | Lag and calendar features, without leakage |
| Models | `src/powerhours/models.py` | Two naive baselines and gradient boosting |
| Backtest | `src/powerhours/backtest.py` | Walk-forward evaluation |
| Window | `src/powerhours/window.py` | Cheapest window and the "regret" metric |
| Daily job | `src/powerhours/forecast.py` | Forecast, save, score |
| Dashboard | `app/streamlit_app.py` | Streamlit app |

### The metric I care about

Mean absolute error tells you how wrong the prices are. But the question is about
*timing*: a forecast can be off by 20 EUR/MWh at every hour and still pick the right
window. So besides MAE I report **window regret**: how much more you pay by running the
machine in the window the forecast recommends instead of the truly cheapest one.

## Run it yourself

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev,app]"

pytest                                                    # tests, no internet needed
python -m powerhours.ingest backfill --zone DE-LU --start 2024-01-01   # a few minutes
python -m powerhours.backtest --days 90
python -m powerhours.forecast
streamlit run app/streamlit_app.py
```

The API allows two price requests per minute, so the backfill pauses between requests.

## Data and licence

- Source: [Energy-Charts](https://www.energy-charts.info) by Fraunhofer ISE.
- German (DE-LU) day-ahead prices: Bundesnetzagentur | SMARD.de, CC BY 4.0.
- Norwegian prices are restricted to private and internal use by the API's terms, so
  they are stored in `data/private/`, which is git-ignored, and are not part of this
  repository.

## How this was built

I built this project with the help of AI assistants (Claude). The first working skeleton
was generated in one session; I then read and tested every part, and the analysis,
modelling decisions and conclusions are mine. `LEARNING_LOG.md` records what I decided,
what went wrong and what I learned along the way.

<!-- TODO (you): keep this section true. Edit it to describe what you actually did. -->
