"""
bot/news_flow.py — News brief flow (stateless, uses context.user_data)
"""

from telegram import Update
from telegram.ext import ContextTypes

import news_fetcher

STEP_URLS = "news_step_urls"


async def on_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User clicked Artikel button."""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    context.user_data["flow"] = "news"
    context.user_data["step"] = STEP_URLS
    await query.edit_message_text(
        "Paste URL artikel, satu per baris:\n\nContoh:\nhttps://cnnindonesia.com/..."
    )


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pasted URLs."""
    raw = update.message.text.strip()
    urls = [line.strip() for line in raw.splitlines() if line.strip().startswith("http")]

    if not urls:
        await update.message.reply_text("Tidak ada URL valid. Pastikan diawali https://")
        return

    context.user_data["step"] = ""
    msg = await update.message.reply_text(
        "Fetching " + str(len(urls)) + " artikel dan generating brief..."
    )

    try:
        brief, articles = await news_fetcher.generate_brief(urls)
        failed = [a for a in articles if not a["ok"]]
        header = "*News Brief* - " + str(len(articles)) + " artikel"
        if failed:
            header += " (" + str(len(failed)) + " gagal di-fetch)"

        await msg.edit_text(header, parse_mode="Markdown")

        for chunk in _split(brief, 4000):
            await update.message.reply_text("```\n" + chunk + "\n```", parse_mode="Markdown")

        if failed:
            fail_list = "\n".join("- " + a["url"] for a in failed)
            await update.message.reply_text("Gagal di-fetch:\n" + fail_list)

    except Exception as exc:
        await msg.edit_text("Error: " + str(exc))


def _split(text: str, size: int) -> list:
    return [text[i: i + size] for i in range(0, len(text), size)]
