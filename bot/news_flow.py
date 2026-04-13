"""
bot/news_flow.py — Conversation flow untuk News Brief (inline, tanpa Actions)
"""

from dataclasses import dataclass, field
from telegram.ext import MessageHandler, filters, ConversationHandler, CallbackQueryHandler

import news_fetcher

# States
NEWS_ENTRY = 20
NEWS_URLS = 21


@dataclass
class NewsHandler:
    entry: object = None
    states: dict = field(default_factory=dict)


def build_news_handler() -> NewsHandler:
    h = NewsHandler()

    async def on_entry(update, context):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            "Paste URL artikel — satu per baris, bisa lebih dari satu:\n\n"
            "Contoh:\n"
            "https://cnnindonesia.com/...\n"
            "https://detik.com/..."
        )
        return NEWS_URLS

    async def on_urls(update, context):
        raw = update.message.text.strip()
        urls = [line.strip() for line in raw.splitlines() if line.strip().startswith("http")]

        if not urls:
            await update.message.reply_text("Tidak ada URL valid. Pastikan diawali https://")
            return NEWS_URLS

        msg = await update.message.reply_text(
            f"⏳ Fetching {len(urls)} artikel dan generating brief..."
        )

        try:
            brief, articles = await news_fetcher.generate_brief(urls)

            failed = [a for a in articles if not a["ok"]]
            header = f"📰 *News Brief* — {len(articles)} artikel"
            if failed:
                header += f" ({len(failed)} gagal di-fetch)"

            await msg.edit_text(header, parse_mode="Markdown")

            # Kirim brief dalam chunks
            for chunk in _split(brief, 4000):
                await update.message.reply_text(f"```\n{chunk}\n```", parse_mode="Markdown")

            if failed:
                fail_list = "\n".join(f"• {a['url']}" for a in failed)
                await update.message.reply_text(f"⚠️ Gagal di-fetch:\n{fail_list}")

        except Exception as exc:
            await msg.edit_text(f"❌ Error: {exc}")

        return ConversationHandler.END

    h.entry = on_entry
    h.states = {
        NEWS_ENTRY: [],
        NEWS_URLS: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_urls)],
    }
    return h


def _split(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]
