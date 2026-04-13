"""
bot/main.py — Entry point Telegram bot TrendSpy
"""

import logging
import os

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
            {"text": "🔍 TikTok", "callback_data": "type_tiktok"},
            {"text": "📰 Artikel", "callback_data": "type_news"},
        ]
    ]
    from telegram import InlineKeyboardMarkup
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
        entry_points=[CommandHandler("start", start)],
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
    )

    app.add_handler(conv)
    logger.info("Bot berjalan...")
    app.run_polling()


if __name__ == "__main__":
    main()
