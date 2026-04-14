"""
bot/tiktok_flow.py — TikTok research flow handlers
State machine via context.user_data["state"]:
  idle -> choose_mode -> enter_query -> (enter_qualifier ->) done
"""

import logging

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import ContextTypes

import github_actions

logger = logging.getLogger(__name__)

MODE_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("Keyword", callback_data="mode_keyword"),
        InlineKeyboardButton("Hashtag", callback_data="mode_hashtag"),
        InlineKeyboardButton("Profil", callback_data="mode_profile"),
    ]
])

MODE_LABELS = {
    "keyword": "keyword",
    "hashtag": "hashtag (tanpa #)",
    "profile": "username TikTok (tanpa @)",
}


async def handle_type_tiktok(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User tapped the TikTok button from the main menu."""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    context.user_data["state"] = "choose_mode"
    await query.edit_message_text("Tipe query?", reply_markup=MODE_KEYBOARD)


async def handle_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User tapped Keyword / Hashtag / Profil."""
    query = update.callback_query
    await query.answer()

    if context.user_data.get("state") != "choose_mode":
        # Stale button — restart gracefully
        context.user_data.clear()
        context.user_data["state"] = "choose_mode"
        await query.edit_message_text("Tipe query?", reply_markup=MODE_KEYBOARD)
        return

    mode = query.data.replace("mode_", "")
    context.user_data["mode"] = mode
    context.user_data["state"] = "enter_query"
    label = MODE_LABELS.get(mode, mode)
    await query.edit_message_text("Masukkan " + label + ":")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text input for enter_query and enter_qualifier states."""
    state = context.user_data.get("state")
    text = update.message.text.strip()

    if state == "enter_query":
        context.user_data["query"] = text
        mode = context.user_data.get("mode")
        if mode == "keyword":
            context.user_data["state"] = "enter_qualifier"
            await update.message.reply_text(
                "Tambah konteks? Opsional, bantu filter hasil.\n"
                "Ketik konteks atau kirim /skip"
            )
        else:
            await _trigger_and_report(update, context, qualifier="")

    elif state == "enter_qualifier":
        qualifier = "" if text.lower().startswith("/skip") else text
        await _trigger_and_report(update, context, qualifier=qualifier)


async def _trigger_and_report(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    qualifier: str,
) -> None:
    """Trigger GitHub Actions workflow and send back the report."""
    context.user_data["state"] = "idle"
    query_text = context.user_data.get("query", "")
    mode = context.user_data.get("mode", "keyword")

    label = "`" + query_text + "`"
    if qualifier:
        label += " (konteks: _" + qualifier + "_)"

    msg = await update.message.reply_text(
        "Memproses " + label + "... Biasanya 3-5 menit.",
        parse_mode="Markdown",
    )

    try:
        trigger_time = await github_actions.trigger_workflow(
            query=query_text,
            mode=mode,
            qualifier=qualifier,
        )
        run = await github_actions.poll_run(trigger_time)

        if run is None or run.get("conclusion") != "success":
            await msg.edit_text(
                "Workflow gagal atau timeout. Cek tab Actions di GitHub."
            )
            return

        await msg.edit_text("Selesai! Mengambil laporan...")
        report = await github_actions.fetch_latest_report()

        if not report:
            await msg.edit_text("Laporan tidak ditemukan di folder reports/.")
            return

        await msg.delete()
        for chunk in _chunks(report, 4000):
            await update.message.reply_text(
                "```\n" + chunk + "\n```", parse_mode="Markdown"
            )

    except Exception as exc:
        logger.exception("Error in _trigger_and_report")
        await msg.edit_text("Error: " + str(exc))


def _chunks(text: str, size: int):
    for i in range(0, len(text), size):
        yield text[i: i + size]
