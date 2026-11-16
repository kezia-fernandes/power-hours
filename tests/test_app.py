"""Smoke test: the dashboard must run from top to bottom without an exception."""

from pathlib import Path

import pytest

from powerhours import store
from powerhours.briefing import build_facts, make_briefing, save_briefing
from powerhours.forecast import make_forecast, save_forecast

from .conftest import synthetic_exog, synthetic_prices

APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"


def test_dashboard_runs(tmp_path, monkeypatch):
    testing = pytest.importorskip("streamlit.testing.v1")
    monkeypatch.setenv("POWERHOURS_DATA", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    all_prices = synthetic_prices(days=120)
    prices = all_prices.iloc[: 118 * 96]
    exog = synthetic_exog(all_prices, extra_days=2)
    store.upsert(prices, "price", "DE-LU", public=True, root=tmp_path)
    store.upsert(exog, "exog", "de", public=True, root=tmp_path)
    share = exog[exog["series"] == "solar_forecast"].assign(
        series="renewable_share_of_load", value=lambda f: f["value"] / 400
    )
    store.upsert(share, "power", "de", public=True, root=tmp_path)
    save_forecast(make_forecast("DE-LU", root=tmp_path), "DE-LU", root=tmp_path)
    save_briefing(make_briefing(build_facts("DE-LU", root=tmp_path)), "DE-LU", root=tmp_path)
    store.upsert(all_prices, "price", "DE-LU", public=True, root=tmp_path)  # actuals arrive

    app = testing.AppTest.from_file(str(APP), default_timeout=120).run()
    assert not app.exception, app.exception
    assert app.title[0].value == "When should I run the washing machine?"
    assert len(app.metric) >= 6  # three tiles for tomorrow, three for cheap vs green
