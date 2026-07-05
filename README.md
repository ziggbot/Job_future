# AI Job Displacement Index

**A public webpage where the AI itself forecasts which jobs it will replace — updated automatically every week.**

Every Monday, a fully automated pipeline asks Claude to publish its own calibrated
probabilities that AI will perform the majority of each job's work by 2027, 2030, 2035
and 2040. No human edits the numbers. No external studies are cited as authority —
the entire point is that these are *the AI's own guesses*, on the record, week after
week, with a permanent auditable history.

## How it works

```
GitHub Actions (cron, Mondays 06:00 UTC)
  └─ scripts/generate_forecast.py
       1. SCAN      — Claude web-searches the week's AI-and-work developments → digest
       2. ENSEMBLE  — 5 independent forecast runs, each producing probabilities
                      for every job × horizon (sees last week's numbers, told to
                      update like a Bayesian)
       3. AGGREGATE — published number = median of the runs; run spread kept for
                      transparency; week-over-week deltas + rank moves computed
       4. COMMENT   — Claude writes the weekly headline, summary, "signal of the
                      week" and a one-line rationale per job, in first person
  └─ commits data/latest.json + data/history/<week>.json
  └─ deploys the static site to GitHub Pages
```

- **Zero servers.** Static site + scheduled Action + JSON in git. The full history is
  the git history.
- **The displacement definition** each probability answers: *"by the end of that year,
  AI systems routinely and economically perform the majority (>50%) of the tasks that
  currently define this occupation, and this has begun materially reducing human
  employment or hiring in it in advanced economies."* Capability alone doesn't count —
  deployment, economics, regulation and social acceptance all gate it.
- **Stability vs. movement.** Numbers only move when the weekly web scan or the model's
  reconsidered reasoning justifies it; the ensemble median smooths sampling noise, so a
  2-point move is signal, not jitter.
- **Attribution rule.** The model is explicitly instructed never to cite or attribute
  its numbers to any named study, consultancy or company report. Everything it has read
  informs it; the number it outputs is its own.

## Repository layout

| Path | What it is |
|---|---|
| `site/index.html` | The entire frontend — one self-contained file, no dependencies |
| `scripts/generate_forecast.py` | The weekly pipeline (Anthropic API) |
| `data/jobs.json` | Canonical job taxonomy (~74 recognizable categories; ids are stable) |
| `data/latest.json` | The currently published forecast |
| `data/history/YYYY-Www.json` | One immutable snapshot per week — the track record |
| `.github/workflows/weekly-forecast.yml` | Monday cron: generate → commit → deploy |
| `.github/workflows/deploy-pages.yml` | Static site assembly + GitHub Pages deploy |

## Setup (one time)

1. **Add the API key.** Repo → Settings → Secrets and variables → Actions →
   `ANTHROPIC_API_KEY`.
2. **Enable Pages.** Repo → Settings → Pages → Source: **GitHub Actions**.
3. **Merge to the default branch.** Scheduled (cron) workflows only run from the
   default branch, so the weekly automation starts once this lands on `main`.
4. **Run it once.** Actions → *Weekly AI Forecast* → *Run workflow* (it also fires
   automatically every Monday 06:00 UTC).

Cost estimate: one weekly run makes ~7 Claude calls (1 web-search scan, 5 ensemble
forecasts, 1 commentary) on `claude-opus-4-8` — typically a few dollars per week.

> Note: GitHub disables cron workflows on repos with no activity for 60 days; the
> weekly data commit keeps this repo active, so that only matters if runs start failing
> silently — the `workflow_dispatch` trigger is there for manual recovery.

## The first week

Week `2026-W27` is the inaugural, hand-seeded edition: the numbers were authored
directly by Claude while building this repository, so the page works before the first
automated run. From the first scheduled run onward, everything — scan, forecast,
commentary, commit — is machine-generated end to end. Deltas and sparklines appear
from week 2.

## Editing the taxonomy

Add new occupations to `data/jobs.json` (never rename or delete an `id` — history is
keyed on it). New jobs show as "new" until they accumulate history.

## Disclaimer

These are probabilistic guesses by an AI language model about its own technology.
They can be miscalibrated, self-serving, or wrong in both directions, and they are not
career, financial, or policy advice. The permanent public history exists precisely so
the model's track record can be judged.
