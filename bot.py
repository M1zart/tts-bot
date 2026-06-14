import logging
import io

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config import (
    TELEGRAM_BOT_TOKEN,
    AVAILABLE_VOICES,
    MIN_SPEED,
    MAX_SPEED,
)
from db import init_db, get_user_settings, set_user_voice, set_user_speed
from tts.google_tts import synthesize_text

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Пришли или перешли мне любой текст — озвучу голосом.\n\n"
        "Команды:\n"
        "/voice — выбрать голос\n"
        "/speed 1.2 — настроить скорость (от 0.5 до 2.0)\n"
        "/settings — текущие настройки"
    )


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    settings = get_user_settings(user_id)
    voice_label = AVAILABLE_VOICES[settings["voice_key"]]["label"]
    await update.message.reply_text(
        f"Текущие настройки:\n"
        f"Голос: {voice_label}\n"
        f"Скорость: {settings['speed']}x"
    )


async def voice_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    for key, info in AVAILABLE_VOICES.items():
        keyboard.append(
            [InlineKeyboardButton(info["label"], callback_data=f"voice:{key}")]
        )
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выбери голос:", reply_markup=reply_markup)


async def voice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    voice_key = query.data.split(":", 1)[1]

    if voice_key not in AVAILABLE_VOICES:
        await query.answer("Неизвестный голос")
        return

    set_user_voice(user_id, voice_key)
    await query.answer("Голос обновлён")
    await query.edit_message_text(
        f"Голос установлен: {AVAILABLE_VOICES[voice_key]['label']}"
    )


async def speed_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not context.args:
        settings = get_user_settings(user_id)
        await update.message.reply_text(
            f"Текущая скорость: {settings['speed']}x\n"
            f"Использование: /speed 1.25 (от {MIN_SPEED} до {MAX_SPEED})"
        )
        return

    try:
        speed = float(context.args[0])
    except ValueError:
        await update.message.reply_text("Скорость должна быть числом, например /speed 1.25")
        return

    if not (MIN_SPEED <= speed <= MAX_SPEED):
        await update.message.reply_text(
            f"Скорость должна быть от {MIN_SPEED} до {MAX_SPEED}"
        )
        return

    set_user_speed(user_id, speed)
    await update.message.reply_text(f"Скорость установлена: {speed}x")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if not text or not text.strip():
        return

    settings = get_user_settings(user_id)

    status_msg = await update.message.reply_text("Озвучиваю...")

    try:
        audio_bytes = await synthesize_text(
            text=text,
            voice_key=settings["voice_key"],
            speed=settings["speed"],
        )
    except Exception as e:
        logger.exception("TTS synthesis failed")
        await status_msg.edit_text(f"Ошибка при озвучке: {e}")
        return

    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = "speech.mp3"

    await update.message.reply_audio(audio=audio_file)
    await status_msg.delete()


def main():
    init_db()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("voice", voice_cmd))
    app.add_handler(CommandHandler("speed", speed_cmd))
    app.add_handler(CallbackQueryHandler(voice_callback, pattern=r"^voice:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
