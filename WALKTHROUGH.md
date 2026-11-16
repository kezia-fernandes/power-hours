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

Read the comment at the top twice. There are two groups of features.

**Group 1: past prices and the calendar (`BASE_FEATURES`).** The rule is: features for
a day may only use *earlier* days. Breaking this rule is called *data leakage* and it is
the most common way forecasting projects fool themselves. The code reshapes prices into
a table of days (rows) by hours (columns). Then `m.shift(1)` means "yesterday's row",
`m.shift(7)` means "same weekday last week".
`tests/test_features.py::test_no_leakage_from_target_day` proves the rule holds: it
changes one day's prices to 9999 and checks that this day's own features do not move.

**Group 2: forecasts of solar, wind and demand for the target day (`EXOG_FEATURES`).**
Prices are low when there is a lot of wind and sun and little demand. The grid operators
publish forecasts of all three, one day ahead. Using a *forecast* of tomorrow is not
leakage, because it exists before tomorrow happens. The key derived feature is
**residual load** = demand − wind − solar: the electricity that conventional power
plants still have to produce. The higher it is, the more expensive plants are needed.

**The open question you must be able to discuss.** Is tomorrow's forecast already
published when the morning job runs? The history from the API cannot tell you: it shows
the forecast, not when it appeared. If the forecast only appears in the afternoon, then
a backtest that uses it is too optimistic, because in real life the model would not
have had it. Two things are in place for this:

1. The daily job runs twice each morning. If the forecasts are missing, the model that
   needs them (`gbm_exog`) is skipped and the simpler model (`gbm`) is used.
2. The `exog_seen` dataset records the moment each forecast value was first seen by
   your job. After a few weeks you can answer the question with your own evidence.
   (Rows from the history download all carry the download date; only rows from daily
   runs are informative.)

**Check yourself**
- On the last Sunday of March the day has 23 hours. What does `to_matrix` do about it?
- Why is `lag_7d` a useful feature at all?
- Explain residual load to a friend in two sentences.
- Why would a backtest be "too optimistic" if the forecasts are published after noon?
- Query `exog_seen` after two weeks: on how many mornings was tomorrow's forecast there in time?

## 6. `models.py`: baselines first

Four models with the same interface:

- `naive_yesterday`: tomorrow at 14:00 = today at 14:00.
- `naive_last_week`: tomorrow at 14:00 = same weekday last week at 14:00.
- `gbm`: gradient-boosted trees on past prices and calendar, untuned.
- `gbm_exog`: the same, plus the solar, wind and demand forecasts.

A model only means something relative to a baseline. "MAE of 12" says nothing. "25%
better than the naive forecast" says a lot. That is the `skill_vs_naive` column.

To try an idea of your own, add one line to `MODELS`. Everything else picks it up.

**Check yourself**
- In plain words, how does gradient boosting build its prediction?
- The model uses `loss="absolute_error"`. What would change with squared error, and which price hours would it care more about?
- Why does `fit` drop features that have no values at all?

## 7. `backtest.py`: honest evaluation

A random train/test split is wrong for time series, because the model would train on
days *after* the ones it is tested on. Instead we walk forward: train on everything up
to a date, predict the next 7 days, move on, retrain, repeat.

**Check yourself**
- Find the line that guarantees training data is strictly before the test block.
- Why do we refit every 7 days instead of every day or only once?

## 8. `window.py`: your own metric

`best_window` finds the cheapest block of N hours (or, with `largest=True`, the block
with the highest value, used for the greenest hours). `window_regret` asks: if I trust
the forecast, how much more do I pay than someone who knew the future?

This is the part of the project that is most *yours*: a metric designed for the question
instead of a default one. Expect to be asked about it.

**Check yourself**
- Construct by hand a forecast with a large MAE but zero regret.
- Is a regret of 9 EUR/MWh a lot? Convert it to cents for one 1 kWh wash. (Then think about whether that changes how you tell the story.)

## 9. `experiment.py`: the lab notebook

`python -m powerhours.experiment run --name "..." --notes "..."` backtests every model
and appends the scores to `experiments/log.jsonl`, with the date, the git commit and the
feature list. You can also start it from GitHub (Actions tab, "Run experiment").

The log is the honest history of the project. Do not delete runs that went badly.

**Check yourself**
- Why is the git commit stored with every run?
- If you try 30 ideas and report the best one, why might its score be too good? What would protect you? (Hint: a final test period you only touch once.)

## 10. `green.py`: cheap versus green

"Green" is measured as the renewable share of load: the percentage of the electricity
being used that renewables are covering in that hour. `cheap_vs_green` finds, for every
day, the cheapest window and the greenest window and compares them.
`price_by_share_bucket` shows the average price for each band of renewable share.

**Check yourself**
- The share can be above 100%. What is happening physically in such an hour?
- On a day when cheapest and greenest differ, what might be the reason?

## 11. `forecast.py`: the daily job

Makes tomorrow's forecast with every model that can run and saves it. Safeguards that
keep the track record honest:

- A saved forecast is never overwritten (`store.insert_new`: first write wins).
- Each row records `made_at_utc` and `before_auction`. Late forecasts are stored but excluded from the score.
- `latest_forecast` shows `gbm_exog` if it ran, otherwise `gbm`.

**Check yourself**
- Why is it tempting, and wrong, to regenerate old forecasts after improving the model?

## 12. `briefing.py`: using an LLM responsibly

Read the comment at the top of the file. The design in one sentence: **the code computes,
the LLM only phrases, and a check verifies.**

- `build_facts` produces a small dictionary of numbers. This is all the LLM sees.
- `call_claude` sends the facts with strict instructions.
- `check_grounding` pulls every number out of the answer and rejects the text if a
  number is not among the facts, or the cheapest start time is missing.
- If anything fails, `template_briefing` is used. The daily job cannot break because of the LLM.
- Every attempt is logged with its facts and check result in `data/public/briefing/`.

Know the limits: the check catches invented numbers. It does not catch a sentence that
puts a correct number in the wrong place ("the *most expensive* time is 03:00").

**Check yourself**
- Why not just give the LLM the raw price table and ask "when should I wash"?
- Think of a wrong briefing that would pass the check. How could you catch it?
- After a month: what share of LLM texts passed? Read the rejected ones. What went wrong?

## 13. `.github/workflows/`: automation

- `ci.yml` runs the linter and the tests on every push. A green tick on the repository shows the code works.
- `daily.yml` runs twice every morning: download, forecast, briefing, commit.
- `backfill.yml` downloads history. You start it by hand; it has already been run.
- `experiment.yml` runs a logged backtest. You start it by hand.

**Check yourself**
- What does `permissions: contents: write` allow, and why is it needed?
- What happens if the API is down one morning? What is lost, and what is recovered the next day?
- Why are there two runs each morning?

## 14. `tests/`

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
