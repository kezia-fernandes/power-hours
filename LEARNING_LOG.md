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

## Template for new entries

## YYYY-MM-DD: title

**What I did.**

**What I expected / what happened.**

**What I learned.**

**Next.**
