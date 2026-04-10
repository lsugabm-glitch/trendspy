"""
src/news_brief.py
Fetch article(s) from URLs → extract content → generate TikTok content brief via Claude.
"""

import os
import sys
import argparse
from datetime import datetime

import requests
from bs4 import BeautifulSoup
import anthropic


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_article(url: str) -> dict:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Strip noise
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
            tag.decompose()

        # Title
        title = ""
        if soup.find("h1"):
            title = soup.find("h1").get_text(strip=True)
        elif soup.find("title"):
            title = soup.find("title").get_text(strip=True)

        # Main content — prefer <article>, fallback to <p> harvest
        article_tag = soup.find("article")
        if article_tag:
            content = article_tag.get_text(separator="\n", strip=True)
        else:
            paragraphs = soup.find_all("p")
            content = "\n".join(
                p.get_text(strip=True)
                for p in paragraphs
                if len(p.get_text(strip=True)) > 60
            )

        content = content[:4000]  # cap to avoid token explosion

        return {"url": url, "title": title, "content": content, "ok": True}

    except Exception as exc:
        print(f"  [WARN] Gagal fetch {url}: {exc}")
        return {"url": url, "title": "", "content": "", "ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Claude prompt
# ---------------------------------------------------------------------------

def build_prompt(articles: list[dict], topic: str) -> str:
    blocks = ""
    for i, art in enumerate(articles, 1):
        if art["ok"]:
            blocks += f"### Artikel {i} — {art['title']}\nURL: {art['url']}\n\n{art['content']}\n\n---\n\n"
        else:
            blocks += f"### Artikel {i} — GAGAL DIAMBIL\nURL: {art['url']}\n\n---\n\n"

    topic_line = f"Topik utama yang difokuskan: **{topic}**\n" if topic else ""

    return f"""Kamu content strategist TikTok untuk audiens Indonesia.
{topic_line}
Analisis artikel berikut dan buat content brief yang actionable.

{blocks}
---

Output dalam Markdown. Struktur wajib:

## Ringkasan Berita
Fakta kunci per artikel. Max 2 kalimat per artikel. Langsung ke poin.

## Content Angles
3–5 sudut pandang untuk TikTok Indonesia.
Format per angle:
**[Nama angle]** — [1 kalimat kenapa ini menarik]

## Hook Ideas
7 kalimat pembuka video. Bahasa Indonesia sehari-hari.
Variasi: pertanyaan / fakta mengejutkan / statement provokatif.
Tiap hook max 15 kata.

## Script Outline
Untuk 2 angle terbaik, buat outline:
**[Nama angle]**
- Pembuka (0–15 dtk): [hook + konteks]
- Isi (15–50 dtk): [poin 1] → [poin 2] → [poin 3]
- Penutup (50–60 dtk): [CTA atau takeaway]

## Hashtag
15 hashtag relevan. Campur: niche + Indonesia + broad.

---
Aturan penulisan:
- Bahasa Indonesia
- Hindari: "adalah", "merupakan", "ini adalah", "the", "hal ini"
- Langsung ke poin tanpa basa-basi
"""


# ---------------------------------------------------------------------------
# Claude call
# ---------------------------------------------------------------------------

def generate_brief(articles: list[dict], topic: str) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2500,
        messages=[{"role": "user", "content": build_prompt(articles, topic)}],
    )
    return message.content[0].text


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def save_report(brief: str, articles: list[dict], topic: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    label = topic.replace(" ", "-").lower() if topic else "brief"
    os.makedirs("reports", exist_ok=True)
    path = f"reports/news-brief-{label}-{ts}.md"

    header = (
        f"# News Brief — {topic or 'Update'}\n"
        f"Dibuat: {datetime.now().strftime('%d %B %Y, %H:%M')} WIB  \n"
        f"Sumber: {len(articles)} artikel\n\n"
    )

    sources = "## Sumber\n"
    for art in articles:
        icon = "✓" if art["ok"] else "✗"
        label_text = art["title"] or art["url"]
        sources += f"- {icon} [{label_text}]({art['url']})\n"

    with open(path, "w", encoding="utf-8") as f:
        f.write(header + sources + "\n---\n\n" + brief)

    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate TikTok content brief from news articles")
    parser.add_argument("--urls", required=True, help="Comma-separated article URLs")
    parser.add_argument("--topic", default="", help="Topic label for the report filename")
    args = parser.parse_args()

    urls = [u.strip() for u in args.urls.split(",") if u.strip()]
    if not urls:
        print("Error: tidak ada URL yang diberikan.")
        sys.exit(1)

    print(f"Fetching {len(urls)} artikel...")
    articles = [fetch_article(url) for url in urls]

    ok_count = sum(1 for a in articles if a["ok"])
    print(f"  Berhasil: {ok_count}/{len(urls)}")

    if ok_count == 0:
        print("Error: semua artikel gagal di-fetch.")
        sys.exit(1)

    print("Generating brief dengan Claude...")
    brief = generate_brief(articles, args.topic)

    path = save_report(brief, articles, args.topic)
    print(f"Laporan disimpan: {path}")


if __name__ == "__main__":
    main()
