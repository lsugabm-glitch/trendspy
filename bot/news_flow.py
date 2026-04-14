"""
bot/news_flow.py — News brief flow handlers
State machine via context.user_data["state"]:
  idle -> enter_urls -> done
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

import news_fetcher

logger = logging.getLogger(__name__)


async def handle_type_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User tapped the Artikel button from the main menu."""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    context.user_data["state"] = "enter_urls"
    await query.edit_message_text(
        "Paste URL artikel, satu per baris:\n\n"
        "Contoh:\n"
        "https://cnnindonesia.com/...\n"
        "https://detik.com/..."
    )


async def handle_urls(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User sent one or more URLs."""
    raw = update.message.text.strip()
    urls = [
        line.strip()
        for line in raw.splitlines()
        if line.strip().startswith("http")
    ]

    if not urls:
        await update.message.reply_text(
            "Tidak ada URL valid. Pastikan diawali https://"
        )
        return

    context.user_data["state"] = "idle"
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

        for chunk in _chunks(brief, 4000):
            await update.message.reply_text(
                "```\n" + chunk + "\n```", parse_mode="Markdown"
            )

        if failed:
            fail_list = "\n".join("- " + a["url"] for a in failed)
            await update.message.reply_text("Gagal di-fetch:\n" + fail_list)

    except Exception as exc:
        logger.exception("Error in handle_urls")
        await msg.edit_text("Error: " + str(exc))


def _chunks(text: str, size: int):
    for i in range(0, len(text), size):
        yield text[i: i + size]
