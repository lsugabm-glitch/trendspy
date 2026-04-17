"""
plan.py — Turns a free-text research brief into a structured scraping plan.

Reads a brief (from --brief or BRIEF env var), asks Claude Sonnet to produce
a JSON plan, validates it, and writes data/plan_<ts>.json.

Downstream steps (scrape.py, insights.py) read this file when --from_plan is used.

Usage:
    python src/plan.py --brief "Saya ingin tahu tren skincare lokal..."
    python src/plan.py --brief "..." --dry_run          # plan only, no scraping
    python src/plan.py --brief "..." --period_days 14   # override time window

Required env vars:
    ANTHROPIC_API_KEY
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# Hard caps — the planner is told these, and we re-enforce them after parsing.
MAX_KEYWORDS = 5
MAX_HASHTAGS = 5
MAX_PROFILES = 3
MAX_VIDEOS_CAP = 300
DEFAULT_PERIOD_DAYS = 14
DEFAULT_MAX_VIDEOS = 200

SYSTEM_PROMPT = f"""You are a TikTok research planner for an Indonesian content team.

Given a research brief (in Indonesian or English), produce a structured scraping plan
as JSON. The plan will be executed against the Apify TikTok scraper.

Rules:
- Output ONLY valid JSON. No prose, no markdown, no code fences.
- Maximum {MAX_KEYWORDS} keywords, {MAX_HASHTAGS} hashtags, {MAX_PROFILES} profiles.
- Keywords should be short search phrases (2-4 words), in the language the topic
  is most discussed in on Indonesian TikTok (often a mix of Indonesian and English).
- Hashtags must NOT include the # symbol.
- Profiles must NOT include the @ symbol.
- Prefer fewer, higher-signal queries over many vague ones.
- If the brief is about a specific creator or account, lean profile-heavy.
- If the brief is about a trend or topic, lean keyword + hashtag.
- research_brief field: restate the user's goal in 2-3 sentences in Bahasa Indonesia.
  This will be shown in the final report and used to focus the AI insights.

JSON schema:
{{
  "research_brief": "string (Bahasa Indonesia, 2-3 sentences)",
  "keywords": ["string", ...],
  "hashtags": ["string without #", ...],
  "profiles": ["string without @", ...],
  "period_days": integer (7, 14, or 30),
  "max_videos_per_query": integer (max {MAX_VIDEOS_CAP}),
  "rationale": "string (1-2 sentences explaining the keyword choices, in Bahasa Indonesia)"
}}
"""


def build_plan(brief: str, period_override: int | None, max_videos_override: int | None) -> dict:
    """Call Claude Sonnet and return a validated plan dict."""
    client = Anthropic()  # Reads ANTHROPIC_API_KEY from env

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Research brief:\n\n{brief}"}],
    )

    raw = response.content[0].text.strip()

    # Defensive: strip code fences if the model added them anyway
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        plan = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: Planner returned invalid JSON:\n{raw}", file=sys.stderr)
        raise SystemExit(1) from e

    # Enforce caps regardless of what the model returned
    plan["keywords"] = plan.get("keywords", [])[:MAX_KEYWORDS]
    plan["hashtags"] = [h.lstrip("#") for h in plan.get("hashtags", [])][:MAX_HASHTAGS]
    plan["profiles"] = [p.lstrip("@") for p in plan.get("profiles", [])][:MAX_PROFILES]

    # Apply overrides if the user set them in the form
    if period_override:
        plan["period_days"] = period_override
    else:
        plan["period_days"] = plan.get("period_days", DEFAULT_PERIOD_DAYS)

    if max_videos_override:
        plan["max_videos_per_query"] = min(max_videos_override, MAX_VIDEOS_CAP)
    else:
        plan["max_videos_per_query"] = min(
            plan.get("max_videos_per_query", DEFAULT_MAX_VIDEOS), MAX_VIDEOS_CAP
        )

    # Sanity check: at least one query must exist
    total_queries = len(plan["keywords"]) + len(plan["hashtags"]) + len(plan["profiles"])
    if total_queries == 0:
        print("ERROR: Planner produced an empty plan (no keywords/hashtags/profiles).", file=sys.stderr)
        raise SystemExit(1)

    plan["brief_original"] = brief
    return plan


def print_plan_summary(plan: dict) -> None:
    """Pretty-print the plan to the Actions log so it's easy to review."""
    print("\n" + "=" * 60)
    print("SCRAPING PLAN")
    print("=" * 60)
    print(f"Brief: {plan['research_brief']}")
    print(f"Rationale: {plan.get('rationale', '(none)')}")
    print(f"Period: {plan['period_days']} days")
    print(f"Max videos per query: {plan['max_videos_per_query']}")
    print(f"Keywords ({len(plan['keywords'])}): {plan['keywords']}")
    print(f"Hashtags ({len(plan['hashtags'])}): {plan['hashtags']}")
    print(f"Profiles ({len(plan['profiles'])}): {plan['profiles']}")
    total = len(plan["keywords"]) + len(plan["hashtags"]) + len(plan["profiles"])
    print(f"Total Apify queries: {total}")
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--brief", default=os.environ.get("BRIEF", ""))
    parser.add_argument("--period_days", type=int, default=None)
    parser.add_argument("--max_videos", type=int, default=None)
    parser.add_argument("--dry_run", action="store_true",
                        default=os.environ.get("DRY_RUN", "").lower() == "true")
    args = parser.parse_args()

    if not args.brief.strip():
        print("ERROR: No brief provided. Use --brief or set BRIEF env var.", file=sys.stderr)
        raise SystemExit(1)

    plan = build_plan(args.brief, args.period_days, args.max_videos)
    print_plan_summary(plan)

    Path("data").mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = Path("data") / f"plan_{ts}.json"
    out_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    print(f"Plan saved to {out_path}")

    if args.dry_run:
        print("\nDRY RUN — stopping here. No scraping performed.")
        raise SystemExit(0)


if __name__ == "__main__":
    main()
