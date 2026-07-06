# Research: designing an AI-authored weekly job-displacement forecast

Deep research conducted while designing this site (July 2026; ~25 sources across five
angles, claims adversarially spot-checked). This document records what the evidence
says and which design decisions in this repository follow from it.

---

## 1. Taxonomy: what unit should the forecast be about?

**What serious indices do.** The rigorous exposure indices are built on standardized
occupation codes scored at the *task* level: the ILO's generative-AI exposure index
scores ISCO-08 occupations from task-level GPT-4 ratings, benchmarked against 52,558
human survey judgments and Delphi-style expert rounds ([ILO][ilo]); Anthropic's
Economic Index and labor-market research map real AI conversations onto the US O*NET
taxonomy (900+ occupations, ~20,000 tasks) ([AEI][aei], [labor report][labor]);
European work crosswalks US scores to 3-digit ISCO-08 (~130 groups) as the practical
internationally legible granularity ([Bruegel][bruegel]).

**Why we still chose ~74 coarse, named categories.** Fine-grained codes are for
measurement; this site is a public ritual. Occupation rankings with single percentage
scores are demonstrably the format that travels ("computer programmers: 74.5%
exposed" led the coverage of Anthropic's labor report). Our categories are loosely
aligned with SOC/ISCO major groups but named for recognizability ("Long-Haul Truck
Drivers", not "53-3032 Heavy and Tractor-Trailer Truck Drivers"). IDs are stable so
the history stays joinable, and the taxonomy can be refined without breaking it.

**The task-vs-occupation trap.** The strongest warning in the literature: occupation-
level automation probabilities systematically overstate displacement because
occupations hide hard-to-automate task residue. A task-based OECD approach found ~9%
of jobs highly automatable where the occupation-based approach (Frey & Osborne) said
47% ([OECD 2016][oecd16]). Anthropic's usage data shows AI use is diffuse: only ~4%
of occupations show AI use on ≥75% of their tasks ([AEI][aei]).
**Design consequence:** every probability on the site answers a *task-majority +
falling-hiring* question, stated verbatim above the ranking table — never "chance the
job is gone."

## 2. Presentation: what makes probabilistic forecasts legible and recurring

- **A crisp, checkable target definition.** AI 2027's timeline forecast works because
  every probability is anchored on one concretely operationalized milestone rather
  than vague capability language ([AI 2027][ai2027]). → Our displacement definition is
  a single sentence displayed on the page and embedded in the prompt.
- **Probability + horizon year** is the reusable pattern (distributions over arrival
  years with headline medians). → We publish four horizons (2027/2030/2035/2040) with
  a horizon toggle, medians as headline numbers.
- **Banded gradients complement point numbers.** The ILO deliberately publishes four
  tiered exposure gradients per occupation rather than bare percentages (confirmed
  3–0 in verification). → Each row carries a band chip (Low / Guarded / Elevated /
  High / Critical) alongside the exact percentage.
- **Scarcity of movement is what makes movement news.** The Doomsday Clock's hand has
  moved only 27 times since 1947; most updates are "no change", which is precisely why
  a move is a headline ([Bulletin][clock]). → The pipeline instructs Bayesian
  stability (move only on evidence), the ensemble median suppresses sampling noise,
  and the page leads with deltas and "biggest mover" tiles — so a 2-point move reads
  as signal.
- **A named, ritual cadence.** The Clock is an annual event by a named body; election
  forecasts built rituals around continuous updates with uncertainty made visceral
  (FiveThirtyEight's design writing on communicating uncertainty). → Fixed Monday
  06:00 UTC publication, a visible countdown to the next update, and a first-person
  weekly headline quote as the shareable artifact.

## 3. Eliciting calibrated probabilities from an LLM

- **Ensembles work.** An ensemble of twelve LLMs matched a 925-person human forecaster
  crowd on real tournament questions ([Schoenegger et al.][wisdom]). → We ensemble 5
  independent runs and publish the median, keeping run-to-run spread in the data.
- **Expect upward bias.** LLM forecasters show systematic acquiescence: mean
  probabilities sit significantly above 50% on question sets that resolve ~50/50
  ([same study][wisdom]). And the base-rate evidence says high-risk labels historically
  meant *slower growth*, not job destruction — across 21 OECD countries, a decade of
  "high automation risk" produced no net job destruction ([OECD 2021][oecd21]).
  → The system prompt now contains explicit debiasing rules: respect the
  exposure-to-displacement conversion lag, and err lower when evidence is thin.
- **Anchoring on reference forecasts improves calibration** (17–28% Brier improvement
  when models saw a crowd median) ([wisdom]). → Each weekly run sees last week's
  published numbers as its anchor, with license to correct miscalibration.
- **Avoid contamination; build a track record.** ForecastBench keeps LLM forecasting
  honest by only scoring questions unresolved at submission time ([ForecastBench][fb]).
  → Every weekly snapshot is committed immutably; the site's history *is* the model's
  auditable track record, including what it gets wrong.
- **Fresh evidence is the only honest reason weekly numbers move.** A model's
  parametric knowledge is frozen; without new input, weekly deltas would be sampling
  noise dressed as news. → The pipeline's first step is a live web-search scan whose
  digest conditions every forecast run.

## 4. Positioning "the AI's own guess"

- **Precedent for disclaiming authority while communicating risk.** The Bulletin
  explicitly frames the Clock as a metaphor, not a prediction — and it works as a
  global attention ritual anyway ([clock]). → The site pairs its confident first-person
  numbers with a plain disclaimer: an AI's self-assessment is a striking perspective,
  not a labor-market authority; it can be self-serving and miscalibrated in both
  directions.
- **Exposure ≠ replacement, say so.** The ILO explicitly cautions that its numbers
  measure potential exposure and transformation, not replacement (confirmed 3–0).
  → Our definition strip and disclaimer draw the same line.
- **The no-citation rule is a positioning feature, not spin.** The model is
  instructed that everything it has read informs it but the published number is its
  own — and never to attribute numbers to named studies or consultancies. This is
  what differentiates the site from yet another study aggregator, and it is stated
  openly in the methodology so readers know exactly what they're looking at.

## 5. Architecture

The zero-maintenance pattern is well-established ("git scraping": scheduled GitHub
Action fetches/produces data, commits JSON, static site renders it — [Simon
Willison][gitscrape], productized as [Flat Data][flat]). Operational caveats folded
into our workflows: cron is UTC and can be delayed/skipped under load; keep
`workflow_dispatch` for manual recovery; repos inactive for 60 days get their
schedules disabled (our weekly bot commit keeps the repo active); pushes made with
`GITHUB_TOKEN` don't trigger other workflows, so deploy is chained explicitly after
the forecast job.

---

## What changed in this repo because of the research

| Finding | Change |
|---|---|
| Occupation-level probabilities overstate displacement (OECD, ILO, AEI) | Task-majority + falling-hiring definition, shown verbatim above the table; base-rate rule added to the forecaster prompt |
| LLM forecasters skew high / acquiesce | Explicit downward-correction rule in the prompt; median-of-ensemble publishing |
| Banded gradients aid legibility (ILO) | Low→Critical band chips beside each percentage |
| Rare moves are the news (Doomsday Clock) | Bayesian-stability instruction + delta-led layout; "no moves" is a valid week |
| Anchoring improves calibration | Last week's numbers passed into every run |
| Track record integrity (ForecastBench) | Immutable weekly snapshots in `data/history/` |
| Ritual cadence | Fixed Monday publication + on-page countdown |

[ilo]: https://www.ilo.org/publications/generative-ai-and-jobs-refined-global-index-occupational-exposure
[aei]: https://www.anthropic.com/news/the-anthropic-economic-index
[labor]: https://www.anthropic.com/research/labor-market-impacts
[bruegel]: https://www.bruegel.org/system/files/2024-03/WP%2006.pdf
[oecd16]: https://www.oecd.org/en/publications/the-risk-of-automation-for-jobs-in-oecd-countries_5jlz9h56dvq7-en.html
[oecd21]: https://www.oecd.org/content/dam/oecd/en/publications/reports/2021/01/what-happened-to-jobs-at-high-risk-of-automation_ffdb138f/10bc97f4-en.pdf
[ai2027]: https://ai-2027.com/research/timelines-forecast
[clock]: https://thebulletin.org/doomsday-clock/
[wisdom]: https://arxiv.org/abs/2402.19379
[fb]: https://arxiv.org/abs/2409.19839
[gitscrape]: https://simonwillison.net/2020/Oct/9/git-scraping/
[flat]: https://githubnext.com/projects/flat-data/
