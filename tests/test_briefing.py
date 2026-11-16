import pytest

from powerhours import store
from powerhours.briefing import (
    build_facts,
    check_grounding,
    make_briefing,
    read_briefings,
    save_briefing,
    template_briefing,
)
from powerhours.forecast import make_forecast, save_forecast

from .conftest import synthetic_exog, synthetic_prices


@pytest.fixture
def facts(tmp_path):
    prices = synthetic_prices(days=100)
    store.upsert(prices, "price", "DE-LU", public=True, root=tmp_path)
    store.upsert(synthetic_exog(prices, extra_days=2), "exog", "de", public=True, root=tmp_path)
    save_forecast(make_forecast("DE-LU", root=tmp_path), "DE-LU", root=tmp_path)
    return build_facts("DE-LU", root=tmp_path)


def test_facts_are_complete_and_consistent(facts):
    assert facts["window_hours"] == 2
    assert facts["cheapest_price_eur_per_mwh"] <= facts["day_average_price_eur_per_mwh"]
    assert facts["day_average_price_eur_per_mwh"] <= facts["most_expensive_price_eur_per_mwh"]
    assert "greenest_start" in facts
    low = facts["wind_solar_share_in_cheapest_window_pct"]
    assert low <= facts["wind_solar_share_in_greenest_window_pct"]


def test_no_forecast_means_no_facts(tmp_path):
    assert build_facts("DE-LU", root=tmp_path) is None


def test_template_always_passes_its_own_check(facts):
    assert check_grounding(template_briefing(facts), facts) == []


def test_check_catches_invented_numbers_and_missing_time(facts):
    good = template_briefing(facts)
    assert "number not in facts: 87" in check_grounding(good + " You save 87 percent.", facts)
    without_time = good.replace(facts["cheapest_start"], "some point")
    assert "cheapest start time is missing" in check_grounding(without_time, facts)


def test_llm_text_is_used_only_if_it_passes(facts, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    honest = f"Start the machine at {facts['cheapest_start']} on {facts['date']}."
    record = make_briefing(facts, complete=lambda facts, model: honest)
    assert (record["source"], record["text"], record["problems"]) == ("llm", honest, [])

    record = make_briefing(facts, complete=lambda facts, model: honest + " Prices fall 99%.")
    assert record["source"] == "template"
    assert record["llm_text"].endswith("99%.")  # the rejected text is kept for analysis
    assert record["problems"] == ["number not in facts: 99"]


def test_no_key_and_api_errors_fall_back_to_template(facts, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert make_briefing(facts)["source"] == "template"

    def broken(facts, model):
        raise TimeoutError

    record = make_briefing(facts, complete=broken)
    assert record["source"] == "template"
    assert record["problems"] == ["LLM call failed: TimeoutError"]


def test_one_briefing_per_day_unless_upgraded(facts, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    template = make_briefing(facts)
    assert save_briefing(template, "DE-LU", root=tmp_path)
    assert not save_briefing(template, "DE-LU", root=tmp_path)
    honest = f"Start at {facts['cheapest_start']}."
    upgraded = make_briefing(facts, complete=lambda facts, model: honest)
    assert save_briefing(upgraded, "DE-LU", root=tmp_path)
    assert [r["source"] for r in read_briefings("DE-LU", root=tmp_path)] == ["template", "llm"]
