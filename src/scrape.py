"""
scrape.py — Fetch TikTok video data via Apify API.

Reads keywords/hashtags from config/keywords.json, runs the
clockworks/tiktok-scraper actor for each, and saves raw + combined JSON
to the data/ directory.

Required env vars:
    APIFY_API_TOKEN
"""

import json
import os
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


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def run_actor(client: ApifyClient, search_type: str, query: str, max_items: int) -> list[dict]:
    """Run the Apify TikTok scraper actor and return the dataset items."""
    if search_type == "hashtag":
        actor_input = {
            "hashtags": [query.lstrip("#")],
            "maxItems": max_items,
        }
    elif search_type == "profile":
        actor_input = {
            "profiles": [query.lstrip("@")],
            "maxItems": max_items,
        }
    else:
        actor_input = {
            "search": query,
            "maxItems": max_items,
        }

    print(f"  Running actor for {search_type}={query!r} (max {max_items} videos)...")
    run = client.actor(ACTOR_ID).call(run_input=actor_input)
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    print(f"  Retrieved {len(items)} videos.")
    return items


def filter_by_period(items: list[dict], period_days: int) -> list[dict]:
    """Drop videos posted before the period_days cutoff (client-side filter)."""
    if period_days <= 0:
        return items
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=period_days)
    kept = []
    for v in items:
        raw = v.get("createTimeISO") or v.get("createTime")
        if raw is None:
            kept.append(v)  # no timestamp — keep rather than silently discard
            continue
        if isinstance(raw, (int, float)):
            created = datetime.fromtimestamp(raw, tz=timezone.utc)
        else:
            try:
                created = datetime.fromisoformat(str(raw).rstrip("Z")).replace(tzinfo=timezone.utc)
            except ValueError:
                kept.append(v)
                continue
        if created >= cutoff:
            kept.append(v)
    return kept


def scrape(
    keywords: list[str] | None = None,
    hashtags: list[str] | None = None,
    profiles: list[str] | None = None,
    max_videos: int | None = None,
    period_days: int | None = None,
) -> Path:
    """
    Main scrape entry point.

    When called with explicit arguments (on-demand mode) those values override
    config/keywords.json.  Called with no arguments it reads from the config
    file (scheduled mode).
    """
    api_token = os.environ.get("APIFY_API_TOKEN")
    if not api_token:
        print("ERROR: APIFY_API_TOKEN not set.", file=sys.stderr)
        sys.exit(1)

    config = load_config()
    keywords = keywords if keywords is not None else config["keywords"]
    hashtags = hashtags if hashtags is not None else config["hashtags"]
    profiles = profiles if profiles is not None else config["profiles"]
    max_videos = max_videos if max_videos is not None else config["max_videos_per_keyword"]
    period_days = period_days if period_days is not None else config["period_days"]

    client = ApifyClient(api_token)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    all_videos: list[dict] = []

    for kw in keywords:
        slug = kw.replace(" ", "_")
        items = run_actor(client, "keyword", kw, max_videos)
        items = filter_by_period(items, period_days)
        raw_path = DATA_DIR / f"raw_keyword_{slug}_{timestamp}.json"
        raw_path.write_text(json.dumps(items, indent=2, ensure_ascii=False))
        for item in items:
            item["_source_type"] = "keyword"
            item["_source_query"] = kw
        all_videos.extend(items)

    for ht in hashtags:
        slug = ht.lstrip("#")
        items = run_actor(client, "hashtag", ht, max_videos)
        items = filter_by_period(items, period_days)
        raw_path = DATA_DIR / f"raw_hashtag_{slug}_{timestamp}.json"
        raw_path.write_text(json.dumps(items, indent=2, ensure_ascii=False))
        for item in items:
            item["_source_type"] = "hashtag"
            item["_source_query"] = ht
        all_videos.extend(items)

    for profile in profiles:
        slug = profile.lstrip("@")
        items = run_actor(client, "profile", profile, max_videos)
        items = filter_by_period(items, period_days)
        raw_path = DATA_DIR / f"raw_profile_{slug}_{timestamp}.json"
        raw_path.write_text(json.dumps(items, indent=2, ensure_ascii=False))
        for item in items:
            item["_source_type"] = "profile"
            item["_source_query"] = profile
        all_videos.extend(items)

    # Deduplicate by video ID (keep first occurrence)
    seen: set[str] = set()
    unique_videos: list[dict] = []
    for v in all_videos:
        vid = v.get("id") or v.get("videoId") or v.get("webVideoUrl", "")
        if vid not in seen:
            seen.add(vid)
            unique_videos.append(v)

    combined_path = DATA_DIR / f"combined_{timestamp}.json"
    combined_path.write_text(json.dumps(unique_videos, indent=2, ensure_ascii=False))
    print(f"\nSaved {len(unique_videos)} unique videos → {combined_path}")
    return combined_path


if __name__ == "__main__":
    # Support optional CLI overrides for on-demand workflow:
    # python scrape.py --query "#hashtag" --mode hashtag --period_days 14 --max_videos 200
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default=None)
    parser.add_argument("--mode", choices=["keyword", "hashtag", "profile"], default="keyword")
    parser.add_argument("--period_days", type=int, default=None)
    parser.add_argument("--max_videos", type=int, default=None)
    args = parser.parse_args()

    if args.query:
        if args.mode == "hashtag":
            scrape(keywords=[], hashtags=[args.query], profiles=[], max_videos=args.max_videos, period_days=args.period_days)
        elif args.mode == "profile":
            scrape(keywords=[], hashtags=[], profiles=[args.query], max_videos=args.max_videos, period_days=args.period_days)
        else:
            scrape(keywords=[args.query], hashtags=[], profiles=[], max_videos=args.max_videos, period_days=args.period_days)
    else:
        scrape()
