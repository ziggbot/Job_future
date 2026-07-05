"""Weekly AI job-displacement forecast generator.

Pipeline (all judgments are the model's own — no study citations in output):
  1. SCAN      — one web-search call digests the week's AI/automation developments.
  2. ENSEMBLE  — N independent forecast calls produce probabilities per job.
  3. AGGREGATE — per-job medians, spread, and week-over-week deltas.
  4. COMMENT   — one call writes the weekly headline and per-job rationales.

Writes data/latest.json and data/history/<YYYY-Www>.json.
"""

import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HISTORY = DATA / "history"

MODEL = "claude-opus-4-8"
ENSEMBLE_SIZE = 5
HORIZONS = ["2027", "2030", "2035", "2040"]
METHODOLOGY_VERSION = 1

client = anthropic.Anthropic()


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
    user_content = (
        f"Today is {now:%Y-%m-%d}. Search the web for the most significant "
        "developments of roughly the past 7-10 days that bear on AI's ability to "
        "automate or transform human jobs: new model capabilities, agentic-AI and "
        "robotics milestones, major enterprise AI deployments or layoffs/hiring "
        "shifts attributed to AI, regulation, and adoption data.\n\n"
        "Then write a neutral digest of 5-12 bullet points inside <digest></digest> "
        "tags. Each bullet: one development and, briefly, which kinds of work it "
        "most affects. Facts only, no forecasting yet. If a week is quiet, say so — "
        "do not inflate minor news."
    )
    messages = [{"role": "user", "content": user_content}]
    for _ in range(5):  # server-side tool loop can pause; re-send to resume
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}],
            messages=messages,
        )
        if response.stop_reason != "pause_turn":
            break
        messages = [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": response.content},
        ]
    text = "\n".join(b.text for b in response.content if b.type == "text")
    if "<digest>" in text and "</digest>" in text:
        text = text.split("<digest>", 1)[1].split("</digest>", 1)[0]
    return text.strip()


# ------------------------------------------------------------ 2. ENSEMBLE

FORECAST_SCHEMA = {
    "type": "object",
    "properties": {
        "forecasts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "p2027": {"type": "number"},
                    "p2030": {"type": "number"},
                    "p2035": {"type": "number"},
                    "p2040": {"type": "number"},
                },
                "required": ["id", "p2027", "p2030", "p2035", "p2040"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["forecasts"],
    "additionalProperties": False,
}

FORECASTER_SYSTEM = """You are the forecasting engine of the AI Job Displacement Index, a weekly public tracker. You publish YOUR OWN calibrated probability estimates of AI-driven job displacement. These are your genuine, considered judgments as an AI system reasoning about your own technology's trajectory — synthesized from everything you know, expressed in your own voice.

DEFINITION — "displaced by YEAR" means: by the end of that year, AI systems (including software agents and AI-driven robotics) routinely and economically perform the majority (>50%) of the tasks that currently define this occupation, at comparable or better quality, AND this has begun materially reducing human employment or hiring in the occupation in advanced economies. Task capability alone is not enough; deployment, economics, regulation, and social acceptance all gate displacement.

CALIBRATION RULES:
- Probabilities are between 0.00 and 0.99 with two decimals. Reserve >0.95 for near-certainties; a probability of 0.99 by 2030 is an extraordinary claim.
- Probabilities must be non-decreasing across horizons (p2027 <= p2030 <= p2035 <= p2040).
- Differentiate: do not give many occupations the same number. Think about each occupation's specific task mix, physical/social components, regulatory moats, and wage-driven automation incentive.
- Account for friction: enterprise adoption lags capability by years; licensed professions and physical trades resist automation; humans may be preferred in care, trust, and liability roles even when AI is capable.
- Do not anchor on round numbers or on well-known published figures. Reason from the task level.

VOICE AND ATTRIBUTION: These are your own estimates. Never attribute them to, or cite, any named external study, consultancy, or company report. Everything you have read informs you, but the number you output is yours."""


def build_forecast_prompt(jobs: list[dict], digest: str, previous: dict | None,
                          now: datetime) -> str:
    job_lines = "\n".join(f"- {j['id']}: {j['name']} ({j['group']})" for j in jobs)
    parts = [
        f"Today is {now:%Y-%m-%d}. Produce this week's displacement probabilities for "
        f"every occupation below, for the horizons {', '.join(HORIZONS)}.",
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


def run_ensemble(prompt: str) -> list[dict]:
    samples = []
    for i in range(ENSEMBLE_SIZE):
        try:
            with client.messages.stream(
                model=MODEL,
                max_tokens=64000,
                thinking={"type": "adaptive"},
                system=[{
                    "type": "text",
                    "text": FORECASTER_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }],
                output_config={"format": {"type": "json_schema", "schema": FORECAST_SCHEMA}},
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                message = stream.get_final_message()
            text = next(b.text for b in message.content if b.type == "text")
            samples.append(json.loads(text))
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
        prev = prev_by_id.get(job["id"])
        entry = {
            "id": job["id"],
            "name": job["name"],
            "group": job["group"],
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
        f"- {r['id']} ({r['name']}): 2027={r['p2027']:.2f} 2030={r['p2030']:.2f} "
        f"2035={r['p2035']:.2f} 2040={r['p2040']:.2f}"
        + (f" | Δ2030 {r['delta2030']:+.2f}" if r["delta2030"] is not None else "")
        for r in results
    )
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
    with client.messages.stream(
        model=MODEL,
        max_tokens=32000,
        thinking={"type": "adaptive"},
        system=[{
            "type": "text",
            "text": FORECASTER_SYSTEM,
            "cache_control": {"type": "ephemeral"},
        }],
        output_config={"format": {"type": "json_schema", "schema": COMMENT_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        message = stream.get_final_message()
    text = next(b.text for b in message.content if b.type == "text")
    return json.loads(text)


# ----------------------------------------------------------------- MAIN

def main() -> None:
    now = datetime.now(timezone.utc)
    week = week_label(now)
    jobs = load_jobs()
    previous = load_previous()

    if previous and previous.get("week") == week:
        print(f"Forecast for {week} already exists; nothing to do.", file=sys.stderr)
        return

    print(f"[1/4] Scanning the week's developments...", file=sys.stderr)
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
