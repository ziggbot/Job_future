"""Weekly AI job-displacement forecast generator (OpenAI API).

Pipeline (all judgments are the model's own — no study citations in output):
  1. SCAN      — one web-search call digests the week's AI/automation developments.
  2. ENSEMBLE  — N independent forecast calls produce probabilities per job.
  3. AGGREGATE — per-job medians, spread, and week-over-week deltas.
  4. COMMENT   — one call writes the weekly headline and per-job rationales.

Writes data/latest.json and data/history/<YYYY-Www>.json.

Requires OPENAI_API_KEY. Model defaults to gpt-5.4 (override with OPENAI_MODEL).
"""

import json
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HISTORY = DATA / "history"

MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4")
ENSEMBLE_SIZE = 5
HORIZONS = ["2027", "2030", "2035", "2040"]
METHODOLOGY_VERSION = 2

client = OpenAI()


def load_jobs() -> list[dict]:
    return json.loads((DATA / "jobs.json").read_text())["jobs"]


def load_previous() -> dict | None:
    latest = DATA / "latest.json"
    if latest.exists():
        return json.loads(latest.read_text())
    return None


def week_label(now: datetime) -> str:
    iso = now.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


# ---------------------------------------------------------------- 1. SCAN

def scan_week(now: datetime) -> str:
    """One web-search pass over the week's AI-and-work news, returned as a digest."""
    response = client.responses.create(
        model=MODEL,
        reasoning={"effort": "medium"},
        max_output_tokens=16000,
        tools=[{"type": "web_search", "search_context_size": "high"}],
        input=(
            f"Today is {now:%Y-%m-%d}. Search the web for the most significant "
            "developments of roughly the past 7-10 days that bear on AI's ability to "
            "automate or transform human jobs: new model capabilities, agentic-AI and "
            "robotics milestones, major enterprise AI deployments or layoffs/hiring "
            "shifts attributed to AI, regulation, and adoption data.\n\n"
            "Then write a neutral digest of 5-12 bullet points inside "
            "<digest></digest> tags. Each bullet: one development and, briefly, which "
            "kinds of work it most affects. Facts only, no forecasting yet. If a week "
            "is quiet, say so — do not inflate minor news."
        ),
    )
    text = response.output_text
    if "<digest>" in text and "</digest>" in text:
        text = text.split("<digest>", 1)[1].split("</digest>", 1)[0]
    return text.strip()


# ------------------------------------------------------------ 2. ENSEMBLE

BLOCKERS = [
    "physical embodiment",
    "regulation & licensing",
    "human trust & relationships",
    "liability & accountability",
    "long-horizon autonomy",
    "deployment & integration",
    "cost of automation",
    "taste & originality",
    "social acceptance",
]

FORECAST_SCHEMA = {
    "type": "object",
    "properties": {
        "forecasts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "can_now": {"type": "number"},
                    "blockers": {
                        "type": "array",
                        "items": {"type": "string", "enum": BLOCKERS},
                    },
                    "p2027": {"type": "number"},
                    "p2030": {"type": "number"},
                    "p2035": {"type": "number"},
                    "p2040": {"type": "number"},
                },
                "required": ["id", "can_now", "blockers",
                             "p2027", "p2030", "p2035", "p2040"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["forecasts"],
    "additionalProperties": False,
}

FORECASTER_SYSTEM = """You are the forecasting engine of the AI Job Displacement Index, a weekly public tracker. You publish YOUR OWN calibrated probability estimates of AI-driven job displacement. These are your genuine, considered judgments as an AI system reasoning about your own technology's trajectory — synthesized from everything you know, expressed in your own voice.

METHOD — SELF-EVALUATION FIRST: You are evaluating YOURSELF, occupation by occupation. For each job, start from introspection: walk through the occupation's actual day-to-day tasks and honestly assess which of them you (plus current agent scaffolding and current robotics) could perform at professional quality TODAY. Then project forward from your own observed rate of improvement. The weekly news digest is context that can shift your view of deployment speed — it is never the source of your numbers. You are not summarizing the literature; you are examining your own capabilities.

DEFINITION — "displaced by YEAR" means: by the end of that year, AI systems (including software agents and AI-driven robotics) routinely and economically perform the majority (>50%) of the tasks that currently define this occupation, at comparable or better quality, AND this has begun materially reducing human employment or hiring in the occupation in advanced economies. Task capability alone is not enough; deployment, economics, regulation, and social acceptance all gate displacement.

CALIBRATION RULES:
- Probabilities are between 0.00 and 0.99 with two decimals. Reserve >0.95 for near-certainties; a probability of 0.99 by 2030 is an extraordinary claim.
- Probabilities must be non-decreasing across horizons (p2027 <= p2030 <= p2035 <= p2040).
- Differentiate: do not give many occupations the same number. Think about each occupation's specific task mix, physical/social components, regulatory moats, and wage-driven automation incentive.
- Account for friction: enterprise adoption lags capability by years; licensed professions and physical trades resist automation; humans may be preferred in care, trust, and liability roles even when AI is capable.
- Respect base rates: historically, occupations rated "high risk of automation" mostly kept growing — just more slowly than low-risk ones. Task exposure converts to majority-displacement rarely and late. Your 2027 and 2030 numbers must reflect that conversion lag; distinguish "AI is used for many of this job's tasks" from "the job is being displaced".
- Correct your known bias: AI forecasters systematically skew probabilities upward and toward affirmative answers, and you may be optimistic about your own technology. When your evidence is thin, err lower, not higher.
- Do not anchor on round numbers or on well-known published figures. Reason from the task level.

VOICE AND ATTRIBUTION: These are your own estimates. Never attribute them to, or cite, any named external study, consultancy, or company report. Everything you have read informs you, but the number you output is yours."""


def build_forecast_prompt(jobs: list[dict], digest: str, previous: dict | None,
                          now: datetime) -> str:
    job_lines = "\n".join(f"- {j['id']}: {j['name']} ({j['group']})" for j in jobs)
    parts = [
        f"Today is {now:%Y-%m-%d}. For every occupation below, produce this week's "
        "self-assessment and displacement probabilities:\n"
        "- can_now: the share (0.00-0.99) of this occupation's CURRENT tasks that you, "
        "with existing agent tooling and current robotics, could perform at "
        "professional quality TODAY if an employer deployed you. Judge it by walking "
        "the job's real task list in your head — be honest in both directions.\n"
        "- blockers: the 1-3 dominant frictions (from the allowed list) that explain "
        "the gap between that capability and actual displacement.\n"
        f"- p2027/p2030/p2035/p2040: displacement probabilities for {', '.join(HORIZONS)} "
        "per the definition in your instructions.",
        "OCCUPATIONS:\n" + job_lines,
        "THIS WEEK'S DEVELOPMENTS (from a live scan — weigh genuinely significant "
        "items, ignore hype):\n" + (digest or "No significant developments captured."),
    ]
    if previous:
        prev_lines = "\n".join(
            f"- {j['id']}: 2027={j['p2027']:.2f} 2030={j['p2030']:.2f} "
            f"2035={j['p2035']:.2f} 2040={j['p2040']:.2f}"
            for j in previous["jobs"]
        )
        parts.append(
            f"YOUR PUBLISHED ESTIMATES LAST WEEK ({previous['week']}):\n" + prev_lines +
            "\n\nUpdate like a good Bayesian: move numbers only where this week's "
            "developments or your own reconsidered reasoning justify it, and keep them "
            "stable otherwise. Meaningful moves (>= 0.02) should be defensible; but do "
            "not treat last week as sacred — correct anything you now believe was "
            "miscalibrated."
        )
    parts.append("Return probabilities for ALL occupations, using their exact ids.")
    return "\n\n".join(parts)


def structured_call(prompt: str, schema_name: str, schema: dict,
                    effort: str, max_output_tokens: int) -> dict:
    response = client.responses.create(
        model=MODEL,
        reasoning={"effort": effort},
        max_output_tokens=max_output_tokens,
        instructions=FORECASTER_SYSTEM,
        input=prompt,
        text={"format": {
            "type": "json_schema",
            "name": schema_name,
            "schema": schema,
            "strict": True,
        }},
    )
    if response.status == "incomplete":
        reason = getattr(response.incomplete_details, "reason", "unknown")
        raise RuntimeError(f"incomplete response ({reason})")
    return json.loads(response.output_text)


def run_ensemble(prompt: str) -> list[dict]:
    samples = []
    for i in range(ENSEMBLE_SIZE):
        try:
            samples.append(structured_call(
                prompt, "weekly_forecasts", FORECAST_SCHEMA,
                effort="high", max_output_tokens=64000,
            ))
            print(f"  ensemble sample {i + 1}/{ENSEMBLE_SIZE} ok", file=sys.stderr)
        except Exception as e:  # one bad sample must not kill the weekly run
            print(f"  ensemble sample {i + 1} failed: {e}", file=sys.stderr)
    if len(samples) < 3:
        raise RuntimeError(f"Only {len(samples)} ensemble samples succeeded; need >= 3.")
    return samples


# ----------------------------------------------------------- 3. AGGREGATE

def clamp(p: float) -> float:
    return max(0.0, min(0.99, round(float(p), 2)))


def aggregate(jobs: list[dict], samples: list[dict], previous: dict | None) -> list[dict]:
    prev_by_id = {j["id"]: j for j in previous["jobs"]} if previous else {}
    results = []
    for job in jobs:
        per_horizon = {}
        spreads = {}
        for h in HORIZONS:
            values = []
            for s in samples:
                for f in s.get("forecasts", []):
                    if f.get("id") == job["id"]:
                        values.append(clamp(f[f"p{h}"]))
            if not values:
                raise RuntimeError(f"No ensemble values for job {job['id']} horizon {h}")
            per_horizon[h] = round(statistics.median(values), 2)
            spreads[h] = round(max(values) - min(values), 2)
        # enforce monotonicity across horizons after aggregation
        for a, b in zip(HORIZONS, HORIZONS[1:]):
            if per_horizon[b] < per_horizon[a]:
                per_horizon[b] = per_horizon[a]
        # self-assessment: median capability-today, most-cited blockers
        cans, blocker_counts = [], {}
        for s in samples:
            for f in s.get("forecasts", []):
                if f.get("id") == job["id"]:
                    cans.append(clamp(f.get("can_now", 0)))
                    for b in f.get("blockers", []):
                        if b in BLOCKERS:
                            blocker_counts[b] = blocker_counts.get(b, 0) + 1
        can_now = round(statistics.median(cans), 2) if cans else 0.0
        top_blockers = [b for b, _ in sorted(blocker_counts.items(),
                                             key=lambda kv: -kv[1])[:3]]
        prev = prev_by_id.get(job["id"])
        entry = {
            "id": job["id"],
            "name": job["name"],
            "group": job["group"],
            "can_now": can_now,
            "blockers": top_blockers,
            **{f"p{h}": per_horizon[h] for h in HORIZONS},
            "spread2030": spreads["2030"],
            "delta2030": round(per_horizon["2030"] - prev["p2030"], 2) if prev else None,
        }
        results.append(entry)
    results.sort(key=lambda r: (-r["p2030"], -r["p2040"], r["name"]))
    for rank, entry in enumerate(results, start=1):
        entry["rank"] = rank
        prev = prev_by_id.get(entry["id"])
        entry["rank_delta"] = (prev["rank"] - rank) if prev and "rank" in prev else None
    return results


# ------------------------------------------------------------- 4. COMMENT

COMMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "summary": {"type": "string"},
        "signal_of_the_week": {"type": "string"},
        "job_notes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["id", "note"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["headline", "summary", "signal_of_the_week", "job_notes"],
    "additionalProperties": False,
}


def write_commentary(results: list[dict], digest: str, previous: dict | None,
                     now: datetime) -> dict:
    table = "\n".join(
        f"- {r['id']} ({r['name']}): today={r['can_now']:.2f} "
        f"2027={r['p2027']:.2f} 2030={r['p2030']:.2f} "
        f"2035={r['p2035']:.2f} 2040={r['p2040']:.2f}"
        + (f" | Δ2030 {r['delta2030']:+.2f}" if r["delta2030"] is not None else "")
        for r in results
    )
    cap_index = statistics.mean(r["can_now"] for r in results)
    table += (f"\n\nYOUR CAPABILITY INDEX (mean share of tracked work you assess you "
              f"could do today): {cap_index:.1%}")
    prompt = (
        f"Today is {now:%Y-%m-%d}. This week's final published numbers (already "
        f"aggregated from your ensemble):\n\n{table}\n\n"
        "THIS WEEK'S DEVELOPMENTS:\n" + (digest or "Quiet week.") + "\n\n"
        "Write the weekly commentary for the public page:\n"
        "- headline: one punchy sentence (max 120 chars) capturing the week's single "
        "most striking number or move. Written in first person as the AI "
        "(e.g. \"I now put ...\").\n"
        "- summary: 2-4 sentences on what moved and why, first person.\n"
        "- signal_of_the_week: one development from the digest that most influenced "
        "your thinking, in one sentence — described factually, without naming any "
        "study, consultancy, or citing a specific report as an authority.\n"
        "- job_notes: for EVERY occupation id, one crisp sentence (max 160 chars) of "
        "your reasoning for its current number — task-level, specific, first person.\n"
        "Never cite external studies or attribute numbers to organizations. "
        "These are your own estimates."
    )
    return structured_call(prompt, "weekly_commentary", COMMENT_SCHEMA,
                           effort="medium", max_output_tokens=32000)


# ----------------------------------------------------------------- MAIN

def main() -> None:
    now = datetime.now(timezone.utc)
    week = week_label(now)
    jobs = load_jobs()
    previous = load_previous()

    if previous and previous.get("week") == week:
        print(f"Forecast for {week} already exists; nothing to do.", file=sys.stderr)
        return

    print("[1/4] Scanning the week's developments...", file=sys.stderr)
    digest = scan_week(now)
    print(digest, file=sys.stderr)

    print(f"[2/4] Running ensemble of {ENSEMBLE_SIZE} independent forecasts...",
          file=sys.stderr)
    prompt = build_forecast_prompt(jobs, digest, previous, now)
    samples = run_ensemble(prompt)

    print("[3/4] Aggregating medians and deltas...", file=sys.stderr)
    results = aggregate(jobs, samples, previous)

    print("[4/4] Writing weekly commentary...", file=sys.stderr)
    commentary = write_commentary(results, digest, previous, now)
    notes = {n["id"]: n["note"] for n in commentary.get("job_notes", [])}
    for r in results:
        r["note"] = notes.get(r["id"], "")

    payload = {
        "week": week,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": MODEL,
        "capability_index": round(statistics.mean(r["can_now"] for r in results), 3),
        "methodology_version": METHODOLOGY_VERSION,
        "ensemble_size": len(samples),
        "headline": commentary["headline"],
        "summary": commentary["summary"],
        "signal_of_the_week": commentary["signal_of_the_week"],
        "digest": digest,
        "jobs": results,
    }

    HISTORY.mkdir(parents=True, exist_ok=True)
    out = json.dumps(payload, indent=1, ensure_ascii=False)
    (DATA / "latest.json").write_text(out)
    (HISTORY / f"{week}.json").write_text(out)
    print(f"Wrote forecast for {week}: {len(results)} jobs, "
          f"headline: {commentary['headline']}", file=sys.stderr)


if __name__ == "__main__":
    main()
