"""
analyze.py — Compute engagement metrics and aggregate TikTok video data.

Reads the latest combined_*.json from data/, enriches each video with
derived metrics, and writes an analyzed_*.json with aggregated summaries.
"""

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def latest_combined() -> Path:
    files = sorted(DATA_DIR.glob("combined_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        print("ERROR: No combined_*.json found in data/. Run scrape.py first.", file=sys.stderr)
        sys.exit(1)
    return files[0]


def parse_timestamp(video: dict) -> datetime | None:
    """Try several common field names the Apify actor may use."""
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


def enrich(video: dict) -> dict:
    stats = video.get("stats") or video.get("videoMeta") or {}

    def _int(key: str, fallback_keys: list[str] | None = None) -> int:
        val = video.get(key) or stats.get(key)
        if val is None and fallback_keys:
            for k in fallback_keys:
                val = video.get(k) or stats.get(k)
                if val is not None:
                    break
        try:
            return int(val or 0)
        except (TypeError, ValueError):
            return 0

    views = _int("playCount", ["viewCount", "views", "plays"])
    likes = _int("diggCount", ["likeCount", "likes"])
    comments = _int("commentCount", ["comments"])
    shares = _int("shareCount", ["shares"])

    total_engagement = likes + comments + shares
    engagement_rate = (total_engagement / views * 100) if views > 0 else 0.0

    created_at = parse_timestamp(video)
    now = datetime.now(tz=timezone.utc)
    hours_since = max((now - created_at).total_seconds() / 3600, 1) if created_at else None
    engagement_velocity = total_engagement / hours_since if hours_since else None

    video["_views"] = views
    video["_likes"] = likes
    video["_comments"] = comments
    video["_shares"] = shares
    video["_total_engagement"] = total_engagement
    video["_engagement_rate"] = round(engagement_rate, 4)
    video["_engagement_velocity"] = round(engagement_velocity, 4) if engagement_velocity is not None else None
    video["_created_at"] = created_at.isoformat() if created_at else None
    return video


def assign_tiers(videos: list[dict]) -> list[dict]:
    """Label each video with a performance tier based on view count percentile."""
    sorted_views = sorted((v["_views"] for v in videos), reverse=True)
    n = len(sorted_views)
    if n == 0:
        return videos
    top10 = sorted_views[max(0, int(n * 0.10) - 1)]
    top30 = sorted_views[max(0, int(n * 0.30) - 1)]
    top70 = sorted_views[max(0, int(n * 0.70) - 1)]

    for v in videos:
        views = v["_views"]
        if views >= top10:
            v["_tier"] = "viral"
        elif views >= top30:
            v["_tier"] = "strong"
        elif views >= top70:
            v["_tier"] = "average"
        else:
            v["_tier"] = "weak"
    return videos


def extract_hashtags(video: dict) -> list[str]:
    tags = video.get("hashtags") or video.get("textExtra") or []
    if isinstance(tags, list):
        result = []
        for t in tags:
            if isinstance(t, str):
                result.append(t.lstrip("#").lower())
            elif isinstance(t, dict):
                name = t.get("hashtagName") or t.get("text") or ""
                if name:
                    result.append(name.lstrip("#").lower())
        return result
    return []


def creator_name(video: dict) -> str:
    author = video.get("authorMeta") or video.get("author") or {}
    if isinstance(author, dict):
        return author.get("uniqueId") or author.get("name") or author.get("nickname") or "unknown"
    return str(author) or "unknown"


def video_url(video: dict) -> str:
    return video.get("webVideoUrl") or video.get("videoUrl") or video.get("url") or ""


def video_caption(video: dict) -> str:
    return video.get("text") or video.get("desc") or video.get("caption") or ""


def analyze() -> Path:
    src = latest_combined()
    print(f"Analyzing {src.name}...")
    videos: list[dict] = json.loads(src.read_text())

    if not videos:
        print("ERROR: combined JSON is empty.", file=sys.stderr)
        sys.exit(1)

    videos = [enrich(v) for v in videos]
    videos = assign_tiers(videos)

    # --- Top 10 lists ---
    by_views = sorted(videos, key=lambda v: v["_views"], reverse=True)[:10]
    by_velocity = sorted(
        [v for v in videos if v["_engagement_velocity"] is not None],
        key=lambda v: v["_engagement_velocity"],
        reverse=True,
    )[:10]
    by_engagement = sorted(videos, key=lambda v: v["_total_engagement"], reverse=True)[:10]

    def summarize(v: dict) -> dict:
        return {
            "url": video_url(v),
            "caption": video_caption(v)[:200],
            "creator": creator_name(v),
            "views": v["_views"],
            "likes": v["_likes"],
            "comments": v["_comments"],
            "shares": v["_shares"],
            "total_engagement": v["_total_engagement"],
            "engagement_rate": v["_engagement_rate"],
            "engagement_velocity": v["_engagement_velocity"],
            "tier": v["_tier"],
            "source_type": v.get("_source_type"),
            "source_query": v.get("_source_query"),
        }

    # --- Top creators ---
    creator_views: dict[str, int] = defaultdict(int)
    creator_videos: dict[str, int] = defaultdict(int)
    for v in videos:
        cn = creator_name(v)
        creator_views[cn] += v["_views"]
        creator_videos[cn] += 1

    top_creators = sorted(creator_views.items(), key=lambda x: x[1], reverse=True)[:20]
    top_creators_list = [
        {"creator": c, "total_views": tv, "video_count": creator_videos[c]}
        for c, tv in top_creators
    ]

    # --- Keyword / source performance ---
    source_stats: dict[str, dict] = defaultdict(lambda: {"views": [], "engagements": [], "count": 0})
    for v in videos:
        key = f"{v.get('_source_type','?')}:{v.get('_source_query','?')}"
        source_stats[key]["views"].append(v["_views"])
        source_stats[key]["engagements"].append(v["_total_engagement"])
        source_stats[key]["count"] += 1

    keyword_performance = []
    for src_key, data in source_stats.items():
        avg_views = sum(data["views"]) / len(data["views"]) if data["views"] else 0
        avg_eng = sum(data["engagements"]) / len(data["engagements"]) if data["engagements"] else 0
        keyword_performance.append({
            "source": src_key,
            "video_count": data["count"],
            "avg_views": round(avg_views),
            "avg_engagement": round(avg_eng),
            "performance_score": round(avg_views * 0.7 + avg_eng * 0.3),
        })
    keyword_performance.sort(key=lambda x: x["performance_score"], reverse=True)

    # --- Trending hashtags in high-performing videos ---
    high_perf = [v for v in videos if v["_tier"] in ("viral", "strong")]
    hashtag_counter: Counter = Counter()
    for v in high_perf:
        for tag in extract_hashtags(v):
            hashtag_counter[tag] += 1
    trending_hashtags = [{"hashtag": tag, "count": cnt} for tag, cnt in hashtag_counter.most_common(30)]

    # --- Summary stats ---
    tier_counts = Counter(v["_tier"] for v in videos)
    total_views = sum(v["_views"] for v in videos)

    result = {
        "metadata": {
            "source_file": src.name,
            "analyzed_at": datetime.utcnow().isoformat(),
            "total_videos": len(videos),
            "total_views": total_views,
            "tier_breakdown": dict(tier_counts),
        },
        "top_by_views": [summarize(v) for v in by_views],
        "top_by_engagement_velocity": [summarize(v) for v in by_velocity],
        "top_by_total_engagement": [summarize(v) for v in by_engagement],
        "top_creators": top_creators_list,
        "keyword_performance": keyword_performance,
        "trending_hashtags": trending_hashtags,
    }

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_path = DATA_DIR / f"analyzed_{timestamp}.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"Saved analysis → {out_path}")
    return out_path


if __name__ == "__main__":
    analyze()
