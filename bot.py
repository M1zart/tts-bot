import logging
import io
import asyncio

from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
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
    API_SECRET,
    PORT,
    OWNER_CHAT_ID,
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


async def synthesize_and_send(bot, chat_id: int, text: str, user_id: int):
    """Синтезирует текст в аудио и отправляет в указанный чат."""
    settings = get_user_settings(user_id)

    audio_bytes = await synthesize_text(
        text=text,
        voice_key=settings["voice_key"],
        speed=settings["speed"],
    )

    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = "speech.mp3"

    await bot.send_audio(chat_id=chat_id, audio=audio_file)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = update.message.text

    if not text or not text.strip():
        return

    status_msg = await update.message.reply_text("Озвучиваю...")

    try:
        await synthesize_and_send(context.bot, chat_id, text, user_id)
    except Exception as e:
        logger.exception("TTS synthesis failed")
        await status_msg.edit_text(f"Ошибка при озвучке: {e}")
        return

    await status_msg.delete()


async def handle_speak_request(request: web.Request) -> web.Response:
    """HTTP-эндпоинт для браузерного расширения: POST /speak"""
    if not API_SECRET:
        return web.json_response({"ok": False, "error": "API_SECRET not configured"}, status=500)

    auth_header = request.headers.get("Authorization", "")
    expected = f"Bearer {API_SECRET}"
    if auth_header != expected:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)

    if not OWNER_CHAT_ID:
        return web.json_response({"ok": False, "error": "OWNER_CHAT_ID not configured"}, status=500)

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)

    text = data.get("text", "").strip()
    if not text:
        return web.json_response({"ok": False, "error": "empty text"}, status=400)

    bot = request.app["bot"]
    chat_id = int(OWNER_CHAT_ID)

    try:
        await synthesize_and_send(bot, chat_id, text, chat_id)
    except Exception as e:
        logger.exception("HTTP TTS synthesis failed")
        return web.json_response({"ok": False, "error": str(e)}, status=500)

    return web.json_response({"ok": True})


async def handle_speak_audio_request(request: web.Request) -> web.Response:
    """HTTP-эндпоинт для браузерного расширения: POST /speak_audio
    Возвращает MP3-аудио напрямую в ответе, без отправки в Telegram."""
    if not API_SECRET:
        return web.json_response({"ok": False, "error": "API_SECRET not configured"}, status=500)

    auth_header = request.headers.get("Authorization", "")
    expected = f"Bearer {API_SECRET}"
    if auth_header != expected:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)

    text = data.get("text", "").strip()
    if not text:
        return web.json_response({"ok": False, "error": "empty text"}, status=400)

    # Используем настройки владельца (если OWNER_CHAT_ID задан), иначе дефолтные
    user_id = int(OWNER_CHAT_ID) if OWNER_CHAT_ID else 0
    settings = get_user_settings(user_id)

    try:
        audio_bytes = await synthesize_text(
            text=text,
            voice_key=settings["voice_key"],
            speed=settings["speed"],
        )
    except Exception as e:
        logger.exception("HTTP TTS synthesis (audio) failed")
        return web.json_response({"ok": False, "error": str(e)}, status=500)

    return web.Response(
        body=audio_bytes,
        content_type="audio/mpeg",
        headers={"Access-Control-Allow-Origin": "*"},
    )


async def handle_options(request: web.Request) -> web.Response:
    return web.Response(
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }
    )


async def run_web_server(bot):
    app = web.Application()
    app["bot"] = bot
    app.router.add_post("/speak", handle_speak_request)
    app.router.add_post("/speak_audio", handle_speak_audio_request)
    app.router.add_options("/speak_audio", handle_options)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"HTTP server started on port {PORT}")


async def post_init(application):
    await application.bot.set_my_commands([
        BotCommand("start", "Начало работы"),
        BotCommand("voice", "Выбрать голос"),
        BotCommand("speed", "Настроить скорость"),
        BotCommand("settings", "Текущие настройки"),
    ])


async def run_bot():
    init_db()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("voice", voice_cmd))
    app.add_handler(CommandHandler("speed", speed_cmd))
    app.add_handler(CallbackQueryHandler(voice_callback, pattern=r"^voice:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot starting...")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    await run_web_server(app.bot)

    # Держим процесс живым
    await asyncio.Event().wait()


def main():
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
