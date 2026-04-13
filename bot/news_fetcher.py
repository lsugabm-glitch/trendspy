"""
bot/news_fetcher.py — Fetch artikel + generate brief via Claude (inline, tanpa Actions)
"""

import os
import anthropic
import httpx
from bs4 import BeautifulSoup


async def fetch_article(url: str) -> dict:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.get(url, headers=headers)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
            tag.decompose()

        title = ""
        if soup.find("h1"):
            title = soup.find("h1").get_text(strip=True)
        elif soup.find("title"):
            title = soup.find("title").get_text(strip=True)

        article_tag = soup.find("article")
        if article_tag:
            content = article_tag.get_text(separator="\n", strip=True)
        else:
            paragraphs = soup.find_all("p")
            content = "\n".join(
                p.get_text(strip=True) for p in paragraphs
                if len(p.get_text(strip=True)) > 60
            )

        return {"url": url, "title": title, "content": content[:4000], "ok": True}

    except Exception as exc:
        return {"url": url, "title": "", "content": "", "ok": False, "error": str(exc)}


def _build_prompt(articles: list[dict]) -> str:
    blocks = ""
    for i, art in enumerate(articles, 1):
        if art["ok"]:
            blocks += f"### Artikel {i} — {art['title']}\nURL: {art['url']}\n\n{art['content']}\n\n---\n\n"
        else:
            blocks += f"### Artikel {i} — GAGAL\nURL: {art['url']}\nError: {art.get('error','')}\n\n---\n\n"

    return f"""Kamu content strategist TikTok untuk audiens Indonesia.

Analisis artikel berikut. Nilai potensi viral tiap berita — termasuk berita yang tampak biasa, cari angle yang bisa membuatnya menarik.

{blocks}
---

Output Markdown. Struktur wajib:

## Ringkasan Berita
Fakta kunci per artikel. Max 2 kalimat per artikel.

## Potensi Konten
Nilai tiap berita: ⚡ Tinggi / 🔶 Sedang / 🔵 Bisa diangkat dengan framing tepat
Sertakan alasan 1 kalimat per berita.

## Content Angles
3–5 sudut pandang untuk TikTok Indonesia.
**[Nama angle]** — [kenapa menarik, 1 kalimat]

## Hook Ideas
7 kalimat pembuka video. Bahasa Indonesia sehari-hari.
Variasi: pertanyaan / fakta mengejutkan / statement provokatif. Max 15 kata per hook.

## Script Outline
2 angle terbaik:
**[Nama angle]**
- Pembuka (0–15 dtk): hook + konteks
- Isi (15–50 dtk): poin 1 → poin 2 → poin 3
- Penutup (50–60 dtk): CTA atau takeaway

## Hashtag
15 hashtag relevan. Campur niche + Indonesia + broad.

---
Aturan: Bahasa Indonesia. Hindari "adalah", "merupakan", "hal ini". Langsung ke poin.
"""


async def generate_brief(urls: list[str]) -> tuple[str, list[dict]]:
    """Fetch articles and generate brief. Returns (markdown_text, articles)."""
    import asyncio
    articles = await asyncio.gather(*[fetch_article(u) for u in urls])
    articles = list(articles)

    ok = [a for a in articles if a["ok"]]
    if not ok:
        return "❌ Semua artikel gagal di-fetch. Coba URL lain.", articles

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2500,
        messages=[{"role": "user", "content": _build_prompt(articles)}],
    )
    return message.content[0].text, articles
