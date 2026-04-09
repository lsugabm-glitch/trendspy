"""
report.py — Generate dark-themed HTML intelligence reports.

Reads the latest analyzed_*.json and insights_*.json from data/ and
writes per-report HTML files to docs/. Also generates a hub page at
docs/index.html when running in multi-report mode.

Usage:
    python src/report.py                     # multi-report mode (reads config)
    python src/report.py --slug on_demand    # single slug → docs/index.html
    python src/report.py --slug skincare_indonesia  # → docs/report_skincare_indonesia.html
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
CONFIG_PATH = ROOT / "config" / "keywords.json"
DOCS_DIR.mkdir(exist_ok=True)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_reports(config: dict) -> list[dict]:
    if "reports" in config:
        return config["reports"]
    return [{
        "name": "default",
        "keywords": config.get("keywords", []),
        "hashtags": config.get("hashtags", []),
        "profiles": config.get("profiles", []),
    }]


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
    import re as _re
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
            # Handle links in list items
            content = stripped[2:]
            content = _re.sub(r"https?://\S+", lambda m: f'<a href="{m.group()}" target="_blank" rel="noopener">{m.group()}</a>', escape(content))
            content = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content)
            html_parts.append(f"<li>{content}</li>")
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
            formatted = escape(stripped)
            formatted = _re.sub(r"https?://\S+", lambda m: f'<a href="{m.group()}" target="_blank" rel="noopener">{m.group()}</a>', formatted)
            formatted = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", formatted)
            html_parts.append(f"<p>{formatted}</p>")

    if in_list:
        html_parts.append("</ul>")

    return "\n".join(html_parts)


DARK_CSS = """
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --bg: #0d0f14;
      --surface: #161b22;
      --surface2: #1f2937;
      --accent: #58a6ff;
      --accent2: #f78166;
      --accent3: #3fb950;
      --text: #e6edf3;
      --muted: #8b949e;
      --border: #30363d;
    }
    body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.6; }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    header { background: var(--surface); border-bottom: 1px solid var(--border); padding: 2rem; }
    header h1 { font-size: 1.8rem; color: var(--accent); letter-spacing: -0.5px; }
    header h1 span { color: var(--accent2); }
    .meta-grid { display: flex; gap: 1.25rem; margin-top: 1rem; flex-wrap: wrap; }
    .meta-item { background: var(--surface2); border-radius: 8px; padding: 0.75rem 1.25rem; }
    .meta-item .label { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
    .meta-item .value { font-size: 1.4rem; font-weight: 700; color: var(--text); }
    .benchmark-card { background: var(--surface2); border: 1px solid var(--accent3); border-radius: 10px; padding: 1rem 1.5rem; margin-top: 1.25rem; }
    .benchmark-card .benchmark-title { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--accent3); margin-bottom: 0.75rem; font-weight: 700; }
    .benchmark-grid { display: flex; gap: 2rem; flex-wrap: wrap; }
    .benchmark-item .label { font-size: 0.7rem; color: var(--muted); text-transform: uppercase; }
    .benchmark-item .value { font-size: 1.2rem; font-weight: 700; color: var(--accent3); }
    main { max-width: 1200px; margin: 0 auto; padding: 2rem; }
    section { margin-bottom: 3rem; }
    section h2 { font-size: 1.2rem; color: var(--accent); border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1.25rem; }
    .insights-box { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1.75rem; }
    .insights-box h2 { color: var(--text); border: none; padding-bottom: 0; margin-bottom: 0; font-size: 1rem; }
    .insights-box .insight-section { color: var(--accent2); margin: 1.25rem 0 0.5rem; font-size: 1rem; }
    .insights-box p { color: #cdd9e5; margin: 0.4rem 0; }
    .insights-box ul { padding-left: 1.5rem; color: #cdd9e5; }
    .insights-box li { margin: 0.3rem 0; }
    .insights-box strong { color: var(--text); }
    table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
    th { background: var(--surface2); color: var(--muted); text-align: left; padding: 0.6rem 0.75rem; font-weight: 600; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.05em; }
    td { padding: 0.6rem 0.75rem; border-bottom: 1px solid var(--border); vertical-align: middle; }
    tr:hover td { background: var(--surface); }
    td.rank { color: var(--muted); font-weight: 700; width: 2rem; }
    td.num { font-variant-numeric: tabular-nums; color: var(--accent); text-align: right; }
    .bar-wrap { background: var(--surface2); border-radius: 4px; overflow: hidden; min-width: 120px; }
    .bar { background: var(--accent); color: #fff; font-size: 0.75rem; font-weight: 600; padding: 0.2rem 0.5rem; border-radius: 4px; white-space: nowrap; }
    .hashtag-cloud { display: flex; flex-wrap: wrap; gap: 0.5rem; padding: 1rem; background: var(--surface); border-radius: 10px; border: 1px solid var(--border); }
    .hashtag { color: var(--accent); font-weight: 500; cursor: default; }
    .hashtag sup { color: var(--muted); font-size: 0.65rem; }
    footer { text-align: center; color: var(--muted); font-size: 0.8rem; padding: 2rem; border-top: 1px solid var(--border); }
"""


def build_html(analyzed: dict, insights: dict) -> str:
    meta = analyzed["metadata"]
    ins_meta = insights["metadata"]
    run_date = ins_meta["generated_at"][:10]
    total_videos = meta["total_videos"]
    total_views = fmt_num(meta["total_views"])

    sources = list({v["source_query"] for v in analyzed.get("top_by_views", []) if v.get("source_query")})
    sources_str = escape(", ".join(sources) if sources else "—")

    # Benchmark targets
    benchmarks = analyzed.get("benchmarks", {})
    targets = benchmarks.get("benchmark_targets", {})
    views_to_beat = fmt_num(targets.get("views_to_beat", 0))
    er_to_beat = f"{targets.get('er_to_beat', 0):.2f}%"
    velocity_to_beat = fmt_num(targets.get("velocity_to_beat")) + "/hr" if targets.get("velocity_to_beat") else "—"

    # Top videos table rows (no tier column)
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
  <title>TrendSpy — Laporan Intelijen TikTok</title>
  <style>
{DARK_CSS}
  </style>
</head>
<body>
<header>
  <h1>TrendSpy <span>//</span> Intelijen TikTok</h1>
  <div class="meta-grid">
    <div class="meta-item"><div class="label">Tanggal Laporan</div><div class="value">{run_date}</div></div>
    <div class="meta-item"><div class="label">Video Dianalisis</div><div class="value">{total_videos:,}</div></div>
    <div class="meta-item"><div class="label">Total Tayangan</div><div class="value">{total_views}</div></div>
    <div class="meta-item"><div class="label">Kata Kunci Dipantau</div><div class="value" style="font-size:0.95rem;padding-top:0.2rem">{sources_str}</div></div>
  </div>
  <div class="benchmark-card">
    <div class="benchmark-title">Target untuk Dikalahkan</div>
    <div class="benchmark-grid">
      <div class="benchmark-item"><div class="label">Target Tayangan</div><div class="value">{views_to_beat}</div></div>
      <div class="benchmark-item"><div class="label">Target ER</div><div class="value">{er_to_beat}</div></div>
      <div class="benchmark-item"><div class="label">Target Kecepatan</div><div class="value">{velocity_to_beat}</div></div>
    </div>
  </div>
</header>

<main>

<section>
  <h2>Laporan Insight AI &mdash; oleh Claude Sonnet</h2>
  <div class="insights-box">
    {insights_html}
  </div>
</section>

<section>
  <h2>10 Video Teratas berdasarkan Tayangan</h2>
  <table>
    <thead>
      <tr><th>#</th><th>Keterangan</th><th>Kreator</th><th>Tayangan</th><th>ER%</th><th>Kecepatan Engagement</th></tr>
    </thead>
    <tbody>
      {"".join(video_rows)}
    </tbody>
  </table>
</section>

<section>
  <h2>Peringkat Kreator Teratas</h2>
  <table>
    <thead>
      <tr><th>#</th><th>Kreator</th><th>Total Tayangan</th><th>Video</th></tr>
    </thead>
    <tbody>
      {"".join(creator_rows)}
    </tbody>
  </table>
</section>

<section>
  <h2>Performa Kata Kunci</h2>
  <table>
    <thead>
      <tr><th>Sumber</th><th>Video</th><th>Avg Tayangan</th><th>Avg Engagement</th><th>Skor</th></tr>
    </thead>
    <tbody>
      {"".join(kw_rows)}
    </tbody>
  </table>
</section>

<section>
  <h2>Hashtag Trending</h2>
  <div class="hashtag-cloud">
    {"".join(hashtag_spans)}
  </div>
</section>

</main>
<footer>
  Dibuat oleh TrendSpy &bull; {run_date} &bull; Model: {escape(ins_meta['model'])} &bull;
  Token: {ins_meta['input_tokens']:,} masuk / {ins_meta['output_tokens']:,} keluar
</footer>
</body>
</html>"""


def build_hub_html(reports_info: list[dict]) -> str:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    cards = []
    for r in reports_info:
        cards.append(f"""
      <a class="report-card" href="report_{r['slug']}.html">
        <div class="report-name">{escape(r['name'])}</div>
        <div class="report-link">Lihat Laporan →</div>
      </a>""")

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TrendSpy — Pusat Laporan</title>
  <style>
{DARK_CSS}
    .report-grid {{ display: flex; gap: 1.5rem; flex-wrap: wrap; margin-top: 1rem; }}
    .report-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1.5rem 2rem; min-width: 220px; transition: border-color 0.2s; text-decoration: none !important; }}
    .report-card:hover {{ border-color: var(--accent); }}
    .report-card .report-name {{ font-size: 1.1rem; font-weight: 700; color: var(--text); margin-bottom: 0.5rem; }}
    .report-card .report-link {{ font-size: 0.85rem; color: var(--accent); }}
    .other-links {{ list-style: none; display: flex; gap: 1rem; flex-wrap: wrap; padding-top: 0.5rem; }}
    .other-links li a {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 0.5rem 1rem; display: inline-block; font-size: 0.9rem; }}
    .other-links li a:hover {{ border-color: var(--accent); text-decoration: none; }}
  </style>
</head>
<body>
<header>
  <h1>TrendSpy <span>//</span> Pusat Laporan</h1>
  <div class="meta-grid">
    <div class="meta-item"><div class="label">Tanggal</div><div class="value">{today}</div></div>
    <div class="meta-item"><div class="label">Total Laporan</div><div class="value">{len(reports_info)}</div></div>
  </div>
</header>
<main>
  <section>
    <h2>Laporan Tersedia</h2>
    <div class="report-grid">
      {"".join(cards)}
    </div>
  </section>
  <section>
    <h2>Laporan Lainnya</h2>
    <ul class="other-links">
      <li><a href="ecosystem.html">Pemetaan Ekosistem</a></li>
    </ul>
  </section>
</main>
<footer>
  TrendSpy &bull; {today}
</footer>
</body>
</html>"""


def generate_report(slug: str) -> Path:
    """Generate HTML for a single report slug."""
    analyzed = json.loads(latest(f"analyzed_{slug}_*.json").read_text())
    insights = json.loads(latest(f"insights_{slug}_*.json").read_text())
    html = build_html(analyzed, insights)
    if slug == "on_demand":
        out_path = DOCS_DIR / "index.html"
    else:
        out_path = DOCS_DIR / f"report_{slug}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"Report saved → {out_path}")
    return out_path


def generate_all() -> None:
    """Generate reports for all configured slugs + hub page."""
    config = load_config()
    reports = get_reports(config)
    reports_info = []
    for report in reports:
        slug = slugify(report["name"])
        try:
            path = generate_report(slug)
            reports_info.append({"name": report["name"], "slug": slug})
        except SystemExit:
            print(f"Skipping {slug} — no data files found", file=sys.stderr)

    if reports_info:
        hub_path = DOCS_DIR / "index.html"
        hub_path.write_text(build_hub_html(reports_info), encoding="utf-8")
        print(f"Hub page saved → {hub_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", default=None, help="Report slug (single-report mode)")
    args = parser.parse_args()

    if args.slug:
        generate_report(args.slug)
    else:
        generate_all()
