"""
bot/main.py — Entry point Telegram bot TrendSpy
"""

import logging
import os
import traceback

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ContextTypes,
)

import tiktok_flow
import news_flow

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.DEBUG,
)
logger = logging.getLogger(__name__)

MAIN_MENU = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("🔍 TikTok", callback_data="type_tiktok"),
        InlineKeyboardButton("📰 Artikel", callback_data="type_news"),
    ]
])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("START command from user %s", update.effective_user.id)
    context.user_data.clear()
    await update.message.reply_text("Halo! Mau riset apa?", reply_markup=MAIN_MENU)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    user_id = update.effective_user.id
    logger.info("CALLBACK from user %s: data=%s", user_id, data)

    if data == "type_tiktok":
        await tiktok_flow.on_entry(update, context)
    elif data == "type_news":
        await news_flow.on_entry(update, context)
    elif data.startswith("mode_"):
        await tiktok_flow.on_mode(update, context)
    else:
        await update.callback_query.answer()


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("step", "")
    user_id = update.effective_user.id
    logger.info("MESSAGE from user %s: step=%s text=%s", user_id, step, update.message.text[:30])

    if step in (tiktok_flow.STEP_QUERY, tiktok_flow.STEP_QUALIFIER):
        await tiktok_flow.on_message(update, context)
    elif step == news_flow.STEP_URLS:
        await news_flow.on_message(update, context)
    else:
        await update.message.reply_text(
            "Ketik /start untuk mulai.", reply_markup=MAIN_MENU
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled exception:\n%s", traceback.format_exc())


def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info("Bot berjalan... instance_id=%s", os.getpid())
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
