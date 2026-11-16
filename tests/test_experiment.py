from powerhours.experiment import read_log, run_experiment
from powerhours.features import build_features, hourly_matrix


def test_run_is_logged_and_listed(prices, tmp_path):
    features = build_features(hourly_matrix(prices, "Europe/Berlin"))
    log = tmp_path / "experiments" / "log.jsonl"
    summary = run_experiment("first", days=14, notes="test", features=features, log_path=log)
    run_experiment("second", days=14, features=features, log_path=log)

    table = read_log(log)
    assert len(table) == 2 * len(summary)
    assert set(table["name"]) == {"first", "second"}
    row = table[(table["name"] == "first") & (table["model"] == "gbm")].iloc[0]
    assert row["notes"] == "test"
    assert "lag_1d" in row["features"]
    assert row["mae"] > 0
    assert read_log(tmp_path / "missing.jsonl").empty
