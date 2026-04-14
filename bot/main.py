"""
bot/main.py — MINIMAL CALLBACK TEST
"""
import logging
import os
import traceback

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

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
    logger.info("START from user %s", update.effective_user.id)
    await update.message.reply_text("Halo! Mau riset apa?", reply_markup=MAIN_MENU)


async def catch_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = update.callback_query.data
    user_id = update.effective_user.id
    logger.info("CALLBACK RECEIVED user=%s data=%s", user_id, data)
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("button received: " + data)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("ERROR: %s", traceback.format_exc())


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(catch_all_callback))
    app.add_error_handler(on_error)

    logger.info("TEST BOT started pid=%s", os.getpid())
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"],
    )


if __name__ == "__main__":
    main()
