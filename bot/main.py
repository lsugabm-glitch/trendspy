"""
bot/main.py — Entry point Telegram bot TrendSpy
"""

import logging
import os

from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, ConversationHandler, MessageHandler, filters, CallbackQueryHandler

from tiktok_flow import build_tiktok_handler
from news_flow import build_news_handler, NEWS_ENTRY

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Top-level states
CHOOSE_TYPE = 0


async def start(update, context):
    keyboard = [
        [
            InlineKeyboardButton("🔍 TikTok", callback_data="type_tiktok"),
            InlineKeyboardButton("📰 Artikel", callback_data="type_news"),
        ]
    ]
    # Handle both message and callback_query entry points
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            "Halo! Mau riset apa?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        await update.message.reply_text(
            "Halo! Mau riset apa?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    return CHOOSE_TYPE


async def cancel(update, context):
    await update.message.reply_text("Dibatalkan. Ketik /start untuk mulai lagi.")
    return ConversationHandler.END


def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    tiktok_handler = build_tiktok_handler()
    news_handler = build_news_handler()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            # Also handle button clicks as entry points so the bot works after restarts
            CallbackQueryHandler(tiktok_handler.entry, pattern="^type_tiktok$"),
            CallbackQueryHandler(news_handler.entry, pattern="^type_news$"),
        ],
        states={
            CHOOSE_TYPE: [
                CallbackQueryHandler(tiktok_handler.entry, pattern="^type_tiktok$"),
                CallbackQueryHandler(news_handler.entry, pattern="^type_news$"),
            ],
            **tiktok_handler.states,
            **news_handler.states,
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=False,
        allow_reentry=True,
    )

    app.add_handler(conv)
    logger.info("Bot berjalan...")
    app.run_polling()


if __name__ == "__main__":
    main()
