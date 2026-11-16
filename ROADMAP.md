# Roadmap: what is left, and all of it is yours

The skeleton runs. Everything below is where the project becomes your work. Do the
steps in order. After each one, write a few lines in `LEARNING_LOG.md`.

## Step 0: get it running (this week, about 2 hours)

- [x] Create a GitHub repository, put this folder in it, push. (done 2026-11-16)
- [ ] Clone the repository to your computer (`git clone`), so you work on the same copy.
- [ ] Set up Python and run the commands in the README. All tests should pass.
- [x] Backfill for Germany from 2024-01-01 (done on GitHub via the "Backfill history"
      workflow; the data is in `data/public/`, so you do not need to download it again).
- [ ] Run the backfill for Norway (`--zone NO2`, or the zone where your aunt lives).
      Check that it lands in `data/private/` and that `git status` does not show it.
- [x] Run "Daily forecast" by hand once (done; it now runs by itself every morning).
- [ ] Check the Actions tab after a few days: is there a green run for every morning?
- [ ] Choose a licence for your code (MIT is the usual choice) and add a `LICENSE` file.

From this day on the forecast history grows by itself. The earlier you do step 0, the
longer your live track record will be when you apply.

## Step 1: understand it (week 1)

- [ ] Work through `WALKTHROUGH.md` and answer every "Check yourself" question in writing.
- [ ] Break something on purpose (for example change `shift(1)` to `shift(0)` in
      `features.py`), run the tests and the backtest, and see what happens. Then undo it.

## Step 2: explore the data (weeks 2 to 3) — the core of your story

Make a notebook `notebooks/01_exploration.ipynb`. Questions to answer with charts:

- [ ] What does a typical day look like in Germany? Summer vs winter? Weekday vs weekend?
- [ ] The same for Norway. Is your aunt right? Is night really cheapest there?
- [ ] Is night the cheapest time in Germany too, or is it midday? Why might the two differ?
      (Look at how each country produces its electricity.)
- [ ] How often are German prices negative? At which hours and in which months?
- [ ] How much could a household really save by shifting one wash per day? Be honest
      about the size of the number, and about what households actually pay (most have
      a fixed tariff, only some have a dynamic one).

Write the answers down. This is the "Results" section of your README.

## Step 3: make the model better (weeks 3 to 5)

Run `python -m powerhours.backtest --days 180` first and save the output: that is the
number to beat.

- [ ] Add wind and solar. Prices are low when renewables are high. The API has forecasts
      for tomorrow (`public_power_forecast` with `production_type` solar, wind, load).
      Think carefully: which values are really available in the morning of the day before?
- [ ] Add German public holidays.
- [ ] Try one other model family (for example a linear model, or one model per hour).
- [ ] Tune the gradient boosting a little. Keep a separate final test period that you
      never use for tuning.
- [ ] Look at the errors. When is the model worst? Which hours, which kinds of days?

Keep a table of every experiment, including the ones that did not help. Failed
experiments described honestly impress interviewers.

## Step 4: the green question (week 6, optional but fits you)

- [ ] Ingest the generation mix (`--with-power`) and compute the renewable share per hour.
- [ ] Are the cheapest hours also the greenest? Always, or only sometimes?
- [ ] Add a "greenest window" recommendation next to the cheapest one.

## Step 5: dashboard and deployment (week 7)

- [ ] Redesign the dashboard so a stranger understands it in 10 seconds.
- [ ] Deploy it on Streamlit Community Cloud (free) and put the link in the README.
- [ ] Before making anything Norwegian public: read the licence terms yourself and decide
      what you may show. If in doubt, check whether ENTSO-E's Transparency Platform
      offers the same prices under terms that allow publishing, or publish only your
      written findings.

## Step 6: tell the story (week 8)

- [ ] Fill in the README: screenshot, results, what you learned, limitations.
- [ ] Draw an architecture diagram.
- [ ] Write a short post (LinkedIn or a blog) about one finding.
- [ ] Practise a two-minute explanation of the project out loud.

## Questions you should be able to answer in an interview

1. Why this project?
2. What is data leakage and how do you prevent it here?
3. Why is your model better than the naive baseline, and by how much?
4. What is window regret and why did you need it?
5. What did not work?
6. Which parts did AI write, and how did you make sure they are correct?
7. What would you do next with more time?
