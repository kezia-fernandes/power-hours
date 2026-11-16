"""Dashboard skeleton. Run with:  streamlit run app/streamlit_app.py

This is deliberately plain. Making it clear and good-looking is on the roadmap.
"""

import pandas as pd
import streamlit as st

from powerhours import store
from powerhours.config import ZONES
from powerhours.forecast import score_forecasts
from powerhours.window import best_window, window_costs

st.set_page_config(page_title="Power hours", page_icon="🧺")
st.title("When should I run the washing machine?")

con = store.connect()
tables = {row[0] for row in con.sql("SHOW TABLES").fetchall()}
if "price" not in tables:
    st.warning("No data yet. Run `python -m powerhours.ingest backfill --start 2024-01-01`.")
    st.stop()

# --- Tomorrow -----------------------------------------------------------------
zone = "DE-LU"
tz = ZONES[zone].timezone
forecasts = store.read("forecast", zone)

st.header("Next forecast for Germany")
if forecasts.empty:
    st.info("No forecast saved yet. Run `python -m powerhours.forecast`.")
else:
    latest = forecasts[forecasts["made_at_utc"] == forecasts["made_at_utc"].max()]
    gbm = latest[latest["model"] == "gbm"].sort_values("ts_utc")
    local = gbm["ts_utc"].dt.tz_convert(tz)
    duration = st.slider("How long does the programme run (hours)?", 1, 6, 2)
    start = best_window(gbm["yhat"], duration)
    cost = window_costs(gbm["yhat"], duration)
    st.metric(
        f"Cheapest {duration}-hour window on {local.iloc[0]:%A %d %B}",
        f"start at {local.iloc[start]:%H:%M}",
        f"{cost[start] - cost.mean():.0f} EUR/MWh vs. average window",
        delta_color="inverse",
    )
    st.line_chart(pd.DataFrame({"forecast (EUR/MWh)": gbm["yhat"].to_numpy()}, index=local))

# --- Track record ---------------------------------------------------------------
st.header("How good have the forecasts been?")
scored = score_forecasts(zone)
if scored.empty:
    st.info("Nothing to score yet. This fills up once forecasts meet real prices.")
else:
    real = scored[scored["before_auction"]]
    st.caption(f"Only forecasts made before the auction count: {real['ts_utc'].nunique()} hours.")
    st.dataframe(real.groupby("model")["abs_error"].mean().rename("MAE (EUR/MWh)").round(2))
    recent = real[real["model"] == "gbm"].sort_values("ts_utc").tail(24 * 14)
    st.line_chart(recent.set_index("ts_utc")[["y", "yhat"]])

# --- Germany vs Norway ------------------------------------------------------------
st.header("A typical day: which hours are cheap?")
profile = con.sql(
    """
    SELECT key AS zone,
           hour(timezone(CASE key WHEN 'DE-LU' THEN 'Europe/Berlin' ELSE 'Europe/Oslo' END,
                         ts_utc)) AS hour,
           avg(value) AS avg_price
    FROM price
    WHERE series = 'day_ahead_price'
    GROUP BY ALL
    ORDER BY ALL
    """
).df()
st.line_chart(profile.pivot(index="hour", columns="zone", values="avg_price"))
st.caption(
    "Data: Energy-Charts (Fraunhofer ISE); German prices: Bundesnetzagentur | SMARD.de, "
    "CC BY 4.0. Norwegian prices have a restricted licence and only appear when you run "
    "this locally with your own private copy of the data."
)
