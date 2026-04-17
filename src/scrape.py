"""
scrape.py — Fetch TikTok video data via Apify API.

Reads keywords/hashtags from config/keywords.json, runs the
clockworks/tiktok-scraper actor for each, and saves raw + combined JSON
to the data/ directory.

Usage:
    python src/scrape.py                                         # multi-report mode
    python src/scrape.py --query "#hashtag" --mode hashtag       # on-demand single query
    python src/scrape.py --from_plan                             # from AI-generated plan

Required env vars:
    APIFY_API_TOKEN
"""

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from apify_client import ApifyClient
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "keywords.json"
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

ACTOR_ID = "clockworks/tiktok-scraper"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_reports(config: dict) -> list[dict]:
    """Return list of report configs from either new or legacy format."""
    if "reports" in config:
        return config["reports"]
    return [{
        "name": "default",
        "keywords": config.get("keywords", []),
        "hashtags": config.get("hashtags", []),
        "profiles": config.get("profiles", []),
        "max_videos_per_keyword": config.get("max_videos_per_keyword", 300),
        "period_days": config.get("period_days", 7),
    }]


def latest_plan() -> Path:
    """Find the most recent plan_*.json file."""
    files = sorted(DATA_DIR.glob("plan_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        print("ERROR: No plan_*.json found in data/. Run plan.py first.", file=sys.stderr)
        sys.exit(1)
    return files[0]


def run_actor(client: ApifyClient, search_type: str, query: str, max_items: int) -> list[dict]:
    """Run the Apify TikTok scraper actor and return the dataset items."""
    if search_type == "hashtag":
        actor_input = {
            "hashtags": [query.lstrip("#")],
            "resultsPerPage": max_items,
            "maxItems": max_items,
        }
    elif search_type == "profile":
        actor_input = {
            "profiles": [query.lstrip("@")],
            "resultsPerPage": max_items,
            "maxItems": max_items,
        }
    else:
        actor_input = {
            "hashtags": [query],
            "resultsPerPage": max_items,
            "maxItems": max_items,
        }

    print(f"\n[scrape] ── {search_type.upper()} query: {query!r}")
    print(f"[scrape] Actor input sent to {ACTOR_ID}:")
    print(json.dumps(actor_input, indent=2, ensure_ascii=False))

    run = client.actor(ACTOR_ID).call(
        run_input=actor_input,
        timeout_secs=120,
        memory_mbytes=1024,
        wait_secs=60,
    )

    dataset = client.dataset(run["defaultDatasetId"])
    dataset_info = dataset.get()
    print(f"[scrape] Dataset item count (before iterate): {dataset_info.get('itemCount', 'unknown')}")

    items = list(dataset.iterate_items())

    print(f"[scrape] Raw items returned by Apify: {len(items)}")

    if len(items) == 0:
        raise RuntimeError(
            f"Apify returned 0 results for {search_type}={query!r}. "
            "Possible causes: wrong input format, API token invalid, "
            "actor quota exhausted, or this keyword has no TikTok results."
        )

    print(f"[scrape] First raw item (field names + values):")
    print(json.dumps(items[0], indent=2, ensure_ascii=False, default=str))

    return items


def filter_by_period(items: list[dict], period_days: int, query: str) -> list[dict]:
    """Drop videos posted before the period_days cutoff (client-side filter)."""
    if period_days <= 0:
        return items
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=period_days)
    kept = []
    no_timestamp = 0
    too_old = 0
    for v in items:
        raw = v.get("createTimeISO") or v.get("createTime")
        if raw is None:
            no_timestamp += 1
            kept.append(v)
            continue
        if isinstance(raw, (int, float)):
            created = datetime.fromtimestamp(raw, tz=timezone.utc)
        else:
            try:
                created = datetime.fromisoformat(str(raw).rstrip("Z")).replace(tzinfo=timezone.utc)
            except ValueError:
                no_timestamp += 1
                kept.append(v)
                continue
        if created >= cutoff:
            kept.append(v)
        else:
            too_old += 1

    print(
        f"[scrape] Date filter ({period_days}d cutoff: {cutoff.date()}) for {query!r}: "
        f"{len(items)} in → {len(kept)} kept "
        f"({too_old} too old, {no_timestamp} no timestamp)"
    )
    return kept


def scrape_report(client: ApifyClient, report_cfg: dict, timestamp: str) -> Path:
    """Scrape a single report config and return the combined file path."""
    slug = slugify(report_cfg["name"])
    keywords = report_cfg.get("keywords", [])
    hashtags = report_cfg.get("hashtags", [])
    profiles = report_cfg.get("profiles", [])
    max_videos = report_cfg.get("max_videos_per_keyword", 300)
    period_days = report_cfg.get("period_days", 7)

    all_videos: list[dict] = []

    for kw in keywords:
        kw_slug = kw.replace(" ", "_")
        items = run_actor(client, "keyword", kw, max_videos)
        items = filter_by_period(items, period_days, kw)
        raw_path = DATA_DIR / f"raw_keyword_{slug}_{kw_slug}_{timestamp}.json"
        raw_path.write_text(json.dumps(items, indent=2, ensure_ascii=False))
        for item in items:
            item["_source_type"] = "keyword"
            item["_source_query"] = kw
        all_videos.extend(items)

    for ht in hashtags:
        ht_slug = ht.lstrip("#")
        items = run_actor(client, "hashtag", ht, max_videos)
        items = filter_by_period(items, period_days, ht)
        raw_path = DATA_DIR / f"raw_hashtag_{slug}_{ht_slug}_{timestamp}.json"
        raw_path.write_text(json.dumps(items, indent=2, ensure_ascii=False))
        for item in items:
            item["_source_type"] = "hashtag"
            item["_source_query"] = ht
        all_videos.extend(items)

    for profile in profiles:
        profile_slug = profile.lstrip("@")
        items = run_actor(client, "profile", profile, max_videos)
        items = filter_by_period(items, period_days, profile)
        raw_path = DATA_DIR / f"raw_profile_{slug}_{profile_slug}_{timestamp}.json"
        raw_path.write_text(json.dumps(items, indent=2, ensure_ascii=False))
        for item in items:
            item["_source_type"] = "profile"
            item["_source_query"] = profile
        all_videos.extend(items)

    # Deduplicate by video ID
    seen: set[str] = set()
    unique_videos: list[dict] = []
    for v in all_videos:
        vid = v.get("id") or v.get("videoId") or v.get("webVideoUrl", "")
        if vid not in seen:
            seen.add(vid)
            unique_videos.append(v)

    combined_path = DATA_DIR / f"combined_{slug}_{timestamp}.json"
    combined_path.write_text(json.dumps(unique_videos, indent=2, ensure_ascii=False))
    print(f"\nSaved {len(unique_videos)} unique videos → {combined_path}")
    return combined_path


def scrape_from_plan() -> Path:
    """Load the latest AI-generated plan and scrape accordingly."""
    plan_path = latest_plan()
    print(f"[scrape] Loading plan from {plan_path.name}")
    plan = json.loads(plan_path.read_text())

    # Convert the plan into the same report_cfg format that scrape_report() expects
    report_cfg = {
        "name": "on_demand",
        "keywords": plan.get("keywords", []),
        "hashtags": plan.get("hashtags", []),
        "profiles": plan.get("profiles", []),
        "max_videos_per_keyword": plan.get("max_videos_per_query", 200),
        "period_days": plan.get("period_days", 14),
    }

    print(f"[scrape] Plan → keywords={report_cfg['keywords']}, "
          f"hashtags={report_cfg['hashtags']}, profiles={report_cfg['profiles']}")

    api_token = os.environ.get("APIFY_API_TOKEN")
    if not api_token:
        print("ERROR: APIFY_API_TOKEN not set.", file=sys.stderr)
        sys.exit(1)

    client = ApifyClient(api_token)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return scrape_report(client, report_cfg, timestamp)


def scrape_all() -> list[Path]:
    """Scrape all reports from config (scheduled mode)."""
    api_token = os.environ.get("APIFY_API_TOKEN")
    if not api_token:
        print("ERROR: APIFY_API_TOKEN not set.", file=sys.stderr)
        sys.exit(1)

    config = load_config()
    reports = get_reports(config)
    client = ApifyClient(api_token)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    paths = []
    for report in reports:
        path = scrape_report(client, report, timestamp)
        paths.append(path)
    return paths


def scrape_single(query: str, mode: str, period_days: int | None, max_videos: int | None) -> Path:
    """Scrape a single on-demand query. Writes combined_on_demand_*.json."""
    api_token = os.environ.get("APIFY_API_TOKEN")
    if not api_token:
        print("ERROR: APIFY_API_TOKEN not set.", file=sys.stderr)
        sys.exit(1)

    config = load_config()
    reports = get_reports(config)
    default_report = reports[0] if reports else {}
    if max_videos is None:
        max_videos = default_report.get("max_videos_per_keyword", 300)
    if period_days is None:
        period_days = default_report.get("period_days", 7)

    client = ApifyClient(api_token)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    items = run_actor(client, mode, query, max_videos)
    items = filter_by_period(items, period_days, query)
    for item in items:
        item["_source_type"] = mode
        item["_source_query"] = query

    query_slug = re.sub(r"[^a-z0-9]+", "_", query.lower().lstrip("#@")).strip("_")
    raw_path = DATA_DIR / f"raw_{mode}_{query_slug}_{timestamp}.json"
    raw_path.write_text(json.dumps(items, indent=2, ensure_ascii=False))

    combined_path = DATA_DIR / f"combined_on_demand_{timestamp}.json"
    combined_path.write_text(json.dumps(items, indent=2, ensure_ascii=False))
    print(f"\nSaved {len(items)} videos → {combined_path}")
    return combined_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default=None)
    parser.add_argument("--mode", choices=["keyword", "hashtag", "profile"], default="keyword")
    parser.add_argument("--period_days", type=int, default=None)
    parser.add_argument("--max_videos", type=int, default=None)
    parser.add_argument("--from_plan", action="store_true", help="Load scraping plan from latest plan_*.json")
    args = parser.parse_args()

    if args.from_plan:
        scrape_from_plan()
    elif args.query:
        scrape_single(args.query, args.mode, args.period_days, args.max_videos)
    else:
        scrape_all()
