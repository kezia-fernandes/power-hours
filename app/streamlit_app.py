"""Dashboard. Run with:  streamlit run app/streamlit_app.py

Layout, top to bottom: the answer for tomorrow, the evidence behind it, how well the
forecasts have done, and what the data says about cheap and green hours in general.
"""

import altair as alt
import pandas as pd
import streamlit as st

from powerhours import store
from powerhours.briefing import read_briefings
from powerhours.config import ZONES
from powerhours.experiment import read_log
from powerhours.features import hourly_matrix, load_features
from powerhours.forecast import latest_forecast, score_forecasts
from powerhours.green import (
    cheap_vs_green,
    price_by_share_bucket,
    share_matrix,
    summarize_cheap_vs_green,
)
from powerhours.window import best_window, window_means

ZONE = "DE-LU"
TZ = ZONES[ZONE].timezone
BLUE, ORANGE, AQUA, BAND = "#2a78d6", "#eb6834", "#1baf7a", "#8a8984"

st.set_page_config(page_title="Power hours", page_icon="🧺", layout="centered")


@st.cache_data(ttl=3600)
def load():
    prices = store.read("price", ZONE)
    power = store.read("power", ZONES[ZONE].country)
    norway = store.read("price", "NO2")
    return prices, power, norway


def show(chart):
    """Draw a chart at full width (the argument name changed between Streamlit versions)."""
    try:
        st.altair_chart(chart, width="stretch")
    except TypeError:
        st.altair_chart(chart, use_container_width=True)


def hour_axis(title="Hour of day"):
    return alt.X(
        "hour:Q", title=title, scale=alt.Scale(domain=[0, 24]), axis=alt.Axis(tickCount=12)
    )


def line_with_window(frame, column, title, color, start, duration, label):
    """One line over the day, with the recommended window shaded behind it."""
    band = pd.DataFrame({"start": [start], "end": [start + duration], "label": [label]})
    shade = (
        alt.Chart(band)
        .mark_rect(opacity=0.18, color=BAND)
        .encode(x="start:Q", x2="end:Q", tooltip=["label:N"])
    )
    line = (
        alt.Chart(frame)
        .mark_line(color=color, strokeWidth=2, point=alt.OverlayMarkDef(color=color, size=30))
        .encode(
            x=hour_axis(),
            y=alt.Y(f"{column}:Q", title=title),
            tooltip=[alt.Tooltip("hour:Q", title="Hour"), alt.Tooltip(f"{column}:Q", format=".0f")],
        )
    )
    return (shade + line).properties(height=240)


prices, power, norway = load()
st.title("When should I run the washing machine?")
st.caption(
    "A daily forecast of German electricity prices, made every morning before the "
    "market publishes them."
)
if prices.empty:
    st.warning("No data yet. Run `python -m powerhours.ingest backfill --start 2024-01-01`.")
    st.stop()

# ── 1. Tomorrow ──────────────────────────────────────────────────────────────────
forecast = latest_forecast(ZONE)
if forecast.empty:
    st.info("No forecast saved yet. Run `python -m powerhours.forecast`.")
else:
    local = forecast["ts_utc"].dt.tz_convert(TZ)
    day = local.iloc[0]
    frame = pd.DataFrame({"hour": local.dt.hour.to_numpy(), "price": forecast["yhat"].to_numpy()})
    st.header(f"{day:%A} {day.day} {day:%B}")

    briefings = [b for b in read_briefings(ZONE) if b["date"] == f"{day:%A} {day.day} {day:%B}"]
    if briefings:
        latest = briefings[-1]
        st.info(latest["text"])
        how = (
            "Written by an LLM from the numbers below; every number was checked automatically."
            if latest["source"] == "llm"
            else "Written from a fixed template."
        )
        st.caption(how)

    duration = st.slider("How long does the programme run (hours)?", 1, 6, 2)
    means = window_means(frame["price"], duration)
    cheap = best_window(frame["price"], duration)

    features = load_features(ZONE)
    target = features[features["date"] == pd.Timestamp(day.date())].sort_values("hour")
    has_share = len(target) == len(frame) and target["ws_share_fc"].notna().all()

    left, middle, right = st.columns(3)
    left.metric("Cheapest start", f"{cheap:02d}:00")
    left.caption(f"about {means[cheap]:.0f} EUR/MWh")
    if has_share:
        share = target["ws_share_fc"].to_numpy()
        green = best_window(share, duration, largest=True)
        green_share = window_means(share, duration)[green]
        middle.metric("Greenest start", f"{green:02d}:00")
        middle.caption(f"about {green_share:.0f}% wind and solar")
    else:
        middle.metric("Greenest start", "n/a")
        middle.caption("wind and solar forecast not published yet")
    right.metric("Day average", f"{frame['price'].mean():.0f}")
    right.caption("EUR/MWh")

    st.subheader("Forecast price")
    show(
        line_with_window(
            frame, "price", "EUR/MWh", BLUE, cheap, duration, f"cheapest {duration} hours"
        )
    )
    if has_share:
        st.subheader("Forecast wind and solar, as a share of demand")
        share_frame = pd.DataFrame({"hour": target["hour"].to_numpy(), "share": share})
        show(
            line_with_window(
                share_frame,
                "share",
                "% of demand",
                AQUA,
                green,
                duration,
                f"greenest {duration} hours",
            )
        )
    st.caption(
        f"Model: {forecast['model'].iloc[0]}. Shaded: the recommended window. Prices are "
        "wholesale market prices; households pay taxes and grid fees on top."
    )

# ── 2. Track record ──────────────────────────────────────────────────────────────
st.header("How good are the forecasts?")
scored = score_forecasts(ZONE)
real = scored[scored["before_auction"]] if not scored.empty else scored
if real.empty:
    st.info(
        "No forecast has met its real prices yet. This section fills up day by day. "
        "Until then, see the backtest results under Experiments."
    )
else:
    days = real["ts_utc"].dt.tz_convert(TZ).dt.date.nunique()
    mae = real.groupby("model")["abs_error"].mean().sort_values()
    st.caption(f"Live results over {days} day(s). Only forecasts made before the auction count.")
    table = mae.rename("Average error (EUR/MWh)").round(1).reset_index()
    st.dataframe(table.rename(columns={"model": "Model"}), hide_index=True)

    shown = real[real["model"] == forecast["model"].iloc[0]].sort_values("ts_utc").tail(24 * 7)
    long = shown.melt(id_vars="ts_utc", value_vars=["y", "yhat"], var_name="kind")
    long["kind"] = long["kind"].map({"y": "Actual", "yhat": "Forecast"})
    long["time"] = long["ts_utc"].dt.tz_convert(TZ).dt.tz_localize(None)
    chart = (
        alt.Chart(long)
        .mark_line(strokeWidth=2)
        .encode(
            x=alt.X("time:T", title=None),
            y=alt.Y("value:Q", title="EUR/MWh"),
            color=alt.Color(
                "kind:N",
                title=None,
                scale=alt.Scale(domain=["Actual", "Forecast"], range=[BLUE, ORANGE]),
                legend=alt.Legend(orient="top"),
            ),
            tooltip=[
                alt.Tooltip("time:T", format="%a %d %b %H:%M"),
                "kind:N",
                alt.Tooltip("value:Q", format=".0f"),
            ],
        )
        .properties(height=260)
    )
    show(chart)

# ── 3. What the data says ────────────────────────────────────────────────────────
st.header("What the data says")
matrix = hourly_matrix(prices, TZ)

st.subheader("A typical day in Germany, summer and winter")
season = pd.Series(
    ["Summer (Apr-Sep)" if 4 <= m <= 9 else "Winter (Oct-Mar)" for m in matrix.index.month],
    index=matrix.index,
)
profile = matrix.groupby(season).mean().T.reset_index().melt(id_vars="hour", var_name="season")
show(
    alt.Chart(profile)
    .mark_line(strokeWidth=2)
    .encode(
        x=hour_axis(),
        y=alt.Y("value:Q", title="Average price (EUR/MWh)"),
        color=alt.Color(
            "season:N",
            title=None,
            scale=alt.Scale(domain=["Summer (Apr-Sep)", "Winter (Oct-Mar)"], range=[ORANGE, BLUE]),
            legend=alt.Legend(orient="top"),
        ),
        tooltip=["season:N", alt.Tooltip("hour:Q"), alt.Tooltip("value:Q", format=".0f")],
    )
    .properties(height=260)
)

if not norway.empty:
    st.subheader("Germany and Norway")
    both = pd.DataFrame(
        {
            "Germany": matrix.mean(),
            "Norway (south)": hourly_matrix(norway, ZONES["NO2"].timezone).mean(),
        }
    )
    both = both.reset_index().melt(id_vars="hour", var_name="country")
    show(
        alt.Chart(both)
        .mark_line(strokeWidth=2)
        .encode(
            x=hour_axis(),
            y=alt.Y("value:Q", title="Average price (EUR/MWh)"),
            color=alt.Color(
                "country:N",
                title=None,
                scale=alt.Scale(domain=["Germany", "Norway (south)"], range=[BLUE, AQUA]),
                legend=alt.Legend(orient="top"),
            ),
            tooltip=["country:N", alt.Tooltip("hour:Q"), alt.Tooltip("value:Q", format=".0f")],
        )
        .properties(height=260)
    )
    st.caption(
        "Norwegian prices are shown from a private local copy; their licence forbids sharing."
    )

if not power.empty:
    st.subheader("Are the cheapest hours also the greenest?")
    shares = share_matrix(power, TZ)
    summary = summarize_cheap_vs_green(cheap_vs_green(matrix, shares, duration=2))
    if summary:
        a, b, c = st.columns(3)
        a.metric("Days compared", f"{summary['days']}")
        b.metric("Windows overlap", f"{summary['share_of_days_overlapping']:.0%} of days")
        c.metric("Extra price for green", f"+{summary['avg_extra_price_for_green']:.0f}")
        c.caption("EUR/MWh, greenest vs cheapest window")
        buckets = price_by_share_bucket(matrix, shares)
        show(
            alt.Chart(buckets)
            .mark_bar(color=AQUA, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
            .encode(
                x=alt.X(
                    "bucket:N",
                    title="Renewable share of demand",
                    sort=None,
                    axis=alt.Axis(labelAngle=0),
                ),
                y=alt.Y("avg_price:Q", title="Average price (EUR/MWh)"),
                tooltip=[
                    alt.Tooltip("bucket:N", title="Renewable share"),
                    alt.Tooltip("avg_price:Q", title="Average price", format=".0f"),
                    alt.Tooltip("hours:Q", title="Hours in this band"),
                ],
            )
            .properties(height=260)
        )
        st.caption(
            "Each bar: all hours since 2024 in which renewables covered that share of demand."
        )

# ── 4. Experiments ───────────────────────────────────────────────────────────────
st.header("Experiments")
log = read_log()
if log.empty:
    st.info("No experiments logged yet. Run `python -m powerhours.experiment run --name ...`.")
else:
    st.caption("Backtests on past data: each model forecasts days it has never seen.")
    columns = {
        "run_at": "Run",
        "name": "Experiment",
        "model": "Model",
        "mae": "Avg error",
        "skill_vs_naive": "Skill vs naive",
        "window_regret": "Window regret",
        "test_from": "Test from",
        "test_to": "Test to",
    }
    st.dataframe(log[list(columns)].rename(columns=columns), hide_index=True)

st.divider()
st.caption(
    "Data: Energy-Charts (Fraunhofer ISE), CC BY 4.0. German day-ahead prices: "
    "Bundesnetzagentur | SMARD.de, CC BY 4.0. Code and method: see the repository."
)
