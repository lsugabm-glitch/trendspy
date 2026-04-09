"""
ecosystem.py — Map the TikTok creator ecosystem for a given subject.

Discovers accounts via hashtag search, enriches each with full profile data,
computes engagement metrics, assesses content alignment with Claude, and
generates an HTML report.

Usage:
    python src/ecosystem.py --subject "skincare" --max_accounts 20

Required env vars:
    APIFY_API_TOKEN
    ANTHROPIC_API_KEY
"""

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import anthropic
from apify_client import ApifyClient
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
DATA_DIR.mkdir(exist_ok=True)
DOCS_DIR.mkdir(exist_ok=True)

DISCOVERY_ACTOR = "clockworks/tiktok-scraper"
PROFILE_ACTOR = "clockworks/tiktok-profile-scraper"
MODEL = "claude-sonnet-4-6"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def discover_accounts(client: ApifyClient, subject: str, max_items: int = 50) -> list[str]:
    """Run hashtag search to discover accounts posting about the subject."""
    print(f"\n[ecosystem] Discovering accounts for #{subject}...")
    actor_input = {
        "hashtags": [subject.lstrip("#")],
        "resultsPerPage": max_items,
        "maxItems": max_items,
    }
    print(f"[ecosystem] Discovery input: {json.dumps(actor_input, indent=2)}")

    run = client.actor(DISCOVERY_ACTOR).call(
        run_input=actor_input,
        timeout_secs=120,
        memory_mbytes=1024,
        wait_secs=60,
    )

    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    print(f"[ecosystem] Discovery returned {len(items)} videos")

    usernames: list[str] = []
    seen: set[str] = set()
    for item in items:
        author = item.get("authorMeta") or item.get("author") or {}
        if isinstance(author, dict):
            username = author.get("uniqueId") or author.get("name") or ""
        else:
            username = str(author)
        username = username.strip().lstrip("@")
        if username and username not in seen:
            seen.add(username)
            usernames.append(username)

    print(f"[ecosystem] Found {len(usernames)} unique accounts")
    return usernames


def scrape_profile(client: ApifyClient, username: str) -> list[dict]:
    """Fetch videos for a single profile via tiktok-profile-scraper."""
    print(f"\n[ecosystem] Scraping profile: @{username}")
    actor_input = {
        "profiles": [username],
        "resultsPerPage": 100,
        "maxItems": 100,
    }

    run = client.actor(PROFILE_ACTOR).call(
        run_input=actor_input,
        timeout_secs=120,
        memory_mbytes=1024,
        wait_secs=60,
    )

    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    print(f"[ecosystem] Got {len(items)} videos for @{username}")
    return items


def parse_timestamp(video: dict) -> datetime | None:
    for field in ("createTime", "createTimeISO", "timestamp", "postedAt"):
        raw = video.get(field)
        if not raw:
            continue
        if isinstance(raw, (int, float)):
            return datetime.fromtimestamp(raw, tz=timezone.utc)
        try:
            return datetime.fromisoformat(str(raw).rstrip("Z")).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def compute_account_metrics(username: str, videos: list[dict]) -> dict:
    """Compute all required metrics for an account from its video list."""
    now = datetime.now(tz=timezone.utc)
    cutoff_30d = now - timedelta(days=30)
    cutoff_90d = now - timedelta(days=90)

    enriched = []
    for v in videos:
        stats = v.get("stats") or v.get("videoMeta") or {}

        def _int(key: str, fallback_keys: list[str] | None = None) -> int:
            val = v.get(key) or stats.get(key)
            if val is None and fallback_keys:
                for k in fallback_keys:
                    val = v.get(k) or stats.get(k)
                    if val is not None:
                        break
            try:
                return int(val or 0)
            except (TypeError, ValueError):
                return 0

        enriched.append({
            "ts": parse_timestamp(v),
            "views": _int("playCount", ["viewCount", "views", "plays"]),
            "likes": _int("diggCount", ["likeCount", "likes"]),
            "caption": v.get("text") or v.get("desc") or v.get("caption") or "",
        })

    with_ts = sorted([e for e in enriched if e["ts"] is not None], key=lambda x: x["ts"])

    # 30-day metrics
    recent_30d = [e for e in with_ts if e["ts"] >= cutoff_30d]
    total_views_30d = sum(e["views"] for e in recent_30d)
    total_content_30d = len(recent_30d)
    avg_views_per_content_30d = total_views_30d / total_content_30d if total_content_30d else 0
    avg_post_per_day_30d = total_content_30d / 30

    # All-time metrics
    all_views = [e["views"] for e in enriched if e["views"] > 0]
    lowest_views_all_time = min(all_views) if all_views else 0
    highest_views_all_time = max(all_views) if all_views else 0
    total_likes = sum(e["likes"] for e in enriched)

    # First visible post & account age
    first_post_ts = with_ts[0]["ts"] if with_ts else None
    first_visible_post = first_post_ts.strftime("%Y-%m-%d") if first_post_ts else "—"
    account_age_days = int((now - first_post_ts).total_seconds() / 86400) if first_post_ts else None
    account_age = f"{account_age_days} hari" if account_age_days is not None else "—"

    # Activity status
    latest_post_ts = with_ts[-1]["ts"] if with_ts else None
    if latest_post_ts:
        if latest_post_ts >= cutoff_30d:
            activity_status = "Aktif"
        elif latest_post_ts >= cutoff_90d:
            activity_status = "Jeda"
        else:
            activity_status = "Tidak Aktif"
    else:
        activity_status = "Tidak Diketahui"

    # Extract author meta (following/follower counts)
    following_count = None
    follower_count = None
    for v in videos:
        author = v.get("authorMeta") or v.get("author") or {}
        if isinstance(author, dict):
            following_count = author.get("following") or author.get("followingCount")
            follower_count = author.get("fans") or author.get("followers") or author.get("followerCount")
            if following_count is not None or follower_count is not None:
                break

    # Last 10 captions for AI alignment assessment
    all_captions = [e["caption"] for e in enriched if e["caption"]]
    last_10_captions = all_captions[-10:] if len(all_captions) > 10 else all_captions

    return {
        "username": username,
        "follower_count": follower_count,
        "following_count": following_count,
        "total_videos": len(enriched),
        "total_views_30d": total_views_30d,
        "total_content_30d": total_content_30d,
        "avg_views_per_content_30d": round(avg_views_per_content_30d),
        "avg_post_per_day_30d": round(avg_post_per_day_30d, 2),
        "lowest_views_all_time": lowest_views_all_time,
        "highest_views_all_time": highest_views_all_time,
        "total_likes": total_likes,
        "first_visible_post": first_visible_post,
        "account_age": account_age,
        "account_age_days": account_age_days,
        "activity_status": activity_status,
        "last_10_captions": last_10_captions,
    }


def check_following(username: str, following_count: int | None) -> None:
    """Log whether the following list will be checked based on count."""
    if following_count is None:
        return
    try:
        count = int(following_count)
    except (TypeError, ValueError):
        return
    if count > 100:
        print(f"[ecosystem] Lewati pengecekan following — akun mengikuti {count} akun (>100)")
    else:
        print(f"[ecosystem] @{username} mengikuti {count} akun — dalam batas pengecekan following")


def assess_alignment(ai_client: anthropic.Anthropic, subject: str, captions: list[str]) -> int:
    """Ask Claude to assess content alignment percentage (0–100)."""
    if not captions:
        return 0

    captions_text = "\n".join(f"- {c[:200]}" for c in captions)
    prompt = (
        f"Berikut 10 caption video TikTok dari sebuah akun:\n\n"
        f"{captions_text}\n\n"
        f"Berapa persen konten akun ini yang berhubungan dengan topik {subject}? "
        f"Jawab dengan angka 0-100 saja."
    )

    response = ai_client.messages.create(
        model=MODEL,
        max_tokens=10,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    match = re.search(r"\d+", text)
    if match:
        return min(100, max(0, int(match.group())))
    return 0


def fmt_num(n) -> str:
    if n is None or n == "—":
        return "—"
    try:
        n = float(n)
    except (TypeError, ValueError):
        return str(n)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(int(n))


def escape(s) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_ecosystem_html(subject: str, accounts: list[dict], generated_at: str) -> str:
    today = generated_at[:10]

    status_colors = {
        "Aktif": "#3fb950",
        "Jeda": "#f0883e",
        "Tidak Aktif": "#f85149",
        "Tidak Diketahui": "#8b949e",
    }

    rows = []
    for acc in accounts:
        status = acc.get("activity_status", "—")
        status_color = status_colors.get(status, "#8b949e")
        alignment = acc.get("content_alignment", 0)
        kategori = "Relevan" if alignment >= 80 else "Tidak Relevan"
        kategori_color = "#3fb950" if alignment >= 80 else "#8b949e"
        avg_ppd = acc.get("avg_post_per_day_30d", 0)
        try:
            avg_ppd_str = f"{float(avg_ppd):.2f}"
        except (TypeError, ValueError):
            avg_ppd_str = "—"

        rows.append(f"""
          <tr>
            <td>{escape(subject)}</td>
            <td><span style="color:{kategori_color};font-weight:600">{kategori}</span></td>
            <td><a href="https://tiktok.com/@{escape(acc['username'])}" target="_blank" rel="noopener">@{escape(acc['username'])}</a></td>
            <td><span style="color:{status_color};font-weight:600">{escape(status)}</span></td>
            <td>{escape(acc.get('first_visible_post', '—'))}</td>
            <td>{escape(acc.get('account_age', '—'))}</td>
            <td class="num">{fmt_num(acc.get('lowest_views_all_time'))}</td>
            <td class="num">{fmt_num(acc.get('highest_views_all_time'))}</td>
            <td class="num">{fmt_num(acc.get('total_likes'))}</td>
            <td class="num">{fmt_num(acc.get('total_views_30d'))}</td>
            <td class="num">{acc.get('total_content_30d', 0)}</td>
            <td class="num">{fmt_num(acc.get('avg_views_per_content_30d'))}</td>
            <td class="num">{avg_ppd_str}</td>
          </tr>""")

    aktif = sum(1 for a in accounts if a.get("activity_status") == "Aktif")
    relevan = sum(1 for a in accounts if a.get("content_alignment", 0) >= 80)

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TrendSpy — Pemetaan Ekosistem: {escape(subject)}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --bg: #0d0f14;
      --surface: #161b22;
      --surface2: #1f2937;
      --accent: #58a6ff;
      --accent2: #f78166;
      --accent3: #3fb950;
      --text: #e6edf3;
      --muted: #8b949e;
      --border: #30363d;
    }}
    body {{ background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.6; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    header {{ background: var(--surface); border-bottom: 1px solid var(--border); padding: 2rem; }}
    header h1 {{ font-size: 1.8rem; color: var(--accent); letter-spacing: -0.5px; }}
    header h1 span {{ color: var(--accent2); }}
    .meta-grid {{ display: flex; gap: 1.25rem; margin-top: 1rem; flex-wrap: wrap; }}
    .meta-item {{ background: var(--surface2); border-radius: 8px; padding: 0.75rem 1.25rem; }}
    .meta-item .label {{ font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }}
    .meta-item .value {{ font-size: 1.4rem; font-weight: 700; color: var(--text); }}
    main {{ max-width: 1700px; margin: 0 auto; padding: 2rem; }}
    section {{ margin-bottom: 3rem; }}
    section h2 {{ font-size: 1.2rem; color: var(--accent); border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1.25rem; }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.8rem; }}
    th {{ background: var(--surface2); color: var(--muted); text-align: left; padding: 0.6rem 0.75rem; font-weight: 600; text-transform: uppercase; font-size: 0.65rem; letter-spacing: 0.05em; white-space: nowrap; }}
    td {{ padding: 0.6rem 0.75rem; border-bottom: 1px solid var(--border); vertical-align: middle; white-space: nowrap; }}
    tr:hover td {{ background: var(--surface); }}
    td.num {{ font-variant-numeric: tabular-nums; color: var(--accent); text-align: right; }}
    .back-link {{ margin-bottom: 1.5rem; display: inline-block; font-size: 0.9rem; }}
    footer {{ text-align: center; color: var(--muted); font-size: 0.8rem; padding: 2rem; border-top: 1px solid var(--border); margin-top: 2rem; }}
  </style>
</head>
<body>
<header>
  <h1>TrendSpy <span>//</span> Pemetaan Ekosistem</h1>
  <div class="meta-grid">
    <div class="meta-item"><div class="label">Subjek</div><div class="value" style="font-size:1.1rem">{escape(subject)}</div></div>
    <div class="meta-item"><div class="label">Tanggal</div><div class="value">{today}</div></div>
    <div class="meta-item"><div class="label">Total Akun</div><div class="value">{len(accounts)}</div></div>
    <div class="meta-item"><div class="label">Akun Aktif</div><div class="value" style="color:#3fb950">{aktif}</div></div>
    <div class="meta-item"><div class="label">Konten Relevan</div><div class="value" style="color:#58a6ff">{relevan}</div></div>
  </div>
</header>
<main>
  <a class="back-link" href="index.html">&#8592; Kembali ke Pusat Laporan</a>
  <section>
    <h2>Peta Akun &mdash; #{escape(subject)}</h2>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Subjek</th>
            <th>Kategori</th>
            <th>Akun TikTok</th>
            <th>Status</th>
            <th>Post Pertama</th>
            <th>Usia Akun</th>
            <th>Views Terendah</th>
            <th>Views Tertinggi</th>
            <th>Total Likes</th>
            <th>Total Views 30 Hari</th>
            <th>Total Konten 30 Hari</th>
            <th>Rata-rata Views per Konten</th>
            <th>Rata-rata Post per Hari</th>
          </tr>
        </thead>
        <tbody>
          {"".join(rows)}
        </tbody>
      </table>
    </div>
  </section>
</main>
<footer>
  TrendSpy &bull; Pemetaan Ekosistem &bull; {today}
</footer>
</body>
</html>"""


def run_ecosystem(subject: str, max_accounts: int) -> None:
    """Main entry point for ecosystem mapping."""
    api_token = os.environ.get("APIFY_API_TOKEN")
    if not api_token:
        print("ERROR: APIFY_API_TOKEN not set.", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    apify_client = ApifyClient(api_token)
    ai_client = anthropic.Anthropic(api_key=api_key)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    subject_slug = slugify(subject)

    # Step 1: Discover accounts via hashtag search
    usernames = discover_accounts(apify_client, subject, max_items=50)
    usernames = usernames[:max_accounts]
    print(f"\n[ecosystem] Processing {len(usernames)} accounts (limit: {max_accounts})")

    # Step 2: Scrape each profile and compute metrics
    accounts = []
    for username in usernames:
        try:
            videos = scrape_profile(apify_client, username)
            if not videos:
                print(f"[ecosystem] No videos found for @{username}, skipping")
                continue

            metrics = compute_account_metrics(username, videos)

            # Check following list eligibility
            following_count = metrics.get("following_count")
            try:
                fc_int = int(following_count) if following_count is not None else None
            except (TypeError, ValueError):
                fc_int = None
            check_following(username, fc_int)

            # Step 3: Assess content alignment via Claude
            captions = metrics.get("last_10_captions", [])
            alignment = assess_alignment(ai_client, subject, captions)
            print(f"[ecosystem] @{username} — content alignment: {alignment}%")
            if alignment >= 80:
                print(f"[ecosystem] Flagged as highly relevant (>= 80%): @{username}")

            metrics["content_alignment"] = alignment
            metrics.pop("last_10_captions", None)
            accounts.append(metrics)

        except Exception as e:
            print(f"[ecosystem] ERROR processing @{username}: {e}", file=sys.stderr)
            continue

    print(f"\n[ecosystem] Successfully processed {len(accounts)} accounts")

    # Step 4: Save JSON
    generated_at = datetime.utcnow().isoformat()
    output = {
        "metadata": {
            "subject": subject,
            "generated_at": generated_at,
            "total_accounts": len(accounts),
            "max_accounts": max_accounts,
        },
        "accounts": accounts,
    }

    json_path = DATA_DIR / f"ecosystem_{subject_slug}_{timestamp}.json"
    json_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"[ecosystem] Saved → {json_path}")

    # Step 5: Generate HTML report
    html = build_ecosystem_html(subject, accounts, generated_at)
    html_path = DOCS_DIR / "ecosystem.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"[ecosystem] HTML saved → {html_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Map TikTok creator ecosystem for a subject")
    parser.add_argument("--subject", required=True, help="Topic/niche to map (e.g. 'skincare')")
    parser.add_argument("--max_accounts", type=int, default=20, help="Max accounts to process")
    args = parser.parse_args()

    run_ecosystem(args.subject, args.max_accounts)
