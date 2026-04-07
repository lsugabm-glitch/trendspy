"""
insights.py — Generate strategic AI insights from analyzed TikTok data.

Reads the latest analyzed_*.json from data/, builds a rich prompt,
calls the Claude API (claude-sonnet-4-6), and saves the response to
data/insights_*.json.

Required env vars:
    ANTHROPIC_API_KEY
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096


def latest_analyzed() -> Path:
    files = sorted(DATA_DIR.glob("analyzed_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        print("ERROR: No analyzed_*.json found in data/. Run analyze.py first.", file=sys.stderr)
        sys.exit(1)
    return files[0]


def fmt_num(n: int | float | None) -> str:
    if n is None:
        return "N/A"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(int(n))


def build_prompt(data: dict) -> str:
    meta = data["metadata"]
    total = meta["total_videos"]
    total_views = fmt_num(meta["total_views"])
    tiers = meta["tier_breakdown"]
    analyzed_at = meta["analyzed_at"][:10]

    lines = [
        "You are a senior content strategist specializing in TikTok growth for Indonesian brands and creators.",
        "",
        f"## Data Overview",
        f"- Analysis date: {analyzed_at}",
        f"- Total videos analyzed: {total:,}",
        f"- Total combined views: {total_views}",
        f"- Viral (top 10%): {tiers.get('viral', 0)} videos",
        f"- Strong (10–30%): {tiers.get('strong', 0)} videos",
        f"- Average (30–70%): {tiers.get('average', 0)} videos",
        f"- Weak (bottom 30%): {tiers.get('weak', 0)} videos",
        "",
        "## Top 10 Videos by Views",
    ]

    for i, v in enumerate(data["top_by_views"], 1):
        lines.append(
            f"{i}. [{v['creator']}] {fmt_num(v['views'])} views | "
            f"ER {v['engagement_rate']:.2f}% | "
            f"Source: {v['source_query']} | "
            f"Caption: {v['caption'][:120]!r}"
        )

    lines += ["", "## Top 10 Videos by Engagement Velocity (engagements/hour)"]
    for i, v in enumerate(data["top_by_engagement_velocity"], 1):
        lines.append(
            f"{i}. [{v['creator']}] {fmt_num(v['engagement_velocity'])}/hr | "
            f"{fmt_num(v['views'])} views | "
            f"Caption: {v['caption'][:120]!r}"
        )

    lines += ["", "## Top Creators (by total views)"]
    for c in data["top_creators"][:10]:
        lines.append(f"- @{c['creator']}: {fmt_num(c['total_views'])} total views across {c['video_count']} videos")

    lines += ["", "## Keyword / Hashtag Performance"]
    for kp in data["keyword_performance"]:
        lines.append(
            f"- {kp['source']}: {kp['video_count']} videos | "
            f"avg views {fmt_num(kp['avg_views'])} | "
            f"avg engagement {fmt_num(kp['avg_engagement'])} | "
            f"score {fmt_num(kp['performance_score'])}"
        )

    lines += ["", "## Trending Hashtags in High-Performing Videos"]
    tags = [f"#{h['hashtag']} ({h['count']})" for h in data["trending_hashtags"][:20]]
    lines.append(", ".join(tags))

    lines += [
        "",
        "---",
        "",
        "Based on this data, provide a deep strategic analysis for an Indonesian content team. Structure your response with these exact sections:",
        "",
        "### 1. Executive Summary",
        "What is working RIGHT NOW in this niche? 3–5 key takeaways a content manager can act on today.",
        "",
        "### 2. Top 3 Content Opportunities",
        "Specific content ideas with clear reasoning tied to the data. Include why each opportunity is ripe.",
        "",
        "### 3. Hook Patterns That Are Performing",
        "Analyze the captions of top-performing videos. What opening hooks, formats, or storytelling structures are driving views? Include real examples.",
        "",
        "### 4. Creator Insights",
        "Who is winning and why? What can be learned from the top creators' approach?",
        "",
        "### 5. Keyword & Niche ROI Analysis",
        "Which topics/hashtags have the best return? Which are oversaturated or underperforming? Be specific.",
        "",
        "### 6. Recommended Content Angles for Next 7 Days",
        "Give 5 specific content angle recommendations with brief rationale for each.",
        "",
        "### 7. What to AVOID",
        "Based on underperforming content patterns, what approaches should the team stop or avoid?",
        "",
        "Be specific, data-driven, and actionable. This team publishes 3–5 videos per week.",
    ]

    return "\n".join(lines)


def generate_insights() -> Path:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    src = latest_analyzed()
    print(f"Generating insights from {src.name}...")
    data = json.loads(src.read_text())

    prompt = build_prompt(data)
    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )

    ai_text = message.content[0].text
    print(f"Received {len(ai_text)} chars from Claude.")

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    result = {
        "metadata": {
            "source_file": src.name,
            "generated_at": datetime.utcnow().isoformat(),
            "model": MODEL,
            "input_tokens": message.usage.input_tokens,
            "output_tokens": message.usage.output_tokens,
        },
        "insights": ai_text,
    }

    out_path = DATA_DIR / f"insights_{timestamp}.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"Saved insights → {out_path}")
    return out_path


if __name__ == "__main__":
    generate_insights()
