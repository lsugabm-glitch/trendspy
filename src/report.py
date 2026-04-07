"""
report.py — Generate a dark-themed HTML intelligence report.

Reads the latest analyzed_*.json and insights_*.json from data/ and
writes docs/index.html (served by GitHub Pages).
"""

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
DOCS_DIR.mkdir(exist_ok=True)


def latest(pattern: str) -> Path:
    files = sorted(DATA_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        print(f"ERROR: No {pattern} found in data/.", file=sys.stderr)
        sys.exit(1)
    return files[0]


def fmt_num(n) -> str:
    if n is None:
        return "—"
    n = float(n)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(int(n))


def escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def insights_to_html(text: str) -> str:
    """Convert markdown-style insights text to basic HTML."""
    lines = text.split("\n")
    html_parts = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("### "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<h3 class="insight-section">{escape(stripped[4:])}</h3>')
        elif stripped.startswith("## "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<h2>{escape(stripped[3:])}</h2>')
        elif stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            html_parts.append(f"<li>{escape(stripped[2:])}</li>")
        elif stripped == "":
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append("<br>")
        elif stripped.startswith("**") and stripped.endswith("**"):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<p><strong>{escape(stripped[2:-2])}</strong></p>")
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            # Bold inline **text**
            import re
            formatted = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escape(stripped))
            html_parts.append(f"<p>{formatted}</p>")

    if in_list:
        html_parts.append("</ul>")

    return "\n".join(html_parts)


def tier_badge(tier: str) -> str:
    colors = {"viral": "#ff4757", "strong": "#ffa502", "average": "#2ed573", "weak": "#747d8c"}
    color = colors.get(tier, "#747d8c")
    return f'<span class="tier-badge" style="background:{color}">{tier}</span>'


def build_html(analyzed: dict, insights: dict) -> str:
    meta = analyzed["metadata"]
    ins_meta = insights["metadata"]
    run_date = ins_meta["generated_at"][:10]
    total_videos = meta["total_videos"]
    total_views = fmt_num(meta["total_views"])
    tiers = meta["tier_breakdown"]

    sources = list({v["source_query"] for v in analyzed.get("top_by_views", [])})
    sources_str = escape(", ".join(sources) if sources else "—")

    # Top videos table rows
    video_rows = []
    for i, v in enumerate(analyzed["top_by_views"], 1):
        url = escape(v["url"])
        caption = escape(v["caption"][:80]) + ("…" if len(v["caption"]) > 80 else "")
        creator = escape(v["creator"])
        views = fmt_num(v["views"])
        er = f"{v['engagement_rate']:.2f}%"
        ev = fmt_num(v["engagement_velocity"]) + "/hr" if v["engagement_velocity"] else "—"
        video_rows.append(f"""
        <tr>
          <td class="rank">{i}</td>
          <td><a href="{url}" target="_blank" rel="noopener">{caption}</a></td>
          <td>@{creator}</td>
          <td class="num">{views}</td>
          <td class="num">{er}</td>
          <td class="num">{ev}</td>
          <td>{tier_badge(v['tier'])}</td>
        </tr>""")

    # Top creators rows
    creator_rows = []
    for i, c in enumerate(analyzed["top_creators"][:15], 1):
        creator_rows.append(f"""
        <tr>
          <td class="rank">{i}</td>
          <td>@{escape(c['creator'])}</td>
          <td class="num">{fmt_num(c['total_views'])}</td>
          <td class="num">{c['video_count']}</td>
        </tr>""")

    # Keyword performance rows
    kw_rows = []
    max_score = analyzed["keyword_performance"][0]["performance_score"] if analyzed["keyword_performance"] else 1
    for kp in analyzed["keyword_performance"]:
        pct = int(kp["performance_score"] / max(max_score, 1) * 100)
        kw_rows.append(f"""
        <tr>
          <td>{escape(kp['source'])}</td>
          <td class="num">{kp['video_count']}</td>
          <td class="num">{fmt_num(kp['avg_views'])}</td>
          <td class="num">{fmt_num(kp['avg_engagement'])}</td>
          <td>
            <div class="bar-wrap"><div class="bar" style="width:{pct}%">{fmt_num(kp['performance_score'])}</div></div>
          </td>
        </tr>""")

    # Hashtag cloud
    hashtag_spans = []
    max_count = analyzed["trending_hashtags"][0]["count"] if analyzed["trending_hashtags"] else 1
    for h in analyzed["trending_hashtags"]:
        size = 0.8 + (h["count"] / max(max_count, 1)) * 1.4
        hashtag_spans.append(
            f'<span class="hashtag" style="font-size:{size:.1f}rem">#{escape(h["hashtag"])} <sup>{h["count"]}</sup></span>'
        )

    insights_html = insights_to_html(insights["insights"])

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TrendSpy — TikTok Intelligence Report</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --bg: #0d0f14;
      --surface: #161b22;
      --surface2: #1f2937;
      --accent: #58a6ff;
      --accent2: #f78166;
      --text: #e6edf3;
      --muted: #8b949e;
      --border: #30363d;
      --viral: #ff4757;
      --strong: #ffa502;
      --avg: #2ed573;
      --weak: #747d8c;
    }}
    body {{ background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.6; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    header {{ background: var(--surface); border-bottom: 1px solid var(--border); padding: 2rem; }}
    header h1 {{ font-size: 1.8rem; color: var(--accent); letter-spacing: -0.5px; }}
    header h1 span {{ color: var(--accent2); }}
    .meta-grid {{ display: flex; gap: 2rem; margin-top: 1rem; flex-wrap: wrap; }}
    .meta-item {{ background: var(--surface2); border-radius: 8px; padding: 0.75rem 1.25rem; }}
    .meta-item .label {{ font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }}
    .meta-item .value {{ font-size: 1.4rem; font-weight: 700; color: var(--text); }}
    .tier-summary {{ display: flex; gap: 1rem; margin-top: 1rem; flex-wrap: wrap; }}
    .tier-pill {{ padding: 0.3rem 0.8rem; border-radius: 20px; font-size: 0.8rem; font-weight: 600; }}
    main {{ max-width: 1200px; margin: 0 auto; padding: 2rem; }}
    section {{ margin-bottom: 3rem; }}
    section h2 {{ font-size: 1.2rem; color: var(--accent); border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1.25rem; }}
    .insights-box {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1.75rem; }}
    .insights-box h2 {{ color: var(--text); border: none; padding-bottom: 0; margin-bottom: 0; font-size: 1rem; }}
    .insights-box .insight-section {{ color: var(--accent2); margin: 1.25rem 0 0.5rem; font-size: 1rem; }}
    .insights-box p {{ color: #cdd9e5; margin: 0.4rem 0; }}
    .insights-box ul {{ padding-left: 1.5rem; color: #cdd9e5; }}
    .insights-box li {{ margin: 0.3rem 0; }}
    .insights-box strong {{ color: var(--text); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.875rem; }}
    th {{ background: var(--surface2); color: var(--muted); text-align: left; padding: 0.6rem 0.75rem; font-weight: 600; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.05em; }}
    td {{ padding: 0.6rem 0.75rem; border-bottom: 1px solid var(--border); vertical-align: middle; }}
    tr:hover td {{ background: var(--surface); }}
    td.rank {{ color: var(--muted); font-weight: 700; width: 2rem; }}
    td.num {{ font-variant-numeric: tabular-nums; color: var(--accent); text-align: right; }}
    .tier-badge {{ display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.7rem; font-weight: 700; color: #fff; text-transform: uppercase; }}
    .bar-wrap {{ background: var(--surface2); border-radius: 4px; overflow: hidden; min-width: 120px; }}
    .bar {{ background: var(--accent); color: #fff; font-size: 0.75rem; font-weight: 600; padding: 0.2rem 0.5rem; border-radius: 4px; white-space: nowrap; }}
    .hashtag-cloud {{ display: flex; flex-wrap: wrap; gap: 0.5rem; padding: 1rem; background: var(--surface); border-radius: 10px; border: 1px solid var(--border); }}
    .hashtag {{ color: var(--accent); font-weight: 500; cursor: default; }}
    .hashtag sup {{ color: var(--muted); font-size: 0.65rem; }}
    footer {{ text-align: center; color: var(--muted); font-size: 0.8rem; padding: 2rem; border-top: 1px solid var(--border); }}
  </style>
</head>
<body>
<header>
  <h1>TrendSpy <span>//</span> TikTok Intelligence</h1>
  <div class="meta-grid">
    <div class="meta-item"><div class="label">Report Date</div><div class="value">{run_date}</div></div>
    <div class="meta-item"><div class="label">Videos Analyzed</div><div class="value">{total_videos:,}</div></div>
    <div class="meta-item"><div class="label">Total Views</div><div class="value">{total_views}</div></div>
    <div class="meta-item"><div class="label">Keywords Tracked</div><div class="value" style="font-size:0.95rem;padding-top:0.2rem">{sources_str}</div></div>
  </div>
  <div class="tier-summary">
    <span class="tier-pill" style="background:var(--viral)">Viral: {tiers.get('viral',0)}</span>
    <span class="tier-pill" style="background:var(--strong)">Strong: {tiers.get('strong',0)}</span>
    <span class="tier-pill" style="background:var(--avg)">Average: {tiers.get('average',0)}</span>
    <span class="tier-pill" style="background:var(--weak)">Weak: {tiers.get('weak',0)}</span>
  </div>
</header>

<main>

<section>
  <h2>AI Insight Report &mdash; by Claude Sonnet</h2>
  <div class="insights-box">
    {insights_html}
  </div>
</section>

<section>
  <h2>Top 10 Videos by Views</h2>
  <table>
    <thead>
      <tr><th>#</th><th>Caption</th><th>Creator</th><th>Views</th><th>ER%</th><th>Velocity</th><th>Tier</th></tr>
    </thead>
    <tbody>
      {"".join(video_rows)}
    </tbody>
  </table>
</section>

<section>
  <h2>Top Creators Leaderboard</h2>
  <table>
    <thead>
      <tr><th>#</th><th>Creator</th><th>Total Views</th><th>Videos</th></tr>
    </thead>
    <tbody>
      {"".join(creator_rows)}
    </tbody>
  </table>
</section>

<section>
  <h2>Keyword Performance</h2>
  <table>
    <thead>
      <tr><th>Source</th><th>Videos</th><th>Avg Views</th><th>Avg Engagement</th><th>Score</th></tr>
    </thead>
    <tbody>
      {"".join(kw_rows)}
    </tbody>
  </table>
</section>

<section>
  <h2>Trending Hashtags (in high-performing videos)</h2>
  <div class="hashtag-cloud">
    {"".join(hashtag_spans)}
  </div>
</section>

</main>
<footer>
  Generated by TrendSpy &bull; {run_date} &bull; Model: {escape(ins_meta['model'])} &bull;
  Tokens used: {ins_meta['input_tokens']:,} in / {ins_meta['output_tokens']:,} out
</footer>
</body>
</html>"""


def generate_report() -> Path:
    analyzed = json.loads(latest("analyzed_*.json").read_text())
    insights = json.loads(latest("insights_*.json").read_text())

    print("Building HTML report...")
    html = build_html(analyzed, insights)

    out_path = DOCS_DIR / "index.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"Report saved → {out_path}")
    return out_path


if __name__ == "__main__":
    generate_report()
