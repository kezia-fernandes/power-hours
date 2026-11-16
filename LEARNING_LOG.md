# Learning log

Short dated notes: what I decided, what broke, what I learned. Rewrite the first entry
in your own words once you have read the code, and delete this line.

## 2026-11-16: starting point

**Idea.** My aunt in Norway runs her washing machine at night because power is cheaper.
Is that also true in Germany? An AI assistant suggested electricity price forecasting as
a project; the Norway comparison and the washing-machine question are my angle on it.

**Built today (with Claude, in one session).** Project skeleton: API client, storage,
features, two naive baselines plus gradient boosting, walk-forward backtest, daily
forecast job, tests, CI, dashboard skeleton. The history download (German prices since
2024-01-01) and the first daily forecast ran successfully on GitHub Actions.

**Decisions made today and why.**

- *Data source: Energy-Charts API (Fraunhofer ISE).* Free, no API key, covers Germany and Norway.
- *Parquet files per month instead of a database file.* Only one small file changes per
  day, so the daily job can commit data to git.
- *Hourly averages instead of 15-minute prices.* Simpler to start with. Might revisit.
- *Custom metric "window regret".* MAE measures price accuracy, but my question is about
  choosing the right hours.
- *Forecasts are saved and never overwritten.* Otherwise the track record would not be honest.

**Surprise of the day.** Open data is not always open. German prices are CC BY 4.0, but
the Norwegian prices from the same API are restricted to private use. The code now
separates public and private data automatically, and Norwegian data stays out of the repository.

**First real backtest (last 90 days, Germany, 2-hour window).**

| model | MAE (EUR/MWh) | RMSE | window regret | hit rate |
|---|---|---|---|---|
| naive_yesterday | 44.9 | 63.8 | 10.0 | 36% |
| gbm (untuned) | 45.1 | 59.4 | 8.9 | 32% |
| naive_last_week | 67.5 | 91.7 | 9.3 | 32% |

The untuned model does not beat "same as yesterday" on MAE. It is slightly better on
RMSE and window regret. This is the baseline to beat.

**Data note.** Prices are hourly until October 2025 and every 15 minutes after that.

**Open questions.**

- Why is the untuned model no better than "same as yesterday"? What is it missing?
- Which Norwegian zone does my aunt live in?
- How will I present the Norway comparison publicly, given the licence?

## 2026-11-16 (later): extending the project

**Added (with Claude, same evening).** Generation mix and the grid operators' day-ahead
forecasts of solar, wind and demand; a second model that uses them (`gbm_exog`); an
experiment log; the cheap-versus-green analysis; a redesigned dashboard; a daily briefing
written by an LLM and checked against the computed numbers.

**Experiment "baseline" (last 180 days, Germany, 2-hour window).**

| model | MAE (EUR/MWh) | skill vs naive | window regret | hit rate |
|---|---|---|---|---|
| gbm_exog | 25.3 | +31% | 2.2 | 52% |
| gbm | 33.0 | +10% | 5.3 | 41% |
| naive_yesterday | 36.5 | 0 | 6.2 | 43% |
| naive_last_week | 51.2 | -40% | 6.3 | 35% |

Adding the renewable forecasts cut the error by about a third and the window regret by
almost two thirds. **Caveat:** this assumes the forecasts for tomorrow are published
before the morning run. On the evening of 16 November they reached only to the end of
17 November, so for the 18 November forecast `gbm_exog` could not run yet. Whether they
appear in time each morning is not known. The `exog_seen` data will show it.

**First look at the data (to be checked and explained by me).**

- Since 2024, the cheapest hours in Germany on average are around 13:00, not at night.
  The most expensive are around 19:00.
- Price and renewable share move in opposite directions (correlation about -0.7).
- The cheapest and the greenest 2-hour window overlap on about three days out of four.
- Prices in autumn 2026 are far higher than in 2024. I do not know why yet.

**Things that went wrong today.**

- The API's combined "wind" forecast has no history. Fixed by downloading onshore and
  offshore separately and adding them.
- The model crashed on a feature column with no values at all. Fixed by dropping such
  columns at training time.

**Decisions and why.**

- *The LLM never computes.* Code produces the facts, the LLM phrases them, a check
  verifies every number, and a template is the fallback.
- *Own experiment log instead of MLflow.* One small file I can read and explain.
- *Generation data stored hourly.* The model works hourly and the repository stays small.

**Open questions.**

- Are the solar/wind/demand forecasts available before noon? (Roadmap step 3.)
- How often will the LLM briefing pass the check?

## Template for new entries

## YYYY-MM-DD: title

**What I did.**

**What I expected / what happened.**

**What I learned.**

**Next.**
