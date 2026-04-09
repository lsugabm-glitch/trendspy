"""
insights.py — Generate strategic AI insights from analyzed TikTok data.

Reads the latest analyzed_*.json from data/, builds a rich prompt,
calls the Claude API (claude-sonnet-4-6), and saves the response to
data/insights_*.json.

Usage:
    python src/insights.py                     # multi-report mode (reads config)
    python src/insights.py --slug on_demand    # single slug mode

Required env vars:
    ANTHROPIC_API_KEY
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CONFIG_PATH = ROOT / "config" / "keywords.json"

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096

SYSTEM_PROMPT = """Anda adalah senior content strategist yang ahli dalam pertumbuhan TikTok untuk brand dan kreator Indonesia.

Instruksi penting:
- Tulis seluruh respons dalam Bahasa Indonesia
- Gunakan terminologi content marketing Indonesia
- Sapa pembaca sebagai "tim konten"
- Tulis dengan gaya laporan profesional yang ringkas
- Hindari kata penghubung yang tidak perlu (namun, selain itu, lebih lanjut, sebagai tambahan)
- Setiap kalimat harus langsung ke intinya
- Gunakan bullet points untuk daftar, bukan paragraf panjang
- Target: setiap section maksimal 150 kata
- Jangan menulis ulang data yang sudah ada di tabel
- Selalu referensikan link video spesifik saat membuat klaim tentang konten yang berhasil. Contoh: "Hook pattern X bekerja dengan baik (lihat: [link])"
"""


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
        "max_videos_per_keyword": config.get("max_videos_per_keyword", 300),
        "period_days": config.get("period_days", 7),
    }]


def latest(pattern: str) -> Path:
    files = sorted(DATA_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        print(f"ERROR: No {pattern} found in data/. Run analyze.py first.", file=sys.stderr)
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
    analyzed_at = meta["analyzed_at"][:10]

    benchmarks = data.get("benchmarks", {})
    targets = benchmarks.get("benchmark_targets", {})
    top_v = benchmarks.get("top_video_by_views", {})
    top_vel = benchmarks.get("top_video_by_velocity", {})
    top_er_v = benchmarks.get("top_video_by_er", {})

    lines = [
        f"## Ringkasan Data",
        f"- Tanggal analisis: {analyzed_at}",
        f"- Total video dianalisis: {total:,}",
        f"- Total tayangan gabungan: {total_views}",
        "",
        "## Target Benchmark (Harus Dikalahkan)",
        f"- Target tayangan: {fmt_num(targets.get('views_to_beat', 0))} (20% di atas video terbaik: {fmt_num(top_v.get('views', 0))})",
        f"- Target ER: {targets.get('er_to_beat', 0):.2f}%",
        f"- Target velocity: {fmt_num(targets.get('velocity_to_beat', 0))}/hr",
        "",
        "## Video Terbaik Saat Ini (Benchmark)",
        f"- Creator: @{top_v.get('creator', 'N/A')}",
        f"- Tayangan: {fmt_num(top_v.get('views', 0))} | ER: {top_v.get('engagement_rate', 0):.2f}% | Velocity: {fmt_num(top_v.get('engagement_velocity'))}/hr",
        f"- Link: {top_v.get('url', 'N/A')}",
        f"- Caption: \"{top_v.get('caption', '')[:150]}\"",
        "",
        "## 10 Video Teratas berdasarkan Tayangan",
    ]

    for i, v in enumerate(data["top_by_views"], 1):
        url = v.get("url", "")
        caption = v.get("caption", "")[:120]
        ev = fmt_num(v["engagement_velocity"]) + "/hr" if v["engagement_velocity"] else "N/A"
        lines.append(
            f"[{i}] Views: {fmt_num(v['views'])} | ER: {v['engagement_rate']:.2f}% | Velocity: {ev}"
        )
        lines.append(f"Caption: \"{caption}\"")
        lines.append(f"Link: {url}")
        lines.append("")

    lines += ["## 10 Video Teratas berdasarkan Kecepatan Engagement (engagement/jam)"]
    for i, v in enumerate(data["top_by_engagement_velocity"], 1):
        ev = fmt_num(v["engagement_velocity"]) + "/hr" if v["engagement_velocity"] else "N/A"
        url = v.get("url", "")
        lines.append(
            f"[{i}] [{v['creator']}] {ev} | "
            f"{fmt_num(v['views'])} views | "
            f"Caption: \"{v['caption'][:100]}\""
        )
        lines.append(f"Link: {url}")
        lines.append("")

    lines += ["## Kreator Teratas (berdasarkan total tayangan)"]
    for c in data["top_creators"][:10]:
        lines.append(f"- @{c['creator']}: {fmt_num(c['total_views'])} total tayangan dari {c['video_count']} video")

    lines += ["", "## Performa Kata Kunci / Hashtag"]
    for kp in data["keyword_performance"]:
        lines.append(
            f"- {kp['source']}: {kp['video_count']} video | "
            f"avg tayangan {fmt_num(kp['avg_views'])} | "
            f"avg engagement {fmt_num(kp['avg_engagement'])} | "
            f"skor {fmt_num(kp['performance_score'])}"
        )

    lines += ["", "## Hashtag Trending di Video Berkinerja Tinggi"]
    tags = [f"#{h['hashtag']} ({h['count']})" for h in data["trending_hashtags"][:20]]
    lines.append(", ".join(tags))

    views_to_beat = fmt_num(targets.get("views_to_beat", 0))
    er_to_beat = f"{targets.get('er_to_beat', 0):.2f}%"
    velocity_to_beat = fmt_num(targets.get("velocity_to_beat", 0)) + "/hr" if targets.get("velocity_to_beat") else "N/A"

    lines += [
        "",
        "---",
        "",
        "Berdasarkan data ini, buat analisis strategis mendalam untuk tim konten Indonesia. Gunakan struktur section berikut:",
        "",
        "### 1. Ringkasan Eksekutif",
        "Apa yang sedang berhasil SEKARANG di niche ini? 3–5 poin utama yang bisa langsung dieksekusi tim konten hari ini.",
        "",
        "### 2. 3 Peluang Konten Teratas",
        "Ide konten spesifik dengan reasoning yang terhubung ke data. Sertakan link contoh video yang relevan.",
        "",
        "### 3. Pola Hook yang Berperforma",
        "Analisis caption video terbaik. Hook, format, atau struktur storytelling apa yang mendorong tayangan tinggi? Sertakan contoh nyata dengan link video.",
        "",
        "### 4. Insight Kreator",
        "Siapa yang menang dan mengapa? Apa yang bisa dipelajari dari pendekatan kreator teratas?",
        "",
        "### 5. Analisis ROI Kata Kunci & Niche",
        "Topik/hashtag mana yang paling menguntungkan? Mana yang jenuh atau underperforming?",
        "",
        "### 6. Rekomendasi Angle Konten untuk 7 Hari ke Depan",
        "5 rekomendasi angle konten spesifik dengan reasoning singkat untuk masing-masing.",
        "",
        "### 7. Yang Harus DIHINDARI",
        "Berdasarkan pola konten yang underperforming, pendekatan apa yang harus dihentikan atau dihindari?",
        "",
        "### 8. Bagaimana Membuat Konten yang Lebih Baik",
        f"Gunakan data benchmark dan top 10 video untuk memberikan rekomendasi spesifik kepada tim konten tentang cara membuat konten yang mengungguli video terbaik dalam dataset.",
        f"Fokus pada:",
        f"- Apa yang membuat video teratas (@{top_v.get('creator', 'N/A')}, {fmt_num(top_v.get('views', 0))} tayangan) berhasil?",
        f"- Elemen apa yang harus diubah atau ditingkatkan untuk melampaui target {views_to_beat} tayangan?",
        f"- Hook, format, atau pendekatan baru apa yang berpotensi melampaui ER target {er_to_beat} dan velocity {velocity_to_beat}?",
        f"- Sertakan link video referensi yang relevan dalam rekomendasi.",
    ]

    return "\n".join(lines)


def generate_insights(slug: str) -> Path:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    src = latest(f"analyzed_{slug}_*.json")
    print(f"Generating insights from {src.name} (slug={slug})...")
    data = json.loads(src.read_text())

    prompt = build_prompt(data)
    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
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
            "report_slug": slug,
        },
        "insights": ai_text,
    }

    out_path = DATA_DIR / f"insights_{slug}_{timestamp}.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"Saved insights → {out_path}")
    return out_path


def generate_all() -> list[Path]:
    """Generate insights for all reports from config."""
    config = load_config()
    reports = get_reports(config)
    paths = []
    for report in reports:
        slug = slugify(report["name"])
        paths.append(generate_insights(slug))
    return paths


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", default=None, help="Report slug (single-report mode)")
    args = parser.parse_args()

    if args.slug:
        generate_insights(args.slug)
    else:
        generate_all()
