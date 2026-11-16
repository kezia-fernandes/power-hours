# Roadmap: what is left, and all of it is yours

The system runs by itself. Everything below is where the project becomes your work.
Do the steps in order. After each one, write a few lines in `LEARNING_LOG.md`.

## Already done (2026-11-16)

- [x] Repository on GitHub, tests and checks passing
- [x] History downloaded: German prices, generation mix, solar/wind/demand forecasts since 2024
- [x] Daily job running twice every morning: data, forecast, briefing
- [x] Experiment log, green analysis, dashboard, LLM briefing with number check

## Step 0: set up (this week, about 2 hours)

- [ ] Clone the repository to your computer: `git clone https://github.com/kezia-fernandes/power-hours`
- [ ] Set up Python and run the commands in the README. All tests should pass.
- [ ] Look at the dashboard locally: `streamlit run app/streamlit_app.py`
- [ ] **Turn on the LLM briefing.** Create an API key at console.anthropic.com (this costs
      money, but a few sentences a day with a small model is very little; set a low
      spending limit). Then on GitHub: repository Settings → Secrets and variables →
      Actions → New repository secret, name `ANTHROPIC_API_KEY`. Never put the key in
      a file or a chat. Until you do this, the briefing uses the fixed template.
- [ ] Run the backfill for Norway on your computer (`--zone NO2`, or the zone where your
      aunt lives). Check that it lands in `data/private/` and that `git status` does not show it.
- [ ] Choose a licence for your code (MIT is the usual choice) and add a `LICENSE` file.
- [ ] Check the Actions tab after a few days: is there a green run for every morning?

## Step 1: understand it (weeks 1 to 2)

- [ ] Work through `WALKTHROUGH.md` and answer every "Check yourself" question in writing.
- [ ] Break something on purpose (for example change `shift(1)` to `shift(0)` in
      `features.py`), run the tests and the backtest, and see what happens. Then undo it.

## Step 2: explore the data (weeks 2 to 3) — the core of your story

Make a notebook `notebooks/01_exploration.ipynb`. Questions to answer with charts:

- [ ] What does a typical day look like in Germany? Summer vs winter? Weekday vs weekend?
- [ ] The same for Norway. Is your aunt right? Is night really cheapest there?
- [ ] In Germany, is night the cheapest time, or midday? Why might the two countries differ?
      (Compare how each country produces its electricity: the generation mix is in the data.)
- [ ] How often are German prices negative? At which hours and in which months?
- [ ] Prices in autumn 2026 are much higher than in 2024. Find out why. (This is research,
      not code: read the news.)
- [ ] How much could a household really save by shifting one wash per day? Be honest
      about the size of the number, and about what households actually pay (most have
      a fixed tariff, only some have a dynamic one).

Write the answers down. This is the "Results" section of your README.

## Step 3: answer the availability question (after 2 to 3 weeks of daily runs)

- [ ] Query the `exog_seen` data: on how many mornings were tomorrow's solar, wind and
      demand forecasts published before the job ran? Before noon?
- [ ] If they are reliably there: good, say so with numbers.
- [ ] If they are not: the backtest of `gbm_exog` is too optimistic. The honest fix is a
      source that is certainly available in the morning, for example weather forecasts
      (wind speed, sunshine) from a free weather API. Build that as a new feature group.

Whatever the answer, this is your best interview story: "I checked whether my best
feature would really have been available, and here is what I found."

## Step 4: make the model better (weeks 3 to 6)

The experiment log has the starting numbers. Every idea = one logged experiment.

- [ ] Add German public holidays.
- [ ] Try one other model family (for example a linear model, or one model per hour).
- [ ] Tune the gradient boosting a little.
- [ ] Decide on a final test period that you never use while trying ideas, and report
      your final model on it exactly once.
- [ ] Look at the errors. When is the model worst? Which hours, which kinds of days?
- [ ] Prices changed a lot between 2024 and 2026. Is it better to train on all history
      or only on the most recent months?

Keep the failed experiments in the log. Described honestly, they impress interviewers.

## Step 5: improve the LLM part (week 6)

- [ ] After a month, read `data/public/briefing/DE-LU.jsonl`. What share of LLM texts
      passed the check? What went wrong in the rejected ones?
- [ ] Find a wrong briefing that would pass the check, then improve the check to catch it.
- [ ] Try a different prompt and compare pass rates. That is an LLM evaluation.

## Step 6: dashboard and deployment (week 7)

- [ ] Deploy the dashboard on Streamlit Community Cloud (free) and put the link in the
      README. `requirements.txt` is prepared but untested there.
- [ ] Improve the dashboard where a stranger gets confused. Ask a friend to try it.
- [ ] Before making anything Norwegian public: read the licence terms yourself and decide
      what you may show. If in doubt, check whether ENTSO-E's Transparency Platform
      offers the same prices under terms that allow publishing, or publish only your
      written findings.

## Step 7: tell the story (week 8)

- [ ] Fill in the README: screenshot, results, what you learned, limitations.
- [ ] Draw an architecture diagram.
- [ ] Write a short post (LinkedIn or a blog) about one finding.
- [ ] Practise a two-minute explanation of the project out loud.

## Questions you should be able to answer in an interview

1. Why this project?
2. What is data leakage and how do you prevent it here?
3. Is your best feature really available when you forecast? How do you know?
4. Why is your model better than the naive baseline, and by how much?
5. What is window regret and why did you need it?
6. How do you stop the LLM from saying something false?
7. What did not work?
8. Which parts did AI write, and how did you make sure they are correct?
9. What would you do next with more time?
