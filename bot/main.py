"""
bot/main.py — TrendSpy Telegram bot entry point
"""

import logging
import os
import traceback

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

import tiktok_flow
import news_flow

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

MAIN_MENU = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("TikTok", callback_data="type_tiktok"),
        InlineKeyboardButton("Artikel", callback_data="type_news"),
    ]
])


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    context.user_data["state"] = "idle"
    await update.message.reply_text("Halo! Mau riset apa?", reply_markup=MAIN_MENU)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data
    state = context.user_data.get("state", "idle")
    logger.info("CALLBACK user=%s data=%s state=%s", update.effective_user.id, data, state)

    if data == "type_tiktok":
        await tiktok_flow.handle_type_tiktok(update, context)
    elif data == "type_news":
        await news_flow.handle_type_news(update, context)
    elif data.startswith("mode_"):
        await tiktok_flow.handle_mode(update, context)
    else:
        await query.answer()


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get("state", "idle")
    logger.info("MESSAGE user=%s state=%s text=%r", update.effective_user.id, state, update.message.text[:40])

    if state in ("enter_query", "enter_qualifier"):
        await tiktok_flow.handle_text(update, context)
    elif state == "enter_urls":
        await news_flow.handle_urls(update, context)
    else:
        await update.message.reply_text("Ketik /start untuk mulai.", reply_markup=MAIN_MENU)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception:\n%s", traceback.format_exc())


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_error_handler(on_error)

    logger.info("Bot started (pid=%s)", os.getpid())
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
