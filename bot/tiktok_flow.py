"""
bot/tiktok_flow.py — TikTok research flow (stateless, uses context.user_data)
"""

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import ContextTypes

import github_actions

STEP_MODE = "tiktok_step_mode"
STEP_QUERY = "tiktok_step_query"
STEP_QUALIFIER = "tiktok_step_qualifier"

MODE_LABELS = {
    "keyword": "keyword",
    "hashtag": "hashtag (tanpa #)",
    "profile": "username TikTok (tanpa @)",
}

MODE_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("Keyword", callback_data="mode_keyword"),
        InlineKeyboardButton("Hashtag", callback_data="mode_hashtag"),
        InlineKeyboardButton("Profil", callback_data="mode_profile"),
    ]
])


async def on_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User clicked TikTok button."""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    context.user_data["flow"] = "tiktok"
    context.user_data["step"] = STEP_MODE
    await query.edit_message_text("Tipe query?", reply_markup=MODE_KEYBOARD)


async def on_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User clicked a mode button (keyword/hashtag/profile)."""
    query = update.callback_query
    await query.answer()
    mode = query.data.replace("mode_", "")
    context.user_data["tiktok_mode"] = mode
    context.user_data["step"] = STEP_QUERY
    label = MODE_LABELS.get(mode, mode)
    await query.edit_message_text("Masukkan " + label + ":")


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages for query and qualifier steps."""
    step = context.user_data.get("step")
    text = update.message.text.strip()

    if step == STEP_QUERY:
        context.user_data["tiktok_query"] = text
        mode = context.user_data.get("tiktok_mode")
        if mode == "keyword":
            context.user_data["step"] = STEP_QUALIFIER
            await update.message.reply_text(
                "Tambah konteks? Opsional.\nKetik konteks atau /skip",
                parse_mode="Markdown",
            )
        else:
            await _run(update, context, qualifier="")

    elif step == STEP_QUALIFIER:
        qualifier = "" if text.startswith("/skip") else text
        await _run(update, context, qualifier=qualifier)


async def _run(update: Update, context: ContextTypes.DEFAULT_TYPE, qualifier: str):
    context.user_data["step"] = ""
    query_text = context.user_data.get("tiktok_query", "")
    mode = context.user_data.get("tiktok_mode", "keyword")

    label = "`" + query_text + "`"
    if qualifier:
        label += " (konteks: _" + qualifier + "_)"
    msg = await update.message.reply_text(
        "Memproses " + label + "... Biasanya 3-5 menit.",
        parse_mode="Markdown",
    )

    try:
        trigger_time = await github_actions.trigger_workflow(
            query=query_text, mode=mode, qualifier=qualifier
        )
        run = await github_actions.poll_run(trigger_time)

        if run is None or run.get("conclusion") != "success":
            await msg.edit_text("Workflow gagal atau timeout. Cek tab Actions di GitHub.")
            return

        await msg.edit_text("Selesai! Mengambil laporan...")
        report = await github_actions.fetch_latest_report()

        if not report:
            await msg.edit_text("Laporan tidak ditemukan.")
            return

        await msg.delete()
        for chunk in _split(report, 4000):
            await update.message.reply_text("```\n" + chunk + "\n```", parse_mode="Markdown")

    except Exception as exc:
        await msg.edit_text("Error: " + str(exc))


def _split(text: str, size: int) -> list:
    return [text[i: i + size] for i in range(0, len(text), size)]
