# Walkthrough: understand every piece before you publish it

Read this with the code open. Each section ends with questions. If you can answer them
without looking, you can defend that part in an interview. If not, ask an AI model to
explain that file to you, then come back.

Suggested order: about 20 to 30 minutes per section.

---

## 1. The problem in one paragraph

Electricity for tomorrow is sold today in an auction (the "day-ahead market"). Around
13:00 the results are published: one price per 15 minutes for all of tomorrow. Our job
runs in the morning, *before* that, and predicts tomorrow's prices. In the afternoon the
real prices arrive, and we can check how good the forecast was. This gives a new,
honest test of the model every single day.

**Check yourself**
- Why is a forecast made at 15:00 worthless here?
- Prices can be negative. What does a negative price mean, and when does it happen?

## 2. `config.py`: the choices

All settings live in one place: which zones, which timezone, how polite to be to the API.

**Check yourself**
- Germany's zone is called `DE-LU`. What does the LU stand for, and why do the two share a zone?
- Norway has five zones. Why does a country get split into several price zones?

## 3. `client.py`: talking to the API

Three ideas:

1. **Rate limiting.** The API allows 2 price requests per minute. The client remembers
   when it last called an endpoint and sleeps if the next call would be too early.
2. **Retries.** If the server answers `429 Too Many Requests`, it tells us how long to
   wait in the `Retry-After` header. We wait, then try again, up to 4 times.
3. **One parser for everything.** Every endpoint returns the same "envelope" shape, so
   `envelope_to_frame` works for prices, solar output, wind output and so on.

Notice that `sleep` and `clock` are passed in as arguments. That is why
`tests/test_client.py` can test the waiting logic in milliseconds without really waiting.
This trick is called *dependency injection*.

**Check yourself**
- What happens on a `404`, and why is that not treated as an error?
- Why does the table have a "long" format (one row per timestamp and series) instead of one column per series?

## 4. `store.py`: where the data lives

Data is saved as one Parquet file per month, in `data/public/...` or `data/private/...`.

- **Why Parquet and not CSV?** Smaller, faster, and it remembers data types (a timestamp
  stays a timestamp).
- **Why monthly files?** Each day only the current month's file changes, so committing
  data to git every day stays cheap.
- **Upsert.** Writing merges new rows with existing ones and removes duplicates by key.
  Running the same download twice changes nothing. This property is called
  *idempotency*, and it is what makes an automated daily job safe.
- **Public vs private.** The API states a licence with every response. Germany's prices
  are CC BY 4.0, Norway's are for private use only. The code checks this automatically
  and keeps restricted data in a git-ignored folder.
- **DuckDB.** `store.connect()` gives you a SQL database over all the files. Try it:

```python
from powerhours import store

con = store.connect()
con.sql("SELECT key, min(ts_utc), max(ts_utc), count(*) FROM price GROUP BY key").show()
```

**Check yourself**
- What would go wrong in the daily job if `upsert` simply appended rows?
- Why are timestamps stored in UTC rather than German local time?

## 5. `features.py`: the most important file

Read the comment at the top twice. The rule is: **features for a day may only use
earlier days.** Breaking this rule is called *data leakage* and it is the most common
way forecasting projects fool themselves.

The code reshapes prices into a table of days (rows) by hours (columns). Then
`m.shift(1)` means "yesterday's row", `m.shift(7)` means "same weekday last week".

`tests/test_features.py::test_no_leakage_from_target_day` proves the rule holds: it
changes one day's prices to 9999 and checks that this day's own features do not move.

**Check yourself**
- On the last Sunday of March the day has 23 hours. What does `hourly_matrix` do about it?
- Why is `lag_7d` a useful feature at all?
- Which obvious information about tomorrow is *not* used yet? (Hint: what makes power cheap?)

## 6. `models.py`: baselines first

Three models with the same interface:

- `naive_yesterday`: tomorrow at 14:00 = today at 14:00.
- `naive_last_week`: tomorrow at 14:00 = same weekday last week at 14:00.
- `gbm`: gradient-boosted trees on all features, untuned.

A model only means something relative to a baseline. "MAE of 12" says nothing. "25%
better than the naive forecast" says a lot.

**Check yourself**
- In plain words, how does gradient boosting build its prediction?
- The model uses `loss="absolute_error"`. What would change with squared error, and which price hours would it care more about?

## 7. `backtest.py`: honest evaluation

A random train/test split is wrong for time series, because the model would train on
days *after* the ones it is tested on. Instead we walk forward: train on everything up
to a date, predict the next 7 days, move on, retrain, repeat.

**Check yourself**
- Find the line that guarantees training data is strictly before the test block.
- Why do we refit every 7 days instead of every day or only once?

## 8. `window.py`: your own metric

`best_window` finds the cheapest block of N hours. `window_regret` asks: if I trust the
forecast, how much more do I pay than someone who knew the future?

This is the part of the project that is most *yours*: a metric designed for the question
instead of a default one. Expect to be asked about it.

**Check yourself**
- Construct by hand a forecast with a large MAE but zero regret.
- Is a regret of 1.3 EUR/MWh a lot? Convert it to cents for one 1 kWh wash. (Then think about whether that changes how you tell the story.)

## 9. `forecast.py`: the daily job

Makes tomorrow's forecast with every model and saves it. Two safeguards keep the track
record honest:

- A saved forecast is never overwritten.
- Each row records `made_at_utc` and `before_auction`. Late forecasts are stored but excluded from the score.

**Check yourself**
- Why is it tempting, and wrong, to regenerate old forecasts after improving the model?

## 10. `.github/workflows/`: automation

- `ci.yml` runs the linter and the tests on every push. A green tick on the repository shows the code works.
- `daily.yml` runs every morning: download, forecast, commit the new data.

**Check yourself**
- What does `permissions: contents: write` allow, and why is it needed?
- What happens if the API is down one morning? What is lost, and what is recovered the next day?

## 11. `tests/`

Tests use synthetic prices (`tests/conftest.py`), so they need no internet and always
give the same result. Run `pytest -v` and read the test names: they are a list of
promises the code makes.

---

## What has and has not been verified

- All 21 tests pass, and the full pipeline ran end to end on synthetic data.
- The parser was checked against a shortened copy of a real API response (in
  `tests/fixtures/`). The licence text in that file is a stand-in; the real wording comes
  from the API, and the code only looks for "CC BY" in it.
- Run against the live API on 2026-11-16 through GitHub Actions: the history download,
  the backtest and the first daily forecast all succeeded.
