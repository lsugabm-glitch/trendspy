"""
bot/tiktok_flow.py — Conversation flow untuk TikTok on-demand research
"""

from dataclasses import dataclass, field
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackQueryHandler, MessageHandler, filters, ConversationHandler

import github_actions

# States (angka unik, tidak overlap dengan main.py)
TIKTOK_MODE = 10
TIKTOK_QUERY = 11
TIKTOK_QUALIFIER = 12


@dataclass
class TikTokHandler:
    entry: object = None
    states: dict = field(default_factory=dict)


def build_tiktok_handler() -> TikTokHandler:
    h = TikTokHandler()

    async def on_entry(update, context):
        query = update.callback_query
        await query.answer()
        keyboard = [
            [
                InlineKeyboardButton("🔤 Keyword", callback_data="mode_keyword"),
                InlineKeyboardButton("#️⃣ Hashtag", callback_data="mode_hashtag"),
                InlineKeyboardButton("👤 Profil", callback_data="mode_profile"),
            ]
        ]
        await query.edit_message_text(
            "Tipe query?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return TIKTOK_MODE

    async def on_mode(update, context):
        query = update.callback_query
        await query.answer()
        mode = query.data.replace("mode_", "")
        context.user_data["tiktok_mode"] = mode

        labels = {"keyword": "keyword", "hashtag": "hashtag (tanpa #)", "profile": "username TikTok (tanpa @)"}
        await query.edit_message_text(f"Masukkan {labels[mode]}:")
        return TIKTOK_QUERY

    async def on_query(update, context):
        raw = update.message.text.strip()
        context.user_data["tiktok_query"] = raw
        mode = context.user_data.get("tiktok_mode")

        if mode == "keyword":
            await update.message.reply_text(
                "Tambah konteks? Opsional — bantu filter hasil lebih relevan.\n"
                "Contoh: kalau keyword *Nadiem*, konteks bisa *Gojek founder*\n\n"
                "Ketik konteks atau kirim /skip",
                parse_mode="Markdown",
            )
            return TIKTOK_QUALIFIER
        else:
            # Hashtag dan profil tidak perlu qualifier
            await _run_tiktok(update, context, qualifier="")
            return ConversationHandler.END

    async def on_qualifier(update, context):
        qualifier = update.message.text.strip()
        if qualifier.startswith("/skip"):
            qualifier = ""
        await _run_tiktok(update, context, qualifier=qualifier)
        return ConversationHandler.END

    async def on_skip(update, context):
        await _run_tiktok(update, context, qualifier="")
        return ConversationHandler.END

    async def _run_tiktok(update, context, qualifier: str):
        query = context.user_data.get("tiktok_query", "")
        mode = context.user_data.get("tiktok_mode", "keyword")

        label = f"`{query}`" + (f" (konteks: _{qualifier}_)" if qualifier else "")
        msg = await update.message.reply_text(
            f"⏳ Memproses {label}...\nBiasanya 3–5 menit.",
            parse_mode="Markdown",
        )

        try:
            trigger_time = await github_actions.trigger_workflow(
                query=query,
                mode=mode,
                qualifier=qualifier,
            )

            run = await github_actions.poll_run(trigger_time)

            if run is None or run.get("conclusion") != "success":
                await msg.edit_text("❌ Workflow gagal atau timeout. Cek tab Actions di GitHub.")
                return

            await msg.edit_text("✅ Selesai! Mengambil laporan...")
            report = await github_actions.fetch_latest_report()

            if not report:
                await msg.edit_text("⚠️ Laporan tidak ditemukan. Cek folder `reports/` di GitHub.")
                return

            # Telegram max 4096 char per pesan
            await msg.delete()
            for chunk in _split(report, 4000):
                await update.message.reply_text(f"```\n{chunk}\n```", parse_mode="Markdown")

        except Exception as exc:
            await msg.edit_text(f"❌ Error: {exc}")

    h.entry = on_entry
    h.states = {
        TIKTOK_MODE: [CallbackQueryHandler(on_mode, pattern="^mode_")],
        TIKTOK_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_query)],
        TIKTOK_QUALIFIER: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, on_qualifier),
            MessageHandler(filters.Regex(r"^/skip$"), on_skip),
        ],
    }
    return h


def _split(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]
